# Bot Roadmap — Carcassonne AI

## Current state (Feb 2025)

### Implemented bots

| Bot | bot_id | Strength | Description |
|-----|--------|----------|-------------|
| Random | `"random"` | Baseline | Picks uniformly from valid actions |
| MCTS + Heuristic | `"mcts"` | Strong amateur | Monte Carlo Tree Search with progressive widening and configurable heuristic eval |

### Arena results (200 sims, 1s, 3 dets, pw_c=2.0, pw_alpha=0.5)

```
Random vs MCTS:       MCTS 20-0 (100%)  avg 80.2 vs 23.1  [20 games]
```

MCTS scores ~3.5x random on average.

**MCTS vs MCTS+RAVE optimization** (k=100, depth=4, FPU on):

| Config | Games | MCTS wins | RAVE wins | MCTS avg | RAVE avg |
|--------|-------|-----------|-----------|----------|----------|
| Before (k=300, unlimited, no FPU) | 20 | 13 (65%) | 6 (30%) | 75.7 | 62.3 |
| After (k=100, depth=4, FPU) | 50 | 24 (48%) | **26 (52%)** | 75.1 | 67.3 |

Three key improvements turned RAVE from losing 65-30% to winning 52-48%:
1. **Depth-limited AMAF** (max_amaf_depth=4) — prevents deep-ply AMAF pollution
2. **First-play urgency** (rave_fpu=True) — uses AMAF as prior for unvisited children
3. **Lower rave_k** (100 vs 300) — faster fade from AMAF to pure UCT

### Architecture

All game logic and MCTS run in the Rust game engine (`game-engine/`), communicating with the Python backend via gRPC.

```
backend/src/engine/
├── bot_strategy.py      # BotStrategy protocol + registry (get_strategy, register_strategy)
├── bot_runner.py         # Live server integration (async, uses bot_strategy by bot_id)
└── grpc_plugin.py        # GrpcGamePlugin adapter (delegates all game calls to Rust)

game-engine/src/
├── engine/
│   ├── mcts.rs           # Game-agnostic MCTS (determinization, UCT, PW, RAVE)
│   ├── simulator.rs      # State advancement (used by MCTS + Arena)
│   ├── arena.rs          # Bot-vs-bot arena runner
│   ├── bot_strategy.rs   # Strategy trait, MctsStrategy, RandomStrategy
│   ├── evaluator.rs      # Heuristic evaluator trait
│   └── plugin.rs         # TypedGamePlugin trait
├── games/carcassonne/
│   └── evaluator.rs      # Carcassonne heuristic evaluation function
└── server.rs             # gRPC server (tonic)
```

**Built-in bots**: `GrpcMctsStrategy` delegates MCTS search to the Rust engine via a single `MctsSearch` gRPC call. `RandomStrategy` picks uniformly from valid actions (valid actions fetched via gRPC).

**Adding a new bot**: implement `BotStrategy.choose_action(game_data, phase, player_id, plugin) -> dict`, register with `register_strategy("my_bot", factory)`, then test via arena.

### MCTS implementation details (Rust engine)

- **Algorithm**: UCT with heuristic leaf evaluation (no random rollouts)
- **Progressive widening**: Limits tree width proportional to visit count (`max_children = pw_c * visits^pw_alpha`). Actions sorted by heuristic priority (city placements > monastery > road > field > skip). Default: pw_c=2.0, pw_alpha=0.5 (at 100 visits → 20 children max)
- **Stochasticity handling**: Determinization — shuffle the tile bag N times, run independent MCTS trees per determinization (parallelized via rayon), aggregate root visit counts
- **Two-phase turns**: `place_tile` and `place_meeple` are separate tree levels
- **Leaf evaluation**: Heuristic function, not rollouts. Heuristic eval is sub-microsecond in Rust
- **Performance**: ~20x faster than the original Python implementation (3.4-4.6s per self-play game vs 81.3s)
- **RAVE / AMAF**: Optional blending of UCT Q-value with AMAF statistics (`β = sqrt(k / (3N + k))`). Enabled via `use_rave=True`. Depth-limited AMAF (default 4 plies = 2 turns) + first-play urgency (AMAF as prior for unvisited children). Default rave_k=100
- **Root selection**: Value-based tie-breaking (highest avg value when visit counts tie) — critical for play quality with wide progressive widening
- **Default params**: 800 sims, 5s time limit, C=1.41, 4 determinizations, pw_c=2.0, pw_alpha=0.5

### Heuristic evaluator (game-engine/src/games/carcassonne/evaluator.rs)

Configurable via `EvalWeights` dataclass. Returns value in [0, 1] with four components whose weights shift during the game:

| Component | Early → Late weight | What it measures |
|-----------|-------------------|------------------|
| Score differential | 0.35 → 0.45 | Current points vs best opponent (sigmoid) |
| Feature potential | 0.35 → 0.20 | Expected value of incomplete features with meeples. Includes **contested feature penalty** (wasted meeples on opponent-controlled features) |
| Meeple economy | 0.20 → 0.15 | Available meeples vs opponents, penalises hoarding. **Scarcity awareness** — strong penalty when at 0 meeples mid-game |
| Field potential | 0.10 → 0.20 | Estimated end-game field scoring (3pts per adjacent completed city). **Nearly-complete city awareness** — also values fields adjacent to cities likely to complete |

Named weight presets for arena experimentation:
- `default` — balanced play
- `aggressive` — higher score weight, lower meeple conservation
- `field_heavy` — emphasises field scoring potential
- `conservative` — prioritises meeple economy

### Arena testing

Arena tests now run in the Rust engine via `cargo test`:

```bash
# Full test suite including arena tests (~3 min in release)
cd game-engine && cargo test --release

# Quick unit tests only (~10s)
cd game-engine && cargo test --release --lib -- --skip arena --skip mcts_per_game
```

The `RunArena` gRPC call also supports running arena matches from the Python backend. See `docs/09-rust-mcts-engine.md` for details.

---

## Roadmap: learning-based bots

### Why Carcassonne is harder than Chess/Go for AlphaZero

1. **Stochastic tile draws** — random tile from bag of 72 each turn. Standard MCTS can't plan ahead without knowing future tiles. Game-tree complexity is 10^195 (exceeds Chess at 10^123).
2. **Hidden information** — tile bag contents are known (counts) but draw order is not.
3. **Variable action space** — 20-80 valid tile placements per turn + 2-5 meeple options. Requires action masking.
4. **Complex state** — sparse grid with feature graph (cities, roads, fields, monasteries) that merge. Encoding requires ~30x30x117 tensor = 105,300 values (14x larger than Chess).

### Existing work on ML/RL for Carcassonne

| Project | Approach | Result |
|---------|----------|--------|
| [Ameneyro et al., 2020](https://arxiv.org/abs/2009.12974) (IEEE CoG) | Vanilla MCTS | Outperformed all hand-crafted search algorithms |
| [muzero-carcassonne](https://github.com/Maxi13421/muzero-carcassonne) (132 commits) | MuZero fork, PyTorch, GTX 1050Ti | "Did not systematically reach human level", regression after extended training |
| [wingedsheep/carcassonne](https://github.com/wingedsheep/carcassonne) | Python engine for RL | Has 30x30x117 state encoding, no trained agent |
| [PyTAG](https://github.com/martinballa/PyTAG) | PPO self-play on tabletop games | Framework supports Carcassonne, no published results |

### Tier 1: MCTS improvements (low cost, incremental)

**Estimated effort**: 1-2 weeks per item, $0 compute

- [x] **Configurable evaluator weights** — `EvalWeights` dataclass with named presets (default, aggressive, field_heavy, conservative) + `make_carcassonne_eval()` factory
- [x] **Progressive widening** — limits branching proportional to visit count (`pw_c * visits^pw_alpha`), with heuristic action ordering
- [x] **Better meeple heuristics** — contested feature penalty, meeple scarcity awareness, nearly-complete city field valuation
- [x] **RAVE / AMAF** — All-Moves-As-First heuristic with depth-limited AMAF + first-play urgency. Wins 52-48% vs baseline MCTS (k=100, depth=4, FPU). Enabled via `--p1-rave`/`--p2-rave` flags
- [ ] **Opening book** — pre-compute good first few moves
- [ ] **Endgame solver** — exact evaluation when few tiles remain

### Tier 2: PPO self-play (moderate cost)

**Estimated effort**: 3-5 weeks, $20-100 cloud GPU

- [ ] **Gymnasium/PettingZoo wrapper** — wrap the existing Carcassonne plugin as an RL environment
- [ ] **State encoding** — 30x30 grid with ~60-120 feature planes (tile edges, feature ownership, meeple positions, scores, meeple supply, tiles remaining)
- [ ] **Action encoding** — factored heads: position (900) + rotation (4) + meeple (10) with masking
- [ ] **PPO training** — stable-baselines3 + PettingZoo, self-play
- [ ] **Arena evaluation** — measure PPO vs MCTS vs random

Frameworks: [stable-baselines3](https://github.com/DLR-RM/stable-baselines3), [PettingZoo](https://pettingzoo.farama.org/)

### Tier 3: Stochastic MuZero (higher cost, principled approach)

**Estimated effort**: 6-10 weeks, $80-500 cloud GPU

- [ ] **Custom environment** — wrap plugin with LightZero or muzero-general API
- [ ] **Stochastic MuZero** — explicitly models chance nodes (tile draws) through learned dynamics
- [ ] **Neural network architecture** — ResNet or GNN on the board state
- [ ] **Self-play training loop** — play, store, train, repeat
- [ ] **Arena evaluation** — measure vs MCTS baseline

Frameworks: [LightZero](https://github.com/opendilab/LightZero) (NeurIPS 2023 spotlight — supports AlphaZero, MuZero, Stochastic MuZero, EfficientZero, Gumbel MuZero)

The muzero-carcassonne project's struggles suggest hyperparameter tuning and state representation are the hard parts, not compute.

### Tier 4: Full AlphaZero with PIMC (highest effort)

**Estimated effort**: 8-12 weeks, $200-2000 cloud GPU

- [ ] **PIMC adaptation** — at chance nodes, sample possible tile sequences and average MCTS results
- [ ] **Neural network** — policy + value heads trained from self-play
- [ ] **Dedicated training infrastructure** — multi-GPU or cloud training pipeline

Paper: [AlphaZe** — AlphaZero-like baselines for imperfect information games are surprisingly strong](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2023.1014561/full)

### Compute cost estimates

| Approach | GPU Hours | Cost (Vast.ai/RunPod) | Cost (AWS) |
|----------|-----------|----------------------|-----------|
| MCTS + heuristic | 0 | $0 | $0 |
| PPO self-play | 50-200 | $20-80 | $100-500 |
| Stochastic MuZero | 200-1,000 | $80-400 | $500-2,500 |
| Full AlphaZero+PIMC | 500-3,000 | $200-1,200 | $1,250-7,500 |

Self-play games needed: estimated 500K-5M for a strong amateur bot.

Minimum hardware: single RTX 3060/3070 training 1-4 weeks, or RTX 4090 for 3-7 days.

### Key references

- [Playing Carcassonne with MCTS (Ameneyro et al., 2020)](https://arxiv.org/abs/2009.12974)
- [Stochastic MuZero (Planning in Stochastic Environments, 2022)](https://openreview.net/forum?id=X6D9bAHhBQ1)
- [LightZero: Unified Benchmark for MCTS-based RL](https://github.com/opendilab/LightZero)
- [muzero-general](https://github.com/werner-duvaud/muzero-general)
- [AlphaZe**: AlphaZero for imperfect information games](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2023.1014561/full)
- [Invalid Action Masking in Policy Gradient Algorithms](https://arxiv.org/abs/2006.14171)
- [Scaling Laws with Board Games (Jones, 2021)](https://arxiv.org/abs/2104.03113)
- [Programming Carcassonne for RL (wingedsheep blog)](https://wingedsheep.com/programming-carcassonne/)
