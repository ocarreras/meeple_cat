from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Player(_message.Message):
    __slots__ = ("player_id", "display_name", "seat_index", "is_bot", "bot_id")
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    SEAT_INDEX_FIELD_NUMBER: _ClassVar[int]
    IS_BOT_FIELD_NUMBER: _ClassVar[int]
    BOT_ID_FIELD_NUMBER: _ClassVar[int]
    player_id: str
    display_name: str
    seat_index: int
    is_bot: bool
    bot_id: str
    def __init__(self, player_id: _Optional[str] = ..., display_name: _Optional[str] = ..., seat_index: _Optional[int] = ..., is_bot: bool = ..., bot_id: _Optional[str] = ...) -> None: ...

class GameConfig(_message.Message):
    __slots__ = ("base_time_ms", "increment_ms", "options", "random_seed")
    class OptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    BASE_TIME_MS_FIELD_NUMBER: _ClassVar[int]
    INCREMENT_MS_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    RANDOM_SEED_FIELD_NUMBER: _ClassVar[int]
    base_time_ms: int
    increment_ms: int
    options: _containers.ScalarMap[str, str]
    random_seed: int
    def __init__(self, base_time_ms: _Optional[int] = ..., increment_ms: _Optional[int] = ..., options: _Optional[_Mapping[str, str]] = ..., random_seed: _Optional[int] = ...) -> None: ...

class ExpectedAction(_message.Message):
    __slots__ = ("player_id", "action_type")
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    ACTION_TYPE_FIELD_NUMBER: _ClassVar[int]
    player_id: str
    action_type: str
    def __init__(self, player_id: _Optional[str] = ..., action_type: _Optional[str] = ...) -> None: ...

class Phase(_message.Message):
    __slots__ = ("name", "concurrent_mode", "expected_actions", "auto_resolve", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NAME_FIELD_NUMBER: _ClassVar[int]
    CONCURRENT_MODE_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_ACTIONS_FIELD_NUMBER: _ClassVar[int]
    AUTO_RESOLVE_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    name: str
    concurrent_mode: str
    expected_actions: _containers.RepeatedCompositeFieldContainer[ExpectedAction]
    auto_resolve: bool
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, name: _Optional[str] = ..., concurrent_mode: _Optional[str] = ..., expected_actions: _Optional[_Iterable[_Union[ExpectedAction, _Mapping]]] = ..., auto_resolve: bool = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...

class Action(_message.Message):
    __slots__ = ("action_type", "player_id", "payload_json")
    ACTION_TYPE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    action_type: str
    player_id: str
    payload_json: bytes
    def __init__(self, action_type: _Optional[str] = ..., player_id: _Optional[str] = ..., payload_json: _Optional[bytes] = ...) -> None: ...

class Event(_message.Message):
    __slots__ = ("event_type", "player_id", "payload_json")
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_JSON_FIELD_NUMBER: _ClassVar[int]
    event_type: str
    player_id: str
    payload_json: bytes
    def __init__(self, event_type: _Optional[str] = ..., player_id: _Optional[str] = ..., payload_json: _Optional[bytes] = ...) -> None: ...

class GameResult(_message.Message):
    __slots__ = ("winners", "final_scores", "reason")
    class FinalScoresEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    WINNERS_FIELD_NUMBER: _ClassVar[int]
    FINAL_SCORES_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    winners: _containers.RepeatedScalarFieldContainer[str]
    final_scores: _containers.ScalarMap[str, float]
    reason: str
    def __init__(self, winners: _Optional[_Iterable[str]] = ..., final_scores: _Optional[_Mapping[str, float]] = ..., reason: _Optional[str] = ...) -> None: ...

class TransitionResult(_message.Message):
    __slots__ = ("game_data_json", "events", "next_phase", "scores", "game_over")
    class ScoresEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: float
        def __init__(self, key: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    NEXT_PHASE_FIELD_NUMBER: _ClassVar[int]
    SCORES_FIELD_NUMBER: _ClassVar[int]
    GAME_OVER_FIELD_NUMBER: _ClassVar[int]
    game_data_json: bytes
    events: _containers.RepeatedCompositeFieldContainer[Event]
    next_phase: Phase
    scores: _containers.ScalarMap[str, float]
    game_over: GameResult
    def __init__(self, game_data_json: _Optional[bytes] = ..., events: _Optional[_Iterable[_Union[Event, _Mapping]]] = ..., next_phase: _Optional[_Union[Phase, _Mapping]] = ..., scores: _Optional[_Mapping[str, float]] = ..., game_over: _Optional[_Union[GameResult, _Mapping]] = ...) -> None: ...

class GetGameInfoRequest(_message.Message):
    __slots__ = ("game_id",)
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    def __init__(self, game_id: _Optional[str] = ...) -> None: ...

class GetGameInfoResponse(_message.Message):
    __slots__ = ("game_id", "display_name", "min_players", "max_players", "description", "disconnect_policy")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    MIN_PLAYERS_FIELD_NUMBER: _ClassVar[int]
    MAX_PLAYERS_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    DISCONNECT_POLICY_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    display_name: str
    min_players: int
    max_players: int
    description: str
    disconnect_policy: str
    def __init__(self, game_id: _Optional[str] = ..., display_name: _Optional[str] = ..., min_players: _Optional[int] = ..., max_players: _Optional[int] = ..., description: _Optional[str] = ..., disconnect_policy: _Optional[str] = ...) -> None: ...

class ListGamesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListGamesResponse(_message.Message):
    __slots__ = ("games",)
    GAMES_FIELD_NUMBER: _ClassVar[int]
    games: _containers.RepeatedCompositeFieldContainer[GetGameInfoResponse]
    def __init__(self, games: _Optional[_Iterable[_Union[GetGameInfoResponse, _Mapping]]] = ...) -> None: ...

class CreateInitialStateRequest(_message.Message):
    __slots__ = ("game_id", "players", "config")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    players: _containers.RepeatedCompositeFieldContainer[Player]
    config: GameConfig
    def __init__(self, game_id: _Optional[str] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ..., config: _Optional[_Union[GameConfig, _Mapping]] = ...) -> None: ...

class CreateInitialStateResponse(_message.Message):
    __slots__ = ("game_data_json", "phase", "events")
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    game_data_json: bytes
    phase: Phase
    events: _containers.RepeatedCompositeFieldContainer[Event]
    def __init__(self, game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., events: _Optional[_Iterable[_Union[Event, _Mapping]]] = ...) -> None: ...

class GetValidActionsRequest(_message.Message):
    __slots__ = ("game_id", "game_data_json", "phase", "player_id")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    game_data_json: bytes
    phase: Phase
    player_id: str
    def __init__(self, game_id: _Optional[str] = ..., game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., player_id: _Optional[str] = ...) -> None: ...

class GetValidActionsResponse(_message.Message):
    __slots__ = ("actions_json",)
    ACTIONS_JSON_FIELD_NUMBER: _ClassVar[int]
    actions_json: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, actions_json: _Optional[_Iterable[bytes]] = ...) -> None: ...

class ValidateActionRequest(_message.Message):
    __slots__ = ("game_id", "game_data_json", "phase", "action")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    game_data_json: bytes
    phase: Phase
    action: Action
    def __init__(self, game_id: _Optional[str] = ..., game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., action: _Optional[_Union[Action, _Mapping]] = ...) -> None: ...

class ValidateActionResponse(_message.Message):
    __slots__ = ("error",)
    ERROR_FIELD_NUMBER: _ClassVar[int]
    error: str
    def __init__(self, error: _Optional[str] = ...) -> None: ...

class ApplyActionRequest(_message.Message):
    __slots__ = ("game_id", "game_data_json", "phase", "action", "players")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    game_data_json: bytes
    phase: Phase
    action: Action
    players: _containers.RepeatedCompositeFieldContainer[Player]
    def __init__(self, game_id: _Optional[str] = ..., game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., action: _Optional[_Union[Action, _Mapping]] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ...) -> None: ...

class ApplyActionResponse(_message.Message):
    __slots__ = ("result",)
    RESULT_FIELD_NUMBER: _ClassVar[int]
    result: TransitionResult
    def __init__(self, result: _Optional[_Union[TransitionResult, _Mapping]] = ...) -> None: ...

class GetPlayerViewRequest(_message.Message):
    __slots__ = ("game_id", "game_data_json", "phase", "player_id", "players")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    game_data_json: bytes
    phase: Phase
    player_id: str
    players: _containers.RepeatedCompositeFieldContainer[Player]
    def __init__(self, game_id: _Optional[str] = ..., game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., player_id: _Optional[str] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ...) -> None: ...

class GetPlayerViewResponse(_message.Message):
    __slots__ = ("view_json",)
    VIEW_JSON_FIELD_NUMBER: _ClassVar[int]
    view_json: bytes
    def __init__(self, view_json: _Optional[bytes] = ...) -> None: ...

class GetSpectatorSummaryRequest(_message.Message):
    __slots__ = ("game_id", "game_data_json", "phase", "players")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    game_data_json: bytes
    phase: Phase
    players: _containers.RepeatedCompositeFieldContainer[Player]
    def __init__(self, game_id: _Optional[str] = ..., game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ...) -> None: ...

class GetSpectatorSummaryResponse(_message.Message):
    __slots__ = ("summary_json",)
    SUMMARY_JSON_FIELD_NUMBER: _ClassVar[int]
    summary_json: bytes
    def __init__(self, summary_json: _Optional[bytes] = ...) -> None: ...

class StateToAiViewRequest(_message.Message):
    __slots__ = ("game_id", "game_data_json", "phase", "player_id", "players")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    game_data_json: bytes
    phase: Phase
    player_id: str
    players: _containers.RepeatedCompositeFieldContainer[Player]
    def __init__(self, game_id: _Optional[str] = ..., game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., player_id: _Optional[str] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ...) -> None: ...

class StateToAiViewResponse(_message.Message):
    __slots__ = ("ai_view_json",)
    AI_VIEW_JSON_FIELD_NUMBER: _ClassVar[int]
    ai_view_json: bytes
    def __init__(self, ai_view_json: _Optional[bytes] = ...) -> None: ...

class ParseAiActionRequest(_message.Message):
    __slots__ = ("game_id", "response_json", "phase", "player_id")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    response_json: bytes
    phase: Phase
    player_id: str
    def __init__(self, game_id: _Optional[str] = ..., response_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., player_id: _Optional[str] = ...) -> None: ...

class ParseAiActionResponse(_message.Message):
    __slots__ = ("action",)
    ACTION_FIELD_NUMBER: _ClassVar[int]
    action: Action
    def __init__(self, action: _Optional[_Union[Action, _Mapping]] = ...) -> None: ...

class OnPlayerForfeitRequest(_message.Message):
    __slots__ = ("game_id", "game_data_json", "phase", "player_id", "players")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    game_data_json: bytes
    phase: Phase
    player_id: str
    players: _containers.RepeatedCompositeFieldContainer[Player]
    def __init__(self, game_id: _Optional[str] = ..., game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., player_id: _Optional[str] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ...) -> None: ...

class OnPlayerForfeitResponse(_message.Message):
    __slots__ = ("result",)
    RESULT_FIELD_NUMBER: _ClassVar[int]
    result: TransitionResult
    def __init__(self, result: _Optional[_Union[TransitionResult, _Mapping]] = ...) -> None: ...

class MctsSearchRequest(_message.Message):
    __slots__ = ("game_id", "game_data_json", "phase", "player_id", "players", "num_simulations", "time_limit_ms", "exploration_constant", "num_determinizations", "eval_profile", "pw_c", "pw_alpha", "use_rave", "rave_k", "max_amaf_depth", "rave_fpu", "tile_aware_amaf")
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    GAME_DATA_JSON_FIELD_NUMBER: _ClassVar[int]
    PHASE_FIELD_NUMBER: _ClassVar[int]
    PLAYER_ID_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    NUM_SIMULATIONS_FIELD_NUMBER: _ClassVar[int]
    TIME_LIMIT_MS_FIELD_NUMBER: _ClassVar[int]
    EXPLORATION_CONSTANT_FIELD_NUMBER: _ClassVar[int]
    NUM_DETERMINIZATIONS_FIELD_NUMBER: _ClassVar[int]
    EVAL_PROFILE_FIELD_NUMBER: _ClassVar[int]
    PW_C_FIELD_NUMBER: _ClassVar[int]
    PW_ALPHA_FIELD_NUMBER: _ClassVar[int]
    USE_RAVE_FIELD_NUMBER: _ClassVar[int]
    RAVE_K_FIELD_NUMBER: _ClassVar[int]
    MAX_AMAF_DEPTH_FIELD_NUMBER: _ClassVar[int]
    RAVE_FPU_FIELD_NUMBER: _ClassVar[int]
    TILE_AWARE_AMAF_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    game_data_json: bytes
    phase: Phase
    player_id: str
    players: _containers.RepeatedCompositeFieldContainer[Player]
    num_simulations: int
    time_limit_ms: float
    exploration_constant: float
    num_determinizations: int
    eval_profile: str
    pw_c: float
    pw_alpha: float
    use_rave: bool
    rave_k: float
    max_amaf_depth: int
    rave_fpu: bool
    tile_aware_amaf: bool
    def __init__(self, game_id: _Optional[str] = ..., game_data_json: _Optional[bytes] = ..., phase: _Optional[_Union[Phase, _Mapping]] = ..., player_id: _Optional[str] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ..., num_simulations: _Optional[int] = ..., time_limit_ms: _Optional[float] = ..., exploration_constant: _Optional[float] = ..., num_determinizations: _Optional[int] = ..., eval_profile: _Optional[str] = ..., pw_c: _Optional[float] = ..., pw_alpha: _Optional[float] = ..., use_rave: bool = ..., rave_k: _Optional[float] = ..., max_amaf_depth: _Optional[int] = ..., rave_fpu: bool = ..., tile_aware_amaf: bool = ...) -> None: ...

class MctsSearchResponse(_message.Message):
    __slots__ = ("action_json", "iterations_run", "elapsed_ms")
    ACTION_JSON_FIELD_NUMBER: _ClassVar[int]
    ITERATIONS_RUN_FIELD_NUMBER: _ClassVar[int]
    ELAPSED_MS_FIELD_NUMBER: _ClassVar[int]
    action_json: bytes
    iterations_run: int
    elapsed_ms: float
    def __init__(self, action_json: _Optional[bytes] = ..., iterations_run: _Optional[int] = ..., elapsed_ms: _Optional[float] = ...) -> None: ...

class RunArenaRequest(_message.Message):
    __slots__ = ("game_id", "num_games", "base_seed", "alternate_seats", "game_options", "strategies")
    class GameOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    NUM_GAMES_FIELD_NUMBER: _ClassVar[int]
    BASE_SEED_FIELD_NUMBER: _ClassVar[int]
    ALTERNATE_SEATS_FIELD_NUMBER: _ClassVar[int]
    GAME_OPTIONS_FIELD_NUMBER: _ClassVar[int]
    STRATEGIES_FIELD_NUMBER: _ClassVar[int]
    game_id: str
    num_games: int
    base_seed: int
    alternate_seats: bool
    game_options: _containers.ScalarMap[str, str]
    strategies: _containers.RepeatedCompositeFieldContainer[ArenaStrategyConfig]
    def __init__(self, game_id: _Optional[str] = ..., num_games: _Optional[int] = ..., base_seed: _Optional[int] = ..., alternate_seats: bool = ..., game_options: _Optional[_Mapping[str, str]] = ..., strategies: _Optional[_Iterable[_Union[ArenaStrategyConfig, _Mapping]]] = ...) -> None: ...

class ArenaStrategyConfig(_message.Message):
    __slots__ = ("name", "strategy_type", "num_simulations", "time_limit_ms", "num_determinizations", "eval_profile", "pw_c", "pw_alpha", "use_rave", "rave_k", "max_amaf_depth", "rave_fpu", "tile_aware_amaf")
    NAME_FIELD_NUMBER: _ClassVar[int]
    STRATEGY_TYPE_FIELD_NUMBER: _ClassVar[int]
    NUM_SIMULATIONS_FIELD_NUMBER: _ClassVar[int]
    TIME_LIMIT_MS_FIELD_NUMBER: _ClassVar[int]
    NUM_DETERMINIZATIONS_FIELD_NUMBER: _ClassVar[int]
    EVAL_PROFILE_FIELD_NUMBER: _ClassVar[int]
    PW_C_FIELD_NUMBER: _ClassVar[int]
    PW_ALPHA_FIELD_NUMBER: _ClassVar[int]
    USE_RAVE_FIELD_NUMBER: _ClassVar[int]
    RAVE_K_FIELD_NUMBER: _ClassVar[int]
    MAX_AMAF_DEPTH_FIELD_NUMBER: _ClassVar[int]
    RAVE_FPU_FIELD_NUMBER: _ClassVar[int]
    TILE_AWARE_AMAF_FIELD_NUMBER: _ClassVar[int]
    name: str
    strategy_type: str
    num_simulations: int
    time_limit_ms: float
    num_determinizations: int
    eval_profile: str
    pw_c: float
    pw_alpha: float
    use_rave: bool
    rave_k: float
    max_amaf_depth: int
    rave_fpu: bool
    tile_aware_amaf: bool
    def __init__(self, name: _Optional[str] = ..., strategy_type: _Optional[str] = ..., num_simulations: _Optional[int] = ..., time_limit_ms: _Optional[float] = ..., num_determinizations: _Optional[int] = ..., eval_profile: _Optional[str] = ..., pw_c: _Optional[float] = ..., pw_alpha: _Optional[float] = ..., use_rave: bool = ..., rave_k: _Optional[float] = ..., max_amaf_depth: _Optional[int] = ..., rave_fpu: bool = ..., tile_aware_amaf: bool = ...) -> None: ...

class ArenaProgressUpdate(_message.Message):
    __slots__ = ("games_completed", "total_games", "final_result")
    GAMES_COMPLETED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_GAMES_FIELD_NUMBER: _ClassVar[int]
    FINAL_RESULT_FIELD_NUMBER: _ClassVar[int]
    games_completed: int
    total_games: int
    final_result: ArenaFinalResult
    def __init__(self, games_completed: _Optional[int] = ..., total_games: _Optional[int] = ..., final_result: _Optional[_Union[ArenaFinalResult, _Mapping]] = ...) -> None: ...

class ArenaFinalResult(_message.Message):
    __slots__ = ("num_games", "wins", "draws", "score_stats", "total_duration_s")
    class WinsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    class ScoreStatsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ArenaScoreStats
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ArenaScoreStats, _Mapping]] = ...) -> None: ...
    NUM_GAMES_FIELD_NUMBER: _ClassVar[int]
    WINS_FIELD_NUMBER: _ClassVar[int]
    DRAWS_FIELD_NUMBER: _ClassVar[int]
    SCORE_STATS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_DURATION_S_FIELD_NUMBER: _ClassVar[int]
    num_games: int
    wins: _containers.ScalarMap[str, int]
    draws: int
    score_stats: _containers.MessageMap[str, ArenaScoreStats]
    total_duration_s: float
    def __init__(self, num_games: _Optional[int] = ..., wins: _Optional[_Mapping[str, int]] = ..., draws: _Optional[int] = ..., score_stats: _Optional[_Mapping[str, ArenaScoreStats]] = ..., total_duration_s: _Optional[float] = ...) -> None: ...

class ArenaScoreStats(_message.Message):
    __slots__ = ("avg", "stddev", "win_rate", "ci_95_lo", "ci_95_hi")
    AVG_FIELD_NUMBER: _ClassVar[int]
    STDDEV_FIELD_NUMBER: _ClassVar[int]
    WIN_RATE_FIELD_NUMBER: _ClassVar[int]
    CI_95_LO_FIELD_NUMBER: _ClassVar[int]
    CI_95_HI_FIELD_NUMBER: _ClassVar[int]
    avg: float
    stddev: float
    win_rate: float
    ci_95_lo: float
    ci_95_hi: float
    def __init__(self, avg: _Optional[float] = ..., stddev: _Optional[float] = ..., win_rate: _Optional[float] = ..., ci_95_lo: _Optional[float] = ..., ci_95_hi: _Optional[float] = ...) -> None: ...
