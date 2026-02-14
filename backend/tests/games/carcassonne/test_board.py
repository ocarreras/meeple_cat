"""Unit tests for Carcassonne board placement validation."""

import pytest

from src.games.carcassonne.board import (
    can_place_tile,
    recalculate_open_positions,
    tile_has_valid_placement,
    get_rotated_edge,
)
from src.games.carcassonne.types import EdgeType, Position


class TestCanPlaceTile:
    """Tests for tile placement validation."""

    def test_can_place_tile_on_occupied_position_returns_false(self):
        """Verify cannot place tile on an already occupied position."""
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }
        assert can_place_tile(board_tiles, "E", "0,0", 0) is False

    def test_can_place_tile_with_no_neighbors_returns_false(self):
        """Verify cannot place tile with no adjacent tiles."""
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }
        # Position 5,5 is far from any placed tiles
        assert can_place_tile(board_tiles, "E", "5,5", 0) is False

    def test_can_place_tile_with_matching_edges_returns_true(self):
        """Verify can place tile when edges match adjacent tiles."""
        # Starting tile D: City N, Road E, Field S, Road W
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }

        # Tile E: City N, Field E/S/W
        # Place it at 0,1 (north of starting tile)
        # Starting tile has City on N, so at 0,1 we need City on S
        # Tile E rotated 180 has City on S
        assert can_place_tile(board_tiles, "E", "0,1", 180) is True

    def test_can_place_tile_with_mismatched_edges_returns_false(self):
        """Verify cannot place tile when edges don't match adjacent tiles."""
        # Starting tile D: City N, Road E, Field S, Road W
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }

        # Tile E: City N, Field E/S/W
        # Try to place at 0,1 (north of starting) with rotation 0
        # This would put City N (at 0,1) against City N (at 0,0) - wait, that should match
        # Let me recalculate: at 0,1, the S edge touches the N edge of 0,0
        # 0,0 has City on N, so 0,1 needs City on S
        # E with rotation 0 has City on N, Field on S - mismatch
        assert can_place_tile(board_tiles, "E", "0,1", 0) is False

    def test_can_place_tile_road_to_road_match(self):
        """Verify road edges can match."""
        # Starting tile D: Road on E and W
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }

        # Place a road tile to the east
        # Position 1,0 (east of 0,0)
        # Starting tile has Road on E, so 1,0 needs Road on W
        # Tile U (straight road N-S) rotated 90 has Road on E and W
        assert can_place_tile(board_tiles, "U", "1,0", 90) is True

    def test_can_place_tile_field_to_field_match(self):
        """Verify field edges can match."""
        # Starting tile D: Field on S
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }

        # Place a field tile to the south
        # Position 0,-1 (south of 0,0)
        # Starting tile has Field on S, so 0,-1 needs Field on N
        # Tile E (City N, Field E/S/W) has Field on S, so rotated 180 has Field on N
        assert can_place_tile(board_tiles, "E", "0,-1", 180) is True

    def test_can_place_tile_multiple_neighbors(self):
        """Verify placement checks all adjacent tiles."""
        # Create an L-shape
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0},  # City N, Road E/W, Field S
            "1,0": {"tile_type_id": "U", "rotation": 90},  # Road E/W
        }

        # Try to place at 1,1 (north of 1,0 and east of 0,0)
        # Must match: S edge to 1,0's N edge (Road), W edge to 0,0's E edge (Road)
        # Tile D rotated 90: City E, Road S/N, Field W
        # This would have Road on S (matches 1,0's Road on N via U rotated 90)
        # But Field on W doesn't match 0,0's Road on E
        assert can_place_tile(board_tiles, "D", "1,1", 90) is False


class TestRecalculateOpenPositions:
    """Tests for calculating open positions."""

    def test_single_tile_has_four_open_positions(self):
        """Verify a single tile creates 4 open positions."""
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }
        open_positions = recalculate_open_positions(board_tiles)

        assert len(open_positions) == 4
        expected = {"0,1", "1,0", "0,-1", "-1,0"}
        assert set(open_positions) == expected

    def test_two_adjacent_tiles_correct_open_positions(self):
        """Verify two adjacent tiles create correct open positions."""
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0},
            "1,0": {"tile_type_id": "E", "rotation": 0}
        }
        open_positions = recalculate_open_positions(board_tiles)

        # Should have positions around both tiles, excluding the shared edge
        # 0,0 contributes: 0,1 (N), 0,-1 (S), -1,0 (W)
        # 1,0 contributes: 1,1 (N), 2,0 (E), 1,-1 (S)
        # Total: 6 unique positions
        expected = {"0,1", "0,-1", "-1,0", "1,1", "2,0", "1,-1"}
        assert set(open_positions) == expected

    def test_no_tiles_returns_empty_list(self):
        """Verify empty board has no open positions."""
        board_tiles = {}
        open_positions = recalculate_open_positions(board_tiles)
        assert open_positions == []

    def test_open_positions_are_sorted(self):
        """Verify open positions are returned in sorted order."""
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }
        open_positions = recalculate_open_positions(board_tiles)
        assert open_positions == sorted(open_positions)


class TestTileHasValidPlacement:
    """Tests for checking if a tile can be placed anywhere."""

    def test_tile_with_valid_placement_returns_true(self):
        """Verify returns true when tile can be placed somewhere."""
        # Starting tile D: City N, Road E/W, Field S
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}
        }
        open_positions = recalculate_open_positions(board_tiles)

        # Tile E (City N, Field E/S/W) can be placed north with 180 rotation
        assert tile_has_valid_placement(board_tiles, open_positions, "E") is True

    def test_tile_with_no_valid_placement_returns_false(self):
        """Verify returns false when tile cannot be placed anywhere."""
        # Surround a single open position with field-only edges so that a tile
        # needing city edges (tile C = CCCC) cannot be placed.
        # Tile A (monastery) has all field edges: F F F F.
        # Place A tiles around a center so the only open spots expose field edges.
        board_tiles = {
            "0,0": {"tile_type_id": "A", "rotation": 0},   # FFFF
            "1,0": {"tile_type_id": "A", "rotation": 0},   # FFFF
            "-1,0": {"tile_type_id": "A", "rotation": 0},  # FFFF
            "0,1": {"tile_type_id": "A", "rotation": 0},   # FFFF
            "0,-1": {"tile_type_id": "A", "rotation": 0},  # FFFF
        }
        open_positions = recalculate_open_positions(board_tiles)

        # Every open position only borders field edges.
        # Tile C (CCCC) needs city on all sides — no rotation can match field.
        assert tile_has_valid_placement(board_tiles, open_positions, "C") is False

    def test_tile_requiring_rotation_found(self):
        """Verify function checks all rotations."""
        board_tiles = {
            "0,0": {"tile_type_id": "D", "rotation": 0}  # City N, Road E/W, Field S
        }
        open_positions = recalculate_open_positions(board_tiles)

        # Tile U (straight road N-S) won't work at rotation 0 for any position
        # but at rotation 90 (road E-W) it can connect to roads on E or W
        assert tile_has_valid_placement(board_tiles, open_positions, "U") is True


class TestGetRotatedEdge:
    """Tests for getting rotated edge types."""

    def test_get_rotated_edge_no_rotation(self):
        """Verify getting edge with no rotation returns original."""
        # Tile D: City N, Road E, Field S, Road W
        assert get_rotated_edge("D", 0, "N") == EdgeType.CITY
        assert get_rotated_edge("D", 0, "E") == EdgeType.ROAD
        assert get_rotated_edge("D", 0, "S") == EdgeType.FIELD
        assert get_rotated_edge("D", 0, "W") == EdgeType.ROAD

    def test_get_rotated_edge_90_degrees(self):
        """Verify getting edge with 90-degree rotation."""
        # Tile D rotated 90: what was N is now E, E->S, S->W, W->N
        assert get_rotated_edge("D", 90, "N") == EdgeType.ROAD  # Was W
        assert get_rotated_edge("D", 90, "E") == EdgeType.CITY  # Was N
        assert get_rotated_edge("D", 90, "S") == EdgeType.ROAD  # Was E
        assert get_rotated_edge("D", 90, "W") == EdgeType.FIELD  # Was S

    def test_get_rotated_edge_180_degrees(self):
        """Verify getting edge with 180-degree rotation."""
        # Tile D rotated 180: N<->S, E<->W
        assert get_rotated_edge("D", 180, "N") == EdgeType.FIELD  # Was S
        assert get_rotated_edge("D", 180, "E") == EdgeType.ROAD   # Was W
        assert get_rotated_edge("D", 180, "S") == EdgeType.CITY   # Was N
        assert get_rotated_edge("D", 180, "W") == EdgeType.ROAD   # Was E

    def test_get_rotated_edge_270_degrees(self):
        """Verify getting edge with 270-degree rotation."""
        # Tile D rotated 270: N->W, W->S, S->E, E->N
        assert get_rotated_edge("D", 270, "N") == EdgeType.ROAD  # Was E
        assert get_rotated_edge("D", 270, "E") == EdgeType.FIELD  # Was S
        assert get_rotated_edge("D", 270, "S") == EdgeType.ROAD  # Was W
        assert get_rotated_edge("D", 270, "W") == EdgeType.CITY  # Was N


class TestPosition:
    """Tests for Position helper class methods."""

    def test_position_neighbor_north(self):
        """Verify neighbor calculation for north direction."""
        pos = Position(x=0, y=0)
        north = pos.neighbor("N")
        assert north == Position(x=0, y=1)

    def test_position_neighbor_east(self):
        """Verify neighbor calculation for east direction."""
        pos = Position(x=0, y=0)
        east = pos.neighbor("E")
        assert east == Position(x=1, y=0)

    def test_position_neighbor_south(self):
        """Verify neighbor calculation for south direction."""
        pos = Position(x=0, y=0)
        south = pos.neighbor("S")
        assert south == Position(x=0, y=-1)

    def test_position_neighbor_west(self):
        """Verify neighbor calculation for west direction."""
        pos = Position(x=0, y=0)
        west = pos.neighbor("W")
        assert west == Position(x=-1, y=0)

    def test_position_neighbors_returns_all_four(self):
        """Verify neighbors() returns all 4 adjacent positions."""
        pos = Position(x=0, y=0)
        neighbors = pos.neighbors()

        assert len(neighbors) == 4
        assert neighbors["N"] == Position(x=0, y=1)
        assert neighbors["E"] == Position(x=1, y=0)
        assert neighbors["S"] == Position(x=0, y=-1)
        assert neighbors["W"] == Position(x=-1, y=0)
