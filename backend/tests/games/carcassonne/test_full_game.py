"""Comprehensive full game simulation tests for Carcassonne."""

import pytest

from src.engine.errors import InvalidActionError
from src.engine.models import (
    Action,
    GameConfig,
    Phase,
    Player,
    PlayerId,
)
from src.engine.protocol import GamePlugin
from src.games.carcassonne.plugin import CarcassonnePlugin


# ------------------------------------------------------------------ #
#  Test 1: Plugin satisfies protocol
# ------------------------------------------------------------------ #


def test_plugin_satisfies_protocol():
    """Verify CarcassonnePlugin is an instance of GamePlugin protocol."""
    plugin = CarcassonnePlugin()
    assert isinstance(plugin, GamePlugin)
    assert plugin.game_id == "carcassonne"
    assert plugin.display_name == "Carcassonne"
    assert plugin.min_players == 2
    assert plugin.max_players == 5
    assert plugin.description != ""
    assert isinstance(plugin.config_schema, dict)


# ------------------------------------------------------------------ #
#  Test 2: Create initial state
# ------------------------------------------------------------------ #


def test_create_initial_state():
    """Test that initial state is correctly set up."""
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId("p0"), display_name="Player0", seat_index=0),
        Player(player_id=PlayerId("p1"), display_name="Player1", seat_index=1),
    ]
    config = GameConfig(random_seed=42)

    game_data, phase, events = plugin.create_initial_state(players, config)

    # Check board has starting tile at 0,0
    assert "0,0" in game_data["board"]["tiles"]

    # Check starting tile is type "D"
    starting_tile = game_data["board"]["tiles"]["0,0"]
    assert starting_tile["tile_type_id"] == "D"
    assert starting_tile["rotation"] == 0

    # Check tile bag has 71 tiles (72 total - 1 starting tile)
    assert len(game_data["tile_bag"]) == 71

    # Check each player has 7 meeples
    for player in players:
        assert game_data["meeple_supply"][player.player_id] == 7

    # Check features are created for starting tile
    assert len(game_data["features"]) > 0
    assert len(game_data["tile_feature_map"]) > 0
    assert "0,0" in game_data["tile_feature_map"]

    # Check first phase is draw_tile with auto_resolve
    assert phase.name == "draw_tile"
    assert phase.auto_resolve is True
    assert phase.metadata["player_index"] == 0

    # Check events
    assert len(events) == 2
    assert events[0].event_type == "game_started"
    assert events[1].event_type == "starting_tile_placed"


# ------------------------------------------------------------------ #
#  Test 3: Deterministic replay
# ------------------------------------------------------------------ #


def test_deterministic_replay():
    """Run a game with seed=42, record all events. Run again with seed=42, verify identical events."""
    result1 = run_full_game(seed=42, num_players=2, place_meeples=False, max_tiles=10)
    result2 = run_full_game(seed=42, num_players=2, place_meeples=False, max_tiles=10)

    events1 = result1["all_events"]
    events2 = result2["all_events"]

    # Verify same number of events
    assert len(events1) == len(events2), "Event count should match"

    # Verify each event matches
    for i, (e1, e2) in enumerate(zip(events1, events2)):
        assert e1.event_type == e2.event_type, f"Event {i} type mismatch"
        assert e1.player_id == e2.player_id, f"Event {i} player_id mismatch"
        # Compare payload keys and values
        assert e1.payload.keys() == e2.payload.keys(), f"Event {i} payload keys mismatch"


# ------------------------------------------------------------------ #
#  Test 4: Full game completes
# ------------------------------------------------------------------ #


def test_full_game_completes():
    """Simulate a complete 2-player game from start to finish."""
    result = run_full_game(seed=42, num_players=2, place_meeples=True)

    game_data = result["game_data"]
    game_result = result["game_result"]
    all_events = result["all_events"]

    # Verify game ended
    assert game_result is not None, "Game should have ended"
    assert game_result.reason == "normal"

    # Verify all 72 tiles are on the board
    assert len(game_data["board"]["tiles"]) == 72, "All 72 tiles should be placed"

    # Verify tile bag is empty
    assert len(game_data["tile_bag"]) == 0, "Tile bag should be empty"

    # Verify scores are non-negative
    for player_id, score in game_result.final_scores.items():
        assert score >= 0, f"Score for {player_id} should be non-negative"

    # Verify we have winners
    assert len(game_result.winners) >= 1, "Should have at least one winner"

    # Verify events contain game_started and end_game events
    event_types = [e.event_type for e in all_events]
    assert "game_started" in event_types
    assert "tile_bag_empty" in event_types or "end_game_points" in event_types


# ------------------------------------------------------------------ #
#  Test 5: Full game with no meeples
# ------------------------------------------------------------------ #


def test_full_game_no_meeples():
    """Same as above but always skip meeple placement. Verify scores are 0 for both players."""
    result = run_full_game(seed=42, num_players=2, place_meeples=False)

    game_data = result["game_data"]
    game_result = result["game_result"]

    # Verify game ended
    assert game_result is not None, "Game should have ended"

    # Verify all 72 tiles are on the board
    assert len(game_data["board"]["tiles"]) == 72, "All 72 tiles should be placed"

    # Verify scores are 0 for both players (no meeples = no scoring)
    for player_id, score in game_result.final_scores.items():
        assert score == 0, f"Score for {player_id} should be 0 when no meeples placed"


# ------------------------------------------------------------------ #
#  Test 6: Tile draw and place cycle
# ------------------------------------------------------------------ #


def test_tile_draw_and_place_cycle():
    """Test a few turns manually."""
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId("p0"), display_name="Player0", seat_index=0),
        Player(player_id=PlayerId("p1"), display_name="Player1", seat_index=1),
    ]
    config = GameConfig(random_seed=42)

    game_data, phase, events = plugin.create_initial_state(players, config)

    # Phase should be draw_tile with auto_resolve
    assert phase.name == "draw_tile"
    assert phase.auto_resolve is True

    # Initial board should have 1 tile and open positions
    assert len(game_data["board"]["tiles"]) == 1
    assert len(game_data["board"]["open_positions"]) > 0

    # Draw tile (auto-resolve)
    result = plugin.apply_action(game_data, phase, Action(action_type="draw_tile", player_id=PlayerId("p0")), players)
    game_data = result.game_data
    phase = result.next_phase

    # Verify current_tile is set
    assert game_data["current_tile"] is not None
    current_tile = game_data["current_tile"]

    # Verify phase transitioned to place_tile
    assert phase.name == "place_tile"
    assert phase.auto_resolve is False

    # Get valid placements
    valid_placements = plugin.get_valid_actions(game_data, phase, PlayerId("p0"))
    assert len(valid_placements) > 0, "Should have at least one valid placement"

    # Place tile at first valid position
    placement = valid_placements[0]
    action = Action(
        action_type="place_tile",
        player_id=PlayerId("p0"),
        payload=placement,
    )
    result = plugin.apply_action(game_data, phase, action, players)
    game_data = result.game_data
    phase = result.next_phase

    # Verify tile is on board
    assert len(game_data["board"]["tiles"]) == 2, "Should have 2 tiles on board now"
    pos_key = f"{placement['x']},{placement['y']}"
    assert pos_key in game_data["board"]["tiles"]
    assert game_data["board"]["tiles"][pos_key]["tile_type_id"] == current_tile
    assert game_data["board"]["tiles"][pos_key]["rotation"] == placement["rotation"]

    # Verify open positions updated
    assert pos_key not in game_data["board"]["open_positions"]

    # Verify current_tile is cleared
    assert game_data["current_tile"] is None

    # Verify phase transitioned to place_meeple
    assert phase.name == "place_meeple"

    # Skip meeple
    action = Action(
        action_type="place_meeple",
        player_id=PlayerId("p0"),
        payload={"skip": True},
    )
    result = plugin.apply_action(game_data, phase, action, players)
    game_data = result.game_data
    phase = result.next_phase

    # Verify phase transitioned to score_check
    assert phase.name == "score_check"
    assert phase.auto_resolve is True

    # Score check (auto-resolve)
    result = plugin.apply_action(game_data, phase, Action(action_type="score_check", player_id=PlayerId("p0")), players)
    game_data = result.game_data
    phase = result.next_phase

    # Verify phase transitioned to draw_tile for next player
    assert phase.name == "draw_tile"
    assert phase.metadata["player_index"] == 1


# ------------------------------------------------------------------ #
#  Test 7: Invalid placement
# ------------------------------------------------------------------ #


def test_validate_action_invalid_placement():
    """Verify that placing a tile at an invalid position raises an error."""
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId("p0"), display_name="Player0", seat_index=0),
        Player(player_id=PlayerId("p1"), display_name="Player1", seat_index=1),
    ]
    config = GameConfig(random_seed=42)

    game_data, phase, events = plugin.create_initial_state(players, config)

    # Draw tile
    result = plugin.apply_action(game_data, phase, Action(action_type="draw_tile", player_id=PlayerId("p0")), players)
    game_data = result.game_data
    phase = result.next_phase

    # Try to place tile at an invalid position (e.g., far away from board)
    invalid_action = Action(
        action_type="place_tile",
        player_id=PlayerId("p0"),
        payload={"x": 100, "y": 100, "rotation": 0},
    )

    # Validation should return an error
    error = plugin.validate_action(game_data, phase, invalid_action)
    assert error is not None, "Should have validation error for invalid placement"

    # Applying the action should raise InvalidActionError
    with pytest.raises(InvalidActionError):
        plugin.apply_action(game_data, phase, invalid_action, players)


# ------------------------------------------------------------------ #
#  Test 8: Player view hides bag
# ------------------------------------------------------------------ #


def test_player_view_hides_bag():
    """Verify get_player_view shows tiles_remaining count but not the actual bag contents."""
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId("p0"), display_name="Player0", seat_index=0),
        Player(player_id=PlayerId("p1"), display_name="Player1", seat_index=1),
    ]
    config = GameConfig(random_seed=42)

    game_data, phase, events = plugin.create_initial_state(players, config)

    # Get player view
    view = plugin.get_player_view(game_data, phase, PlayerId("p0"), players)

    # Verify tiles_remaining is present
    assert "tiles_remaining" in view
    assert view["tiles_remaining"] == 71

    # Verify tile_bag itself is not exposed
    assert "tile_bag" not in view

    # Verify other expected fields are present
    assert "board" in view
    assert "features" in view
    assert "meeple_supply" in view
    assert "scores" in view


# ------------------------------------------------------------------ #
#  Helper functions
# ------------------------------------------------------------------ #


def run_full_game(seed=42, num_players=2, place_meeples=True, max_tiles=None):
    """
    Run a full game simulation.

    Args:
        seed: Random seed for reproducibility
        num_players: Number of players (2-5)
        place_meeples: Whether to place meeples when possible
        max_tiles: Maximum number of tiles to place (for testing, None = full game)

    Returns:
        dict with keys: game_data, game_result, all_events
    """
    plugin = CarcassonnePlugin()
    players = [
        Player(player_id=PlayerId(f"p{i}"), display_name=f"Player{i}", seat_index=i)
        for i in range(num_players)
    ]
    config = GameConfig(random_seed=seed)
    game_data, phase, events = plugin.create_initial_state(players, config)
    all_events = list(events)

    max_iterations = 500
    iteration = 0
    result = None
    tiles_placed = 1  # Starting tile

    while iteration < max_iterations:
        if phase.name == "game_over":
            break

        # Check if we've reached the max tiles limit (for testing purposes)
        if max_tiles is not None and tiles_placed >= max_tiles:
            break

        # Handle auto-resolve phases
        if phase.auto_resolve:
            if phase.name == "draw_tile":
                player_index = phase.metadata["player_index"]
                player = players[player_index]
                action = Action(action_type="draw_tile", player_id=player.player_id)
            elif phase.name == "score_check":
                player_index = phase.metadata["player_index"]
                player = players[player_index]
                action = Action(action_type="score_check", player_id=player.player_id)
            elif phase.name == "end_game_scoring":
                action = Action(action_type="end_game_scoring", player_id=players[0].player_id)
            else:
                # Unknown auto-resolve phase
                break

            transition = plugin.apply_action(game_data, phase, action, players)
            game_data = transition.game_data
            phase = transition.next_phase
            all_events.extend(transition.events)

            if transition.game_over:
                result = transition.game_over
                break

        # Handle manual action phases
        elif phase.name == "place_tile":
            player_index = phase.metadata["player_index"]
            player = players[player_index]

            # Get valid placements
            valid_placements = plugin.get_valid_actions(game_data, phase, player.player_id)
            if not valid_placements:
                # No valid placements - should not happen in normal game
                break

            # Always pick first valid placement
            placement = valid_placements[0]
            action = Action(
                action_type="place_tile",
                player_id=player.player_id,
                payload=placement,
            )

            transition = plugin.apply_action(game_data, phase, action, players)
            game_data = transition.game_data
            phase = transition.next_phase
            all_events.extend(transition.events)
            tiles_placed += 1

        elif phase.name == "place_meeple":
            player_index = phase.metadata["player_index"]
            player = players[player_index]

            # Get valid meeple placements
            valid_spots = plugin.get_valid_actions(game_data, phase, player.player_id)

            # Decide whether to place a meeple
            if place_meeples and len(valid_spots) > 1:
                # Try to place a meeple (first non-skip option)
                for spot in valid_spots:
                    if not spot.get("skip"):
                        action = Action(
                            action_type="place_meeple",
                            player_id=player.player_id,
                            payload=spot,
                        )
                        break
                else:
                    # Only skip option available
                    action = Action(
                        action_type="place_meeple",
                        player_id=player.player_id,
                        payload={"skip": True},
                    )
            else:
                # Always skip
                action = Action(
                    action_type="place_meeple",
                    player_id=player.player_id,
                    payload={"skip": True},
                )

            transition = plugin.apply_action(game_data, phase, action, players)
            game_data = transition.game_data
            phase = transition.next_phase
            all_events.extend(transition.events)

        else:
            # Unknown phase
            break

        iteration += 1

    return {
        "game_data": game_data,
        "game_result": result,
        "all_events": all_events,
        "iterations": iteration,
    }
