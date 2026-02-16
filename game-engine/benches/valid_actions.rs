//! Criterion benchmarks for the get_valid_actions hot path.
//!
//! Run with:
//!     cargo bench --bench valid_actions
//!
//! Generate fixtures first:
//!     cargo run --bin generate_fixtures

use std::fs;
use std::path::PathBuf;

use criterion::{BenchmarkId, Criterion, criterion_group, criterion_main};

use meeple_game_engine::engine::models::Phase;
use meeple_game_engine::engine::plugin::TypedGamePlugin;
use meeple_game_engine::games::carcassonne::board::{can_place_tile, get_rotated_edge};
use meeple_game_engine::games::carcassonne::plugin::CarcassonnePlugin;
use meeple_game_engine::games::carcassonne::types::CarcassonneState;

#[allow(dead_code)]
struct Fixture {
    label: String,
    state: CarcassonneState,
    phase: Phase,
    player_id: String,
    tiles_placed: usize,
}

fn load_fixtures() -> Vec<Fixture> {
    let fixtures_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("benches/fixtures");

    let mut fixtures = Vec::new();

    let mut entries: Vec<_> = fs::read_dir(&fixtures_dir)
        .unwrap_or_else(|_| {
            panic!(
                "Fixtures directory not found at {:?}. Run `cargo run --bin generate_fixtures` first.",
                fixtures_dir
            )
        })
        .filter_map(|e| e.ok())
        .filter(|e| {
            e.path()
                .extension()
                .map(|ext| ext == "json")
                .unwrap_or(false)
        })
        .collect();

    entries.sort_by_key(|e| e.file_name());

    for entry in entries {
        let path = entry.path();
        let json_str = fs::read_to_string(&path)
            .unwrap_or_else(|_| panic!("Failed to read fixture {:?}", path));
        let fixture_json: serde_json::Value =
            serde_json::from_str(&json_str).unwrap_or_else(|_| panic!("Invalid JSON in {:?}", path));

        let plugin = CarcassonnePlugin;
        let state = plugin.decode_state(&fixture_json["state"]);
        let phase: Phase = serde_json::from_value(fixture_json["phase"].clone())
            .unwrap_or_else(|_| panic!("Failed to decode phase from {:?}", path));
        let player_id = fixture_json["player_id"]
            .as_str()
            .unwrap_or("p0")
            .to_string();
        let tiles_placed = fixture_json["tiles_placed"].as_u64().unwrap_or(0) as usize;
        let seed = fixture_json["seed"].as_u64().unwrap_or(0);

        let label = format!("s{}_t{}", seed, tiles_placed);

        fixtures.push(Fixture {
            label,
            state,
            phase,
            player_id,
            tiles_placed,
        });
    }

    assert!(
        !fixtures.is_empty(),
        "No fixtures found. Run `cargo run --bin generate_fixtures` first."
    );

    fixtures
}

fn bench_get_valid_actions(c: &mut Criterion) {
    let fixtures = load_fixtures();
    let plugin = CarcassonnePlugin;

    let mut group = c.benchmark_group("get_valid_actions");

    for fixture in &fixtures {
        group.bench_with_input(
            BenchmarkId::new("get_valid_actions", &fixture.label),
            fixture,
            |b, f| {
                b.iter(|| {
                    plugin.get_valid_actions(&f.state, &f.phase, &f.player_id)
                });
            },
        );
    }

    group.finish();
}

fn bench_can_place_tile(c: &mut Criterion) {
    let fixtures = load_fixtures();

    let mut group = c.benchmark_group("can_place_tile");

    for fixture in &fixtures {
        let current_tile = match &fixture.state.current_tile {
            Some(t) => t.clone(),
            None => continue,
        };

        // Bench checking all open positions × 4 rotations
        group.bench_with_input(
            BenchmarkId::new("all_positions", &fixture.label),
            fixture,
            |b, f| {
                b.iter(|| {
                    let mut count = 0u32;
                    for pos_key in &f.state.board.open_positions {
                        for rotation in [0u32, 90, 180, 270] {
                            if can_place_tile(
                                &f.state.board.tiles,
                                &current_tile,
                                pos_key,
                                rotation,
                            ) {
                                count += 1;
                            }
                        }
                    }
                    count
                });
            },
        );
    }

    group.finish();
}

fn bench_get_rotated_edge(c: &mut Criterion) {
    let fixtures = load_fixtures();

    let mut group = c.benchmark_group("get_rotated_edge");

    for fixture in &fixtures {
        let current_tile = match &fixture.state.current_tile {
            Some(t) => t.clone(),
            None => continue,
        };

        // Bench calling get_rotated_edge for all 4 directions × 4 rotations
        group.bench_with_input(
            BenchmarkId::new("16_calls", &fixture.label),
            &current_tile,
            |b, tile_id| {
                b.iter(|| {
                    let mut last = meeple_game_engine::games::carcassonne::types::EdgeType::Field;
                    for rotation in [0u32, 90, 180, 270] {
                        for direction in ["N", "E", "S", "W"] {
                            last = get_rotated_edge(tile_id, rotation, direction);
                        }
                    }
                    last
                });
            },
        );
    }

    group.finish();
}

fn bench_state_clone(c: &mut Criterion) {
    let fixtures = load_fixtures();

    let mut group = c.benchmark_group("state_clone");

    for fixture in &fixtures {
        group.bench_with_input(
            BenchmarkId::new("clone", &fixture.label),
            &fixture.state,
            |b, state| {
                b.iter(|| state.clone());
            },
        );
    }

    group.finish();
}

criterion_group!(
    benches,
    bench_get_valid_actions,
    bench_can_place_tile,
    bench_get_rotated_edge,
    bench_state_clone,
);
criterion_main!(benches);
