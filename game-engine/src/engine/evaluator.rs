//! Generic evaluation function for MCTS leaf evaluation.

use crate::engine::plugin::TypedGamePlugin;

/// Default evaluation: sigmoid of score differential using typed state.
pub fn default_eval<P: TypedGamePlugin>(
    plugin: &P,
    state: &P::State,
    player_id: &str,
) -> f64 {
    let scores = plugin.get_scores(state);
    let my_score = scores.get(player_id).copied().unwrap_or(0.0);

    let mut max_opp = 0.0f64;
    let mut has_opp = false;
    for (pid, &s) in &scores {
        if pid != player_id {
            if !has_opp || s > max_opp {
                max_opp = s;
                has_opp = true;
            }
        }
    }

    if !has_opp {
        return 0.5;
    }

    let diff = my_score - max_opp;
    1.0 / (1.0 + (-diff / 20.0_f64).exp())
}
