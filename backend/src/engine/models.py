from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import NewType
from uuid import uuid4

from pydantic import BaseModel, Field

# --- Identifiers ---
PlayerId = NewType("PlayerId", str)
MatchId = NewType("MatchId", str)
GameId = NewType("GameId", str)

# --- Player ---
class Player(BaseModel):
    player_id: PlayerId
    display_name: str
    seat_index: int
    is_bot: bool = False
    bot_id: str | None = None

# --- Timer ---
class TimerMode(str, Enum):
    FISCHER = "fischer"
    BYOYOMI = "byoyomi"
    SIMPLE = "simple"
    TOTAL = "total"
    NONE = "none"

class TimeoutBehavior(str, Enum):
    LOSE_GAME = "lose_game"
    LOSE_TURN = "lose_turn"
    RANDOM_ACTION = "random_action"
    FORCE_PASS = "force_pass"

class TimerConfig(BaseModel):
    mode: TimerMode = TimerMode.NONE
    base_time_ms: int = 0
    increment_ms: int = 0
    periods: int = 1
    period_time_ms: int = 0
    timeout_behavior: TimeoutBehavior = TimeoutBehavior.LOSE_TURN

class GameConfig(BaseModel):
    timer: TimerConfig = Field(default_factory=TimerConfig)
    options: dict = Field(default_factory=dict)
    random_seed: int | None = None

# --- Phase & Action Queue ---
class ConcurrentMode(str, Enum):
    SEQUENTIAL = "sequential"
    COMMIT_REVEAL = "commit_reveal"
    TIME_WINDOW = "time_window"

class ExpectedAction(BaseModel):
    player_id: PlayerId | None = None
    action_type: str
    constraints: dict = Field(default_factory=dict)
    timeout_ms: int | None = None

class Phase(BaseModel):
    name: str
    concurrent_mode: ConcurrentMode = ConcurrentMode.SEQUENTIAL
    expected_actions: list[ExpectedAction] = Field(default_factory=list)
    auto_resolve: bool = False
    metadata: dict = Field(default_factory=dict)

# --- Action ---
class Action(BaseModel):
    action_type: str
    player_id: PlayerId
    payload: dict = Field(default_factory=dict)
    timestamp: datetime | None = None

# --- Event ---
class Event(BaseModel):
    event_type: str
    player_id: PlayerId | None = None
    payload: dict = Field(default_factory=dict)

class PersistedEvent(BaseModel):
    id: int | None = None
    match_id: MatchId
    sequence_number: int
    event_type: str
    player_id: PlayerId | None = None
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# --- Game State ---
class GameStatus(str, Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    PAUSED = "paused"
    FINISHED = "finished"
    ABANDONED = "abandoned"

class GameState(BaseModel):
    match_id: MatchId
    game_id: GameId
    players: list[Player]
    current_phase: Phase
    status: GameStatus = GameStatus.ACTIVE
    turn_number: int = 0
    action_number: int = 0
    config: GameConfig = Field(default_factory=GameConfig)
    player_timers: dict[str, int] = Field(default_factory=dict)  # PlayerId -> ms
    game_data: dict = Field(default_factory=dict)
    scores: dict[str, float] = Field(default_factory=dict)  # PlayerId -> score
    committed_actions: dict[str, Action] = Field(default_factory=dict)

# --- Transition Result ---
class GameResult(BaseModel):
    winners: list[PlayerId]
    final_scores: dict[str, float]  # PlayerId -> score
    reason: str = "normal"
    details: dict = Field(default_factory=dict)

class TransitionResult(BaseModel):
    game_data: dict
    events: list[Event]
    next_phase: Phase
    scores: dict[str, float] = Field(default_factory=dict)
    game_over: GameResult | None = None

# --- Player View ---
class PlayerView(BaseModel):
    match_id: MatchId
    game_id: GameId
    players: list[Player]
    current_phase: Phase
    status: GameStatus
    turn_number: int
    scores: dict[str, float]
    player_timers: dict[str, int]
    game_data: dict
    valid_actions: list[dict] = Field(default_factory=list)
    viewer_id: PlayerId | None = None
    is_spectator: bool = False
