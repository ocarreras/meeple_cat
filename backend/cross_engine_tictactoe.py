#!/usr/bin/env python3
"""Cross-engine TicTacToe arena: isolates MCTS algorithm correctness.

If both Python and Rust MCTS play TicTacToe near-perfectly but Rust MCTS
plays Carcassonne much worse, the bug is in the Carcassonne game logic,
not in the MCTS algorithm itself.

Run from backend/:
    uv run python cross_engine_tictactoe.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time


RUST_BINARY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "game-engine", "target", "release", "meeple-game-engine",
)

GRPC_PORT = 50099

# Modest MCTS budget — TicTacToe is tiny, 100 sims is plenty for perfect play
MCTS_PARAMS = dict(
    num_simulations=100,
    time_limit_ms=999999,
    exploration_constant=1.41,
    num_determinizations=1,  # TicTacToe is deterministic
)

NUM_GAMES = 50


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 1. Build Rust engine
    if "--no-build" not in sys.argv:
        print("Building Rust game engine (release)...")
        env = {**os.environ, "PATH": os.environ.get("PATH", "") + ":" + os.path.expanduser("~/.cargo/bin")}
        r = subprocess.run(
            ["cargo", "build", "--release"],
            cwd="../game-engine", capture_output=True, text=True, env=env,
        )
        if r.returncode != 0:
            print(f"Build failed:\n{r.stderr}")
            sys.exit(1)
        print("Done.\n")
    else:
        print("Skipping build (--no-build).\n")

    # 2. Start Rust gRPC server
    print(f"Starting Rust engine on port {GRPC_PORT}...")
    rust_log = open("/tmp/rust_ttt_server.log", "w")
    proc = subprocess.Popen(
        [RUST_BINARY, "--port", str(GRPC_PORT)],
        stdout=rust_log, stderr=rust_log,
    )
    time.sleep(1.0)
    print("Ready.\n")

    try:
        results = _run_all_tests()
    except Exception as e:
        print(f"\nError: {e}")
        rust_log.flush()
        with open("/tmp/rust_ttt_server.log") as f:
            log = f.read()
        if log:
            print(f"\nRust server log:\n{log}")
        raise
    finally:
        proc.terminate()
        proc.wait()
        rust_log.close()

    # Final verdict
    print()
    print("=" * 60)
    print("  VERDICT".center(60))
    print("=" * 60)
    all_pass = all(r["pass"] for r in results)
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"  [{status}] {r['name']}: {r['detail']}")
    print()
    if all_pass:
        print("  MCTS algorithm is CORRECT in both engines.")
        print("  The Carcassonne quality gap is in the game plugin,")
        print("  not the MCTS core. Investigate: valid actions,")
        print("  features, scoring, or apply_action divergence.")
    else:
        print("  MCTS algorithm has a BUG.")
        print("  Fix mcts.rs / simulator.rs before debugging")
        print("  Carcassonne-specific logic.")


def _run_all_tests() -> list[dict]:
    from src.engine.arena import run_arena
    from src.engine.bot_strategy import MCTSStrategy, RandomStrategy, GrpcMctsStrategy
    from src.games.tictactoe.plugin import TicTacToePlugin

    plugin = TicTacToePlugin()
    results = []

    # ----------------------------------------------------------------
    # Test 1: Python MCTS vs Random
    # ----------------------------------------------------------------
    print("Test 1: Python MCTS vs Random ({} games)".format(NUM_GAMES))
    python_mcts = MCTSStrategy(**MCTS_PARAMS)
    random_strat = RandomStrategy()
    r = run_arena(plugin, {"Py-MCTS": python_mcts, "Random": random_strat},
                  num_games=NUM_GAMES, base_seed=42, alternate_seats=True)
    py_wr = r.win_rate("Py-MCTS")
    print(f"  Py-MCTS: {r.wins['Py-MCTS']} wins  Random: {r.wins['Random']} wins  Draws: {r.draws}")
    passed = py_wr >= 0.80
    results.append({"name": "Python MCTS vs Random", "pass": passed,
                     "detail": f"Py-MCTS wins {py_wr:.0%} (need >=80%)"})
    print()

    # ----------------------------------------------------------------
    # Test 2: Rust MCTS vs Random (via gRPC, Python Random as opponent)
    # ----------------------------------------------------------------
    print("Test 2: Rust MCTS vs Random ({} games)".format(NUM_GAMES))
    rust_mcts = GrpcMctsStrategy(
        grpc_address=f"localhost:{GRPC_PORT}",
        game_id="tictactoe",
        **MCTS_PARAMS,
    )
    r = run_arena(plugin, {"Rust-MCTS": rust_mcts, "Random": random_strat},
                  num_games=NUM_GAMES, base_seed=42, alternate_seats=True)
    rust_wr = r.win_rate("Rust-MCTS")
    print(f"  Rust-MCTS: {r.wins['Rust-MCTS']} wins  Random: {r.wins['Random']} wins  Draws: {r.draws}")
    passed = rust_wr >= 0.80
    results.append({"name": "Rust MCTS vs Random", "pass": passed,
                     "detail": f"Rust-MCTS wins {rust_wr:.0%} (need >=80%)"})
    print()

    # ----------------------------------------------------------------
    # Test 3: Cross-engine — Python MCTS vs Rust MCTS
    # ----------------------------------------------------------------
    n_cross = NUM_GAMES * 2  # more games for tighter CI
    print("Test 3: Python MCTS vs Rust MCTS ({} games)".format(n_cross))
    r = run_arena(plugin, {"Py-MCTS": python_mcts, "Rust-MCTS": rust_mcts},
                  num_games=n_cross, base_seed=42, alternate_seats=True)
    py_wr = r.win_rate("Py-MCTS")
    rs_wr = r.win_rate("Rust-MCTS")
    gap = abs(py_wr - rs_wr)
    print(f"  Py-MCTS: {r.wins['Py-MCTS']} wins ({py_wr:.0%})  Rust-MCTS: {r.wins['Rust-MCTS']} wins ({rs_wr:.0%})  Draws: {r.draws}")
    passed = gap <= 0.25  # allow 25pp gap (some variance expected)
    results.append({"name": "Cross-engine Py vs Rust", "pass": passed,
                     "detail": f"gap={gap:.0%} (need <=25pp)"})
    print()

    # ----------------------------------------------------------------
    # Test 4: Python MCTS vs Python MCTS (baseline symmetry)
    # ----------------------------------------------------------------
    print("Test 4: Python MCTS vs Python MCTS ({} games, baseline)".format(NUM_GAMES))
    py_mcts_a = MCTSStrategy(**MCTS_PARAMS)
    py_mcts_b = MCTSStrategy(**MCTS_PARAMS)
    r = run_arena(plugin, {"Py-A": py_mcts_a, "Py-B": py_mcts_b},
                  num_games=NUM_GAMES, base_seed=42, alternate_seats=True)
    py_a_wr = r.win_rate("Py-A")
    py_b_wr = r.win_rate("Py-B")
    gap = abs(py_a_wr - py_b_wr)
    print(f"  Py-A: {r.wins['Py-A']} wins ({py_a_wr:.0%})  Py-B: {r.wins['Py-B']} wins ({py_b_wr:.0%})  Draws: {r.draws}")
    passed = gap <= 0.30
    results.append({"name": "Python MCTS symmetry", "pass": passed,
                     "detail": f"gap={gap:.0%} (need <=30pp)"})
    print()

    return results


if __name__ == "__main__":
    main()
