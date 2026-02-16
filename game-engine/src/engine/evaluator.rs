//! Generic evaluation function trait for MCTS leaf evaluation.

use crate::engine::models::*;
use crate::engine::plugin::GamePlugin;

/// Evaluation function type: (game_data, phase, player_id, players, plugin) -> f64 in [0, 1]
pub type EvalFn = Box<dyn Fn(&serde_json::Value, &Phase, &str, &[Player], &dyn GamePlugin) -> f64 + Send + Sync>;

/// Default evaluation: sigmoid of score differential.
pub fn default_eval_fn(
    game_data: &serde_json::Value,
    _phase: &Phase,
    player_id: &str,
    _players: &[Player],
    _plugin: &dyn GamePlugin,
) -> f64 {
    let scores = &game_data["scores"];
    let my_score = scores.get(player_id).and_then(|v| v.as_f64()).unwrap_or(0.0);

    let mut max_opp = 0.0f64;
    let mut has_opp = false;
    if let Some(obj) = scores.as_object() {
        for (pid, v) in obj {
            if pid != player_id {
                let s = v.as_f64().unwrap_or(0.0);
                if !has_opp || s > max_opp {
                    max_opp = s;
                    has_opp = true;
                }
            }
        }
    }

    if !has_opp {
        return 0.5;
    }

    let diff = my_score - max_opp;
    1.0 / (1.0 + (-diff / 20.0_f64).exp())
}
