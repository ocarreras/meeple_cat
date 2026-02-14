from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from src.engine.models import (
    Action,
    Event,
    GameConfig,
    GameId,
    Phase,
    Player,
    PlayerId,
    TransitionResult,
)


@runtime_checkable
class GamePlugin(Protocol):
    """Interface that every game must implement."""

    game_id: ClassVar[str]
    display_name: ClassVar[str]
    min_players: ClassVar[int]
    max_players: ClassVar[int]
    description: ClassVar[str]
    config_schema: ClassVar[dict]

    def create_initial_state(
        self,
        players: list[Player],
        config: GameConfig,
    ) -> tuple[dict, Phase, list[Event]]:
        ...

    def validate_config(self, options: dict) -> list[str]:
        ...

    def get_valid_actions(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> list[dict]:
        ...

    def validate_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
    ) -> str | None:
        ...

    def apply_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        ...

    def get_player_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId | None,
        players: list[Player],
    ) -> dict:
        ...

    def resolve_concurrent_actions(
        self,
        game_data: dict,
        phase: Phase,
        actions: dict[str, Action],
        players: list[Player],
    ) -> TransitionResult:
        ...

    def state_to_ai_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> dict:
        ...

    def parse_ai_action(
        self,
        response: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> Action:
        ...

    def on_player_disconnect(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> dict | None:
        ...

    def get_spectator_summary(
        self,
        game_data: dict,
        phase: Phase,
        players: list[Player],
    ) -> dict:
        ...
