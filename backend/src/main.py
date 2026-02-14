from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from src.api.auth import router as auth_router
from src.api.games import router as games_router
from src.api.matches import router as matches_router
from src.api.rooms import router as rooms_router
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
    logger.info("Database tables ensured")

    # Initialize Redis
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    app.state.redis = redis

    # Initialize plugin registry
    registry = PluginRegistry()
    registry.auto_discover()
    app.state.registry = registry
    logger.info(f"Loaded {len(registry.list_games())} game plugins")

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
    )
    app.state.session_manager = session_manager

    # Recover sessions
    recovered = await session_manager.recover_sessions()
    logger.info(f"Recovered {recovered} active sessions")

    logger.info("Server startup complete")

    yield

    # Shutdown
    logger.info("Shutting down meeple.cat server...")
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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(games_router, prefix="/api/v1")
    app.include_router(matches_router, prefix="/api/v1")
    app.include_router(rooms_router, prefix="/api/v1")
    app.include_router(ws_router)

    return app


app = create_app()
