from __future__ import annotations

import secrets

from redis.asyncio import Redis


async def create_ws_ticket(redis: Redis, user_id: str, display_name: str) -> str:
    """Create a single-use, 30-second WebSocket ticket stored in Redis."""
    ticket = secrets.token_urlsafe(32)
    await redis.setex(f"ws_ticket:{ticket}", 30, f"{user_id}:{display_name}".encode())
    return ticket


async def validate_ws_ticket(redis: Redis, ticket: str) -> tuple[str, str] | None:
    """Validate and consume a WebSocket ticket. Returns (user_id, display_name) or None."""
    value = await redis.getdel(f"ws_ticket:{ticket}")
    if not value:
        return None
    decoded = value.decode()
    user_id, display_name = decoded.split(":", 1)
    return user_id, display_name
