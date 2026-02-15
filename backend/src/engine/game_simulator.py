"""Synchronous game simulator — advances game state through auto-resolve phases.

Used by MCTS (to simulate forward from a position) and the Arena (to play
complete games without async/DB/WebSocket overhead).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from src.engine.models import Action, GameResult, Phase, Player, PlayerId
from src.engine.protocol import GamePlugin


@dataclass
class SimulationState:
    """Mutable game state for synchronous simulation."""

    game_data: dict
    phase: Phase
    players: list[Player]
    scores: dict[str, float] = field(default_factory=dict)
    game_over: GameResult | None = None


def apply_action_and_resolve(
    plugin: GamePlugin,
    state: SimulationState,
    action: Action,
) -> None:
    """Apply an action and auto-resolve all subsequent auto-resolve phases.

    Mutates *state* in place.  After return, ``state.phase`` is either a
    non-auto-resolve phase (player needs to act) or ``state.game_over`` is set.
    """
    result = plugin.apply_action(
        state.game_data, state.phase, action, state.players
    )
    state.game_data = result.game_data
    state.phase = result.next_phase
    state.scores = result.scores or state.scores
    state.game_over = result.game_over

    if state.game_over:
        return

    # Auto-resolve loop
    max_auto = 50  # safety limit
    while state.phase.auto_resolve and not state.game_over and max_auto > 0:
        max_auto -= 1

        pid = _phase_player_id(state.phase, state.players)
        synthetic = Action(action_type=state.phase.name, player_id=pid)

        result = plugin.apply_action(
            state.game_data, state.phase, synthetic, state.players
        )
        state.game_data = result.game_data
        state.phase = result.next_phase
        state.scores = result.scores or state.scores
        state.game_over = result.game_over


def clone_state(state: SimulationState) -> SimulationState:
    """Deep-copy a simulation state.

    ``players`` is shared (immutable during a game).
    """
    return SimulationState(
        game_data=copy.deepcopy(state.game_data),
        phase=state.phase.model_copy(deep=True),
        players=state.players,  # shared — never mutated
        scores=dict(state.scores),
        game_over=state.game_over,
    )


def _phase_player_id(phase: Phase, players: list[Player]) -> PlayerId:
    """Extract the acting player from a phase, falling back to first player."""
    if phase.expected_actions:
        pid = phase.expected_actions[0].player_id
        if pid is not None:
            return pid
    pi = phase.metadata.get("player_index")
    if pi is not None and pi < len(players):
        return players[pi].player_id
    return players[0].player_id if players else PlayerId("system")
