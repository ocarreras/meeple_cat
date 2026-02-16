//! Complete tile catalog for the Carcassonne base game (24 types, 72 tiles).
//! Mirrors backend/src/games/carcassonne/tiles.py.

use once_cell::sync::Lazy;
use std::collections::HashMap;

use super::types::*;

use EdgeType::{City as C, Field as F, Road as R};
use FeatureType::{City, Field, Monastery, Road};

fn edges(n: EdgeType, e: EdgeType, s: EdgeType, w: EdgeType) -> [EdgeType; 4] {
    [n, e, s, w]
}

fn feat(
    ft: FeatureType,
    e: &[&str],
    spots: &[&str],
) -> TileFeature {
    TileFeature {
        feature_type: ft,
        edges: e.iter().map(|s| s.to_string()).collect(),
        has_pennant: false,
        is_monastery: false,
        meeple_spots: spots.iter().map(|s| s.to_string()).collect(),
        adjacent_cities: vec![],
    }
}

fn feat_pennant(
    ft: FeatureType,
    e: &[&str],
    spots: &[&str],
) -> TileFeature {
    TileFeature {
        has_pennant: true,
        ..feat(ft, e, spots)
    }
}

fn feat_monastery(spots: &[&str]) -> TileFeature {
    TileFeature {
        feature_type: Monastery,
        edges: vec![],
        has_pennant: false,
        is_monastery: true,
        meeple_spots: spots.iter().map(|s| s.to_string()).collect(),
        adjacent_cities: vec![],
    }
}

fn feat_with_adj(
    ft: FeatureType,
    e: &[&str],
    spots: &[&str],
    adj: &[&str],
) -> TileFeature {
    TileFeature {
        adjacent_cities: adj.iter().map(|s| s.to_string()).collect(),
        ..feat(ft, e, spots)
    }
}

pub static TILE_CATALOG: Lazy<Vec<TileDefinition>> = Lazy::new(|| {
    vec![
        // A: Monastery with road south (x2)
        TileDefinition {
            tile_type_id: "A".into(),
            edges: edges(F, F, R, F),
            features: vec![
                feat_monastery(&["monastery"]),
                feat(Road, &["S"], &["road_S"]),
                feat_with_adj(Field, &["N", "E", "W", "S:E", "S:W"], &["field_NEW"], &[]),
            ],
            count: 2,
            image_id: "tile_A".into(),
            internal_connections: vec![],
        },
        // B: Monastery, no road (x4)
        TileDefinition {
            tile_type_id: "B".into(),
            edges: edges(F, F, F, F),
            features: vec![
                feat_monastery(&["monastery"]),
                feat_with_adj(Field, &["N", "E", "S", "W"], &["field_NESW"], &[]),
            ],
            count: 4,
            image_id: "tile_B".into(),
            internal_connections: vec![],
        },
        // C: Full city with pennant (x1)
        TileDefinition {
            tile_type_id: "C".into(),
            edges: edges(C, C, C, C),
            features: vec![
                feat_pennant(City, &["N", "E", "S", "W"], &["city_NESW"]),
            ],
            count: 1,
            image_id: "tile_C".into(),
            internal_connections: vec![],
        },
        // D: City N, road E-W (x4) — the starting tile
        TileDefinition {
            tile_type_id: "D".into(),
            edges: edges(C, R, F, R),
            features: vec![
                feat(City, &["N"], &["city_N"]),
                feat(Road, &["E", "W"], &["road_EW"]),
                feat_with_adj(Field, &["E:N", "W:N"], &["field_N"], &["city_N"]),
                feat_with_adj(Field, &["S", "E:S", "W:S"], &["field_S"], &["city_N"]),
            ],
            count: 4,
            image_id: "tile_D".into(),
            internal_connections: vec![],
        },
        // E: City N (x5)
        TileDefinition {
            tile_type_id: "E".into(),
            edges: edges(C, F, F, F),
            features: vec![
                feat(City, &["N"], &["city_N"]),
                feat_with_adj(Field, &["E", "S", "W"], &["field_ESW"], &["city_N"]),
            ],
            count: 5,
            image_id: "tile_E".into(),
            internal_connections: vec![],
        },
        // F: City E-W connected, with pennant (x2)
        TileDefinition {
            tile_type_id: "F".into(),
            edges: edges(F, C, F, C),
            features: vec![
                feat_pennant(City, &["E", "W"], &["city_EW"]),
                feat_with_adj(Field, &["N"], &["field_N"], &["city_EW"]),
                feat_with_adj(Field, &["S"], &["field_S"], &["city_EW"]),
            ],
            count: 2,
            image_id: "tile_F".into(),
            internal_connections: vec![],
        },
        // G: City N-S connected (x1)
        TileDefinition {
            tile_type_id: "G".into(),
            edges: edges(C, F, C, F),
            features: vec![
                feat(City, &["N", "S"], &["city_NS"]),
                feat_with_adj(Field, &["E"], &["field_E"], &["city_NS"]),
                feat_with_adj(Field, &["W"], &["field_W"], &["city_NS"]),
            ],
            count: 1,
            image_id: "tile_G".into(),
            internal_connections: vec![],
        },
        // H: City N and city S, NOT connected (x3)
        TileDefinition {
            tile_type_id: "H".into(),
            edges: edges(C, F, C, F),
            features: vec![
                feat(City, &["N"], &["city_N"]),
                feat(City, &["S"], &["city_S"]),
                feat_with_adj(Field, &["E"], &["field_E"], &["city_N", "city_S"]),
                feat_with_adj(Field, &["W"], &["field_W"], &["city_N", "city_S"]),
            ],
            count: 3,
            image_id: "tile_H".into(),
            internal_connections: vec![],
        },
        // I: City N and city W, NOT connected (x2)
        TileDefinition {
            tile_type_id: "I".into(),
            edges: edges(C, F, F, C),
            features: vec![
                feat(City, &["N"], &["city_N"]),
                feat(City, &["W"], &["city_W"]),
                feat_with_adj(Field, &["E", "S"], &["field_ES"], &["city_N", "city_W"]),
            ],
            count: 2,
            image_id: "tile_I".into(),
            internal_connections: vec![],
        },
        // J: City N, road E-S curve (x3)
        TileDefinition {
            tile_type_id: "J".into(),
            edges: edges(C, R, R, F),
            features: vec![
                feat(City, &["N"], &["city_N"]),
                feat(Road, &["E", "S"], &["road_ES"]),
                feat_with_adj(Field, &["W", "E:N", "S:W"], &["field_W"], &["city_N"]),
                feat_with_adj(Field, &["E:S", "S:E"], &["field_ES"], &["city_N"]),
            ],
            count: 3,
            image_id: "tile_J".into(),
            internal_connections: vec![],
        },
        // K: City N, road W-S curve (x3)
        TileDefinition {
            tile_type_id: "K".into(),
            edges: edges(C, F, R, R),
            features: vec![
                feat(City, &["N"], &["city_N"]),
                feat(Road, &["S", "W"], &["road_SW"]),
                feat_with_adj(Field, &["E", "S:E", "W:N"], &["field_E"], &["city_N"]),
                feat_with_adj(Field, &["S:W", "W:S"], &["field_SW"], &["city_N"]),
            ],
            count: 3,
            image_id: "tile_K".into(),
            internal_connections: vec![],
        },
        // L: City N, road E-S-W T-junction (x3)
        TileDefinition {
            tile_type_id: "L".into(),
            edges: edges(C, R, R, R),
            features: vec![
                feat(City, &["N"], &["city_N"]),
                feat(Road, &["E"], &["road_E"]),
                feat(Road, &["S"], &["road_S"]),
                feat(Road, &["W"], &["road_W"]),
                feat_with_adj(Field, &["E:N"], &["field_NE"], &["city_N"]),
                feat_with_adj(Field, &["E:S", "S:E"], &["field_SE"], &[]),
                feat_with_adj(Field, &["S:W", "W:S"], &["field_SW"], &[]),
                feat_with_adj(Field, &["W:N"], &["field_NW"], &["city_N"]),
            ],
            count: 3,
            image_id: "tile_L".into(),
            internal_connections: vec![],
        },
        // M: City N-W connected, with pennant (x2)
        TileDefinition {
            tile_type_id: "M".into(),
            edges: edges(C, F, F, C),
            features: vec![
                feat_pennant(City, &["N", "W"], &["city_NW"]),
                feat_with_adj(Field, &["E", "S"], &["field_ES"], &["city_NW"]),
            ],
            count: 2,
            image_id: "tile_M".into(),
            internal_connections: vec![],
        },
        // N: City N-W connected, no pennant (x3)
        TileDefinition {
            tile_type_id: "N".into(),
            edges: edges(C, F, F, C),
            features: vec![
                feat(City, &["N", "W"], &["city_NW"]),
                feat_with_adj(Field, &["E", "S"], &["field_ES"], &["city_NW"]),
            ],
            count: 3,
            image_id: "tile_N".into(),
            internal_connections: vec![],
        },
        // O: City N-W connected, pennant, road E-S (x2)
        TileDefinition {
            tile_type_id: "O".into(),
            edges: edges(C, R, R, C),
            features: vec![
                feat_pennant(City, &["N", "W"], &["city_NW"]),
                feat(Road, &["E", "S"], &["road_ES"]),
                feat_with_adj(Field, &["E:N", "S:W"], &["field_NE"], &["city_NW"]),
                feat_with_adj(Field, &["E:S", "S:E"], &["field_SE"], &[]),
            ],
            count: 2,
            image_id: "tile_O".into(),
            internal_connections: vec![],
        },
        // P: City N-W connected, no pennant, road E-S (x3)
        TileDefinition {
            tile_type_id: "P".into(),
            edges: edges(C, R, R, C),
            features: vec![
                feat(City, &["N", "W"], &["city_NW"]),
                feat(Road, &["E", "S"], &["road_ES"]),
                feat_with_adj(Field, &["E:N", "S:W"], &["field_NE"], &["city_NW"]),
                feat_with_adj(Field, &["E:S", "S:E"], &["field_SE"], &[]),
            ],
            count: 3,
            image_id: "tile_P".into(),
            internal_connections: vec![],
        },
        // Q: City N-E-W connected, with pennant (x2)
        TileDefinition {
            tile_type_id: "Q".into(),
            edges: edges(C, C, F, C),
            features: vec![
                feat_pennant(City, &["N", "E", "W"], &["city_NEW"]),
                feat_with_adj(Field, &["S"], &["field_S"], &["city_NEW"]),
            ],
            count: 2,
            image_id: "tile_Q".into(),
            internal_connections: vec![],
        },
        // R: City N-E-W connected, pennant, road S (x2)
        TileDefinition {
            tile_type_id: "R".into(),
            edges: edges(C, C, R, C),
            features: vec![
                feat_pennant(City, &["N", "E", "W"], &["city_NEW"]),
                feat(Road, &["S"], &["road_S"]),
                feat_with_adj(Field, &["S:W"], &["field_SW"], &["city_NEW"]),
                feat_with_adj(Field, &["S:E"], &["field_SE"], &["city_NEW"]),
            ],
            count: 2,
            image_id: "tile_R".into(),
            internal_connections: vec![],
        },
        // S: City N-E-W connected, no pennant (x2)
        TileDefinition {
            tile_type_id: "S".into(),
            edges: edges(C, C, F, C),
            features: vec![
                feat(City, &["N", "E", "W"], &["city_NEW"]),
                feat_with_adj(Field, &["S"], &["field_S"], &["city_NEW"]),
            ],
            count: 2,
            image_id: "tile_S".into(),
            internal_connections: vec![],
        },
        // T: City N-E-W connected, no pennant, road S (x1)
        TileDefinition {
            tile_type_id: "T".into(),
            edges: edges(C, C, R, C),
            features: vec![
                feat(City, &["N", "E", "W"], &["city_NEW"]),
                feat(Road, &["S"], &["road_S"]),
                feat_with_adj(Field, &["S:W"], &["field_SW"], &["city_NEW"]),
                feat_with_adj(Field, &["S:E"], &["field_SE"], &["city_NEW"]),
            ],
            count: 1,
            image_id: "tile_T".into(),
            internal_connections: vec![],
        },
        // U: Road N-S straight (x8)
        TileDefinition {
            tile_type_id: "U".into(),
            edges: edges(R, F, R, F),
            features: vec![
                feat(Road, &["N", "S"], &["road_NS"]),
                feat_with_adj(Field, &["E", "N:E", "S:E"], &["field_E"], &[]),
                feat_with_adj(Field, &["W", "N:W", "S:W"], &["field_W"], &[]),
            ],
            count: 8,
            image_id: "tile_U".into(),
            internal_connections: vec![],
        },
        // V: Road S-W curve (x9)
        TileDefinition {
            tile_type_id: "V".into(),
            edges: edges(F, F, R, R),
            features: vec![
                feat(Road, &["S", "W"], &["road_SW"]),
                feat_with_adj(Field, &["N", "E", "S:E", "W:N"], &["field_NE"], &[]),
                feat_with_adj(Field, &["S:W", "W:S"], &["field_SW"], &[]),
            ],
            count: 9,
            image_id: "tile_V".into(),
            internal_connections: vec![],
        },
        // W: Road 3-way T-junction N-S-W (x4)
        TileDefinition {
            tile_type_id: "W".into(),
            edges: edges(R, F, R, R),
            features: vec![
                feat(Road, &["N"], &["road_N"]),
                feat(Road, &["S"], &["road_S"]),
                feat(Road, &["W"], &["road_W"]),
                feat_with_adj(Field, &["E", "N:E", "S:E"], &["field_NE", "field_SE"], &[]),
                feat_with_adj(Field, &["N:W", "W:N"], &["field_NW"], &[]),
                feat_with_adj(Field, &["S:W", "W:S"], &["field_SW"], &[]),
            ],
            count: 4,
            image_id: "tile_W".into(),
            internal_connections: vec![],
        },
        // X: Road 4-way crossroads (x1)
        TileDefinition {
            tile_type_id: "X".into(),
            edges: edges(R, R, R, R),
            features: vec![
                feat(Road, &["N"], &["road_N"]),
                feat(Road, &["E"], &["road_E"]),
                feat(Road, &["S"], &["road_S"]),
                feat(Road, &["W"], &["road_W"]),
                feat_with_adj(Field, &["N:E", "E:N"], &["field_NE"], &[]),
                feat_with_adj(Field, &["E:S", "S:E"], &["field_SE"], &[]),
                feat_with_adj(Field, &["S:W", "W:S"], &["field_SW"], &[]),
                feat_with_adj(Field, &["W:N", "N:W"], &["field_NW"], &[]),
            ],
            count: 1,
            image_id: "tile_X".into(),
            internal_connections: vec![],
        },
    ]
});

pub static TILE_LOOKUP: Lazy<HashMap<String, &'static TileDefinition>> = Lazy::new(|| {
    TILE_CATALOG
        .iter()
        .map(|t| (t.tile_type_id.clone(), t))
        .collect()
});

/// Pre-computed rotated edges for all tile types × 4 rotations.
/// Indexed by tile type u8 index → \[rotation_index (0-3)\]\[direction_index (N=0,E=1,S=2,W=3)\].
pub static ROTATED_EDGES: Lazy<Vec<[[EdgeType; 4]; 4]>> = Lazy::new(|| {
    let mut table = vec![[[EdgeType::Field; 4]; 4]; 24];
    for tile in TILE_CATALOG.iter() {
        let idx = tile_type_to_index(&tile.tile_type_id) as usize;
        for rot_idx in 0..4usize {
            for dir_idx in 0..4usize {
                let source_idx = (dir_idx + 4 - rot_idx) % 4;
                table[idx][rot_idx][dir_idx] = tile.edges[source_idx];
            }
        }
    }
    table
});

/// Fast tile definition lookup by u8 index (0–23).
pub static TILE_DEFS: Lazy<Vec<&'static TileDefinition>> = Lazy::new(|| {
    let mut defs: Vec<Option<&'static TileDefinition>> = vec![None; 24];
    for t in TILE_CATALOG.iter() {
        let idx = tile_type_to_index(&t.tile_type_id) as usize;
        defs[idx] = Some(t);
    }
    defs.into_iter().map(|d| d.unwrap()).collect()
});

pub const STARTING_TILE_ID: &str = "D";
pub const STARTING_TILE_IDX: u8 = 3; // tile_type_to_index("D")

/// Build the draw bag as u8 tile type indices. Excludes one copy of the starting tile.
pub fn build_tile_bag(_expansions: Option<&[String]>) -> Vec<u8> {
    let mut bag = Vec::with_capacity(71);
    for tile_def in TILE_CATALOG.iter() {
        let count = if tile_def.tile_type_id == STARTING_TILE_ID {
            tile_def.count - 1
        } else {
            tile_def.count
        };
        let idx = tile_type_to_index(&tile_def.tile_type_id);
        for _ in 0..count {
            bag.push(idx);
        }
    }
    bag
}

/// Pre-computed rotated features for all tile types × 4 rotations.
/// Indexed by tile type u8 index → [rotation_index (0-3)].
/// Returns a borrowed slice — zero allocation on the hot path.
pub static ROTATED_FEATURES: Lazy<Vec<[Vec<TileFeature>; 4]>> = Lazy::new(|| {
    let mut table: Vec<[Vec<TileFeature>; 4]> = Vec::with_capacity(24);
    for _ in 0..24 {
        table.push([vec![], vec![], vec![], vec![]]);
    }
    for tile in TILE_CATALOG.iter() {
        let idx = tile_type_to_index(&tile.tile_type_id) as usize;
        for rot_idx in 0..4usize {
            let rotation = rot_idx as u32 * 90;
            if rotation == 0 {
                table[idx][0] = tile.features.clone();
            } else {
                table[idx][rot_idx] = tile.features
                    .iter()
                    .map(|feat| TileFeature {
                        feature_type: feat.feature_type,
                        edges: feat.edges.iter()
                            .map(|e| rotate_compound_edge(e, rotation))
                            .collect(),
                        has_pennant: feat.has_pennant,
                        is_monastery: feat.is_monastery,
                        meeple_spots: feat.meeple_spots.iter()
                            .map(|s| rotate_meeple_spot(s, rotation))
                            .collect(),
                        adjacent_cities: feat.adjacent_cities.iter()
                            .map(|s| rotate_meeple_spot(s, rotation))
                            .collect(),
                    })
                    .collect();
            }
        }
    }
    table
});

/// Get the features of a tile with rotation applied.
/// Returns a borrowed slice from the pre-computed table — zero allocation.
#[inline]
pub fn get_rotated_features(tile_type_idx: u8, rotation: u32) -> &'static [TileFeature] {
    let rot_idx = ((rotation / 90) % 4) as usize;
    &ROTATED_FEATURES[tile_type_idx as usize][rot_idx]
}

/// String-based wrapper for non-hot-path callers.
pub fn get_rotated_features_by_name(tile_type_id: &str, rotation: u32) -> &'static [TileFeature] {
    get_rotated_features(tile_type_to_index(tile_type_id), rotation)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tile_catalog_count() {
        assert_eq!(TILE_CATALOG.len(), 24);
    }

    #[test]
    fn test_total_tiles() {
        let total: u32 = TILE_CATALOG.iter().map(|t| t.count).sum();
        assert_eq!(total, 72);
    }

    #[test]
    fn test_tile_bag_size() {
        let bag = build_tile_bag(None);
        assert_eq!(bag.len(), 71); // 72 - 1 starting tile
    }

    #[test]
    fn test_tile_lookup() {
        assert!(TILE_LOOKUP.contains_key("A"));
        assert!(TILE_LOOKUP.contains_key("X"));
        assert_eq!(TILE_LOOKUP["D"].tile_type_id, "D");
    }

    #[test]
    fn test_starting_tile_is_d() {
        let tile = &TILE_LOOKUP[STARTING_TILE_ID];
        assert_eq!(tile.edges[0], EdgeType::City);  // N
        assert_eq!(tile.edges[1], EdgeType::Road);   // E
        assert_eq!(tile.edges[2], EdgeType::Field);  // S
        assert_eq!(tile.edges[3], EdgeType::Road);   // W
    }

    #[test]
    fn test_rotated_features_d_90() {
        let features = get_rotated_features(tile_type_to_index("D"), 90);
        // D rotated 90°: city moves from N to E
        let city_feat = features.iter().find(|f| f.feature_type == FeatureType::City).unwrap();
        assert!(city_feat.edges.contains(&"E".to_string()));
        assert!(city_feat.meeple_spots.contains(&"city_E".to_string()));
    }
}
