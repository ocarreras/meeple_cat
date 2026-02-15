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

# Disconnect policies — declared as ClassVar on each game plugin
DISCONNECT_POLICY_ABANDON_ALL = "abandon_all"
DISCONNECT_POLICY_FORFEIT_PLAYER = "forfeit_player"


@runtime_checkable
class GamePlugin(Protocol):
    """Interface that every game must implement."""

    game_id: ClassVar[str]
    display_name: ClassVar[str]
    min_players: ClassVar[int]
    max_players: ClassVar[int]
    description: ClassVar[str]
    config_schema: ClassVar[dict]
    disconnect_policy: ClassVar[str]  # DISCONNECT_POLICY_ABANDON_ALL or DISCONNECT_POLICY_FORFEIT_PLAYER

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

    def on_player_forfeit(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> TransitionResult | None:
        """Called when a forfeited player's turn comes up.

        The plugin should advance past the forfeited player's turn.
        Return a TransitionResult to skip their turn, or None if
        the engine should handle it generically.
        """
        ...

    def get_spectator_summary(
        self,
        game_data: dict,
        phase: Phase,
        players: list[Player],
    ) -> dict:
        ...
