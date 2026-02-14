from __future__ import annotations

from typing import Protocol

from src.engine.models import GameState, MatchId


class StateStoreProtocol(Protocol):
    """Protocol for hot state persistence (Redis)."""

    async def save_state(self, state: GameState) -> None:
        """Save game state to Redis."""
        ...

    async def load_state(self, match_id: MatchId) -> GameState | None:
        """Load game state from Redis."""
        ...

    async def delete_state(self, match_id: MatchId) -> None:
        """Delete game state from Redis."""
        ...

    async def list_active_matches(self) -> list[str]:
        """List all active match IDs in Redis."""
        ...


class StateStore:
    """Redis-backed state store implementation."""

    KEY_PREFIX = "game_state:"

    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    async def save_state(self, state: GameState) -> None:
        """Save game state to Redis."""
        key = f"{self.KEY_PREFIX}{state.match_id}"
        value = state.model_dump_json()
        await self.redis.set(key, value)

    async def load_state(self, match_id: MatchId) -> GameState | None:
        """Load game state from Redis."""
        key = f"{self.KEY_PREFIX}{match_id}"
        data = await self.redis.get(key)
        if data is None:
            return None
        return GameState.model_validate_json(data)

    async def delete_state(self, match_id: MatchId) -> None:
        """Delete game state from Redis."""
        key = f"{self.KEY_PREFIX}{match_id}"
        await self.redis.delete(key)

    async def list_active_matches(self) -> list[str]:
        """List all active match IDs in Redis."""
        pattern = f"{self.KEY_PREFIX}*"
        keys = []
        async for key in self.redis.scan_iter(match=pattern):
            # Strip the prefix to get the match_id
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            match_id = key.replace(self.KEY_PREFIX, "")
            keys.append(match_id)
        return keys
