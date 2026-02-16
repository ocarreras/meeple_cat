#!/usr/bin/env python3
"""Benchmark: Python vs Rust game engine performance comparison.

Run from backend/:
    uv run python benchmark.py

Measures:
  1. Arena: random vs random (10-tile short games)
  2. Arena: random vs random (full 72-tile games)
  3. MCTS search: place_tile phase with many remaining tiles
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time


RUST_BINARY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "game-engine", "target", "release", "meeple-game-engine")


# ---------------------------------------------------------------------------
# Python benchmarks
# ---------------------------------------------------------------------------

def bench_python_arena(num_games: int, tile_count: int | None = None) -> dict:
    from src.engine.arena import run_arena
    from src.engine.bot_strategy import RandomStrategy
    from src.games.carcassonne.plugin import CarcassonnePlugin

    plugin = CarcassonnePlugin()
    strategies = {"random_a": RandomStrategy(seed=1), "random_b": RandomStrategy(seed=2)}
    opts = {"tile_count": tile_count} if tile_count else {}

    t0 = time.monotonic()
    result = run_arena(plugin=plugin, strategies=strategies, num_games=num_games, base_seed=42, game_options=opts)
    elapsed = time.monotonic() - t0
    avg_ms = sum(result.game_durations_ms) / max(len(result.game_durations_ms), 1)

    return {"elapsed_s": elapsed, "avg_game_ms": avg_ms, "games_per_sec": num_games / max(elapsed, 1e-9)}


def _advance_to_place_tile(plugin, players, seed=42, tile_count=72, *, max_actions=6):
    """Create a game and advance to a place_tile phase early enough that
    many tiles remain in the bag (ensuring MCTS simulations do real work)."""
    from src.engine.models import GameConfig, Action, PlayerId
    from src.engine.game_simulator import SimulationState, apply_action_and_resolve

    config = GameConfig(random_seed=seed, options={"tile_count": tile_count})
    game_data, phase, _ = plugin.create_initial_state(players, config)
    state = SimulationState(
        game_data=game_data, phase=phase, players=players,
        scores={p.player_id: 0.0 for p in players},
    )

    rng = random.Random(seed)
    tiles_placed = 0
    for _ in range(400):
        if state.game_over:
            break
        if state.phase.auto_resolve:
            pi = state.phase.metadata.get("player_index")
            pid = state.players[pi].player_id if pi is not None and pi < len(state.players) else PlayerId("system")
            apply_action_and_resolve(plugin, state, Action(action_type=state.phase.name, player_id=pid))
            continue
        if not state.phase.expected_actions:
            break
        acting = state.phase.expected_actions[0].player_id
        valid = plugin.get_valid_actions(state.game_data, state.phase, acting)
        if not valid:
            break

        # We want place_tile with multiple options AND many tiles still in bag
        remaining = len(state.game_data.get("tile_bag", []))
        if state.phase.name == "place_tile" and len(valid) > 3 and tiles_placed >= max_actions and remaining >= 30:
            return state, valid, remaining

        if state.phase.name == "place_tile":
            tiles_placed += 1

        apply_action_and_resolve(plugin, state, Action(
            action_type=state.phase.expected_actions[0].action_type,
            player_id=acting, payload=rng.choice(valid),
        ))

    return None, [], 0


def bench_python_mcts(num_simulations: int, num_determinizations: int) -> dict:
    from src.engine.models import Player, PlayerId
    from src.engine.mcts import mcts_search
    from src.games.carcassonne.plugin import CarcassonnePlugin
    from src.games.carcassonne.evaluator import make_carcassonne_eval, EvalWeights

    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId("p0"), display_name="A", seat_index=0),
        Player(player_id=PlayerId("p1"), display_name="B", seat_index=1),
    ]

    # Try multiple seeds to find a good mid-game position
    state = None
    for seed in range(200):
        state, valid, remaining = _advance_to_place_tile(plugin, players, seed=seed)
        if state and len(valid) > 3 and remaining >= 30:
            break

    if not state:
        return {"error": "could not find suitable position", "iters_per_sec": 0, "elapsed_s": 0}

    acting = state.phase.expected_actions[0].player_id
    eval_fn = make_carcassonne_eval(EvalWeights())
    print(f"(phase={state.phase.name}, {len(valid)} valid, {remaining} tiles left) ", end="", flush=True)

    t0 = time.monotonic()
    mcts_search(
        game_data=state.game_data, phase=state.phase, player_id=acting,
        plugin=plugin, num_simulations=num_simulations, time_limit_ms=999999,
        num_determinizations=num_determinizations, eval_fn=eval_fn,
    )
    elapsed = time.monotonic() - t0
    total = num_simulations * num_determinizations

    return {"elapsed_s": elapsed, "total_iterations": total, "iters_per_sec": total / max(elapsed, 1e-9)}


# ---------------------------------------------------------------------------
# Rust benchmarks (via gRPC)
# ---------------------------------------------------------------------------

def _start_rust(port):
    proc = subprocess.Popen([RUST_BINARY, "--port", str(port)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(0.5)
    return proc


def bench_rust_arena(num_games: int, tile_count: int | None = None) -> dict:
    import grpc
    from src.engine.proto import game_engine_pb2 as pb2, game_engine_pb2_grpc as pb2_grpc

    proc = _start_rust(50098)
    try:
        stub = pb2_grpc.GameEngineServiceStub(grpc.insecure_channel("localhost:50098"))
        opts = {"tile_count": str(tile_count)} if tile_count else {}

        t0 = time.monotonic()
        updates = list(stub.RunArena(pb2.RunArenaRequest(
            game_id="carcassonne", num_games=num_games, base_seed=42, alternate_seats=True,
            game_options=opts,
            strategies=[
                pb2.ArenaStrategyConfig(name="random_a", strategy_type="random"),
                pb2.ArenaStrategyConfig(name="random_b", strategy_type="random"),
            ],
        )))
        elapsed = time.monotonic() - t0

        engine_time = elapsed
        for u in updates:
            if u.HasField("final_result"):
                engine_time = u.final_result.total_duration_s

        return {
            "elapsed_s": elapsed, "engine_time_s": engine_time,
            "avg_game_ms": (engine_time * 1000) / max(num_games, 1),
            "games_per_sec": num_games / max(engine_time, 1e-9),
        }
    finally:
        proc.terminate()
        proc.wait()


def _advance_rust_to_place_tile(stub, pb2, seed=42, tile_count=72, *, max_actions=6):
    """Advance a Rust game to a place_tile phase with many remaining tiles."""
    players_proto = [
        pb2.Player(player_id="p0", display_name="A", seat_index=0),
        pb2.Player(player_id="p1", display_name="B", seat_index=1),
    ]

    resp = stub.CreateInitialState(pb2.CreateInitialStateRequest(
        game_id="carcassonne", players=players_proto,
        config=pb2.GameConfig(random_seed=seed, options={"tile_count": str(tile_count)}),
    ))
    gd, ph = resp.game_data_json, resp.phase

    tiles_placed = 0
    for _ in range(400):
        if ph.auto_resolve:
            pi_str = ph.metadata.get("player_index", "")
            pid = "system"
            if pi_str:
                try:
                    idx = json.loads(pi_str)
                    pid = f"p{idx}" if isinstance(idx, int) and idx < 2 else "system"
                except Exception:
                    pass
            r = stub.ApplyAction(pb2.ApplyActionRequest(
                game_id="carcassonne", game_data_json=gd, phase=ph,
                action=pb2.Action(action_type=ph.name, player_id=pid, payload_json=b"{}"),
                players=players_proto,
            ))
            gd, ph = r.result.game_data_json, r.result.next_phase
            if r.result.HasField("game_over"):
                return None, None, None, 0, 0
            continue

        if not ph.expected_actions:
            break
        acting = ph.expected_actions[0].player_id
        vr = stub.GetValidActions(pb2.GetValidActionsRequest(
            game_id="carcassonne", game_data_json=gd, phase=ph, player_id=acting,
        ))
        if not vr.actions_json:
            break

        # Parse game_data to check remaining tiles
        game_data_dict = json.loads(gd)
        remaining = len(game_data_dict.get("tile_bag", []))

        if ph.name == "place_tile" and len(vr.actions_json) > 3 and tiles_placed >= max_actions and remaining >= 30:
            return gd, ph, players_proto, len(vr.actions_json), remaining

        if ph.name == "place_tile":
            tiles_placed += 1

        r = stub.ApplyAction(pb2.ApplyActionRequest(
            game_id="carcassonne", game_data_json=gd, phase=ph,
            action=pb2.Action(
                action_type=ph.expected_actions[0].action_type,
                player_id=acting, payload_json=vr.actions_json[0],
            ),
            players=players_proto,
        ))
        gd, ph = r.result.game_data_json, r.result.next_phase
        if r.result.HasField("game_over"):
            return None, None, None, 0, 0

    return None, None, None, 0, 0


def bench_rust_mcts(num_simulations: int, num_determinizations: int) -> dict:
    import grpc
    from src.engine.proto import game_engine_pb2 as pb2, game_engine_pb2_grpc as pb2_grpc

    proc = _start_rust(50097)
    try:
        stub = pb2_grpc.GameEngineServiceStub(grpc.insecure_channel("localhost:50097"))

        gd, ph, players_proto = None, None, None
        num_valid, remaining = 0, 0
        for seed in range(200):
            gd, ph, players_proto, num_valid, remaining = _advance_rust_to_place_tile(stub, pb2, seed=seed)
            if gd is not None and num_valid > 3 and remaining >= 30:
                break

        if gd is None:
            return {"error": "could not find suitable position", "iters_per_sec": 0, "elapsed_s": 0}

        acting = ph.expected_actions[0].player_id if ph.expected_actions else "p0"
        print(f"(phase={ph.name}, {num_valid} valid, {remaining} tiles left) ", end="", flush=True)

        t0 = time.monotonic()
        mr = stub.MctsSearch(pb2.MctsSearchRequest(
            game_id="carcassonne", game_data_json=gd, phase=ph,
            player_id=acting, players=players_proto,
            num_simulations=num_simulations, time_limit_ms=999999,
            num_determinizations=num_determinizations,
        ))
        elapsed = time.monotonic() - t0
        total = num_simulations * num_determinizations

        return {
            "elapsed_s": elapsed, "engine_ms": mr.elapsed_ms,
            "total_iterations": total,
            "iters_per_sec": total / max(mr.elapsed_ms / 1000, 1e-9),
        }
    finally:
        proc.terminate()
        proc.wait()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("Building Rust game engine (release)...")
    env = {**os.environ, "PATH": os.environ.get("PATH", "") + ":" + os.path.expanduser("~/.cargo/bin")}
    r = subprocess.run(["cargo", "build", "--release"], cwd="../game-engine", capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(f"Build failed:\n{r.stderr}")
        sys.exit(1)
    print("Done.\n")

    W = 70
    print("=" * W)
    print("  BENCHMARK: Python vs Rust Game Engine".center(W))
    print("=" * W)
    print()

    results = []

    # 1. Arena short
    N1 = 200
    print(f"[1/4] Arena: random vs random, {N1} short games (10 tiles)")
    print("  Python...", end=" ", flush=True)
    py1 = bench_python_arena(N1, tile_count=10)
    print(f"{py1['elapsed_s']:.2f}s  ({py1['games_per_sec']:.0f} games/s, {py1['avg_game_ms']:.1f}ms/game)")
    print("  Rust...", end="   ", flush=True)
    rs1 = bench_rust_arena(N1, tile_count=10)
    print(f"{rs1['engine_time_s']:.3f}s  ({rs1['games_per_sec']:.0f} games/s, {rs1['avg_game_ms']:.2f}ms/game)")
    s1 = rs1["games_per_sec"] / max(py1["games_per_sec"], 1e-9)
    results.append(("Arena 10-tile", f"{py1['games_per_sec']:.0f} g/s", f"{rs1['games_per_sec']:.0f} g/s", s1))
    print(f"  => {s1:.0f}x speedup\n")

    # 2. Arena full
    N2 = 50
    print(f"[2/4] Arena: random vs random, {N2} full games (72 tiles)")
    print("  Python...", end=" ", flush=True)
    py2 = bench_python_arena(N2)
    print(f"{py2['elapsed_s']:.2f}s  ({py2['games_per_sec']:.1f} games/s, {py2['avg_game_ms']:.0f}ms/game)")
    print("  Rust...", end="   ", flush=True)
    rs2 = bench_rust_arena(N2)
    print(f"{rs2['engine_time_s']:.3f}s  ({rs2['games_per_sec']:.0f} games/s, {rs2['avg_game_ms']:.1f}ms/game)")
    s2 = rs2["games_per_sec"] / max(py2["games_per_sec"], 1e-9)
    results.append(("Arena full-game", f"{py2['games_per_sec']:.1f} g/s", f"{rs2['games_per_sec']:.0f} g/s", s2))
    print(f"  => {s2:.0f}x speedup\n")

    # 3. MCTS low budget (what the bot uses per move)
    SIMS, DETS = 200, 3
    total_iters = SIMS * DETS
    print(f"[3/4] MCTS search: {SIMS} sims x {DETS} dets = {total_iters} iterations")
    print("  Python... ", end="", flush=True)
    py3 = bench_python_mcts(SIMS, DETS)
    if py3.get("error"):
        print(f"ERROR: {py3['error']}")
    else:
        print(f"{py3['elapsed_s']:.3f}s  ({py3['iters_per_sec']:.0f} iters/s)")
    print("  Rust...   ", end="", flush=True)
    rs3 = bench_rust_mcts(SIMS, DETS)
    if rs3.get("error"):
        print(f"ERROR: {rs3['error']}")
    else:
        print(f"{rs3['elapsed_s']:.3f}s  ({rs3['iters_per_sec']:.0f} iters/s, engine={rs3['engine_ms']:.0f}ms)")
    if not py3.get("error") and not rs3.get("error"):
        s3 = rs3["iters_per_sec"] / max(py3["iters_per_sec"], 1e-9)
        results.append((f"MCTS {SIMS}x{DETS}", f"{py3['iters_per_sec']:.0f} it/s", f"{rs3['iters_per_sec']:.0f} it/s", s3))
        print(f"  => {s3:.0f}x speedup\n")
    else:
        print()

    # 4. MCTS heavy budget (stress test)
    SIMS2, DETS2 = 1000, 5
    total_iters2 = SIMS2 * DETS2
    print(f"[4/4] MCTS search: {SIMS2} sims x {DETS2} dets = {total_iters2} iterations")
    print("  Python... ", end="", flush=True)
    py4 = bench_python_mcts(SIMS2, DETS2)
    if py4.get("error"):
        print(f"ERROR: {py4['error']}")
    else:
        print(f"{py4['elapsed_s']:.3f}s  ({py4['iters_per_sec']:.0f} iters/s)")
    print("  Rust...   ", end="", flush=True)
    rs4 = bench_rust_mcts(SIMS2, DETS2)
    if rs4.get("error"):
        print(f"ERROR: {rs4['error']}")
    else:
        print(f"{rs4['elapsed_s']:.3f}s  ({rs4['iters_per_sec']:.0f} iters/s, engine={rs4['engine_ms']:.0f}ms)")
    if not py4.get("error") and not rs4.get("error"):
        s4 = rs4["iters_per_sec"] / max(py4["iters_per_sec"], 1e-9)
        results.append((f"MCTS {SIMS2}x{DETS2}", f"{py4['iters_per_sec']:.0f} it/s", f"{rs4['iters_per_sec']:.0f} it/s", s4))
        print(f"  => {s4:.0f}x speedup\n")
    else:
        print()

    # Summary
    print("=" * W)
    print("  RESULTS".center(W))
    print("=" * W)
    print()
    print(f"  {'Benchmark':<25s} {'Python':>15s} {'Rust':>15s} {'Speedup':>10s}")
    print(f"  {'-'*25} {'-'*15} {'-'*15} {'-'*10}")
    for label, py_str, rs_str, speedup in results:
        print(f"  {label:<25s} {py_str:>15s} {rs_str:>15s} {speedup:>9.0f}x")
    print()
    print("  Notes:")
    print("  - Rust uses strongly-typed CarcassonneState (no JSON in hot path)")
    print("  - MCTS speedup: typed struct Clone + direct field access vs copy.deepcopy")
    print("  - Arena speedup: typed simulation loop avoids JSON ser/deser per action")
    print()


if __name__ == "__main__":
    main()
