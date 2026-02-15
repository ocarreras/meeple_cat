"""CLI for running bot-vs-bot arena matches.

Usage::

    uv run python -m src.engine.arena_cli --p1 random --p2 mcts --games 50
"""

from __future__ import annotations

import argparse
import sys

from src.engine.arena import run_arena
from src.engine.bot_strategy import MCTSStrategy, RandomStrategy


def _make_strategy(name: str, args: argparse.Namespace):
    if name == "random":
        return RandomStrategy()
    if name == "mcts":
        from src.games.carcassonne.evaluator import carcassonne_eval

        return MCTSStrategy(
            num_simulations=args.mcts_sims,
            time_limit_ms=args.mcts_time_ms,
            num_determinizations=args.mcts_dets,
            eval_fn=carcassonne_eval,
        )
    print(f"Unknown strategy: {name}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot-vs-Bot Arena")
    parser.add_argument("--game", default="carcassonne")
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--p1", default="random", help="Strategy for player 1")
    parser.add_argument("--p2", default="mcts", help="Strategy for player 2")
    parser.add_argument("--mcts-sims", type=int, default=200)
    parser.add_argument("--mcts-time-ms", type=float, default=1000)
    parser.add_argument("--mcts-dets", type=int, default=3)
    args = parser.parse_args()

    # Resolve plugin
    if args.game == "carcassonne":
        from src.games.carcassonne.plugin import CarcassonnePlugin

        plugin = CarcassonnePlugin()
    else:
        print(f"Unknown game: {args.game}", file=sys.stderr)
        sys.exit(1)

    # Build strategies — handle same-name case
    if args.p1 == args.p2:
        names = {f"{args.p1}_1": _make_strategy(args.p1, args),
                 f"{args.p2}_2": _make_strategy(args.p2, args)}
    else:
        names = {args.p1: _make_strategy(args.p1, args),
                 args.p2: _make_strategy(args.p2, args)}

    print(f"Arena: {' vs '.join(names.keys())}, {args.games} games")
    print()

    result = run_arena(
        plugin=plugin,
        strategies=names,
        num_games=args.games,
        base_seed=args.seed,
        progress_callback=lambda done, total: print(
            f"\r  Game {done}/{total}", end="", flush=True
        ),
    )
    print()
    print()
    print(result.summary())


if __name__ == "__main__":
    main()
