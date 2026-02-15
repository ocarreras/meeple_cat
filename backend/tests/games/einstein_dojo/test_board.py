"""Tests for Ein Stein Dojo board logic."""

from __future__ import annotations

from src.games.einstein_dojo.board import (
    apply_placement,
    create_empty_board,
    derive_hex_state,
    get_all_valid_placements,
    get_candidate_anchors,
    validate_placement,
)
from src.games.einstein_dojo.pieces import (
    PIECE_A_BASE,
    get_placed_kites,
    orientation_index,
)
from src.games.einstein_dojo.types import HexState, kite_to_key


class TestEmptyBoard:
    def test_create_empty_board(self) -> None:
        board = create_empty_board()
        assert board["kite_owners"] == {}
        assert board["hex_states"] == {}
        assert board["placed_pieces"] == []

    def test_first_placement_always_valid(self) -> None:
        board = create_empty_board()
        err = validate_placement(board, "p1", 0, 0, 0)
        assert err is None

    def test_first_placement_any_orientation(self) -> None:
        for orient in range(12):
            board = create_empty_board()
            err = validate_placement(board, "p1", orient, 0, 0)
            assert err is None, f"Orientation {orient} should be valid"

    def test_first_placement_any_position(self) -> None:
        board = create_empty_board()
        err = validate_placement(board, "p1", 0, 5, -3)
        assert err is None


class TestOverlapDetection:
    def test_exact_overlap_rejected(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        err = validate_placement(board, "p2", 0, 0, 0)
        assert err is not None
        assert "already occupied" in err

    def test_partial_overlap_rejected(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        # Try a different orientation at same anchor — likely overlaps
        err = validate_placement(board, "p2", 1, 0, 0)
        # Should fail since some kites at (0,0) are shared
        assert err is not None


class TestAdjacency:
    def test_non_adjacent_rejected(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        # Place far away — should fail adjacency
        err = validate_placement(board, "p2", 0, 10, 10)
        assert err is not None
        assert "adjacent" in err

    def test_adjacent_accepted(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        # Find a valid adjacent placement
        placements = get_all_valid_placements(board, "p2")
        assert len(placements) > 0, "Should have at least one valid adjacent placement"


class TestHexState:
    def test_empty_hex(self) -> None:
        state = derive_hex_state({}, 0, 0)
        assert state == HexState.EMPTY

    def test_open_hex_single_kite(self) -> None:
        owners = {kite_to_key(0, 0, 0): "p1"}
        state = derive_hex_state(owners, 0, 0)
        assert state == HexState.OPEN

    def test_open_hex_multiple_kites_same_player(self) -> None:
        owners = {
            kite_to_key(0, 0, 0): "p1",
            kite_to_key(0, 0, 1): "p1",
            kite_to_key(0, 0, 2): "p1",
        }
        state = derive_hex_state(owners, 0, 0)
        assert state == HexState.OPEN

    def test_complete_hex(self) -> None:
        owners = {kite_to_key(0, 0, k): "p1" for k in range(6)}
        state = derive_hex_state(owners, 0, 0)
        assert state == HexState.COMPLETE

    def test_conflict_hex(self) -> None:
        owners = {
            kite_to_key(0, 0, 0): "p1",
            kite_to_key(0, 0, 3): "p2",
        }
        state = derive_hex_state(owners, 0, 0)
        assert state == HexState.CONFLICT


class TestApplyPlacement:
    def test_sets_kite_owners(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        assert len(board["kite_owners"]) == 8

    def test_all_kites_owned_by_player(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        for owner in board["kite_owners"].values():
            assert owner == "p1"

    def test_records_placed_piece(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        assert len(board["placed_pieces"]) == 1
        piece = board["placed_pieces"][0]
        assert piece["player_id"] == "p1"
        assert piece["orientation"] == 0
        assert piece["anchor_q"] == 0
        assert piece["anchor_r"] == 0

    def test_updates_hex_states(self) -> None:
        board = create_empty_board()
        changed = apply_placement(board, "p1", 0, 0, 0)
        assert len(changed) > 0
        # All affected hexes should be OPEN (4 kites in one, 2 in each of the others)
        for key in changed:
            assert board["hex_states"][key] in (HexState.OPEN, HexState.COMPLETE)

    def test_multiple_placements(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        placements = get_all_valid_placements(board, "p2")
        assert len(placements) > 0
        p = placements[0]
        apply_placement(board, "p2", p["orientation"], p["anchor_q"], p["anchor_r"])
        assert len(board["placed_pieces"]) == 2
        assert len(board["kite_owners"]) == 16


class TestCandidateAnchors:
    def test_empty_board_has_origin(self) -> None:
        board = create_empty_board()
        anchors = get_candidate_anchors(board)
        assert (0, 0) in anchors

    def test_after_placement_has_neighbors(self) -> None:
        board = create_empty_board()
        apply_placement(board, "p1", 0, 0, 0)
        anchors = get_candidate_anchors(board)
        # Should include occupied hexes and their 2-step neighborhood
        assert len(anchors) > 10


class TestValidPlacements:
    def test_empty_board_has_many_placements(self) -> None:
        board = create_empty_board()
        placements = get_all_valid_placements(board, "p1")
        # On empty board, at least 12 orientations at origin
        assert len(placements) >= 12

    def test_orientation_validation(self) -> None:
        board = create_empty_board()
        err = validate_placement(board, "p1", -1, 0, 0)
        assert err is not None
        err = validate_placement(board, "p1", 12, 0, 0)
        assert err is not None
