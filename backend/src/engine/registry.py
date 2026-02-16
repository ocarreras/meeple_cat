from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

from src.engine.models import GameId

if TYPE_CHECKING:
    from src.engine.protocol import GamePlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Discovers and registers game plugins."""

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

    def auto_discover(self, package: str = "src.games") -> None:
        pkg = importlib.import_module(package)
        for _importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
            if ispkg:
                try:
                    mod = importlib.import_module(f"{package}.{modname}")
                    if hasattr(mod, "plugin"):
                        self.register(mod.plugin)
                except Exception as e:
                    logger.warning(f"Failed to load game plugin '{modname}': {e}")

    def connect_grpc(self, address: str) -> None:
        """Connect to the Rust game engine via gRPC and register all available games."""
        from src.engine.grpc_plugin import connect_grpc

        plugins = connect_grpc(address)
        for plugin in plugins:
            self.register(plugin)
        logger.info(f"Registered {len(plugins)} game plugins from gRPC at {address}")
