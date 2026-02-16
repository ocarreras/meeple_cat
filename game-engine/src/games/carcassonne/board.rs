//! Board logic: tile placement validation, open position calculation.
//! Mirrors backend/src/games/carcassonne/board.py.

use std::collections::{HashMap, HashSet};

use super::tiles::ROTATED_EDGES;
use super::types::*;

/// Get the edge type at a given direction for a tile with rotation applied.
/// Uses pre-computed lookup table — zero allocation.
#[inline]
pub fn get_rotated_edge(tile_type_idx: u8, rotation: u32, direction: &str) -> EdgeType {
    let rot_idx = ((rotation / 90) % 4) as usize;
    let dir_idx = direction_index(direction);
    ROTATED_EDGES[tile_type_idx as usize][rot_idx][dir_idx]
}

/// Check if a tile can be placed at the given position with the given rotation.
///
/// Rules:
/// 1. Position must be empty
/// 2. Position must be adjacent to at least one placed tile
/// 3. All edges touching adjacent tiles must match
pub fn can_place_tile(
    board_tiles: &HashMap<(i32, i32), PlacedTile>,
    tile_type_idx: u8,
    pos: (i32, i32),
    rotation: u32,
) -> bool {
    if board_tiles.contains_key(&pos) {
        return false;
    }

    let (x, y) = pos;
    let mut has_neighbor = false;

    // Inline neighbor offsets for N, E, S, W
    const NEIGHBOR_OFFSETS: [(i32, i32, usize); 4] = [
        (0, 1, 0),   // N → opposite is S (index 2)
        (1, 0, 1),   // E → opposite is W (index 3)
        (0, -1, 2),  // S → opposite is N (index 0)
        (-1, 0, 3),  // W → opposite is E (index 1)
    ];
    const OPPOSITE_DIR_IDX: [usize; 4] = [2, 3, 0, 1]; // N→S, E→W, S→N, W→E

    let rot_idx = ((rotation / 90) % 4) as usize;

    for &(dx, dy, dir_idx) in &NEIGHBOR_OFFSETS {
        let neighbor_pos = (x + dx, y + dy);
        let Some(neighbor_tile) = board_tiles.get(&neighbor_pos) else {
            continue;
        };

        has_neighbor = true;

        let opp_dir_idx = OPPOSITE_DIR_IDX[dir_idx];
        let neighbor_rot_idx = ((neighbor_tile.rotation / 90) % 4) as usize;

        let neighbor_edge = ROTATED_EDGES[neighbor_tile.tile_type_id as usize][neighbor_rot_idx][opp_dir_idx];
        let our_edge = ROTATED_EDGES[tile_type_idx as usize][rot_idx][dir_idx];

        if our_edge != neighbor_edge {
            return false;
        }
    }

    has_neighbor
}

/// Recalculate all open positions (empty positions adjacent to placed tiles).
pub fn recalculate_open_positions(board_tiles: &HashMap<(i32, i32), PlacedTile>) -> Vec<(i32, i32)> {
    let mut open_set: HashSet<(i32, i32)> = HashSet::new();

    for &(x, y) in board_tiles.keys() {
        for (dx, dy) in [(0, 1), (1, 0), (0, -1), (-1, 0)] {
            let neighbor = (x + dx, y + dy);
            if !board_tiles.contains_key(&neighbor) {
                open_set.insert(neighbor);
            }
        }
    }

    let mut result: Vec<(i32, i32)> = open_set.into_iter().collect();
    result.sort();
    result
}

/// Check if a tile type can be placed anywhere on the board.
pub fn tile_has_valid_placement(
    board_tiles: &HashMap<(i32, i32), PlacedTile>,
    open_positions: &[(i32, i32)],
    tile_type_idx: u8,
) -> bool {
    for &pos in open_positions {
        for rotation in [0, 90, 180, 270] {
            if can_place_tile(board_tiles, tile_type_idx, pos, rotation) {
                return true;
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_board_with_starting_tile() -> HashMap<(i32, i32), PlacedTile> {
        let mut tiles = HashMap::new();
        tiles.insert(
            (0, 0),
            PlacedTile {
                tile_type_id: tile_type_to_index("D"),
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
        assert!(open.contains(&(-1, 0)));
        assert!(open.contains(&(0, 1)));
        assert!(open.contains(&(0, -1)));
        assert!(open.contains(&(1, 0)));
    }

    #[test]
    fn test_cannot_place_on_occupied() {
        let board = make_board_with_starting_tile();
        assert!(!can_place_tile(&board, tile_type_to_index("E"), (0, 0), 0));
    }

    #[test]
    fn test_cannot_place_isolated() {
        let board = make_board_with_starting_tile();
        assert!(!can_place_tile(&board, tile_type_to_index("E"), (5, 5), 0));
    }

    #[test]
    fn test_can_place_matching_edge() {
        let board = make_board_with_starting_tile();
        // D has city on N edge. E has city on N edge.
        // Placing E at (0,1) needs its S edge to match D's N edge (city).
        // E: N=city, E=field, S=field, W=field
        // E rotated 180: N=field, E=field, S=city, W=field → S=city matches D's N=city
        assert!(can_place_tile(&board, tile_type_to_index("E"), (0, 1), 180));
    }

    #[test]
    fn test_cannot_place_mismatching_edge() {
        let board = make_board_with_starting_tile();
        // D has city on N. E at (0,1) rotation 0: S=field, needs city.
        assert!(!can_place_tile(&board, tile_type_to_index("E"), (0, 1), 0));
    }

    #[test]
    fn test_tile_has_valid_placement() {
        let board = make_board_with_starting_tile();
        let open = recalculate_open_positions(&board);
        // E (city N) should be placeable somewhere
        assert!(tile_has_valid_placement(&board, &open, tile_type_to_index("E")));
        // C (city on all sides) can only go next to all-city neighbors
        assert!(tile_has_valid_placement(&board, &open, tile_type_to_index("C")));
    }
}
