from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

from src.engine.models import MatchId, PlayerId
from src.ws.messages import ServerMessage

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for players and spectators."""

    def __init__(self) -> None:
        # match_id -> player_id -> WebSocket
        self._players: dict[str, dict[str, WebSocket]] = {}
        # match_id -> list[WebSocket]
        self._spectators: dict[str, list[WebSocket]] = {}

    async def connect_player(
        self, match_id: MatchId, player_id: PlayerId, ws: WebSocket
    ) -> None:
        """Accept a player's WebSocket connection."""
        await ws.accept()
        if match_id not in self._players:
            self._players[match_id] = {}
        self._players[match_id][player_id] = ws
        logger.info(f"Player {player_id} connected to match {match_id}")

    async def connect_spectator(self, match_id: MatchId, ws: WebSocket) -> None:
        """Accept a spectator's WebSocket connection."""
        await ws.accept()
        if match_id not in self._spectators:
            self._spectators[match_id] = []
        self._spectators[match_id].append(ws)
        logger.info(f"Spectator connected to match {match_id}")

    def disconnect_player(self, match_id: MatchId, player_id: PlayerId) -> None:
        """Remove a player's WebSocket connection."""
        if match_id in self._players:
            self._players[match_id].pop(player_id, None)
            if not self._players[match_id]:
                del self._players[match_id]
            logger.info(f"Player {player_id} disconnected from match {match_id}")

    def disconnect_spectator(self, match_id: MatchId, ws: WebSocket) -> None:
        """Remove a spectator's WebSocket connection."""
        if match_id in self._spectators:
            try:
                self._spectators[match_id].remove(ws)
                if not self._spectators[match_id]:
                    del self._spectators[match_id]
                logger.info(f"Spectator disconnected from match {match_id}")
            except ValueError:
                pass

    async def send_to_player(
        self, match_id: MatchId, player_id: PlayerId, message: ServerMessage
    ) -> None:
        """Send a message to a specific player."""
        if match_id not in self._players:
            return
        ws = self._players[match_id].get(player_id)
        if ws is None:
            return

        try:
            await ws.send_json(message.model_dump(mode="json"))
        except Exception as e:
            logger.warning(
                f"Failed to send message to player {player_id} in match {match_id}: {e}"
            )
            self.disconnect_player(match_id, player_id)

    async def broadcast_to_match(
        self, match_id: MatchId, message: ServerMessage
    ) -> None:
        """Broadcast a message to all players and spectators in a match."""
        data = message.model_dump(mode="json")

        # Send to all players
        if match_id in self._players:
            for player_id, ws in list(self._players[match_id].items()):
                try:
                    await ws.send_json(data)
                except Exception as e:
                    logger.warning(
                        f"Failed to broadcast to player {player_id} in match {match_id}: {e}"
                    )
                    self.disconnect_player(match_id, player_id)

        # Send to all spectators
        if match_id in self._spectators:
            for ws in list(self._spectators[match_id]):
                try:
                    await ws.send_json(data)
                except Exception as e:
                    logger.warning(
                        f"Failed to broadcast to spectator in match {match_id}: {e}"
                    )
                    self.disconnect_spectator(match_id, ws)

    def get_connected_players(self, match_id: MatchId) -> list[str]:
        """Get list of connected player IDs for a match."""
        if match_id not in self._players:
            return []
        return list(self._players[match_id].keys())

    def cleanup_match(self, match_id: MatchId) -> None:
        """Remove all connections for a match."""
        self._players.pop(match_id, None)
        self._spectators.pop(match_id, None)
        logger.info(f"Cleaned up connections for match {match_id}")
