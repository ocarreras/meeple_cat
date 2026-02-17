//! Bot-vs-bot diagnostic simulations.
//!
//! These are NOT run in CI — use them locally to verify bot strength
//! and catch integration issues (e.g. wrong eval profile, missing heuristics).
//!
//! Run with:
//!     cargo test --release --test bot_diagnostics -- --ignored --nocapture

use std::collections::HashMap;

use meeple_game_engine::engine::arena::run_arena;
use meeple_game_engine::engine::bot_strategy::{BotStrategy, MctsStrategy, RandomStrategy};
use meeple_game_engine::engine::mcts::{mcts_search, MctsParams};
use meeple_game_engine::engine::models::*;
use meeple_game_engine::engine::plugin::TypedGamePlugin;
use meeple_game_engine::engine::simulator::{apply_action_and_resolve, SimulationState};
use meeple_game_engine::games::carcassonne::evaluator::{make_carcassonne_eval, DEFAULT_WEIGHTS};
use meeple_game_engine::games::carcassonne::plugin::CarcassonnePlugin;
use meeple_game_engine::games::carcassonne::types::CarcassonneState;

/// MCTS (500 sims, default eval, 5 determinizations) vs Random.
/// Matches production bot config. Baseline: MCTS should win 100% with avg ~90 pts.
#[test]
#[ignore]
fn mcts_vs_random() {
    let plugin = CarcassonnePlugin;
    let num_games = 20;

    let eval_fn = make_carcassonne_eval(&DEFAULT_WEIGHTS);
    let mcts = MctsStrategy::<CarcassonnePlugin>::with_eval(
        MctsParams {
            num_simulations: 500,
            time_limit_ms: 999999.0,
            num_determinizations: 5,
            pw_c: 2.0,
            pw_alpha: 0.5,
            ..Default::default()
        },
        eval_fn,
    );

    let mut strategies: HashMap<String, Box<dyn BotStrategy<CarcassonnePlugin>>> = HashMap::new();
    strategies.insert("mcts".into(), Box::new(mcts));
    strategies.insert("random".into(), Box::new(RandomStrategy));

    let result = run_arena(
        &plugin,
        &strategies,
        num_games,
        42,
        2,
        None,
        true,
        Some(&|done, total| {
            eprintln!("  game {}/{}", done, total);
        }),
    );

    println!("\n{}", result.summary());

    let scores_m = result.total_scores.get("mcts").unwrap();
    let scores_r = result.total_scores.get("random").unwrap();
    for i in 0..num_games {
        println!(
            "  Game {:2}: mcts={:3.0}  random={:3.0}",
            i, scores_m[i], scores_r[i]
        );
    }

    let avg_mcts = result.avg_score("mcts");
    let avg_random = result.avg_score("random");
    let wr = result.win_rate("mcts");
    println!(
        "\n  MCTS avg={:.1} (+/-{:.1})  Random avg={:.1} (+/-{:.1})  MCTS win rate={:.0}%",
        avg_mcts,
        result.score_stddev("mcts"),
        avg_random,
        result.score_stddev("random"),
        wr * 100.0
    );

    // Sanity checks — if these fail, something is wrong with the integration
    assert!(wr >= 0.8, "MCTS win rate {:.0}% is too low", wr * 100.0);
    assert!(avg_mcts >= 60.0, "MCTS avg score {:.1} is too low", avg_mcts);
}

/// Reproduces the gRPC bug: players sorted by UUID instead of seat order.
/// The MCTS simulations swap player turns, causing it to optimize for the opponent.
/// Expected: MCTS with wrong player order scores MUCH lower than with correct order.
#[test]
#[ignore]
fn mcts_wrong_player_order() {
    let plugin = CarcassonnePlugin;
    let num_games = 5;
    let base_seed = 42u64;

    let params = MctsParams {
        num_simulations: 500,
        time_limit_ms: 999999.0,
        num_determinizations: 5,
        pw_c: 2.0,
        pw_alpha: 0.5,
        ..Default::default()
    };

    for &swap in &[false, true] {
        let label = if swap { "WRONG order (sorted UUID)" } else { "CORRECT order" };
        let mut mcts_total = 0.0;
        let mut random_total = 0.0;

        for game_idx in 0..num_games {
            let seed = base_seed + game_idx as u64;

            // Use UUID-like names where "aaa" sorts before "zzz"
            let correct_players = vec![
                Player {
                    player_id: "zzz-bot".into(),
                    display_name: "mcts".into(),
                    seat_index: 0,
                    is_bot: true,
                    bot_id: None,
                },
                Player {
                    player_id: "aaa-human".into(),
                    display_name: "random".into(),
                    seat_index: 1,
                    is_bot: false,
                    bot_id: None,
                },
            ];

            // Swapped: sorted alphabetically (aaa < zzz), swapping seat 0 and 1
            let wrong_players = vec![
                Player {
                    player_id: "aaa-human".into(),
                    display_name: "random".into(),
                    seat_index: 0,
                    is_bot: false,
                    bot_id: None,
                },
                Player {
                    player_id: "zzz-bot".into(),
                    display_name: "mcts".into(),
                    seat_index: 1,
                    is_bot: true,
                    bot_id: None,
                },
            ];

            let mcts_pid = "zzz-bot";
            let random_pid = "aaa-human";
            let mcts_players = if swap { &wrong_players } else { &correct_players };

            let config = GameConfig {
                random_seed: Some(seed),
                options: serde_json::json!({}),
            };
            let (state, phase, _) = plugin.create_initial_state(&correct_players, &config);
            let mut sim = SimulationState {
                state,
                phase,
                players: correct_players.clone(),
                scores: correct_players.iter().map(|p| (p.player_id.clone(), 0.0)).collect(),
                game_over: None,
            };

            resolve_auto(&plugin, &mut sim);

            for _ in 0..500 {
                if sim.game_over.is_some() { break; }
                if sim.phase.auto_resolve {
                    resolve_auto(&plugin, &mut sim);
                    continue;
                }
                let acting_pid = if !sim.phase.expected_actions.is_empty() {
                    sim.phase.expected_actions[0].player_id.clone()
                } else { break; };

                let chosen = if acting_pid == mcts_pid {
                    let eval_fn = make_carcassonne_eval(&DEFAULT_WEIGHTS);
                    let eval_ref: Option<&(dyn Fn(&CarcassonneState, &Phase, &str, &[Player]) -> f64 + Sync)> =
                        Some(eval_fn.as_ref());
                    // Pass mcts_players (correct or wrong order) to MCTS
                    let (action, _) = mcts_search(
                        &sim.state, &sim.phase, &acting_pid, &plugin,
                        mcts_players, &params, eval_ref,
                    );
                    action
                } else {
                    let valid = plugin.get_valid_actions(&sim.state, &sim.phase, &acting_pid);
                    if valid.is_empty() { break; }
                    use rand::seq::SliceRandom;
                    valid.choose(&mut rand::thread_rng()).cloned().unwrap()
                };

                let action_type = sim.phase.expected_actions[0].action_type.clone();
                let action = Action { action_type, player_id: acting_pid, payload: chosen };
                apply_action_and_resolve(&plugin, &mut sim, &action);
            }

            let ms = sim.scores.get(mcts_pid).copied().unwrap_or(0.0);
            let rs = sim.scores.get(random_pid).copied().unwrap_or(0.0);
            mcts_total += ms;
            random_total += rs;
        }

        println!(
            "  {}: mcts avg={:.1}  random avg={:.1}",
            label,
            mcts_total / num_games as f64,
            random_total / num_games as f64,
        );
    }
}

/// Same as mcts_vs_random but with a JSON round-trip before every MCTS call.
/// This mirrors the gRPC production path: Python stores game_data as JSON,
/// Rust decodes it before running MCTS. If this test scores much lower than
/// mcts_vs_random, we have a serialization bug.
#[test]
#[ignore]
fn mcts_vs_random_json_roundtrip() {
    let plugin = CarcassonnePlugin;
    let num_games = 10;
    let base_seed = 42u64;

    let params = MctsParams {
        num_simulations: 500,
        time_limit_ms: 999999.0,
        num_determinizations: 5,
        pw_c: 2.0,
        pw_alpha: 0.5,
        ..Default::default()
    };

    let mut mcts_scores = Vec::new();
    let mut random_scores = Vec::new();
    let mut mcts_wins = 0usize;

    for game_idx in 0..num_games {
        let seed = base_seed + game_idx as u64;

        // Alternate seats
        let (mcts_seat, random_seat) = if game_idx % 2 == 0 { (0, 1) } else { (1, 0) };
        let players = vec![
            Player {
                player_id: "p0".into(),
                display_name: if mcts_seat == 0 { "mcts" } else { "random" }.into(),
                seat_index: 0,
                is_bot: true,
                bot_id: None,
            },
            Player {
                player_id: "p1".into(),
                display_name: if mcts_seat == 1 { "mcts" } else { "random" }.into(),
                seat_index: 1,
                is_bot: true,
                bot_id: None,
            },
        ];
        let mcts_pid = format!("p{}", mcts_seat);
        let random_pid = format!("p{}", random_seat);

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

        // Auto-resolve initial phases
        resolve_auto(&plugin, &mut sim);

        for _ in 0..500 {
            if sim.game_over.is_some() {
                break;
            }
            if sim.phase.auto_resolve {
                resolve_auto(&plugin, &mut sim);
                continue;
            }

            let acting_pid = if !sim.phase.expected_actions.is_empty() {
                sim.phase.expected_actions[0].player_id.clone()
            } else {
                break;
            };

            let chosen = if acting_pid == mcts_pid {
                // === KEY: JSON round-trip before MCTS, just like gRPC path ===
                let json_state = plugin.encode_state(&sim.state);
                let decoded_state: CarcassonneState =
                    serde_json::from_value(json_state).expect("JSON round-trip failed");

                let eval_fn = make_carcassonne_eval(&DEFAULT_WEIGHTS);
                let eval_ref: Option<
                    &(dyn Fn(&CarcassonneState, &Phase, &str, &[Player]) -> f64 + Sync),
                > = Some(eval_fn.as_ref());

                let (action, _iters) = mcts_search(
                    &decoded_state,
                    &sim.phase,
                    &acting_pid,
                    &plugin,
                    &players,
                    &params,
                    eval_ref,
                );
                action
            } else {
                // Random opponent
                let valid = plugin.get_valid_actions(&sim.state, &sim.phase, &acting_pid);
                if valid.is_empty() {
                    break;
                }
                use rand::seq::SliceRandom;
                valid.choose(&mut rand::thread_rng()).cloned().unwrap()
            };

            let action_type = sim.phase.expected_actions[0].action_type.clone();
            let action = Action {
                action_type,
                player_id: acting_pid,
                payload: chosen,
            };
            apply_action_and_resolve(&plugin, &mut sim, &action);
        }

        let ms = sim.scores.get(&mcts_pid).copied().unwrap_or(0.0);
        let rs = sim.scores.get(&random_pid).copied().unwrap_or(0.0);
        mcts_scores.push(ms);
        random_scores.push(rs);
        if ms > rs {
            mcts_wins += 1;
        }
        eprintln!(
            "  game {}/{}: mcts={:.0} random={:.0}",
            game_idx + 1,
            num_games,
            ms,
            rs
        );
    }

    let avg_mcts = mcts_scores.iter().sum::<f64>() / num_games as f64;
    let avg_random = random_scores.iter().sum::<f64>() / num_games as f64;
    let wr = mcts_wins as f64 / num_games as f64;

    println!("\n=== JSON round-trip MCTS vs Random ({} games) ===", num_games);
    for i in 0..num_games {
        println!(
            "  Game {:2}: mcts={:3.0}  random={:3.0}",
            i, mcts_scores[i], random_scores[i]
        );
    }
    println!(
        "\n  MCTS avg={:.1}  Random avg={:.1}  MCTS win rate={:.0}%",
        avg_mcts, avg_random, wr * 100.0
    );

    assert!(wr >= 0.7, "JSON round-trip MCTS win rate {:.0}% is too low", wr * 100.0);
    assert!(avg_mcts >= 50.0, "JSON round-trip MCTS avg score {:.1} is too low", avg_mcts);
}

fn resolve_auto(plugin: &CarcassonnePlugin, state: &mut SimulationState<CarcassonneState>) {
    let mut max_auto = 50;
    while state.phase.auto_resolve && state.game_over.is_none() && max_auto > 0 {
        max_auto -= 1;
        let pid = if let Some(pi) = state.phase.metadata.get("player_index").and_then(|v| v.as_u64())
        {
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
