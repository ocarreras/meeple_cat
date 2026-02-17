# 09 — Rust MCTS Engine

## Overview

The Rust game engine (`game-engine/`) provides a high-performance MCTS (Monte Carlo Tree Search) implementation that communicates with the Python backend via gRPC. It supports any game implementing the `TypedGamePlugin` trait, with Carcassonne and TicTacToe currently implemented.

## Performance: Rust vs Python

Benchmarked on Carcassonne with identical MCTS parameters (500 simulations, 3 determinizations, UCT exploration constant 1.41).

### Game Timing

| Engine | Avg time/game | Speedup |
|--------|---------------|---------|
| Python MCTS self-play | 81.3s | 1x |
| Rust MCTS self-play | 3.4 - 4.6s | ~20x |
| Cross-engine (per game) | 34.7s | bottlenecked by Python state transitions |

### Play Strength (Cross-Engine, 50 games)

| Engine | Win rate | 95% CI | Avg score |
|--------|----------|--------|-----------|
| Rust MCTS | 82.0% (41 wins) | 69.2% - 90.2% | 95.0 +/- 22.1 |
| Python MCTS | 18.0% (9 wins) | 9.8% - 30.8% | 72.9 +/- 17.0 |

Rust is stronger because it uses value-based tie-breaking at the root (selecting by highest average value when visit counts tie), which is a better policy than Python's insertion-order tie-breaking.

### Self-Play Score Totals

| Engine | Avg total score (A+B) |
|--------|-----------------------|
| Python | 165.3 |
| Rust | 171.8 - 211.4 |

## Architecture

```
Python backend (FastAPI)
  |
  |-- gRPC (protobuf) --> Rust game engine (tonic)
  |                          |-- MCTS search (rayon parallel determinizations)
  |                          |-- TypedGamePlugin (no JSON in hot path)
  |                          |-- NodeArena (cache-friendly node allocation)
  |
  |-- Python MCTS (fallback, no gRPC dependency)
```

### Key Files

| File | Purpose |
|------|---------|
| `game-engine/src/engine/mcts.rs` | MCTS core: search, UCT selection, progressive widening, RAVE |
| `game-engine/src/engine/simulator.rs` | Action application and auto-resolve loop |
| `game-engine/src/engine/arena.rs` | Bot-vs-bot arena runner |
| `game-engine/src/engine/bot_strategy.rs` | Strategy trait, MctsStrategy, RandomStrategy |
| `game-engine/src/engine/plugin.rs` | TypedGamePlugin trait, JsonAdapter |
| `game-engine/src/server.rs` | gRPC server (tonic) |
| `game-engine/src/games/carcassonne/` | Carcassonne plugin (board, tiles, features, scoring, evaluator) |
| `game-engine/src/games/tictactoe/` | TicTacToe plugin (used for MCTS isolation testing) |

### MCTS Parameters

```rust
pub struct MctsParams {
    pub num_simulations: usize,       // default: 800
    pub time_limit_ms: f64,           // default: 5000
    pub exploration_constant: f64,    // default: 1.41 (sqrt(2))
    pub num_determinizations: usize,  // default: 4
    pub pw_c: f64,                    // progressive widening constant, default: 2.0
    pub pw_alpha: f64,                // progressive widening exponent, default: 0.5
    pub use_rave: bool,               // AMAF/RAVE, default: false
    pub rave_k: f64,                  // RAVE equivalence parameter, default: 500.0
}
```

## Root Action Selection

The MCTS aggregates visit counts and values across determinizations, then selects the action with the most visits. When multiple actions tie in visit count (common with wide progressive widening), ties are broken by **highest average value** (`total_value / visit_count`).

This is critical for play quality. With `pw_c >= 2`, visits spread across many children (~11 visits each for 44 children with 500 sims), making ties frequent. Naive tie-breaking (alphabetical, random) degrades play to near-random quality.

## Running Tests

```bash
# Full test suite (includes MCTS arena tests, ~3 min in release)
cd game-engine && cargo test --release

# Quick unit tests only (~10s)
cd game-engine && cargo test --release --lib -- --skip arena --skip mcts_per_game

# Cross-engine comparison (requires both engines, ~30 min for 50 games)
cd backend && NUM_GAMES=50 uv run python cross_engine_arena.py

# TicTacToe isolation test (verifies MCTS correctness on solved game)
cd backend && uv run python cross_engine_tictactoe.py
```

## Game Logic Equivalence

Rust and Python Carcassonne implementations produce identical game states:

- Replay comparison test: 71-turn game trace, 0 divergences
- Board fuzz test: 50 random games, 7000+ moves, all edge-consistent
- Evaluator comparison: 15 mid-game states, 0.000000 difference
