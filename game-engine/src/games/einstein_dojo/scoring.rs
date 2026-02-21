//! Scoring for Ein Stein Dojo — count complete hexes + resolved hexes + marks per player.

use std::collections::HashMap;

use super::types::{Board, HexState};

/// Count score per player: Complete hexes + resolved hexes + marks.
///
/// Returns {player_id: score}.
pub fn count_scores(board: &Board) -> HashMap<String, i64> {
    let mut counts: HashMap<String, i64> = HashMap::new();

    // Complete hexes: 1 point each
    for (hex_key, &state) in &board.hex_states {
        if state == HexState::Complete {
            let kite_key = format!("{hex_key}:0");
            if let Some(owner) = board.kite_owners.get(&kite_key) {
                *counts.entry(owner.clone()).or_insert(0) += 1;
            }
        }
    }

    // Resolved hexes: 1 point each (from hex_owners)
    for (hex_key, owner) in &board.hex_owners {
        let state = board.hex_states.get(hex_key).copied().unwrap_or(HexState::Empty);
        if state == HexState::Resolved {
            *counts.entry(owner.clone()).or_insert(0) += 1;
        }
    }

    // Marks: 1 point each
    for owner in board.hex_marks.values() {
        *counts.entry(owner.clone()).or_insert(0) += 1;
    }

    counts
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::games::einstein_dojo::board::apply_placement;

    #[test]
    fn test_no_scores_initially() {
        let board = Board::new();
        let counts = count_scores(&board);
        assert!(counts.is_empty());
    }

    #[test]
    fn test_complete_hex_scores() {
        let mut board = Board::new();
        for k in 0..6 {
            board.kite_owners.insert(format!("0,0:{k}"), "p1".into());
        }
        board.hex_states.insert("0,0".into(), HexState::Complete);

        let counts = count_scores(&board);
        assert_eq!(counts.get("p1"), Some(&1));
    }

    #[test]
    fn test_single_placement_no_complete() {
        let mut board = Board::new();
        apply_placement(&mut board, "p1", 0, 0, 0);
        let counts = count_scores(&board);
        assert_eq!(counts.get("p1").copied().unwrap_or(0), 0);
    }

    #[test]
    fn test_marks_count_in_score() {
        let mut board = Board::new();
        board.hex_marks.insert("0,0".into(), "p1".into());
        board.hex_marks.insert("1,0".into(), "p2".into());
        board.hex_marks.insert("0,1".into(), "p1".into());

        let counts = count_scores(&board);
        assert_eq!(counts.get("p1"), Some(&2));
        assert_eq!(counts.get("p2"), Some(&1));
    }

    #[test]
    fn test_marks_plus_complete_hex() {
        let mut board = Board::new();
        // Complete hex for p1
        for k in 0..6 {
            board.kite_owners.insert(format!("0,0:{k}"), "p1".into());
        }
        board.hex_states.insert("0,0".into(), HexState::Complete);
        // Mark for p1
        board.hex_marks.insert("1,0".into(), "p1".into());

        let counts = count_scores(&board);
        assert_eq!(counts.get("p1"), Some(&2)); // 1 complete + 1 mark
    }

    #[test]
    fn test_resolved_hex_scores() {
        let mut board = Board::new();
        board.hex_states.insert("0,0".into(), HexState::Resolved);
        board.hex_owners.insert("0,0".into(), "p1".into());
        let counts = count_scores(&board);
        assert_eq!(counts.get("p1"), Some(&1));
    }

    #[test]
    fn test_complete_plus_resolved_plus_marks() {
        let mut board = Board::new();
        // Complete hex for p1
        for k in 0..6 {
            board.kite_owners.insert(format!("0,0:{k}"), "p1".into());
        }
        board.hex_states.insert("0,0".into(), HexState::Complete);
        // Resolved hex for p1
        board.hex_states.insert("1,0".into(), HexState::Resolved);
        board.hex_owners.insert("1,0".into(), "p1".into());
        // Mark for p1
        board.hex_marks.insert("2,0".into(), "p1".into());

        let counts = count_scores(&board);
        assert_eq!(counts.get("p1"), Some(&3)); // 1 + 1 + 1
    }
}
