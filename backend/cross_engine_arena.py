#!/usr/bin/env python3
"""Cross-engine arena: Python MCTS vs Rust MCTS (via gRPC).

Both engines use the same MCTS parameters and the same game state
(Python's CarcassonnePlugin is the source of truth for state transitions).
The only difference is which MCTS engine selects moves.

Since both are searching the same game tree with the same budget,
results should be roughly even — this serves as a sanity check.

Run from backend/:
    uv run python cross_engine_arena.py
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

# MCTS parameters — same for both engines
MCTS_PARAMS = dict(
    num_simulations=500,
    time_limit_ms=999999,
    exploration_constant=1.41,
    num_determinizations=3,
)

NUM_GAMES = int(os.environ.get("NUM_GAMES", "50"))


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 1. Build Rust engine (skip if --no-build flag)
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
    rust_log = open("/tmp/rust_arena_server.log", "w")
    proc = subprocess.Popen(
        [RUST_BINARY, "--port", str(GRPC_PORT)],
        stdout=rust_log, stderr=rust_log,
    )
    time.sleep(1.0)
    print("Ready.\n")

    try:
        _run_arena()
    except Exception as e:
        print(f"\nError: {e}")
        rust_log.flush()
        with open("/tmp/rust_arena_server.log") as f:
            log = f.read()
        if log:
            print(f"\nRust server log:\n{log}")
        raise
    finally:
        proc.terminate()
        proc.wait()
        rust_log.close()


def _run_arena():
    from src.engine.arena import run_arena
    from src.engine.bot_strategy import MCTSStrategy, GrpcMctsStrategy
    from src.games.carcassonne.plugin import CarcassonnePlugin
    from src.games.carcassonne.evaluator import make_carcassonne_eval, EvalWeights

    plugin = CarcassonnePlugin()
    eval_fn = make_carcassonne_eval(EvalWeights())

    python_mcts = MCTSStrategy(eval_fn=eval_fn, **MCTS_PARAMS)
    rust_mcts = GrpcMctsStrategy(
        grpc_address=f"localhost:{GRPC_PORT}",
        game_id="carcassonne",
        eval_profile="default",
        **MCTS_PARAMS,
    )

    strategies = {
        "Python-MCTS": python_mcts,
        "Rust-MCTS": rust_mcts,
    }

    W = 60
    print("=" * W)
    print("  Cross-Engine Arena: Python MCTS vs Rust MCTS".center(W))
    print("=" * W)
    print(f"  Games: {NUM_GAMES}")
    print(f"  MCTS: {MCTS_PARAMS['num_simulations']} sims x {MCTS_PARAMS['num_determinizations']} dets")
    print(f"  Seats alternate each game")
    print()

    t0 = time.monotonic()

    def progress(done, total):
        elapsed = time.monotonic() - t0
        rate = done / max(elapsed, 1e-9)
        eta = (total - done) / max(rate, 1e-9)
        print(f"\r  Game {done}/{total}  ({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)", end="", flush=True)

    result = run_arena(
        plugin=plugin,
        strategies=strategies,
        num_games=NUM_GAMES,
        base_seed=42,
        alternate_seats=True,
        progress_callback=progress,
    )

    total_s = time.monotonic() - t0
    print(f"\r  Completed {NUM_GAMES} games in {total_s:.1f}s ({total_s/NUM_GAMES:.1f}s/game)")
    print()
    print(result.summary())
    print()

    # Sanity check verdict
    py_wr = result.win_rate("Python-MCTS")
    rs_wr = result.win_rate("Rust-MCTS")
    diff = abs(py_wr - rs_wr)
    if diff <= 0.20:
        print("  PASS: Win rates are within 20pp — engines appear equivalent.")
    else:
        print(f"  WARNING: Win rate gap is {diff:.0%} — investigate possible divergence.")


if __name__ == "__main__":
    main()
