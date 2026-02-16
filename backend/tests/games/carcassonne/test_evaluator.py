"""Tests for the Carcassonne heuristic evaluator."""

from src.engine.game_simulator import (
    SimulationState,
    apply_action_and_resolve,
)
from src.engine.models import Action, GameConfig, Player, PlayerId
from src.games.carcassonne.evaluator import (
    DEFAULT_WEIGHTS,
    WEIGHT_PRESETS,
    EvalWeights,
    _completion_probability,
    _meeple_counts,
    _sigmoid,
    carcassonne_eval,
    make_carcassonne_eval,
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


# ------------------------------------------------------------------
# EvalWeights and make_carcassonne_eval tests
# ------------------------------------------------------------------


def test_eval_weights_defaults():
    """EvalWeights defaults should match the documented values."""
    w = EvalWeights()
    assert w.score_base == 0.35
    assert w.score_delta == 0.10
    assert w.meeple_hoard_threshold == 6
    assert w.field_scale == 10.0


def test_weight_presets_exist():
    """All named presets should be available."""
    assert "default" in WEIGHT_PRESETS
    assert "aggressive" in WEIGHT_PRESETS
    assert "field_heavy" in WEIGHT_PRESETS
    assert "conservative" in WEIGHT_PRESETS
    assert WEIGHT_PRESETS["default"] is DEFAULT_WEIGHTS


def test_make_carcassonne_eval_default():
    """make_carcassonne_eval() should produce same result as carcassonne_eval."""
    plugin, state = _make_state()
    default_fn = make_carcassonne_eval()
    v_default = default_fn(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )
    v_direct = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )
    assert abs(v_default - v_direct) < 1e-9


def test_make_carcassonne_eval_custom_weights():
    """Custom weights should produce different evaluations than defaults."""
    plugin, state = _make_state()

    default_fn = make_carcassonne_eval(DEFAULT_WEIGHTS)
    aggressive_fn = make_carcassonne_eval(WEIGHT_PRESETS["aggressive"])

    v_default = default_fn(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )
    v_aggressive = aggressive_fn(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )

    # Different weight profiles should produce different evaluations
    # (they have different base weights so will differ numerically)
    assert isinstance(v_default, float)
    assert isinstance(v_aggressive, float)
    assert 0.0 <= v_default <= 1.0
    assert 0.0 <= v_aggressive <= 1.0
    # At minimum, verify both produce valid different-parameterized results
    # The exact direction depends on all component interactions
    assert v_default != v_aggressive


# ------------------------------------------------------------------
# Contested features and meeple counts
# ------------------------------------------------------------------


def test_meeple_counts():
    """_meeple_counts should separate player vs opponent counts."""
    meeples = [
        {"player_id": "p0"},
        {"player_id": "p1"},
        {"player_id": "p1"},
    ]
    my, max_opp, total_opp = _meeple_counts(meeples, PlayerId("p0"))
    assert my == 1
    assert max_opp == 2
    assert total_opp == 2


def test_meeple_counts_no_opponents():
    meeples = [{"player_id": "p0"}, {"player_id": "p0"}]
    my, max_opp, total_opp = _meeple_counts(meeples, PlayerId("p0"))
    assert my == 2
    assert max_opp == 0
    assert total_opp == 0


def test_contested_feature_penalty():
    """Features where we have meeples but don't control should lower eval."""
    plugin, state = _make_state()

    # Create a contested city feature — opponent has more meeples
    state.game_data["features"]["test_city"] = {
        "feature_type": "city",
        "is_complete": False,
        "tiles": ["0,0", "1,0", "2,0"],
        "open_edges": ["2,0_E"],
        "pennants": 0,
        "meeples": [
            {"player_id": "p0"},
            {"player_id": "p1"},
            {"player_id": "p1"},
        ],
    }

    # p0 has meeples on a feature they don't control — should lower eval
    v_contested = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )

    # Remove our wasted meeple
    state.game_data["features"]["test_city"]["meeples"] = [
        {"player_id": "p1"},
        {"player_id": "p1"},
    ]
    v_no_waste = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )

    # Having wasted meeples should produce a lower eval than not
    assert v_contested < v_no_waste


def test_meeple_scarcity_penalty():
    """0 meeples mid-game should produce lower eval."""
    plugin, state = _make_state()

    # Set up mid-game scenario with scores equal
    state.game_data["scores"]["p0"] = 20
    state.game_data["scores"]["p1"] = 20

    # With normal meeple supply
    state.game_data["meeple_supply"]["p0"] = 4
    state.game_data["meeple_supply"]["p1"] = 4
    v_normal = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )

    # With 0 meeples for p0
    state.game_data["meeple_supply"]["p0"] = 0
    v_scarce = carcassonne_eval(
        state.game_data, state.phase, PlayerId("p0"), state.players, plugin
    )

    assert v_scarce < v_normal
