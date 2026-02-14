"""Board logic: tile placement validation, open position calculation."""

from __future__ import annotations

from src.games.carcassonne.tiles import TILE_LOOKUP, get_rotated_features
from src.games.carcassonne.types import (
    DIRECTIONS,
    OPPOSITE_DIRECTION,
    EdgeType,
    Position,
    rotate_edges,
)


def get_rotated_edge(tile_type_id: str, rotation: int, direction: str) -> EdgeType:
    """Get the edge type at a given direction for a tile with rotation applied."""
    tile_def = TILE_LOOKUP[tile_type_id]
    rotated = rotate_edges(tile_def.edges, rotation)
    return rotated[direction]


def can_place_tile(
    board_tiles: dict[str, dict],
    tile_type_id: str,
    position_key: str,
    rotation: int,
) -> bool:
    """Check if a tile can be placed at the given position with the given rotation.

    Rules:
    1. Position must be empty
    2. Position must be adjacent to at least one placed tile
    3. All edges touching adjacent tiles must match (city-city, road-road, field-field)
    """
    if position_key in board_tiles:
        return False

    pos = Position.from_key(position_key)
    has_neighbor = False

    for direction in DIRECTIONS:
        neighbor_pos = pos.neighbor(direction)
        neighbor_key = neighbor_pos.to_key()

        if neighbor_key not in board_tiles:
            continue

        has_neighbor = True
        neighbor_tile = board_tiles[neighbor_key]
        neighbor_edge = get_rotated_edge(
            neighbor_tile["tile_type_id"],
            neighbor_tile["rotation"],
            OPPOSITE_DIRECTION[direction],
        )
        our_edge = get_rotated_edge(tile_type_id, rotation, direction)

        if our_edge != neighbor_edge:
            return False

    return has_neighbor


def recalculate_open_positions(board_tiles: dict[str, dict]) -> list[str]:
    """Recalculate all open positions (empty positions adjacent to placed tiles)."""
    open_set: set[str] = set()

    for pos_key in board_tiles:
        pos = Position.from_key(pos_key)
        for direction in DIRECTIONS:
            neighbor = pos.neighbor(direction)
            neighbor_key = neighbor.to_key()
            if neighbor_key not in board_tiles:
                open_set.add(neighbor_key)

    return sorted(open_set)


def tile_has_valid_placement(
    board_tiles: dict[str, dict],
    open_positions: list[str],
    tile_type_id: str,
) -> bool:
    """Check if a tile type can be placed anywhere on the board."""
    for pos_key in open_positions:
        for rotation in (0, 90, 180, 270):
            if can_place_tile(board_tiles, tile_type_id, pos_key, rotation):
                return True
    return False
