"""Monte Carlo Tree Search — game-agnostic, with pluggable evaluation.

Uses determinization (Information Set MCTS) to handle stochastic elements
such as random tile draws.  Leaf nodes are scored by a heuristic evaluation
function rather than random rollouts, which is both faster and more accurate
for games where random play is far from competent play.
"""

from __future__ import annotations

import copy
import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable

from src.engine.game_simulator import (
    SimulationState,
    apply_action_and_resolve,
    clone_state,
)
from src.engine.models import Action, Phase, Player, PlayerId
from src.engine.protocol import GamePlugin

# Type alias for the evaluation function.
# (game_data, phase, player_id, players, plugin) → float in [0, 1]
EvalFn = Callable[[dict, Phase, PlayerId, list[Player], GamePlugin], float]


# ------------------------------------------------------------------
# MCTS node
# ------------------------------------------------------------------

@dataclass
class MCTSNode:
    """A node in the MCTS search tree."""

    action_taken: dict | None  # action payload that led here (None for root)
    parent: MCTSNode | None
    acting_player: PlayerId | None = None  # who acted to reach this node
    children: list[MCTSNode] = field(default_factory=list)
    untried_actions: list[dict] | None = None  # None = not yet expanded
    visit_count: int = 0
    total_value: float = 0.0

    @property
    def q_value(self) -> float:
        if self.visit_count == 0:
            return 0.0
        return self.total_value / self.visit_count

    def uct_value(self, parent_visits: int, c: float) -> float:
        if self.visit_count == 0:
            return float("inf")
        exploit = self.total_value / self.visit_count
        explore = c * math.sqrt(math.log(parent_visits) / self.visit_count)
        return exploit + explore

    def best_child_uct(self, c: float) -> MCTSNode:
        return max(self.children, key=lambda ch: ch.uct_value(self.visit_count, c))

    def most_visited_child(self) -> MCTSNode:
        return max(self.children, key=lambda ch: ch.visit_count)


# ------------------------------------------------------------------
# Main search entry point
# ------------------------------------------------------------------


def mcts_search(
    game_data: dict,
    phase: Phase,
    player_id: PlayerId,
    plugin: GamePlugin,
    *,
    players: list[Player] | None = None,
    num_simulations: int = 500,
    time_limit_ms: float = 2000,
    exploration_constant: float = 1.41,
    num_determinizations: int = 5,
    eval_fn: EvalFn | None = None,
) -> dict:
    """Run MCTS and return the best action payload for *player_id*.

    Parameters
    ----------
    game_data, phase, player_id:
        Current game state where a decision is needed.
    plugin:
        The game plugin (used for valid actions, apply, etc.).
    players:
        Player list.  If *None*, synthetic players are built from
        ``game_data["scores"]`` keys.
    num_simulations:
        Max MCTS iterations across all determinizations.
    time_limit_ms:
        Hard wall-clock budget (ms) across all determinizations.
    exploration_constant:
        UCT exploration constant *C*.
    num_determinizations:
        How many random tile-bag shuffles to average over.
    eval_fn:
        Heuristic leaf evaluator.  Falls back to a score-differential
        sigmoid if not provided.
    """
    if players is None:
        score_keys = list(game_data.get("scores", {}).keys())
        players = [
            Player(player_id=PlayerId(pid), display_name=pid, seat_index=i)
            for i, pid in enumerate(score_keys)
        ]

    if eval_fn is None:
        eval_fn = _default_eval_fn

    valid_actions = plugin.get_valid_actions(game_data, phase, player_id)
    if len(valid_actions) <= 1:
        return valid_actions[0] if valid_actions else {}

    # Aggregate visit counts across determinizations
    action_visits: dict[str, int] = {}
    action_values: dict[str, float] = {}
    action_map: dict[str, dict] = {}

    sims_per_det = max(1, num_simulations // num_determinizations)
    total_deadline = time.monotonic() + time_limit_ms / 1000.0
    time_per_det = time_limit_ms / num_determinizations / 1000.0

    rng = random.Random()

    for _det_idx in range(num_determinizations):
        det_deadline = min(time.monotonic() + time_per_det, total_deadline)
        if time.monotonic() >= total_deadline:
            break

        # Create a determinized copy — shuffle the tile bag
        det_game_data = copy.deepcopy(game_data)
        remaining_bag = det_game_data.get("tile_bag")
        if remaining_bag:
            rng.shuffle(remaining_bag)

        root_state = SimulationState(
            game_data=det_game_data,
            phase=phase.model_copy(deep=True),
            players=players,
            scores=dict(game_data.get("scores", {})),
        )

        root = MCTSNode(action_taken=None, parent=None)

        for _sim_i in range(sims_per_det):
            if time.monotonic() >= det_deadline:
                break
            _run_one_iteration(
                root, root_state, player_id, players, plugin,
                exploration_constant, eval_fn,
            )

        # Collect visit counts from this determinization's tree
        for child in root.children:
            key = _action_key(child.action_taken)
            action_map[key] = child.action_taken
            action_visits[key] = action_visits.get(key, 0) + child.visit_count
            action_values[key] = action_values.get(key, 0.0) + child.total_value

    if not action_visits:
        # Fallback: no iterations completed, pick first valid
        return valid_actions[0]

    best_key = max(action_visits, key=lambda k: action_visits[k])
    return action_map[best_key]


# ------------------------------------------------------------------
# Single MCTS iteration
# ------------------------------------------------------------------


def _run_one_iteration(
    root: MCTSNode,
    root_state: SimulationState,
    searching_player: PlayerId,
    players: list[Player],
    plugin: GamePlugin,
    c: float,
    eval_fn: EvalFn,
) -> None:
    """One MCTS iteration: select → expand → evaluate → backpropagate."""
    node = root
    state = clone_state(root_state)

    # 1. SELECT — walk down using UCT
    while (
        node.untried_actions is not None
        and len(node.untried_actions) == 0
        and node.children
    ):
        node = node.best_child_uct(c)
        if node.action_taken is not None and node.acting_player is not None:
            _apply_node_action(state, node, plugin)

    # 2. EXPAND — if this node hasn't been expanded yet, discover actions
    if state.game_over is None and node.untried_actions is None:
        acting_pid = _get_acting_player(state.phase, players)
        if acting_pid:
            node.untried_actions = plugin.get_valid_actions(
                state.game_data, state.phase, acting_pid
            )
        else:
            node.untried_actions = []

    # Pick one untried action and create a child node
    if state.game_over is None and node.untried_actions:
        idx = random.randrange(len(node.untried_actions))
        action_payload = node.untried_actions.pop(idx)
        acting_pid = _get_acting_player(state.phase, players)

        child = MCTSNode(
            action_taken=action_payload,
            parent=node,
            acting_player=acting_pid,
        )
        node.children.append(child)
        node = child

        if acting_pid:
            _apply_node_action(state, node, plugin)

    # 3. EVALUATE
    if state.game_over is not None:
        value = _terminal_value(state, searching_player)
    else:
        value = eval_fn(
            state.game_data, state.phase, searching_player, players, plugin
        )

    # 4. BACKPROPAGATE
    while node is not None:
        node.visit_count += 1
        # Value is always from searching_player's perspective.
        # For opponent nodes, invert.
        if node.acting_player is None or node.acting_player == searching_player:
            node.total_value += value
        else:
            node.total_value += 1.0 - value
        node = node.parent


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _apply_node_action(
    state: SimulationState,
    node: MCTSNode,
    plugin: GamePlugin,
) -> None:
    """Apply a node's action to the simulation state."""
    action_type = (
        state.phase.expected_actions[0].action_type
        if state.phase.expected_actions
        else state.phase.name
    )
    action = Action(
        action_type=action_type,
        player_id=node.acting_player,
        payload=node.action_taken,
    )
    apply_action_and_resolve(plugin, state, action)


def _get_acting_player(phase: Phase, players: list[Player]) -> PlayerId | None:
    """Who needs to act in this phase?"""
    if phase.expected_actions:
        return phase.expected_actions[0].player_id
    pi = phase.metadata.get("player_index")
    if pi is not None and pi < len(players):
        return players[pi].player_id
    return None


def _terminal_value(state: SimulationState, player_id: PlayerId) -> float:
    """Convert a terminal game result to [0, 1]."""
    result = state.game_over
    if not result:
        return 0.5
    if player_id in result.winners:
        return 1.0 if len(result.winners) == 1 else 0.8
    return 0.0


def _action_key(action: dict | None) -> str:
    """Deterministic string key for an action payload."""
    if action is None:
        return ""
    if "x" in action and "y" in action and "rotation" in action:
        return f"{action['x']},{action['y']},{action['rotation']}"
    if action.get("skip"):
        return "skip"
    if "meeple_spot" in action:
        return f"meeple:{action['meeple_spot']}"
    return json.dumps(action, sort_keys=True)


def _default_eval_fn(
    game_data: dict,
    phase: Phase,
    player_id: PlayerId,
    players: list[Player],
    plugin: GamePlugin,
) -> float:
    """Simple fallback: sigmoid of score differential."""
    scores = game_data.get("scores", {})
    my_score = scores.get(player_id, 0)
    others = [s for pid, s in scores.items() if pid != player_id]
    if not others:
        return 0.5
    diff = my_score - max(others)
    return 1.0 / (1.0 + math.exp(-diff / 20.0))
