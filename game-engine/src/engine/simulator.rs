//! Synchronous game simulator — advances game state through auto-resolve phases.
//! Used by MCTS and Arena. Mirrors backend/src/engine/game_simulator.py.

use std::collections::HashMap;

use crate::engine::models::*;
use crate::engine::plugin::TypedGamePlugin;

/// Mutable game state for synchronous simulation (typed, no JSON).
#[derive(Clone)]
pub struct SimulationState<S: Clone> {
    pub state: S,
    pub phase: Phase,
    pub players: Vec<Player>,
    pub scores: HashMap<String, f64>,
    pub game_over: Option<GameResult>,
}

/// Apply an action and auto-resolve all subsequent auto-resolve phases.
/// Mutates `sim` in place.
pub fn apply_action_and_resolve<P: TypedGamePlugin>(
    plugin: &P,
    sim: &mut SimulationState<P::State>,
    action: &Action,
) {
    let result = plugin.apply_action(&sim.state, &sim.phase, action, &sim.players);
    sim.state = result.state;
    sim.phase = result.next_phase;
    if !result.scores.is_empty() {
        sim.scores = result.scores;
    }
    sim.game_over = result.game_over;

    if sim.game_over.is_some() {
        return;
    }

    let mut max_auto = 50;
    while sim.phase.auto_resolve && sim.game_over.is_none() && max_auto > 0 {
        max_auto -= 1;

        let pid = phase_player_id(&sim.phase, &sim.players);
        let synthetic = Action {
            action_type: sim.phase.name.clone(),
            player_id: pid,
            payload: serde_json::json!({}),
        };

        let result = plugin.apply_action(&sim.state, &sim.phase, &synthetic, &sim.players);
        sim.state = result.state;
        sim.phase = result.next_phase;
        if !result.scores.is_empty() {
            sim.scores = result.scores;
        }
        sim.game_over = result.game_over;
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
