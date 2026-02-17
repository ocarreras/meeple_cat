//! Board state management for Ein Stein Dojo.
//!
//! Tracks kite ownership, derives hex cell states, and validates tile placements.

use std::collections::HashSet;

use super::pieces::{get_placed_kites, hex_to_key, kite_to_key, NUM_ORIENTATIONS};
use super::types::{Board, HexState, PlacedPiece};

/// Axial hex directions (flat-top): the 6 neighbors of (q, r).
const HEX_DIRECTIONS: [(i32, i32); 6] = [
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, -1),
    (-1, 1),
];

/// Return the 6 axial-coordinate neighbors of hex (q, r).
pub fn hex_neighbors(q: i32, r: i32) -> [(i32, i32); 6] {
    HEX_DIRECTIONS.map(|(dq, dr)| (q + dq, r + dr))
}

/// Examine the 6 kites of hex (q, r) and derive its state.
pub fn derive_hex_state(board: &Board, q: i32, r: i32) -> HexState {
    let mut players_present: HashSet<&str> = HashSet::new();
    let mut kites_filled = 0u8;

    for k in 0..6u8 {
        let key = kite_to_key(q, r, k);
        if let Some(owner) = board.kite_owners.get(&key) {
            players_present.insert(owner.as_str());
            kites_filled += 1;
        }
    }

    if kites_filled == 0 {
        HexState::Empty
    } else if players_present.len() > 1 {
        HexState::Conflict
    } else if kites_filled == 6 {
        HexState::Complete
    } else {
        HexState::Open
    }
}

/// Validate a tile placement. Return error message or None if valid.
pub fn validate_placement(
    board: &Board,
    orientation: u8,
    anchor_q: i32,
    anchor_r: i32,
) -> Option<String> {
    if orientation >= NUM_ORIENTATIONS {
        return Some(format!("Invalid orientation: {orientation}"));
    }

    let kites = get_placed_kites(orientation, anchor_q, anchor_r);

    // Check no overlap
    for &(q, r, k) in &kites {
        let key = kite_to_key(q, r, k);
        if board.kite_owners.contains_key(&key) {
            return Some(format!("Kite {key} is already occupied"));
        }
    }

    // Check adjacency (first placement is exempt)
    if !board.placed_pieces.is_empty() {
        let piece_hexes: HashSet<(i32, i32)> = kites.iter().map(|&(q, r, _)| (q, r)).collect();
        let occupied_hexes = get_occupied_hex_coords(board);
        if piece_hexes.is_disjoint(&occupied_hexes) {
            return Some("Piece must be adjacent to an existing tile".into());
        }
    }

    None
}

/// Place a tile on the board. Returns list of hex keys whose state changed.
///
/// Assumes validate_placement() has already returned None.
pub fn apply_placement(
    board: &mut Board,
    player_id: &str,
    orientation: u8,
    anchor_q: i32,
    anchor_r: i32,
) -> Vec<String> {
    let kites = get_placed_kites(orientation, anchor_q, anchor_r);

    // Set kite ownership
    for &(q, r, k) in &kites {
        board
            .kite_owners
            .insert(kite_to_key(q, r, k), player_id.to_string());
    }

    // Record placement for rendering
    board.placed_pieces.push(PlacedPiece {
        player_id: player_id.to_string(),
        orientation,
        anchor_q,
        anchor_r,
    });

    // Recalculate hex states for affected hexes
    let affected_hexes: HashSet<(i32, i32)> = kites.iter().map(|&(q, r, _)| (q, r)).collect();
    let mut changed = Vec::new();
    for (q, r) in affected_hexes {
        let key = hex_to_key(q, r);
        let old_state = board.hex_states.get(&key).copied().unwrap_or(HexState::Empty);
        let new_state = derive_hex_state(board, q, r);
        board.hex_states.insert(key.clone(), new_state);
        if new_state != old_state {
            changed.push(key);
        }
    }

    changed
}

/// Return hex positions that could serve as anchor points for new placements.
///
/// Returns all hexes within 2 steps of any occupied hex to bound the search space.
pub fn get_candidate_anchors(board: &Board) -> HashSet<(i32, i32)> {
    if board.kite_owners.is_empty() {
        let mut s = HashSet::new();
        s.insert((0, 0));
        return s;
    }

    let occupied = get_occupied_hex_coords(board);
    let mut candidates = HashSet::new();

    for &(q, r) in &occupied {
        candidates.insert((q, r));
        for (nq, nr) in hex_neighbors(q, r) {
            candidates.insert((nq, nr));
            for (nnq, nnr) in hex_neighbors(nq, nr) {
                candidates.insert((nnq, nnr));
            }
        }
    }

    candidates
}

/// Return all valid placements as (orientation, anchor_q, anchor_r).
pub fn get_all_valid_placements(board: &Board) -> Vec<(u8, i32, i32)> {
    let candidates = get_candidate_anchors(board);
    let mut valid = Vec::new();

    for (aq, ar) in candidates {
        for orient in 0..NUM_ORIENTATIONS {
            if validate_placement(board, orient, aq, ar).is_none() {
                valid.push((orient, aq, ar));
            }
        }
    }

    valid
}

/// Extract the set of hex cells that have at least one occupied kite.
fn get_occupied_hex_coords(board: &Board) -> HashSet<(i32, i32)> {
    let mut hexes = HashSet::new();
    for key in board.kite_owners.keys() {
        if let Some(hex_part) = key.split(':').next() {
            let mut parts = hex_part.split(',');
            if let (Some(q), Some(r)) = (parts.next(), parts.next()) {
                if let (Ok(q), Ok(r)) = (q.parse::<i32>(), r.parse::<i32>()) {
                    hexes.insert((q, r));
                }
            }
        }
    }
    hexes
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hex_neighbors_count() {
        let n = hex_neighbors(0, 0);
        assert_eq!(n.len(), 6);
    }

    #[test]
    fn test_derive_hex_state_empty() {
        let board = Board::new();
        assert_eq!(derive_hex_state(&board, 0, 0), HexState::Empty);
    }

    #[test]
    fn test_derive_hex_state_open() {
        let mut board = Board::new();
        board.kite_owners.insert("0,0:0".into(), "p1".into());
        board.kite_owners.insert("0,0:1".into(), "p1".into());
        assert_eq!(derive_hex_state(&board, 0, 0), HexState::Open);
    }

    #[test]
    fn test_derive_hex_state_complete() {
        let mut board = Board::new();
        for k in 0..6 {
            board
                .kite_owners
                .insert(format!("0,0:{k}"), "p1".into());
        }
        assert_eq!(derive_hex_state(&board, 0, 0), HexState::Complete);
    }

    #[test]
    fn test_derive_hex_state_conflict() {
        let mut board = Board::new();
        for k in 0..3 {
            board
                .kite_owners
                .insert(format!("0,0:{k}"), "p1".into());
        }
        for k in 3..6 {
            board
                .kite_owners
                .insert(format!("0,0:{k}"), "p2".into());
        }
        assert_eq!(derive_hex_state(&board, 0, 0), HexState::Conflict);
    }

    #[test]
    fn test_validate_first_placement_always_valid() {
        let board = Board::new();
        // Any valid orientation at any anchor should work for first placement
        assert!(validate_placement(&board, 0, 0, 0).is_none());
        assert!(validate_placement(&board, 6, 3, -2).is_none());
    }

    #[test]
    fn test_validate_placement_overlap_rejected() {
        let mut board = Board::new();
        apply_placement(&mut board, "p1", 0, 0, 0);
        // Same position same orientation = overlap
        assert!(validate_placement(&board, 0, 0, 0).is_some());
    }

    #[test]
    fn test_validate_placement_adjacent_ok() {
        let mut board = Board::new();
        apply_placement(&mut board, "p1", 0, 0, 0);
        // Find a valid adjacent placement
        let valid = get_all_valid_placements(&board);
        assert!(!valid.is_empty(), "should have valid adjacent placements");
    }

    #[test]
    fn test_validate_placement_isolated_rejected() {
        let mut board = Board::new();
        apply_placement(&mut board, "p1", 0, 0, 0);
        // Far away placement should fail adjacency check
        assert!(validate_placement(&board, 0, 100, 100).is_some());
    }

    #[test]
    fn test_apply_placement_updates_kite_owners() {
        let mut board = Board::new();
        apply_placement(&mut board, "p1", 0, 0, 0);
        assert_eq!(board.kite_owners.len(), 8);
        assert_eq!(board.placed_pieces.len(), 1);
    }

    #[test]
    fn test_candidate_anchors_empty_board() {
        let board = Board::new();
        let anchors = get_candidate_anchors(&board);
        assert!(anchors.contains(&(0, 0)));
        assert_eq!(anchors.len(), 1);
    }
}
