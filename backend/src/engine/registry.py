from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.engine.models import GameId

if TYPE_CHECKING:
    from src.engine.protocol import GamePlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registers game plugins provided by the Rust engine via gRPC."""

    def __init__(self) -> None:
        self._plugins: dict[str, GamePlugin] = {}

    def register(self, plugin: GamePlugin) -> None:
        game_id = plugin.game_id
        if game_id in self._plugins:
            raise ValueError(f"Game '{game_id}' already registered")
        self._plugins[game_id] = plugin

    def get(self, game_id: str) -> GamePlugin:
        if game_id not in self._plugins:
            raise KeyError(f"Unknown game: {game_id}")
        return self._plugins[game_id]

    def list_games(self) -> list[dict]:
        return [
            {
                "game_id": p.game_id,
                "display_name": p.display_name,
                "min_players": p.min_players,
                "max_players": p.max_players,
                "description": p.description,
            }
            for p in self._plugins.values()
        ]

    def connect_grpc(self, address: str, max_retries: int = 30, retry_delay: float = 2.0) -> None:
        """Connect to the Rust game engine via gRPC and register all available games.

        Retries on failure to handle the case where the game engine is still starting up.
        """
        from src.engine.grpc_plugin import connect_grpc

        for attempt in range(1, max_retries + 1):
            try:
                plugins = connect_grpc(address)
                for plugin in plugins:
                    self.register(plugin)
                logger.info(f"Registered {len(plugins)} game plugins from gRPC at {address}")
                return
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"Failed to connect to game engine at {address} after {max_retries} attempts")
                    raise
                logger.warning(
                    f"Game engine not ready at {address} (attempt {attempt}/{max_retries}): {e}. "
                    f"Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
