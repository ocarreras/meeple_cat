//! Scoring for Ein Stein Dojo — count complete hexes per player.

use std::collections::HashMap;

use super::types::{Board, HexState};

/// Count hexes in COMPLETE state per player.
///
/// Returns {player_id: count_of_complete_hexes}.
pub fn count_complete_hexes(board: &Board) -> HashMap<String, i64> {
    let mut counts: HashMap<String, i64> = HashMap::new();

    for (hex_key, &state) in &board.hex_states {
        if state == HexState::Complete {
            // All 6 kites belong to the same player — check kite 0
            let kite_key = format!("{hex_key}:0");
            if let Some(owner) = board.kite_owners.get(&kite_key) {
                *counts.entry(owner.clone()).or_insert(0) += 1;
            }
        }
    }

    counts
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::games::einstein_dojo::board::apply_placement;

    #[test]
    fn test_no_complete_hexes_initially() {
        let board = Board::new();
        let counts = count_complete_hexes(&board);
        assert!(counts.is_empty());
    }

    #[test]
    fn test_complete_hex_after_filling() {
        let mut board = Board::new();
        // Manually fill all 6 kites of hex (0,0) with one player
        for k in 0..6 {
            board.kite_owners.insert(format!("0,0:{k}"), "p1".into());
        }
        board.hex_states.insert("0,0".into(), HexState::Complete);

        let counts = count_complete_hexes(&board);
        assert_eq!(counts.get("p1"), Some(&1));
    }

    #[test]
    fn test_single_placement_no_complete() {
        let mut board = Board::new();
        apply_placement(&mut board, "p1", 0, 0, 0);
        // One piece cannot complete a hex (only covers 4+2+2 kites across 3 hexes)
        let counts = count_complete_hexes(&board);
        assert_eq!(counts.get("p1").copied().unwrap_or(0), 0);
    }
}
