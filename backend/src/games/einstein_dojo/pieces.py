"""Einstein hat tile geometry — all 12 orientations.

Each piece covers 8 kites across 3 hex cells (4+2+2 distribution).
A hex cell has 6 kites indexed 0-5, one per vertex (flat-top orientation).

Piece A (hat chirality) and Piece B (shirt chirality) are mirror images.
Each can be rotated in 60-degree increments giving 6 rotations per chirality.
Total: 12 unique orientations.
"""

from __future__ import annotations

# A footprint is a list of (dq, dr, kite_index) tuples relative to an anchor.
Footprint = list[tuple[int, int, int]]

# ── Base piece definitions (confirmed via kite-explorer tool) ──

PIECE_A_BASE: Footprint = [
    (0, 0, 1), (0, 0, 2), (0, 0, 3), (0, 0, 4),   # 4 kites in major hex
    (-1, 1, 4), (-1, 1, 5),                          # 2 kites
    (-1, 0, 0), (-1, 0, 1),                          # 2 kites
]

PIECE_B_BASE: Footprint = [
    (0, 0, 0), (0, 0, 1), (0, 0, 2), (0, 0, 5),    # 4 kites in major hex
    (1, -1, 2), (1, -1, 3),                          # 2 kites
    (1, 0, 4), (1, 0, 5),                            # 2 kites
]


def rotate_footprint(footprint: Footprint) -> Footprint:
    """Rotate a footprint 60 degrees clockwise.

    Hex transform:  (q, r) -> (-r, q + r)
    Kite transform: k -> (k + 1) % 6
    """
    return [(-r, q + r, (k + 1) % 6) for q, r, k in footprint]


def mirror_footprint(footprint: Footprint) -> Footprint:
    """Mirror a footprint (vertical axis) to convert A <-> B chirality.

    Hex transform:  (q, r) -> (-q, q + r)
    Kite transform: k -> (3 - k) % 6
    """
    return [(-q, q + r, (3 - k) % 6) for q, r, k in footprint]


def _normalize(footprint: Footprint) -> tuple[tuple[int, int, int], ...]:
    """Return a canonical sorted tuple for comparison."""
    return tuple(sorted(footprint))


def _build_all_orientations() -> list[Footprint]:
    """Pre-compute all 12 orientations: A rotations 0-5, then B rotations 0-5."""
    orientations: list[Footprint] = []

    # 6 rotations of chirality A
    fp = list(PIECE_A_BASE)
    for _ in range(6):
        orientations.append(list(fp))
        fp = rotate_footprint(fp)

    # 6 rotations of chirality B
    fp = list(PIECE_B_BASE)
    for _ in range(6):
        orientations.append(list(fp))
        fp = rotate_footprint(fp)

    return orientations


ALL_ORIENTATIONS: list[Footprint] = _build_all_orientations()
"""Index 0-5: chirality A, rotations 0-5. Index 6-11: chirality B, rotations 0-5."""

NUM_ORIENTATIONS = len(ALL_ORIENTATIONS)  # 12


def orientation_index(chirality: str, rotation: int) -> int:
    """Convert (chirality, rotation) to an index into ALL_ORIENTATIONS."""
    base = 0 if chirality == "A" else 6
    return base + (rotation % 6)


def orientation_info(index: int) -> tuple[str, int]:
    """Convert an orientation index back to (chirality, rotation)."""
    if index < 6:
        return "A", index
    return "B", index - 6


def get_placed_kites(
    orient: int, anchor_q: int, anchor_r: int,
) -> list[tuple[int, int, int]]:
    """Return the 8 absolute (q, r, kite_index) tuples for a placement.

    Args:
        orient: orientation index 0..11
        anchor_q, anchor_r: translation offset on the hex grid
    """
    footprint = ALL_ORIENTATIONS[orient]
    return [(dq + anchor_q, dr + anchor_r, k) for dq, dr, k in footprint]


def get_occupied_hexes(
    orient: int, anchor_q: int, anchor_r: int,
) -> set[tuple[int, int]]:
    """Return the set of hex cells (q, r) that a placement touches."""
    return {(dq + anchor_q, dr + anchor_r) for dq, dr, _k in ALL_ORIENTATIONS[orient]}
