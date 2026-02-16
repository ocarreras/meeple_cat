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
    pub edges: HashMap<String, EdgeType>,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlacedTile {
    pub tile_type_id: String,
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
    pub tile_bag: Vec<String>,
    pub current_tile: Option<String>,
    pub last_placed_position: Option<String>,
    pub features: HashMap<String, Feature>,
    pub tile_feature_map: HashMap<String, HashMap<String, String>>,
    pub meeple_supply: HashMap<String, i32>,
    pub scores: HashMap<String, i64>,
    pub current_player_index: usize,
    #[serde(default)]
    pub rng_state: Option<u64>,
    #[serde(default)]
    pub forfeited_players: Vec<String>,
    #[serde(default)]
    pub end_game_breakdown: Option<serde_json::Value>,
}

impl CarcassonneState {
    pub fn from_json(value: &serde_json::Value) -> Result<Self, serde_json::Error> {
        serde_json::from_value(value.clone())
    }

    pub fn to_json(&self) -> serde_json::Value {
        serde_json::to_value(self).expect("CarcassonneState serialization should not fail")
    }

    /// Scores as f64 for compatibility with engine models.
    pub fn float_scores(&self) -> std::collections::HashMap<String, f64> {
        self.scores.iter().map(|(k, v)| (k.clone(), *v as f64)).collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Board {
    pub tiles: HashMap<String, PlacedTile>,
    pub open_positions: Vec<String>,
}

// --- Rotation helpers ---

/// Rotate edge types clockwise by rotation degrees (0, 90, 180, 270).
pub fn rotate_edges(edges: &HashMap<String, EdgeType>, rotation: u32) -> HashMap<String, EdgeType> {
    let steps = ((rotation / 90) % 4) as usize;
    if steps == 0 {
        return edges.clone();
    }
    let mut rotated = HashMap::with_capacity(4);
    for (i, d) in DIRECTIONS.iter().enumerate() {
        let source = DIRECTIONS[(i + 4 - steps) % 4];
        if let Some(edge_type) = edges.get(source) {
            rotated.insert(d.to_string(), *edge_type);
        }
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
        let edges: HashMap<String, EdgeType> = [
            ("N".into(), EdgeType::City),
            ("E".into(), EdgeType::Road),
            ("S".into(), EdgeType::Field),
            ("W".into(), EdgeType::Road),
        ]
        .into_iter()
        .collect();

        let rotated = rotate_edges(&edges, 90);
        assert_eq!(rotated["N"], EdgeType::Road);  // W→N
        assert_eq!(rotated["E"], EdgeType::City);   // N→E
        assert_eq!(rotated["S"], EdgeType::Road);   // E→S
        assert_eq!(rotated["W"], EdgeType::Field);  // S→W
    }

    #[test]
    fn test_all_surrounding() {
        let pos = Position::new(0, 0);
        let surrounding = pos.all_surrounding();
        assert_eq!(surrounding.len(), 8);
    }
}
