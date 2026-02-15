"""Tests for the MCTS search engine."""

from src.engine.game_simulator import (
    SimulationState,
    apply_action_and_resolve,
)
from src.engine.mcts import MCTSNode, _action_key, mcts_search
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
