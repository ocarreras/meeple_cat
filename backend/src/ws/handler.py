from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import ValidationError

from src.auth import decode_token
from src.auth.ws_auth import validate_ws_ticket
from src.engine.errors import GameNotActiveError, InvalidActionError, NotYourTurnError, PlayerForfeitedError
from src.engine.event_store import EventStore
from src.engine.models import Action, GameStatus, PlayerId
from src.ws.messages import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/game/{match_id}")
async def game_websocket(
    ws: WebSocket,
    match_id: str,
    token: str | None = Query(None),
    ticket: str | None = Query(None),
):
    """WebSocket endpoint for game play."""
    # 1. Authenticate — try ticket first, then legacy JWT token
    player_id: PlayerId | None = None

    if ticket:
        redis = ws.app.state.redis
        result = await validate_ws_ticket(redis, ticket)
        if result:
            user_id, _display_name = result
            player_id = PlayerId(user_id)
        else:
            await ws.accept()
            await ws.close(code=4001, reason="Invalid or expired ticket")
            return
    elif token:
        try:
            token_data = decode_token(token)
            player_id = PlayerId(token_data.user_id)
        except Exception as e:
            logger.warning(f"Authentication failed: {e}")
            await ws.accept()
            await ws.close(code=4001, reason="Authentication failed")
            return
    else:
        await ws.accept()
        await ws.close(code=4001, reason="No authentication provided")
        return

    # 2. Get session
    session_manager = ws.app.state.session_manager
    session = session_manager.get_session(match_id)
    if session is None:
        logger.warning(f"Match {match_id} not found")
        await ws.accept()
        await ws.close(code=4004, reason="Match not found")
        return

    # 3. Verify player is in match
    player_ids = [p.player_id for p in session.state.players]
    if player_id not in player_ids:
        logger.warning(f"Player {player_id} not in match {match_id}")
        await ws.accept()
        await ws.close(code=4003, reason="Player not in match")
        return

    # 4. Connect via connection manager
    connection_manager = ws.app.state.connection_manager
    await connection_manager.connect_player(match_id, player_id, ws)

    try:
        # 5. Send CONNECTED message
        connected_msg = ServerMessage(
            type=ServerMessageType.CONNECTED,
            payload={"match_id": match_id, "player_id": player_id},
        )
        await ws.send_json(connected_msg.model_dump())

        # 5b. Handle reconnection (cancel grace period timer if active)
        if player_id in session.state.disconnected_players:
            db_session_factory = ws.app.state.db_session_factory
            async with db_session_factory() as db_session:
                session._event_store = EventStore(db_session)
                await session.handle_player_reconnect(player_id)
                await db_session.commit()

        # 6. Broadcast initial views
        await session._broadcast_views()

        # 7. Message loop
        while True:
            data = await ws.receive_json()

            try:
                client_msg = ClientMessage.model_validate(data)
            except ValidationError as e:
                logger.warning(f"Invalid message format: {e}")
                continue

            if client_msg.type == ClientMessageType.PING:
                # Send PONG
                pong_msg = ServerMessage(
                    type=ServerMessageType.PONG,
                    payload={},
                )
                await ws.send_json(pong_msg.model_dump())

            elif client_msg.type == ClientMessageType.ACTION:
                # Handle action
                try:
                    # Create Action object
                    action = Action(
                        action_type=client_msg.payload["action_type"],
                        player_id=player_id,
                        payload=client_msg.payload.get("payload", {}),
                    )

                    # Get fresh DB session
                    db_session_factory = ws.app.state.db_session_factory
                    async with db_session_factory() as db_session:
                        # Create new EventStore and assign to session
                        event_store = EventStore(db_session)
                        session._event_store = event_store

                        # Handle action
                        await session.handle_action(action)

                        # Commit the transaction
                        await db_session.commit()

                except (InvalidActionError, NotYourTurnError, GameNotActiveError, PlayerForfeitedError) as e:
                    # Send ERROR message
                    error_msg = ServerMessage(
                        type=ServerMessageType.ERROR,
                        payload={
                            "error": type(e).__name__,
                            "message": str(e),
                        },
                    )
                    await ws.send_json(error_msg.model_dump())
                except Exception as e:
                    logger.error(f"Error handling action: {e}", exc_info=True)
                    error_msg = ServerMessage(
                        type=ServerMessageType.ERROR,
                        payload={
                            "error": "InternalError",
                            "message": "An internal error occurred",
                        },
                    )
                    await ws.send_json(error_msg.model_dump())

            elif client_msg.type == ClientMessageType.RESIGN:
                # Log resign (simplified for now)
                logger.info(f"Player {player_id} resigned from match {match_id}")

    except WebSocketDisconnect:
        # 8. Disconnect from connection manager
        connection_manager.disconnect_player(match_id, player_id)
        logger.info(f"Player {player_id} disconnected from match {match_id}")

        # 9. Notify session for grace period handling
        if session and session.state.status == GameStatus.ACTIVE:
            try:
                db_session_factory = ws.app.state.db_session_factory
                async with db_session_factory() as db_session:
                    session._event_store = EventStore(db_session)
                    await session.handle_player_disconnect(player_id)
                    await db_session.commit()
            except Exception as e:
                logger.error(
                    f"Error handling disconnect for {player_id} in {match_id}: {e}",
                    exc_info=True,
                )
