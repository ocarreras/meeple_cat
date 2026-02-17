//! Monte Carlo Tree Search engine with determinization, progressive widening, and RAVE.
//! Mirrors backend/src/engine/mcts.py.

use std::collections::HashMap;
use std::time::Instant;

use rayon::prelude::*;

use crate::engine::evaluator::default_eval;
use crate::engine::models::*;
use crate::engine::plugin::TypedGamePlugin;
use crate::engine::simulator::{apply_action_and_resolve, SimulationState};

/// MCTS search parameters.
#[derive(Clone)]
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

        let (_amaf_n, amaf_q) = if let Some(p) = parent {
            let n = p.amaf_visits.get(action_k.as_str()).copied().unwrap_or(0);
            if n > 0 {
                (n, p.amaf_values.get(action_k.as_str()).copied().unwrap_or(0.0) / n as f64)
            } else {
                (0, 0.5)
            }
        } else {
            (0, 0.5)
        };
        // β uses parent_visits (not amaf_n) — simplified RAVE schedule
        // matching the Python implementation. As parent gets more visits,
        // β shrinks and we rely more on UCT than AMAF.
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
        // Use first-max (not last-max) to match Python's max() tie-breaking.
        // This ensures the MCTS deepens the first-expanded (earliest) child
        // when UCT values tie, producing deeper trees that reach terminal
        // states faster.
        let mut best_idx = node.children[0];
        let mut best_val = self.nodes[best_idx].uct_value(parent_visits, c);
        for &child_idx in &node.children[1..] {
            let val = self.nodes[child_idx].uct_value(parent_visits, c);
            if val > best_val {
                best_val = val;
                best_idx = child_idx;
            }
        }
        best_idx
    }

    fn best_child_rave(&self, node_idx: usize, c: f64, rave_k: f64, rave_fpu: bool) -> usize {
        let node = &self.nodes[node_idx];
        let parent_visits = node.visit_count;
        let mut best_idx = node.children[0];
        let mut best_val = self.nodes[best_idx].rave_value(parent_visits, c, rave_k, rave_fpu, Some(node));
        for &child_idx in &node.children[1..] {
            let val = self.nodes[child_idx].rave_value(parent_visits, c, rave_k, rave_fpu, Some(node));
            if val > best_val {
                best_val = val;
                best_idx = child_idx;
            }
        }
        best_idx
    }

}

/// Per-determinization results, collected and aggregated after parallel execution.
struct DetResult {
    visits: HashMap<String, u32>,
    values: HashMap<String, f64>,
    actions: HashMap<String, serde_json::Value>,
    iterations: usize,
}

/// Run MCTS on typed state and return the best action payload and total iterations run.
/// Determinizations run in parallel via rayon for ~linear speedup with core count.
pub fn mcts_search<P: TypedGamePlugin>(
    state: &P::State,
    phase: &Phase,
    player_id: &str,
    plugin: &P,
    players: &[Player],
    params: &MctsParams,
    eval_fn: Option<&(dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64 + Sync)>,
) -> (serde_json::Value, usize) {
    // Validate player ordering invariants — zero cost in release builds
    debug_assert!(
        !players.is_empty(),
        "MCTS: players list must not be empty"
    );
    debug_assert!(
        players.iter().enumerate().all(|(i, p)| p.seat_index == i as i32),
        "MCTS: players must be ordered by seat_index. Got: {:?}",
        players.iter().map(|p| (&p.player_id, p.seat_index)).collect::<Vec<_>>()
    );
    debug_assert!(
        players.iter().any(|p| p.player_id == player_id),
        "MCTS: searching player_id '{}' not found in players: {:?}",
        player_id,
        players.iter().map(|p| &p.player_id).collect::<Vec<_>>()
    );

    let valid_actions = plugin.get_valid_actions(state, phase, player_id);
    if valid_actions.len() <= 1 {
        return (valid_actions.into_iter().next().unwrap_or(serde_json::json!({})), 0);
    }

    let sims_per_det = (params.num_simulations / params.num_determinizations).max(1);
    let total_deadline = Instant::now() + std::time::Duration::from_millis(params.time_limit_ms as u64);
    let base_scores = plugin.get_scores(state);

    // Run determinizations in parallel
    let det_results: Vec<DetResult> = (0..params.num_determinizations)
        .into_par_iter()
        .map(|_det_idx| {
            if Instant::now() >= total_deadline {
                return DetResult {
                    visits: HashMap::new(),
                    values: HashMap::new(),
                    actions: HashMap::new(),
                    iterations: 0,
                };
            }

            let mut det_state = state.clone();
            plugin.determinize(&mut det_state);

            let root_state = SimulationState {
                state: det_state,
                phase: phase.clone(),
                players: players.to_vec(),
                scores: base_scores.clone(),
                game_over: None,
            };

            let mut arena = NodeArena::new();
            let root_idx = arena.alloc(MctsNode::new(None, None));
            let mut iterations = 0;

            for _sim_i in 0..sims_per_det {
                if Instant::now() >= total_deadline {
                    break;
                }
                iterations += 1;
                run_one_iteration(
                    &mut arena,
                    root_idx,
                    &root_state,
                    player_id,
                    players,
                    plugin,
                    params,
                    eval_fn,
                );
            }

            let mut visits = HashMap::new();
            let mut values = HashMap::new();
            let mut actions = HashMap::new();

            let root = arena.get(root_idx);
            for &child_idx in &root.children {
                let child = arena.get(child_idx);
                if let Some(ref action) = child.action_taken {
                    let key = action_key(action);
                    actions.entry(key.clone()).or_insert_with(|| action.clone());
                    *visits.entry(key.clone()).or_insert(0) += child.visit_count;
                    *values.entry(key).or_insert(0.0) += child.total_value;
                }
            }

            DetResult { visits, values, actions, iterations }
        })
        .collect();

    // Aggregate results from all determinizations
    let mut action_visits: HashMap<String, u32> = HashMap::new();
    let mut action_values: HashMap<String, f64> = HashMap::new();
    let mut action_map: HashMap<String, serde_json::Value> = HashMap::new();
    let mut total_iterations: usize = 0;

    for det in det_results {
        total_iterations += det.iterations;
        for (key, count) in &det.visits {
            *action_visits.entry(key.clone()).or_insert(0) += count;
            if !action_map.contains_key(key) {
                if let Some(action) = det.actions.get(key) {
                    action_map.insert(key.clone(), action.clone());
                }
            }
        }
        for (key, value) in &det.values {
            *action_values.entry(key.clone()).or_insert(0.0) += value;
        }
    }

    if action_visits.is_empty() {
        return (valid_actions.into_iter().next().unwrap_or(serde_json::json!({})), total_iterations);
    }

    // Find the max visit count, then break ties by highest average value.
    // When many children have similar visit counts (common with wide PW),
    // the average value provides better differentiation than alphabetical order.
    let max_visits = action_visits.values().copied().max().unwrap_or(0);
    let best_key = action_visits.iter()
        .filter(|(_, &v)| v == max_visits)
        .max_by(|(a_key, _), (b_key, _)| {
            let a_val = action_values.get(*a_key).copied().unwrap_or(0.0) / max_visits.max(1) as f64;
            let b_val = action_values.get(*b_key).copied().unwrap_or(0.0) / max_visits.max(1) as f64;
            a_val.partial_cmp(&b_val).unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|(k, _)| k.clone())
        .unwrap();

    (action_map.remove(&best_key).unwrap_or(serde_json::json!({})), total_iterations)
}

/// One MCTS iteration: select -> expand -> evaluate -> backpropagate.
fn run_one_iteration<P: TypedGamePlugin>(
    arena: &mut NodeArena,
    root_idx: usize,
    root_state: &SimulationState<P::State>,
    searching_player: &str,
    players: &[Player],
    plugin: &P,
    params: &MctsParams,
    eval_fn: Option<&(dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64 + Sync)>,
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
            apply_node_action(plugin, &mut state, arena.get(child_idx));
        }
    }

    // 2. EXPAND
    if state.game_over.is_none() {
        let needs_expand = arena.get(node_idx).untried_actions.is_none();
        if needs_expand {
            let acting_pid = get_acting_player(&state.phase, players);
            let actions = if let Some(ref pid) = acting_pid {
                let mut acts = plugin.get_valid_actions(&state.state, &state.phase, pid);
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
                    amaf_key(plugin, &action_payload, &state)
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

            if acting_pid.is_some() {
                let child = arena.get(child_idx);
                let key = if !child.amaf_key.is_empty() {
                    child.amaf_key.clone()
                } else {
                    action_key(&action_payload)
                };
                played_actions.push((key, acting_pid));
                apply_node_action(plugin, &mut state, arena.get(child_idx));
            }
        }
    }

    // 3. EVALUATE
    let value = if state.game_over.is_some() {
        terminal_value(&state.game_over, searching_player)
    } else if let Some(eval) = eval_fn {
        eval(&state.state, &state.phase, searching_player, players)
    } else {
        // Default: sigmoid of score differential
        default_eval(plugin, &state.state, searching_player)
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
    (pw_c * (visit_count.max(1) as f64).powf(pw_alpha)).max(1.0) as usize
}

// ------------------------------------------------------------------ //
//  Helpers
// ------------------------------------------------------------------ //

fn apply_node_action<P: TypedGamePlugin>(
    plugin: &P,
    state: &mut SimulationState<P::State>,
    node: &MctsNode,
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
            debug_assert_eq!(
                players[idx].seat_index, idx as i32,
                "get_acting_player: player at index {} has seat_index {}, expected {}. \
                 Players may be misordered.",
                idx, players[idx].seat_index, idx
            );
            return Some(players[idx].player_id.clone());
        }
    }
    None
}

fn terminal_value(game_over: &Option<GameResult>, player_id: &str) -> f64 {
    match game_over {
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

fn amaf_key<P: TypedGamePlugin>(
    plugin: &P,
    action: &serde_json::Value,
    state: &SimulationState<P::State>,
) -> String {
    if let (Some(x), Some(y), Some(r)) = (
        action.get("x").and_then(|v| v.as_i64()),
        action.get("y").and_then(|v| v.as_i64()),
        action.get("rotation").and_then(|v| v.as_u64()),
    ) {
        let context = plugin.amaf_context(&state.state);
        if !context.is_empty() {
            return format!("{}:{},{},{}", context, x, y, r);
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

/// Tree statistics for diagnostics.
#[derive(Debug, Default)]
pub struct TreeStats {
    pub total_nodes: usize,
    pub max_depth: usize,
    pub root_children: usize,
    pub root_visit_count: u32,
    pub leaf_evals: usize,     // nodes with visit_count > 0 and no children
    pub terminal_count: usize, // tracked via a counter during search
    pub avg_leaf_depth: f64,
    pub root_child_visits: Vec<(String, u32, f64)>, // (action_key, visits, avg_value)
}

fn collect_tree_stats(arena: &NodeArena, root_idx: usize) -> TreeStats {
    let mut stats = TreeStats::default();
    let root = arena.get(root_idx);
    stats.root_visit_count = root.visit_count;
    stats.root_children = root.children.len();

    // Collect root children info
    let mut child_info: Vec<(String, u32, f64)> = root.children.iter().map(|&ci| {
        let c = arena.get(ci);
        let key = action_key_from_opt(&c.action_taken);
        let avg = if c.visit_count > 0 { c.total_value / c.visit_count as f64 } else { 0.0 };
        (key, c.visit_count, avg)
    }).collect();
    child_info.sort_by(|a, b| b.1.cmp(&a.1)); // sort by visits desc
    stats.root_child_visits = child_info;

    // BFS to count nodes, depth, leaves
    let mut queue = std::collections::VecDeque::new();
    queue.push_back((root_idx, 0usize));
    let mut leaf_depths = Vec::new();

    while let Some((idx, depth)) = queue.pop_front() {
        stats.total_nodes += 1;
        if depth > stats.max_depth {
            stats.max_depth = depth;
        }
        let node = arena.get(idx);
        if node.children.is_empty() && node.visit_count > 0 {
            stats.leaf_evals += 1;
            leaf_depths.push(depth as f64);
        }
        for &ci in &node.children {
            queue.push_back((ci, depth + 1));
        }
    }

    if !leaf_depths.is_empty() {
        stats.avg_leaf_depth = leaf_depths.iter().sum::<f64>() / leaf_depths.len() as f64;
    }

    stats
}

/// Like mcts_search but returns per-determinization tree stats for diagnostics.
pub fn mcts_search_with_stats<P: TypedGamePlugin>(
    state: &P::State,
    phase: &Phase,
    player_id: &str,
    plugin: &P,
    players: &[Player],
    params: &MctsParams,
    eval_fn: Option<&(dyn Fn(&P::State, &Phase, &str, &[Player]) -> f64 + Sync)>,
) -> (serde_json::Value, usize, Vec<TreeStats>) {
    let valid_actions = plugin.get_valid_actions(state, phase, player_id);
    if valid_actions.len() <= 1 {
        return (valid_actions.into_iter().next().unwrap_or(serde_json::json!({})), 0, vec![]);
    }

    let sims_per_det = (params.num_simulations / params.num_determinizations).max(1);
    let total_deadline = Instant::now() + std::time::Duration::from_millis(params.time_limit_ms as u64);
    let base_scores = plugin.get_scores(state);

    let det_results: Vec<(DetResult, TreeStats)> = (0..params.num_determinizations)
        .into_par_iter()
        .map(|_det_idx| {
            if Instant::now() >= total_deadline {
                return (DetResult {
                    visits: HashMap::new(),
                    values: HashMap::new(),
                    actions: HashMap::new(),
                    iterations: 0,
                }, TreeStats::default());
            }

            let mut det_state = state.clone();
            plugin.determinize(&mut det_state);

            let root_state = SimulationState {
                state: det_state,
                phase: phase.clone(),
                players: players.to_vec(),
                scores: base_scores.clone(),
                game_over: None,
            };

            let mut arena = NodeArena::new();
            let root_idx = arena.alloc(MctsNode::new(None, None));
            let mut iterations = 0;

            for _sim_i in 0..sims_per_det {
                if Instant::now() >= total_deadline {
                    break;
                }
                iterations += 1;
                run_one_iteration(
                    &mut arena, root_idx, &root_state,
                    player_id, players, plugin, params, eval_fn,
                );
            }

            let stats = collect_tree_stats(&arena, root_idx);

            let mut visits = HashMap::new();
            let mut values = HashMap::new();
            let mut actions = HashMap::new();

            let root = arena.get(root_idx);
            for &child_idx in &root.children {
                let child = arena.get(child_idx);
                if let Some(ref action) = child.action_taken {
                    let key = action_key(action);
                    actions.entry(key.clone()).or_insert_with(|| action.clone());
                    *visits.entry(key.clone()).or_insert(0) += child.visit_count;
                    *values.entry(key).or_insert(0.0) += child.total_value;
                }
            }

            (DetResult { visits, values, actions, iterations }, stats)
        })
        .collect();

    let mut action_visits: HashMap<String, u32> = HashMap::new();
    let mut action_values: HashMap<String, f64> = HashMap::new();
    let mut action_map: HashMap<String, serde_json::Value> = HashMap::new();
    let mut total_iterations: usize = 0;
    let mut all_stats = Vec::new();

    for (det, stats) in det_results {
        total_iterations += det.iterations;
        all_stats.push(stats);
        for (key, count) in &det.visits {
            *action_visits.entry(key.clone()).or_insert(0) += count;
            if !action_map.contains_key(key) {
                if let Some(action) = det.actions.get(key) {
                    action_map.insert(key.clone(), action.clone());
                }
            }
        }
        for (key, value) in &det.values {
            *action_values.entry(key.clone()).or_insert(0.0) += value;
        }
    }

    if action_visits.is_empty() {
        return (valid_actions.into_iter().next().unwrap_or(serde_json::json!({})), total_iterations, all_stats);
    }

    let max_visits = action_visits.values().copied().max().unwrap_or(0);
    let best_key = action_visits.iter()
        .filter(|(_, &v)| v == max_visits)
        .max_by(|(a_key, _), (b_key, _)| {
            let a_val = action_values.get(*a_key).copied().unwrap_or(0.0) / max_visits.max(1) as f64;
            let b_val = action_values.get(*b_key).copied().unwrap_or(0.0) / max_visits.max(1) as f64;
            a_val.partial_cmp(&b_val).unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|(k, _)| k.clone())
        .unwrap();

    (action_map.remove(&best_key).unwrap_or(serde_json::json!({})), total_iterations, all_stats)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::plugin::{GamePlugin, JsonAdapter};
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
        let json_plugin = JsonAdapter(CarcassonnePlugin);
        let players = make_players(2);
        let config = GameConfig {
            random_seed: Some(42),
            options: serde_json::json!({"tile_count": 5}),
        };

        // Use JsonAdapter for initial state + draw action (returns JSON for apply_action)
        let (game_data, phase, _) = json_plugin.create_initial_state(&players, &config);

        // Advance to place_tile phase via JSON boundary
        let draw_action = Action {
            action_type: "draw_tile".into(),
            player_id: "p1".into(),
            payload: serde_json::json!({}),
        };
        let result = json_plugin.apply_action(&game_data, &phase, &draw_action, &players);
        let game_data = result.game_data;
        let phase = result.next_phase;

        // Decode to typed state for MCTS
        let state = plugin.decode_state(&game_data);

        let params = MctsParams {
            num_simulations: 20,
            time_limit_ms: 500.0,
            num_determinizations: 2,
            ..Default::default()
        };

        let (best, iterations) = mcts_search(&state, &phase, "p1", &plugin, &players, &params, None);

        // Should have x, y, rotation (tile placement)
        assert!(best.get("x").is_some(), "MCTS should return an action with x");
        assert!(best.get("y").is_some(), "MCTS should return an action with y");
        assert!(best.get("rotation").is_some(), "MCTS should return an action with rotation");
        assert!(iterations > 0, "Should have run at least one iteration");
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

        let (state, phase, _) = plugin.create_initial_state(&players, &config);

        let params = MctsParams::default();
        let (_action, _iters) = mcts_search(&state, &phase, "p1", &plugin, &players, &params, None);
    }

    #[test]
    fn test_save_eval_states() {
        // Save several mid-game states with Rust evaluations for cross-language comparison.
        use crate::games::carcassonne::evaluator::{make_carcassonne_eval, DEFAULT_WEIGHTS};
        use crate::engine::simulator::{apply_action_and_resolve, SimulationState};
        use crate::engine::plugin::TypedGamePlugin;

        let plugin = CarcassonnePlugin;
        let players = make_players(2);
        let eval_fn = make_carcassonne_eval(&DEFAULT_WEIGHTS);

        let mut results: Vec<serde_json::Value> = Vec::new();

        for seed in [42u64, 123, 999, 7, 50] {
            let config = GameConfig {
                random_seed: Some(seed),
                options: serde_json::json!({}),
            };
            let (state, phase, _) = plugin.create_initial_state(&players, &config);
            let mut sim = SimulationState {
                state,
                phase,
                players: players.clone(),
                scores: players.iter().map(|p| (p.player_id.clone(), 0.0)).collect(),
                game_over: None,
            };

            let mut rng = seed;
            let mut step = 0;

            loop {
                if sim.game_over.is_some() { break; }
                while sim.phase.auto_resolve && sim.game_over.is_none() {
                    let at = sim.phase.name.clone();
                    apply_action_and_resolve(&plugin, &mut sim, &Action {
                        action_type: at, player_id: "system".into(),
                        payload: serde_json::json!({}),
                    });
                }
                if sim.game_over.is_some() { break; }

                let acting_pid = sim.phase.expected_actions[0].player_id.clone();
                let valid = plugin.get_valid_actions(&sim.state, &sim.phase, &acting_pid);
                if valid.is_empty() { break; }

                // Save state at certain checkpoints
                if matches!(step, 5 | 10 | 15 | 20 | 25 | 30) && sim.phase.name == "place_tile" {
                    let game_data = plugin.encode_state(&sim.state);
                    let eval_p1 = eval_fn(&sim.state, &sim.phase, "p1", &players);
                    let eval_p2 = eval_fn(&sim.state, &sim.phase, "p2", &players);

                    results.push(serde_json::json!({
                        "seed": seed,
                        "step": step,
                        "phase": sim.phase.name,
                        "scores": sim.state.scores,
                        "rust_eval_p1": eval_p1,
                        "rust_eval_p2": eval_p2,
                        "game_data": game_data,
                    }));
                }

                step += 1;
                rng = rng.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                let idx = (rng >> 33) as usize % valid.len();
                let action = Action {
                    action_type: sim.phase.expected_actions[0].action_type.clone(),
                    player_id: acting_pid,
                    payload: valid[idx].clone(),
                };
                apply_action_and_resolve(&plugin, &mut sim, &action);
            }
        }

        let json = serde_json::to_string_pretty(&results).unwrap();
        std::fs::write("/tmp/rust_eval_states.json", &json).unwrap();
        println!("Saved {} states to /tmp/rust_eval_states.json", results.len());

        for r in &results {
            println!("  seed={} step={} scores={} eval_p1={:.6} eval_p2={:.6}",
                r["seed"], r["step"], r["scores"],
                r["rust_eval_p1"].as_f64().unwrap(),
                r["rust_eval_p2"].as_f64().unwrap());
        }
    }

    #[test]
    fn test_mcts_tree_stats_comparison() {
        // Compare tree structure between pw_c=1 and pw_c=2 at a high-branching mid-game state
        use crate::games::carcassonne::evaluator::{make_carcassonne_eval, DEFAULT_WEIGHTS};
        use crate::engine::simulator::{apply_action_and_resolve, SimulationState};

        let plugin = CarcassonnePlugin;
        let players = make_players(2);

        // Try multiple seeds to find a state with many valid actions
        let mut best_sim: Option<SimulationState<_>> = None;
        let mut best_count = 0;

        for seed in 40..100 {
            let config = GameConfig {
                random_seed: Some(seed),
                options: serde_json::json!({}),
            };
            let (state, phase, _) = plugin.create_initial_state(&players, &config);
            let mut sim = SimulationState {
                state,
                phase,
                players: players.clone(),
                scores: players.iter().map(|p| (p.player_id.clone(), 0.0)).collect(),
                game_over: None,
            };

            let mut rng = seed * 31337;
            for _ in 0..200 {
                if sim.game_over.is_some() { break; }
                while sim.phase.auto_resolve && sim.game_over.is_none() {
                    let at = sim.phase.name.clone();
                    apply_action_and_resolve(&plugin, &mut sim, &Action {
                        action_type: at, player_id: "system".into(),
                        payload: serde_json::json!({}),
                    });
                }
                if sim.game_over.is_some() { break; }

                let acting_pid = sim.phase.expected_actions[0].player_id.clone();
                let valid = plugin.get_valid_actions(&sim.state, &sim.phase, &acting_pid);
                if valid.is_empty() { break; }

                if sim.phase.name == "place_tile" && valid.len() > best_count {
                    best_count = valid.len();
                    best_sim = Some(sim.clone());
                    if best_count >= 40 { break; }
                }

                rng = rng.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                let idx = (rng >> 33) as usize % valid.len();
                let action = Action {
                    action_type: sim.phase.expected_actions[0].action_type.clone(),
                    player_id: acting_pid,
                    payload: valid[idx].clone(),
                };
                apply_action_and_resolve(&plugin, &mut sim, &action);
            }
            if best_count >= 40 { break; }
        }

        let sim = best_sim.expect("Should find a state with many actions");
        let acting_pid = sim.phase.expected_actions[0].player_id.clone();
        let valid_actions = plugin.get_valid_actions(&sim.state, &sim.phase, &acting_pid);
        println!("\nMid-game state: phase={} valid_actions={} acting={}",
            sim.phase.name, valid_actions.len(), acting_pid);
        println!("Scores: {:?}", sim.scores);

        // Print the action sort order
        let mut sorted_actions: Vec<_> = valid_actions.iter().collect();
        sorted_actions.sort_by(|a, b| action_sort_key(a).cmp(&action_sort_key(b)));
        println!("\nAction priority order (first 20):");
        for (i, a) in sorted_actions.iter().take(20).enumerate() {
            let key = action_key(a);
            let sort = action_sort_key(a);
            println!("  {:2}. {} sort_key={:?}", i, key, sort);
        }

        let eval_fn = make_carcassonne_eval(&DEFAULT_WEIGHTS);

        let configs = [
            ("pw_c=1", 1.0f64, 0.5f64),
            ("pw_c=2", 2.0, 0.5),
            ("pw_c=100 (no PW)", 100.0, 0.5),
        ];

        for (label, pw_c, pw_alpha) in &configs {
            let params = MctsParams {
                num_simulations: 500,
                time_limit_ms: 999999.0,
                num_determinizations: 1,
                pw_c: *pw_c,
                pw_alpha: *pw_alpha,
                ..Default::default()
            };

            let (best_action, iters, stats) = mcts_search_with_stats(
                &sim.state, &sim.phase, &acting_pid, &plugin, &players, &params,
                Some(&|s, ph, pid, pl| eval_fn(s, ph, pid, pl)),
            );

            println!("\n=== {} (iters={}) ===", label, iters);
            for (i, s) in stats.iter().enumerate() {
                println!("  Det {}: nodes={} root_children={} max_depth={} avg_leaf_depth={:.1} leaf_evals={}",
                    i, s.total_nodes, s.root_children, s.max_depth, s.avg_leaf_depth, s.leaf_evals);
                println!("  Top-10 root children by visits:");
                for (key, visits, avg) in s.root_child_visits.iter().take(10) {
                    println!("    {} : visits={} avg_val={:.4}", key, visits, avg);
                }
                let total_visits: u32 = s.root_child_visits.iter().map(|x| x.1).sum();
                println!("  Total children: {} total_visits: {}", s.root_child_visits.len(), total_visits);
            }
            println!("  Best action: {}", best_action);
        }
    }

    /// CI smoke test: 2 short games (10 tiles, 50 sims).
    /// Uses UUID-like IDs where alphabetical sort != seat order,
    /// so player-ordering bugs cause MCTS to lose.
    #[test]
    fn test_mcts_beats_random_smoke() {
        use crate::engine::simulator::{apply_action_and_resolve, SimulationState};
        use crate::games::carcassonne::evaluator::{make_carcassonne_eval, DEFAULT_WEIGHTS};
        use rand::seq::SliceRandom;

        let plugin = CarcassonnePlugin;
        let eval_fn = make_carcassonne_eval(&DEFAULT_WEIGHTS);

        let params = MctsParams {
            num_simulations: 50,
            time_limit_ms: 999999.0,
            num_determinizations: 2,
            ..Default::default()
        };

        let mut mcts_total = 0.0;
        let mut random_total = 0.0;

        for seed in [42u64, 123] {
            // "zzz" at seat 0, "aaa" at seat 1 — alphabetical sort would swap these
            let players = vec![
                Player {
                    player_id: "zzz-mcts-bot".into(),
                    display_name: "MCTS".into(),
                    seat_index: 0,
                    is_bot: true,
                    bot_id: None,
                },
                Player {
                    player_id: "aaa-random".into(),
                    display_name: "Random".into(),
                    seat_index: 1,
                    is_bot: false,
                    bot_id: None,
                },
            ];

            let config = GameConfig {
                random_seed: Some(seed),
                options: serde_json::json!({"tile_count": 10}),
            };
            let (state, phase, _) = plugin.create_initial_state(&players, &config);
            let mut sim = SimulationState {
                state,
                phase,
                players: players.clone(),
                scores: players.iter().map(|p| (p.player_id.clone(), 0.0)).collect(),
                game_over: None,
            };

            for _ in 0..200 {
                if sim.game_over.is_some() { break; }
                while sim.phase.auto_resolve && sim.game_over.is_none() {
                    let phase_name = sim.phase.name.clone();
                    let pid = sim.phase.metadata.get("player_index")
                        .and_then(|v| v.as_u64())
                        .and_then(|i| sim.players.get(i as usize))
                        .map(|p| p.player_id.clone())
                        .unwrap_or_else(|| "system".into());
                    apply_action_and_resolve(&plugin, &mut sim, &Action {
                        action_type: phase_name,
                        player_id: pid,
                        payload: serde_json::json!({}),
                    });
                }
                if sim.game_over.is_some() || sim.phase.expected_actions.is_empty() { break; }

                let acting_pid = sim.phase.expected_actions[0].player_id.clone();

                let chosen = if acting_pid == "zzz-mcts-bot" {
                    let eval_ref: Option<&(dyn Fn(&_, &Phase, &str, &[Player]) -> f64 + Sync)> =
                        Some(eval_fn.as_ref());
                    let (action, _) = mcts_search(
                        &sim.state, &sim.phase, &acting_pid, &plugin,
                        &players, &params, eval_ref,
                    );
                    action
                } else {
                    let valid = plugin.get_valid_actions(&sim.state, &sim.phase, &acting_pid);
                    if valid.is_empty() { break; }
                    valid.choose(&mut rand::thread_rng()).cloned().unwrap()
                };

                let action_type = sim.phase.expected_actions[0].action_type.clone();
                apply_action_and_resolve(&plugin, &mut sim, &Action {
                    action_type, player_id: acting_pid, payload: chosen,
                });
            }

            mcts_total += sim.scores.get("zzz-mcts-bot").copied().unwrap_or(0.0);
            random_total += sim.scores.get("aaa-random").copied().unwrap_or(0.0);
        }

        let avg_mcts = mcts_total / 2.0;
        let avg_random = random_total / 2.0;

        assert!(
            avg_mcts > avg_random,
            "MCTS avg ({:.1}) should beat Random avg ({:.1}). \
             Check player ordering in mcts_search.",
            avg_mcts, avg_random,
        );
        assert!(
            avg_mcts >= 10.0,
            "MCTS avg score {:.1} is suspiciously low (expected >= 10). \
             May indicate player ordering or eval bugs.",
            avg_mcts,
        );
    }
}
