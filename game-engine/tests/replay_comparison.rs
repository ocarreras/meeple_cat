//! Replay a Python-generated game trace through the Rust Carcassonne plugin
//! and compare valid actions + scores at every step.
//!
//! Run with:
//!     cargo test --test replay_comparison -- --nocapture
//!
//! Generate fixture first (from backend/):
//!     uv run python generate_game_trace.py

use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

use meeple_game_engine::engine::models::*;
use meeple_game_engine::engine::plugin::TypedGamePlugin;
use meeple_game_engine::engine::simulator::{apply_action_and_resolve, SimulationState};
use meeple_game_engine::games::carcassonne::evaluator::{make_carcassonne_eval, DEFAULT_WEIGHTS};
use meeple_game_engine::games::carcassonne::plugin::CarcassonnePlugin;

fn load_trace() -> serde_json::Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/game_trace.json");
    let json_str = fs::read_to_string(&path)
        .unwrap_or_else(|_| panic!("Fixture not found at {:?}. Run generate_game_trace.py first.", path));
    serde_json::from_str(&json_str).expect("Invalid JSON in game trace fixture")
}

fn make_players() -> Vec<Player> {
    vec![
        Player {
            player_id: "p0".into(),
            display_name: "P0".into(),
            seat_index: 0,
            is_bot: true,
            bot_id: None,
        },
        Player {
            player_id: "p1".into(),
            display_name: "P1".into(),
            seat_index: 1,
            is_bot: true,
            bot_id: None,
        },
    ]
}

/// Resolve auto-resolve phases (draw_tile, score_check, etc.)
fn resolve_auto(plugin: &CarcassonnePlugin, sim: &mut SimulationState<<CarcassonnePlugin as TypedGamePlugin>::State>) {
    let mut max_auto = 50;
    while sim.phase.auto_resolve && sim.game_over.is_none() && max_auto > 0 {
        max_auto -= 1;
        let pid = if !sim.phase.expected_actions.is_empty() {
            sim.phase.expected_actions[0].player_id.clone()
        } else if let Some(pi) = sim.phase.metadata.get("player_index").and_then(|v| v.as_u64()) {
            let idx = pi as usize;
            if idx < sim.players.len() {
                sim.players[idx].player_id.clone()
            } else {
                "system".into()
            }
        } else {
            "system".into()
        };

        let synthetic = Action {
            action_type: sim.phase.name.clone(),
            player_id: pid,
            payload: serde_json::json!({}),
        };
        apply_action_and_resolve(plugin, sim, &synthetic);
    }
}

/// Extract (x, y, rotation) tuples from valid tile placement actions, sorted.
fn extract_tile_placements(actions: &[serde_json::Value]) -> Vec<(i64, i64, i64)> {
    let mut placements: Vec<(i64, i64, i64)> = actions
        .iter()
        .map(|a| {
            let x = a["x"].as_i64().unwrap_or(0);
            let y = a["y"].as_i64().unwrap_or(0);
            let rot = a["rotation"].as_i64().unwrap_or(0);
            (x, y, rot)
        })
        .collect();
    placements.sort();
    placements
}

/// Extract meeple spot names from valid meeple actions, sorted.
fn extract_meeple_spots(actions: &[serde_json::Value]) -> Vec<String> {
    let mut spots: Vec<String> = actions
        .iter()
        .filter_map(|a| {
            if a.get("skip").is_some() {
                Some("skip".to_string())
            } else if let Some(spot) = a.get("meeple_spot").and_then(|v| v.as_str()) {
                Some(spot.to_string())
            } else {
                None
            }
        })
        .collect();
    spots.sort();
    spots
}

#[test]
fn test_replay_python_game_trace() {
    let trace = load_trace();
    let plugin = CarcassonnePlugin;
    let players = make_players();

    // Decode initial state from Python-generated JSON
    let initial_state = plugin.decode_state(&trace["initial_state"]);
    let initial_phase: Phase = serde_json::from_value(trace["initial_phase"].clone())
        .expect("Failed to decode initial phase");

    let scores_map: HashMap<String, f64> = players
        .iter()
        .map(|p| (p.player_id.clone(), 0.0))
        .collect();

    let mut sim = SimulationState {
        state: initial_state,
        phase: initial_phase,
        players: players.clone(),
        scores: scores_map,
        game_over: None,
    };

    let turns = trace["turns"].as_array().expect("turns should be array");
    let mut divergences: Vec<String> = Vec::new();
    let mut first_divergence_turn: Option<usize> = None;

    for turn_data in turns {
        let turn_num = turn_data["turn"].as_u64().unwrap() as usize;
        let expected_pid = turn_data["player_id"].as_str().unwrap();
        let tile_drawn = turn_data["tile_drawn"].as_str().unwrap_or("?");

        if sim.game_over.is_some() {
            divergences.push(format!(
                "Turn {}: Rust game already over, Python still playing",
                turn_num
            ));
            break;
        }

        // Handle auto-resolve if needed
        if sim.phase.auto_resolve {
            resolve_auto(&plugin, &mut sim);
        }

        // Verify we're at place_tile phase
        if sim.phase.name != "place_tile" {
            divergences.push(format!(
                "Turn {}: Expected place_tile phase, got '{}'",
                turn_num, sim.phase.name
            ));
            break;
        }

        // Verify correct player
        let rust_pid = &sim.phase.expected_actions[0].player_id;
        if rust_pid != expected_pid {
            divergences.push(format!(
                "Turn {}: Player mismatch: Python={}, Rust={}",
                turn_num, expected_pid, rust_pid
            ));
            break;
        }

        // Verify tile drawn
        let rust_tile = sim.state.current_tile
            .map(|t| meeple_game_engine::games::carcassonne::types::tile_index_to_type(t).to_string())
            .unwrap_or_default();
        if rust_tile != tile_drawn {
            divergences.push(format!(
                "Turn {}: Tile drawn mismatch: Python='{}', Rust='{}'",
                turn_num, tile_drawn, rust_tile
            ));
            if first_divergence_turn.is_none() {
                first_divergence_turn = Some(turn_num);
            }
            // Continue anyway - tile bag may have diverged
        }

        // --- Compare valid tile placements ---
        let rust_tile_valid = plugin.get_valid_actions(&sim.state, &sim.phase, expected_pid);
        let rust_placements = extract_tile_placements(&rust_tile_valid);

        let py_placements_json = turn_data["valid_tile_placements"].as_array().unwrap();
        let py_placements = extract_tile_placements(py_placements_json);

        if rust_placements.len() != py_placements.len() {
            let msg = format!(
                "Turn {} (tile={}): valid_tile_placements count: Python={}, Rust={}",
                turn_num, tile_drawn, py_placements.len(), rust_placements.len()
            );
            divergences.push(msg.clone());
            println!("DIVERGENCE: {}", msg);

            // Show what's different
            let rust_set: std::collections::HashSet<_> = rust_placements.iter().collect();
            let py_set: std::collections::HashSet<_> = py_placements.iter().collect();
            let in_py_not_rust: Vec<_> = py_set.difference(&rust_set).collect();
            let in_rust_not_py: Vec<_> = rust_set.difference(&py_set).collect();
            if !in_py_not_rust.is_empty() {
                println!("  In Python but not Rust: {:?}", in_py_not_rust);
            }
            if !in_rust_not_py.is_empty() {
                println!("  In Rust but not Python: {:?}", in_rust_not_py);
            }

            if first_divergence_turn.is_none() {
                first_divergence_turn = Some(turn_num);
            }
        } else if rust_placements != py_placements {
            let msg = format!(
                "Turn {} (tile={}): valid_tile_placements differ (same count={})",
                turn_num, tile_drawn, rust_placements.len()
            );
            divergences.push(msg.clone());
            println!("DIVERGENCE: {}", msg);
            if first_divergence_turn.is_none() {
                first_divergence_turn = Some(turn_num);
            }
        }

        // --- Apply chosen tile placement ---
        let chosen_tile = turn_data["chosen_tile_placement"].clone();
        let tile_action = Action {
            action_type: "place_tile".into(),
            player_id: expected_pid.to_string(),
            payload: chosen_tile,
        };
        apply_action_and_resolve(&plugin, &mut sim, &tile_action);

        if sim.game_over.is_some() {
            // Game ended during tile placement (shouldn't happen but handle it)
            continue;
        }

        // Verify place_meeple phase
        if sim.phase.name != "place_meeple" {
            divergences.push(format!(
                "Turn {}: Expected place_meeple after tile, got '{}'",
                turn_num, sim.phase.name
            ));
            break;
        }

        // --- Compare valid meeple actions ---
        let rust_meeple_valid = plugin.get_valid_actions(&sim.state, &sim.phase, expected_pid);
        let rust_spots = extract_meeple_spots(&rust_meeple_valid);

        let py_meeple_json = turn_data["valid_meeple_actions"].as_array().unwrap();
        let py_spots = extract_meeple_spots(py_meeple_json);

        if rust_spots != py_spots {
            let msg = format!(
                "Turn {} (tile={}): valid_meeple_spots differ: Python={:?}, Rust={:?}",
                turn_num, tile_drawn, py_spots, rust_spots
            );
            divergences.push(msg.clone());
            println!("DIVERGENCE: {}", msg);
            if first_divergence_turn.is_none() {
                first_divergence_turn = Some(turn_num);
            }
        }

        // --- Apply chosen meeple action ---
        let chosen_meeple = turn_data["chosen_meeple"].clone();
        let meeple_action = Action {
            action_type: "place_meeple".into(),
            player_id: expected_pid.to_string(),
            payload: chosen_meeple,
        };
        apply_action_and_resolve(&plugin, &mut sim, &meeple_action);
        // Auto-resolve: score_check -> draw_tile -> place_tile

        // --- Compare scores ---
        let py_scores = turn_data["scores_after"].as_object().unwrap();
        for (pid, py_score) in py_scores {
            let py_s = py_score.as_f64().unwrap_or(0.0);
            let rust_s = sim.scores.get(pid).copied().unwrap_or(0.0);
            if (py_s - rust_s).abs() > 0.01 {
                let msg = format!(
                    "Turn {} (tile={}): Score mismatch for {}: Python={}, Rust={}",
                    turn_num, tile_drawn, pid, py_s, rust_s
                );
                divergences.push(msg.clone());
                println!("DIVERGENCE: {}", msg);
                if first_divergence_turn.is_none() {
                    first_divergence_turn = Some(turn_num);
                }
            }
        }

        // --- Compare evaluator output ---
        if let (Some(py_eval_p0), Some(py_eval_p1)) = (
            turn_data["eval_p0"].as_f64(),
            turn_data["eval_p1"].as_f64(),
        ) {
            let eval_fn = make_carcassonne_eval(&DEFAULT_WEIGHTS);
            let rust_eval_p0 = eval_fn(&sim.state, &sim.phase, "p0", &players);
            let rust_eval_p1 = eval_fn(&sim.state, &sim.phase, "p1", &players);

            let eval_tol = 0.0001;
            if (py_eval_p0 - rust_eval_p0).abs() > eval_tol {
                let msg = format!(
                    "Turn {} (tile={}): eval_p0 mismatch: Python={:.6}, Rust={:.6} (diff={:.6})",
                    turn_num, tile_drawn, py_eval_p0, rust_eval_p0, (py_eval_p0 - rust_eval_p0).abs()
                );
                divergences.push(msg.clone());
                println!("DIVERGENCE: {}", msg);
                if first_divergence_turn.is_none() {
                    first_divergence_turn = Some(turn_num);
                }
            }
            if (py_eval_p1 - rust_eval_p1).abs() > eval_tol {
                let msg = format!(
                    "Turn {} (tile={}): eval_p1 mismatch: Python={:.6}, Rust={:.6} (diff={:.6})",
                    turn_num, tile_drawn, py_eval_p1, rust_eval_p1, (py_eval_p1 - rust_eval_p1).abs()
                );
                divergences.push(msg.clone());
                println!("DIVERGENCE: {}", msg);
                if first_divergence_turn.is_none() {
                    first_divergence_turn = Some(turn_num);
                }
            }
        }

        // Progress
        let rust_total: f64 = sim.scores.values().sum();
        let py_total = turn_data["total_score_after"].as_f64().unwrap_or(0.0);
        if turn_num % 10 == 0 || !divergences.is_empty() {
            println!(
                "  Turn {:2} [{}] tile={}: Py_total={:.0} Rust_total={:.0} {}",
                turn_num,
                expected_pid,
                tile_drawn,
                py_total,
                rust_total,
                if (py_total - rust_total).abs() < 0.01 { "OK" } else { "MISMATCH" }
            );
        }
    }

    // Final summary
    println!("\n{}", "=".repeat(60));
    println!("REPLAY SUMMARY");
    println!("{}", "=".repeat(60));
    println!("Turns replayed: {}", turns.len());
    println!("Divergences found: {}", divergences.len());

    if let Some(first) = first_divergence_turn {
        println!("First divergence at turn: {}", first);
    }

    if divergences.is_empty() {
        println!("RESULT: PASS — Rust and Python produce identical results");
    } else {
        println!("\nAll divergences:");
        for (i, d) in divergences.iter().enumerate() {
            println!("  {}. {}", i + 1, d);
        }
        println!("\nRESULT: FAIL — {} divergences found", divergences.len());
    }

    // Final scores
    let py_final = trace["final_scores"].as_object().unwrap();
    let py_total: f64 = py_final.values().map(|v| v.as_f64().unwrap_or(0.0)).sum();
    let rust_total: f64 = sim.scores.values().sum();
    println!("\nPython final scores: {:?}", py_final);
    println!("Rust final scores: {:?}", sim.scores);
    println!("Python total: {:.0}", py_total);
    println!("Rust total: {:.0}", rust_total);

    assert!(
        divergences.is_empty(),
        "Found {} divergences between Python and Rust game replay. First at turn {:?}.",
        divergences.len(),
        first_divergence_turn,
    );
}
