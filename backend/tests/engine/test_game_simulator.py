"""Tests for the synchronous game simulator."""

from src.engine.game_simulator import (
    SimulationState,
    apply_action_and_resolve,
    clone_state,
)
from src.engine.models import Action, GameConfig, Phase, Player, PlayerId
from src.games.carcassonne.plugin import CarcassonnePlugin


def _make_initial_state(seed: int = 42, num_players: int = 2) -> tuple:
    """Create an initial Carcassonne state and advance past the first auto-resolve."""
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId(f"p{i}"), display_name=f"P{i}", seat_index=i)
        for i in range(num_players)
    ]
    config = GameConfig(random_seed=seed)
    game_data, phase, _events = plugin.create_initial_state(players, config)

    state = SimulationState(
        game_data=game_data,
        phase=phase,
        players=players,
        scores={p.player_id: 0.0 for p in players},
    )
    return plugin, state


def test_apply_action_resolves_auto_phases():
    """After resolving draw_tile (auto), we should land on place_tile."""
    plugin, state = _make_initial_state()

    # Initial phase is draw_tile (auto_resolve)
    assert state.phase.name == "draw_tile"
    assert state.phase.auto_resolve is True

    # Apply the draw_tile action — should auto-resolve into place_tile
    pid = state.players[0].player_id
    action = Action(action_type="draw_tile", player_id=pid)
    apply_action_and_resolve(plugin, state, action)

    assert state.phase.name == "place_tile"
    assert state.phase.auto_resolve is False
    assert state.game_data["current_tile"] is not None


def test_full_turn_cycle():
    """Place a tile, skip meeple — should end up at next player's place_tile."""
    plugin, state = _make_initial_state()

    # Resolve draw_tile → place_tile
    pid = state.players[0].player_id
    draw = Action(action_type="draw_tile", player_id=pid)
    apply_action_and_resolve(plugin, state, draw)
    assert state.phase.name == "place_tile"

    # Place tile
    valid = plugin.get_valid_actions(state.game_data, state.phase, pid)
    place = Action(action_type="place_tile", player_id=pid, payload=valid[0])
    apply_action_and_resolve(plugin, state, place)
    assert state.phase.name == "place_meeple"

    # Skip meeple — should auto-resolve score_check + draw_tile → place_tile for P1
    skip = Action(action_type="place_meeple", player_id=pid, payload={"skip": True})
    apply_action_and_resolve(plugin, state, skip)
    assert state.phase.name == "place_tile"
    assert state.phase.metadata["player_index"] == 1


def test_clone_state_independence():
    """Modifying cloned state must not affect the original."""
    plugin, state = _make_initial_state()

    # Resolve to place_tile
    pid = state.players[0].player_id
    draw = Action(action_type="draw_tile", player_id=pid)
    apply_action_and_resolve(plugin, state, draw)

    cloned = clone_state(state)

    # Mutate the clone
    valid = plugin.get_valid_actions(cloned.game_data, cloned.phase, pid)
    place = Action(action_type="place_tile", player_id=pid, payload=valid[0])
    apply_action_and_resolve(plugin, cloned, place)

    # Original should still be at place_tile with same tile count
    assert state.phase.name == "place_tile"
    assert len(state.game_data["board"]["tiles"]) == 1
    # Clone advanced
    assert cloned.phase.name == "place_meeple"
    assert len(cloned.game_data["board"]["tiles"]) == 2


def test_full_game_via_simulator():
    """Run a complete game using the simulator and verify it finishes."""
    plugin, state = _make_initial_state()

    # Resolve initial auto-resolve
    pid = state.players[0].player_id
    draw = Action(action_type="draw_tile", player_id=pid)
    apply_action_and_resolve(plugin, state, draw)

    max_iters = 500
    for _ in range(max_iters):
        if state.game_over is not None:
            break

        if state.phase.auto_resolve:
            pid = state.players[state.phase.metadata.get("player_index", 0)].player_id
            action = Action(action_type=state.phase.name, player_id=pid)
            apply_action_and_resolve(plugin, state, action)
            continue

        acting_pid = state.phase.expected_actions[0].player_id
        valid = plugin.get_valid_actions(state.game_data, state.phase, acting_pid)
        if not valid:
            break

        # Always pick first valid + skip meeples for speed
        payload = valid[0]
        if state.phase.name == "place_meeple":
            payload = {"skip": True}

        action = Action(
            action_type=state.phase.expected_actions[0].action_type,
            player_id=acting_pid,
            payload=payload,
        )
        apply_action_and_resolve(plugin, state, action)

    assert state.game_over is not None
    assert len(state.game_data["board"]["tiles"]) == 72
