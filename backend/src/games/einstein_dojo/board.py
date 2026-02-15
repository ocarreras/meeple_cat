"""Board state management for Ein Stein Dojo.

The board tracks which kites are occupied and by whom, derives hex cell
states, and validates tile placements.
"""

from __future__ import annotations

from src.games.einstein_dojo.pieces import (
    NUM_ORIENTATIONS,
    get_occupied_hexes,
    get_placed_kites,
)
from src.games.einstein_dojo.types import (
    HexState,
    hex_neighbors,
    hex_to_key,
    kite_to_key,
)


def create_empty_board() -> dict:
    """Create an empty board data structure."""
    return {
        "kite_owners": {},
        "hex_states": {},
        "placed_pieces": [],
    }


def derive_hex_state(kite_owners: dict[str, str], q: int, r: int) -> HexState:
    """Examine the 6 kites of hex (q, r) and derive its state."""
    players_present: set[str] = set()
    kites_filled = 0

    for k in range(6):
        key = kite_to_key(q, r, k)
        owner = kite_owners.get(key)
        if owner is not None:
            players_present.add(owner)
            kites_filled += 1

    if kites_filled == 0:
        return HexState.EMPTY
    if len(players_present) > 1:
        return HexState.CONFLICT
    if kites_filled == 6:
        return HexState.COMPLETE
    return HexState.OPEN


def validate_placement(
    board: dict,
    player_id: str,
    orientation: int,
    anchor_q: int,
    anchor_r: int,
) -> str | None:
    """Validate a tile placement. Return error message or None if valid."""
    if orientation < 0 or orientation >= NUM_ORIENTATIONS:
        return f"Invalid orientation: {orientation}"

    kites = get_placed_kites(orientation, anchor_q, anchor_r)
    kite_owners = board["kite_owners"]

    # Check no overlap
    for q, r, k in kites:
        key = kite_to_key(q, r, k)
        if key in kite_owners:
            return f"Kite {key} is already occupied"

    # Check adjacency (first placement is exempt)
    if board["placed_pieces"]:
        piece_hexes = {(q, r) for q, r, _k in kites}
        occupied_hexes = _get_occupied_hexes(kite_owners)
        if not piece_hexes & occupied_hexes:
            return "Piece must be adjacent to an existing tile"

    return None


def apply_placement(
    board: dict,
    player_id: str,
    orientation: int,
    anchor_q: int,
    anchor_r: int,
) -> list[str]:
    """Place a tile on the board. Returns list of hex keys whose state changed.

    Assumes validate_placement() has already returned None.
    """
    kites = get_placed_kites(orientation, anchor_q, anchor_r)
    kite_owners = board["kite_owners"]
    hex_states = board["hex_states"]

    # Set kite ownership
    for q, r, k in kites:
        kite_owners[kite_to_key(q, r, k)] = player_id

    # Record placement for rendering
    board["placed_pieces"].append({
        "player_id": player_id,
        "orientation": orientation,
        "anchor_q": anchor_q,
        "anchor_r": anchor_r,
    })

    # Recalculate hex states for affected hexes
    affected_hexes = {(q, r) for q, r, _k in kites}
    changed: list[str] = []
    for q, r in affected_hexes:
        key = hex_to_key(q, r)
        old_state = hex_states.get(key, HexState.EMPTY)
        new_state = derive_hex_state(kite_owners, q, r)
        hex_states[key] = new_state
        if new_state != old_state:
            changed.append(key)

    return changed


def get_candidate_anchors(board: dict) -> set[tuple[int, int]]:
    """Return hex positions that could serve as anchor points for new placements.

    Returns all hexes within 2 steps of any occupied hex. This bounds the
    search space for get_valid_actions.
    """
    kite_owners = board["kite_owners"]
    if not kite_owners:
        # Empty board — only (0, 0) is a candidate
        return {(0, 0)}

    occupied = _get_occupied_hexes(kite_owners)
    candidates: set[tuple[int, int]] = set()

    for q, r in occupied:
        candidates.add((q, r))
        for nq, nr in hex_neighbors(q, r):
            candidates.add((nq, nr))
            for nnq, nnr in hex_neighbors(nq, nr):
                candidates.add((nnq, nnr))

    return candidates


def get_all_valid_placements(
    board: dict,
    player_id: str,
) -> list[dict]:
    """Return all valid placements for a player.

    Each item is {"anchor_q": int, "anchor_r": int, "orientation": int}.
    """
    candidates = get_candidate_anchors(board)
    valid: list[dict] = []

    for anchor_q, anchor_r in candidates:
        for orient in range(NUM_ORIENTATIONS):
            if validate_placement(board, player_id, orient, anchor_q, anchor_r) is None:
                valid.append({
                    "anchor_q": anchor_q,
                    "anchor_r": anchor_r,
                    "orientation": orient,
                })

    return valid


def _get_occupied_hexes(kite_owners: dict[str, str]) -> set[tuple[int, int]]:
    """Extract the set of hex cells that have at least one occupied kite."""
    hexes: set[tuple[int, int]] = set()
    for key in kite_owners:
        hex_part = key.split(":")[0]
        q, r = hex_part.split(",")
        hexes.add((int(q), int(r)))
    return hexes
