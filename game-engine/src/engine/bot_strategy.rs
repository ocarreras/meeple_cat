//! Bot strategy trait and implementations.
//! Mirrors backend/src/engine/bot_strategy.py.

use rand::seq::SliceRandom;

use crate::engine::mcts::{mcts_search, MctsParams};
use crate::engine::models::*;
use crate::engine::plugin::GamePlugin;

/// A bot strategy selects an action payload given the current game state.
pub trait BotStrategy: Send + Sync {
    fn choose_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        plugin: &dyn GamePlugin,
        players: &[Player],
    ) -> serde_json::Value;
}

/// Picks a uniformly random valid action.
pub struct RandomStrategy;

impl BotStrategy for RandomStrategy {
    fn choose_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        plugin: &dyn GamePlugin,
        _players: &[Player],
    ) -> serde_json::Value {
        let valid = plugin.get_valid_actions(game_data, phase, player_id);
        if valid.is_empty() {
            return serde_json::json!({});
        }
        let mut rng = rand::thread_rng();
        valid.choose(&mut rng).cloned().unwrap_or(serde_json::json!({}))
    }
}

/// Wraps the MCTS engine as a BotStrategy.
pub struct MctsStrategy {
    pub params: MctsParams,
}

impl MctsStrategy {
    pub fn new(params: MctsParams) -> Self {
        Self { params }
    }
}

impl Default for MctsStrategy {
    fn default() -> Self {
        Self { params: MctsParams::default() }
    }
}

impl BotStrategy for MctsStrategy {
    fn choose_action(
        &self,
        game_data: &serde_json::Value,
        phase: &Phase,
        player_id: &str,
        plugin: &dyn GamePlugin,
        players: &[Player],
    ) -> serde_json::Value {
        mcts_search(game_data, phase, player_id, plugin, players, &self.params, None)
    }
}
