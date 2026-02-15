"""Tests for the bot strategy abstraction."""

import pytest

from src.engine.bot_strategy import RandomStrategy, get_strategy
from src.engine.models import GameConfig, Phase, Player, PlayerId
from src.games.carcassonne.plugin import CarcassonnePlugin


def _make_place_tile_state():
    """Create a state at the place_tile phase."""
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId("p0"), display_name="P0", seat_index=0),
        Player(player_id=PlayerId("p1"), display_name="P1", seat_index=1),
    ]
    config = GameConfig(random_seed=42)
    game_data, phase, _ = plugin.create_initial_state(players, config)

    # Resolve draw_tile → place_tile
    from src.engine.models import Action
    from src.engine.game_simulator import apply_action_and_resolve, SimulationState

    state = SimulationState(
        game_data=game_data, phase=phase, players=players,
        scores={p.player_id: 0.0 for p in players},
    )
    draw = Action(action_type="draw_tile", player_id=PlayerId("p0"))
    apply_action_and_resolve(plugin, state, draw)
    return plugin, state


def test_random_strategy_returns_valid_action():
    plugin, state = _make_place_tile_state()
    strategy = RandomStrategy(seed=123)
    valid = plugin.get_valid_actions(state.game_data, state.phase, PlayerId("p0"))

    chosen = strategy.choose_action(
        state.game_data, state.phase, PlayerId("p0"), plugin
    )
    assert chosen in valid


def test_random_strategy_deterministic_with_seed():
    plugin, state = _make_place_tile_state()

    s1 = RandomStrategy(seed=7)
    s2 = RandomStrategy(seed=7)
    c1 = s1.choose_action(state.game_data, state.phase, PlayerId("p0"), plugin)
    c2 = s2.choose_action(state.game_data, state.phase, PlayerId("p0"), plugin)
    assert c1 == c2


def test_get_strategy_random():
    s = get_strategy("random")
    assert isinstance(s, RandomStrategy)


def test_get_strategy_mcts():
    from src.engine.bot_strategy import MCTSStrategy
    s = get_strategy("mcts")
    assert isinstance(s, MCTSStrategy)


def test_get_strategy_unknown_raises():
    with pytest.raises(ValueError, match="Unknown bot_id"):
        get_strategy("does_not_exist")
