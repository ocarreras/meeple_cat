from __future__ import annotations

import pytest
from httpx import AsyncClient

from src.auth import decode_token


@pytest.mark.asyncio
async def test_get_token_creates_user(client: AsyncClient):
    """Test that POST /auth/token creates a user and returns a token."""
    response = await client.post(
        "/api/v1/auth/token",
        json={"display_name": "Alice"},
    )

    assert response.status_code == 200
    data = response.json()

    assert "token" in data
    assert "user_id" in data
    assert data["display_name"] == "Alice"

    # Verify token can be decoded
    token_data = decode_token(data["token"])
    assert token_data.display_name == "Alice"
    assert token_data.user_id == data["user_id"]


@pytest.mark.asyncio
async def test_get_token_same_name_same_user(client: AsyncClient):
    """Test that requesting a token with the same name returns the same user."""
    # First request
    response1 = await client.post(
        "/api/v1/auth/token",
        json={"display_name": "Bob"},
    )
    data1 = response1.json()

    # Second request with same name
    response2 = await client.post(
        "/api/v1/auth/token",
        json={"display_name": "Bob"},
    )
    data2 = response2.json()

    # Should return same user_id
    assert data1["user_id"] == data2["user_id"]
    assert data1["display_name"] == data2["display_name"]


@pytest.mark.asyncio
async def test_invalid_token_rejected(client: AsyncClient):
    """Test that an invalid token is rejected."""
    # Try to access protected endpoint with bad token
    response = await client.post(
        "/api/v1/matches",
        json={
            "game_id": "carcassonne",
            "player_display_names": ["Alice", "Bob"],
        },
        headers={"Authorization": "Bearer invalid_token_here"},
    )

    assert response.status_code == 401
