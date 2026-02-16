"""CLI for running bot-vs-bot arena matches.

Usage::

    uv run python -m src.engine.arena_cli --p1 random --p2 mcts --games 50

    # Compare evaluator profiles
    uv run python -m src.engine.arena_cli --p1 mcts --p1-eval default \\
        --p2 mcts --p2-eval aggressive --games 100

    # MCTS vs MCTS+RAVE
    uv run python -m src.engine.arena_cli --p1 mcts --p2 mcts --p2-rave --games 50

    # Control progressive widening
    uv run python -m src.engine.arena_cli --p1 random --p2 mcts \\
        --pw-c 2.0 --pw-alpha 0.5 --games 50
"""

from __future__ import annotations

import argparse
import sys

from src.engine.arena import run_arena
from src.engine.bot_strategy import MCTSStrategy, RandomStrategy


def _make_strategy(
    name: str,
    args: argparse.Namespace,
    eval_profile: str = "default",
    use_rave: bool = False,
):
    if name == "random":
        return RandomStrategy()
    if name == "mcts":
        from src.games.carcassonne.evaluator import (
            WEIGHT_PRESETS,
            make_carcassonne_eval,
        )

        weights = WEIGHT_PRESETS.get(eval_profile)
        if weights is None:
            print(
                f"Unknown eval profile: {eval_profile!r}. "
                f"Available: {', '.join(WEIGHT_PRESETS.keys())}",
                file=sys.stderr,
            )
            sys.exit(1)

        eval_fn = make_carcassonne_eval(weights)

        return MCTSStrategy(
            num_simulations=args.mcts_sims,
            time_limit_ms=args.mcts_time_ms,
            num_determinizations=args.mcts_dets,
            eval_fn=eval_fn,
            pw_c=args.pw_c,
            pw_alpha=args.pw_alpha,
            use_rave=use_rave,
            rave_k=args.rave_k,
            max_amaf_depth=args.max_amaf_depth,
            rave_fpu=args.rave_fpu,
            tile_aware_amaf=args.tile_aware_amaf,
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
    parser.add_argument(
        "--p1-eval",
        default="default",
        help="Evaluator profile for p1 (default, aggressive, field_heavy, conservative)",
    )
    parser.add_argument(
        "--p2-eval",
        default="default",
        help="Evaluator profile for p2 (default, aggressive, field_heavy, conservative)",
    )
    parser.add_argument(
        "--p1-rave",
        action="store_true",
        help="Enable RAVE/AMAF for player 1",
    )
    parser.add_argument(
        "--p2-rave",
        action="store_true",
        help="Enable RAVE/AMAF for player 2",
    )
    parser.add_argument("--mcts-sims", type=int, default=200)
    parser.add_argument("--mcts-time-ms", type=float, default=1000)
    parser.add_argument("--mcts-dets", type=int, default=3)
    parser.add_argument(
        "--pw-c", type=float, default=2.0, help="Progressive widening constant"
    )
    parser.add_argument(
        "--pw-alpha",
        type=float,
        default=0.5,
        help="Progressive widening exponent (0 = disabled)",
    )
    parser.add_argument(
        "--rave-k",
        type=float,
        default=100.0,
        help="RAVE equivalence parameter (higher = trust AMAF longer)",
    )
    parser.add_argument(
        "--max-amaf-depth",
        type=int,
        default=4,
        help="AMAF depth limit in plies (0 = unlimited, 4 = 2 full turns)",
    )
    parser.add_argument(
        "--rave-fpu",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use AMAF as first-play urgency prior for unvisited children",
    )
    parser.add_argument(
        "--tile-aware-amaf",
        action="store_true",
        help="Include tile type in AMAF keys",
    )
    args = parser.parse_args()

    # Resolve plugin
    if args.game == "carcassonne":
        from src.games.carcassonne.plugin import CarcassonnePlugin

        plugin = CarcassonnePlugin()
    else:
        print(f"Unknown game: {args.game}", file=sys.stderr)
        sys.exit(1)

    # Build strategy labels for display
    def _label(name: str, profile: str, rave: bool) -> str:
        parts = [name]
        if name == "mcts":
            if profile != "default":
                parts = [f"mcts({profile})"]
            if rave:
                parts.append("+rave")
        return "".join(parts)

    p1_label = _label(args.p1, args.p1_eval, args.p1_rave)
    p2_label = _label(args.p2, args.p2_eval, args.p2_rave)

    # Handle same-label case
    if p1_label == p2_label:
        p1_label = f"{p1_label}_1"
        p2_label = f"{p2_label}_2"

    names = {
        p1_label: _make_strategy(args.p1, args, args.p1_eval, args.p1_rave),
        p2_label: _make_strategy(args.p2, args, args.p2_eval, args.p2_rave),
    }

    print(f"Arena: {' vs '.join(names.keys())}, {args.games} games")
    if args.p1 == "mcts" or args.p2 == "mcts":
        print(
            f"  MCTS: sims={args.mcts_sims}, time={args.mcts_time_ms}ms, "
            f"dets={args.mcts_dets}, pw_c={args.pw_c}, pw_alpha={args.pw_alpha}"
        )
        if args.p1_rave or args.p2_rave:
            print(
                f"  RAVE: k={args.rave_k}, max_amaf_depth={args.max_amaf_depth}, "
                f"fpu={'on' if args.rave_fpu else 'off'}"
                f"{', tile_aware' if args.tile_aware_amaf else ''}"
            )
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
