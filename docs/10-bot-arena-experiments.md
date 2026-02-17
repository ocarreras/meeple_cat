# 10 — Bot Arena Experiments & Difficulty Tiers

This document records the systematic arena experiments conducted to establish
bot difficulty tiers for Carcassonne and improve the hard bot's evaluation
function.

## Background

The MCTS bot uses Information Set Monte Carlo Tree Search (IS-MCTS) with
determinization: for each search, it samples N possible hidden states (tile
orderings), runs a separate MCTS tree for each, and aggregates the results.

Key parameters:
- **num_simulations**: MCTS rollouts per determinization
- **num_determinizations**: number of hidden-state samples
- **eval_profile**: heuristic evaluation function used at leaf nodes
- **RAVE**: Rapid Action Value Estimation (AMAF-based move ordering)

## Experimental Setup

All experiments use the arena CLI (`cargo run --release --bin arena`), which
runs bot-vs-bot matches with alternating seats and reports win rates with
Wilson 95% confidence intervals.

Baseline: **medium** profile (300 sims, 3 dets, v1 default eval, no RAVE).

---

## Phase 1: Eval Preset Comparison

**Question**: Which existing eval weight preset is strongest?

All test profiles use 800 sims, 5 dets, no RAVE (except where noted).

| Profile | Eval Preset | Win % vs Medium | Avg Score | Medium Avg |
|---------|-------------|-----------------|-----------|------------|
| test_aggressive | aggressive | 38% [29.1-47.8] | 86.6 | 88.5 |
| test_field_heavy | field_heavy | 40% [30.9-49.8] | 89.3 | 98.8 |
| test_conservative | conservative | 23% [15.8-32.2] | 72.7 | 93.1 |

**Finding**: All alternative presets lose to default, even with 2.5x more
simulations. The default weight allocation is already near-optimal. Conservative
(hoarding meeples) is by far the weakest strategy.

---

## Phase 2: Weight Tuning (v1 Evaluator)

**Question**: Can tighter sigmoid scales or modified weights improve the v1 eval?

| Profile | Change | Win % vs Medium | Avg Score |
|---------|--------|-----------------|-----------|
| exp_tight | Tighter sigmoid scales (score=15, potential=8, field=6) | 52% [42.3-61.5] | 82.2 |
| exp_field_late | More field weight late game (field_delta=0.20) | 39% [30.0-48.8] | 85.7 |
| exp_combined | Tight scales + field late | 41% [31.9-50.8] | 81.0 |

**Finding**: Tighter scales showed a marginal edge (52% vs 47%), suggesting the
v1 eval's sigmoid compression was too flat. But increasing field weight hurt
performance. Weight tuning alone is insufficient.

---

## Phase 3: Enhanced Heuristics (v1 Framework)

**Question**: Do additional heuristic signals (near-completion bonus, trapped
meeple penalty, city size scaling) improve play?

| Profile | Parameters | Win % vs Medium | Avg Score |
|---------|-----------|-----------------|-----------|
| exp_enhanced | near_completion=2.0, trapped=3.0, city_exp=1.15, dominance=0.2 + RAVE | 24% [16.7-33.2] | 61.0 |
| exp_enhanced_no_rave | Same params, no RAVE | 26% [18.4-35.4] | 66.1 |
| exp_mild_enhanced | near_completion=1.3, trapped=1.0, city_exp=1.05, dominance=0.1 + RAVE | 40% [30.9-49.8] | 77.9 |

**Finding**: Additional heuristics introduced noise rather than signal. Even
mild parameters hurt performance. The v1 framework's double-sigmoid
architecture compresses these signals too much to be useful.

---

## Phase 4: RAVE Impact

**Question**: Does RAVE help or hurt with the Carcassonne evaluator?

| Profile | Config | Win % vs Medium | Avg Score |
|---------|--------|-----------------|-----------|
| exp_default_rave | Default eval + RAVE (800 sims, 5 dets) | 42% [32.8-51.8] | 78.0 |
| exp_default_no_rave | Default eval, no RAVE (800 sims, 5 dets) | 53% [43.3-62.5] | 89.8 |
| exp_tight_rave | Tight scales + RAVE | 36% [27.3-45.8] | 75.3 |

**Finding**: RAVE consistently hurts performance by ~10-15 percentage points.
In Carcassonne, tile placement is highly position-dependent — placing tile X at
(3,4) is completely different from placing it at (5,6). AMAF statistics average
across positions, creating noise that misleads the search tree.

---

## Phase 5: Determinization Count

**Question**: Do more determinizations improve play?

| Profile | Sims | Dets | Sims/Det | Win % vs Medium |
|---------|------|------|----------|-----------------|
| medium (baseline) | 300 | 3 | 100 | — |
| exp_default_no_rave | 800 | 5 | 160 | 53% |
| exp_more_dets | 800 | 8 | 100 | 50% |
| exp_dets_only | 300 | 8 | 37 | 37% |

**Finding**: More determinizations don't help unless sims-per-determinization
stays adequate. With 300 sims / 8 dets (37 sims each), performance drops
significantly. The sweet spot is 5 determinizations with 800 sims (160 each).

---

## Phase 6: V2 Evaluator (Unified Score Space)

**Hypothesis**: The v1 evaluator's architecture — four separate sigmoid-compressed
components weighted-averaged together — loses too much signal. Each component
independently compresses to [0,1], then the weighted average always lands near
0.5. A 10-point score lead plus 10-point potential advantage should combine
additively, not go through separate sigmoids.

**V2 design**: All signals computed in raw point-equivalents, combined with
game-progress-dependent weights, then a single final sigmoid:

```
total_advantage = score_weight * score_diff
               + potential_weight * expected_points_diff
               + field_weight * field_points_diff
               + meeple_weight * meeple_point_equivalent_diff
               - stuck_meeple_penalty

eval = sigmoid(total_advantage, scale)
```

Key differences from v1:
- Potential is estimated in raw expected points (completion_probability * scoring_value)
- Meeples are valued in point-equivalents (4 pts * (1 - 0.7 * game_progress) per meeple)
- Stuck meeples (on features with <15% completion chance) are penalized
- Game-progress weights: score importance increases (0.35 -> 0.50), potential
  decreases (0.35 -> 0.20), field increases (0.10 -> 0.20)

| Profile | Scale | Win % vs Medium (100g) | Avg Score |
|---------|-------|----------------------|-----------|
| exp_v2_scale10 | 10 | **58%** [48.2-67.2] | 89.4 vs 77.7 |
| exp_v2_scale15 | 15 | 56% [46.2-65.3] | 88.1 vs 82.3 |
| exp_v2_scale20 | 20 | 55% [45.2-64.4] | 88.9 vs 82.4 |

**200-game validation** (v2_scale10 vs medium):

```
exp_v2_scale10: 114 wins (57.0%) [95% CI: 50.1%-63.7%]  avg=89.5
        medium:  83 wins (41.5%) [95% CI: 34.9%-48.4%]  avg=81.7
```

**Finding**: The v2 evaluator with scale=10 is statistically significantly
stronger than medium (lower CI bound > 50%). The unified score space provides
a sharper gradient for MCTS to exploit.

---

## Final Difficulty Ladder

| Matchup | Games | Winner | Win Rate | Avg Scores |
|---------|-------|--------|----------|------------|
| Easy vs Medium | 50 | Medium | **90%** [78.6-95.7] | 90.6 vs 53.6 |
| Easy vs Hard | 50 | Hard | **100%** [92.9-100.0] | 84.7 vs 48.3 |
| Medium vs Hard | 50 | Hard | **56%** [42.3-68.8] | 90.7 vs 86.2 |
| Medium vs Hard | 200 | Hard | **57%** [50.1-63.7] | 89.5 vs 81.7 |

### Profile Configuration

| Tier | Sims | Dets | Eval | RAVE | Time Limit |
|------|------|------|------|------|------------|
| **Easy** | 100 | 2 | None (score-diff only) | No | 1s |
| **Medium** | 300 | 3 | V1 default weights | No | 3s |
| **Hard** | 800 | 5 | V2 unified score space (scale=10) | No | 5s |

---

## Key Takeaways

1. **Evaluator architecture matters more than parameters.** Tuning weights within
   the v1 framework couldn't beat the default. Changing the architecture (v2
   unified score space) provided a statistically significant improvement.

2. **RAVE hurts in Carcassonne.** AMAF statistics are harmful when move quality
   is highly position-dependent. The previous hard bot (with RAVE) was actually
   weaker than medium.

3. **Double-sigmoid compression kills signal.** The v1 eval's four independent
   sigmoids averaged together always produced values near 0.5, making it hard
   for MCTS to distinguish good from bad positions.

4. **More simulations have diminishing returns.** With the same eval, 800 sims
   vs 300 sims gives only ~3% edge. The eval function quality is the bottleneck.

5. **Determinization count has a sweet spot.** Too many determinizations spread
   simulations too thin. 5 determinizations with 800 sims (160 sims/det) is
   optimal for the current time budget.

6. **Difficulty separation requires different mechanisms per tier.**
   - Easy vs Medium: eval function on/off (98% win rate difference)
   - Medium vs Hard: eval architecture change (57% win rate)
   - Sim count and MCTS params contribute minimally on their own

---

## Future Experiments

- **V2 weight tuning**: The internal game-progress weights in evaluate_v2 are
  hand-tuned. Systematic optimization (e.g., CLOP or Bayesian optimization
  over arena results) could find better values.
- **Better completion probability**: The current formula is crude. Tile-aware
  completion probability (checking which remaining tiles could fill each open
  edge) would improve the potential signal.
- **Opponent modeling**: The current eval treats the opponent as a mirror. A
  minimax-style approach within the eval could improve play.
- **Progressive widening tuning**: pw_c=2 and pw_alpha=0.5 are defaults. Arena
  experiments could optimize these.
- **Time management**: Spending more time on critical decisions (e.g., early
  farmer placements) and less on forced moves.
