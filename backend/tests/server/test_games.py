from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_games(client: AsyncClient):
    """Test that GET /games returns a list of games including carcassonne."""
    response = await client.get("/api/v1/games")

    assert response.status_code == 200
    games = response.json()

    assert isinstance(games, list)
    assert len(games) > 0

    # Check that mock-game is in the list
    game_ids = [g["game_id"] for g in games]
    assert "mock-game" in game_ids

    # Check structure of first game
    game = games[0]
    assert "game_id" in game
    assert "display_name" in game
    assert "min_players" in game
    assert "max_players" in game
    assert "description" in game


@pytest.mark.asyncio
async def test_get_game_details(client: AsyncClient):
    """Test that GET /games/mock-game returns game details."""
    response = await client.get("/api/v1/games/mock-game")

    assert response.status_code == 200
    game = response.json()

    assert game["game_id"] == "mock-game"
    assert "display_name" in game
    assert "min_players" in game
    assert "max_players" in game
    assert "description" in game
    assert "config_schema" in game


@pytest.mark.asyncio
async def test_get_unknown_game_404(client: AsyncClient):
    """Test that GET /games/unknown returns 404."""
    response = await client.get("/api/v1/games/unknown_game")

    assert response.status_code == 404
