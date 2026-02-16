//! Bot-vs-bot arena runner.
//! Mirrors backend/src/engine/arena.py.

use std::collections::HashMap;
use std::time::Instant;

use crate::engine::bot_strategy::{BotStrategy, TypedBotStrategy};
use crate::engine::models::*;
use crate::engine::plugin::{GamePlugin, TypedGamePlugin};
use crate::engine::simulator::{
    apply_action_and_resolve, apply_action_and_resolve_typed,
    SimulationState, TypedSimulationState,
};

/// Aggregated results from an arena run.
pub struct ArenaResult {
    pub num_games: usize,
    pub wins: HashMap<String, usize>,
    pub draws: usize,
    pub total_scores: HashMap<String, Vec<f64>>,
    pub game_durations_ms: Vec<f64>,
}

impl ArenaResult {
    pub fn win_rate(&self, name: &str) -> f64 {
        *self.wins.get(name).unwrap_or(&0) as f64 / self.num_games.max(1) as f64
    }

    pub fn avg_score(&self, name: &str) -> f64 {
        let scores = self.total_scores.get(name);
        match scores {
            Some(s) if !s.is_empty() => s.iter().sum::<f64>() / s.len() as f64,
            _ => 0.0,
        }
    }

    pub fn score_stddev(&self, name: &str) -> f64 {
        let scores = match self.total_scores.get(name) {
            Some(s) if s.len() >= 2 => s,
            _ => return 0.0,
        };
        let avg = self.avg_score(name);
        let variance = scores.iter().map(|s| (s - avg).powi(2)).sum::<f64>() / (scores.len() - 1) as f64;
        variance.sqrt()
    }

    pub fn confidence_interval_95(&self, name: &str) -> (f64, f64) {
        let n = self.num_games;
        if n == 0 {
            return (0.0, 0.0);
        }
        let p = self.win_rate(name);
        let z = 1.96_f64;
        let denom = 1.0 + z * z / n as f64;
        let center = (p + z * z / (2.0 * n as f64)) / denom;
        let margin = z * ((p * (1.0 - p) + z * z / (4.0 * n as f64)) / n as f64).sqrt() / denom;
        ((center - margin).max(0.0), (center + margin).min(1.0))
    }

    pub fn summary(&self) -> String {
        let mut lines = vec![format!("Arena Results ({} games)", self.num_games)];
        lines.push("=".repeat(60));
        for name in self.wins.keys() {
            let wr = self.win_rate(name);
            let (ci_lo, ci_hi) = self.confidence_interval_95(name);
            let avg = self.avg_score(name);
            let std = self.score_stddev(name);
            lines.push(format!(
                "  {:>12}: {:3} wins ({:5.1}%)  [95% CI: {:.1}%-{:.1}%]  avg={:5.1} +/- {:4.1}",
                name,
                self.wins[name],
                wr * 100.0,
                ci_lo * 100.0,
                ci_hi * 100.0,
                avg,
                std,
            ));
        }
        lines.push(format!("  {:>12}: {}", "Draws", self.draws));
        if !self.game_durations_ms.is_empty() {
            let avg_ms = self.game_durations_ms.iter().sum::<f64>() / self.game_durations_ms.len() as f64;
            let total_s = self.game_durations_ms.iter().sum::<f64>() / 1000.0;
            lines.push(format!("  Avg game: {:.0}ms  |  Total: {:.1}s", avg_ms, total_s));
        }
        lines.join("\n")
    }
}

/// Run `num_games` between the given strategies and return aggregated stats.
pub fn run_arena(
    plugin: &dyn GamePlugin,
    strategies: &HashMap<String, Box<dyn BotStrategy>>,
    num_games: usize,
    base_seed: u64,
    num_players: usize,
    game_options: Option<serde_json::Value>,
    alternate_seats: bool,
    progress_callback: Option<&dyn Fn(usize, usize)>,
) -> ArenaResult {
    let strategy_names: Vec<String> = strategies.keys().cloned().collect();
    assert_eq!(strategy_names.len(), num_players);

    let mut result = ArenaResult {
        num_games,
        wins: strategy_names.iter().map(|n| (n.clone(), 0)).collect(),
        draws: 0,
        total_scores: strategy_names.iter().map(|n| (n.clone(), Vec::new())).collect(),
        game_durations_ms: Vec::new(),
    };

    for game_idx in 0..num_games {
        let seed = base_seed + game_idx as u64;

        let seat_assignment: Vec<String> = if alternate_seats {
            (0..num_players)
                .map(|i| strategy_names[(i + game_idx) % num_players].clone())
                .collect()
        } else {
            strategy_names[..num_players].to_vec()
        };

        let players: Vec<Player> = (0..num_players)
            .map(|i| Player {
                player_id: format!("p{}", i),
                display_name: seat_assignment[i].clone(),
                seat_index: i as i32,
                is_bot: true,
                bot_id: Some(seat_assignment[i].clone()),
            })
            .collect();

        let pid_to_strategy: HashMap<String, &dyn BotStrategy> = (0..num_players)
            .map(|i| (format!("p{}", i), strategies[&seat_assignment[i]].as_ref()))
            .collect();

        let pid_to_name: HashMap<String, String> = (0..num_players)
            .map(|i| (format!("p{}", i), seat_assignment[i].clone()))
            .collect();

        let config = GameConfig {
            random_seed: Some(seed),
            options: game_options.clone().unwrap_or(serde_json::json!({})),
        };

        let t0 = Instant::now();
        let game_result = play_one_game(plugin, &players, &config, &pid_to_strategy);
        let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;
        result.game_durations_ms.push(elapsed_ms);

        match game_result {
            None => {
                result.draws += 1;
                for name in &strategy_names {
                    result.total_scores.get_mut(name).unwrap().push(0.0);
                }
            }
            Some(gr) => {
                for (pid, score) in &gr.final_scores {
                    if let Some(name) = pid_to_name.get(pid) {
                        result.total_scores.get_mut(name).unwrap().push(*score);
                    }
                }

                if gr.winners.len() == 1 {
                    if let Some(name) = pid_to_name.get(&gr.winners[0]) {
                        *result.wins.get_mut(name).unwrap() += 1;
                    }
                } else {
                    result.draws += 1;
                }
            }
        }

        if let Some(cb) = progress_callback {
            cb(game_idx + 1, num_games);
        }
    }

    result
}

fn play_one_game(
    plugin: &dyn GamePlugin,
    players: &[Player],
    config: &GameConfig,
    pid_to_strategy: &HashMap<String, &dyn BotStrategy>,
) -> Option<GameResult> {
    let (game_data, phase, _) = plugin.create_initial_state(players, config);

    let mut state = SimulationState {
        game_data,
        phase,
        players: players.to_vec(),
        scores: players.iter().map(|p| (p.player_id.clone(), 0.0)).collect(),
        game_over: None,
    };

    // Resolve initial auto-resolve phases
    resolve_auto(plugin, &mut state);

    let max_iterations = 500;
    for _ in 0..max_iterations {
        if state.game_over.is_some() {
            break;
        }

        if state.phase.auto_resolve {
            resolve_auto(plugin, &mut state);
            continue;
        }

        let acting_pid = if !state.phase.expected_actions.is_empty() {
            state.phase.expected_actions[0].player_id.clone()
        } else {
            break;
        };

        let strategy = match pid_to_strategy.get(&acting_pid) {
            Some(s) => *s,
            None => break,
        };

        let chosen = strategy.choose_action(
            &state.game_data,
            &state.phase,
            &acting_pid,
            plugin,
            players,
        );

        let action_type = state.phase.expected_actions[0].action_type.clone();
        let action = Action {
            action_type,
            player_id: acting_pid,
            payload: chosen,
        };
        apply_action_and_resolve(plugin, &mut state, &action);
    }

    state.game_over
}

// ================================================================== //
//  Typed arena — zero-JSON hot path
// ================================================================== //

/// Run typed arena: `num_games` between typed strategies.
pub fn run_arena_typed<P: TypedGamePlugin>(
    plugin: &P,
    strategies: &HashMap<String, Box<dyn TypedBotStrategy<P>>>,
    num_games: usize,
    base_seed: u64,
    num_players: usize,
    game_options: Option<serde_json::Value>,
    alternate_seats: bool,
    progress_callback: Option<&dyn Fn(usize, usize)>,
) -> ArenaResult {
    let strategy_names: Vec<String> = strategies.keys().cloned().collect();
    assert_eq!(strategy_names.len(), num_players);

    let mut result = ArenaResult {
        num_games,
        wins: strategy_names.iter().map(|n| (n.clone(), 0)).collect(),
        draws: 0,
        total_scores: strategy_names.iter().map(|n| (n.clone(), Vec::new())).collect(),
        game_durations_ms: Vec::new(),
    };

    for game_idx in 0..num_games {
        let seed = base_seed + game_idx as u64;

        let seat_assignment: Vec<String> = if alternate_seats {
            (0..num_players)
                .map(|i| strategy_names[(i + game_idx) % num_players].clone())
                .collect()
        } else {
            strategy_names[..num_players].to_vec()
        };

        let players: Vec<Player> = (0..num_players)
            .map(|i| Player {
                player_id: format!("p{}", i),
                display_name: seat_assignment[i].clone(),
                seat_index: i as i32,
                is_bot: true,
                bot_id: Some(seat_assignment[i].clone()),
            })
            .collect();

        let pid_to_strategy: HashMap<String, &dyn TypedBotStrategy<P>> = (0..num_players)
            .map(|i| (format!("p{}", i), strategies[&seat_assignment[i]].as_ref()))
            .collect();

        let pid_to_name: HashMap<String, String> = (0..num_players)
            .map(|i| (format!("p{}", i), seat_assignment[i].clone()))
            .collect();

        let config = GameConfig {
            random_seed: Some(seed),
            options: game_options.clone().unwrap_or(serde_json::json!({})),
        };

        let t0 = Instant::now();
        let game_result = play_one_game_typed(plugin, &players, &config, &pid_to_strategy);
        let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;
        result.game_durations_ms.push(elapsed_ms);

        match game_result {
            None => {
                result.draws += 1;
                for name in &strategy_names {
                    result.total_scores.get_mut(name).unwrap().push(0.0);
                }
            }
            Some(gr) => {
                for (pid, score) in &gr.final_scores {
                    if let Some(name) = pid_to_name.get(pid) {
                        result.total_scores.get_mut(name).unwrap().push(*score);
                    }
                }

                if gr.winners.len() == 1 {
                    if let Some(name) = pid_to_name.get(&gr.winners[0]) {
                        *result.wins.get_mut(name).unwrap() += 1;
                    }
                } else {
                    result.draws += 1;
                }
            }
        }

        if let Some(cb) = progress_callback {
            cb(game_idx + 1, num_games);
        }
    }

    result
}

fn play_one_game_typed<P: TypedGamePlugin>(
    plugin: &P,
    players: &[Player],
    config: &GameConfig,
    pid_to_strategy: &HashMap<String, &dyn TypedBotStrategy<P>>,
) -> Option<GameResult> {
    // Create initial state via JSON interface, then decode to typed
    let (game_data, phase, _) = plugin.create_initial_state(players, config);
    let typed_state = plugin.decode_state(&game_data);

    let mut state = TypedSimulationState {
        state: typed_state,
        phase,
        players: players.to_vec(),
        scores: players.iter().map(|p| (p.player_id.clone(), 0.0)).collect(),
        game_over: None,
    };

    // Resolve initial auto-resolve phases
    resolve_auto_typed(plugin, &mut state);

    let max_iterations = 500;
    for _ in 0..max_iterations {
        if state.game_over.is_some() {
            break;
        }

        if state.phase.auto_resolve {
            resolve_auto_typed(plugin, &mut state);
            continue;
        }

        let acting_pid = if !state.phase.expected_actions.is_empty() {
            state.phase.expected_actions[0].player_id.clone()
        } else {
            break;
        };

        let strategy = match pid_to_strategy.get(&acting_pid) {
            Some(s) => *s,
            None => break,
        };

        let chosen = strategy.choose_action_typed(
            &state.state,
            &state.phase,
            &acting_pid,
            plugin,
            players,
        );

        let action_type = state.phase.expected_actions[0].action_type.clone();
        let action = Action {
            action_type,
            player_id: acting_pid,
            payload: chosen,
        };
        apply_action_and_resolve_typed(plugin, &mut state, &action);
    }

    state.game_over
}

fn resolve_auto_typed<P: TypedGamePlugin>(
    plugin: &P,
    state: &mut TypedSimulationState<P::State>,
) {
    let mut max_auto = 50;
    while state.phase.auto_resolve && state.game_over.is_none() && max_auto > 0 {
        max_auto -= 1;

        let pid = if let Some(pi) = state.phase.metadata.get("player_index").and_then(|v| v.as_u64()) {
            let idx = pi as usize;
            if idx < state.players.len() {
                state.players[idx].player_id.clone()
            } else {
                "system".into()
            }
        } else {
            "system".into()
        };

        let synthetic = Action {
            action_type: state.phase.name.clone(),
            player_id: pid,
            payload: serde_json::json!({}),
        };
        apply_action_and_resolve_typed(plugin, state, &synthetic);
    }
}

fn resolve_auto(plugin: &dyn GamePlugin, state: &mut SimulationState) {
    let mut max_auto = 50;
    while state.phase.auto_resolve && state.game_over.is_none() && max_auto > 0 {
        max_auto -= 1;

        let pid = if let Some(pi) = state.phase.metadata.get("player_index").and_then(|v| v.as_u64()) {
            let idx = pi as usize;
            if idx < state.players.len() {
                state.players[idx].player_id.clone()
            } else {
                "system".into()
            }
        } else {
            "system".into()
        };

        let synthetic = Action {
            action_type: state.phase.name.clone(),
            player_id: pid,
            payload: serde_json::json!({}),
        };
        apply_action_and_resolve(plugin, state, &synthetic);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::bot_strategy::{RandomStrategy, TypedRandomStrategy};
    use crate::games::carcassonne::plugin::CarcassonnePlugin;

    #[test]
    fn test_arena_random_vs_random() {
        let plugin = CarcassonnePlugin;
        let mut strategies: HashMap<String, Box<dyn BotStrategy>> = HashMap::new();
        strategies.insert("random_a".into(), Box::new(RandomStrategy));
        strategies.insert("random_b".into(), Box::new(RandomStrategy));

        let result = run_arena(
            &plugin,
            &strategies,
            3,  // just 3 games for speed
            42,
            2,
            Some(serde_json::json!({"tile_count": 10})),
            true,
            None,
        );

        assert_eq!(result.num_games, 3);
        let total_outcomes = result.wins.values().sum::<usize>() + result.draws;
        assert_eq!(total_outcomes, 3);
    }

    #[test]
    fn test_arena_typed_random_vs_random() {
        let plugin = CarcassonnePlugin;
        let mut strategies: HashMap<String, Box<dyn TypedBotStrategy<CarcassonnePlugin>>> = HashMap::new();
        strategies.insert("random_a".into(), Box::new(TypedRandomStrategy));
        strategies.insert("random_b".into(), Box::new(TypedRandomStrategy));

        let result = run_arena_typed(
            &plugin,
            &strategies,
            3,
            42,
            2,
            Some(serde_json::json!({"tile_count": 10})),
            true,
            None,
        );

        assert_eq!(result.num_games, 3);
        let total_outcomes = result.wins.values().sum::<usize>() + result.draws;
        assert_eq!(total_outcomes, 3);
    }
}
