//! Heuristic evaluation function for Carcassonne MCTS.
//! Returns a value in [0, 1] representing how good the position is for the player.
//! Mirrors backend/src/games/carcassonne/evaluator.py.

use crate::engine::models::*;
use crate::games::carcassonne::scoring::get_adjacent_completed_cities;
use crate::games::carcassonne::types::{CarcassonneState, FeatureType, PlacedMeeple, Position};

/// Tunable parameters for the Carcassonne heuristic evaluator.
#[derive(Clone, Copy)]
pub struct EvalWeights {
    pub score_base: f64,
    pub score_delta: f64,
    pub score_scale: f64,
    pub potential_base: f64,
    pub potential_delta: f64,
    pub potential_scale: f64,
    pub meeple_base: f64,
    pub meeple_delta: f64,
    pub meeple_hoard_threshold: i64,
    pub meeple_hoard_penalty: f64,
    pub meeple_hoard_progress_gate: f64,
    pub field_base: f64,
    pub field_delta: f64,
    pub field_scale: f64,
}

impl Default for EvalWeights {
    fn default() -> Self {
        DEFAULT_WEIGHTS
    }
}

pub static AGGRESSIVE_WEIGHTS: EvalWeights = EvalWeights {
    score_base: 0.45,
    score_delta: 0.10,
    score_scale: 25.0,
    potential_base: 0.30,
    potential_delta: -0.15,
    potential_scale: 15.0,
    meeple_base: 0.10,
    meeple_delta: -0.05,
    meeple_hoard_threshold: 5,
    meeple_hoard_penalty: 0.8,
    meeple_hoard_progress_gate: 0.15,
    field_base: 0.15,
    field_delta: 0.10,
    field_scale: 10.0,
};

pub static FIELD_HEAVY_WEIGHTS: EvalWeights = EvalWeights {
    score_base: 0.30,
    score_delta: 0.10,
    score_scale: 25.0,
    potential_base: 0.25,
    potential_delta: -0.10,
    potential_scale: 15.0,
    meeple_base: 0.20,
    meeple_delta: -0.05,
    meeple_hoard_threshold: 6,
    meeple_hoard_penalty: 0.8,
    meeple_hoard_progress_gate: 0.2,
    field_base: 0.25,
    field_delta: 0.15,
    field_scale: 8.0,
};

pub static DEFAULT_WEIGHTS: EvalWeights = EvalWeights {
    score_base: 0.35,
    score_delta: 0.10,
    score_scale: 25.0,
    potential_base: 0.35,
    potential_delta: -0.15,
    potential_scale: 15.0,
    meeple_base: 0.20,
    meeple_delta: -0.05,
    meeple_hoard_threshold: 6,
    meeple_hoard_penalty: 0.8,
    meeple_hoard_progress_gate: 0.2,
    field_base: 0.10,
    field_delta: 0.10,
    field_scale: 10.0,
};

pub static CONSERVATIVE_WEIGHTS: EvalWeights = EvalWeights {
    score_base: 0.30,
    score_delta: 0.10,
    score_scale: 25.0,
    potential_base: 0.25,
    potential_delta: -0.10,
    potential_scale: 15.0,
    meeple_base: 0.30,
    meeple_delta: -0.05,
    meeple_hoard_threshold: 7,
    meeple_hoard_penalty: 0.9,
    meeple_hoard_progress_gate: 0.2,
    field_base: 0.15,
    field_delta: 0.05,
    field_scale: 10.0,
};

/// Create an evaluation function parameterised by `weights`.
pub fn make_carcassonne_eval(
    weights: &'static EvalWeights,
) -> Box<dyn Fn(&CarcassonneState, &Phase, &str, &[Player]) -> f64 + Send + Sync> {
    Box::new(move |state, phase, player_id, players| {
        evaluate(state, phase, player_id, players, weights)
    })
}

fn evaluate(
    state: &CarcassonneState,
    _phase: &Phase,
    player_id: &str,
    players: &[Player],
    w: &EvalWeights,
) -> f64 {
    let tiles_remaining = state.tile_bag.len() as i64;
    let board_size = state.board.tiles.len() as i64;
    let total_tiles = board_size + tiles_remaining;
    let game_progress = 1.0 - (tiles_remaining as f64 / total_tiles.max(1) as f64);

    // 1. Score differential
    let my_score = state.scores.get(player_id).copied().unwrap_or(0) as f64;
    let mut max_opp = 0.0_f64;
    for (pid, &s) in &state.scores {
        if pid != player_id {
            let sf = s as f64;
            if sf > max_opp {
                max_opp = sf;
            }
        }
    }
    let score_diff = my_score - max_opp;
    let score_component = sigmoid(score_diff, w.score_scale);

    // 2. Incomplete feature potential
    let mut my_potential = 0.0_f64;
    let mut opp_potential = 0.0_f64;
    let mut wasted_meeple_penalty = 0.0_f64;

    for (_fid, feat) in &state.features {
        if feat.is_complete {
            continue;
        }
        if feat.feature_type == FeatureType::Field {
            continue;
        }
        if feat.meeples.is_empty() {
            continue;
        }

        let potential = raw_feature_potential(
            feat.feature_type,
            feat.tiles.len(),
            feat.open_edges.len(),
            feat.pennants as i64,
            tiles_remaining,
            state,
            &feat.tiles,
        );

        let (my_count, max_count) = meeple_counts(&feat.meeples, player_id);

        if my_count == 0 {
            opp_potential += potential;
        } else if my_count >= max_count {
            my_potential += potential;
        } else {
            opp_potential += potential;
            wasted_meeple_penalty += my_count as f64 * 1.5;
        }
    }

    let potential_diff = my_potential - opp_potential - wasted_meeple_penalty;
    let potential_component = sigmoid(potential_diff, w.potential_scale);

    // 3. Meeple economy
    let my_meeples = state.meeple_supply.get(player_id).copied().unwrap_or(0) as i64;
    let mut opp_meeple_sum = 0i64;
    let mut opp_count = 0;
    for p in players {
        if p.player_id != player_id {
            opp_meeple_sum += state.meeple_supply.get(&p.player_id).copied().unwrap_or(0) as i64;
            opp_count += 1;
        }
    }
    let avg_opp_meeples = opp_meeple_sum as f64 / opp_count.max(1) as f64;

    let mut meeple_value = (my_meeples as f64 / 7.0).min(1.0);

    if my_meeples >= w.meeple_hoard_threshold && game_progress > w.meeple_hoard_progress_gate {
        meeple_value *= w.meeple_hoard_penalty;
    }
    if my_meeples == 0 && game_progress < 0.85 {
        meeple_value *= 0.3;
    } else if my_meeples <= 1 && game_progress < 0.7 {
        meeple_value *= 0.6;
    }

    let relative = sigmoid((my_meeples as f64 - avg_opp_meeples) * 0.5, 3.0);
    let meeple_component = 0.5 * relative + 0.5 * meeple_value;

    // 4. Field scoring potential
    let my_field = estimate_field_value(state, player_id, tiles_remaining);
    let mut max_opp_field = 0.0_f64;
    for p in players {
        if p.player_id != player_id {
            let f = estimate_field_value(state, &p.player_id, tiles_remaining);
            if f > max_opp_field {
                max_opp_field = f;
            }
        }
    }
    let field_diff = my_field - max_opp_field;
    let field_component = sigmoid(field_diff, w.field_scale);

    // Weighted combination
    let score_weight = w.score_base + w.score_delta * game_progress;
    let potential_weight = w.potential_base + w.potential_delta * game_progress;
    let meeple_weight = w.meeple_base + w.meeple_delta * game_progress;
    let field_weight = w.field_base + w.field_delta * game_progress;

    let value = score_weight * score_component
        + potential_weight * potential_component
        + meeple_weight * meeple_component
        + field_weight * field_component;

    value.clamp(0.0, 1.0)
}

fn sigmoid(x: f64, scale: f64) -> f64 {
    1.0 / (1.0 + (-x / scale.max(1e-9)).exp())
}

fn completion_probability(open_edges: usize, tiles_remaining: i64) -> f64 {
    if open_edges == 0 {
        return 1.0;
    }
    if tiles_remaining <= 0 {
        return 0.0;
    }
    let ratio = tiles_remaining as f64 / (open_edges * 3).max(1) as f64;
    (ratio * 0.5).min(1.0)
}

fn meeple_counts(meeples: &[PlacedMeeple], player_id: &str) -> (i64, i64) {
    let mut counts: std::collections::HashMap<&str, i64> = std::collections::HashMap::new();
    for m in meeples {
        *counts.entry(m.player_id.as_str()).or_insert(0) += 1;
    }
    let my_count = counts.remove(player_id).unwrap_or(0);
    let max_opp = counts.values().copied().max().unwrap_or(0);
    (my_count, max_opp)
}

fn raw_feature_potential(
    feature_type: FeatureType,
    tile_count: usize,
    open_edge_count: usize,
    pennants: i64,
    tiles_remaining: i64,
    state: &CarcassonneState,
    tiles: &[String],
) -> f64 {
    match feature_type {
        FeatureType::City => {
            let cp = completion_probability(open_edge_count, tiles_remaining);
            cp * (tile_count as f64 * 2.0 + pennants as f64 * 2.0)
                + (1.0 - cp) * (tile_count as f64 + pennants as f64)
        }
        FeatureType::Road => tile_count as f64,
        FeatureType::Monastery => {
            if tiles.is_empty() {
                return 0.0;
            }
            let pos = Position::from_key(&tiles[0]);
            let neighbors: usize = pos
                .all_surrounding()
                .iter()
                .filter(|p| state.board.tiles.contains_key(&p.to_key()))
                .count();
            let cp = completion_probability(8 - neighbors, tiles_remaining);
            cp * 9.0 + (1.0 - cp) * (1.0 + neighbors as f64)
        }
        _ => 0.0,
    }
}

fn estimate_field_value(state: &CarcassonneState, player_id: &str, tiles_remaining: i64) -> f64 {
    let mut total = 0.0_f64;

    for (fid, feat) in &state.features {
        if feat.feature_type != FeatureType::Field {
            continue;
        }
        if feat.meeples.is_empty() {
            continue;
        }

        let (my_count, max_count) = meeple_counts(&feat.meeples, player_id);
        if my_count == 0 || my_count < max_count {
            continue;
        }

        // 1. Count properly adjacent completed cities (using tile definitions)
        let adj_cities = get_adjacent_completed_cities(state, feat, fid);
        total += adj_cities.len() as f64 * 3.0;

        // 2. Estimate value from nearby incomplete cities
        let completed_set: std::collections::HashSet<&str> =
            adj_cities.iter().map(|s| s.as_str()).collect();
        let mut seen_cities: std::collections::HashSet<&str> = std::collections::HashSet::new();

        for tile_pos in &feat.tiles {
            if let Some(spots) = state.tile_feature_map.get(tile_pos.as_str()) {
                for (_spot, city_fid) in spots {
                    if completed_set.contains(city_fid.as_str()) {
                        continue;
                    }
                    if seen_cities.contains(city_fid.as_str()) {
                        continue;
                    }
                    if let Some(city_feat) = state.features.get(city_fid.as_str()) {
                        if city_feat.feature_type != FeatureType::City {
                            continue;
                        }
                        if city_feat.is_complete {
                            continue; // already counted above
                        }
                        seen_cities.insert(city_fid.as_str());
                        let prob = completion_probability(city_feat.open_edges.len(), tiles_remaining);
                        if prob > 0.3 {
                            total += prob * 3.0;
                        }
                    }
                }
            }
        }
    }

    total
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::models::Player;

    #[test]
    fn test_eval_diagnostic() {
        // Load state saved by Python eval_diagnostic.py
        let json_path = "/tmp/eval_diagnostic_state.json";
        let json_str = match std::fs::read_to_string(json_path) {
            Ok(s) => s,
            Err(_) => {
                eprintln!("Skipping: run backend/eval_diagnostic.py first to generate {}", json_path);
                return;
            }
        };
        let game_data: serde_json::Value = serde_json::from_str(&json_str).unwrap();
        let state: CarcassonneState = serde_json::from_value(game_data).unwrap();
        let player_id = "p1";
        let players = vec![
            Player { player_id: "p1".into(), display_name: "P1".into(), seat_index: 0, is_bot: false, bot_id: None },
            Player { player_id: "p2".into(), display_name: "P2".into(), seat_index: 1, is_bot: false, bot_id: None },
        ];
        let w = &DEFAULT_WEIGHTS;
        let phase = Phase {
            name: "place_tile".into(),
            auto_resolve: false,
            concurrent_mode: None,
            expected_actions: vec![],
            metadata: serde_json::json!({}),
        };

        // Compute components (matching evaluator.rs evaluate fn)
        let tiles_remaining = state.tile_bag.len() as i64;
        let board_size = state.board.tiles.len() as i64;
        let total_tiles = board_size + tiles_remaining;
        let game_progress = 1.0 - (tiles_remaining as f64 / total_tiles.max(1) as f64);

        // 1. Score
        let my_score = state.scores.get(player_id).copied().unwrap_or(0) as f64;
        let mut max_opp = 0.0_f64;
        for (pid, &s) in &state.scores {
            if pid != player_id {
                let sf = s as f64;
                if sf > max_opp { max_opp = sf; }
            }
        }
        let score_diff = my_score - max_opp;
        let score_component = sigmoid(score_diff, w.score_scale);

        // 2. Potential
        let mut my_potential = 0.0_f64;
        let mut opp_potential = 0.0_f64;
        let mut wasted = 0.0_f64;
        for (_fid, feat) in &state.features {
            if feat.is_complete { continue; }
            if feat.feature_type == FeatureType::Field { continue; }
            if feat.meeples.is_empty() { continue; }
            let potential = raw_feature_potential(
                feat.feature_type, feat.tiles.len(), feat.open_edges.len(),
                feat.pennants as i64, tiles_remaining, &state, &feat.tiles,
            );
            let (my_count, max_count) = meeple_counts(&feat.meeples, player_id);
            if my_count == 0 {
                opp_potential += potential;
            } else if my_count >= max_count {
                my_potential += potential;
            } else {
                opp_potential += potential;
                wasted += my_count as f64 * 1.5;
            }
        }
        let potential_diff = my_potential - opp_potential - wasted;
        let potential_component = sigmoid(potential_diff, w.potential_scale);

        // 3. Meeple
        let my_meeples = state.meeple_supply.get(player_id).copied().unwrap_or(0) as i64;
        let mut opp_meeple_sum = 0i64;
        let mut opp_count = 0;
        for p in &players {
            if p.player_id != player_id {
                opp_meeple_sum += state.meeple_supply.get(&p.player_id).copied().unwrap_or(0) as i64;
                opp_count += 1;
            }
        }
        let avg_opp_meeples = opp_meeple_sum as f64 / opp_count.max(1) as f64;
        let mut meeple_value = (my_meeples as f64 / 7.0).min(1.0);
        if my_meeples >= w.meeple_hoard_threshold && game_progress > w.meeple_hoard_progress_gate {
            meeple_value *= w.meeple_hoard_penalty;
        }
        if my_meeples == 0 && game_progress < 0.85 {
            meeple_value *= 0.3;
        } else if my_meeples <= 1 && game_progress < 0.7 {
            meeple_value *= 0.6;
        }
        let relative = sigmoid((my_meeples as f64 - avg_opp_meeples) * 0.5, 3.0);
        let meeple_component = 0.5 * relative + 0.5 * meeple_value;

        // 4. Field
        let my_field = estimate_field_value(&state, player_id, tiles_remaining);
        let mut max_opp_field = 0.0_f64;
        for p in &players {
            if p.player_id != player_id {
                let f = estimate_field_value(&state, &p.player_id, tiles_remaining);
                if f > max_opp_field { max_opp_field = f; }
            }
        }
        let field_diff = my_field - max_opp_field;
        let field_component = sigmoid(field_diff, w.field_scale);

        // Weights
        let score_weight = w.score_base + w.score_delta * game_progress;
        let potential_weight = w.potential_base + w.potential_delta * game_progress;
        let meeple_weight = w.meeple_base + w.meeple_delta * game_progress;
        let field_weight = w.field_base + w.field_delta * game_progress;

        let value = score_weight * score_component
            + potential_weight * potential_component
            + meeple_weight * meeple_component
            + field_weight * field_component;
        let value = value.clamp(0.0, 1.0);

        // Also run the actual evaluate function for comparison
        let eval_result = evaluate(&state, &phase, player_id, &players, w);

        eprintln!("============================================================");
        eprintln!("  RUST EVALUATOR DIAGNOSTIC");
        eprintln!("============================================================");
        eprintln!("  Board tiles: {}", board_size);
        eprintln!("  Tiles remaining: {}", tiles_remaining);
        eprintln!("  Game progress: {:.4}", game_progress);
        eprintln!("  Scores: {:?}", state.scores);
        eprintln!("  Meeple supply: {:?}", state.meeple_supply);
        eprintln!("  Features: {} total", state.features.len());
        let n_complete = state.features.values().filter(|f| f.is_complete).count();
        let n_field = state.features.values().filter(|f| f.feature_type == FeatureType::Field).count();
        eprintln!("    Complete: {}, Fields: {}", n_complete, n_field);
        eprintln!();
        eprintln!("  1. Score: my={}, max_opp={}, diff={}", my_score, max_opp, score_diff);
        eprintln!("     component={:.6}  weight={:.4}", score_component, score_weight);
        eprintln!();
        eprintln!("  2. Potential: my={:.2}, opp={:.2}, wasted={:.2}", my_potential, opp_potential, wasted);
        eprintln!("     diff={:.2}  component={:.6}  weight={:.4}", potential_diff, potential_component, potential_weight);
        eprintln!();
        eprintln!("  3. Meeple: my={}, avg_opp={:.1}", my_meeples, avg_opp_meeples);
        eprintln!("     value={:.4}  relative={:.6}", meeple_value, relative);
        eprintln!("     component={:.6}  weight={:.4}", meeple_component, meeple_weight);
        eprintln!();
        eprintln!("  4. Field: my={:.2}, max_opp={:.2}, diff={:.2}", my_field, max_opp_field, field_diff);
        eprintln!("     component={:.6}  weight={:.4}", field_component, field_weight);
        eprintln!();
        eprintln!("  FINAL VALUE (manual): {:.6}", value);
        eprintln!("  FINAL VALUE (evaluate fn): {:.6}", eval_result);
    }
}
