"""Domain models for Ein Stein Dojo."""

from __future__ import annotations

from enum import Enum


class Chirality(str, Enum):
    A = "A"  # hat
    B = "B"  # shirt (mirror of A)


class HexState(str, Enum):
    EMPTY = "empty"
    OPEN = "open"          # some kites filled, all same player
    COMPLETE = "complete"  # all 6 kites filled by one player
    CONFLICT = "conflict"  # kites filled by different players


# Axial hex directions (flat-top): the 6 neighbors of (q, r)
HEX_DIRECTIONS: list[tuple[int, int]] = [
    (1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1),
]


def hex_neighbors(q: int, r: int) -> list[tuple[int, int]]:
    """Return the 6 axial-coordinate neighbors of hex (q, r)."""
    return [(q + dq, r + dr) for dq, dr in HEX_DIRECTIONS]


def hex_to_key(q: int, r: int) -> str:
    return f"{q},{r}"


def key_to_hex(key: str) -> tuple[int, int]:
    q, r = key.split(",")
    return int(q), int(r)


def kite_to_key(q: int, r: int, k: int) -> str:
    return f"{q},{r}:{k}"


def key_to_kite(key: str) -> tuple[int, int, int]:
    hex_part, k_str = key.split(":")
    q, r = hex_part.split(",")
    return int(q), int(r), int(k_str)
