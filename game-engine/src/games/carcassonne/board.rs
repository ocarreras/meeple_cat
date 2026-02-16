//! Board logic: tile placement validation, open position calculation.
//! Mirrors backend/src/games/carcassonne/board.py.

use std::collections::{HashMap, HashSet};

use super::tiles::TILE_LOOKUP;
use super::types::*;

/// Get the edge type at a given direction for a tile with rotation applied.
pub fn get_rotated_edge(tile_type_id: &str, rotation: u32, direction: &str) -> EdgeType {
    let tile_def = &TILE_LOOKUP[tile_type_id];
    let rotated = rotate_edges(&tile_def.edges, rotation);
    rotated[direction]
}

/// Check if a tile can be placed at the given position with the given rotation.
///
/// Rules:
/// 1. Position must be empty
/// 2. Position must be adjacent to at least one placed tile
/// 3. All edges touching adjacent tiles must match
pub fn can_place_tile(
    board_tiles: &HashMap<String, PlacedTile>,
    tile_type_id: &str,
    position_key: &str,
    rotation: u32,
) -> bool {
    if board_tiles.contains_key(position_key) {
        return false;
    }

    let pos = Position::from_key(position_key);
    let mut has_neighbor = false;

    for direction in DIRECTIONS {
        let neighbor_pos = pos.neighbor(direction);
        let neighbor_key = neighbor_pos.to_key();

        let Some(neighbor_tile) = board_tiles.get(&neighbor_key) else {
            continue;
        };

        has_neighbor = true;
        let neighbor_edge = get_rotated_edge(
            &neighbor_tile.tile_type_id,
            neighbor_tile.rotation,
            opposite_direction(direction),
        );
        let our_edge = get_rotated_edge(tile_type_id, rotation, direction);

        if our_edge != neighbor_edge {
            return false;
        }
    }

    has_neighbor
}

/// Recalculate all open positions (empty positions adjacent to placed tiles).
pub fn recalculate_open_positions(board_tiles: &HashMap<String, PlacedTile>) -> Vec<String> {
    let mut open_set: HashSet<String> = HashSet::new();

    for pos_key in board_tiles.keys() {
        let pos = Position::from_key(pos_key);
        for direction in DIRECTIONS {
            let neighbor = pos.neighbor(direction);
            let neighbor_key = neighbor.to_key();
            if !board_tiles.contains_key(&neighbor_key) {
                open_set.insert(neighbor_key);
            }
        }
    }

    let mut result: Vec<String> = open_set.into_iter().collect();
    result.sort();
    result
}

/// Check if a tile type can be placed anywhere on the board.
pub fn tile_has_valid_placement(
    board_tiles: &HashMap<String, PlacedTile>,
    open_positions: &[String],
    tile_type_id: &str,
) -> bool {
    for pos_key in open_positions {
        for rotation in [0, 90, 180, 270] {
            if can_place_tile(board_tiles, tile_type_id, pos_key, rotation) {
                return true;
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_board_with_starting_tile() -> HashMap<String, PlacedTile> {
        let mut tiles = HashMap::new();
        tiles.insert(
            "0,0".into(),
            PlacedTile {
                tile_type_id: "D".into(),
                rotation: 0,
            },
        );
        tiles
    }

    #[test]
    fn test_starting_tile_open_positions() {
        let board = make_board_with_starting_tile();
        let open = recalculate_open_positions(&board);
        assert_eq!(open.len(), 4);
        assert!(open.contains(&"-1,0".to_string()));
        assert!(open.contains(&"0,1".to_string()));
        assert!(open.contains(&"0,-1".to_string()));
        assert!(open.contains(&"1,0".to_string()));
    }

    #[test]
    fn test_cannot_place_on_occupied() {
        let board = make_board_with_starting_tile();
        assert!(!can_place_tile(&board, "E", "0,0", 0));
    }

    #[test]
    fn test_cannot_place_isolated() {
        let board = make_board_with_starting_tile();
        assert!(!can_place_tile(&board, "E", "5,5", 0));
    }

    #[test]
    fn test_can_place_matching_edge() {
        let board = make_board_with_starting_tile();
        // D has city on N edge. E has city on N edge.
        // Placing E at (0,1) needs its S edge to match D's N edge (city).
        // E: N=city, E=field, S=field, W=field
        // E rotated 180: N=field, E=field, S=city, W=field → S=city matches D's N=city
        assert!(can_place_tile(&board, "E", "0,1", 180));
    }

    #[test]
    fn test_cannot_place_mismatching_edge() {
        let board = make_board_with_starting_tile();
        // D has city on N. E at (0,1) rotation 0: S=field, needs city.
        assert!(!can_place_tile(&board, "E", "0,1", 0));
    }

    #[test]
    fn test_tile_has_valid_placement() {
        let board = make_board_with_starting_tile();
        let open = recalculate_open_positions(&board);
        // E (city N) should be placeable somewhere
        assert!(tile_has_valid_placement(&board, &open, "E"));
        // C (city on all sides) can only go next to all-city neighbors
        // With just starting tile D (city N, road E, field S, road W), C can go at (0,1) where D's N=city
        // C would need ALL edges to match, but D only exposes city on N
        // At (0,1): C's S must be city (ok, D's N is city). But C has city on all sides,
        // and no other neighbors exist. So C can be placed at (0,1).
        assert!(tile_has_valid_placement(&board, &open, "C"));
    }
}
