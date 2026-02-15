from __future__ import annotations

from src.engine.models import GameResult, MatchId, PlayerId, PlayerView
from src.ws.connection_manager import ConnectionManager
from src.ws.messages import ServerMessage, ServerMessageType


class Broadcaster:
    """Wraps ConnectionManager to send high-level game messages."""

    def __init__(self, connection_manager: ConnectionManager) -> None:
        self.connection_manager = connection_manager

    async def send_state_update(
        self, match_id: MatchId, player_id: PlayerId, view: PlayerView
    ) -> None:
        """Send a state update to a specific player."""
        message = ServerMessage(
            type=ServerMessageType.STATE_UPDATE,
            payload={"view": view.model_dump(mode="json")},
        )
        await self.connection_manager.send_to_player(match_id, player_id, message)

    async def send_error(
        self, match_id: MatchId, player_id: PlayerId, error_message: str
    ) -> None:
        """Send an error message to a specific player."""
        message = ServerMessage(
            type=ServerMessageType.ERROR,
            payload={"message": error_message},
        )
        await self.connection_manager.send_to_player(match_id, player_id, message)

    async def send_game_over(self, match_id: MatchId, result: GameResult) -> None:
        """Broadcast game over to all players and spectators."""
        message = ServerMessage(
            type=ServerMessageType.GAME_OVER,
            payload=result.model_dump(mode="json"),
        )
        await self.connection_manager.broadcast_to_match(match_id, message)

    async def send_action_committed(
        self, match_id: MatchId, player_id: PlayerId, action_type: str
    ) -> None:
        """Notify a player that their action was committed."""
        message = ServerMessage(
            type=ServerMessageType.ACTION_COMMITTED,
            payload={"action_type": action_type},
        )
        await self.connection_manager.send_to_player(match_id, player_id, message)

    async def send_player_disconnected(
        self, match_id: MatchId, player_id: PlayerId, grace_period_seconds: float
    ) -> None:
        """Broadcast that a player disconnected."""
        message = ServerMessage(
            type=ServerMessageType.PLAYER_DISCONNECTED,
            payload={
                "player_id": player_id,
                "grace_period_seconds": grace_period_seconds,
            },
        )
        await self.connection_manager.broadcast_to_match(match_id, message)

    async def send_player_reconnected(
        self, match_id: MatchId, player_id: PlayerId
    ) -> None:
        """Broadcast that a player reconnected."""
        message = ServerMessage(
            type=ServerMessageType.PLAYER_RECONNECTED,
            payload={"player_id": player_id},
        )
        await self.connection_manager.broadcast_to_match(match_id, message)

    async def send_player_forfeited(
        self, match_id: MatchId, player_id: PlayerId
    ) -> None:
        """Broadcast that a player was forfeited due to disconnect timeout."""
        message = ServerMessage(
            type=ServerMessageType.PLAYER_FORFEITED,
            payload={"player_id": player_id},
        )
        await self.connection_manager.broadcast_to_match(match_id, message)
