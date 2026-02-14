"""Scoring logic for completed features and end-game scoring."""

from __future__ import annotations

from src.games.carcassonne.types import FeatureType, Position


def score_completed_feature(feature: dict) -> dict[str, int]:
    """Score a completed feature. Returns {player_id: points}.

    Scoring rules:
    - City: 2 points per tile + 2 per pennant
    - Road: 1 point per tile
    - Monastery: 9 points (tile + 8 neighbors)
    - Field: not scored during game (end-game only)

    If tied for most meeples, all tied players get full points.
    """
    meeples = feature.get("meeples", [])
    if not meeples:
        return {}

    # Count meeples per player
    meeple_counts: dict[str, int] = {}
    for m in meeples:
        pid = m["player_id"]
        meeple_counts[pid] = meeple_counts.get(pid, 0) + 1

    max_count = max(meeple_counts.values())
    winners = [pid for pid, count in meeple_counts.items() if count == max_count]

    ft = feature["feature_type"]
    tiles = feature.get("tiles", [])

    if ft in (FeatureType.CITY, "city"):
        points = len(tiles) * 2 + feature.get("pennants", 0) * 2
    elif ft in (FeatureType.ROAD, "road"):
        points = len(tiles)
    elif ft in (FeatureType.MONASTERY, "monastery"):
        points = 9
    else:
        return {}  # Fields not scored during game

    return {pid: points for pid in winners}


def score_end_game(
    game_data: dict,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Score all incomplete features and fields at game end.

    Scoring rules for incomplete features:
    - City: 1 point per tile + 1 per pennant (half the complete rate)
    - Road: 1 point per tile
    - Monastery: 1 point per tile (self + present neighbors)
    - Field: 3 points per completed adjacent city

    Returns:
        totals: {player_id: total_points}
        breakdown: {player_id: {category: points}}
            categories: "fields", "roads", "cities", "monasteries"
    """
    scores: dict[str, int] = {}
    breakdown: dict[str, dict[str, int]] = {}
    features = game_data["features"]
    board_tiles = game_data["board"]["tiles"]

    for feature_id, feature in features.items():
        if feature.get("is_complete"):
            continue

        meeples = feature.get("meeples", [])
        if not meeples:
            continue

        meeple_counts: dict[str, int] = {}
        for m in meeples:
            pid = m["player_id"]
            meeple_counts[pid] = meeple_counts.get(pid, 0) + 1

        max_count = max(meeple_counts.values())
        winners = [pid for pid, c in meeple_counts.items() if c == max_count]

        ft = feature["feature_type"]
        tiles = feature.get("tiles", [])

        if ft in (FeatureType.CITY, "city"):
            points = len(tiles) + feature.get("pennants", 0)
            category = "cities"
        elif ft in (FeatureType.ROAD, "road"):
            points = len(tiles)
            category = "roads"
        elif ft in (FeatureType.MONASTERY, "monastery"):
            if tiles:
                pos = Position.from_key(tiles[0])
                neighbors_present = sum(
                    1 for p in pos.all_surrounding()
                    if p.to_key() in board_tiles
                )
                points = 1 + neighbors_present
            else:
                points = 0
            category = "monasteries"
        elif ft in (FeatureType.FIELD, "field"):
            adjacent_cities = _get_adjacent_completed_cities(game_data, feature)
            points = len(adjacent_cities) * 3
            category = "fields"
        else:
            continue

        for pid in winners:
            scores[pid] = scores.get(pid, 0) + points
            if pid not in breakdown:
                breakdown[pid] = {"fields": 0, "roads": 0, "cities": 0, "monasteries": 0}
            breakdown[pid][category] = breakdown[pid].get(category, 0) + points

    return scores, breakdown


def _get_adjacent_completed_cities(
    game_data: dict, field_feature: dict
) -> list[str]:
    """Find all completed cities that border this field.

    A field borders a city if they share a tile AND the field's tile feature
    has adjacent_cities listing the city meeple spot (which maps to a city feature).
    """
    features = game_data["features"]
    tile_feature_map = game_data["tile_feature_map"]

    adjacent_city_ids: set[str] = set()

    for tile_pos in field_feature.get("tiles", []):
        if tile_pos not in tile_feature_map:
            continue

        # Find which meeple spots on this tile belong to this field
        field_spots_on_tile = []
        for spot, fid in tile_feature_map[tile_pos].items():
            if fid == field_feature.get("feature_id"):
                field_spots_on_tile.append(spot)

        # For each field spot, check its adjacent_cities from the original tile definition
        # We need to look up the placed tile to get rotation, then check the rotated features
        _check_field_city_adjacency(
            game_data, tile_pos, field_spots_on_tile,
            field_feature, adjacent_city_ids
        )

    return list(adjacent_city_ids)


def _check_field_city_adjacency(
    game_data: dict,
    tile_pos: str,
    field_spots: list[str],
    field_feature: dict,
    adjacent_city_ids: set[str],
) -> None:
    """Check if field spots on a tile are adjacent to any completed cities."""
    from src.games.carcassonne.tiles import TILE_LOOKUP, get_rotated_features

    board_tiles = game_data["board"]["tiles"]
    tile_feature_map = game_data["tile_feature_map"]
    features = game_data["features"]

    if tile_pos not in board_tiles:
        return

    placed_tile = board_tiles[tile_pos]
    tile_type_id = placed_tile["tile_type_id"]
    rotation = placed_tile["rotation"]

    rotated_features = get_rotated_features(tile_type_id, rotation)

    for tile_feat in rotated_features:
        # Check if any of our field spots are in this tile feature's meeple_spots
        matching_spots = [s for s in tile_feat.meeple_spots if s in field_spots]
        if not matching_spots:
            continue

        # This tile feature has our field spots — check its adjacent_cities
        for city_spot in tile_feat.adjacent_cities:
            # Find which feature this city spot belongs to
            city_feature_id = tile_feature_map.get(tile_pos, {}).get(city_spot)
            if city_feature_id is None:
                continue

            city_feature = features.get(city_feature_id)
            if city_feature is None:
                continue

            if city_feature.get("is_complete"):
                adjacent_city_ids.add(city_feature_id)
