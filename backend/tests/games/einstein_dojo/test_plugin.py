"""Tests for Ein Stein Dojo plugin — full game simulation."""

from __future__ import annotations

from src.engine.models import (
    Action,
    ConcurrentMode,
    GameConfig,
    Phase,
    Player,
)
from src.games.einstein_dojo.board import get_all_valid_placements
from src.games.einstein_dojo.plugin import EinsteinDojoPlugin, TILES_PER_PLAYER


def _make_players() -> list[Player]:
    return [
        Player(player_id="p1", display_name="Alice", seat_index=0),
        Player(player_id="p2", display_name="Bob", seat_index=1),
    ]


def _make_plugin() -> EinsteinDojoPlugin:
    return EinsteinDojoPlugin()


class TestClassAttributes:
    def test_game_id(self) -> None:
        p = _make_plugin()
        assert p.game_id == "einstein_dojo"

    def test_player_count(self) -> None:
        p = _make_plugin()
        assert p.min_players == 2
        assert p.max_players == 2

    def test_disconnect_policy(self) -> None:
        p = _make_plugin()
        assert p.disconnect_policy == "forfeit_player"


class TestCreateInitialState:
    def test_returns_tuple(self) -> None:
        p = _make_plugin()
        result = p.create_initial_state(_make_players(), GameConfig())
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_game_data_structure(self) -> None:
        p = _make_plugin()
        game_data, _, _ = p.create_initial_state(_make_players(), GameConfig())
        assert "board" in game_data
        assert "tiles_remaining" in game_data
        assert "scores" in game_data
        assert "current_player_index" in game_data

    def test_tiles_per_player(self) -> None:
        p = _make_plugin()
        game_data, _, _ = p.create_initial_state(_make_players(), GameConfig())
        assert game_data["tiles_remaining"]["p1"] == TILES_PER_PLAYER
        assert game_data["tiles_remaining"]["p2"] == TILES_PER_PLAYER

    def test_initial_scores_zero(self) -> None:
        p = _make_plugin()
        game_data, _, _ = p.create_initial_state(_make_players(), GameConfig())
        assert game_data["scores"]["p1"] == 0
        assert game_data["scores"]["p2"] == 0

    def test_first_phase_is_place_tile(self) -> None:
        p = _make_plugin()
        _, phase, _ = p.create_initial_state(_make_players(), GameConfig())
        assert phase.name == "place_tile"
        assert phase.concurrent_mode == ConcurrentMode.SEQUENTIAL
        assert not phase.auto_resolve

    def test_first_player_expected(self) -> None:
        p = _make_plugin()
        players = _make_players()
        _, phase, _ = p.create_initial_state(players, GameConfig())
        assert len(phase.expected_actions) == 1
        assert phase.expected_actions[0].player_id == "p1"
        assert phase.expected_actions[0].action_type == "place_tile"

    def test_game_started_event(self) -> None:
        p = _make_plugin()
        _, _, events = p.create_initial_state(_make_players(), GameConfig())
        assert len(events) == 1
        assert events[0].event_type == "game_started"
        assert events[0].payload["tiles_per_player"] == TILES_PER_PLAYER


class TestValidateAction:
    def test_missing_fields_rejected(self) -> None:
        p = _make_plugin()
        game_data, phase, _ = p.create_initial_state(_make_players(), GameConfig())
        action = Action(action_type="place_tile", player_id="p1", payload={})
        err = p.validate_action(game_data, phase, action)
        assert err is not None
        assert "Missing" in err

    def test_invalid_orientation_rejected(self) -> None:
        p = _make_plugin()
        game_data, phase, _ = p.create_initial_state(_make_players(), GameConfig())
        action = Action(
            action_type="place_tile",
            player_id="p1",
            payload={"anchor_q": 0, "anchor_r": 0, "orientation": "bad"},
        )
        err = p.validate_action(game_data, phase, action)
        assert err is not None

    def test_valid_first_placement(self) -> None:
        p = _make_plugin()
        game_data, phase, _ = p.create_initial_state(_make_players(), GameConfig())
        action = Action(
            action_type="place_tile",
            player_id="p1",
            payload={"anchor_q": 0, "anchor_r": 0, "orientation": 0},
        )
        err = p.validate_action(game_data, phase, action)
        assert err is None


class TestGetValidActions:
    def test_first_player_has_actions(self) -> None:
        p = _make_plugin()
        game_data, phase, _ = p.create_initial_state(_make_players(), GameConfig())
        actions = p.get_valid_actions(game_data, phase, "p1")
        assert len(actions) >= 12  # at least 12 orientations at origin

    def test_wrong_player_has_no_actions(self) -> None:
        p = _make_plugin()
        game_data, phase, _ = p.create_initial_state(_make_players(), GameConfig())
        actions = p.get_valid_actions(game_data, phase, "p2")
        assert actions == []

    def test_wrong_phase_has_no_actions(self) -> None:
        p = _make_plugin()
        game_data, _, _ = p.create_initial_state(_make_players(), GameConfig())
        other_phase = Phase(name="score_check", auto_resolve=True)
        actions = p.get_valid_actions(game_data, other_phase, "p1")
        assert actions == []


class TestApplyAction:
    def test_place_tile_decrements_tiles(self) -> None:
        p = _make_plugin()
        players = _make_players()
        game_data, phase, _ = p.create_initial_state(players, GameConfig())
        action = Action(
            action_type="place_tile",
            player_id="p1",
            payload={"anchor_q": 0, "anchor_r": 0, "orientation": 0},
        )
        result = p.apply_action(game_data, phase, action, players)
        assert result.game_data["tiles_remaining"]["p1"] == TILES_PER_PLAYER - 1

    def test_place_tile_emits_event(self) -> None:
        p = _make_plugin()
        players = _make_players()
        game_data, phase, _ = p.create_initial_state(players, GameConfig())
        action = Action(
            action_type="place_tile",
            player_id="p1",
            payload={"anchor_q": 0, "anchor_r": 0, "orientation": 0},
        )
        result = p.apply_action(game_data, phase, action, players)
        assert any(e.event_type == "tile_placed" for e in result.events)

    def test_place_tile_transitions_to_score_check(self) -> None:
        p = _make_plugin()
        players = _make_players()
        game_data, phase, _ = p.create_initial_state(players, GameConfig())
        action = Action(
            action_type="place_tile",
            player_id="p1",
            payload={"anchor_q": 0, "anchor_r": 0, "orientation": 0},
        )
        result = p.apply_action(game_data, phase, action, players)
        assert result.next_phase.name == "score_check"
        assert result.next_phase.auto_resolve is True
        assert result.game_over is None

    def test_score_check_advances_turn(self) -> None:
        p = _make_plugin()
        players = _make_players()
        game_data, phase, _ = p.create_initial_state(players, GameConfig())

        # Place tile as p1
        action = Action(
            action_type="place_tile",
            player_id="p1",
            payload={"anchor_q": 0, "anchor_r": 0, "orientation": 0},
        )
        result = p.apply_action(game_data, phase, action, players)

        # Auto-resolve score_check (engine passes a dummy action)
        score_action = Action(action_type="auto_resolve", player_id="p1", payload={})
        result2 = p.apply_action(result.game_data, result.next_phase, score_action, players)

        assert result2.next_phase.name == "place_tile"
        assert result2.next_phase.expected_actions[0].player_id == "p2"
        assert result2.game_data["current_player_index"] == 1


class TestGetPlayerView:
    def test_returns_all_data(self) -> None:
        p = _make_plugin()
        players = _make_players()
        game_data, phase, _ = p.create_initial_state(players, GameConfig())
        view = p.get_player_view(game_data, phase, "p1", players)
        assert "board" in view
        assert "tiles_remaining" in view
        assert "scores" in view
        assert "current_player_index" in view

    def test_spectator_view_same(self) -> None:
        p = _make_plugin()
        players = _make_players()
        game_data, phase, _ = p.create_initial_state(players, GameConfig())
        player_view = p.get_player_view(game_data, phase, "p1", players)
        spectator_view = p.get_player_view(game_data, phase, None, players)
        assert player_view == spectator_view


class TestAlternatingTurns:
    def _do_turn(
        self,
        plugin: EinsteinDojoPlugin,
        game_data: dict,
        phase: Phase,
        player_id: str,
        players: list[Player],
    ) -> tuple[dict, Phase]:
        """Execute one full turn: place_tile + score_check."""
        placements = get_all_valid_placements(game_data["board"], player_id)
        assert len(placements) > 0, f"No valid placements for {player_id}"
        p = placements[0]

        action = Action(
            action_type="place_tile",
            player_id=player_id,
            payload=p,
        )
        result = plugin.apply_action(game_data, phase, action, players)
        assert result.next_phase.name == "score_check"

        # Auto-resolve score_check
        score_action = Action(action_type="auto_resolve", player_id=player_id, payload={})
        result2 = plugin.apply_action(result.game_data, result.next_phase, score_action, players)

        return result2.game_data, result2.next_phase

    def test_four_turns_alternate(self) -> None:
        plugin = _make_plugin()
        players = _make_players()
        game_data, phase, _ = plugin.create_initial_state(players, GameConfig())

        # Turn 1: p1
        assert phase.expected_actions[0].player_id == "p1"
        game_data, phase = self._do_turn(plugin, game_data, phase, "p1", players)

        # Turn 2: p2
        assert phase.expected_actions[0].player_id == "p2"
        game_data, phase = self._do_turn(plugin, game_data, phase, "p2", players)

        # Turn 3: p1
        assert phase.expected_actions[0].player_id == "p1"
        game_data, phase = self._do_turn(plugin, game_data, phase, "p1", players)

        # Turn 4: p2
        assert phase.expected_actions[0].player_id == "p2"
        game_data, phase = self._do_turn(plugin, game_data, phase, "p2", players)

        assert game_data["tiles_remaining"]["p1"] == TILES_PER_PLAYER - 2
        assert game_data["tiles_remaining"]["p2"] == TILES_PER_PLAYER - 2
        assert len(game_data["board"]["placed_pieces"]) == 4


class TestFullGameSimulation:
    def test_game_ends_when_tiles_exhausted(self) -> None:
        """Simulate a full game until one player runs out of tiles."""
        plugin = _make_plugin()
        players = _make_players()
        game_data, phase, _ = plugin.create_initial_state(players, GameConfig())

        turn = 0
        max_turns = TILES_PER_PLAYER * 2 * 2 + 10  # each turn = place + score_check

        while turn < max_turns:
            if phase.name == "game_over":
                break

            if phase.name == "place_tile":
                player_id = phase.expected_actions[0].player_id
                placements = get_all_valid_placements(game_data["board"], player_id)

                if not placements:
                    # No valid placements — shouldn't happen normally, but bail
                    break

                p = placements[0]
                action = Action(
                    action_type="place_tile",
                    player_id=player_id,
                    payload=p,
                )
                result = plugin.apply_action(game_data, phase, action, players)
                game_data = result.game_data
                phase = result.next_phase

                if result.game_over is not None:
                    # Game ended
                    assert len(result.game_over.winners) >= 1
                    assert result.game_over.reason == "normal"
                    break

            elif phase.name == "score_check":
                # Auto-resolve
                score_action = Action(action_type="auto_resolve", player_id="p1", payload={})
                result = plugin.apply_action(game_data, phase, score_action, players)
                game_data = result.game_data
                phase = result.next_phase

                if result.game_over is not None:
                    assert len(result.game_over.winners) >= 1
                    break

            turn += 1
        else:
            # Should not reach max_turns
            raise AssertionError("Game did not end within expected turns")

        # Verify at least one player used all tiles
        tiles = game_data["tiles_remaining"]
        assert tiles["p1"] == 0 or tiles["p2"] == 0


class TestForfeit:
    def test_forfeit_skips_player(self) -> None:
        plugin = _make_plugin()
        players = _make_players()
        game_data, phase, _ = plugin.create_initial_state(players, GameConfig())

        result = plugin.on_player_forfeit(game_data, phase, "p1", players)
        assert result is not None
        assert result.next_phase.name == "place_tile"
        assert result.next_phase.expected_actions[0].player_id == "p2"
        assert any(e.event_type == "turn_skipped" for e in result.events)

    def test_forfeit_wrong_phase_returns_none(self) -> None:
        plugin = _make_plugin()
        players = _make_players()
        game_data, _, _ = plugin.create_initial_state(players, GameConfig())

        other_phase = Phase(name="score_check", auto_resolve=True)
        result = plugin.on_player_forfeit(game_data, other_phase, "p1", players)
        assert result is None


class TestAIInterface:
    def test_state_to_ai_view(self) -> None:
        plugin = _make_plugin()
        players = _make_players()
        game_data, phase, _ = plugin.create_initial_state(players, GameConfig())

        view = plugin.state_to_ai_view(game_data, phase, "p1", players)
        assert "board" in view
        assert "valid_actions" in view
        assert len(view["valid_actions"]) > 0

    def test_parse_ai_action(self) -> None:
        plugin = _make_plugin()
        players = _make_players()
        _, phase, _ = plugin.create_initial_state(players, GameConfig())

        response = {
            "action": {
                "payload": {"anchor_q": 0, "anchor_r": 0, "orientation": 0},
            },
        }
        action = plugin.parse_ai_action(response, phase, "p1")
        assert action.action_type == "place_tile"
        assert action.player_id == "p1"
        assert action.payload["anchor_q"] == 0


class TestSpectatorSummary:
    def test_returns_summary(self) -> None:
        plugin = _make_plugin()
        players = _make_players()
        game_data, phase, _ = plugin.create_initial_state(players, GameConfig())

        summary = plugin.get_spectator_summary(game_data, phase, players)
        assert "scores" in summary
        assert "tiles_remaining" in summary
        assert "pieces_placed" in summary
        assert summary["pieces_placed"] == 0
