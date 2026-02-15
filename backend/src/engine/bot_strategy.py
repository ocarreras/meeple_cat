"""Bot strategy abstraction — maps bot_id strings to action-selection callables."""

from __future__ import annotations

import random as _random
from typing import Callable, Protocol

from src.engine.models import Phase, PlayerId
from src.engine.protocol import GamePlugin


class BotStrategy(Protocol):
    """A bot strategy selects an action payload given the current game state."""

    def choose_action(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        plugin: GamePlugin,
    ) -> dict:
        """Return the chosen action payload (same shape as get_valid_actions items)."""
        ...


class RandomStrategy:
    """Picks a uniformly random valid action."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = _random.Random(seed)

    def choose_action(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        plugin: GamePlugin,
    ) -> dict:
        valid = plugin.get_valid_actions(game_data, phase, player_id)
        return self._rng.choice(valid)


class MCTSStrategy:
    """Wraps the MCTS engine as a BotStrategy."""

    def __init__(
        self,
        num_simulations: int = 500,
        time_limit_ms: float = 2000,
        exploration_constant: float = 1.41,
        num_determinizations: int = 5,
        eval_fn: Callable | None = None,
    ) -> None:
        self.num_simulations = num_simulations
        self.time_limit_ms = time_limit_ms
        self.exploration_constant = exploration_constant
        self.num_determinizations = num_determinizations
        self.eval_fn = eval_fn

    def choose_action(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        plugin: GamePlugin,
    ) -> dict:
        from src.engine.mcts import mcts_search

        return mcts_search(
            game_data=game_data,
            phase=phase,
            player_id=player_id,
            plugin=plugin,
            num_simulations=self.num_simulations,
            time_limit_ms=self.time_limit_ms,
            exploration_constant=self.exploration_constant,
            num_determinizations=self.num_determinizations,
            eval_fn=self.eval_fn,
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_STRATEGY_FACTORIES: dict[str, Callable[..., BotStrategy]] = {
    "random": lambda **kwargs: RandomStrategy(**kwargs),
    "mcts": lambda **kwargs: MCTSStrategy(**kwargs),
}


def get_strategy(bot_id: str, **kwargs: object) -> BotStrategy:
    """Create a BotStrategy instance for the given *bot_id*."""
    factory = _STRATEGY_FACTORIES.get(bot_id)
    if factory is None:
        raise ValueError(f"Unknown bot_id: {bot_id!r}")
    return factory(**kwargs)


def register_strategy(
    bot_id: str, factory: Callable[..., BotStrategy]
) -> None:
    """Register a new strategy factory."""
    _STRATEGY_FACTORIES[bot_id] = factory
