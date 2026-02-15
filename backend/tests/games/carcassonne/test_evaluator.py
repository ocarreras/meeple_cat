"""Tests for the Carcassonne heuristic evaluator."""

from src.engine.game_simulator import (
    SimulationState,
    apply_action_and_resolve,
)
from src.engine.models import Action, GameConfig, Player, PlayerId
from src.games.carcassonne.evaluator import (
    _completion_probability,
    _sigmoid,
    carcassonne_eval,
)
from src.games.carcassonne.plugin import CarcassonnePlugin


def _make_state(seed=42, num_players=2):
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId(f"p{i}"), display_name=f"P{i}", seat_index=i)
        for i in range(num_players)
    ]
    config = GameConfig(random_seed=seed)
    game_data, phase, _ = plugin.create_initial_state(players, config)
    state = SimulationState(
        game_data=game_data, phase=phase, players=players,
        scores={p.player_id: 0.0 for p in players},
    )
    # Advance to place_tile
    draw = Action(action_type="draw_tile", player_id=PlayerId("p0"))
    apply_action_and_resolve(plugin, state, draw)
    return plugin, state


def test_eval_returns_value_in_range():
    """Evaluator should always return value in [0, 1]."""
    plugin, state = _make_state()
    val = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )
    assert 0.0 <= val <= 1.0


def test_eval_symmetric_at_start():
    """At the start of the game, both players should get similar evaluations."""
    plugin, state = _make_state()
    v0 = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )
    v1 = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p1"), state.players, plugin
    )
    # Should be close to 0.5 for both, and roughly symmetric
    assert abs(v0 - 0.5) < 0.15
    assert abs(v1 - 0.5) < 0.15


def test_eval_prefers_higher_score():
    """Player with higher score should get higher evaluation."""
    plugin, state = _make_state()

    # Manually give p0 a big score advantage
    state.game_data["scores"]["p0"] = 50
    state.game_data["scores"]["p1"] = 10

    v0 = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )
    v1 = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p1"), state.players, plugin
    )
    assert v0 > v1


def test_eval_across_many_states():
    """Run several turns and verify eval always returns [0, 1]."""
    plugin, state = _make_state()

    for _ in range(10):
        if state.game_over:
            break
        if state.phase.auto_resolve:
            pi = state.phase.metadata.get("player_index", 0)
            pid = state.players[pi].player_id
            action = Action(action_type=state.phase.name, player_id=pid)
            apply_action_and_resolve(plugin, state, action)
            continue

        acting_pid = state.phase.expected_actions[0].player_id
        valid = plugin.get_valid_actions(state.game_data, state.phase, acting_pid)
        if not valid:
            break

        # Evaluate before acting
        val = carcassonne_eval(
            state.game_data, state.phase, acting_pid, state.players, plugin
        )
        assert 0.0 <= val <= 1.0

        payload = valid[0]
        if state.phase.name == "place_meeple":
            payload = {"skip": True}

        action = Action(
            action_type=state.phase.expected_actions[0].action_type,
            player_id=acting_pid,
            payload=payload,
        )
        apply_action_and_resolve(plugin, state, action)


def test_completion_probability_bounds():
    assert _completion_probability(0, 50) == 1.0
    assert _completion_probability(5, 0) == 0.0
    # Many open edges with few tiles remaining → low probability
    assert 0.0 < _completion_probability(10, 5) < 1.0
    # Moderate case
    assert _completion_probability(2, 40) >= _completion_probability(5, 40)


def test_sigmoid_properties():
    assert abs(_sigmoid(0) - 0.5) < 1e-9
    assert _sigmoid(100) > 0.99
    assert _sigmoid(-100) < 0.01
