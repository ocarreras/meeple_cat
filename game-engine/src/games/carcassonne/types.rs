//! Carcassonne core types — mirrors backend/src/games/carcassonne/types.py

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EdgeType {
    City,
    Road,
    Field,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FeatureType {
    City,
    Road,
    Field,
    Monastery,
}

pub const DIRECTIONS: [&str; 4] = ["N", "E", "S", "W"];

pub fn opposite_direction(dir: &str) -> &'static str {
    match dir {
        "N" => "S",
        "E" => "W",
        "S" => "N",
        "W" => "E",
        _ => panic!("Invalid direction: {dir}"),
    }
}

pub fn direction_index(dir: &str) -> usize {
    match dir {
        "N" => 0,
        "E" => 1,
        "S" => 2,
        "W" => 3,
        _ => panic!("Invalid direction: {dir}"),
    }
}

// --- Tile type ID conversion ---

const TILE_TYPE_STRINGS: [&str; 24] = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
    "U", "V", "W", "X",
];

/// Convert tile type ID string (e.g. "A") to u8 index (0–23).
#[inline]
pub fn tile_type_to_index(id: &str) -> u8 {
    id.as_bytes()[0] - b'A'
}

/// Convert tile type u8 index (0–23) to string ID (e.g. "A").
#[inline]
pub fn tile_index_to_type(idx: u8) -> &'static str {
    TILE_TYPE_STRINGS[idx as usize]
}

// --- Tile definitions ---

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TileFeature {
    pub feature_type: FeatureType,
    pub edges: Vec<String>,
    #[serde(default)]
    pub has_pennant: bool,
    #[serde(default)]
    pub is_monastery: bool,
    pub meeple_spots: Vec<String>,
    #[serde(default)]
    pub adjacent_cities: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TileDefinition {
    pub tile_type_id: String,
    /// Edges indexed by direction: N=0, E=1, S=2, W=3.
    pub edges: [EdgeType; 4],
    pub features: Vec<TileFeature>,
    pub count: u32,
    pub image_id: String,
    #[serde(default)]
    pub internal_connections: Vec<Vec<String>>,
}

// --- Position ---

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Position {
    pub x: i32,
    pub y: i32,
}

impl Position {
    pub fn new(x: i32, y: i32) -> Self {
        Self { x, y }
    }

    pub fn to_key(self) -> String {
        format!("{},{}", self.x, self.y)
    }

    pub fn from_key(key: &str) -> Self {
        let mut parts = key.split(',');
        let x: i32 = parts.next().unwrap().parse().unwrap();
        let y: i32 = parts.next().unwrap().parse().unwrap();
        Self { x, y }
    }

    pub fn neighbor(self, direction: &str) -> Self {
        match direction {
            "N" => Self::new(self.x, self.y + 1),
            "E" => Self::new(self.x + 1, self.y),
            "S" => Self::new(self.x, self.y - 1),
            "W" => Self::new(self.x - 1, self.y),
            _ => panic!("Invalid direction: {direction}"),
        }
    }

    /// All 8 surrounding positions (for monastery completion check).
    pub fn all_surrounding(self) -> Vec<Self> {
        let mut result = Vec::with_capacity(8);
        for dx in -1..=1 {
            for dy in -1..=1 {
                if dx == 0 && dy == 0 {
                    continue;
                }
                result.push(Self::new(self.x + dx, self.y + dy));
            }
        }
        result
    }
}

// --- Board-level types ---

/// A tile placed on the board. Uses u8 tile type index and u32 rotation
/// for Copy semantics and cheap cloning.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PlacedTile {
    pub tile_type_id: u8,
    pub rotation: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlacedMeeple {
    pub player_id: String,
    pub position: String,
    pub spot: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Feature {
    pub feature_id: String,
    pub feature_type: FeatureType,
    pub tiles: Vec<String>,
    #[serde(default)]
    pub meeples: Vec<PlacedMeeple>,
    #[serde(default)]
    pub is_complete: bool,
    #[serde(default)]
    pub pennants: u32,
    #[serde(default)]
    pub open_edges: Vec<[String; 2]>,
    #[serde(default, rename = "_merged_from")]
    pub merged_from: Vec<String>,
}

/// Full Carcassonne game state (strongly typed, serialized to/from JSON at gRPC boundary).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CarcassonneState {
    pub board: Board,
    #[serde(with = "serde_tile_bag")]
    pub tile_bag: Vec<u8>,
    #[serde(with = "serde_current_tile")]
    pub current_tile: Option<u8>,
    pub last_placed_position: Option<String>,
    pub features: HashMap<String, Feature>,
    pub tile_feature_map: HashMap<String, HashMap<String, String>>,
    pub meeple_supply: HashMap<String, i32>,
    pub scores: HashMap<String, i64>,
    pub current_player_index: usize,
    #[serde(default)]
    pub rng_state: serde_json::Value,
    #[serde(default)]
    pub forfeited_players: Vec<String>,
    #[serde(default)]
    pub end_game_breakdown: Option<serde_json::Value>,
    /// Sequential counter for generating feature IDs (avoids UUID overhead in MCTS).
    #[serde(default)]
    pub next_feature_id: u64,
    /// Redirect table for merged feature IDs: old_id -> surviving_id.
    #[serde(default)]
    pub feature_redirects: HashMap<String, String>,
}

impl CarcassonneState {
    pub fn to_json(&self) -> serde_json::Value {
        serde_json::to_value(self).expect("CarcassonneState serialization should not fail")
    }

    /// Scores as f64 for compatibility with engine models.
    pub fn float_scores(&self) -> std::collections::HashMap<String, f64> {
        self.scores.iter().map(|(k, v)| (k.clone(), *v as f64)).collect()
    }
}

/// Board with (i32, i32) tuple keys for zero-allocation neighbor lookups.
/// Custom Serialize/Deserialize maintains "x,y" string key JSON format.
#[derive(Debug, Clone)]
pub struct Board {
    pub tiles: HashMap<(i32, i32), PlacedTile>,
    pub open_positions: Vec<(i32, i32)>,
}

// --- Board custom serde ---

#[derive(Serialize, Deserialize)]
struct PlacedTileSerde {
    tile_type_id: String,
    rotation: u32,
}

#[derive(Serialize, Deserialize)]
struct BoardSerde {
    tiles: HashMap<String, PlacedTileSerde>,
    open_positions: Vec<String>,
}

impl Serialize for Board {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let serde_board = BoardSerde {
            tiles: self.tiles.iter().map(|(&(x, y), tile)| {
                (
                    format!("{},{}", x, y),
                    PlacedTileSerde {
                        tile_type_id: tile_index_to_type(tile.tile_type_id).to_string(),
                        rotation: tile.rotation,
                    },
                )
            }).collect(),
            open_positions: self.open_positions.iter()
                .map(|(x, y)| format!("{},{}", x, y))
                .collect(),
        };
        serde_board.serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for Board {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let serde_board = BoardSerde::deserialize(deserializer)?;
        Ok(Board {
            tiles: serde_board.tiles.into_iter().map(|(key, tile)| {
                let pos = Position::from_key(&key);
                (
                    (pos.x, pos.y),
                    PlacedTile {
                        tile_type_id: tile_type_to_index(&tile.tile_type_id),
                        rotation: tile.rotation,
                    },
                )
            }).collect(),
            open_positions: serde_board.open_positions.into_iter().map(|key| {
                let pos = Position::from_key(&key);
                (pos.x, pos.y)
            }).collect(),
        })
    }
}

// --- Serde helpers for tile_bag (Vec<u8> ↔ Vec<String>) ---

mod serde_tile_bag {
    use super::tile_index_to_type;

    pub fn serialize<S: serde::Serializer>(bag: &[u8], serializer: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeSeq;
        let mut seq = serializer.serialize_seq(Some(bag.len()))?;
        for &idx in bag {
            seq.serialize_element(tile_index_to_type(idx))?;
        }
        seq.end()
    }

    pub fn deserialize<'de, D: serde::Deserializer<'de>>(deserializer: D) -> Result<Vec<u8>, D::Error> {
        use serde::Deserialize;
        let strings: Vec<String> = Vec::deserialize(deserializer)?;
        Ok(strings.iter().map(|s| super::tile_type_to_index(s)).collect())
    }
}

// --- Serde helpers for current_tile (Option<u8> ↔ Option<String>) ---

mod serde_current_tile {
    use super::tile_index_to_type;

    pub fn serialize<S: serde::Serializer>(tile: &Option<u8>, serializer: S) -> Result<S::Ok, S::Error> {
        match tile {
            Some(idx) => serializer.serialize_some(tile_index_to_type(*idx)),
            None => serializer.serialize_none(),
        }
    }

    pub fn deserialize<'de, D: serde::Deserializer<'de>>(deserializer: D) -> Result<Option<u8>, D::Error> {
        use serde::Deserialize;
        let opt: Option<String> = Option::deserialize(deserializer)?;
        Ok(opt.map(|s| super::tile_type_to_index(&s)))
    }
}

// --- Rotation helpers ---

/// Rotate edge types clockwise by rotation degrees (0, 90, 180, 270).
pub fn rotate_edges(edges: &[EdgeType; 4], rotation: u32) -> [EdgeType; 4] {
    let steps = ((rotation / 90) % 4) as usize;
    if steps == 0 {
        return *edges;
    }
    let mut rotated = [EdgeType::Field; 4];
    for i in 0..4 {
        let source = (i + 4 - steps) % 4;
        rotated[i] = edges[source];
    }
    rotated
}

/// Rotate a single direction clockwise.
pub fn rotate_direction(direction: &str, rotation: u32) -> &'static str {
    let steps = ((rotation / 90) % 4) as usize;
    let idx = direction_index(direction);
    DIRECTIONS[(idx + steps) % 4]
}

/// Rotate a compound edge like "E:N" → both direction and side.
pub fn rotate_compound_edge(edge: &str, rotation: u32) -> String {
    if let Some((direction, side)) = edge.split_once(':') {
        format!(
            "{}:{}",
            rotate_direction(direction, rotation),
            rotate_direction(side, rotation)
        )
    } else {
        rotate_direction(edge, rotation).to_string()
    }
}

/// Rotate a meeple spot name by rotating direction components.
/// e.g. "city_N" with 90° → "city_E", "road_EW" with 90° → "road_NS"
pub fn rotate_meeple_spot(spot: &str, rotation: u32) -> String {
    if rotation == 0 {
        return spot.to_string();
    }

    let parts: Vec<&str> = spot.split('_').collect();
    if parts.len() < 2 {
        return spot.to_string(); // e.g. "monastery"
    }

    let prefix = parts[0];
    let direction_part = parts[1];
    let suffix = if parts.len() > 2 {
        Some(parts[2..].join("_"))
    } else {
        None
    };

    // Rotate each direction letter
    let mut rotated_chars: Vec<(usize, char)> = Vec::new();
    let dir_order = |c: char| -> usize {
        match c {
            'N' => 0,
            'E' => 1,
            'S' => 2,
            'W' => 3,
            _ => 99,
        }
    };

    for ch in direction_part.chars() {
        if "NESW".contains(ch) {
            let rotated = rotate_direction(&ch.to_string(), rotation);
            let rotated_ch = rotated.chars().next().unwrap();
            rotated_chars.push((dir_order(rotated_ch), rotated_ch));
        } else {
            rotated_chars.push((dir_order(ch), ch));
        }
    }

    // Sort by canonical direction order (N, E, S, W)
    rotated_chars.sort_by_key(|(order, _)| *order);
    let rotated_dirs: String = rotated_chars.into_iter().map(|(_, c)| c).collect();

    match suffix {
        Some(s) => format!("{prefix}_{rotated_dirs}_{s}"),
        None => format!("{prefix}_{rotated_dirs}"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_position_to_from_key() {
        let pos = Position::new(3, -1);
        assert_eq!(pos.to_key(), "3,-1");
        assert_eq!(Position::from_key("3,-1"), pos);
    }

    #[test]
    fn test_position_neighbor() {
        let pos = Position::new(0, 0);
        assert_eq!(pos.neighbor("N"), Position::new(0, 1));
        assert_eq!(pos.neighbor("E"), Position::new(1, 0));
        assert_eq!(pos.neighbor("S"), Position::new(0, -1));
        assert_eq!(pos.neighbor("W"), Position::new(-1, 0));
    }

    #[test]
    fn test_rotate_direction() {
        assert_eq!(rotate_direction("N", 0), "N");
        assert_eq!(rotate_direction("N", 90), "E");
        assert_eq!(rotate_direction("N", 180), "S");
        assert_eq!(rotate_direction("N", 270), "W");
        assert_eq!(rotate_direction("E", 90), "S");
    }

    #[test]
    fn test_rotate_compound_edge() {
        assert_eq!(rotate_compound_edge("E:N", 90), "S:E");
        assert_eq!(rotate_compound_edge("N", 90), "E");
    }

    #[test]
    fn test_rotate_meeple_spot() {
        assert_eq!(rotate_meeple_spot("city_N", 90), "city_E");
        assert_eq!(rotate_meeple_spot("road_EW", 90), "road_NS");
        assert_eq!(rotate_meeple_spot("field_NE", 90), "field_ES");
        assert_eq!(rotate_meeple_spot("monastery", 90), "monastery");
    }

    #[test]
    fn test_rotate_edges() {
        // N=City, E=Road, S=Field, W=Road
        let edges = [EdgeType::City, EdgeType::Road, EdgeType::Field, EdgeType::Road];

        let rotated = rotate_edges(&edges, 90);
        assert_eq!(rotated[0], EdgeType::Road);  // W→N
        assert_eq!(rotated[1], EdgeType::City);   // N→E
        assert_eq!(rotated[2], EdgeType::Road);   // E→S
        assert_eq!(rotated[3], EdgeType::Field);  // S→W
    }

    #[test]
    fn test_all_surrounding() {
        let pos = Position::new(0, 0);
        let surrounding = pos.all_surrounding();
        assert_eq!(surrounding.len(), 8);
    }

    #[test]
    fn test_tile_type_roundtrip() {
        for idx in 0..24u8 {
            let s = tile_index_to_type(idx);
            assert_eq!(tile_type_to_index(s), idx);
        }
    }
}
