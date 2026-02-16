#!/usr/bin/env python3
"""Diagnostic: Compare Python and Rust evaluator outputs on the same game state."""

import json
import math
import os
import subprocess
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def main():
    from src.engine.models import Action, Phase, Player
    from src.games.carcassonne.plugin import CarcassonnePlugin
    from src.games.carcassonne.evaluator import (
        _evaluate, _sigmoid, _completion_probability, _meeple_counts,
        _raw_feature_potential, _estimate_field_value, _feature_controller,
        DEFAULT_WEIGHTS,
    )
    from src.games.carcassonne.types import FeatureType

    plugin = CarcassonnePlugin()
    players = [
        Player(player_id="p1", display_name="P1", seat_index=0),
        Player(player_id="p2", display_name="P2", seat_index=1),
    ]
    from src.engine.models import GameConfig
    config = GameConfig(random_seed=42)

    # Create and advance game to a mid-game state
    game_data, phase, _ = plugin.create_initial_state(players, config)

    # Play 10 turns deterministically (always pick first valid action)
    turns = 0
    max_turns = 10
    while phase.name != "game_over" and turns < max_turns:
        if phase.auto_resolve:
            pid = phase.metadata.get("player_index", 0)
            pid_str = players[pid].player_id if pid < len(players) else "system"
            action = Action(action_type=phase.name, player_id=pid_str)
            result = plugin.apply_action(game_data, phase, action, players)
            game_data = result.game_data
            phase = result.next_phase
            continue

        pid = phase.expected_actions[0].player_id
        valid = plugin.get_valid_actions(game_data, phase, pid)
        if not valid:
            break
        action = Action(
            action_type=phase.expected_actions[0].action_type,
            player_id=pid,
            payload=valid[0],
        )
        result = plugin.apply_action(game_data, phase, action, players)
        game_data = result.game_data
        phase = result.next_phase
        turns += 1

    # Now evaluate this state
    w = DEFAULT_WEIGHTS
    scores = game_data.get("scores", {})
    features = game_data.get("features", {})
    meeple_supply = game_data.get("meeple_supply", {})
    tiles_remaining = len(game_data.get("tile_bag", []))
    board_size = len(game_data["board"]["tiles"])
    total_tiles = board_size + tiles_remaining
    game_progress = 1.0 - (tiles_remaining / max(total_tiles, 1))

    player_id = "p1"

    # 1. Score differential
    my_score = scores.get(player_id, 0)
    opponent_scores = [s for pid, s in scores.items() if pid != player_id]
    max_opp = max(opponent_scores) if opponent_scores else 0
    score_diff = my_score - max_opp
    score_component = _sigmoid(score_diff, scale=w.score_scale)

    # 2. Feature potential
    my_potential = 0.0
    opp_potential = 0.0
    wasted_meeple_penalty = 0.0
    for feat in features.values():
        if feat.get("is_complete"):
            continue
        ft = feat["feature_type"]
        if ft in (FeatureType.FIELD, "field"):
            continue
        meeples = feat.get("meeples", [])
        if not meeples:
            continue
        tiles = feat.get("tiles", [])
        open_edges = feat.get("open_edges", [])
        pennants = feat.get("pennants", 0)
        potential = _raw_feature_potential(ft, tiles, open_edges, pennants, tiles_remaining, game_data)
        my_count, max_count, _ = _meeple_counts(meeples, player_id)
        if my_count == 0:
            opp_potential += potential
        elif my_count >= max_count:
            my_potential += potential
        else:
            opp_potential += potential
            wasted_meeple_penalty += my_count * 1.5

    potential_diff = my_potential - opp_potential - wasted_meeple_penalty
    potential_component = _sigmoid(potential_diff, scale=w.potential_scale)

    # 3. Meeple economy
    my_meeples = meeple_supply.get(player_id, 0)
    opp_meeple_list = [meeple_supply.get(p.player_id, 0) for p in players if p.player_id != player_id]
    avg_opp_meeples = sum(opp_meeple_list) / max(len(opp_meeple_list), 1)
    meeple_value = min(my_meeples / 7.0, 1.0)
    if my_meeples >= w.meeple_hoard_threshold and game_progress > w.meeple_hoard_progress_gate:
        meeple_value *= w.meeple_hoard_penalty
    if my_meeples == 0 and game_progress < 0.85:
        meeple_value *= 0.3
    elif my_meeples <= 1 and game_progress < 0.7:
        meeple_value *= 0.6
    relative = _sigmoid((my_meeples - avg_opp_meeples) * 0.5, scale=3.0)
    meeple_component = 0.5 * relative + 0.5 * meeple_value

    # 4. Field
    my_field = _estimate_field_value(game_data, player_id, tiles_remaining)
    opp_field_scores = [_estimate_field_value(game_data, p.player_id, tiles_remaining) for p in players if p.player_id != player_id]
    max_opp_field = max(opp_field_scores) if opp_field_scores else 0
    field_diff = my_field - max_opp_field
    field_component = _sigmoid(field_diff, scale=w.field_scale)

    # Weighted combo
    score_weight = w.score_base + w.score_delta * game_progress
    potential_weight = w.potential_base + w.potential_delta * game_progress
    meeple_weight = w.meeple_base + w.meeple_delta * game_progress
    field_weight = w.field_base + w.field_delta * game_progress

    value = (score_weight * score_component
             + potential_weight * potential_component
             + meeple_weight * meeple_component
             + field_weight * field_component)
    value = max(0.0, min(1.0, value))

    print("=" * 60)
    print("  PYTHON EVALUATOR DIAGNOSTIC")
    print("=" * 60)
    print(f"  Board tiles: {board_size}")
    print(f"  Tiles remaining: {tiles_remaining}")
    print(f"  Game progress: {game_progress:.4f}")
    print(f"  Scores: {dict(scores)}")
    print(f"  Meeple supply: {dict(meeple_supply)}")
    print(f"  Features: {len(features)} total")
    n_complete = sum(1 for f in features.values() if f.get("is_complete"))
    n_field = sum(1 for f in features.values() if f.get("feature_type") in (FeatureType.FIELD, "field"))
    print(f"    Complete: {n_complete}, Fields: {n_field}")
    print()
    print(f"  1. Score: my={my_score}, max_opp={max_opp}, diff={score_diff}")
    print(f"     component={score_component:.6f}  weight={score_weight:.4f}")
    print()
    print(f"  2. Potential: my={my_potential:.2f}, opp={opp_potential:.2f}, wasted={wasted_meeple_penalty:.2f}")
    print(f"     diff={potential_diff:.2f}  component={potential_component:.6f}  weight={potential_weight:.4f}")
    print()
    print(f"  3. Meeple: my={my_meeples}, avg_opp={avg_opp_meeples:.1f}")
    print(f"     value={meeple_value:.4f}  relative={relative:.6f}")
    print(f"     component={meeple_component:.6f}  weight={meeple_weight:.4f}")
    print()
    print(f"  4. Field: my={my_field:.2f}, max_opp={max_opp_field:.2f}, diff={field_diff:.2f}")
    print(f"     component={field_component:.6f}  weight={field_weight:.4f}")
    print()
    print(f"  FINAL VALUE: {value:.6f}")
    print()

    # Save game_data for Rust comparison
    json_path = "/tmp/eval_diagnostic_state.json"
    with open(json_path, "w") as f:
        json.dump(game_data, f)
    print(f"  State saved to {json_path}")
    print(f"  State size: {os.path.getsize(json_path)} bytes")


if __name__ == "__main__":
    main()
