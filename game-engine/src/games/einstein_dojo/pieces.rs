//! Einstein hat tile geometry — all 12 orientations.
//!
//! Each piece covers 8 kites across 3 hex cells (4+2+2 distribution).
//! A hex cell has 6 kites indexed 0-5 (flat-top orientation).
//!
//! Piece A (hat) and Piece B (shirt) are mirror images.
//! Each has 6 rotations (60° increments) giving 12 total orientations.

use std::collections::HashSet;
use std::sync::LazyLock;

/// A kite: (q, r, k) where (q,r) is the hex and k is kite index 0..5.
pub type Kite = (i32, i32, u8);
pub type Footprint = Vec<Kite>;

pub const NUM_ORIENTATIONS: u8 = 12;

/// Piece A (hat) base footprint at anchor (0,0).
/// Hex(0,0): kites 1,2,3,4 | Hex(-1,1): kites 4,5 | Hex(-1,0): kites 0,1
const PIECE_A_BASE: [Kite; 8] = [
    (0, 0, 1),
    (0, 0, 2),
    (0, 0, 3),
    (0, 0, 4),
    (-1, 1, 4),
    (-1, 1, 5),
    (-1, 0, 0),
    (-1, 0, 1),
];

/// Piece B (shirt) base footprint — vertical mirror of A.
/// Hex(0,0): kites 0,1,2,5 | Hex(1,-1): kites 2,3 | Hex(1,0): kites 4,5
const PIECE_B_BASE: [Kite; 8] = [
    (0, 0, 0),
    (0, 0, 1),
    (0, 0, 2),
    (0, 0, 5),
    (1, -1, 2),
    (1, -1, 3),
    (1, 0, 4),
    (1, 0, 5),
];

/// Rotate a footprint 60° clockwise: (q,r) → (-r, q+r), kite → (kite+1)%6.
fn rotate_footprint(footprint: &[Kite]) -> Footprint {
    footprint
        .iter()
        .map(|&(q, r, k)| (-r, q + r, (k + 1) % 6))
        .collect()
}

/// All 12 orientations: [0..5] = A rotations, [6..11] = B rotations.
pub static ALL_ORIENTATIONS: LazyLock<Vec<Footprint>> = LazyLock::new(|| {
    let mut orientations = Vec::with_capacity(12);

    // A chirality: 6 rotations
    let mut fp: Footprint = PIECE_A_BASE.to_vec();
    for _ in 0..6 {
        orientations.push(fp.clone());
        fp = rotate_footprint(&fp);
    }

    // B chirality: 6 rotations
    fp = PIECE_B_BASE.to_vec();
    for _ in 0..6 {
        orientations.push(fp.clone());
        fp = rotate_footprint(&fp);
    }

    orientations
});

/// Get the 8 absolute kite positions for a piece at given orientation and anchor.
pub fn get_placed_kites(orientation: u8, anchor_q: i32, anchor_r: i32) -> Vec<Kite> {
    ALL_ORIENTATIONS[orientation as usize]
        .iter()
        .map(|&(dq, dr, k)| (dq + anchor_q, dr + anchor_r, k))
        .collect()
}

/// Get the set of hex cells occupied by a piece.
pub fn get_occupied_hexes(orientation: u8, anchor_q: i32, anchor_r: i32) -> HashSet<(i32, i32)> {
    get_placed_kites(orientation, anchor_q, anchor_r)
        .iter()
        .map(|&(q, r, _)| (q, r))
        .collect()
}

/// Build a kite key string matching frontend format: "q,r:k".
pub fn kite_to_key(q: i32, r: i32, k: u8) -> String {
    format!("{q},{r}:{k}")
}

/// Build a hex key string: "q,r".
pub fn hex_to_key(q: i32, r: i32) -> String {
    format!("{q},{r}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_piece_a_has_8_kites() {
        assert_eq!(PIECE_A_BASE.len(), 8);
    }

    #[test]
    fn test_piece_b_has_8_kites() {
        assert_eq!(PIECE_B_BASE.len(), 8);
    }

    #[test]
    fn test_piece_spans_3_hexes() {
        let hexes_a: HashSet<(i32, i32)> = PIECE_A_BASE.iter().map(|&(q, r, _)| (q, r)).collect();
        assert_eq!(hexes_a.len(), 3);

        let hexes_b: HashSet<(i32, i32)> = PIECE_B_BASE.iter().map(|&(q, r, _)| (q, r)).collect();
        assert_eq!(hexes_b.len(), 3);
    }

    #[test]
    fn test_all_orientations_count() {
        assert_eq!(ALL_ORIENTATIONS.len(), 12);
    }

    #[test]
    fn test_all_orientations_unique() {
        let mut seen = HashSet::new();
        for fp in ALL_ORIENTATIONS.iter() {
            let mut sorted = fp.clone();
            sorted.sort();
            assert!(seen.insert(sorted), "duplicate orientation found");
        }
    }

    #[test]
    fn test_each_orientation_has_8_kites_across_3_hexes() {
        for (i, fp) in ALL_ORIENTATIONS.iter().enumerate() {
            assert_eq!(fp.len(), 8, "orientation {i} has wrong kite count");
            let hexes: HashSet<(i32, i32)> = fp.iter().map(|&(q, r, _)| (q, r)).collect();
            assert_eq!(hexes.len(), 3, "orientation {i} has wrong hex count");
        }
    }

    #[test]
    fn test_rotate_6_times_returns_to_original() {
        let mut fp: Footprint = PIECE_A_BASE.to_vec();
        for _ in 0..6 {
            fp = rotate_footprint(&fp);
        }
        let mut original = PIECE_A_BASE.to_vec();
        original.sort();
        fp.sort();
        assert_eq!(fp, original);
    }

    #[test]
    fn test_get_placed_kites_with_offset() {
        let kites = get_placed_kites(0, 5, 3);
        // Orientation 0 = A base. Anchor (5,3) shifts all coordinates.
        assert_eq!(kites.len(), 8);
        assert!(kites.contains(&(5, 3, 1)));  // (0,0,1) + (5,3)
        assert!(kites.contains(&(4, 4, 4)));  // (-1,1,4) + (5,3)
        assert!(kites.contains(&(4, 3, 0)));  // (-1,0,0) + (5,3)
    }

    #[test]
    fn test_kite_to_key() {
        assert_eq!(kite_to_key(1, -2, 3), "1,-2:3");
    }

    #[test]
    fn test_hex_to_key() {
        assert_eq!(hex_to_key(-1, 1), "-1,1");
    }
}
