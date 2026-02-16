"""Heuristic evaluation function for Carcassonne MCTS.

Returns a value in [0, 1] representing how good the position is for the
given player (0 = lost, 0.5 = even, 1 = winning).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from src.engine.models import Phase, Player, PlayerId
from src.engine.protocol import GamePlugin
from src.games.carcassonne.types import FeatureType

# Type alias matching mcts.EvalFn
EvalFn = Callable[[dict, Phase, PlayerId, list[Player], GamePlugin], float]


# ------------------------------------------------------------------
# Configurable weight profiles
# ------------------------------------------------------------------


@dataclass
class EvalWeights:
    """Tunable parameters for the Carcassonne heuristic evaluator.

    Component weights follow ``base + delta * game_progress`` where
    *game_progress* goes from 0.0 (start) to 1.0 (end).
    """

    # Score differential
    score_base: float = 0.35
    score_delta: float = 0.10  # 0.35 → 0.45
    score_scale: float = 25.0

    # Incomplete feature potential
    potential_base: float = 0.35
    potential_delta: float = -0.15  # 0.35 → 0.20
    potential_scale: float = 15.0

    # Meeple economy
    meeple_base: float = 0.20
    meeple_delta: float = -0.05  # 0.20 → 0.15
    meeple_hoard_threshold: int = 6
    meeple_hoard_penalty: float = 0.8
    meeple_hoard_progress_gate: float = 0.2

    # Field scoring potential
    field_base: float = 0.10
    field_delta: float = 0.10  # 0.10 → 0.20
    field_scale: float = 10.0


DEFAULT_WEIGHTS = EvalWeights()

AGGRESSIVE_WEIGHTS = EvalWeights(
    score_base=0.45,
    score_delta=0.10,
    potential_base=0.30,
    potential_delta=-0.15,
    meeple_base=0.10,
    meeple_delta=-0.05,
    field_base=0.15,
    field_delta=0.10,
    meeple_hoard_threshold=5,
    meeple_hoard_progress_gate=0.15,
)

FIELD_HEAVY_WEIGHTS = EvalWeights(
    score_base=0.30,
    score_delta=0.10,
    potential_base=0.25,
    potential_delta=-0.10,
    meeple_base=0.20,
    meeple_delta=-0.05,
    field_base=0.25,
    field_delta=0.15,
    field_scale=8.0,
)

CONSERVATIVE_WEIGHTS = EvalWeights(
    score_base=0.30,
    score_delta=0.10,
    potential_base=0.25,
    potential_delta=-0.10,
    meeple_base=0.30,
    meeple_delta=-0.05,
    field_base=0.15,
    field_delta=0.05,
    meeple_hoard_threshold=7,
    meeple_hoard_penalty=0.9,
)

WEIGHT_PRESETS: dict[str, EvalWeights] = {
    "default": DEFAULT_WEIGHTS,
    "aggressive": AGGRESSIVE_WEIGHTS,
    "field_heavy": FIELD_HEAVY_WEIGHTS,
    "conservative": CONSERVATIVE_WEIGHTS,
}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def make_carcassonne_eval(weights: EvalWeights | None = None) -> EvalFn:
    """Return an evaluation function parameterised by *weights*."""
    w = weights or DEFAULT_WEIGHTS

    def _eval(
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
        plugin: GamePlugin,
    ) -> float:
        return _evaluate(game_data, phase, player_id, players, plugin, w)

    return _eval


def carcassonne_eval(
    game_data: dict,
    phase: Phase,
    player_id: PlayerId,
    players: list[Player],
    plugin: GamePlugin,
) -> float:
    """Evaluate a Carcassonne position using default weights."""
    return _evaluate(game_data, phase, player_id, players, plugin, DEFAULT_WEIGHTS)


# ------------------------------------------------------------------
# Core evaluation
# ------------------------------------------------------------------


def _evaluate(
    game_data: dict,
    phase: Phase,
    player_id: PlayerId,
    players: list[Player],
    plugin: GamePlugin,
    w: EvalWeights,
) -> float:
    """Evaluate a Carcassonne position for *player_id*.

    Components (weights shift during the game):

    1. Score differential  — current points vs best opponent
    2. Feature potential    — expected value of incomplete features with meeples
    3. Meeple economy      — available meeples vs opponents
    4. Field potential      — estimated end-game field scoring
    """
    scores = game_data.get("scores", {})
    features = game_data.get("features", {})
    meeple_supply = game_data.get("meeple_supply", {})
    tiles_remaining = len(game_data.get("tile_bag", []))
    board_size = len(game_data["board"]["tiles"])
    total_tiles = board_size + tiles_remaining
    game_progress = 1.0 - (tiles_remaining / max(total_tiles, 1))

    # ------------------------------------------------------------------
    # 1. Score differential
    # ------------------------------------------------------------------
    my_score = scores.get(player_id, 0)
    opponent_scores = [s for pid, s in scores.items() if pid != player_id]
    max_opp = max(opponent_scores) if opponent_scores else 0
    score_diff = my_score - max_opp
    score_component = _sigmoid(score_diff, scale=w.score_scale)

    # ------------------------------------------------------------------
    # 2. Incomplete feature potential (with contested-feature awareness)
    # ------------------------------------------------------------------
    my_potential = 0.0
    opp_potential = 0.0
    wasted_meeple_penalty = 0.0

    for feat in features.values():
        if feat.get("is_complete"):
            continue

        ft = feat["feature_type"]
        if ft in (FeatureType.FIELD, "field"):
            continue  # handled separately

        meeples = feat.get("meeples", [])
        if not meeples:
            continue

        tiles = feat.get("tiles", [])
        open_edges = feat.get("open_edges", [])
        pennants = feat.get("pennants", 0)

        # Estimate raw potential value of this feature
        potential = _raw_feature_potential(
            ft, tiles, open_edges, pennants, tiles_remaining, game_data
        )

        # Determine control and attribute value
        my_count, max_count, total_opp = _meeple_counts(meeples, player_id)

        if my_count == 0:
            # Only opponent meeples — attribute to opponent
            opp_potential += potential
        elif my_count >= max_count:
            # We control (or tie) — attribute to us
            my_potential += potential
        else:
            # We have meeples but don't control → wasted investment
            # Opponent gets the value, we get a penalty for the wasted meeples
            opp_potential += potential
            wasted_meeple_penalty += my_count * 1.5

    potential_diff = my_potential - opp_potential - wasted_meeple_penalty
    potential_component = _sigmoid(potential_diff, scale=w.potential_scale)

    # ------------------------------------------------------------------
    # 3. Meeple economy (with scarcity awareness)
    # ------------------------------------------------------------------
    my_meeples = meeple_supply.get(player_id, 0)
    opp_meeples = [
        meeple_supply.get(p.player_id, 0)
        for p in players
        if p.player_id != player_id
    ]
    avg_opp_meeples = sum(opp_meeples) / max(len(opp_meeples), 1)

    meeple_value = min(my_meeples / 7.0, 1.0)

    # Penalise hoarding (not investing) after the early game
    if my_meeples >= w.meeple_hoard_threshold and game_progress > w.meeple_hoard_progress_gate:
        meeple_value *= w.meeple_hoard_penalty

    # Scarcity penalty: 0 meeples with game still going is very bad
    if my_meeples == 0 and game_progress < 0.85:
        meeple_value *= 0.3
    elif my_meeples <= 1 and game_progress < 0.7:
        meeple_value *= 0.6

    relative = _sigmoid((my_meeples - avg_opp_meeples) * 0.5, scale=3.0)
    meeple_component = 0.5 * relative + 0.5 * meeple_value

    # ------------------------------------------------------------------
    # 4. Field scoring potential (with nearly-complete city awareness)
    # ------------------------------------------------------------------
    my_field = _estimate_field_value(game_data, player_id, tiles_remaining)
    opp_field_scores = [
        _estimate_field_value(game_data, p.player_id, tiles_remaining)
        for p in players
        if p.player_id != player_id
    ]
    max_opp_field = max(opp_field_scores) if opp_field_scores else 0
    field_diff = my_field - max_opp_field
    field_component = _sigmoid(field_diff, scale=w.field_scale)

    # ------------------------------------------------------------------
    # Weighted combination (weights shift from early to late game)
    # ------------------------------------------------------------------
    score_weight = w.score_base + w.score_delta * game_progress
    potential_weight = w.potential_base + w.potential_delta * game_progress
    meeple_weight = w.meeple_base + w.meeple_delta * game_progress
    field_weight = w.field_base + w.field_delta * game_progress

    value = (
        score_weight * score_component
        + potential_weight * potential_component
        + meeple_weight * meeple_component
        + field_weight * field_component
    )
    return max(0.0, min(1.0, value))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _sigmoid(x: float, scale: float = 20.0) -> float:
    """Map *x* to (0, 1) via a logistic curve."""
    return 1.0 / (1.0 + math.exp(-x / max(scale, 1e-9)))


def _completion_probability(open_edges: int, tiles_remaining: int) -> float:
    """Rough estimate of how likely a feature is to be completed."""
    if open_edges == 0:
        return 1.0
    if tiles_remaining == 0:
        return 0.0
    ratio = tiles_remaining / max(open_edges * 3, 1)
    return min(1.0, ratio * 0.5)


def _meeple_counts(
    meeples: list[dict], player_id: PlayerId
) -> tuple[int, int, int]:
    """Return (my_count, max_opponent_count, total_opponent_count)."""
    counts: dict[str, int] = {}
    for m in meeples:
        pid = m["player_id"]
        counts[pid] = counts.get(pid, 0) + 1
    my_count = counts.pop(player_id, 0)
    opp_counts = list(counts.values())
    max_opp = max(opp_counts) if opp_counts else 0
    total_opp = sum(opp_counts)
    return my_count, max_opp, total_opp


def _feature_controller(
    meeples: list[dict], player_id: PlayerId
) -> tuple[str | None, bool]:
    """Return (controlling_player_id, is_player_id_the_controller)."""
    counts: dict[str, int] = {}
    for m in meeples:
        pid = m["player_id"]
        counts[pid] = counts.get(pid, 0) + 1
    if not counts:
        return None, False
    max_count = max(counts.values())
    # If tied, all tied players "control" — attribute to player if they're one of them
    my_count = counts.get(player_id, 0)
    if my_count == max_count:
        return player_id, True
    # Pick first opponent with max count
    for pid, cnt in counts.items():
        if cnt == max_count:
            return pid, False
    return None, False


def _raw_feature_potential(
    ft: str,
    tiles: list[str],
    open_edges: list,
    pennants: int,
    tiles_remaining: int,
    game_data: dict,
) -> float:
    """Estimate the point value of an incomplete feature."""
    if ft in (FeatureType.CITY, "city"):
        completion_prob = _completion_probability(len(open_edges), tiles_remaining)
        return (
            completion_prob * (len(tiles) * 2 + pennants * 2)
            + (1 - completion_prob) * (len(tiles) + pennants)
        )
    elif ft in (FeatureType.ROAD, "road"):
        return float(len(tiles))
    elif ft in (FeatureType.MONASTERY, "monastery"):
        if tiles:
            board_tiles = game_data["board"]["tiles"]
            from src.games.carcassonne.types import Position

            pos = Position.from_key(tiles[0])
            neighbors = sum(
                1 for p in pos.all_surrounding() if p.to_key() in board_tiles
            )
            completion_prob = _completion_probability(
                8 - neighbors, tiles_remaining
            )
            return completion_prob * 9 + (1 - completion_prob) * (1 + neighbors)
        return 0.0
    return 0.0


def _estimate_field_value(
    game_data: dict, player_id: str, tiles_remaining: int = 0
) -> float:
    """Estimate end-game field points for *player_id*.

    Counts both completed adjacent cities (3 pts each) and nearly-complete
    cities weighted by their completion probability.
    """
    features = game_data.get("features", {})
    total = 0.0

    for feat in features.values():
        ft = feat.get("feature_type")
        if ft not in (FeatureType.FIELD, "field"):
            continue

        meeples = feat.get("meeples", [])
        if not meeples:
            continue

        _, controlled_by_me = _feature_controller(meeples, player_id)
        if not controlled_by_me:
            continue

        from src.games.carcassonne.scoring import _get_adjacent_completed_cities

        adj_cities = _get_adjacent_completed_cities(game_data, feat)
        total += len(adj_cities) * 3

        # Also value nearly-complete adjacent cities
        total += _estimate_nearby_city_potential(
            game_data, feat, adj_cities, tiles_remaining
        )

    return total


def _estimate_nearby_city_potential(
    game_data: dict,
    field_feature: dict,
    already_completed: list[str],
    tiles_remaining: int,
) -> float:
    """Estimate value from adjacent cities that are close to completing."""
    features = game_data.get("features", {})
    tile_feature_map = game_data.get("tile_feature_map", {})
    completed_set = set(already_completed)
    seen_cities: set[str] = set()
    value = 0.0

    for tile_pos in field_feature.get("tiles", []):
        spot_map = tile_feature_map.get(tile_pos, {})
        for spot, fid in spot_map.items():
            if fid in completed_set or fid in seen_cities:
                continue
            city_feat = features.get(fid)
            if city_feat is None:
                continue
            ct = city_feat.get("feature_type")
            if ct not in (FeatureType.CITY, "city"):
                continue
            if city_feat.get("is_complete"):
                continue  # already counted
            seen_cities.add(fid)

            open_edges = city_feat.get("open_edges", [])
            prob = _completion_probability(len(open_edges), tiles_remaining)
            if prob > 0.3:  # only count if reasonably likely to complete
                value += prob * 3  # 3 pts per completed adjacent city

    return value
