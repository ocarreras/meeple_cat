"""Tests for Einstein hat tile geometry."""

from __future__ import annotations

from src.games.einstein_dojo.pieces import (
    ALL_ORIENTATIONS,
    NUM_ORIENTATIONS,
    PIECE_A_BASE,
    PIECE_B_BASE,
    Footprint,
    get_occupied_hexes,
    get_placed_kites,
    mirror_footprint,
    orientation_index,
    orientation_info,
    rotate_footprint,
)


def _normalize(fp: Footprint) -> frozenset[tuple[int, int, int]]:
    return frozenset(fp)


class TestBasePieces:
    def test_piece_a_has_8_kites(self) -> None:
        assert len(PIECE_A_BASE) == 8

    def test_piece_b_has_8_kites(self) -> None:
        assert len(PIECE_B_BASE) == 8

    def test_piece_a_covers_3_hexes(self) -> None:
        hexes = {(q, r) for q, r, _k in PIECE_A_BASE}
        assert len(hexes) == 3

    def test_piece_b_covers_3_hexes(self) -> None:
        hexes = {(q, r) for q, r, _k in PIECE_B_BASE}
        assert len(hexes) == 3

    def test_piece_a_has_4_2_2_distribution(self) -> None:
        from collections import Counter
        counts = Counter((q, r) for q, r, _k in PIECE_A_BASE)
        assert sorted(counts.values()) == [2, 2, 4]

    def test_piece_b_has_4_2_2_distribution(self) -> None:
        from collections import Counter
        counts = Counter((q, r) for q, r, _k in PIECE_B_BASE)
        assert sorted(counts.values()) == [2, 2, 4]

    def test_all_kite_indices_valid(self) -> None:
        for q, r, k in PIECE_A_BASE + PIECE_B_BASE:
            assert 0 <= k <= 5, f"Invalid kite index {k} at ({q},{r})"

    def test_no_duplicate_kites_in_piece_a(self) -> None:
        assert len(set(PIECE_A_BASE)) == 8

    def test_no_duplicate_kites_in_piece_b(self) -> None:
        assert len(set(PIECE_B_BASE)) == 8


class TestRotation:
    def test_rotation_preserves_8_kites(self) -> None:
        fp = rotate_footprint(PIECE_A_BASE)
        assert len(fp) == 8

    def test_rotation_preserves_3_hexes(self) -> None:
        fp = rotate_footprint(PIECE_A_BASE)
        hexes = {(q, r) for q, r, _k in fp}
        assert len(hexes) == 3

    def test_rotation_preserves_4_2_2(self) -> None:
        from collections import Counter
        fp = rotate_footprint(PIECE_A_BASE)
        counts = Counter((q, r) for q, r, _k in fp)
        assert sorted(counts.values()) == [2, 2, 4]

    def test_six_rotations_return_to_original(self) -> None:
        fp = list(PIECE_A_BASE)
        for _ in range(6):
            fp = rotate_footprint(fp)
        assert _normalize(fp) == _normalize(PIECE_A_BASE)

    def test_six_rotations_return_to_original_b(self) -> None:
        fp = list(PIECE_B_BASE)
        for _ in range(6):
            fp = rotate_footprint(fp)
        assert _normalize(fp) == _normalize(PIECE_B_BASE)


class TestMirror:
    def test_mirror_of_a_equals_b(self) -> None:
        mirrored = mirror_footprint(PIECE_A_BASE)
        assert _normalize(mirrored) == _normalize(PIECE_B_BASE)

    def test_mirror_of_b_equals_a(self) -> None:
        mirrored = mirror_footprint(PIECE_B_BASE)
        assert _normalize(mirrored) == _normalize(PIECE_A_BASE)

    def test_double_mirror_returns_to_original(self) -> None:
        double = mirror_footprint(mirror_footprint(PIECE_A_BASE))
        assert _normalize(double) == _normalize(PIECE_A_BASE)


class TestAllOrientations:
    def test_total_count(self) -> None:
        assert NUM_ORIENTATIONS == 12

    def test_all_unique(self) -> None:
        normalized = [_normalize(fp) for fp in ALL_ORIENTATIONS]
        assert len(set(normalized)) == 12, "Some orientations are duplicates"

    def test_each_has_8_kites(self) -> None:
        for i, fp in enumerate(ALL_ORIENTATIONS):
            assert len(fp) == 8, f"Orientation {i} has {len(fp)} kites"

    def test_each_covers_3_hexes(self) -> None:
        for i, fp in enumerate(ALL_ORIENTATIONS):
            hexes = {(q, r) for q, r, _k in fp}
            assert len(hexes) == 3, f"Orientation {i} covers {len(hexes)} hexes"

    def test_each_has_4_2_2_distribution(self) -> None:
        from collections import Counter
        for i, fp in enumerate(ALL_ORIENTATIONS):
            counts = Counter((q, r) for q, r, _k in fp)
            assert sorted(counts.values()) == [2, 2, 4], (
                f"Orientation {i}: {sorted(counts.values())}"
            )

    def test_a_orientations_are_first_six(self) -> None:
        """Orientations 0-5 are chirality A."""
        for i in range(6):
            chirality, rotation = orientation_info(i)
            assert chirality == "A"
            assert rotation == i

    def test_b_orientations_are_last_six(self) -> None:
        """Orientations 6-11 are chirality B."""
        for i in range(6, 12):
            chirality, rotation = orientation_info(i)
            assert chirality == "B"
            assert rotation == i - 6


class TestOrientationIndex:
    def test_roundtrip(self) -> None:
        for chirality in ("A", "B"):
            for rotation in range(6):
                idx = orientation_index(chirality, rotation)
                c, r = orientation_info(idx)
                assert c == chirality
                assert r == rotation


class TestGetPlacedKites:
    def test_at_origin(self) -> None:
        kites = get_placed_kites(0, 0, 0)
        assert len(kites) == 8
        # At origin, should match PIECE_A_BASE
        assert set(kites) == set(PIECE_A_BASE)

    def test_with_offset(self) -> None:
        kites = get_placed_kites(0, 3, -2)
        for q, r, k in kites:
            # All should be offset by (3, -2)
            assert (q - 3, r + 2, k) in PIECE_A_BASE

    def test_get_occupied_hexes(self) -> None:
        hexes = get_occupied_hexes(0, 0, 0)
        assert len(hexes) == 3
        expected = {(q, r) for q, r, _k in PIECE_A_BASE}
        assert hexes == expected
