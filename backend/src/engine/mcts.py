"""Monte Carlo Tree Search — game-agnostic, with pluggable evaluation.

Uses determinization (Information Set MCTS) to handle stochastic elements
such as random tile draws.  Leaf nodes are scored by a heuristic evaluation
function rather than random rollouts, which is both faster and more accurate
for games where random play is far from competent play.

Supports **progressive widening** to focus search on the most promising
actions when the branching factor is large (e.g. 50+ tile placements).

Supports **RAVE/AMAF** (Rapid Action Value Estimation / All-Moves-As-First)
to share action-value statistics across sibling branches, speeding up
convergence when visit counts are low.
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

    # AMAF / RAVE statistics (populated only when use_rave=True)
    # Keyed by action_key (or amaf_key) string → count and total value
    amaf_visits: dict[str, int] = field(default_factory=dict)
    amaf_values: dict[str, float] = field(default_factory=dict)

    # Tile-aware AMAF key (set when tile_aware_amaf=True)
    amaf_key: str = ""

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

    def rave_value(
        self, parent_visits: int, c: float, rave_k: float,
        rave_fpu: bool = False,
    ) -> float:
        """UCT + RAVE blended value for child selection.

        Combines standard UCT exploitation with AMAF statistics from the
        parent node.  The blend weight β decreases as the parent gets more
        visits, eventually converging to pure UCT.

        When *rave_fpu* is True and the child is unvisited, uses AMAF data
        as a first-play urgency prior instead of returning infinity.
        """
        action_k = self.amaf_key or _action_key(self.action_taken)

        if self.visit_count == 0:
            if rave_fpu and self.parent is not None:
                amaf_n = self.parent.amaf_visits.get(action_k, 0)
                if amaf_n > 0:
                    amaf_q = self.parent.amaf_values.get(action_k, 0.0) / amaf_n
                    # Range [1.0, 2.0] — still explore, but prefer promising
                    return 1.0 + amaf_q
            return float("inf")

        q_uct = self.total_value / self.visit_count

        # Look up AMAF stats in parent for this child's action
        amaf_n = 0
        amaf_q = 0.5  # prior when no AMAF data
        if self.parent is not None:
            amaf_n = self.parent.amaf_visits.get(action_k, 0)
            if amaf_n > 0:
                amaf_q = self.parent.amaf_values.get(action_k, 0.0) / amaf_n

        # β ∈ [0, 1]: high when parent_visits is low, approaches 0 as visits grow
        beta = math.sqrt(rave_k / (3.0 * parent_visits + rave_k))
        blended = (1.0 - beta) * q_uct + beta * amaf_q

        explore = c * math.sqrt(math.log(parent_visits) / self.visit_count)
        return blended + explore

    def best_child_uct(self, c: float) -> MCTSNode:
        return max(self.children, key=lambda ch: ch.uct_value(self.visit_count, c))

    def best_child_rave(
        self, c: float, rave_k: float, rave_fpu: bool = False,
    ) -> MCTSNode:
        return max(
            self.children,
            key=lambda ch: ch.rave_value(self.visit_count, c, rave_k, rave_fpu),
        )

    def most_visited_child(self) -> MCTSNode:
        return max(self.children, key=lambda ch: ch.visit_count)


# ------------------------------------------------------------------
# Progressive widening helpers
# ------------------------------------------------------------------


def _max_children(visit_count: int, pw_c: float, pw_alpha: float) -> int:
    """Maximum number of children allowed by progressive widening."""
    return max(1, int(pw_c * max(1, visit_count) ** pw_alpha))


_MEEPLE_SPOT_PRIORITY: dict[str, int] = {
    "city": 0,
    "monastery": 1,
    "road": 2,
    "field": 3,
}


def _action_sort_key(action: dict) -> tuple:
    """Sort key for action ordering (lower = higher priority).

    For tile placements: prefer positions adjacent to more tiles (heuristic:
    positions closer to the origin tend to be more connected).
    For meeple placements: city > monastery > road > field > skip.
    """
    if action.get("skip"):
        return (10,)
    if "meeple_spot" in action:
        spot = action["meeple_spot"]
        # Spot format: "city_N", "road_S", "field_NE_NW", "monastery"
        prefix = spot.split("_")[0] if "_" in spot else spot
        return (1, _MEEPLE_SPOT_PRIORITY.get(prefix, 5))
    if "x" in action and "y" in action:
        # Prefer positions closer to origin (likely more connected)
        return (0, abs(action["x"]) + abs(action["y"]))
    return (5,)


# ------------------------------------------------------------------
# RAVE β computation (exported for testing)
# ------------------------------------------------------------------


def rave_beta(parent_visits: int, rave_k: float) -> float:
    """Compute the RAVE blending weight β.

    β = sqrt(rave_k / (3 * parent_visits + rave_k))
    β ≈ 1 when parent_visits is small, β → 0 as parent_visits grows.
    """
    return math.sqrt(rave_k / (3.0 * parent_visits + rave_k))


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
    pw_c: float = 2.0,
    pw_alpha: float = 0.5,
    use_rave: bool = False,
    rave_k: float = 100.0,
    max_amaf_depth: int = 4,
    rave_fpu: bool = True,
    tile_aware_amaf: bool = False,
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
    pw_c:
        Progressive widening constant.  A node may have at most
        ``pw_c * visits^pw_alpha`` children.  Set ``pw_alpha=0`` to
        disable widening (every action expanded immediately).
    pw_alpha:
        Progressive widening exponent (0 = disabled, 0.5 = sqrt).
    use_rave:
        Enable RAVE/AMAF statistics for faster convergence.
    rave_k:
        RAVE equivalence parameter.  Higher values trust AMAF longer
        before falling back to pure UCT.
    max_amaf_depth:
        Maximum number of plies below a node to propagate AMAF stats.
        0 = unlimited (original behaviour).  Default 4 = 2 full turns.
    rave_fpu:
        When True, use AMAF as a first-play urgency prior for unvisited
        children instead of infinity.
    tile_aware_amaf:
        When True, include tile type in AMAF keys to prevent conflation
        of different tiles at the same board position.
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
                exploration_constant, eval_fn, pw_c, pw_alpha,
                use_rave, rave_k, max_amaf_depth, rave_fpu,
                tile_aware_amaf,
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
    pw_c: float,
    pw_alpha: float,
    use_rave: bool,
    rave_k: float,
    max_amaf_depth: int = 4,
    rave_fpu: bool = True,
    tile_aware_amaf: bool = False,
) -> None:
    """One MCTS iteration: select → expand → evaluate → backpropagate."""
    node = root
    state = clone_state(root_state)

    # Track actions played in this iteration for AMAF updates
    played_actions: list[tuple[str, PlayerId | None]] = []

    # Helper to build the appropriate AMAF key
    def _make_key(action: dict) -> str:
        if tile_aware_amaf:
            return _amaf_key(action, state)
        return _action_key(action)

    # 1. SELECT — walk down using UCT (or UCT+RAVE) while node is "fully widened"
    while node.children and _at_widening_limit(node, pw_c, pw_alpha):
        if use_rave:
            node = node.best_child_rave(c, rave_k, rave_fpu)
        else:
            node = node.best_child_uct(c)
        if node.action_taken is not None and node.acting_player is not None:
            # Set amaf_key on first traversal if tile-aware mode
            if tile_aware_amaf and not node.amaf_key:
                node.amaf_key = _amaf_key(node.action_taken, state)
            played_actions.append(
                (node.amaf_key or _action_key(node.action_taken), node.acting_player)
            )
            _apply_node_action(state, node, plugin)

    # 2. EXPAND — if this node hasn't been expanded yet, discover actions
    if state.game_over is None and node.untried_actions is None:
        acting_pid = _get_acting_player(state.phase, players)
        if acting_pid:
            actions = plugin.get_valid_actions(
                state.game_data, state.phase, acting_pid
            )
            # Sort by heuristic priority so best actions are expanded first
            actions.sort(key=_action_sort_key)
            node.untried_actions = actions
        else:
            node.untried_actions = []

    # Pick one untried action if below widening limit
    should_expand = (
        state.game_over is None
        and node.untried_actions
        and not _at_widening_limit(node, pw_c, pw_alpha)
    )

    if should_expand:
        # Take the first untried action (list is priority-sorted)
        action_payload = node.untried_actions.pop(0)
        acting_pid = _get_acting_player(state.phase, players)

        child = MCTSNode(
            action_taken=action_payload,
            parent=node,
            acting_player=acting_pid,
            amaf_key=_make_key(action_payload) if use_rave else "",
        )
        node.children.append(child)
        node = child

        if acting_pid:
            played_actions.append((child.amaf_key or _action_key(action_payload), acting_pid))
            _apply_node_action(state, node, plugin)

    # 3. EVALUATE
    if state.game_over is not None:
        value = _terminal_value(state, searching_player)
    else:
        value = eval_fn(
            state.game_data, state.phase, searching_player, players, plugin
        )

    # 4. BACKPROPAGATE
    _backpropagate(node, value, searching_player, played_actions, use_rave,
                   max_amaf_depth)


def _backpropagate(
    leaf: MCTSNode,
    value: float,
    searching_player: PlayerId,
    played_actions: list[tuple[str, PlayerId | None]],
    use_rave: bool,
    max_amaf_depth: int = 0,
) -> None:
    """Walk back to root, updating visit counts and optionally AMAF stats.

    When *max_amaf_depth* > 0, only actions within that many plies below
    a node contribute to its AMAF statistics.  0 = unlimited.
    """
    node = leaf
    depth = len(played_actions)

    while node is not None:
        node.visit_count += 1
        # Value is always from searching_player's perspective.
        # For opponent nodes, invert.
        if node.acting_player is None or node.acting_player == searching_player:
            node.total_value += value
        else:
            node.total_value += 1.0 - value

        # AMAF update: for each action played BELOW this node, update AMAF stats
        if use_rave and depth < len(played_actions):
            # Depth-limited AMAF: only consider nearby actions
            if max_amaf_depth > 0:
                end_i = min(len(played_actions), depth + max_amaf_depth)
            else:
                end_i = len(played_actions)
            for i in range(depth, end_i):
                ak, player = played_actions[i]
                # Update AMAF from searching_player's perspective
                node.amaf_visits[ak] = node.amaf_visits.get(ak, 0) + 1
                if player is None or player == searching_player:
                    node.amaf_values[ak] = node.amaf_values.get(ak, 0.0) + value
                else:
                    node.amaf_values[ak] = node.amaf_values.get(ak, 0.0) + (1.0 - value)

        depth -= 1
        node = node.parent


def _at_widening_limit(node: MCTSNode, pw_c: float, pw_alpha: float) -> bool:
    """Check if a node has reached its progressive widening child limit."""
    if not node.untried_actions:
        # No more actions to expand — always at limit
        return True
    limit = _max_children(node.visit_count, pw_c, pw_alpha)
    return len(node.children) >= limit


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


def _amaf_key(action: dict | None, state: SimulationState | None = None) -> str:
    """AMAF key that optionally includes tile context.

    When *state* is provided and the action is a tile placement, prepends
    the current tile type to prevent conflating different tiles at the same
    position across different tree depths.
    """
    if action is None:
        return ""
    if (
        state is not None
        and "x" in action
        and "y" in action
        and "rotation" in action
    ):
        tile = state.game_data.get("current_tile", "")
        if tile:
            return f"{tile}:{action['x']},{action['y']},{action['rotation']}"
    return _action_key(action)


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
