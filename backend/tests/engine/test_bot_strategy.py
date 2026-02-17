"""Tests for the bot strategy abstraction."""

import pytest

from src.engine.bot_strategy import (
    GrpcMctsStrategy,
    RandomStrategy,
    get_strategy,
    register_strategy,
)
from src.engine.models import Phase, PlayerId
from tests.engine.test_registry import MockPlugin


def test_random_strategy_returns_valid_action():
    plugin = MockPlugin()
    phase = Phase(
        name="play",
        expected_actions=[{"player_id": "p0", "action_type": "draw"}],
    )
    strategy = RandomStrategy(seed=123)
    valid = plugin.get_valid_actions({}, phase, PlayerId("p0"))
    chosen = strategy.choose_action({}, phase, PlayerId("p0"), plugin)
    assert chosen in valid


def test_random_strategy_deterministic_with_seed():
    plugin = MockPlugin()
    phase = Phase(
        name="play",
        expected_actions=[{"player_id": "p0", "action_type": "draw"}],
    )
    s1 = RandomStrategy(seed=7)
    s2 = RandomStrategy(seed=7)
    c1 = s1.choose_action({}, phase, PlayerId("p0"), plugin)
    c2 = s2.choose_action({}, phase, PlayerId("p0"), plugin)
    assert c1 == c2


def test_get_strategy_random():
    s = get_strategy("random")
    assert isinstance(s, RandomStrategy)


def test_get_strategy_mcts_after_registration():
    register_strategy(
        "mcts",
        lambda game_id="carcassonne", **kwargs: GrpcMctsStrategy(
            grpc_address="localhost:50051", game_id=game_id, **kwargs,
        ),
    )
    s = get_strategy("mcts", game_id="carcassonne")
    assert isinstance(s, GrpcMctsStrategy)


def test_get_strategy_unknown_raises():
    with pytest.raises(ValueError, match="Unknown bot_id"):
        get_strategy("does_not_exist")
