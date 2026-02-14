from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_match(client: AsyncClient):
    """Test creating a match."""
    # First get tokens for both players
    resp1 = await client.post("/api/v1/auth/token", json={"display_name": "Alice"})
    alice_token = resp1.json()["token"]

    resp2 = await client.post("/api/v1/auth/token", json={"display_name": "Bob"})

    # Create match
    response = await client.post(
        "/api/v1/matches",
        json={
            "game_id": "carcassonne",
            "player_display_names": ["Alice", "Bob"],
            "config": {},
            "random_seed": 42,
        },
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    assert response.status_code == 200
    data = response.json()

    assert "match_id" in data
    assert data["game_id"] == "carcassonne"
    assert data["status"] == "active"
    assert len(data["players"]) == 2

    # Verify player order
    player_names = [p["display_name"] for p in sorted(data["players"], key=lambda x: x["seat_index"])]
    assert player_names == ["Alice", "Bob"]


@pytest.mark.asyncio
async def test_get_match(client: AsyncClient):
    """Test getting match details."""
    # Create a match first
    resp1 = await client.post("/api/v1/auth/token", json={"display_name": "Charlie"})
    charlie_token = resp1.json()["token"]

    create_resp = await client.post(
        "/api/v1/matches",
        json={
            "game_id": "carcassonne",
            "player_display_names": ["Charlie", "Dave"],
            "random_seed": 123,
        },
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    match_id = create_resp.json()["match_id"]

    # Get match details
    response = await client.get(f"/api/v1/matches/{match_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["match_id"] == match_id
    assert data["game_id"] == "carcassonne"
    assert data["status"] == "active"
    assert len(data["players"]) == 2


@pytest.mark.asyncio
async def test_create_match_bad_player_count(client: AsyncClient):
    """Test that creating a match with invalid player count fails."""
    resp = await client.post("/api/v1/auth/token", json={"display_name": "Solo"})
    token = resp.json()["token"]

    # Carcassonne requires 2-5 players, so 1 player should fail
    response = await client.post(
        "/api/v1/matches",
        json={
            "game_id": "carcassonne",
            "player_display_names": ["Solo"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "Invalid player count" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_match_unknown_game(client: AsyncClient):
    """Test that creating a match with unknown game fails."""
    resp = await client.post("/api/v1/auth/token", json={"display_name": "Eve"})
    token = resp.json()["token"]

    response = await client.post(
        "/api/v1/matches",
        json={
            "game_id": "unknown_game",
            "player_display_names": ["Eve", "Frank"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
