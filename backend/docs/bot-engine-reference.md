# Bot Engine Reference — Rust Rewrite Guide

This document captures every algorithmic detail, parameter, edge case, and arena insight from the Python MCTS bot engine. Use it to validate the Rust implementation produces equivalent results.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [MCTS Algorithm](#2-mcts-algorithm)
3. [Progressive Widening](#3-progressive-widening)
4. [RAVE / AMAF](#4-rave--amaf)
5. [Game Simulator](#5-game-simulator)
6. [Carcassonne Heuristic Evaluator](#6-carcassonne-heuristic-evaluator)
7. [Bot Strategies & Registry](#7-bot-strategies--registry)
8. [Arena Runner](#8-arena-runner)
9. [Data Models](#9-data-models)
10. [Game Plugin Protocol](#10-game-plugin-protocol)
11. [Action Key System](#11-action-key-system)
12. [Arena Results & Insights](#12-arena-results--insights)
13. [Invariants & Edge Cases](#13-invariants--edge-cases)
14. [Rust Implementation Notes](#14-rust-implementation-notes)

---

## 1. Architecture Overview

```
engine/
├── mcts.py               # Game-agnostic MCTS with UCT, PW, RAVE
├── game_simulator.py     # Synchronous state advancement
├── bot_strategy.py       # BotStrategy protocol + registry
├── arena.py              # Bot-vs-bot arena runner
├── arena_cli.py          # CLI for arena experiments
├── protocol.py           # GamePlugin protocol (trait)
└── models.py             # Phase, Action, Player, GameResult

games/carcassonne/
└── evaluator.py          # Heuristic evaluation function
```

**Data flow:** Arena/BotRunner → BotStrategy.choose_action() → mcts_search() → _run_one_iteration() loops → eval_fn() at leaves → backpropagate → return best action by visit count.

**Key types:**
- `PlayerId = NewType("PlayerId", str)` — e.g. `"p0"`, `"p1"`
- `game_data: dict` — mutable game state blob owned by the plugin
- `Phase` — current game phase with expected actions
- `Action` — player action with type, player_id, and payload dict

---

## 2. MCTS Algorithm

### 2.1 Entry Point: `mcts_search()`

**All parameters with defaults:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `game_data` | dict | required | Current game state |
| `phase` | Phase | required | Current phase |
| `player_id` | PlayerId | required | Who is deciding |
| `plugin` | GamePlugin | required | Game logic implementation |
| `players` | list[Player] \| None | None | Player list (auto-built from scores if None) |
| `num_simulations` | int | 500 | Max iterations across all determinizations |
| `time_limit_ms` | float | 2000 | Hard wall-clock budget in ms |
| `exploration_constant` | float | 1.41 | UCT exploration constant C |
| `num_determinizations` | int | 5 | Number of tile-bag shuffles to average |
| `eval_fn` | EvalFn \| None | None | Leaf evaluation (sigmoid fallback if None) |
| `pw_c` | float | 2.0 | Progressive widening constant |
| `pw_alpha` | float | 0.5 | Progressive widening exponent |
| `use_rave` | bool | False | Enable RAVE/AMAF |
| `rave_k` | float | 100.0 | RAVE equivalence parameter |
| `max_amaf_depth` | int | 4 | AMAF depth limit in plies (0=unlimited) |
| `rave_fpu` | bool | True | First-play urgency with AMAF prior |
| `tile_aware_amaf` | bool | False | Include tile type in AMAF keys |

**EvalFn signature:** `(game_data, phase, player_id, players, plugin) -> float` in [0, 1].

### 2.2 Determinization Loop

```
for det_idx in 0..num_determinizations:
    if wall_clock >= total_deadline: break

    det_game_data = deep_copy(game_data)
    if det_game_data has "tile_bag":
        shuffle(det_game_data["tile_bag"])

    root_state = SimulationState(det_game_data, phase.deep_copy(), players, scores)
    root = MCTSNode(action=None, parent=None)

    sims_per_det = num_simulations / num_determinizations
    det_deadline = min(now + time_per_det, total_deadline)

    for sim_i in 0..sims_per_det:
        if now >= det_deadline: break
        _run_one_iteration(root, root_state, ...)

    // Aggregate root's children visit counts
    for child in root.children:
        key = action_key(child.action)
        action_visits[key] += child.visit_count
        action_values[key] += child.total_value
        action_map[key] = child.action

// Return action with highest aggregated visit count
best_key = argmax(action_visits)
return action_map[best_key]
```

**Time budgeting:**
- `time_per_det = time_limit_ms / num_determinizations / 1000.0` (seconds)
- Each determinization gets `det_deadline = min(now + time_per_det, total_deadline)`
- Partial results are kept if time runs out mid-determinization

**Early exit:** If only 0 or 1 valid actions, return immediately without search.

### 2.3 Single Iteration: `_run_one_iteration()`

Four phases executed sequentially on a cloned state:

#### SELECT

Walk down the tree following the best child while the node is at its progressive widening limit:

```
played_actions = []   // (action_key, acting_player) pairs
node = root
state = clone(root_state)

while node.children is non-empty AND _at_widening_limit(node):
    if use_rave:
        node = node.best_child_rave(c, rave_k, rave_fpu)
    else:
        node = node.best_child_uct(c)

    if node.action is not None and node.acting_player is not None:
        // For tile-aware AMAF, set amaf_key on first traversal
        if tile_aware_amaf and node.amaf_key is empty:
            node.amaf_key = _amaf_key(node.action, state)
        played_actions.push((node.amaf_key or action_key(node.action), node.acting_player))
        apply_node_action(state, node, plugin)
```

#### EXPAND

If the node hasn't been expanded yet (untried_actions is None) and game isn't over:

```
acting_pid = get_acting_player(state.phase, players)
if acting_pid exists:
    actions = plugin.get_valid_actions(game_data, phase, acting_pid)
    actions.sort_by(_action_sort_key)   // Heuristic priority
    node.untried_actions = actions
else:
    node.untried_actions = []
```

Then, if below widening limit and there are untried actions:

```
action_payload = node.untried_actions.pop_front()   // Take highest priority
acting_pid = get_acting_player(state.phase, players)

child = MCTSNode(
    action=action_payload,
    parent=node,
    acting_player=acting_pid,
    amaf_key=_make_key(action_payload) if use_rave else "",
)
node.children.push(child)
node = child

played_actions.push((child.amaf_key or action_key(action_payload), acting_pid))
apply_node_action(state, node, plugin)
```

#### EVALUATE

```
if state.game_over is not None:
    value = terminal_value(state, searching_player)
else:
    value = eval_fn(state.game_data, state.phase, searching_player, players, plugin)
```

**Terminal value:**
- Sole winner: 1.0
- Shared winner (draw): 0.8
- Loser: 0.0
- No result (shouldn't happen): 0.5

#### BACKPROPAGATE

See [Section 4.3](#43-backpropagation-with-amaf) for full AMAF backpropagation.

### 2.4 MCTSNode Data Structure

```rust
struct MCTSNode {
    action_taken: Option<ActionPayload>,    // None for root
    parent: Option<NodeRef>,
    acting_player: Option<PlayerId>,        // Who acted to reach this node
    children: Vec<MCTSNode>,
    untried_actions: Option<Vec<ActionPayload>>,  // None = not yet expanded
    visit_count: u32,                       // N(v)
    total_value: f64,                       // Sum of backpropagated values

    // RAVE statistics (HashMap<String, _>)
    amaf_visits: HashMap<String, u32>,      // action_key -> count
    amaf_values: HashMap<String, f64>,      // action_key -> sum of values
    amaf_key: String,                       // Tile-aware key (empty if disabled)
}
```

### 2.5 Child Selection Formulas

**UCT (Upper Confidence Bound for Trees):**
```
uct_value(child, parent_visits, c):
    if child.visit_count == 0: return +INF
    exploit = child.total_value / child.visit_count
    explore = c * sqrt(ln(parent_visits) / child.visit_count)
    return exploit + explore
```

**RAVE (UCT + AMAF blend):**
```
rave_value(child, parent_visits, c, rave_k, rave_fpu):
    action_k = child.amaf_key or action_key(child.action)

    if child.visit_count == 0:
        if rave_fpu and child.parent exists:
            amaf_n = parent.amaf_visits.get(action_k, 0)
            if amaf_n > 0:
                amaf_q = parent.amaf_values[action_k] / amaf_n
                return 1.0 + amaf_q    // Range [1.0, 2.0]
        return +INF

    q_uct = child.total_value / child.visit_count

    // Look up AMAF in parent
    amaf_n = parent.amaf_visits.get(action_k, 0)
    amaf_q = if amaf_n > 0 { parent.amaf_values[action_k] / amaf_n } else { 0.5 }

    beta = sqrt(rave_k / (3.0 * parent_visits + rave_k))
    blended = (1.0 - beta) * q_uct + beta * amaf_q
    explore = c * sqrt(ln(parent_visits) / child.visit_count)
    return blended + explore
```

**Beta formula:** `β = sqrt(rave_k / (3 * N_parent + rave_k))`
- At N=0: β=1.0 (pure AMAF)
- At N=33 (k=100): β≈0.50
- At N=200 (k=100): β≈0.26
- At N→∞: β→0 (pure UCT)

**best_child_uct(c):** `argmax over children of uct_value`
**best_child_rave(c, rave_k, rave_fpu):** `argmax over children of rave_value`
**most_visited_child():** `argmax over children of visit_count`

---

## 3. Progressive Widening

**Purpose:** Limit tree breadth proportional to visit count. Prevents exploring all 50+ tile placements at every node.

### 3.1 Maximum Children Formula

```
max_children(visit_count, pw_c, pw_alpha) -> int:
    return max(1, floor(pw_c * max(1, visit_count) ^ pw_alpha))
```

**Examples with pw_c=2.0, pw_alpha=0.5:**

| Visits | max_children |
|--------|-------------|
| 0 | 1 (minimum) |
| 1 | 2 |
| 4 | 4 |
| 9 | 6 |
| 16 | 8 |
| 25 | 10 |
| 100 | 20 |

**Disabling:** Set `pw_alpha=0` → `max_children = pw_c` always (constant, no widening).

### 3.2 Widening Limit Check

```
_at_widening_limit(node, pw_c, pw_alpha) -> bool:
    if node.untried_actions is empty:
        return true   // All actions expanded, no more to try
    limit = max_children(node.visit_count, pw_c, pw_alpha)
    return len(node.children) >= limit
```

**Interaction with SELECT/EXPAND:**
- SELECT continues while at widening limit (all allowed children exist)
- EXPAND creates a new child only when BELOW widening limit
- As visit count grows, more children are allowed → wider exploration

### 3.3 Action Ordering

When actions are first discovered, they're sorted by heuristic priority so the most promising are expanded first:

```
_action_sort_key(action) -> (priority_tier, sub_priority):
    if action has "skip": return (10,)
    if action has "meeple_spot":
        prefix = spot.split("_")[0] or spot
        priority = {city: 0, monastery: 1, road: 2, field: 3}.get(prefix, 5)
        return (1, priority)
    if action has "x" and "y":
        return (0, abs(x) + abs(y))   // Closer to origin = higher priority
    return (5,)
```

**Priority order (lower = expanded first):**
1. Tile placements near origin (tier 0)
2. Meeple: city (1,0) > monastery (1,1) > road (1,2) > field (1,3)
3. Unknown actions (tier 5)
4. Skip (tier 10)

---

## 4. RAVE / AMAF

**RAVE** (Rapid Action Value Estimation) / **AMAF** (All-Moves-As-First): shares action-value statistics across sibling branches. If placing a city tile at (2,3) led to good outcomes in one simulation branch, that information informs the value of the same action in other branches.

### 4.1 AMAF Statistics Storage

Each node stores:
- `amaf_visits: {action_key: count}` — how many times this action was played below this node
- `amaf_values: {action_key: total_value}` — sum of values when this action was played below

### 4.2 Action Tracking During Iteration

During SELECT and EXPAND, record every action taken:

```
played_actions: Vec<(String, Option<PlayerId>)> = []
// Each entry: (action_key_or_amaf_key, acting_player)
```

These are collected in order from root to leaf (depth-ordered).

### 4.3 Backpropagation with AMAF

```
_backpropagate(leaf, value, searching_player, played_actions, use_rave, max_amaf_depth):
    node = leaf
    depth = len(played_actions)    // Starts at total depth

    while node is not None:
        node.visit_count += 1

        // Value perspective: searching_player's POV
        if node.acting_player is None or node.acting_player == searching_player:
            node.total_value += value
        else:
            node.total_value += 1.0 - value   // Invert for opponent

        // AMAF update for actions played BELOW this node
        if use_rave and depth < len(played_actions):
            end_i = if max_amaf_depth > 0 {
                min(len(played_actions), depth + max_amaf_depth)
            } else {
                len(played_actions)
            }

            for i in depth..end_i:
                (ak, player) = played_actions[i]
                node.amaf_visits[ak] += 1
                if player is None or player == searching_player:
                    node.amaf_values[ak] += value
                else:
                    node.amaf_values[ak] += 1.0 - value

        depth -= 1
        node = node.parent
```

**Key insight:** `depth` tracks which index in `played_actions` corresponds to the current node. Actions at indices `>= depth` are "below" this node. As we walk up, `depth` decreases, so more actions become "below."

### 4.4 Depth-Limited AMAF

**Problem:** Without depth limiting, AMAF at a shallow node gets polluted by actions from 4-6 turns later — completely different board state and tile context.

**Solution:** `max_amaf_depth=4` limits AMAF updates to the 4 plies (2 full Carcassonne turns) immediately below each node.

**Arena evidence:** Depth-limiting alone didn't help (67-33% MCTS advantage). Combined with FPU, it became 53-47% MCTS (nearly even).

### 4.5 First-Play Urgency (FPU)

**Problem:** Without FPU, unvisited children get `+INF` UCT value, bypassing AMAF data entirely. The main benefit of RAVE — guiding which unvisited children to try first — is thrown away.

**Solution:** When `rave_fpu=True` and a child has 0 visits but AMAF data exists in the parent, return `1.0 + amaf_q` instead of `+INF`. This ranks unvisited children by AMAF quality while still ensuring all children get explored (since 1.0+ beats any normal blended value in [0,1]+explore).

**Children without AMAF data** still get `+INF` (explored first, as before).

**Arena evidence:** FPU was the single biggest improvement. Without FPU: 67-33% MCTS. With FPU: 53-47% (and 52-48% RAVE advantage over 50 games).

### 4.6 Tile-Aware AMAF Keys

**Problem:** Action key `"1,0,90"` doesn't include which tile is being placed. Different tiles at the same position have different values, but share the same AMAF entry.

**Solution:** When `tile_aware_amaf=True`, prefix tile type: `"C:1,0,90"` instead of `"1,0,90"`.

```
_amaf_key(action, state):
    if state exists and action has x, y, rotation:
        tile = state.game_data["current_tile"]
        if tile: return f"{tile}:{x},{y},{rotation}"
    return action_key(action)    // Fallback to standard key
```

**Arena evidence:** Tile-aware keys didn't improve over depth-limiting alone (57-43%). Depth-limiting already prevents most cross-tile conflation. Default OFF.

---

## 5. Game Simulator

### 5.1 SimulationState

```rust
struct SimulationState {
    game_data: GameData,           // Mutable game state (deep-cloned per iteration)
    phase: Phase,                  // Current phase (deep-cloned per iteration)
    players: Vec<Player>,          // Shared reference (immutable during game)
    scores: HashMap<PlayerId, f64>,
    game_over: Option<GameResult>,
}
```

### 5.2 apply_action_and_resolve()

**Core simulation function.** Applies a player action, then automatically resolves all subsequent auto-resolve phases until the next player-decision phase or game over.

```
apply_action_and_resolve(plugin, state, action):
    result = plugin.apply_action(state.game_data, state.phase, action, state.players)
    state.game_data = result.game_data
    state.phase = result.next_phase
    if result.scores: state.scores = result.scores
    state.game_over = result.game_over

    // Auto-resolve loop (max 50 iterations for safety)
    for _ in 0..50:
        if not state.phase.auto_resolve or state.game_over: break

        synthetic_action = Action(
            action_type=state.phase.name,
            player_id=get_phase_player(state.phase, state.players),
            payload={}
        )
        result = plugin.apply_action(state.game_data, state.phase, synthetic_action, state.players)
        state.game_data = result.game_data
        state.phase = result.next_phase
        if result.scores: state.scores = result.scores
        state.game_over = result.game_over
```

**Auto-resolve phases:** Phases with `auto_resolve=True` require no player choice. Examples: `draw_tile`, `score_check`, `end_turn`. The simulator applies them automatically with empty payloads.

### 5.3 clone_state()

```
clone_state(state) -> SimulationState:
    return SimulationState(
        game_data = deep_clone(state.game_data),
        phase = deep_clone(state.phase),
        players = state.players,              // Shared ref (never mutated)
        scores = shallow_clone(state.scores),
        game_over = state.game_over,          // Copy (small)
    )
```

**Performance note:** Deep-copying game_data is the most expensive operation per MCTS iteration (~0.3ms in Python). In Rust, consider using persistent/immutable data structures or copy-on-write.

### 5.4 Acting Player Resolution

```
get_acting_player(phase, players) -> Option<PlayerId>:
    if phase.expected_actions is non-empty:
        return phase.expected_actions[0].player_id
    if phase.metadata has "player_index" pi, and pi < len(players):
        return players[pi].player_id
    return None
```

### 5.5 Applying Node Actions in MCTS

```
_apply_node_action(state, node, plugin):
    action_type = if phase.expected_actions non-empty {
        phase.expected_actions[0].action_type
    } else {
        phase.name
    }
    action = Action(action_type, node.acting_player, node.action_taken)
    apply_action_and_resolve(plugin, state, action)
```

---

## 6. Carcassonne Heuristic Evaluator

Returns a value in [0.0, 1.0] from the perspective of `player_id`. Four weighted components that shift over game progress.

### 6.1 EvalWeights Configuration

```rust
struct EvalWeights {
    // Score differential
    score_base: f64,           // 0.35 — weight at game start
    score_delta: f64,          // 0.10 — added weight by game end
    score_scale: f64,          // 25.0 — sigmoid scale factor

    // Feature potential
    potential_base: f64,       // 0.35
    potential_delta: f64,      // -0.15 (decreases over game)
    potential_scale: f64,      // 15.0

    // Meeple economy
    meeple_base: f64,          // 0.20
    meeple_delta: f64,         // -0.05
    meeple_hoard_threshold: u32, // 6 — penalize hoarding above this
    meeple_hoard_penalty: f64, // 0.8 — multiplier when hoarding
    meeple_hoard_progress_gate: f64, // 0.2 — only penalize after 20% of game

    // Field potential
    field_base: f64,           // 0.10
    field_delta: f64,          // 0.10
    field_scale: f64,          // 10.0
}
```

**Named presets:**

| Preset | score_base | potential_base | meeple_base | field_base | Key change |
|--------|-----------|----------------|-------------|------------|------------|
| default | 0.35 | 0.35 | 0.20 | 0.10 | Balanced |
| aggressive | 0.45 | 0.30 | 0.10 | 0.15 | Score-focused, low meeple care |
| field_heavy | 0.30 | 0.30 | 0.15 | 0.25 | Emphasize end-game fields |
| conservative | 0.30 | 0.30 | 0.30 | 0.10 | Meeple preservation |

### 6.2 Game Progress

```
game_progress = 1.0 - (tiles_remaining / total_tiles)
```

Where `total_tiles = tiles_remaining + tiles_on_board` (typically 71 placed tiles in a 72-tile game, since 1 starts on the board).

**Dynamic weight at progress p:**
```
score_weight     = score_base     + score_delta     * p    // 0.35 → 0.45
potential_weight = potential_base + potential_delta * p    // 0.35 → 0.20
meeple_weight    = meeple_base   + meeple_delta   * p    // 0.20 → 0.15
field_weight     = field_base    + field_delta    * p    // 0.10 → 0.20
```

### 6.3 Component 1: Score Differential

```
my_score = scores[player_id]
max_opp_score = max(scores[pid] for pid != player_id)
diff = my_score - max_opp_score
score_component = sigmoid(diff, scale=score_scale)
```

**Sigmoid:** `sigmoid(x, scale) = 1.0 / (1.0 + exp(-x / scale))`
- At diff=0: 0.5
- At diff=+scale: ~0.73
- At diff=-scale: ~0.27

### 6.4 Component 2: Feature Potential

Evaluates incomplete features (cities, roads, monasteries) that have meeples:

```
my_potential = 0.0
opp_potential = 0.0
wasted_meeple_penalty = 0.0

for each incomplete feature with meeples:
    skip if field (handled separately)

    raw_value = raw_feature_potential(feature_type, tiles, open_edges, pennants, tiles_remaining)
    (my_count, max_opp_count, total_opp) = meeple_counts(feature.meeples, player_id)

    if my_count == 0:
        opp_potential += raw_value
    elif my_count >= max_opp_count:
        my_potential += raw_value       // We control or tie
    else:
        opp_potential += raw_value      // Contested, opponent controls
        wasted_meeple_penalty += my_count * 1.5   // Our meeples are wasted

diff = my_potential - opp_potential - wasted_meeple_penalty
potential_component = sigmoid(diff, scale=potential_scale)
```

**Raw feature potential:**

```
raw_feature_potential(type, tiles, open_edges, pennants, tiles_remaining):
    prob = completion_probability(len(open_edges), tiles_remaining)

    if type == city:
        // Completed city: 2pts/tile + 2pts/pennant. Incomplete: 1pt/tile + 1pt/pennant
        return prob * (len(tiles) * 2 + pennants * 2)
             + (1 - prob) * (len(tiles) + pennants)
    if type == road:
        return len(tiles)    // Road always worth tile count
    if type == monastery:
        neighbors = count_adjacent_tiles(game_data, monastery_position)
        prob = completion_probability(8 - neighbors, tiles_remaining)
        return prob * 9 + (1 - prob) * (1 + neighbors)
    return 0.0
```

**Completion probability:**

```
completion_probability(open_edges, tiles_remaining):
    if open_edges == 0: return 1.0
    if tiles_remaining == 0: return 0.0
    ratio = tiles_remaining / max(open_edges * 3, 1)
    return min(1.0, ratio * 0.5)    // Conservative: 50% base chance adjusted by ratio
```

**Meeple counts:**

```
meeple_counts(meeples, player_id) -> (my_count, max_opp_count, total_opp):
    counts = group_by(meeples, |m| m.player_id).count()
    my = counts.remove(player_id) or 0
    max_opp = max(counts.values()) or 0
    total_opp = sum(counts.values())
    return (my, max_opp, total_opp)
```

**Contested feature logic:** If we have meeples on a feature but an opponent has MORE meeples, our meeples are "wasted" — they score nothing when the feature completes. Penalty: 1.5 per wasted meeple.

### 6.5 Component 3: Meeple Economy

```
my_meeples = meeple_supply[player_id]
avg_opp_meeples = mean(meeple_supply[pid] for pid != player_id)

// Absolute value: normalized to 7 (max hand)
meeple_value = min(my_meeples / 7.0, 1.0)

// Hoarding penalty: too many unused meeples after early game
if my_meeples >= hoard_threshold and game_progress > hoard_progress_gate:
    meeple_value *= hoard_penalty    // 0.8x

// Scarcity penalty: 0 meeples is devastating mid-game
if my_meeples == 0 and game_progress < 0.85:
    meeple_value *= 0.3
elif my_meeples <= 1 and game_progress < 0.7:
    meeple_value *= 0.6

// Relative advantage via sigmoid
relative = sigmoid((my_meeples - avg_opp_meeples) * 0.5, scale=3.0)

meeple_component = 0.5 * relative + 0.5 * meeple_value
```

**Key thresholds:**
- 0 meeples before 85% game: 0.3x penalty (critical)
- 1 meeple before 70% game: 0.6x penalty (severe)
- 6+ meeples after 20% game: 0.8x penalty (not investing)

### 6.6 Component 4: Field Potential

Estimates end-game field scoring (3 points per adjacent completed city):

```
my_field = estimate_field_value(game_data, player_id, tiles_remaining)
max_opp_field = max(estimate_field_value(..., opp_pid, ...) for each opponent)
field_diff = my_field - max_opp_field
field_component = sigmoid(field_diff, scale=field_scale)
```

**Field value estimation:**

```
estimate_field_value(game_data, player_id, tiles_remaining):
    total = 0.0
    for each field feature with meeples:
        if not controlled_by(player_id): continue

        // Count completed adjacent cities (3 pts each)
        completed_cities = get_adjacent_completed_cities(feature)
        total += len(completed_cities) * 3

        // Nearly-complete cities: add weighted probability
        for each adjacent incomplete city:
            prob = completion_probability(city.open_edges, tiles_remaining)
            if prob > 0.3:
                total += prob * 3

    return total
```

### 6.7 Final Combination

```
value = score_weight * score_component
      + potential_weight * potential_component
      + meeple_weight * meeple_component
      + field_weight * field_component

return clamp(value, 0.0, 1.0)
```

### 6.8 Default Eval Fallback

When no eval_fn is provided, MCTS uses a simple sigmoid of score differential:

```
_default_eval_fn(game_data, phase, player_id, players, plugin):
    scores = game_data["scores"]
    my_score = scores[player_id]
    max_opp = max(scores[pid] for pid != player_id)
    diff = my_score - max_opp
    return 1.0 / (1.0 + exp(-diff / 20.0))
```

---

## 7. Bot Strategies & Registry

### 7.1 BotStrategy Trait

```rust
trait BotStrategy {
    fn choose_action(
        &self,
        game_data: &GameData,
        phase: &Phase,
        player_id: PlayerId,
        plugin: &dyn GamePlugin,
    ) -> ActionPayload;
}
```

### 7.2 RandomStrategy

```
choose_action(game_data, phase, player_id, plugin):
    valid = plugin.get_valid_actions(game_data, phase, player_id)
    return rng.choice(valid)
```

Optionally seeded for deterministic behavior.

### 7.3 MCTSStrategy

Wraps `mcts_search()` with stored parameters. All parameters from mcts_search are configurable.

### 7.4 Registry

```
STRATEGIES: HashMap<String, StrategyFactory> = {
    "random" => |kwargs| RandomStrategy::new(kwargs),
    "mcts"   => |kwargs| MCTSStrategy::new(kwargs),
}

get_strategy(bot_id) -> Box<dyn BotStrategy>
register_strategy(bot_id, factory)
```

---

## 8. Arena Runner

### 8.1 run_arena()

```
run_arena(plugin, strategies, num_games, base_seed, alternate_seats):
    for game_idx in 0..num_games:
        seed = base_seed + game_idx

        // Seat alternation: rotate strategy assignments each game
        if alternate_seats:
            seat_assignment[i] = strategy_names[(i + game_idx) % num_players]

        players = create_players_with_seats(seat_assignment)
        config = GameConfig(random_seed=seed)
        result = play_one_game(plugin, players, config, strategies)
        record(result)

    return ArenaResult(wins, draws, scores, durations)
```

### 8.2 play_one_game()

```
play_one_game(plugin, players, config, strategies):
    (game_data, phase, _) = plugin.create_initial_state(players, config)
    state = SimulationState(game_data, phase, players, scores={}, game_over=None)

    resolve_auto_phases(plugin, state)     // Handle initial auto-resolve

    for _ in 0..500:    // Safety limit
        if state.game_over: break
        if state.phase.auto_resolve:
            resolve_auto_phases(plugin, state)
            continue

        acting_pid = phase.expected_actions[0].player_id
        strategy = strategies[acting_pid]
        chosen = strategy.choose_action(state.game_data, state.phase, acting_pid, plugin)

        action = Action(
            action_type=phase.expected_actions[0].action_type,
            player_id=acting_pid,
            payload=chosen,
        )
        apply_action_and_resolve(plugin, state, action)

    return state.game_over
```

### 8.3 Statistics

**Wilson score confidence interval** (95% CI for win rate):

```
confidence_interval_95(wins, n):
    if n == 0: return (0.0, 0.0)
    p = wins / n
    z = 1.96
    denom = 1 + z^2 / n
    center = (p + z^2 / (2*n)) / denom
    margin = z * sqrt((p*(1-p) + z^2/(4*n)) / n) / denom
    return (max(0, center - margin), min(1, center + margin))
```

**Standard deviation:** Sample stddev of final scores per strategy.

---

## 9. Data Models

### Phase

```rust
struct Phase {
    name: String,                          // e.g. "place_tile", "place_meeple"
    concurrent_mode: ConcurrentMode,       // Sequential (default) or Simultaneous
    expected_actions: Vec<ExpectedAction>,  // Who needs to act
    auto_resolve: bool,                    // If true, resolved automatically (no player input)
    metadata: HashMap<String, Value>,      // Game-specific metadata
}
```

### ExpectedAction

```rust
struct ExpectedAction {
    player_id: Option<PlayerId>,
    action_type: String,                   // e.g. "place_tile"
    constraints: HashMap<String, Value>,
    timeout_ms: Option<u64>,
}
```

### Action

```rust
struct Action {
    action_type: String,
    player_id: PlayerId,
    payload: HashMap<String, Value>,       // Game-specific action data
    timestamp: Option<DateTime>,
}
```

### GameResult

```rust
struct GameResult {
    winners: Vec<PlayerId>,                // May have multiple (draw)
    final_scores: HashMap<PlayerId, f64>,
    reason: String,                        // "normal", "forfeit", "timeout"
    details: HashMap<String, Value>,
}
```

### TransitionResult

```rust
struct TransitionResult {
    game_data: GameData,
    events: Vec<Event>,
    next_phase: Phase,
    scores: HashMap<PlayerId, f64>,
    game_over: Option<GameResult>,
}
```

---

## 10. Game Plugin Protocol

```rust
trait GamePlugin {
    // Metadata
    const GAME_ID: &'static str;
    const DISPLAY_NAME: &'static str;
    const MIN_PLAYERS: u32;
    const MAX_PLAYERS: u32;

    fn create_initial_state(
        &self, players: &[Player], config: &GameConfig
    ) -> (GameData, Phase, Vec<Event>);

    fn get_valid_actions(
        &self, game_data: &GameData, phase: &Phase, player_id: PlayerId
    ) -> Vec<ActionPayload>;

    fn validate_action(
        &self, game_data: &GameData, phase: &Phase, action: &Action
    ) -> Option<String>;   // None = valid, Some(err) = invalid

    fn apply_action(
        &self, game_data: &GameData, phase: &Phase, action: &Action, players: &[Player]
    ) -> TransitionResult;

    fn get_player_view(
        &self, game_data: &GameData, phase: &Phase, player_id: Option<PlayerId>, players: &[Player]
    ) -> PlayerView;

    fn on_player_forfeit(
        &self, game_data: &GameData, phase: &Phase, player_id: PlayerId, players: &[Player]
    ) -> Option<TransitionResult>;
}
```

**Carcassonne phase flow:**
```
draw_tile (auto_resolve) → place_tile (player) → place_meeple (player)
→ score_check (auto_resolve) → [end_turn (auto_resolve) → draw_tile → ...]
→ final_scoring (auto_resolve) → game_over
```

Each player turn is 2 decision points: place_tile + place_meeple. Auto-resolve phases happen between and are transparent to MCTS.

---

## 11. Action Key System

**Standard action keys** (used for visit count aggregation and AMAF):

| Action Type | Key Format | Example |
|-------------|-----------|---------|
| Tile placement | `"{x},{y},{rotation}"` | `"1,-1,90"` |
| Meeple placement | `"meeple:{spot}"` | `"meeple:city_N"` |
| Skip | `"skip"` | `"skip"` |
| None | `""` | `""` |
| Other | JSON serialization | `'{"custom_key": 42}'` |

**Tile-aware AMAF keys** (when `tile_aware_amaf=True`):

| Action Type | Key Format | Example |
|-------------|-----------|---------|
| Tile placement | `"{tile}:{x},{y},{rotation}"` | `"C:1,-1,90"` |
| Others | Same as standard | Same |

---

## 12. Arena Results & Insights

### 12.1 MCTS vs Random

```
MCTS 20-0 (100%)  avg 80.2 vs 23.1  [200 sims, 1s, 3 dets]
```

MCTS scores ~3.5x random. This confirms the evaluator + search is working correctly.

### 12.2 RAVE Parameter Sweep

**Before optimization (unlimited AMAF, no FPU):**

| rave_k | MCTS wins | RAVE wins | Analysis |
|--------|-----------|-----------|----------|
| 300 (20 games) | 13 (65%) | 6 (30%) | β too high, AMAF too noisy |
| 100 (20 games) | 15 (75%) | 5 (25%) | Faster decay, still losing |
| 50 (20 games) | 11 (55%) | 9 (45%) | Closest to parity |
| 500, 100 sims (20 games) | 10 (50%) | 10 (50%) | RAVE helps with fewer sims |

**Insight:** RAVE helps when visit counts are low (fewer simulations). With heuristic eval (low-noise leaf estimates), pure UCT converges well enough that AMAF adds noise.

### 12.3 RAVE Optimization Sweep

All at k=100, 200 sims, 30 games unless noted:

| Config | MCTS wins | RAVE wins | Insight |
|--------|-----------|-----------|---------|
| Baseline (no depth limit, no FPU) | 17 (57%) | 12 (40%) | Starting point |
| Depth=4, no FPU | 20 (67%) | 10 (33%) | Depth alone hurts — cleaner AMAF but no FPU benefit |
| Depth=2 + FPU | 18 (60%) | 12 (40%) | Depth too tight |
| Depth=4 + FPU | 16 (53%) | 14 (47%) | Near parity |
| Depth=6 + FPU | 16 (53%) | 14 (47%) | Similar to depth=4 |
| Depth=4 + FPU + tile-aware | 17 (57%) | 13 (43%) | Tile-aware doesn't help further |
| **Depth=4 + FPU (50 games)** | **24 (48%)** | **26 (52%)** | **RAVE wins** |

### 12.4 Key Insights for Rust Rewrite

1. **FPU is the most impactful RAVE improvement.** Without it, RAVE loses. With it, RAVE slightly wins. This is because FPU leverages AMAF's primary strength: guiding exploration of unvisited children.

2. **Depth-limited AMAF (4 plies) is essential.** Prevents distant game states from polluting AMAF. Two full Carcassonne turns is the sweet spot — captures immediate strategic context.

3. **rave_k=100 is the right ballpark.** At 200 sims with heuristic eval, β fades to ~0.26 by 200 visits. Higher k (300) keeps β too high too long.

4. **Tile-aware AMAF keys provide no measurable benefit** when combined with depth limiting. The depth limit already prevents most cross-tile conflation. Default OFF.

5. **Progressive widening (pw_c=2.0, pw_alpha=0.5) is critical** for Carcassonne's 50+ tile placements per turn. Without it, search spreads too thin.

6. **Heuristic eval >> rollouts.** Rollouts cost ~63ms and are noisy. Heuristic eval costs <0.1ms. This is why RAVE's benefit is marginal — the eval is already good enough that AMAF's noise reduction isn't as valuable as in Go with random rollouts.

7. **Evaluator weight presets** (aggressive, conservative, field_heavy) produce measurably different play styles but no preset dominates others — they're roughly balanced by design.

8. **Performance baseline (Python):** ~1000 MCTS iterations/second at mid-game (~0.3ms deepcopy + ~1ms apply_action). Rust should be 10-100x faster, enabling deeper search.

---

## 13. Invariants & Edge Cases

### Value Perspective
- All values are from the **searching player's perspective**: [0, 1]
- Opponent nodes invert: `1.0 - value`
- Root node and nodes with `acting_player=None` use raw value

### Terminal Values
- Sole winner: 1.0
- Shared winners (draw): 0.8
- Loser: 0.0
- No result (fallback): 0.5

### Empty/Edge Cases
- 0 valid actions → return empty dict
- 1 valid action → return it immediately (no search)
- No iterations completed → return first valid action
- `pw_alpha=0` → constant max_children (no widening)
- `max_amaf_depth=0` → unlimited AMAF (original RAVE)
- `use_rave=False` → AMAF dicts stay empty, pure UCT selection
- Node with `untried_actions=None` → not yet expanded (lazy expansion)
- Node with `untried_actions=[]` → fully expanded (no more actions)

### Auto-Resolve Safety
- Max 50 auto-resolve iterations per apply_action_and_resolve call
- Prevents infinite loops from buggy plugins

### Arena Safety
- Max 500 turns per game
- Prevents infinite games from buggy game logic

### Determinization
- Only `tile_bag` is shuffled; `current_tile` stays fixed (it's already drawn)
- Each determinization gets independent RNG (not seeded — uses system random)
- Results averaged by action key, not by determinization index

---

## 14. Rust Implementation Notes

### Performance-Critical Paths

1. **State cloning** (~0.3ms in Python): Use arena allocators, copy-on-write, or persistent data structures for `game_data`.

2. **apply_action** (~1ms in Python): The game plugin's apply_action is called once per MCTS iteration. Optimize the Carcassonne implementation (feature merging, scoring).

3. **Action key computation**: Called multiple times per iteration. Consider caching or using integer keys instead of string hashing.

4. **AMAF hash maps**: Consider `FxHashMap` or similar fast hasher for AMAF lookups (string keys are small).

### Parallelism Opportunities

- **Determinizations are independent**: Run each determinization on a separate thread. Aggregate results at the end. This is the easiest parallelism win.

- **Root parallelization**: Multiple threads sharing a single tree with mutex on nodes. More complex but higher utilization.

- **Leaf parallelism**: Evaluate multiple leaves in batch. Less applicable with heuristic eval (already fast).

### Validation Strategy

To confirm the Rust rewrite is correct, match these benchmarks:

1. **MCTS vs Random (50 games):** MCTS should win ~100%, avg score ~3x random
2. **MCTS+RAVE vs MCTS (50 games, k=100, depth=4, FPU):** RAVE should win ~50-55%
3. **UCT values:** For known visit counts and values, UCT formula should produce identical numbers
4. **Progressive widening:** At N visits, max_children should match the table in Section 3
5. **Evaluator:** For a known board position, the 4-component eval should produce the same value (within floating point tolerance)
6. **Iteration count:** With Rust's speed gains, expect 10-100x more iterations per second → stronger play
