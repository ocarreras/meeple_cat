from __future__ import annotations

import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import text

from src.api.admin import router as admin_router
from src.api.auth import router as auth_router
from src.api.health import router as health_router
from src.api.games import router as games_router
from src.api.matches import router as matches_router
from src.api.rooms import router as rooms_router
from src.api.users import router as users_router
from src.auth.routes import router as oidc_auth_router
from src.config import settings
from src.engine.bot_runner import BotRunner
from src.engine.registry import PluginRegistry
from src.engine.session_manager import GameSessionManager
from src.engine.state_store import StateStore
from src.models.base import Base
from src.models.database import async_session_factory, engine
import src.models.user  # noqa: F401
import src.models.match  # noqa: F401
import src.models.room  # noqa: F401
import src.auth.models  # noqa: F401
from src.ws.broadcaster import Broadcaster
from src.ws.connection_manager import ConnectionManager
from src.ws.handler import router as ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting up meeple.cat server...")

    # Create database tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Migrate existing tables: add columns that create_all won't add to existing tables
    # Uses IF NOT EXISTS to avoid aborting the transaction on already-existing columns
    async with engine.begin() as conn:
        for stmt in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_guest BOOLEAN DEFAULT true",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT false",
        ]:
            try:
                await conn.execute(text(stmt))
                logger.info(f"Migration applied: {stmt}")
            except Exception:
                pass  # Column already exists
    logger.info("Database tables ensured")

    # Initialize Redis
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    app.state.redis = redis

    # Initialize plugin registry (all game logic provided by Rust engine via gRPC)
    registry = PluginRegistry()
    registry.connect_grpc(settings.game_engine_grpc_url)
    logger.info(f"Connected to Rust game engine at {settings.game_engine_grpc_url}")
    app.state.registry = registry
    logger.info(f"Loaded {len(registry.list_games())} game plugins")

    # Register difficulty-tier MCTS bot strategies backed by Rust engine.
    # Each difficulty maps to a named profile in bot_profiles.toml on the Rust side.
    # Games without MCTS support (e.g. einstein_dojo) fall back to a game-specific
    # random strategy.
    from src.engine.bot_strategy import register_strategy, GrpcMctsStrategy, EinsteinDojoRandomStrategy
    grpc_url = settings.game_engine_grpc_url

    _GAME_SPECIFIC_STRATEGIES: dict[str, type] = {
        "einstein_dojo": EinsteinDojoRandomStrategy,
    }

    for difficulty in ("easy", "medium", "hard"):
        def _make_factory(diff: str) -> object:
            def factory(game_id="carcassonne", **kw):
                if game_id in _GAME_SPECIFIC_STRATEGIES:
                    return _GAME_SPECIFIC_STRATEGIES[game_id]()
                return GrpcMctsStrategy(
                    grpc_address=grpc_url, game_id=game_id, bot_profile=diff, **kw,
                )
            return factory
        register_strategy(f"mcts-{difficulty}", _make_factory(difficulty))

    # Backward compat: "mcts" → hard profile
    def _mcts_fallback(game_id="carcassonne", **kw):
        if game_id in _GAME_SPECIFIC_STRATEGIES:
            return _GAME_SPECIFIC_STRATEGIES[game_id]()
        return GrpcMctsStrategy(
            grpc_address=grpc_url, game_id=game_id, bot_profile="hard", **kw,
        )
    register_strategy("mcts", _mcts_fallback)

    # Initialize connection manager and broadcaster
    cm = ConnectionManager()
    app.state.connection_manager = cm
    broadcaster = Broadcaster(cm)

    # Initialize state store
    state_store = StateStore(redis)
    app.state.db_session_factory = async_session_factory

    # Initialize bot runner and session manager
    bot_runner = BotRunner(db_session_factory=async_session_factory)
    session_manager = GameSessionManager(
        registry=registry,
        state_store=state_store,
        broadcaster=broadcaster,
        db_session_factory=async_session_factory,
        bot_runner=bot_runner,
        grace_period_seconds=settings.disconnect_grace_period_seconds,
    )
    app.state.session_manager = session_manager

    # Recover sessions
    recovered = await session_manager.recover_sessions()
    logger.info(f"Recovered {recovered} active sessions")

    # Clean up stale matches (no Redis state, older than 24h)
    cleaned = await session_manager.cleanup_stale_matches()
    if cleaned:
        logger.info(f"Cleaned up {cleaned} stale matches")

    logger.info("Server startup complete")

    yield

    # Shutdown
    logger.info("Shutting down meeple.cat server...")

    # Close all WebSocket connections gracefully so clients trigger reconnection
    for match_id in list(cm._players.keys()):
        for player_id, ws in list(cm._players.get(match_id, {}).items()):
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                pass
        for ws in list(cm._spectators.get(match_id, [])):
            try:
                await ws.close(code=1001, reason="Server shutting down")
            except Exception:
                pass

    await redis.close()
    await engine.dispose()
    logger.info("Server shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="meeple.cat",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(oidc_auth_router, prefix="/api/v1")
    app.include_router(games_router, prefix="/api/v1")
    app.include_router(matches_router, prefix="/api/v1")
    app.include_router(rooms_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(ws_router)
    app.include_router(health_router)

    return app


app = create_app()
