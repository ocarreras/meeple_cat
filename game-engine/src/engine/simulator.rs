//! Synchronous game simulator — advances game state through auto-resolve phases.
//! Used by MCTS and Arena. Mirrors backend/src/engine/game_simulator.py.

use std::collections::HashMap;

use crate::engine::models::*;
use crate::engine::plugin::GamePlugin;

/// Mutable game state for synchronous simulation.
#[derive(Clone)]
pub struct SimulationState {
    pub game_data: serde_json::Value,
    pub phase: Phase,
    pub players: Vec<Player>,
    pub scores: HashMap<String, f64>,
    pub game_over: Option<GameResult>,
}

/// Apply an action and auto-resolve all subsequent auto-resolve phases.
/// Mutates `state` in place.
pub fn apply_action_and_resolve(
    plugin: &dyn GamePlugin,
    state: &mut SimulationState,
    action: &Action,
) {
    let result = plugin.apply_action(&state.game_data, &state.phase, action, &state.players);
    state.game_data = result.game_data;
    state.phase = result.next_phase;
    if !result.scores.is_empty() {
        state.scores = result.scores;
    }
    state.game_over = result.game_over;

    if state.game_over.is_some() {
        return;
    }

    // Auto-resolve loop
    let mut max_auto = 50;
    while state.phase.auto_resolve && state.game_over.is_none() && max_auto > 0 {
        max_auto -= 1;

        let pid = phase_player_id(&state.phase, &state.players);
        let synthetic = Action {
            action_type: state.phase.name.clone(),
            player_id: pid,
            payload: serde_json::json!({}),
        };

        let result = plugin.apply_action(
            &state.game_data,
            &state.phase,
            &synthetic,
            &state.players,
        );
        state.game_data = result.game_data;
        state.phase = result.next_phase;
        if !result.scores.is_empty() {
            state.scores = result.scores;
        }
        state.game_over = result.game_over;
    }
}

/// Extract the acting player from a phase, falling back to first player.
pub fn phase_player_id(phase: &Phase, players: &[Player]) -> PlayerId {
    if !phase.expected_actions.is_empty() {
        return phase.expected_actions[0].player_id.clone();
    }
    if let Some(pi) = phase.metadata.get("player_index").and_then(|v| v.as_u64()) {
        let idx = pi as usize;
        if idx < players.len() {
            return players[idx].player_id.clone();
        }
    }
    if !players.is_empty() {
        players[0].player_id.clone()
    } else {
        "system".into()
    }
}
