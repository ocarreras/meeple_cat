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


logger = __import__("logging").getLogger(__name__)


class GrpcMctsStrategy:
    """Delegates MCTS search to the Rust game engine via a single gRPC call."""

    def __init__(
        self,
        grpc_address: str,
        game_id: str,
        num_simulations: int = 500,
        time_limit_ms: float = 2000,
        exploration_constant: float = 1.41,
        num_determinizations: int = 5,
        eval_profile: str = "",
        pw_c: float = 2.0,
        pw_alpha: float = 0.5,
        use_rave: bool = False,
        rave_k: float = 100.0,
        max_amaf_depth: int = 4,
        rave_fpu: bool = True,
        tile_aware_amaf: bool = False,
    ) -> None:
        import grpc as _grpc
        from src.engine.proto import game_engine_pb2 as _pb2
        from src.engine.proto import game_engine_pb2_grpc as _pb2_grpc

        self._pb2 = _pb2
        self._stub = _pb2_grpc.GameEngineServiceStub(_grpc.insecure_channel(grpc_address))
        self._game_id = game_id
        self.num_simulations = num_simulations
        self.time_limit_ms = time_limit_ms
        self.exploration_constant = exploration_constant
        self.num_determinizations = num_determinizations
        self.eval_profile = eval_profile
        self.pw_c = pw_c
        self.pw_alpha = pw_alpha
        self.use_rave = use_rave
        self.rave_k = rave_k
        self.max_amaf_depth = max_amaf_depth
        self.rave_fpu = rave_fpu
        self.tile_aware_amaf = tile_aware_amaf

    def choose_action(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        plugin: GamePlugin,
    ) -> dict:
        import json

        from src.engine.grpc_plugin import _phase_to_proto

        resp = self._stub.MctsSearch(
            self._pb2.MctsSearchRequest(
                game_id=self._game_id,
                game_data_json=json.dumps(game_data).encode(),
                phase=_phase_to_proto(phase),
                player_id=player_id,
                players=[],  # Not needed for MCTS search RPC — Rust reconstructs from game_data
                num_simulations=self.num_simulations,
                time_limit_ms=self.time_limit_ms,
                exploration_constant=self.exploration_constant,
                num_determinizations=self.num_determinizations,
                eval_profile=self.eval_profile,
                pw_c=self.pw_c,
                pw_alpha=self.pw_alpha,
                use_rave=self.use_rave,
                rave_k=self.rave_k,
                max_amaf_depth=self.max_amaf_depth,
                rave_fpu=self.rave_fpu,
                tile_aware_amaf=self.tile_aware_amaf,
            )
        )
        logger.info(
            "MCTS search: player=%s iters=%d elapsed=%.0fms eval=%s",
            player_id, resp.iterations_run, resp.elapsed_ms, self.eval_profile,
        )
        return json.loads(resp.action_json)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_STRATEGY_FACTORIES: dict[str, Callable[..., BotStrategy]] = {
    "random": lambda seed=None, **_kwargs: RandomStrategy(seed=seed),
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
