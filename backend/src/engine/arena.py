"""Bot-vs-Bot arena — run N games between strategies and report results."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

from src.engine.bot_strategy import BotStrategy
from src.engine.game_simulator import (
    SimulationState,
    apply_action_and_resolve,
)
from src.engine.models import Action, GameConfig, GameResult, Player, PlayerId
from src.engine.protocol import GamePlugin


@dataclass
class ArenaResult:
    """Aggregated results from an arena run."""

    num_games: int
    wins: dict[str, int]
    draws: int
    total_scores: dict[str, list[float]]
    game_durations_ms: list[float]

    def win_rate(self, name: str) -> float:
        return self.wins.get(name, 0) / max(self.num_games, 1)

    def avg_score(self, name: str) -> float:
        scores = self.total_scores.get(name, [])
        return sum(scores) / max(len(scores), 1)

    def score_stddev(self, name: str) -> float:
        scores = self.total_scores.get(name, [])
        if len(scores) < 2:
            return 0.0
        avg = self.avg_score(name)
        variance = sum((s - avg) ** 2 for s in scores) / (len(scores) - 1)
        return math.sqrt(variance)

    def confidence_interval_95(self, name: str) -> tuple[float, float]:
        """95% Wilson score confidence interval for win rate."""
        n = self.num_games
        if n == 0:
            return (0.0, 0.0)
        p = self.win_rate(name)
        z = 1.96
        denom = 1 + z**2 / n
        center = (p + z**2 / (2 * n)) / denom
        margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
        return (max(0.0, center - margin), min(1.0, center + margin))

    def summary(self) -> str:
        lines = [f"Arena Results ({self.num_games} games)"]
        lines.append("=" * 60)
        for name in self.wins:
            wr = self.win_rate(name)
            ci_lo, ci_hi = self.confidence_interval_95(name)
            avg = self.avg_score(name)
            std = self.score_stddev(name)
            lines.append(
                f"  {name:>12s}: {self.wins[name]:3d} wins "
                f"({wr:5.1%})  "
                f"[95% CI: {ci_lo:.1%}-{ci_hi:.1%}]  "
                f"avg={avg:5.1f} +/- {std:4.1f}"
            )
        lines.append(f"  {'Draws':>12s}: {self.draws}")
        if self.game_durations_ms:
            avg_ms = sum(self.game_durations_ms) / len(self.game_durations_ms)
            total_s = sum(self.game_durations_ms) / 1000
            lines.append(f"  Avg game: {avg_ms:.0f}ms  |  Total: {total_s:.1f}s")
        return "\n".join(lines)


def run_arena(
    plugin: GamePlugin,
    strategies: dict[str, BotStrategy],
    num_games: int = 100,
    base_seed: int = 0,
    num_players: int = 2,
    game_options: dict | None = None,
    alternate_seats: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ArenaResult:
    """Run *num_games* between the given strategies and return aggregated stats.

    Parameters
    ----------
    plugin:
        The game plugin to use.
    strategies:
        Mapping of ``strategy_name -> BotStrategy``.  Must have exactly
        *num_players* entries.
    num_games:
        How many games to play.
    base_seed:
        Game *i* uses ``random_seed = base_seed + i``.
    alternate_seats:
        Rotate seat assignments each game so every strategy plays
        each seat equally.
    progress_callback:
        Called with ``(games_completed, total_games)`` after each game.
    """
    strategy_names = list(strategies.keys())
    assert len(strategy_names) == num_players, (
        f"Need exactly {num_players} strategies, got {len(strategy_names)}"
    )

    result = ArenaResult(
        num_games=num_games,
        wins={n: 0 for n in strategy_names},
        draws=0,
        total_scores={n: [] for n in strategy_names},
        game_durations_ms=[],
    )

    for game_idx in range(num_games):
        seed = base_seed + game_idx

        # Determine seat assignment
        if alternate_seats:
            seat_assignment = [
                strategy_names[(i + game_idx) % num_players]
                for i in range(num_players)
            ]
        else:
            seat_assignment = strategy_names[:num_players]

        players = [
            Player(
                player_id=PlayerId(f"p{i}"),
                display_name=seat_assignment[i],
                seat_index=i,
                is_bot=True,
                bot_id=seat_assignment[i],
            )
            for i in range(num_players)
        ]

        pid_to_strategy = {
            f"p{i}": strategies[seat_assignment[i]]
            for i in range(num_players)
        }
        pid_to_name = {f"p{i}": seat_assignment[i] for i in range(num_players)}

        config = GameConfig(random_seed=seed, options=game_options or {})

        t0 = time.monotonic()
        game_result = _play_one_game(plugin, players, config, pid_to_strategy)
        elapsed_ms = (time.monotonic() - t0) * 1000
        result.game_durations_ms.append(elapsed_ms)

        if game_result is None:
            result.draws += 1
            for name in strategy_names:
                result.total_scores[name].append(0.0)
        else:
            for pid, score in game_result.final_scores.items():
                name = pid_to_name.get(pid)
                if name:
                    result.total_scores[name].append(score)

            if len(game_result.winners) == 1:
                winner_name = pid_to_name.get(game_result.winners[0])
                if winner_name:
                    result.wins[winner_name] += 1
            else:
                result.draws += 1

        if progress_callback:
            progress_callback(game_idx + 1, num_games)

    return result


def _play_one_game(
    plugin: GamePlugin,
    players: list[Player],
    config: GameConfig,
    pid_to_strategy: dict[str, BotStrategy],
) -> GameResult | None:
    """Play a single game synchronously. Returns GameResult or None."""
    game_data, phase, _ = plugin.create_initial_state(players, config)

    state = SimulationState(
        game_data=game_data,
        phase=phase,
        players=players,
        scores={p.player_id: 0.0 for p in players},
    )

    # Resolve initial auto-resolve phases
    _resolve_auto(plugin, state)

    max_iterations = 500
    for _ in range(max_iterations):
        if state.game_over is not None:
            break

        if state.phase.auto_resolve:
            _resolve_auto(plugin, state)
            continue

        acting_pid = _get_acting_pid(state.phase)
        if acting_pid is None:
            break

        strategy = pid_to_strategy.get(acting_pid)
        if strategy is None:
            break

        chosen = strategy.choose_action(
            state.game_data, state.phase, PlayerId(acting_pid), plugin
        )

        action_type = state.phase.expected_actions[0].action_type
        action = Action(
            action_type=action_type,
            player_id=PlayerId(acting_pid),
            payload=chosen,
        )
        apply_action_and_resolve(plugin, state, action)

    return state.game_over


def _resolve_auto(plugin: GamePlugin, state: SimulationState) -> None:
    """Resolve auto-resolve phases until a player-action phase or game over."""
    max_auto = 50
    while state.phase.auto_resolve and not state.game_over and max_auto > 0:
        max_auto -= 1
        pid = PlayerId("system")
        pi = state.phase.metadata.get("player_index")
        if pi is not None and pi < len(state.players):
            pid = state.players[pi].player_id
        synthetic = Action(action_type=state.phase.name, player_id=pid)
        apply_action_and_resolve(plugin, state, synthetic)


def _get_acting_pid(phase) -> str | None:
    if phase.expected_actions:
        return phase.expected_actions[0].player_id
    return None
