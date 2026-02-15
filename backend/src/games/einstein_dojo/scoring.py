"""Scoring for Ein Stein Dojo (first iteration — count complete hexes)."""

from __future__ import annotations

from src.games.einstein_dojo.types import HexState


def count_complete_hexes(board: dict) -> dict[str, int]:
    """Count hexes in COMPLETE state per player.

    Returns {player_id: count_of_complete_hexes}.
    """
    counts: dict[str, int] = {}
    kite_owners = board["kite_owners"]
    hex_states = board["hex_states"]

    for hex_key, state in hex_states.items():
        if state == HexState.COMPLETE:
            # Find which player owns this hex (check any kite — all are same player)
            q_str, r_str = hex_key.split(",")
            sample_kite_key = f"{hex_key}:0"
            owner = kite_owners.get(sample_kite_key)
            if owner is not None:
                counts[owner] = counts.get(owner, 0) + 1

    return counts
