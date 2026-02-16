"""GrpcGamePlugin — adapter that delegates GamePlugin calls to the Rust game engine via gRPC."""

from __future__ import annotations

import json
import logging
from typing import ClassVar

import grpc

from src.engine.models import (
    Action,
    Event,
    GameConfig,
    Phase,
    Player,
    PlayerId,
    TransitionResult,
    GameResult,
    ExpectedAction,
    ConcurrentMode,
)
from src.engine.proto import game_engine_pb2 as pb2
from src.engine.proto import game_engine_pb2_grpc as pb2_grpc

logger = logging.getLogger(__name__)


def _player_to_proto(p: Player) -> pb2.Player:
    return pb2.Player(
        player_id=p.player_id,
        display_name=p.display_name,
        seat_index=p.seat_index,
        is_bot=p.is_bot,
        bot_id=p.bot_id or "",
    )


def _phase_to_proto(phase: Phase) -> pb2.Phase:
    expected = [
        pb2.ExpectedAction(
            player_id=ea.player_id,
            action_type=ea.action_type,
        )
        for ea in phase.expected_actions
    ]
    metadata = {k: json.dumps(v) for k, v in phase.metadata.items()}
    return pb2.Phase(
        name=phase.name,
        concurrent_mode=phase.concurrent_mode.value if phase.concurrent_mode else "sequential",
        expected_actions=expected,
        auto_resolve=phase.auto_resolve,
        metadata=metadata,
    )


def _config_to_proto(config: GameConfig) -> pb2.GameConfig:
    options = {k: json.dumps(v) for k, v in config.options.items()} if config.options else {}
    return pb2.GameConfig(
        options=options,
        random_seed=config.random_seed,
    )


def _action_to_proto(action: Action) -> pb2.Action:
    return pb2.Action(
        action_type=action.action_type,
        player_id=action.player_id,
        payload_json=json.dumps(action.payload).encode(),
    )


def _phase_from_proto(proto_phase: pb2.Phase) -> Phase:
    expected = [
        ExpectedAction(
            player_id=ea.player_id or None,
            action_type=ea.action_type,
        )
        for ea in proto_phase.expected_actions
    ]
    metadata = {}
    for k, v in proto_phase.metadata.items():
        try:
            metadata[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            metadata[k] = v

    cm = ConcurrentMode.SEQUENTIAL
    if proto_phase.concurrent_mode == "commit_reveal":
        cm = ConcurrentMode.COMMIT_REVEAL
    elif proto_phase.concurrent_mode == "time_window":
        cm = ConcurrentMode.TIME_WINDOW

    return Phase(
        name=proto_phase.name,
        concurrent_mode=cm,
        expected_actions=expected,
        auto_resolve=proto_phase.auto_resolve,
        metadata=metadata,
    )


def _event_from_proto(proto_event: pb2.Event) -> Event:
    payload = {}
    if proto_event.payload_json:
        try:
            payload = json.loads(proto_event.payload_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return Event(
        event_type=proto_event.event_type,
        player_id=proto_event.player_id or None,
        payload=payload,
    )


def _game_result_from_proto(proto_gr: pb2.GameResult) -> GameResult:
    return GameResult(
        winners=list(proto_gr.winners),
        final_scores=dict(proto_gr.final_scores),
        reason=proto_gr.reason,
    )


def _transition_from_proto(proto_tr: pb2.TransitionResult) -> TransitionResult:
    game_data = json.loads(proto_tr.game_data_json) if proto_tr.game_data_json else {}
    events = [_event_from_proto(e) for e in proto_tr.events]
    next_phase = _phase_from_proto(proto_tr.next_phase) if proto_tr.HasField("next_phase") else Phase(name="unknown")
    game_over = None
    if proto_tr.HasField("game_over"):
        game_over = _game_result_from_proto(proto_tr.game_over)
    return TransitionResult(
        game_data=game_data,
        events=events,
        next_phase=next_phase,
        scores=dict(proto_tr.scores),
        game_over=game_over,
    )


class GrpcGamePlugin:
    """Implements the GamePlugin protocol by delegating to the Rust game engine via gRPC."""

    def __init__(
        self,
        stub: pb2_grpc.GameEngineServiceStub,
        game_id: str,
        display_name: str,
        min_players: int,
        max_players: int,
        description: str,
        disconnect_policy: str,
        config_schema: dict | None = None,
    ) -> None:
        self._stub = stub
        # ClassVar-like attributes (set per instance for gRPC plugins)
        self.game_id: ClassVar[str] = game_id  # type: ignore[assignment]
        self.display_name: ClassVar[str] = display_name  # type: ignore[assignment]
        self.min_players: ClassVar[int] = min_players  # type: ignore[assignment]
        self.max_players: ClassVar[int] = max_players  # type: ignore[assignment]
        self.description: ClassVar[str] = description  # type: ignore[assignment]
        self.disconnect_policy: ClassVar[str] = disconnect_policy  # type: ignore[assignment]
        self.config_schema: ClassVar[dict] = config_schema or {}  # type: ignore[assignment]

    def create_initial_state(
        self,
        players: list[Player],
        config: GameConfig,
    ) -> tuple[dict, Phase, list[Event]]:
        resp = self._stub.CreateInitialState(
            pb2.CreateInitialStateRequest(
                game_id=self.game_id,
                players=[_player_to_proto(p) for p in players],
                config=_config_to_proto(config),
            )
        )
        game_data = json.loads(resp.game_data_json) if resp.game_data_json else {}
        phase = _phase_from_proto(resp.phase) if resp.HasField("phase") else Phase(name="unknown")
        events = [_event_from_proto(e) for e in resp.events]
        return game_data, phase, events

    def validate_config(self, options: dict) -> list[str]:
        return []

    def get_valid_actions(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> list[dict]:
        resp = self._stub.GetValidActions(
            pb2.GetValidActionsRequest(
                game_id=self.game_id,
                game_data_json=json.dumps(game_data).encode(),
                phase=_phase_to_proto(phase),
                player_id=player_id,
            )
        )
        return [json.loads(a) for a in resp.actions_json]

    def validate_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
    ) -> str | None:
        resp = self._stub.ValidateAction(
            pb2.ValidateActionRequest(
                game_id=self.game_id,
                game_data_json=json.dumps(game_data).encode(),
                phase=_phase_to_proto(phase),
                action=_action_to_proto(action),
            )
        )
        return resp.error if resp.error else None

    def apply_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        resp = self._stub.ApplyAction(
            pb2.ApplyActionRequest(
                game_id=self.game_id,
                game_data_json=json.dumps(game_data).encode(),
                phase=_phase_to_proto(phase),
                action=_action_to_proto(action),
                players=[_player_to_proto(p) for p in players],
            )
        )
        return _transition_from_proto(resp.result)

    def get_player_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId | None,
        players: list[Player],
    ) -> dict:
        resp = self._stub.GetPlayerView(
            pb2.GetPlayerViewRequest(
                game_id=self.game_id,
                game_data_json=json.dumps(game_data).encode(),
                phase=_phase_to_proto(phase),
                player_id=player_id,
                players=[_player_to_proto(p) for p in players],
            )
        )
        return json.loads(resp.view_json) if resp.view_json else {}

    def resolve_concurrent_actions(
        self,
        game_data: dict,
        phase: Phase,
        actions: dict[str, Action],
        players: list[Player],
    ) -> TransitionResult:
        raise NotImplementedError("resolve_concurrent_actions not supported via gRPC yet")

    def state_to_ai_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> dict:
        resp = self._stub.StateToAiView(
            pb2.StateToAiViewRequest(
                game_id=self.game_id,
                game_data_json=json.dumps(game_data).encode(),
                phase=_phase_to_proto(phase),
                player_id=player_id,
                players=[_player_to_proto(p) for p in players],
            )
        )
        return json.loads(resp.ai_view_json) if resp.ai_view_json else {}

    def parse_ai_action(
        self,
        response: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> Action:
        resp = self._stub.ParseAiAction(
            pb2.ParseAiActionRequest(
                game_id=self.game_id,
                response_json=json.dumps(response).encode(),
                phase=_phase_to_proto(phase),
                player_id=player_id,
            )
        )
        payload = {}
        if resp.action and resp.action.payload_json:
            payload = json.loads(resp.action.payload_json)
        return Action(
            action_type=resp.action.action_type,
            player_id=resp.action.player_id,
            payload=payload,
        )

    def on_player_forfeit(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> TransitionResult | None:
        resp = self._stub.OnPlayerForfeit(
            pb2.OnPlayerForfeitRequest(
                game_id=self.game_id,
                game_data_json=json.dumps(game_data).encode(),
                phase=_phase_to_proto(phase),
                player_id=player_id,
                players=[_player_to_proto(p) for p in players],
            )
        )
        if resp.HasField("result"):
            return _transition_from_proto(resp.result)
        return None

    def get_spectator_summary(
        self,
        game_data: dict,
        phase: Phase,
        players: list[Player],
    ) -> dict:
        resp = self._stub.GetSpectatorSummary(
            pb2.GetSpectatorSummaryRequest(
                game_id=self.game_id,
                game_data_json=json.dumps(game_data).encode(),
                phase=_phase_to_proto(phase),
                players=[_player_to_proto(p) for p in players],
            )
        )
        return json.loads(resp.summary_json) if resp.summary_json else {}


def connect_grpc(address: str) -> list[GrpcGamePlugin]:
    """Connect to the Rust game engine and return GrpcGamePlugin instances for all available games."""
    channel = grpc.insecure_channel(address)
    stub = pb2_grpc.GameEngineServiceStub(channel)

    resp = stub.ListGames(pb2.ListGamesRequest())
    plugins = []
    for game_info in resp.games:
        plugin = GrpcGamePlugin(
            stub=stub,
            game_id=game_info.game_id,
            display_name=game_info.display_name,
            min_players=game_info.min_players,
            max_players=game_info.max_players,
            description=game_info.description,
            disconnect_policy=game_info.disconnect_policy,
        )
        plugins.append(plugin)
        logger.info(f"Connected gRPC game plugin: {game_info.game_id}")

    return plugins
