# Bot Roadmap — Carcassonne AI

## Current state (Feb 2025)

### Implemented bots

| Bot | bot_id | Strength | Description |
|-----|--------|----------|-------------|
| Random | `"random"` | Baseline | Picks uniformly from valid actions |
| MCTS + Heuristic | `"mcts"` | Strong amateur | Monte Carlo Tree Search with heuristic leaf evaluation |

### Arena results (MCTS vs Random, 50 games)

```
MCTS:   50 wins (100%)  avg_score=55.3  [95% CI: 92.9%-100.0%]
Random:  0 wins (  0%)  avg_score=19.5  [95% CI: 0.0%-7.1%]
```

MCTS scores ~3x random on average. Each game takes ~9s with 200 simulations, 1s time limit, 3 determinizations.

### Architecture

```
backend/src/engine/
├── bot_strategy.py      # BotStrategy protocol + registry (get_strategy, register_strategy)
├── bot_runner.py         # Live server integration (async, uses bot_strategy by bot_id)
├── mcts.py               # Game-agnostic MCTS (determinization, UCT, heuristic eval)
├── game_simulator.py     # Synchronous state advancement (used by MCTS + Arena)
├── arena.py              # Bot-vs-bot arena runner (ArenaResult with stats + CIs)
└── arena_cli.py          # CLI: uv run python -m src.engine.arena_cli

backend/src/games/carcassonne/
└── evaluator.py          # Carcassonne heuristic evaluation function
```

**Adding a new bot**: implement `BotStrategy.choose_action(game_data, phase, player_id, plugin) -> dict`, register with `register_strategy("my_bot", factory)`, then test via arena.

### MCTS implementation details

- **Algorithm**: UCT with heuristic leaf evaluation (no random rollouts)
- **Stochasticity handling**: Determinization — shuffle the tile bag N times, run independent MCTS trees per determinization, aggregate root visit counts
- **Two-phase turns**: `place_tile` and `place_meeple` are separate tree levels
- **Leaf evaluation**: Heuristic function, not rollouts. Rollouts cost ~63ms and are very noisy; heuristic eval costs <0.1ms
- **Performance**: ~1000 MCTS iterations/second at mid-game (~0.3ms deepcopy + ~1ms apply_action)
- **Default params**: 200 sims, 1s time limit, C=1.41, 3 determinizations

### Heuristic evaluator (evaluator.py)

Returns value in [0, 1] with four components whose weights shift during the game:

| Component | Early → Late weight | What it measures |
|-----------|-------------------|------------------|
| Score differential | 0.35 → 0.45 | Current points vs best opponent (sigmoid) |
| Feature potential | 0.35 → 0.20 | Expected value of incomplete features with meeples (completion probability based on open_edges vs tiles_remaining) |
| Meeple economy | 0.20 → 0.15 | Available meeples vs opponents, penalises hoarding |
| Field potential | 0.10 → 0.20 | Estimated end-game field scoring (3pts per adjacent completed city) |

### Arena CLI usage

```bash
# Random vs random baseline (~6s for 100 games)
uv run python -m src.engine.arena_cli --p1 random --p2 random --games 100

# MCTS vs random (~9s/game)
uv run python -m src.engine.arena_cli --p1 random --p2 mcts --games 50

# Tune MCTS parameters
uv run python -m src.engine.arena_cli --p1 mcts --p2 mcts --games 50 \
    --mcts-sims 500 --mcts-time-ms 2000 --mcts-dets 5

# Output includes: win rates, 95% Wilson CIs, avg scores +/- stddev, game duration
```

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

- [ ] **Tune heuristic weights** — use arena to A/B test weight variations
- [ ] **Progressive widening** — limit branching in early expansion (Carcassonne has 20-80 actions per node)
- [ ] **RAVE / AMAF** — All-Moves-As-First heuristic to speed up convergence (proven for Carcassonne in [arXiv:2009.12974](https://arxiv.org/abs/2009.12974))
- [ ] **Better meeple heuristics** — field placement strategy, feature stealing (place meeple on opponent's feature to share/steal scoring)
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
