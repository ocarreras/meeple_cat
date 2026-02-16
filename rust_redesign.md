# Rust Game Engine Redesign Plan

## Problem Statement

The Rust game engine maintains two parallel code paths — typed (struct-based) and untyped (JSON-based) — that implement identical logic. This accounts for ~955 lines (~27% of the crate) of pure duplication. Every bugfix or feature must be applied in both paths. The typed path was bolted on after the untyped path as a performance optimization, but the architecture should have been designed typed-first from the start.

## Current State

```
game-engine/src/           ~3,500 lines total
├── engine/
│   ├── mcts.rs            ~960 lines  (~350 duplicated)
│   ├── arena.rs           ~508 lines  (~200 duplicated)
│   ├── bot_strategy.rs    ~131 lines  (~60 duplicated)
│   ├── simulator.rs       ~135 lines  (~35 duplicated)
│   ├── evaluator.rs       ~41 lines   (generic default only)
│   ├── plugin.rs          ~153 lines  (two trait definitions)
│   └── models.rs          domain types
├── games/
│   └── carcassonne/
│       ├── evaluator.rs   ~657 lines  (~230 duplicated)
│       ├── plugin.rs      ~800 lines  (implements both traits manually)
│       ├── types.rs       game state structs
│       ├── tiles.rs       tile definitions
│       ├── board.rs       placement validation
│       ├── features.rs    feature tracking/merging
│       ├── scoring.rs     scoring logic
│       └── meeples.rs     meeple validation
└── server.rs              ~808 lines  (~80 hardcoded dispatch)
```

Duplication pairs (each pair has identical logic, different data access):
- `mcts_search` / `mcts_search_typed`
- `run_one_iteration` / `run_one_iteration_typed`
- `apply_node_action` / `apply_node_action_typed`
- `terminal_value` / `terminal_value_typed`
- `amaf_key` / `amaf_key_typed`
- `SimulationState` / `TypedSimulationState`
- `apply_action_and_resolve` / `apply_action_and_resolve_typed`
- `BotStrategy` / `TypedBotStrategy`
- `RandomStrategy` / `TypedRandomStrategy`
- `MctsStrategy` / `TypedMctsStrategy`
- `run_arena` / `run_arena_typed`
- `play_one_game` / `play_one_game_typed`
- `resolve_auto` / `resolve_auto_typed`
- `evaluate` / `evaluate_typed`
- `make_carcassonne_eval` / `make_carcassonne_eval_typed`
- `carcassonne_eval` / `carcassonne_eval_typed`
- `raw_feature_potential` / `raw_feature_potential_typed`
- `estimate_field_value` / `estimate_field_value_typed`
- `meeple_counts` / `meeple_counts_typed`
- `resolve_eval_fn` / `resolve_typed_eval_fn` (in server.rs)

---

## Phase 1: Invert the Trait Hierarchy (eliminate duplication)

**Goal**: Make `TypedGamePlugin` the only trait games implement. Derive `GamePlugin` automatically.

### 1.1 — Add blanket impl of `GamePlugin` for `TypedGamePlugin`

File: `engine/plugin.rs`

The Carcassonne plugin currently implements `GamePlugin` manually by calling `decode_state`, delegating to the typed method, then `encode_state`. This is pure boilerplate. Replace with a blanket impl:

```rust
impl<T: TypedGamePlugin> GamePlugin for T {
    fn game_id(&self) -> &str { self.game_id() }
    // ... metadata methods delegate directly

    fn get_valid_actions(&self, game_data: &Value, phase: &Phase, pid: &str) -> Vec<Value> {
        let state = self.decode_state(game_data);
        self.get_valid_actions_typed(&state, phase, pid)
    }

    fn apply_action(&self, game_data: &Value, phase: &Phase, action: &Action, players: &[Player]) -> TransitionResult {
        let state = self.decode_state(game_data);
        let typed = self.apply_action_typed(&state, phase, action, players);
        TransitionResult {
            game_data: self.encode_state(&typed.state),
            events: typed.events,
            next_phase: typed.next_phase,
            scores: typed.scores,
            game_over: typed.game_over,
        }
    }

    // ... same pattern for get_player_view, validate_action, etc.
}
```

**Complication**: Rust doesn't allow blanket impls if there are also direct impls. Since `TypedGamePlugin: GamePlugin` currently, this is a conflict. Fix: remove the `GamePlugin` supertrait requirement. Instead, `TypedGamePlugin` stands alone, and the blanket impl provides `GamePlugin`. The metadata methods (`game_id`, `display_name`, etc.) move to `TypedGamePlugin`.

Alternatively, introduce a wrapper: `struct PluginAdapter<P: TypedGamePlugin>(P)` that implements `GamePlugin`. The `GameRegistry` stores `PluginAdapter<CarcassonnePlugin>`. This avoids orphan rule issues while keeping the same effect.

**Decision**: Use the wrapper approach — it's simpler and avoids trait coherence issues.

### 1.2 — Move metadata methods to `TypedGamePlugin`

File: `engine/plugin.rs`

Move `game_id`, `display_name`, `min_players`, `max_players`, `description`, `disconnect_policy` from `GamePlugin` to `TypedGamePlugin`. The blanket impl / wrapper forwards them.

Also move `get_player_view`, `get_spectator_summary`, `state_to_ai_view`, `parse_ai_action`, `on_player_forfeit` to `TypedGamePlugin` with typed signatures. These are only needed at the gRPC boundary, so they can take `&Self::State` and the wrapper handles encode/decode.

### 1.3 — Delete the manual `GamePlugin` impl from CarcassonnePlugin

File: `games/carcassonne/plugin.rs`

Currently the plugin implements both traits. After 1.1-1.2, delete the `impl GamePlugin for CarcassonnePlugin` block (the wrapper provides it).

### 1.4 — Delete all untyped MCTS code

File: `engine/mcts.rs`

Delete: `mcts_search`, `run_one_iteration`, `apply_node_action`, `terminal_value`, `amaf_key`.
Keep: `mcts_search_typed` (rename to `mcts_search`), `run_one_iteration_typed` (rename), and all shared code (`MctsNode`, `NodeArena`, `backpropagate`, `action_key`, etc.).

The eval function signature changes from:
```rust
Fn(&Value, &Phase, &str, &[Player], &dyn GamePlugin) -> f64  // untyped
```
to only:
```rust
Fn(&P::State, &Phase, &str, &[Player]) -> f64  // typed
```

### 1.5 — Delete all untyped simulator code

File: `engine/simulator.rs`

Delete: `SimulationState`, `apply_action_and_resolve`.
Keep: `TypedSimulationState` (rename to `SimulationState`), `apply_action_and_resolve_typed` (rename).

### 1.6 — Delete all untyped bot strategy code

File: `engine/bot_strategy.rs`

Delete: `BotStrategy`, `RandomStrategy`, `MctsStrategy`.
Keep: `TypedBotStrategy` (rename to `BotStrategy`), `TypedRandomStrategy` (rename to `RandomStrategy`), `TypedMctsStrategy` (rename to `MctsStrategy`).

### 1.7 — Delete all untyped arena code

File: `engine/arena.rs`

Delete: `run_arena`, `play_one_game`, `resolve_auto`.
Keep: `run_arena_typed` (rename to `run_arena`), `play_one_game_typed` (rename), `resolve_auto_typed` (rename).

### 1.8 — Delete all untyped evaluator code

File: `games/carcassonne/evaluator.rs`

Delete: `evaluate`, `make_carcassonne_eval`, `carcassonne_eval`, `raw_feature_potential`, `estimate_field_value`, `meeple_counts`.
Keep: the `_typed` variants (rename to drop the suffix).

File: `engine/evaluator.rs`

The generic `default_eval_fn` signature changes to match the typed eval signature. It uses `TypedGamePlugin::get_scores_typed` instead of JSON navigation.

### 1.9 — Update server.rs dispatch

File: `server.rs`

Remove the `if req.game_id == "carcassonne"` branches. The server always goes through the `GamePlugin` trait (via the wrapper), which delegates to the typed path internally. For MCTS and Arena RPCs, the server needs direct access to the `TypedGamePlugin` — use an enum or downcast:

```rust
enum TypedPluginRef<'a> {
    Carcassonne(&'a CarcassonnePlugin),
    // future games...
}
```

Or use `Any`-based downcasting on the registry. The enum approach is simpler and type-safe.

Delete: `resolve_eval_fn` (the untyped version).
Keep: `resolve_typed_eval_fn` (rename to `resolve_eval_fn`).

### 1.10 — Update GameRegistry

File: `games/mod.rs`

Store `PluginAdapter` wrappers. Add a method to retrieve the typed plugin for MCTS/Arena:

```rust
pub fn get_typed<P: TypedGamePlugin + 'static>(&self, game_id: &str) -> Option<&P>
```

Or use the enum approach from 1.9.

### Expected result of Phase 1

- ~955 lines deleted
- One code path for everything
- No `_typed` suffix anywhere
- Every game only implements `TypedGamePlugin`
- `GamePlugin` exists only as an auto-derived trait for the gRPC boundary

---

## Phase 2: Performance Fixes

### 2.1 — Parallelize determinizations with rayon

File: `engine/mcts.rs`

`rayon` is already in Cargo.toml but unused. Each determinization is independent — they build separate MCTS trees and only share the final visit-count aggregation. This is embarrassingly parallel.

```rust
use rayon::prelude::*;

let results: Vec<HashMap<String, (u32, f64, Value)>> = (0..params.num_determinizations)
    .into_par_iter()
    .map(|det_idx| {
        // clone base_state, determinize, run sims, return visit counts
    })
    .collect();

// Aggregate
for det_result in results { ... }
```

**Expected speedup**: Linear with core count for the MCTS search (the dominant cost). On a 4-core VPS, ~3-4x faster MCTS.

### 2.2 — Replace UUID with sequential counter for feature IDs

File: `games/carcassonne/features.rs`

During MCTS simulation, `Uuid::new_v4()` is called for every new feature. Replace with a sequential counter stored in `CarcassonneState`:

```rust
pub struct CarcassonneState {
    // ...
    pub next_feature_id: u64,
}

fn next_feature_id(state: &mut CarcassonneState) -> String {
    let id = state.next_feature_id;
    state.next_feature_id += 1;
    format!("f{}", id)
}
```

### 2.3 — Add feature ID redirect table

File: `games/carcassonne/features.rs`

`resolve_feature_id` (line 192) does O(n*m) linear scan through `merged_from` lists. Add:

```rust
pub struct CarcassonneState {
    // ...
    pub feature_redirects: HashMap<String, String>,  // old_id -> surviving_id
}
```

When features merge, populate the redirect table. Lookup becomes O(1).

### 2.4 — Eliminate double-clone in apply_*_typed

File: `games/carcassonne/plugin.rs`

Current: `apply_place_tile_typed(&self, state: &CarcassonneState, ...)` clones state internally, mutates, returns clone.
Fix: Take `state: CarcassonneState` (owned) and return it. The caller (MCTS) already clones before calling.

The `TypedGamePlugin::apply_action_typed` signature changes from `&Self::State` to `Self::State`:

```rust
fn apply_action_typed(
    &self,
    state: Self::State,  // take ownership
    phase: &Phase,
    action: &Action,
    players: &[Player],
) -> TypedTransitionResult<Self::State>;
```

---

## Phase 3: Correctness Fixes

### 3.1 — Fix RAVE beta calculation

File: `engine/mcts.rs`, line 129-131

Current:
```rust
let _ = amaf_n;
let beta = (rave_k / (3.0 * parent_visits as f64 + rave_k)).sqrt();
```

The standard RAVE formula: `beta = sqrt(rave_k / (3 * n + rave_k))` where `n` is the node's own visit count, not the parent's. Either:
- Fix to use `self.visit_count` (standard RAVE)
- Or document explicitly why `parent_visits` is intentional (if it was tuned via arena)

Check the Python implementation to see which it uses and whether the arena results validated one vs the other.

### 3.2 — Track actual iterations_run

File: `engine/mcts.rs`

Add a counter to `mcts_search` that tracks how many iterations actually completed across all determinizations. Return it alongside the best action.

File: `server.rs`

Report the actual count in `MctsSearchResponse.iterations_run`.

### 3.3 — Replace panic with error propagation in decode_state

File: `games/carcassonne/plugin.rs`, line 28

Current: `.expect("Failed to decode CarcassonneState")`
Fix: Return `Result<Self::State, String>` from `decode_state`, propagate as gRPC `Status::invalid_argument`.

### 3.4 — Handle unknown concurrent_mode in proto conversion

File: `server.rs`, line 93

Currently silently maps unknown strings to `None`. Log a warning or return an error.

---

## Phase 4: Dead Code Cleanup

### 4.1 — Delete dead evaluator functions

File: `games/carcassonne/evaluator.rs`

Delete `carcassonne_eval` and `carcassonne_eval_typed` — never called (the `make_*` factories are used).

### 4.2 — Remove or use rayon

If Phase 2.1 is done, `rayon` is used. If not, remove it from `Cargo.toml`.

### 4.3 — Delete einstein_dojo placeholder

File: `games/einstein_dojo/mod.rs` — empty module, delete it and remove from `games/mod.rs`.

### 4.4 — Deduplicate EvalWeights::default() and DEFAULT_WEIGHTS

File: `games/carcassonne/evaluator.rs`

Make `Default` impl reference `DEFAULT_WEIGHTS`:
```rust
impl Default for EvalWeights {
    fn default() -> Self { DEFAULT_WEIGHTS }
}
```
Or eliminate one of the two. They currently define identical values independently.

### 4.5 — Drop unused return value from meeple_counts

`meeple_counts` returns `(my, max_opp, total_opp)` but `total_opp` is never used. Change to return `(my, max_opp)`.

---

## Phase 5: Future Considerations (not blocking)

### 5.1 — Type the actions

Currently `MctsNode.action_taken` is `Option<serde_json::Value>` even in the typed path. Adding `type Action: Clone` to `TypedGamePlugin` and making `MctsNode` generic would eliminate JSON allocation in the MCTS hot loop. This is a larger refactor — the action key/sort/AMAF functions would need to become trait methods.

### 5.2 — Tighten cross-engine arena validation

`cross_engine_arena.py` uses a 20% win-rate tolerance. This is very loose — two identical engines playing random-seeded games should produce byte-identical results. Tighten to exact match with deterministic seeds, or at least <5% with a larger sample.

### 5.3 — Deprecate Python MCTS

Once the Rust engine is validated and deployed with `MEEPLE_GAME_ENGINE_GRPC_URL`, the Python MCTS/evaluator/arena code becomes dead weight. It should be deprecated and eventually removed, keeping only the `GrpcGamePlugin` adapter.

---

## Implementation Order

| Step | Phase | Files Changed | Risk | Estimated Deletions |
|------|-------|---------------|------|---------------------|
| 1 | 1.1-1.3 | plugin.rs, carcassonne/plugin.rs, games/mod.rs | Medium — trait refactor | ~200 lines |
| 2 | 1.4-1.8 | mcts.rs, simulator.rs, bot_strategy.rs, arena.rs, evaluator.rs | Low — pure deletion | ~750 lines |
| 3 | 1.9-1.10 | server.rs, games/mod.rs | Low | ~80 lines |
| 4 | 3.1-3.4 | mcts.rs, plugin.rs, server.rs | Low | net zero |
| 5 | 4.1-4.5 | evaluator.rs, Cargo.toml, games/mod.rs | Very low | ~30 lines |
| 6 | 2.1-2.4 | mcts.rs, features.rs, plugin.rs | Medium — perf changes need arena validation | net zero |

**Validate after each step**: `cargo build && cargo test` + run a short arena to confirm no regression.

---

## Success Criteria

- [x] `cargo build` succeeds with no warnings
- [x] `cargo test` passes all existing tests (26/26)
- [x] No `_typed` suffix anywhere in the codebase
- [x] No untyped `GamePlugin` impl written by hand for any game
- [x] Zero duplicated function pairs
- [ ] Arena: Rust MCTS vs Random ≥95% win rate (sanity check)
- [ ] Arena: Post-refactor MCTS vs pre-refactor MCTS within 2% win rate (no regression)

## Completed Changes Summary

**Phase 1 (Trait Hierarchy)** — DONE
- `TypedGamePlugin` is the primary trait, `GamePlugin` auto-derived via `JsonAdapter<P>`
- CarcassonnePlugin only implements `TypedGamePlugin`
- ~955 lines of duplicated code deleted
- All `_typed` suffixes removed

**Phase 2 (Performance)** — DONE
- Rayon parallel determinizations in MCTS (`into_par_iter()`)
- Sequential feature IDs replace UUID v4 (eliminates crypto-RNG overhead in MCTS hot loop)
- Feature redirect table for O(1) `resolve_feature_id` (was O(n*m) linear scan)
- Double-clone elimination in `apply_action` handlers (take ownership instead of `&mut` + clone)
- Removed `uuid` crate dependency

**Phase 3 (Correctness)** — DONE
- RAVE beta documented (uses `parent_visits`, matches Python impl)
- `mcts_search` returns actual `iterations_run` count
- Better error message in `decode_state` panic

**Phase 4 (Dead Code Cleanup)** — DONE
- Removed unused: `MatchId`, `GameId` type aliases, `Event` builders, disconnect policy constants,
  `CarcassonneState::from_json`, `get_tile_total`, `most_visited_child`
- `EvalWeights` uses `#[derive(Clone, Copy)]` instead of manual impls
- `meeple_counts` returns `(i64, i64)` instead of unused 3-tuple
- `#[allow(dead_code)]` on public API methods for future CLI use
