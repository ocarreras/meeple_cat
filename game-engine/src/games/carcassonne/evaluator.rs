//! Heuristic evaluation function for Carcassonne MCTS.
//! Returns a value in [0, 1] representing how good the position is for the player.
//! Mirrors backend/src/games/carcassonne/evaluator.py.

use crate::engine::models::*;
use crate::engine::plugin::GamePlugin;
use crate::games::carcassonne::types::{CarcassonneState, FeatureType, PlacedMeeple, Position};

/// Tunable parameters for the Carcassonne heuristic evaluator.
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
        Self {
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
        }
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
) -> Box<dyn Fn(&serde_json::Value, &Phase, &str, &[Player], &dyn GamePlugin) -> f64 + Send + Sync> {
    Box::new(move |game_data, phase, player_id, players, plugin| {
        evaluate(game_data, phase, player_id, players, plugin, weights)
    })
}

/// Evaluate a Carcassonne position using default weights.
pub fn carcassonne_eval(
    game_data: &serde_json::Value,
    phase: &Phase,
    player_id: &str,
    players: &[Player],
    plugin: &dyn GamePlugin,
) -> f64 {
    let w = EvalWeights::default();
    evaluate(game_data, phase, player_id, players, plugin, &w)
}

fn evaluate(
    game_data: &serde_json::Value,
    _phase: &Phase,
    player_id: &str,
    players: &[Player],
    _plugin: &dyn GamePlugin,
    w: &EvalWeights,
) -> f64 {
    let scores = &game_data["scores"];
    let features = &game_data["features"];
    let meeple_supply = &game_data["meeple_supply"];
    let tiles_remaining = game_data["tile_bag"]
        .as_array()
        .map(|a| a.len())
        .unwrap_or(0) as i64;
    let board_size = game_data["board"]["tiles"]
        .as_object()
        .map(|o| o.len())
        .unwrap_or(0) as i64;
    let total_tiles = board_size + tiles_remaining;
    let game_progress = 1.0 - (tiles_remaining as f64 / total_tiles.max(1) as f64);

    // 1. Score differential
    let my_score = scores.get(player_id).and_then(|v| v.as_f64()).unwrap_or(0.0);
    let mut max_opp = 0.0_f64;
    if let Some(obj) = scores.as_object() {
        for (pid, v) in obj {
            if pid != player_id {
                let s = v.as_f64().unwrap_or(0.0);
                if s > max_opp {
                    max_opp = s;
                }
            }
        }
    }
    let score_diff = my_score - max_opp;
    let score_component = sigmoid(score_diff, w.score_scale);

    // 2. Incomplete feature potential
    let mut my_potential = 0.0_f64;
    let mut opp_potential = 0.0_f64;
    let mut wasted_meeple_penalty = 0.0_f64;

    if let Some(features_obj) = features.as_object() {
        for (_fid, feat) in features_obj {
            if feat.get("is_complete").and_then(|v| v.as_bool()).unwrap_or(false) {
                continue;
            }
            let ft = feat["feature_type"].as_str().unwrap_or("");
            if ft == "field" {
                continue;
            }
            let meeples = match feat.get("meeples").and_then(|v| v.as_array()) {
                Some(arr) if !arr.is_empty() => arr,
                _ => continue,
            };

            let tiles = feat.get("tiles").and_then(|v| v.as_array());
            let open_edges = feat.get("open_edges").and_then(|v| v.as_array());
            let pennants = feat.get("pennants").and_then(|v| v.as_i64()).unwrap_or(0);

            let potential = raw_feature_potential(
                ft,
                tiles.map(|t| t.len()).unwrap_or(0),
                open_edges.map(|e| e.len()).unwrap_or(0),
                pennants,
                tiles_remaining,
                game_data,
                tiles,
            );

            let (my_count, max_count, _total_opp) = meeple_counts(meeples, player_id);

            if my_count == 0 {
                opp_potential += potential;
            } else if my_count >= max_count {
                my_potential += potential;
            } else {
                opp_potential += potential;
                wasted_meeple_penalty += my_count as f64 * 1.5;
            }
        }
    }

    let potential_diff = my_potential - opp_potential - wasted_meeple_penalty;
    let potential_component = sigmoid(potential_diff, w.potential_scale);

    // 3. Meeple economy
    let my_meeples = meeple_supply
        .get(player_id)
        .and_then(|v| v.as_i64())
        .unwrap_or(0);
    let mut opp_meeple_sum = 0i64;
    let mut opp_count = 0;
    for p in players {
        if p.player_id != player_id {
            opp_meeple_sum += meeple_supply
                .get(&p.player_id)
                .and_then(|v| v.as_i64())
                .unwrap_or(0);
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
    let my_field = estimate_field_value(game_data, player_id, tiles_remaining);
    let mut max_opp_field = 0.0_f64;
    for p in players {
        if p.player_id != player_id {
            let f = estimate_field_value(game_data, &p.player_id, tiles_remaining);
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

fn meeple_counts(meeples: &[serde_json::Value], player_id: &str) -> (i64, i64, i64) {
    let mut counts: std::collections::HashMap<&str, i64> = std::collections::HashMap::new();
    for m in meeples {
        if let Some(pid) = m.get("player_id").and_then(|v| v.as_str()) {
            *counts.entry(pid).or_insert(0) += 1;
        }
    }
    let my_count = counts.remove(player_id).unwrap_or(0);
    let max_opp = counts.values().copied().max().unwrap_or(0);
    let total_opp: i64 = counts.values().sum();
    (my_count, max_opp, total_opp)
}

fn raw_feature_potential(
    ft: &str,
    tile_count: usize,
    open_edge_count: usize,
    pennants: i64,
    tiles_remaining: i64,
    game_data: &serde_json::Value,
    tiles: Option<&Vec<serde_json::Value>>,
) -> f64 {
    match ft {
        "city" => {
            let cp = completion_probability(open_edge_count, tiles_remaining);
            cp * (tile_count as f64 * 2.0 + pennants as f64 * 2.0)
                + (1.0 - cp) * (tile_count as f64 + pennants as f64)
        }
        "road" => tile_count as f64,
        "monastery" => {
            if let Some(tiles_arr) = tiles {
                if tiles_arr.is_empty() {
                    return 0.0;
                }
                let pos_str = tiles_arr[0].as_str().unwrap_or("0,0");
                let pos = Position::from_key(pos_str);
                let board_tiles = &game_data["board"]["tiles"];
                let neighbors: usize = pos
                    .all_surrounding()
                    .iter()
                    .filter(|p| board_tiles.get(&p.to_key()).is_some())
                    .count();
                let cp = completion_probability(8 - neighbors, tiles_remaining);
                cp * 9.0 + (1.0 - cp) * (1.0 + neighbors as f64)
            } else {
                0.0
            }
        }
        _ => 0.0,
    }
}

fn estimate_field_value(game_data: &serde_json::Value, player_id: &str, _tiles_remaining: i64) -> f64 {
    let features = match game_data.get("features").and_then(|v| v.as_object()) {
        Some(f) => f,
        None => return 0.0,
    };

    let mut total = 0.0_f64;

    for (_fid, feat) in features {
        let ft = feat.get("feature_type").and_then(|v| v.as_str()).unwrap_or("");
        if ft != "field" {
            continue;
        }
        let meeples = match feat.get("meeples").and_then(|v| v.as_array()) {
            Some(arr) if !arr.is_empty() => arr,
            _ => continue,
        };

        let (my_count, max_count, _) = meeple_counts(meeples, player_id);
        if my_count < max_count && my_count > 0 {
            continue;
        }
        if my_count == 0 {
            continue;
        }

        let field_tiles = feat.get("tiles").and_then(|v| v.as_array());
        if let Some(tiles) = field_tiles {
            let tile_feature_map = &game_data["tile_feature_map"];
            let mut seen_cities: std::collections::HashSet<String> = std::collections::HashSet::new();

            for tile_pos_val in tiles {
                let tile_pos = match tile_pos_val.as_str() {
                    Some(s) => s,
                    None => continue,
                };
                if let Some(spots) = tile_feature_map.get(tile_pos).and_then(|v| v.as_object()) {
                    for (_spot, city_fid_val) in spots {
                        let city_fid = match city_fid_val.as_str() {
                            Some(s) => s,
                            None => continue,
                        };
                        if seen_cities.contains(city_fid) {
                            continue;
                        }
                        if let Some(city_feat) = features.get(city_fid) {
                            if city_feat.get("feature_type").and_then(|v| v.as_str()) == Some("city")
                                && city_feat.get("is_complete").and_then(|v| v.as_bool()).unwrap_or(false)
                            {
                                seen_cities.insert(city_fid.to_string());
                                total += 3.0;
                            }
                        }
                    }
                }
            }
        }
    }

    total
}

// ================================================================== //
//  Typed evaluation — direct struct access, no JSON navigation
// ================================================================== //

/// Create a typed eval function parameterised by `weights`.
pub fn make_carcassonne_eval_typed(
    weights: &'static EvalWeights,
) -> Box<dyn Fn(&CarcassonneState, &Phase, &str, &[Player]) -> f64 + Send + Sync> {
    Box::new(move |state, phase, player_id, players| {
        evaluate_typed(state, phase, player_id, players, weights)
    })
}

/// Typed eval using default weights.
pub fn carcassonne_eval_typed(
    state: &CarcassonneState,
    phase: &Phase,
    player_id: &str,
    players: &[Player],
) -> f64 {
    let w = EvalWeights::default();
    evaluate_typed(state, phase, player_id, players, &w)
}

fn evaluate_typed(
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

        let potential = raw_feature_potential_typed(
            feat.feature_type,
            feat.tiles.len(),
            feat.open_edges.len(),
            feat.pennants as i64,
            tiles_remaining,
            state,
            &feat.tiles,
        );

        let (my_count, max_count, _) = meeple_counts_typed(&feat.meeples, player_id);

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
    let my_field = estimate_field_value_typed(state, player_id);
    let mut max_opp_field = 0.0_f64;
    for p in players {
        if p.player_id != player_id {
            let f = estimate_field_value_typed(state, &p.player_id);
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

fn meeple_counts_typed(meeples: &[PlacedMeeple], player_id: &str) -> (i64, i64, i64) {
    let mut counts: std::collections::HashMap<&str, i64> = std::collections::HashMap::new();
    for m in meeples {
        *counts.entry(m.player_id.as_str()).or_insert(0) += 1;
    }
    let my_count = counts.remove(player_id).unwrap_or(0);
    let max_opp = counts.values().copied().max().unwrap_or(0);
    let total_opp: i64 = counts.values().sum();
    (my_count, max_opp, total_opp)
}

fn raw_feature_potential_typed(
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

fn estimate_field_value_typed(state: &CarcassonneState, player_id: &str) -> f64 {
    let mut total = 0.0_f64;

    for (_fid, feat) in &state.features {
        if feat.feature_type != FeatureType::Field {
            continue;
        }
        if feat.meeples.is_empty() {
            continue;
        }

        let (my_count, max_count, _) = meeple_counts_typed(&feat.meeples, player_id);
        if my_count == 0 || my_count < max_count {
            continue;
        }

        let mut seen_cities: std::collections::HashSet<&str> = std::collections::HashSet::new();
        for tile_pos in &feat.tiles {
            if let Some(spots) = state.tile_feature_map.get(tile_pos.as_str()) {
                for (_spot, city_fid) in spots {
                    if seen_cities.contains(city_fid.as_str()) {
                        continue;
                    }
                    if let Some(city_feat) = state.features.get(city_fid.as_str()) {
                        if city_feat.feature_type == FeatureType::City && city_feat.is_complete {
                            seen_cities.insert(city_fid.as_str());
                            total += 3.0;
                        }
                    }
                }
            }
        }
    }

    total
}
