//! Domain types for Ein Stein Dojo.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// State of a hex cell based on kite ownership.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum HexState {
    Empty,
    Open,     // some kites filled, all same player
    Complete, // all 6 kites filled by one player
    Conflict, // kites filled by different players
}

/// A placed piece, recorded for history/rendering.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlacedPiece {
    pub player_id: String,
    pub orientation: u8,
    pub anchor_q: i32,
    pub anchor_r: i32,
}

/// The board state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Board {
    pub kite_owners: HashMap<String, String>,   // "q,r:k" -> player_id
    pub hex_states: HashMap<String, HexState>,  // "q,r" -> HexState
    pub placed_pieces: Vec<PlacedPiece>,
    #[serde(default)]
    pub hex_marks: HashMap<String, String>,     // "q,r" -> player_id (mark owner)
}

impl Board {
    pub fn new() -> Self {
        Self {
            kite_owners: HashMap::new(),
            hex_states: HashMap::new(),
            placed_pieces: Vec::new(),
            hex_marks: HashMap::new(),
        }
    }
}

/// Full Ein Stein Dojo game state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EinsteinDojoState {
    pub board: Board,
    pub tiles_remaining: HashMap<String, i32>,
    #[serde(default)]
    pub marks_remaining: HashMap<String, i32>,
    pub scores: HashMap<String, i64>,
    pub current_player_index: usize,
    /// Hex key ("q,r") of the main conflict. None until the first conflict is created.
    #[serde(default)]
    pub main_conflict: Option<String>,
}

impl EinsteinDojoState {
    pub fn float_scores(&self) -> HashMap<String, f64> {
        self.scores
            .iter()
            .map(|(k, v)| (k.clone(), *v as f64))
            .collect()
    }
}
