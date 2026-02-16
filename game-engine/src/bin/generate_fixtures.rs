//! Fixture generator for benchmarks.
//!
//! Plays deterministic games and captures state snapshots at specific
//! tile-placement counts. Run with:
//!
//!     cargo run --bin generate_fixtures

use std::fs;
use std::path::PathBuf;

use meeple_game_engine::engine::models::*;
use meeple_game_engine::engine::plugin::TypedGamePlugin;
use meeple_game_engine::engine::simulator::{apply_action_and_resolve, SimulationState};
use meeple_game_engine::games::carcassonne::plugin::CarcassonnePlugin;

const SEEDS: [u64; 3] = [42, 123, 999];
const CHECKPOINTS: [usize; 4] = [5, 15, 30, 50];

fn make_players() -> Vec<Player> {
    (0..2)
        .map(|i| Player {
            player_id: format!("p{}", i),
            display_name: format!("Player {}", i),
            seat_index: i as i32,
            is_bot: true,
            bot_id: None,
        })
        .collect()
}

fn resolve_auto(
    plugin: &CarcassonnePlugin,
    sim: &mut SimulationState<meeple_game_engine::games::carcassonne::types::CarcassonneState>,
) {
    let mut max_auto = 50;
    while sim.phase.auto_resolve && sim.game_over.is_none() && max_auto > 0 {
        max_auto -= 1;
        let pid = if let Some(pi) = sim.phase.metadata.get("player_index").and_then(|v| v.as_u64())
        {
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

fn main() {
    let fixtures_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("benches/fixtures");
    fs::create_dir_all(&fixtures_dir).expect("Failed to create fixtures directory");

    let plugin = CarcassonnePlugin;
    let players = make_players();

    let mut total_generated = 0;

    for &seed in &SEEDS {
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

        // Resolve initial auto phases (draws first tile)
        resolve_auto(&plugin, &mut sim);

        let mut remaining_checkpoints: Vec<usize> =
            CHECKPOINTS.iter().copied().collect();

        let max_iterations = 500;
        for _ in 0..max_iterations {
            if sim.game_over.is_some() {
                break;
            }
            if remaining_checkpoints.is_empty() {
                break;
            }

            if sim.phase.auto_resolve {
                resolve_auto(&plugin, &mut sim);
                continue;
            }

            // Count tiles placed (board tiles minus starting tile)
            let tiles_placed = sim.state.board.tiles.len() - 1;

            // Check if we're at a checkpoint and in place_tile phase
            if sim.phase.name == "place_tile" {
                if let Some(pos) = remaining_checkpoints
                    .iter()
                    .position(|&cp| cp == tiles_placed)
                {
                    let checkpoint = remaining_checkpoints.remove(pos);
                    let acting_pid = sim.phase.expected_actions[0].player_id.clone();

                    let fixture = serde_json::json!({
                        "state": plugin.encode_state(&sim.state),
                        "phase": sim.phase,
                        "player_id": acting_pid,
                        "tiles_placed": checkpoint,
                        "open_positions_count": sim.state.board.open_positions.len(),
                        "seed": seed,
                    });

                    let filename = format!("state_{}_t{}.json", seed, checkpoint);
                    let path = fixtures_dir.join(&filename);
                    let json = serde_json::to_string_pretty(&fixture)
                        .expect("Failed to serialize fixture");
                    fs::write(&path, &json).expect("Failed to write fixture");

                    total_generated += 1;
                    eprintln!(
                        "  Generated {} (tiles={}, open_positions={}, board_tiles={})",
                        filename,
                        checkpoint,
                        sim.state.board.open_positions.len(),
                        sim.state.board.tiles.len(),
                    );
                }
            }

            // Play: pick first valid action
            let acting_pid = if !sim.phase.expected_actions.is_empty() {
                sim.phase.expected_actions[0].player_id.clone()
            } else {
                break;
            };

            let valid = plugin.get_valid_actions(&sim.state, &sim.phase, &acting_pid);
            if valid.is_empty() {
                break;
            }

            let action_type = sim.phase.expected_actions[0].action_type.clone();
            let action = Action {
                action_type,
                player_id: acting_pid,
                payload: valid[0].clone(),
            };
            apply_action_and_resolve(&plugin, &mut sim, &action);
        }

        // Report any checkpoints we couldn't reach
        for cp in &remaining_checkpoints {
            let tiles_placed = sim.state.board.tiles.len() - 1;
            eprintln!(
                "  Warning: seed={} couldn't reach checkpoint {} (game ended at {} tiles)",
                seed, cp, tiles_placed
            );
        }
    }

    eprintln!("\nGenerated {} fixture files in {:?}", total_generated, fixtures_dir);
}
