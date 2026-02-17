from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.engine.registry import PluginRegistry
from src.engine.session_manager import GameSessionManager
from src.engine.state_store import StateStore
from src.models.base import Base
from src.models.database import get_db
from src.ws.broadcaster import Broadcaster
from src.ws.connection_manager import ConnectionManager


@pytest.fixture
async def test_db_engine():
    """Create a test database engine using in-memory SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_db_session_factory(test_db_engine):
    """Create a test async session factory."""
    factory = async_sessionmaker(
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


@pytest.fixture
async def test_db_session(test_db_session_factory):
    """Create a test database session."""
    async with test_db_session_factory() as session:
        yield session


class FakeRedis:
    """In-memory fake Redis for tests (avoids requiring real Redis)."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    async def set(self, key: str, value: str | bytes, **kwargs) -> None:
        if isinstance(value, str):
            value = value.encode("utf-8")
        self._store[key] = value

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._store.pop(key, None)

    async def scan_iter(self, match: str = "*"):
        import fnmatch
        for key in list(self._store.keys()):
            if fnmatch.fnmatch(key, match):
                yield key

    async def flushdb(self) -> None:
        self._store.clear()

    async def close(self) -> None:
        pass


@pytest.fixture
def test_redis():
    """Create a fake Redis for tests."""
    return FakeRedis()


@pytest.fixture
def test_registry():
    """Create a test plugin registry with a mock game plugin."""
    from tests.engine.test_registry import MockPlugin

    registry = PluginRegistry()
    registry.register(MockPlugin())
    return registry


@pytest.fixture
async def app(test_db_engine, test_db_session_factory, test_redis, test_registry):
    """Create a test FastAPI application with test dependencies."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from src.api.auth import router as auth_router
    from src.api.games import router as games_router
    from src.api.matches import router as matches_router
    from src.ws.handler import router as ws_router

    # Create app without real lifespan (we set up state manually)
    @asynccontextmanager
    async def test_lifespan(app: FastAPI):
        yield

    test_app = FastAPI(title="meeple.cat-test", lifespan=test_lifespan)

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    test_app.include_router(auth_router, prefix="/api/v1")
    test_app.include_router(games_router, prefix="/api/v1")
    test_app.include_router(matches_router, prefix="/api/v1")
    test_app.include_router(ws_router)

    # Override DB dependency
    async def override_get_db():
        async with test_db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    test_app.dependency_overrides[get_db] = override_get_db

    # Set up app state
    test_app.state.redis = test_redis
    test_app.state.registry = test_registry
    test_app.state.db_session_factory = test_db_session_factory

    cm = ConnectionManager()
    test_app.state.connection_manager = cm
    broadcaster = Broadcaster(cm)

    state_store = StateStore(test_redis)
    session_manager = GameSessionManager(
        registry=test_registry,
        state_store=state_store,
        broadcaster=broadcaster,
        db_session_factory=test_db_session_factory,
    )
    test_app.state.session_manager = session_manager

    yield test_app

    test_app.dependency_overrides.clear()


@pytest.fixture
async def client(app):
    """Create a test HTTP client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
