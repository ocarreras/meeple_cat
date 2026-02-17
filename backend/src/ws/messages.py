from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ServerMessageType(str, Enum):
    STATE_UPDATE = "state_update"
    ACTION_COMMITTED = "action_committed"
    ERROR = "error"
    GAME_OVER = "game_over"
    CONNECTED = "connected"
    PONG = "pong"
    PLAYER_DISCONNECTED = "player_disconnected"
    PLAYER_RECONNECTED = "player_reconnected"
    PLAYER_FORFEITED = "player_forfeited"
    GAME_EVENTS = "game_events"


class ClientMessageType(str, Enum):
    ACTION = "action"
    PING = "ping"
    RESIGN = "resign"


class ServerMessage(BaseModel):
    type: ServerMessageType
    payload: dict = Field(default_factory=dict)


class ClientMessage(BaseModel):
    type: ClientMessageType
    payload: dict = Field(default_factory=dict)
