"""Tests for plugin registry."""

from typing import ClassVar
import pytest

from src.engine.models import (
    Action,
    Event,
    GameConfig,
    Phase,
    Player,
    PlayerId,
    TransitionResult,
)
from src.engine.protocol import GamePlugin
from src.engine.registry import PluginRegistry
from src.engine.validation import validate_plugin


class MockPlugin:
    """Mock game plugin for testing."""

    game_id: ClassVar[str] = "mock-game"
    display_name: ClassVar[str] = "Mock Game"
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 4
    description: ClassVar[str] = "A mock game for testing"
    config_schema: ClassVar[dict] = {}
    disconnect_policy: ClassVar[str] = "forfeit_player"

    def create_initial_state(
        self,
        players: list[Player],
        config: GameConfig,
    ) -> tuple[dict, Phase, list[Event]]:
        """Create initial game state."""
        game_data = {"turn": 0, "deck": [1, 2, 3, 4, 5]}
        phase = Phase(
            name="play",
            expected_actions=[
                {"player_id": players[0].player_id, "action_type": "draw"}
            ],
        )
        events = [Event(event_type="game_started")]
        return game_data, phase, events

    def validate_config(self, options: dict) -> list[str]:
        """Validate game configuration."""
        return []

    def get_valid_actions(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> list[dict]:
        """Get valid actions for a player."""
        return [{"type": "draw"}, {"type": "play"}]

    def validate_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
    ) -> str | None:
        """Validate an action."""
        return None

    def apply_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        """Apply an action to the game state."""
        new_data = game_data.copy()
        new_data["turn"] = game_data.get("turn", 0) + 1
        return TransitionResult(
            game_data=new_data,
            events=[Event(event_type="action_applied")],
            next_phase=phase,
        )

    def get_player_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId | None,
        players: list[Player],
    ) -> dict:
        """Get player-specific view of the game state."""
        return {"visible_data": "test", "player_hand": [1, 2, 3]}

    def resolve_concurrent_actions(
        self,
        game_data: dict,
        phase: Phase,
        actions: dict[str, Action],
        players: list[Player],
    ) -> TransitionResult:
        """Resolve concurrent actions."""
        return TransitionResult(
            game_data=game_data,
            events=[],
            next_phase=phase,
        )

    def state_to_ai_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> dict:
        """Convert state to AI-readable format."""
        return {"ai_view": "data"}

    def parse_ai_action(
        self,
        response: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> Action:
        """Parse AI response into an action."""
        return Action(
            action_type=response.get("type", "unknown"),
            player_id=player_id,
            payload=response.get("payload", {}),
        )

    def on_player_forfeit(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> TransitionResult | None:
        """Handle player forfeit."""
        return None

    def get_spectator_summary(
        self,
        game_data: dict,
        phase: Phase,
        players: list[Player],
    ) -> dict:
        """Get spectator view of the game."""
        return {"summary": "game in progress"}


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def test_register_plugin(self):
        """Test registering a plugin."""
        registry = PluginRegistry()
        plugin = MockPlugin()

        registry.register(plugin)

        assert registry.get("mock-game") == plugin

    def test_register_duplicate_raises_error(self):
        """Test that registering duplicate game ID raises ValueError."""
        registry = PluginRegistry()
        plugin1 = MockPlugin()
        plugin2 = MockPlugin()

        registry.register(plugin1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(plugin2)

    def test_get_plugin(self):
        """Test retrieving a registered plugin."""
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)

        retrieved = registry.get("mock-game")

        assert retrieved == plugin
        assert retrieved.game_id == "mock-game"
        assert retrieved.display_name == "Mock Game"

    def test_get_nonexistent_plugin_raises_error(self):
        """Test that getting a non-existent game raises KeyError."""
        registry = PluginRegistry()

        with pytest.raises(KeyError, match="Unknown game"):
            registry.get("nonexistent-game")

    def test_list_games_empty(self):
        """Test listing games when registry is empty."""
        registry = PluginRegistry()

        games = registry.list_games()

        assert games == []

    def test_list_games(self):
        """Test listing registered games."""
        registry = PluginRegistry()
        plugin = MockPlugin()
        registry.register(plugin)

        games = registry.list_games()

        assert len(games) == 1
        assert games[0]["game_id"] == "mock-game"
        assert games[0]["display_name"] == "Mock Game"
        assert games[0]["min_players"] == 2
        assert games[0]["max_players"] == 4
        assert games[0]["description"] == "A mock game for testing"

    def test_list_multiple_games(self):
        """Test listing multiple registered games."""
        registry = PluginRegistry()

        # Create second mock plugin
        class AnotherMockPlugin(MockPlugin):
            game_id: ClassVar[str] = "another-game"
            display_name: ClassVar[str] = "Another Game"
            min_players: ClassVar[int] = 1
            max_players: ClassVar[int] = 2
            description: ClassVar[str] = "Another mock game"

        plugin1 = MockPlugin()
        plugin2 = AnotherMockPlugin()

        registry.register(plugin1)
        registry.register(plugin2)

        games = registry.list_games()

        assert len(games) == 2
        game_ids = [g["game_id"] for g in games]
        assert "mock-game" in game_ids
        assert "another-game" in game_ids

class TestValidatePlugin:
    """Tests for validate_plugin function."""

    def test_validate_valid_plugin(self):
        """Test validating a valid plugin returns no errors."""
        plugin = MockPlugin()

        errors = validate_plugin(plugin)

        assert errors == []

    def test_validate_missing_attributes(self):
        """Test validating plugin with missing attributes."""

        class InvalidPlugin:
            # Missing required attributes
            pass

        plugin = InvalidPlugin()

        errors = validate_plugin(plugin)

        assert len(errors) > 0
        assert any("Missing attribute: game_id" in e for e in errors)
        assert any("Missing attribute: display_name" in e for e in errors)
        assert any("Missing attribute: min_players" in e for e in errors)
        assert any("Missing attribute: max_players" in e for e in errors)

    def test_validate_create_initial_state_returns_wrong_types(self):
        """Test validation fails if create_initial_state returns wrong types."""

        class BadPlugin(MockPlugin):
            def create_initial_state(
                self, players: list[Player], config: GameConfig
            ) -> tuple[dict, Phase, list[Event]]:
                # Returns wrong types
                return "not a dict", "not a phase", []

        plugin = BadPlugin()

        errors = validate_plugin(plugin)

        assert len(errors) > 0
        assert any("must return dict as game_data" in e for e in errors)
        assert any("must return Phase" in e for e in errors)

    def test_validate_first_phase_no_actions_or_auto_resolve(self):
        """Test validation fails if first phase has no actions and isn't auto_resolve."""

        class BadPhasePlugin(MockPlugin):
            def create_initial_state(
                self, players: list[Player], config: GameConfig
            ) -> tuple[dict, Phase, list[Event]]:
                game_data = {"turn": 0}
                # Phase with no expected_actions and auto_resolve=False
                phase = Phase(name="bad_phase", auto_resolve=False)
                events = []
                return game_data, phase, events

        plugin = BadPhasePlugin()

        errors = validate_plugin(plugin)

        assert len(errors) > 0
        assert any("not auto_resolve but has no expected_actions" in e for e in errors)

    def test_validate_determinism(self):
        """Test validation checks deterministic behavior with same seed."""

        class NonDeterministicPlugin(MockPlugin):
            _call_count = 0

            def create_initial_state(
                self, players: list[Player], config: GameConfig
            ) -> tuple[dict, Phase, list[Event]]:
                # Return different data on each call
                self._call_count += 1
                game_data = {"turn": self._call_count}
                phase = Phase(
                    name="play",
                    expected_actions=[
                        {"player_id": players[0].player_id, "action_type": "draw"}
                    ],
                )
                events = []
                return game_data, phase, events

        plugin = NonDeterministicPlugin()

        errors = validate_plugin(plugin)

        assert len(errors) > 0
        assert any("not deterministic" in e for e in errors)

    def test_validate_create_initial_state_exception(self):
        """Test validation catches exceptions in create_initial_state."""

        class CrashingPlugin(MockPlugin):
            def create_initial_state(
                self, players: list[Player], config: GameConfig
            ) -> tuple[dict, Phase, list[Event]]:
                raise RuntimeError("Intentional crash")

        plugin = CrashingPlugin()

        errors = validate_plugin(plugin)

        assert len(errors) > 0
        assert any("create_initial_state failed" in e for e in errors)
        assert any("Intentional crash" in e for e in errors)

    def test_validate_get_valid_actions_called(self):
        """Test validation calls get_valid_actions for all players."""
        plugin = MockPlugin()

        # Track calls
        original_method = plugin.get_valid_actions
        call_count = 0

        def tracked_method(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_method(*args, **kwargs)

        plugin.get_valid_actions = tracked_method

        errors = validate_plugin(plugin)

        assert errors == []
        # Should be called for each player (min_players = 2)
        assert call_count == 2

    def test_validate_get_player_view_called(self):
        """Test validation calls get_player_view for all players."""
        plugin = MockPlugin()

        # Track calls
        original_method = plugin.get_player_view
        call_count = 0

        def tracked_method(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return original_method(*args, **kwargs)

        plugin.get_player_view = tracked_method

        errors = validate_plugin(plugin)

        assert errors == []
        # Should be called for each player (min_players = 2)
        assert call_count == 2

    def test_plugin_protocol_compliance(self):
        """Test that MockPlugin satisfies GamePlugin protocol."""
        plugin = MockPlugin()

        # This will be True if the plugin implements the protocol
        assert isinstance(plugin, GamePlugin)

    def test_validate_plugin_with_min_players(self):
        """Test validation uses min_players to create test players."""

        class ThreePlayerPlugin(MockPlugin):
            min_players: ClassVar[int] = 3

            def create_initial_state(
                self, players: list[Player], config: GameConfig
            ) -> tuple[dict, Phase, list[Event]]:
                # Verify we received min_players
                assert len(players) == 3
                return super().create_initial_state(players, config)

        plugin = ThreePlayerPlugin()

        errors = validate_plugin(plugin)

        assert errors == []
