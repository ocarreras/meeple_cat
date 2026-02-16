//! Bot strategy trait and implementations.
//! Mirrors backend/src/engine/bot_strategy.py.

use rand::seq::SliceRandom;

use crate::engine::mcts::{mcts_search, mcts_search_typed, MctsParams};
use crate::engine::models::*;
use crate::engine::plugin::{GamePlugin, TypedGamePlugin};

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

// ================================================================== //
//  Typed bot strategies — zero-JSON hot path
// ================================================================== //

/// Typed bot strategy: selects an action from typed game state.
pub trait TypedBotStrategy<P: TypedGamePlugin>: Send + Sync {
    fn choose_action_typed(
        &self,
        state: &P::State,
        phase: &Phase,
        player_id: &str,
        plugin: &P,
        players: &[Player],
    ) -> serde_json::Value;
}

/// Typed random strategy — picks a uniformly random valid action.
pub struct TypedRandomStrategy;

impl<P: TypedGamePlugin> TypedBotStrategy<P> for TypedRandomStrategy {
    fn choose_action_typed(
        &self,
        state: &P::State,
        phase: &Phase,
        player_id: &str,
        plugin: &P,
        _players: &[Player],
    ) -> serde_json::Value {
        let valid = plugin.get_valid_actions_typed(state, phase, player_id);
        if valid.is_empty() {
            return serde_json::json!({});
        }
        let mut rng = rand::thread_rng();
        valid.choose(&mut rng).cloned().unwrap_or(serde_json::json!({}))
    }
}

/// Typed MCTS strategy — uses typed MCTS search.
pub struct TypedMctsStrategy<P: TypedGamePlugin> {
    pub params: MctsParams,
    pub eval_fn: Option<Box<dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64 + Send + Sync>>,
}

impl<P: TypedGamePlugin> TypedBotStrategy<P> for TypedMctsStrategy<P> {
    fn choose_action_typed(
        &self,
        state: &P::State,
        phase: &Phase,
        player_id: &str,
        plugin: &P,
        players: &[Player],
    ) -> serde_json::Value {
        let game_data = plugin.encode_state(state);
        let eval_ref: Option<&dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64> =
            self.eval_fn.as_ref().map(|f| f.as_ref() as &dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64);
        mcts_search_typed(&game_data, phase, player_id, plugin, players, &self.params, eval_ref)
    }
}
