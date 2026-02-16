"""Tests for the MCTS search engine."""

from src.engine.game_simulator import (
    SimulationState,
    apply_action_and_resolve,
)
from src.engine.mcts import (
    MCTSNode,
    _action_key,
    _action_sort_key,
    _max_children,
    mcts_search,
    rave_beta,
)
from src.engine.models import Action, GameConfig, Player, PlayerId
from src.games.carcassonne.evaluator import carcassonne_eval
from src.games.carcassonne.plugin import CarcassonnePlugin


def _make_place_tile_state(seed=42):
    """Create a state at the place_tile phase."""
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId("p0"), display_name="P0", seat_index=0),
        Player(player_id=PlayerId("p1"), display_name="P1", seat_index=1),
    ]
    config = GameConfig(random_seed=seed)
    game_data, phase, _ = plugin.create_initial_state(players, config)

    state = SimulationState(
        game_data=game_data, phase=phase, players=players,
        scores={p.player_id: 0.0 for p in players},
    )
    draw = Action(action_type="draw_tile", player_id=PlayerId("p0"))
    apply_action_and_resolve(plugin, state, draw)
    return plugin, state


def test_mcts_returns_valid_action():
    """MCTS should return an action that is in the valid actions list."""
    plugin, state = _make_place_tile_state()

    valid = plugin.get_valid_actions(
        state.game_data, state.phase, PlayerId("p0")
    )

    chosen = mcts_search(
        game_data=state.game_data,
        phase=state.phase,
        player_id=PlayerId("p0"),
        plugin=plugin,
        players=state.players,
        num_simulations=50,
        time_limit_ms=500,
        num_determinizations=2,
        eval_fn=carcassonne_eval,
    )

    # Verify the chosen action matches one of the valid actions
    chosen_key = _action_key(chosen)
    valid_keys = {_action_key(a) for a in valid}
    assert chosen_key in valid_keys


def test_mcts_single_action_returns_immediately():
    """When only one valid action exists, MCTS returns it without searching."""
    plugin, state = _make_place_tile_state()

    # Place tile first
    valid = plugin.get_valid_actions(
        state.game_data, state.phase, PlayerId("p0")
    )
    place = Action(
        action_type="place_tile", player_id=PlayerId("p0"), payload=valid[0]
    )
    apply_action_and_resolve(plugin, state, place)

    # Now in place_meeple — might have only 1-2 options
    # If we get a case with skip only, MCTS should return instantly
    meeple_valid = plugin.get_valid_actions(
        state.game_data, state.phase, PlayerId("p0")
    )

    if len(meeple_valid) == 1:
        chosen = mcts_search(
            game_data=state.game_data,
            phase=state.phase,
            player_id=PlayerId("p0"),
            plugin=plugin,
            players=state.players,
            num_simulations=100,
            time_limit_ms=1000,
        )
        assert chosen == meeple_valid[0]


def test_mcts_with_default_eval():
    """MCTS should work without an explicit eval_fn (uses default)."""
    plugin, state = _make_place_tile_state()

    chosen = mcts_search(
        game_data=state.game_data,
        phase=state.phase,
        player_id=PlayerId("p0"),
        plugin=plugin,
        players=state.players,
        num_simulations=30,
        time_limit_ms=500,
        num_determinizations=1,
    )

    valid = plugin.get_valid_actions(
        state.game_data, state.phase, PlayerId("p0")
    )
    valid_keys = {_action_key(a) for a in valid}
    assert _action_key(chosen) in valid_keys


def test_mcts_mid_game():
    """Run MCTS at a mid-game position (after several turns)."""
    plugin, state = _make_place_tile_state()

    # Play a few turns to get to mid-game
    for _ in range(6):
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
        payload = valid[0] if state.phase.name != "place_meeple" else {"skip": True}
        action = Action(
            action_type=state.phase.expected_actions[0].action_type,
            player_id=acting_pid,
            payload=payload,
        )
        apply_action_and_resolve(plugin, state, action)

    if state.game_over or state.phase.auto_resolve:
        return  # Skip test if game ended early

    acting_pid = state.phase.expected_actions[0].player_id
    chosen = mcts_search(
        game_data=state.game_data,
        phase=state.phase,
        player_id=acting_pid,
        plugin=plugin,
        players=state.players,
        num_simulations=50,
        time_limit_ms=500,
        num_determinizations=2,
        eval_fn=carcassonne_eval,
    )

    valid = plugin.get_valid_actions(state.game_data, state.phase, acting_pid)
    valid_keys = {_action_key(a) for a in valid}
    assert _action_key(chosen) in valid_keys


def test_action_key_place_tile():
    key = _action_key({"x": 1, "y": -1, "rotation": 90, "meeple_spots": ["city_N"]})
    assert key == "1,-1,90"


def test_action_key_place_meeple():
    assert _action_key({"meeple_spot": "city_N"}) == "meeple:city_N"
    assert _action_key({"skip": True}) == "skip"


def test_action_key_none():
    assert _action_key(None) == ""


def test_mcts_node_uct():
    """MCTSNode UCT formula basics."""
    parent = MCTSNode(action_taken=None, parent=None)
    parent.visit_count = 100

    child_a = MCTSNode(action_taken={"x": 0}, parent=parent)
    child_a.visit_count = 50
    child_a.total_value = 30.0  # Q = 0.6

    child_b = MCTSNode(action_taken={"x": 1}, parent=parent)
    child_b.visit_count = 10
    child_b.total_value = 7.0  # Q = 0.7

    parent.children = [child_a, child_b]

    # child_b has higher Q and more exploration bonus (fewer visits)
    assert child_b.uct_value(100, 1.41) > child_a.uct_value(100, 1.41)

    # Unvisited child should have infinite UCT
    child_c = MCTSNode(action_taken={"x": 2}, parent=parent)
    assert child_c.uct_value(100, 1.41) == float("inf")


# ------------------------------------------------------------------
# Progressive widening tests
# ------------------------------------------------------------------


def test_max_children_formula():
    """_max_children should grow with visit count."""
    # pw_c=2.0, pw_alpha=0.5 → max(1, int(2 * sqrt(visits)))
    assert _max_children(1, 2.0, 0.5) == 2  # 2 * 1^0.5 = 2
    assert _max_children(4, 2.0, 0.5) == 4  # 2 * 4^0.5 = 4
    assert _max_children(16, 2.0, 0.5) == 8  # 2 * 16^0.5 = 8
    assert _max_children(100, 2.0, 0.5) == 20  # 2 * 100^0.5 = 20

    # alpha=0 means every visit allows a new child (effectively no widening)
    # pw_c * 1^0 = pw_c always
    assert _max_children(1, 2.0, 0.0) == 2
    assert _max_children(100, 2.0, 0.0) == 2  # Always 2


def test_max_children_minimum():
    """Should always allow at least 1 child."""
    assert _max_children(0, 0.1, 0.5) >= 1
    assert _max_children(1, 0.1, 0.5) >= 1


def test_action_sort_key_tile_placement():
    """Tile placements closer to origin should have lower sort key."""
    near = _action_sort_key({"x": 0, "y": 1, "rotation": 0})
    far = _action_sort_key({"x": 5, "y": 5, "rotation": 90})
    assert near < far


def test_action_sort_key_meeple_priority():
    """Meeple spots should be prioritised: city > monastery > road > field > skip."""
    city = _action_sort_key({"meeple_spot": "city_N"})
    monastery = _action_sort_key({"meeple_spot": "monastery"})
    road = _action_sort_key({"meeple_spot": "road_S"})
    field = _action_sort_key({"meeple_spot": "field_NE_NW"})
    skip = _action_sort_key({"skip": True})

    assert city < monastery < road < field < skip


def test_mcts_with_progressive_widening():
    """MCTS with progressive widening should still return a valid action."""
    plugin, state = _make_place_tile_state()

    chosen = mcts_search(
        game_data=state.game_data,
        phase=state.phase,
        player_id=PlayerId("p0"),
        plugin=plugin,
        players=state.players,
        num_simulations=50,
        time_limit_ms=500,
        num_determinizations=2,
        eval_fn=carcassonne_eval,
        pw_c=2.0,
        pw_alpha=0.5,
    )

    valid = plugin.get_valid_actions(
        state.game_data, state.phase, PlayerId("p0")
    )
    valid_keys = {_action_key(a) for a in valid}
    assert _action_key(chosen) in valid_keys


def test_mcts_no_widening():
    """MCTS with pw_alpha=0 should still work (disables widening)."""
    plugin, state = _make_place_tile_state()

    chosen = mcts_search(
        game_data=state.game_data,
        phase=state.phase,
        player_id=PlayerId("p0"),
        plugin=plugin,
        players=state.players,
        num_simulations=30,
        time_limit_ms=500,
        num_determinizations=1,
        pw_c=100.0,  # Very high → effectively no widening
        pw_alpha=0.0,
    )

    valid = plugin.get_valid_actions(
        state.game_data, state.phase, PlayerId("p0")
    )
    valid_keys = {_action_key(a) for a in valid}
    assert _action_key(chosen) in valid_keys


# ------------------------------------------------------------------
# RAVE / AMAF tests
# ------------------------------------------------------------------


def test_mcts_with_rave():
    """MCTS with RAVE enabled should return a valid action."""
    plugin, state = _make_place_tile_state()

    chosen = mcts_search(
        game_data=state.game_data,
        phase=state.phase,
        player_id=PlayerId("p0"),
        plugin=plugin,
        players=state.players,
        num_simulations=50,
        time_limit_ms=500,
        num_determinizations=2,
        eval_fn=carcassonne_eval,
        use_rave=True,
        rave_k=100.0,
    )

    valid = plugin.get_valid_actions(
        state.game_data, state.phase, PlayerId("p0")
    )
    valid_keys = {_action_key(a) for a in valid}
    assert _action_key(chosen) in valid_keys


def test_rave_value_blending():
    """β should be ~1 at low parent visits and approach 0 at high visits."""
    # β = sqrt(k / (3 * N + k))
    # At N=0: β = sqrt(300/300) = 1.0
    assert rave_beta(0, 300.0) == 1.0

    # At N=100: β = sqrt(300/600) ≈ 0.707
    beta_100 = rave_beta(100, 300.0)
    assert 0.70 < beta_100 < 0.72

    # At N=10000: β = sqrt(300/30300) ≈ 0.099
    beta_10k = rave_beta(10000, 300.0)
    assert beta_10k < 0.11

    # Higher rave_k → slower decay (trust AMAF longer)
    beta_low_k = rave_beta(100, 100.0)
    beta_high_k = rave_beta(100, 1000.0)
    assert beta_low_k < beta_high_k


def test_rave_amaf_stats_populated():
    """After MCTS+RAVE, the root node should have AMAF entries."""
    plugin, state = _make_place_tile_state()

    import copy
    root_state = SimulationState(
        game_data=copy.deepcopy(state.game_data),
        phase=state.phase.model_copy(deep=True),
        players=state.players,
        scores={p.player_id: 0.0 for p in state.players},
    )

    from src.engine.mcts import _run_one_iteration

    root = MCTSNode(action_taken=None, parent=None)
    for _ in range(20):
        _run_one_iteration(
            root, root_state, PlayerId("p0"), state.players, plugin,
            1.41, carcassonne_eval, 2.0, 0.5,
            use_rave=True, rave_k=100.0, max_amaf_depth=4,
        )

    # Root should have accumulated AMAF statistics
    assert root.visit_count == 20
    assert len(root.amaf_visits) > 0
    assert len(root.amaf_values) > 0

    for key, count in root.amaf_visits.items():
        assert count > 0
        assert key in root.amaf_values


def test_rave_disabled_by_default():
    """With use_rave=False, AMAF dicts should remain empty."""
    plugin, state = _make_place_tile_state()

    import copy
    root_state = SimulationState(
        game_data=copy.deepcopy(state.game_data),
        phase=state.phase.model_copy(deep=True),
        players=state.players,
        scores={p.player_id: 0.0 for p in state.players},
    )

    from src.engine.mcts import _run_one_iteration

    root = MCTSNode(action_taken=None, parent=None)
    for _ in range(20):
        _run_one_iteration(
            root, root_state, PlayerId("p0"), state.players, plugin,
            1.41, carcassonne_eval, 2.0, 0.5,
            use_rave=False, rave_k=100.0, max_amaf_depth=4,
        )

    assert root.visit_count == 20
    assert len(root.amaf_visits) == 0
    assert len(root.amaf_values) == 0


def test_depth_limited_amaf():
    """Depth-limited AMAF should have fewer entries than unlimited."""
    plugin, state = _make_place_tile_state()

    import copy
    from src.engine.mcts import _run_one_iteration

    # Run with depth limit = 2
    root_limited = MCTSNode(action_taken=None, parent=None)
    limited_state = SimulationState(
        game_data=copy.deepcopy(state.game_data),
        phase=state.phase.model_copy(deep=True),
        players=state.players,
        scores={p.player_id: 0.0 for p in state.players},
    )
    for _ in range(30):
        _run_one_iteration(
            root_limited, limited_state, PlayerId("p0"), state.players, plugin,
            1.41, carcassonne_eval, 2.0, 0.5,
            use_rave=True, rave_k=100.0, max_amaf_depth=2,
        )

    # Run with unlimited depth
    root_unlimited = MCTSNode(action_taken=None, parent=None)
    unlimited_state = SimulationState(
        game_data=copy.deepcopy(state.game_data),
        phase=state.phase.model_copy(deep=True),
        players=state.players,
        scores={p.player_id: 0.0 for p in state.players},
    )
    for _ in range(30):
        _run_one_iteration(
            root_unlimited, unlimited_state, PlayerId("p0"), state.players, plugin,
            1.41, carcassonne_eval, 2.0, 0.5,
            use_rave=True, rave_k=100.0, max_amaf_depth=0,
        )

    # Depth-limited root should have <= entries than unlimited
    assert len(root_limited.amaf_visits) <= len(root_unlimited.amaf_visits)
    # Both should have at least some AMAF data
    assert len(root_limited.amaf_visits) > 0
    assert len(root_unlimited.amaf_visits) > 0


def test_rave_fpu_prefers_amaf_children():
    """Unvisited children with AMAF data should get an AMAF-based score."""
    parent = MCTSNode(action_taken=None, parent=None)
    parent.visit_count = 10
    parent.amaf_visits["1,0,90"] = 5
    parent.amaf_values["1,0,90"] = 4.0  # amaf_q = 0.8

    child_with_amaf = MCTSNode(
        action_taken={"x": 1, "y": 0, "rotation": 90}, parent=parent
    )
    child_no_amaf = MCTSNode(
        action_taken={"x": 2, "y": 0, "rotation": 0}, parent=parent
    )

    # With FPU, child with AMAF gets 1.0 + amaf_q = 1.8
    val_with = child_with_amaf.rave_value(10, 1.41, 100.0, rave_fpu=True)
    assert val_with == 1.8

    # Child without AMAF still gets inf
    val_without = child_no_amaf.rave_value(10, 1.41, 100.0, rave_fpu=True)
    assert val_without == float("inf")

    # Without FPU, both get inf
    assert child_with_amaf.rave_value(10, 1.41, 100.0, rave_fpu=False) == float("inf")


def test_mcts_rave_optimized():
    """MCTS+RAVE with all optimizations returns a valid action."""
    plugin, state = _make_place_tile_state()

    chosen = mcts_search(
        game_data=state.game_data,
        phase=state.phase,
        player_id=PlayerId("p0"),
        plugin=plugin,
        players=state.players,
        num_simulations=50,
        time_limit_ms=500,
        num_determinizations=2,
        eval_fn=carcassonne_eval,
        use_rave=True,
        rave_k=100.0,
        max_amaf_depth=4,
        rave_fpu=True,
    )

    valid = plugin.get_valid_actions(
        state.game_data, state.phase, PlayerId("p0")
    )
    valid_keys = {_action_key(a) for a in valid}
    assert _action_key(chosen) in valid_keys
