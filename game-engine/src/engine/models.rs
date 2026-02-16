//! Core engine data types mirroring backend/src/engine/models.py

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

pub type PlayerId = String;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Player {
    pub player_id: PlayerId,
    pub display_name: String,
    #[serde(default)]
    pub seat_index: i32,
    #[serde(default)]
    pub is_bot: bool,
    #[serde(default)]
    pub bot_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameConfig {
    #[serde(default)]
    pub options: serde_json::Value,
    pub random_seed: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ConcurrentMode {
    Sequential,
    CommitReveal,
    TimeWindow,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExpectedAction {
    pub player_id: PlayerId,
    pub action_type: String,
    #[serde(default)]
    pub constraints: HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub timeout_ms: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Phase {
    pub name: String,
    #[serde(default)]
    pub concurrent_mode: Option<ConcurrentMode>,
    #[serde(default)]
    pub expected_actions: Vec<ExpectedAction>,
    #[serde(default)]
    pub auto_resolve: bool,
    #[serde(default = "default_metadata")]
    pub metadata: serde_json::Value,
}

fn default_metadata() -> serde_json::Value {
    serde_json::json!({})
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Action {
    pub action_type: String,
    pub player_id: PlayerId,
    #[serde(default)]
    pub payload: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    pub event_type: String,
    #[serde(default)]
    pub player_id: Option<PlayerId>,
    #[serde(default)]
    pub payload: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameResult {
    pub winners: Vec<PlayerId>,
    pub final_scores: HashMap<String, f64>,
    #[serde(default = "default_reason")]
    pub reason: String,
    #[serde(default)]
    pub details: HashMap<String, serde_json::Value>,
}

fn default_reason() -> String {
    "normal".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransitionResult {
    pub game_data: serde_json::Value,
    pub events: Vec<Event>,
    pub next_phase: Phase,
    #[serde(default)]
    pub scores: HashMap<String, f64>,
    #[serde(default)]
    pub game_over: Option<GameResult>,
}
