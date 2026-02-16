# Rust MCTS Quality Analysis

## Status: IN PROGRESS

The Rust MCTS engine produces significantly weaker play than the Python MCTS in cross-engine arena testing. This document captures all findings so far to guide continued debugging after the Rust codebase cleanup.

---

## Test Results

### Before evaluator fix (missing `_estimate_nearby_city_potential`)
- **Python-MCTS: 9 wins, Rust-MCTS: 1 win** (10 games, 500 sims x 3 dets)
- Avg scores: Python 78.5 vs Rust 61.3

### After evaluator fix
- **10-game arena**: Python 6-4 Rust (avg 68.8 vs 57.9) — looked promising
- **50-game arena**: Python 43-7 Rust (avg 69.8 vs 50.2, 86% vs 14%) — **still heavily lopsided**

### Baseline sanity checks (all passed)
- Random vs Random: identical total scores (~37 each) — game logic is correct
- Rust MCTS vs Random: 10-0 (avg 40.4 vs 14.4) — MCTS is functional
- Python MCTS vs Random: 10-0 (avg 61.4 vs 28.1) — much stronger
- Rust-native MCTS vs MCTS (internal arena): avg 31 each — symmetric
- Python MCTS vs MCTS (internal arena): avg ~67 each — symmetric but much higher scores

---

## Fixes Already Applied

### 1. Missing `_estimate_nearby_city_potential` in Rust evaluator (FIXED)
- **File**: `game-engine/src/games/carcassonne/evaluator.rs`
- Python's `_estimate_field_value` values fields adjacent to nearly-complete cities via `_estimate_nearby_city_potential`. Rust was missing this entirely.
- **Impact**: Moderate improvement (10-game result improved from 9-1 to 6-4), but 50-game test shows gap persists.

### 2. `max_children` missing `max(1,...)` floor (FIXED)
- **File**: `game-engine/src/engine/mcts.rs`
- Python: `max(1, int(pw_c * max(1, visit_count) ** pw_alpha))`
- Rust was: `(pw_c * (visit_count.max(1) as f64).powf(pw_alpha)) as usize`
- Now: `(pw_c * (visit_count.max(1) as f64).powf(pw_alpha)).max(1.0) as usize`
- **Impact**: Doesn't trigger with default `pw_c=2.0`, but prevents latent bugs.

### 3. Arena `exploration_constant` hardcoded to 0.0 (DOCUMENTED)
- **File**: `game-engine/src/server.rs` (RunArena handler)
- `ArenaStrategyConfig` proto lacks `exploration_constant` field, so server passes `0.0` to `build_mcts_params`, which falls back to default 1.41.
- **Impact**: None for current usage (default is correct), but prevents tuning in arena mode.

### 4. Earlier fixes (from initial integration)
- `rng_state` type: `Option<u64>` → `serde_json::Value` (Python's `random.getstate()` is a complex nested list)
- Empty players in gRPC: `GrpcMctsStrategy` sends `players=[]`; added reconstruction from `game_data["scores"]`
- Missing default eval: `resolve_typed_eval_fn("default")` was returning `None`; added `DEFAULT_WEIGHTS` static

---

## Known Issues Still Open

### 5. RAVE Beta Calculation — `amaf_n` is unused

In `mcts.rs:129-131`:
```rust
let _ = amaf_n; // used in beta calculation below
let beta = (rave_k / (3.0 * parent_visits as f64 + rave_k)).sqrt();
```

The comment says `amaf_n` is "used in beta calculation below" but it is explicitly suppressed with `let _ = amaf_n`. The beta formula uses `parent_visits` instead of `amaf_n`. This matches the Python implementation's formula:
```python
beta = math.sqrt(rave_k / (3.0 * parent_visits + rave_k))
```

So both use `parent_visits` (not `amaf_n`), meaning this is not a divergence between the two engines. However, the dead code and misleading comment suggest either:
- The original intent was to use `amaf_n` in the beta formula (some RAVE variants do), or
- This is just leftover from development.

**Note**: RAVE is disabled by default (`use_rave=False`), so this doesn't affect the current cross-engine arena tests. But it should be cleaned up.

### 6. Score magnitude gap between engines

Even when both engines play symmetrically against themselves:
- **Rust MCTS vs Rust MCTS**: avg ~31 each (total ~62 per game)
- **Python MCTS vs Python MCTS**: avg ~67 each (total ~134 per game)

This 2x score magnitude difference suggests Rust MCTS plays more conservatively or misses scoring opportunities that Python MCTS finds. This is likely the same root cause as the cross-engine quality gap.

---

## Hypotheses to Investigate (Ranked by Plausibility)

### H1: Evaluation function divergence (HIGH)
Even after the `_estimate_nearby_city_potential` fix, there may be subtle differences in how the Rust typed evaluator computes values compared to Python. A direct eval comparison on identical game states would confirm or rule this out.

**Test**: Write a diagnostic that sends the same game state to both engines and compares eval output values.

### H2: Valid actions divergence during simulation (HIGH)
During MCTS simulation, the Rust `get_valid_actions_typed` may return a different set or count of actions than Python's `get_valid_actions` for intermediate game states deep in the tree. Even one missing or extra action could skew the search.

**Test**: Log action counts at each simulation step and compare between engines.

### H3: Game state divergence in deep simulation (MEDIUM)
The Rust typed game logic may accumulate subtle state differences over many apply_action calls during MCTS simulation. Features, scores, or meeple supply could drift from what Python would produce for the same action sequence.

**Test**: Apply a fixed sequence of actions in both engines and compare resulting game states.

### H4: Action ordering affects progressive widening quality (MEDIUM)
With progressive widening (`pw_c=2.0, pw_alpha=0.5`), only a subset of actions are explored. If Python and Rust enumerate valid actions in different orders (due to HashMap iteration, open_positions ordering, etc.), the "first" actions explored could be systematically better in Python.

**Test**: Compare the first N actions returned by each engine for the same state.

### H5: Performance-related search depth difference (LOW)
The cross-engine arena has Python managing game state and Rust receiving it via gRPC. The gRPC serialization/deserialization overhead might mean Rust completes fewer simulations within the time budget.

**Test**: Log actual simulation count per determinization in both engines.

---

## Debugging Plan (When Resuming)

### Phase 2: TicTacToe Isolation Test
Create a TicTacToe game implementing `TypedGamePlugin` in Rust. Run MCTS on it — MCTS should play near-perfectly in this simple deterministic game. If it doesn't, the MCTS algorithm itself is buggy independent of Carcassonne complexity.

### Phase 3: Direct Eval Comparison
Write a diagnostic script that:
1. Takes a specific Carcassonne game state (mid-game)
2. Calls Python's `_evaluate()` with default weights
3. Sends the same state to Rust via gRPC and gets the typed eval result
4. Compares component-by-component: score_component, potential_component, meeple_component, field_component

### Phase 4: Simulation Trace Comparison
Take a specific game state and run a single MCTS iteration in both engines with logging:
1. Valid actions at root (count and first 5)
2. Action selected for expansion
3. Simulation states after each apply_action
4. Final eval value
5. Backpropagated value

---

## Files of Interest

| File | Role |
|------|------|
| `game-engine/src/engine/mcts.rs` | Rust MCTS (typed + JSON paths) |
| `backend/src/engine/mcts.py` | Python MCTS |
| `game-engine/src/games/carcassonne/evaluator.rs` | Rust eval (typed + JSON) |
| `backend/src/games/carcassonne/evaluator.py` | Python eval |
| `game-engine/src/games/carcassonne/plugin.rs` | Rust plugin (TypedGamePlugin impl) |
| `game-engine/src/engine/simulator.rs` | Rust simulator (auto-resolve loop) |
| `game-engine/src/server.rs` | gRPC server, param building |
| `backend/cross_engine_arena.py` | Cross-engine test harness |
| `backend/src/engine/bot_strategy.py` | GrpcMctsStrategy (Python→Rust bridge) |
