from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/games", tags=["games"])


@router.get("")
async def list_games(request: Request) -> list[dict]:
    """List all available games."""
    registry = request.app.state.registry
    return registry.list_games()


@router.get("/{game_id}")
async def get_game(game_id: str, request: Request) -> dict:
    """Get details about a specific game."""
    registry = request.app.state.registry
    try:
        plugin = registry.get(game_id)
        return {
            "game_id": plugin.game_id,
            "display_name": plugin.display_name,
            "min_players": plugin.min_players,
            "max_players": plugin.max_players,
            "description": plugin.description,
            "config_schema": plugin.config_schema,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Game '{game_id}' not found")
