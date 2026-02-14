"""Feature tracking: creation, merging, completion detection."""

from __future__ import annotations

from uuid import uuid4

from src.engine.models import Event
from src.games.carcassonne.tiles import TILE_LOOKUP, get_rotated_features
from src.games.carcassonne.types import (
    DIRECTIONS,
    OPPOSITE_DIRECTION,
    Feature,
    FeatureType,
    Position,
    rotate_edges,
)


def initialize_features_from_tile(
    tile_type_id: str,
    position_key: str,
    rotation: int,
) -> tuple[dict[str, dict], dict[str, dict[str, str]]]:
    """Create features for a single tile (used for the starting tile).

    Returns:
        features: {feature_id: Feature-as-dict}
        tile_feature_map: {position_key: {meeple_spot: feature_id}}
    """
    features: dict[str, dict] = {}
    tile_feature_map: dict[str, dict[str, str]] = {position_key: {}}

    rotated_features = get_rotated_features(tile_type_id, rotation)
    tile_def = TILE_LOOKUP[tile_type_id]
    rotated_edges_map = rotate_edges(tile_def.edges, rotation)

    for tile_feat in rotated_features:
        feature_id = str(uuid4())

        # Calculate open edges for this feature
        open_edges: list[list[str]] = []
        for edge_dir in tile_feat.edges:
            # This edge is open (no adjacent tile connected yet)
            open_edges.append([position_key, edge_dir])

        # Count pennants
        pennants = 1 if tile_feat.has_pennant else 0

        feature = Feature(
            feature_id=feature_id,
            feature_type=tile_feat.feature_type,
            tiles=[position_key],
            meeples=[],
            is_complete=False,
            pennants=pennants,
            open_edges=open_edges,
        )
        features[feature_id] = feature.model_dump()

        # Map meeple spots to this feature
        for spot in tile_feat.meeple_spots:
            tile_feature_map[position_key][spot] = feature_id

    return features, tile_feature_map


def create_and_merge_features(
    game_data: dict,
    tile_type_id: str,
    position_key: str,
    rotation: int,
) -> list[Event]:
    """Place a tile's features on the board and merge with adjacent features.

    Modifies game_data["features"] and game_data["tile_feature_map"] in place.
    Returns a list of merge events.
    """
    events: list[Event] = []
    features = game_data["features"]
    tile_feature_map = game_data["tile_feature_map"]
    board_tiles = game_data["board"]["tiles"]

    # Initialize the feature map for this tile position
    tile_feature_map[position_key] = {}

    rotated_features = get_rotated_features(tile_type_id, rotation)
    tile_def = TILE_LOOKUP[tile_type_id]
    rotated_edges_map = rotate_edges(tile_def.edges, rotation)

    # Step 1: Create features for the new tile
    new_feature_ids: list[str] = []
    # Map from edge direction to the feature that touches that edge on this new tile
    edge_to_feature: dict[str, str] = {}

    for tile_feat in rotated_features:
        feature_id = str(uuid4())

        open_edges: list[list[str]] = []
        for edge_dir in tile_feat.edges:
            open_edges.append([position_key, edge_dir])

        pennants = 1 if tile_feat.has_pennant else 0

        feature = Feature(
            feature_id=feature_id,
            feature_type=tile_feat.feature_type,
            tiles=[position_key],
            meeples=[],
            is_complete=False,
            pennants=pennants,
            open_edges=open_edges,
        )
        features[feature_id] = feature.model_dump()
        new_feature_ids.append(feature_id)

        for spot in tile_feat.meeple_spots:
            tile_feature_map[position_key][spot] = feature_id

        for edge_dir in tile_feat.edges:
            edge_to_feature[edge_dir] = feature_id

    # Step 2: Merge with adjacent tiles
    pos = Position.from_key(position_key)

    for direction in DIRECTIONS:
        neighbor_pos = pos.neighbor(direction)
        neighbor_key = neighbor_pos.to_key()

        if neighbor_key not in board_tiles:
            continue

        if direction not in edge_to_feature:
            # No feature on this edge (shouldn't happen for non-field edges,
            # but fields may not explicitly list all edges)
            continue

        our_feature_id = edge_to_feature[direction]
        # Resolve to current feature (may have been merged already)
        our_feature_id = _resolve_feature_id(features, our_feature_id, tile_feature_map)

        opposite_dir = OPPOSITE_DIRECTION[direction]

        # Find the feature on the adjacent tile that touches the opposite edge
        adj_feature_id = _find_feature_at_edge(
            tile_feature_map, features, neighbor_key, opposite_dir
        )

        if adj_feature_id is None:
            continue

        adj_feature_id = _resolve_feature_id(features, adj_feature_id, tile_feature_map)

        if our_feature_id == adj_feature_id:
            # Already the same feature (can happen after previous merges)
            # Still need to remove the connecting open edges
            _remove_open_edge(features[our_feature_id], position_key, direction)
            _remove_open_edge(features[our_feature_id], neighbor_key, opposite_dir)
            continue

        # Verify same feature type
        if features[our_feature_id]["feature_type"] != features[adj_feature_id]["feature_type"]:
            continue

        # Merge: absorb adj into ours
        merged_id = _merge_features(
            features, tile_feature_map, our_feature_id, adj_feature_id
        )

        # Remove the connecting open edges
        _remove_open_edge(features[merged_id], position_key, direction)
        _remove_open_edge(features[merged_id], neighbor_key, opposite_dir)

        # Update edge_to_feature for subsequent merges
        for d, fid in edge_to_feature.items():
            if fid == adj_feature_id or fid == our_feature_id:
                edge_to_feature[d] = merged_id

        events.append(Event(
            event_type="feature_merged",
            payload={
                "surviving_feature": merged_id,
                "merged_feature": adj_feature_id if merged_id == our_feature_id else our_feature_id,
                "feature_type": features[merged_id]["feature_type"],
            },
        ))

    return events


def _resolve_feature_id(
    features: dict[str, dict],
    feature_id: str,
    tile_feature_map: dict[str, dict[str, str]],
) -> str:
    """Resolve a feature ID that may have been merged into another."""
    if feature_id in features:
        return feature_id
    # Search for which feature absorbed this one
    for fid, feat in features.items():
        if feature_id in feat.get("_merged_from", []):
            return fid
    return feature_id


def _find_feature_at_edge(
    tile_feature_map: dict[str, dict[str, str]],
    features: dict[str, dict],
    position_key: str,
    direction: str,
) -> str | None:
    """Find the feature ID that touches a specific edge on a tile."""
    if position_key not in tile_feature_map:
        return None

    for spot, fid in tile_feature_map[position_key].items():
        if fid not in features:
            continue
        feat = features[fid]
        # Check if this feature has an open edge at this position+direction
        for oe in feat.get("open_edges", []):
            if oe[0] == position_key and oe[1] == direction:
                return fid
        # Also check if the feature's tiles include this position and the
        # original tile feature touched this edge
        # We check open_edges which should contain all un-connected edges
    return None


def _merge_features(
    features: dict[str, dict],
    tile_feature_map: dict[str, dict[str, str]],
    feature_a_id: str,
    feature_b_id: str,
) -> str:
    """Merge feature_b into feature_a. Returns the surviving feature ID."""
    a = features[feature_a_id]
    b = features[feature_b_id]

    # Combine tiles (deduplicate)
    combined_tiles = list(set(a["tiles"] + b["tiles"]))
    a["tiles"] = combined_tiles

    # Combine meeples
    a["meeples"] = a.get("meeples", []) + b.get("meeples", [])

    # Combine pennants
    a["pennants"] = a.get("pennants", 0) + b.get("pennants", 0)

    # Combine open edges
    a["open_edges"] = a.get("open_edges", []) + b.get("open_edges", [])

    # Track merged IDs for resolution
    merged_from = a.get("_merged_from", [])
    merged_from.append(feature_b_id)
    merged_from.extend(b.get("_merged_from", []))
    a["_merged_from"] = merged_from

    # Update tile_feature_map: all references to feature_b now point to feature_a
    for pos_key, spots in tile_feature_map.items():
        for spot, fid in spots.items():
            if fid == feature_b_id:
                spots[spot] = feature_a_id

    # Remove feature_b
    del features[feature_b_id]

    return feature_a_id


def _remove_open_edge(feature_dict: dict, position_key: str, direction: str) -> None:
    """Remove a specific open edge from a feature."""
    open_edges = feature_dict.get("open_edges", [])
    feature_dict["open_edges"] = [
        oe for oe in open_edges
        if not (oe[0] == position_key and oe[1] == direction)
    ]


def is_feature_complete(game_data: dict, feature: dict) -> bool:
    """Check if a feature is complete.

    - City/Road: complete when no open edges remain
    - Monastery: complete when all 8 surrounding tiles are placed
    - Field: never complete during the game
    """
    ft = feature["feature_type"]

    if ft == FeatureType.FIELD or ft == "field":
        return False

    if ft == FeatureType.MONASTERY or ft == "monastery":
        if not feature["tiles"]:
            return False
        pos = Position.from_key(feature["tiles"][0])
        board_tiles = game_data["board"]["tiles"]
        for surrounding in pos.all_surrounding():
            if surrounding.to_key() not in board_tiles:
                return False
        return True

    # City or Road: complete when no open edges
    return len(feature.get("open_edges", [])) == 0


def check_monastery_completion(
    game_data: dict, position_key: str
) -> tuple[list[Event], dict[str, int]]:
    """Check if any monasteries near the placed tile are now complete.

    When a tile is placed, it might complete monasteries on adjacent tiles
    (including diagonals) or on itself.

    Returns:
        events: scoring events
        scores: {player_id: points}
    """
    from src.games.carcassonne.scoring import score_completed_feature

    events: list[Event] = []
    scores: dict[str, int] = {}
    features = game_data["features"]
    board_tiles = game_data["board"]["tiles"]
    tile_feature_map = game_data["tile_feature_map"]

    pos = Position.from_key(position_key)

    # Check the placed tile and all 8 surrounding tiles for monasteries
    positions_to_check = [pos] + pos.all_surrounding()

    for check_pos in positions_to_check:
        check_key = check_pos.to_key()
        if check_key not in tile_feature_map:
            continue

        for spot, feature_id in tile_feature_map[check_key].items():
            if feature_id not in features:
                continue
            feature = features[feature_id]
            if feature.get("feature_type") not in (FeatureType.MONASTERY, "monastery"):
                continue
            if feature.get("is_complete"):
                continue

            if is_feature_complete(game_data, feature):
                feature["is_complete"] = True
                point_awards = score_completed_feature(feature)

                for pid, points in point_awards.items():
                    scores[pid] = scores.get(pid, 0) + points
                    events.append(Event(
                        event_type="feature_scored",
                        player_id=pid,
                        payload={
                            "feature_id": feature_id,
                            "feature_type": "monastery",
                            "points": points,
                            "tiles": feature["tiles"],
                        },
                    ))

                # Return meeples
                from src.games.carcassonne.meeples import return_meeples
                meeple_events = return_meeples(game_data, feature)
                events.extend(meeple_events)

    return events, scores
