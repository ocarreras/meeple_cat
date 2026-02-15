"""Heuristic evaluation function for Carcassonne MCTS.

Returns a value in [0, 1] representing how good the position is for the
given player (0 = lost, 0.5 = even, 1 = winning).
"""

from __future__ import annotations

import math

from src.engine.models import Phase, Player, PlayerId
from src.engine.protocol import GamePlugin
from src.games.carcassonne.types import FeatureType


def carcassonne_eval(
    game_data: dict,
    phase: Phase,
    player_id: PlayerId,
    players: list[Player],
    plugin: GamePlugin,
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
    score_component = _sigmoid(score_diff, scale=25.0)

    # ------------------------------------------------------------------
    # 2. Incomplete feature potential
    # ------------------------------------------------------------------
    my_potential = 0.0
    opp_potential = 0.0

    for feat in features.values():
        if feat.get("is_complete"):
            continue

        ft = feat["feature_type"]
        if ft in (FeatureType.FIELD, "field"):
            continue  # handled separately

        meeples = feat.get("meeples", [])
        if not meeples:
            continue

        controller, controlled_by_me = _feature_controller(meeples, player_id)
        if controller is None:
            continue

        tiles = feat.get("tiles", [])
        open_edges = feat.get("open_edges", [])
        pennants = feat.get("pennants", 0)

        if ft in (FeatureType.CITY, "city"):
            completion_prob = _completion_probability(len(open_edges), tiles_remaining)
            potential = (
                completion_prob * (len(tiles) * 2 + pennants * 2)
                + (1 - completion_prob) * (len(tiles) + pennants)
            )
        elif ft in (FeatureType.ROAD, "road"):
            potential = float(len(tiles))
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
                potential = completion_prob * 9 + (1 - completion_prob) * (
                    1 + neighbors
                )
            else:
                potential = 0.0
        else:
            continue

        if controlled_by_me:
            my_potential += potential
        else:
            opp_potential += potential

    potential_diff = my_potential - opp_potential
    potential_component = _sigmoid(potential_diff, scale=15.0)

    # ------------------------------------------------------------------
    # 3. Meeple economy
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
    if my_meeples >= 6 and game_progress > 0.2:
        meeple_value *= 0.8

    relative = _sigmoid((my_meeples - avg_opp_meeples) * 0.5, scale=3.0)
    meeple_component = 0.5 * relative + 0.5 * meeple_value

    # ------------------------------------------------------------------
    # 4. Field scoring potential
    # ------------------------------------------------------------------
    my_field = _estimate_field_value(game_data, player_id)
    opp_field_scores = [
        _estimate_field_value(game_data, p.player_id)
        for p in players
        if p.player_id != player_id
    ]
    max_opp_field = max(opp_field_scores) if opp_field_scores else 0
    field_diff = my_field - max_opp_field
    field_component = _sigmoid(field_diff, scale=10.0)

    # ------------------------------------------------------------------
    # Weighted combination (weights shift from early to late game)
    # ------------------------------------------------------------------
    score_weight = 0.35 + 0.10 * game_progress       # 0.35 → 0.45
    potential_weight = 0.35 - 0.15 * game_progress    # 0.35 → 0.20
    meeple_weight = 0.20 - 0.05 * game_progress      # 0.20 → 0.15
    field_weight = 0.10 + 0.10 * game_progress        # 0.10 → 0.20

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


def _estimate_field_value(game_data: dict, player_id: str) -> float:
    """Estimate end-game field points for *player_id*."""
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

    return total
