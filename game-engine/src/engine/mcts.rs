//! Monte Carlo Tree Search engine with determinization, progressive widening, and RAVE.
//! Mirrors backend/src/engine/mcts.py.

use std::collections::HashMap;
use std::time::Instant;

use rand::seq::SliceRandom;

use crate::engine::evaluator::default_eval_fn;
use crate::engine::models::*;
use crate::engine::plugin::GamePlugin;
use crate::engine::simulator::{apply_action_and_resolve, SimulationState};

/// MCTS search parameters.
pub struct MctsParams {
    pub num_simulations: usize,
    pub time_limit_ms: f64,
    pub exploration_constant: f64,
    pub num_determinizations: usize,
    pub pw_c: f64,
    pub pw_alpha: f64,
    pub use_rave: bool,
    pub rave_k: f64,
    pub max_amaf_depth: usize,
    pub rave_fpu: bool,
    pub tile_aware_amaf: bool,
}

impl Default for MctsParams {
    fn default() -> Self {
        Self {
            num_simulations: 500,
            time_limit_ms: 2000.0,
            exploration_constant: 1.41,
            num_determinizations: 5,
            pw_c: 2.0,
            pw_alpha: 0.5,
            use_rave: false,
            rave_k: 100.0,
            max_amaf_depth: 4,
            rave_fpu: true,
            tile_aware_amaf: false,
        }
    }
}

/// A node in the MCTS search tree.
struct MctsNode {
    action_taken: Option<serde_json::Value>,
    parent: Option<usize>, // index into arena
    acting_player: Option<String>,
    children: Vec<usize>, // indices into arena
    untried_actions: Option<Vec<serde_json::Value>>,
    visit_count: u32,
    total_value: f64,
    // AMAF / RAVE statistics
    amaf_visits: HashMap<String, u32>,
    amaf_values: HashMap<String, f64>,
    amaf_key: String,
}

impl MctsNode {
    fn new(action: Option<serde_json::Value>, parent: Option<usize>) -> Self {
        Self {
            action_taken: action,
            parent,
            acting_player: None,
            children: Vec::new(),
            untried_actions: None,
            visit_count: 0,
            total_value: 0.0,
            amaf_visits: HashMap::new(),
            amaf_values: HashMap::new(),
            amaf_key: String::new(),
        }
    }

    fn uct_value(&self, parent_visits: u32, c: f64) -> f64 {
        if self.visit_count == 0 {
            return f64::INFINITY;
        }
        let exploit = self.total_value / self.visit_count as f64;
        let explore = c * ((parent_visits as f64).ln() / self.visit_count as f64).sqrt();
        exploit + explore
    }

    fn rave_value(
        &self,
        parent_visits: u32,
        c: f64,
        rave_k: f64,
        rave_fpu: bool,
        parent: Option<&MctsNode>,
    ) -> f64 {
        let action_k = if !self.amaf_key.is_empty() {
            &self.amaf_key
        } else {
            &action_key_from_opt(&self.action_taken)
        };

        if self.visit_count == 0 {
            if rave_fpu {
                if let Some(p) = parent {
                    let amaf_n = p.amaf_visits.get(action_k.as_str()).copied().unwrap_or(0);
                    if amaf_n > 0 {
                        let amaf_q = p.amaf_values.get(action_k.as_str()).copied().unwrap_or(0.0) / amaf_n as f64;
                        return 1.0 + amaf_q;
                    }
                }
            }
            return f64::INFINITY;
        }

        let q_uct = self.total_value / self.visit_count as f64;

        let (amaf_n, amaf_q) = if let Some(p) = parent {
            let n = p.amaf_visits.get(action_k.as_str()).copied().unwrap_or(0);
            if n > 0 {
                (n, p.amaf_values.get(action_k.as_str()).copied().unwrap_or(0.0) / n as f64)
            } else {
                (0, 0.5)
            }
        } else {
            (0, 0.5)
        };
        let _ = amaf_n; // used in beta calculation below

        let beta = (rave_k / (3.0 * parent_visits as f64 + rave_k)).sqrt();
        let blended = (1.0 - beta) * q_uct + beta * amaf_q;
        let explore = c * ((parent_visits as f64).ln() / self.visit_count as f64).sqrt();
        blended + explore
    }
}

/// Arena-allocated node storage for cache locality.
struct NodeArena {
    nodes: Vec<MctsNode>,
}

impl NodeArena {
    fn new() -> Self {
        Self { nodes: Vec::with_capacity(1024) }
    }

    fn alloc(&mut self, node: MctsNode) -> usize {
        let idx = self.nodes.len();
        self.nodes.push(node);
        idx
    }

    fn get(&self, idx: usize) -> &MctsNode {
        &self.nodes[idx]
    }

    fn get_mut(&mut self, idx: usize) -> &mut MctsNode {
        &mut self.nodes[idx]
    }

    fn best_child_uct(&self, node_idx: usize, c: f64) -> usize {
        let node = &self.nodes[node_idx];
        let parent_visits = node.visit_count;
        *node.children.iter()
            .max_by(|&&a, &&b| {
                let va = self.nodes[a].uct_value(parent_visits, c);
                let vb = self.nodes[b].uct_value(parent_visits, c);
                va.partial_cmp(&vb).unwrap_or(std::cmp::Ordering::Equal)
            })
            .unwrap()
    }

    fn best_child_rave(&self, node_idx: usize, c: f64, rave_k: f64, rave_fpu: bool) -> usize {
        let node = &self.nodes[node_idx];
        let parent_visits = node.visit_count;
        *node.children.iter()
            .max_by(|&&a, &&b| {
                let va = self.nodes[a].rave_value(parent_visits, c, rave_k, rave_fpu, Some(node));
                let vb = self.nodes[b].rave_value(parent_visits, c, rave_k, rave_fpu, Some(node));
                va.partial_cmp(&vb).unwrap_or(std::cmp::Ordering::Equal)
            })
            .unwrap()
    }

    fn most_visited_child(&self, node_idx: usize) -> usize {
        let node = &self.nodes[node_idx];
        *node.children.iter()
            .max_by_key(|&&idx| self.nodes[idx].visit_count)
            .unwrap()
    }
}

/// Run MCTS and return the best action payload.
pub fn mcts_search(
    game_data: &serde_json::Value,
    phase: &Phase,
    player_id: &str,
    plugin: &dyn GamePlugin,
    players: &[Player],
    params: &MctsParams,
    eval_fn: Option<&dyn Fn(&serde_json::Value, &Phase, &str, &[Player], &dyn GamePlugin) -> f64>,
) -> serde_json::Value {
    let valid_actions = plugin.get_valid_actions(game_data, phase, player_id);
    if valid_actions.len() <= 1 {
        return valid_actions.into_iter().next().unwrap_or(serde_json::json!({}));
    }

    let eval: &dyn Fn(&serde_json::Value, &Phase, &str, &[Player], &dyn GamePlugin) -> f64 =
        eval_fn.unwrap_or(&default_eval_fn);

    // Aggregate visit counts across determinizations
    let mut action_visits: HashMap<String, u32> = HashMap::new();
    let mut action_values: HashMap<String, f64> = HashMap::new();
    let mut action_map: HashMap<String, serde_json::Value> = HashMap::new();

    let sims_per_det = (params.num_simulations / params.num_determinizations).max(1);
    let total_deadline = Instant::now() + std::time::Duration::from_millis(params.time_limit_ms as u64);
    let time_per_det = std::time::Duration::from_millis((params.time_limit_ms / params.num_determinizations as f64) as u64);

    let mut rng = rand::thread_rng();

    for _det_idx in 0..params.num_determinizations {
        let det_deadline = std::cmp::min(Instant::now() + time_per_det, total_deadline);
        if Instant::now() >= total_deadline {
            break;
        }

        // Create a determinized copy — shuffle the tile bag
        let mut det_game_data = game_data.clone();
        if let Some(bag) = det_game_data.get_mut("tile_bag").and_then(|v| v.as_array_mut()) {
            bag.shuffle(&mut rng);
        }

        let root_state = SimulationState {
            game_data: det_game_data,
            phase: phase.clone(),
            players: players.to_vec(),
            scores: game_data.get("scores")
                .and_then(|v| v.as_object())
                .map(|obj| obj.iter().map(|(k, v)| (k.clone(), v.as_f64().unwrap_or(0.0))).collect())
                .unwrap_or_default(),
            game_over: None,
        };

        let mut arena = NodeArena::new();
        let root_idx = arena.alloc(MctsNode::new(None, None));

        for _sim_i in 0..sims_per_det {
            if Instant::now() >= det_deadline {
                break;
            }
            run_one_iteration(
                &mut arena,
                root_idx,
                &root_state,
                player_id,
                players,
                plugin,
                params,
                eval,
            );
        }

        // Collect visit counts
        let root = arena.get(root_idx);
        for &child_idx in &root.children {
            let child = arena.get(child_idx);
            if let Some(ref action) = child.action_taken {
                let key = action_key(action);
                action_map.entry(key.clone()).or_insert_with(|| action.clone());
                *action_visits.entry(key.clone()).or_insert(0) += child.visit_count;
                *action_values.entry(key).or_insert(0.0) += child.total_value;
            }
        }
    }

    if action_visits.is_empty() {
        return valid_actions.into_iter().next().unwrap_or(serde_json::json!({}));
    }

    let best_key = action_visits.iter()
        .max_by_key(|(_, &v)| v)
        .map(|(k, _)| k.clone())
        .unwrap();

    action_map.remove(&best_key).unwrap_or(serde_json::json!({}))
}

/// One MCTS iteration: select → expand → evaluate → backpropagate.
fn run_one_iteration(
    arena: &mut NodeArena,
    root_idx: usize,
    root_state: &SimulationState,
    searching_player: &str,
    players: &[Player],
    plugin: &dyn GamePlugin,
    params: &MctsParams,
    eval_fn: &dyn Fn(&serde_json::Value, &Phase, &str, &[Player], &dyn GamePlugin) -> f64,
) {
    let mut node_idx = root_idx;
    let mut state = root_state.clone();
    let mut played_actions: Vec<(String, Option<String>)> = Vec::new();

    // 1. SELECT
    loop {
        let node = arena.get(node_idx);
        if node.children.is_empty() || !at_widening_limit(node, params.pw_c, params.pw_alpha) {
            break;
        }

        let child_idx = if params.use_rave {
            arena.best_child_rave(node_idx, params.exploration_constant, params.rave_k, params.rave_fpu)
        } else {
            arena.best_child_uct(node_idx, params.exploration_constant)
        };

        node_idx = child_idx;
        let child = arena.get(child_idx);

        if child.action_taken.is_some() && child.acting_player.is_some() {
            let key = if !child.amaf_key.is_empty() {
                child.amaf_key.clone()
            } else {
                action_key_from_opt(&child.action_taken)
            };
            played_actions.push((key, child.acting_player.clone()));
            apply_node_action(&mut state, child, plugin);
        }
    }

    // 2. EXPAND
    if state.game_over.is_none() {
        let needs_expand = arena.get(node_idx).untried_actions.is_none();
        if needs_expand {
            let acting_pid = get_acting_player(&state.phase, players);
            let actions = if let Some(ref pid) = acting_pid {
                let mut acts = plugin.get_valid_actions(&state.game_data, &state.phase, pid);
                acts.sort_by(|a, b| action_sort_key(a).cmp(&action_sort_key(b)));
                acts
            } else {
                vec![]
            };
            arena.get_mut(node_idx).untried_actions = Some(actions);
        }

        let should_expand = {
            let node = arena.get(node_idx);
            state.game_over.is_none()
                && node.untried_actions.as_ref().map_or(false, |u| !u.is_empty())
                && !at_widening_limit(node, params.pw_c, params.pw_alpha)
        };

        if should_expand {
            let acting_pid = get_acting_player(&state.phase, players);
            let action_payload = arena.get_mut(node_idx)
                .untried_actions.as_mut().unwrap()
                .remove(0);

            let amaf_key_str = if params.use_rave {
                if params.tile_aware_amaf {
                    amaf_key(&action_payload, Some(&state))
                } else {
                    action_key(&action_payload)
                }
            } else {
                String::new()
            };

            let mut child = MctsNode::new(Some(action_payload.clone()), Some(node_idx));
            child.acting_player = acting_pid.clone();
            child.amaf_key = amaf_key_str;

            let child_idx = arena.alloc(child);
            arena.get_mut(node_idx).children.push(child_idx);
            node_idx = child_idx;

            if let Some(ref pid) = acting_pid {
                let child = arena.get(child_idx);
                let key = if !child.amaf_key.is_empty() {
                    child.amaf_key.clone()
                } else {
                    action_key(&action_payload)
                };
                played_actions.push((key, Some(pid.clone())));
                apply_node_action(&mut state, arena.get(child_idx), plugin);
            }
        }
    }

    // 3. EVALUATE
    let value = if state.game_over.is_some() {
        terminal_value(&state, searching_player)
    } else {
        eval_fn(&state.game_data, &state.phase, searching_player, players, plugin)
    };

    // 4. BACKPROPAGATE
    backpropagate(arena, node_idx, value, searching_player, &played_actions, params.use_rave, params.max_amaf_depth);
}

fn backpropagate(
    arena: &mut NodeArena,
    leaf_idx: usize,
    value: f64,
    searching_player: &str,
    played_actions: &[(String, Option<String>)],
    use_rave: bool,
    max_amaf_depth: usize,
) {
    let mut node_idx_opt = Some(leaf_idx);
    let mut depth = played_actions.len();

    while let Some(idx) = node_idx_opt {
        let node = arena.get_mut(idx);
        node.visit_count += 1;

        if node.acting_player.as_deref() == Some(searching_player) || node.acting_player.is_none() {
            node.total_value += value;
        } else {
            node.total_value += 1.0 - value;
        }

        // AMAF update
        if use_rave && depth < played_actions.len() {
            let end_i = if max_amaf_depth > 0 {
                (depth + max_amaf_depth).min(played_actions.len())
            } else {
                played_actions.len()
            };

            for i in depth..end_i {
                let (ref ak, ref player) = played_actions[i];
                *node.amaf_visits.entry(ak.clone()).or_insert(0) += 1;
                if player.as_deref() == Some(searching_player) || player.is_none() {
                    *node.amaf_values.entry(ak.clone()).or_insert(0.0) += value;
                } else {
                    *node.amaf_values.entry(ak.clone()).or_insert(0.0) += 1.0 - value;
                }
            }
        }

        if depth > 0 {
            depth -= 1;
        }
        node_idx_opt = arena.get(idx).parent;
    }
}

fn at_widening_limit(node: &MctsNode, pw_c: f64, pw_alpha: f64) -> bool {
    if node.untried_actions.as_ref().map_or(true, |u| u.is_empty()) {
        return true;
    }
    let limit = max_children(node.visit_count, pw_c, pw_alpha);
    node.children.len() >= limit
}

fn max_children(visit_count: u32, pw_c: f64, pw_alpha: f64) -> usize {
    (pw_c * (visit_count.max(1) as f64).powf(pw_alpha)) as usize
}

// ------------------------------------------------------------------ //
//  Helpers
// ------------------------------------------------------------------ //

fn apply_node_action(
    state: &mut SimulationState,
    node: &MctsNode,
    plugin: &dyn GamePlugin,
) {
    let action_type = if !state.phase.expected_actions.is_empty() {
        state.phase.expected_actions[0].action_type.clone()
    } else {
        state.phase.name.clone()
    };
    let action = Action {
        action_type,
        player_id: node.acting_player.clone().unwrap_or_else(|| "system".into()),
        payload: node.action_taken.clone().unwrap_or(serde_json::json!({})),
    };
    apply_action_and_resolve(plugin, state, &action);
}

fn get_acting_player(phase: &Phase, players: &[Player]) -> Option<String> {
    if !phase.expected_actions.is_empty() {
        return Some(phase.expected_actions[0].player_id.clone());
    }
    if let Some(pi) = phase.metadata.get("player_index").and_then(|v| v.as_u64()) {
        let idx = pi as usize;
        if idx < players.len() {
            return Some(players[idx].player_id.clone());
        }
    }
    None
}

fn terminal_value(state: &SimulationState, player_id: &str) -> f64 {
    match &state.game_over {
        None => 0.5,
        Some(result) => {
            if result.winners.iter().any(|w| w == player_id) {
                if result.winners.len() == 1 { 1.0 } else { 0.8 }
            } else {
                0.0
            }
        }
    }
}

/// Deterministic string key for an action payload.
pub fn action_key(action: &serde_json::Value) -> String {
    if let (Some(x), Some(y), Some(r)) = (
        action.get("x").and_then(|v| v.as_i64()),
        action.get("y").and_then(|v| v.as_i64()),
        action.get("rotation").and_then(|v| v.as_u64()),
    ) {
        return format!("{},{},{}", x, y, r);
    }
    if action.get("skip").and_then(|v| v.as_bool()).unwrap_or(false) {
        return "skip".into();
    }
    if let Some(spot) = action.get("meeple_spot").and_then(|v| v.as_str()) {
        return format!("meeple:{}", spot);
    }
    serde_json::to_string(action).unwrap_or_default()
}

fn action_key_from_opt(action: &Option<serde_json::Value>) -> String {
    match action {
        Some(a) => action_key(a),
        None => String::new(),
    }
}

fn amaf_key(action: &serde_json::Value, state: Option<&SimulationState>) -> String {
    if let Some(st) = state {
        if let (Some(x), Some(y), Some(r)) = (
            action.get("x").and_then(|v| v.as_i64()),
            action.get("y").and_then(|v| v.as_i64()),
            action.get("rotation").and_then(|v| v.as_u64()),
        ) {
            if let Some(tile) = st.game_data.get("current_tile").and_then(|v| v.as_str()) {
                if !tile.is_empty() {
                    return format!("{}:{},{},{}", tile, x, y, r);
                }
            }
        }
    }
    action_key(action)
}

fn action_sort_key(action: &serde_json::Value) -> (i32, i64) {
    if action.get("skip").and_then(|v| v.as_bool()).unwrap_or(false) {
        return (10, 0);
    }
    if let Some(spot) = action.get("meeple_spot").and_then(|v| v.as_str()) {
        let prefix = spot.split('_').next().unwrap_or(spot);
        let priority = match prefix {
            "city" => 0,
            "monastery" => 1,
            "road" => 2,
            "field" => 3,
            _ => 5,
        };
        return (1, priority);
    }
    if let (Some(x), Some(y)) = (
        action.get("x").and_then(|v| v.as_i64()),
        action.get("y").and_then(|v| v.as_i64()),
    ) {
        return (0, x.abs() + y.abs());
    }
    (5, 0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::games::carcassonne::plugin::CarcassonnePlugin;

    fn make_players(n: u32) -> Vec<Player> {
        (0..n)
            .map(|i| Player {
                player_id: format!("p{}", i + 1),
                display_name: format!("Player {}", i + 1),
                seat_index: i as i32,
                is_bot: false,
                bot_id: None,
            })
            .collect()
    }

    #[test]
    fn test_mcts_returns_valid_action() {
        let plugin = CarcassonnePlugin;
        let players = make_players(2);
        let config = GameConfig {
            random_seed: Some(42),
            options: serde_json::json!({"tile_count": 5}),
        };

        let (game_data, phase, _) = plugin.create_initial_state(&players, &config);

        // Advance to place_tile phase
        let draw_action = Action {
            action_type: "draw_tile".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({}),
        };
        let result = plugin.apply_action(&game_data, &phase, &draw_action, &players);
        let game_data = result.game_data;
        let phase = result.next_phase;

        let params = MctsParams {
            num_simulations: 20,
            time_limit_ms: 500.0,
            num_determinizations: 2,
            ..Default::default()
        };

        let best = mcts_search(&game_data, &phase, "p1", &plugin, &players, &params, None);

        // Should have x, y, rotation (tile placement)
        assert!(best.get("x").is_some(), "MCTS should return an action with x");
        assert!(best.get("y").is_some(), "MCTS should return an action with y");
        assert!(best.get("rotation").is_some(), "MCTS should return an action with rotation");
    }

    #[test]
    fn test_mcts_single_action() {
        // When only one action is valid, should return it immediately
        let plugin = CarcassonnePlugin;
        let players = make_players(2);
        let config = GameConfig {
            random_seed: Some(42),
            options: serde_json::json!({}),
        };

        let (game_data, phase, _) = plugin.create_initial_state(&players, &config);

        // draw_tile has no valid actions (auto-resolve), but let's test with skip-only meeple
        let params = MctsParams::default();

        // This will return empty since draw_tile has no player actions
        let _ = mcts_search(&game_data, &phase, "p1", &plugin, &players, &params, None);
    }
}
