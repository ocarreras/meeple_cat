//! Bot strategy trait and implementations.
//! Mirrors backend/src/engine/bot_strategy.py.

use rand::seq::SliceRandom;

use crate::engine::mcts::{mcts_search, MctsParams};
use crate::engine::models::*;
use crate::engine::plugin::TypedGamePlugin;

/// A bot strategy selects an action payload given the current typed game state.
pub trait BotStrategy<P: TypedGamePlugin>: Send + Sync {
    fn choose_action(
        &self,
        state: &P::State,
        phase: &Phase,
        player_id: &str,
        plugin: &P,
        players: &[Player],
    ) -> serde_json::Value;
}

/// Picks a uniformly random valid action.
pub struct RandomStrategy;

impl<P: TypedGamePlugin> BotStrategy<P> for RandomStrategy {
    fn choose_action(
        &self,
        state: &P::State,
        phase: &Phase,
        player_id: &str,
        plugin: &P,
        _players: &[Player],
    ) -> serde_json::Value {
        let valid = plugin.get_valid_actions(state, phase, player_id);
        if valid.is_empty() {
            return serde_json::json!({});
        }
        let mut rng = rand::thread_rng();
        valid.choose(&mut rng).cloned().unwrap_or(serde_json::json!({}))
    }
}

/// Wraps the MCTS engine as a BotStrategy.
pub struct MctsStrategy<P: TypedGamePlugin> {
    pub params: MctsParams,
    pub eval_fn: Option<Box<dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64 + Send + Sync>>,
}

impl<P: TypedGamePlugin> MctsStrategy<P> {
    #[allow(dead_code)]
    pub fn new(params: MctsParams) -> Self {
        Self { params, eval_fn: None }
    }

    #[allow(dead_code)]
    pub fn with_eval(params: MctsParams, eval_fn: Box<dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64 + Send + Sync>) -> Self {
        Self { params, eval_fn: Some(eval_fn) }
    }
}

impl<P: TypedGamePlugin> BotStrategy<P> for MctsStrategy<P> {
    fn choose_action(
        &self,
        state: &P::State,
        phase: &Phase,
        player_id: &str,
        plugin: &P,
        players: &[Player],
    ) -> serde_json::Value {
        let eval_ref: Option<&(dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64 + Sync)> =
            self.eval_fn.as_ref().map(|f| f.as_ref() as &(dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64 + Sync));
        let (action, _iterations) = mcts_search(state, phase, player_id, plugin, players, &self.params, eval_ref);
        action
    }
}
