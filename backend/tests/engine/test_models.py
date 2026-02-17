"""Tests for engine models."""

from datetime import datetime

import pytest

from src.engine.models import (
    Action,
    ConcurrentMode,
    Event,
    ExpectedAction,
    GameConfig,
    GameId,
    GameResult,
    GameState,
    GameStatus,
    MatchId,
    PersistedEvent,
    Phase,
    Player,
    PlayerId,
    PlayerView,
    TimeoutBehavior,
    TimerConfig,
    TimerMode,
    TransitionResult,
)


class TestPlayer:
    """Tests for Player model."""

    def test_create_player(self):
        player = Player(
            player_id=PlayerId("player-1"),
            display_name="Alice",
            seat_index=0,
        )
        assert player.player_id == "player-1"
        assert player.display_name == "Alice"
        assert player.seat_index == 0
        assert player.is_bot is False
        assert player.bot_id is None

    def test_create_bot_player(self):
        player = Player(
            player_id=PlayerId("bot-1"),
            display_name="BotAlice",
            seat_index=1,
            is_bot=True,
            bot_id="alpha_zero_v1",
        )
        assert player.is_bot is True
        assert player.bot_id == "alpha_zero_v1"

    def test_player_serialization(self):
        player = Player(
            player_id=PlayerId("player-1"),
            display_name="Alice",
            seat_index=0,
        )
        data = player.model_dump()
        assert data["player_id"] == "player-1"
        assert data["display_name"] == "Alice"
        assert data["seat_index"] == 0
        assert data["is_bot"] is False


class TestTimerEnums:
    """Tests for timer-related enums."""

    def test_timer_mode_values(self):
        assert TimerMode.FISCHER.value == "fischer"
        assert TimerMode.BYOYOMI.value == "byoyomi"
        assert TimerMode.SIMPLE.value == "simple"
        assert TimerMode.TOTAL.value == "total"
        assert TimerMode.NONE.value == "none"

    def test_timeout_behavior_values(self):
        assert TimeoutBehavior.LOSE_GAME.value == "lose_game"
        assert TimeoutBehavior.LOSE_TURN.value == "lose_turn"
        assert TimeoutBehavior.RANDOM_ACTION.value == "random_action"
        assert TimeoutBehavior.FORCE_PASS.value == "force_pass"


class TestTimerConfig:
    """Tests for TimerConfig model."""

    def test_timer_config_defaults(self):
        timer = TimerConfig()
        assert timer.mode == TimerMode.NONE
        assert timer.base_time_ms == 0
        assert timer.increment_ms == 0
        assert timer.periods == 1
        assert timer.period_time_ms == 0
        assert timer.timeout_behavior == TimeoutBehavior.LOSE_TURN

    def test_timer_config_fischer(self):
        timer = TimerConfig(
            mode=TimerMode.FISCHER,
            base_time_ms=300000,  # 5 minutes
            increment_ms=5000,  # 5 seconds
        )
        assert timer.mode == TimerMode.FISCHER
        assert timer.base_time_ms == 300000
        assert timer.increment_ms == 5000

    def test_timer_config_byoyomi(self):
        timer = TimerConfig(
            mode=TimerMode.BYOYOMI,
            base_time_ms=600000,  # 10 minutes
            periods=5,
            period_time_ms=30000,  # 30 seconds per period
        )
        assert timer.mode == TimerMode.BYOYOMI
        assert timer.periods == 5
        assert timer.period_time_ms == 30000

    def test_timer_config_serialization(self):
        timer = TimerConfig(
            mode=TimerMode.SIMPLE,
            base_time_ms=180000,
            timeout_behavior=TimeoutBehavior.LOSE_GAME,
        )
        data = timer.model_dump()
        assert data["mode"] == "simple"
        assert data["base_time_ms"] == 180000
        assert data["timeout_behavior"] == "lose_game"


class TestGameConfig:
    """Tests for GameConfig model."""

    def test_game_config_defaults(self):
        config = GameConfig()
        assert isinstance(config.timer, TimerConfig)
        assert config.options == {}
        assert isinstance(config.random_seed, int)

    def test_game_config_with_options(self):
        config = GameConfig(
            options={"board_size": 19, "komi": 7.5},
            random_seed=42,
        )
        assert config.options["board_size"] == 19
        assert config.options["komi"] == 7.5
        assert config.random_seed == 42

    def test_game_config_with_custom_timer(self):
        config = GameConfig(
            timer=TimerConfig(mode=TimerMode.FISCHER, base_time_ms=600000),
        )
        assert config.timer.mode == TimerMode.FISCHER
        assert config.timer.base_time_ms == 600000

    def test_game_config_serialization(self):
        config = GameConfig(
            options={"difficulty": "hard"},
            random_seed=123,
        )
        data = config.model_dump()
        assert data["options"] == {"difficulty": "hard"}
        assert data["random_seed"] == 123
        assert "timer" in data


class TestConcurrentMode:
    """Tests for ConcurrentMode enum."""

    def test_concurrent_mode_values(self):
        assert ConcurrentMode.SEQUENTIAL.value == "sequential"
        assert ConcurrentMode.COMMIT_REVEAL.value == "commit_reveal"
        assert ConcurrentMode.TIME_WINDOW.value == "time_window"


class TestExpectedAction:
    """Tests for ExpectedAction model."""

    def test_expected_action_defaults(self):
        expected = ExpectedAction(action_type="play_card")
        assert expected.player_id is None
        assert expected.action_type == "play_card"
        assert expected.constraints == {}
        assert expected.timeout_ms is None

    def test_expected_action_with_constraints(self):
        expected = ExpectedAction(
            player_id=PlayerId("player-1"),
            action_type="move",
            constraints={"from": "a1", "to": ["a2", "b1"]},
            timeout_ms=30000,
        )
        assert expected.player_id == "player-1"
        assert expected.action_type == "move"
        assert expected.constraints["from"] == "a1"
        assert expected.timeout_ms == 30000


class TestPhase:
    """Tests for Phase model."""

    def test_phase_defaults(self):
        phase = Phase(name="draw")
        assert phase.name == "draw"
        assert phase.concurrent_mode == ConcurrentMode.SEQUENTIAL
        assert phase.expected_actions == []
        assert phase.auto_resolve is False
        assert phase.metadata == {}

    def test_phase_with_expected_actions(self):
        phase = Phase(
            name="play",
            expected_actions=[
                ExpectedAction(
                    player_id=PlayerId("player-1"),
                    action_type="play_card",
                ),
            ],
        )
        assert len(phase.expected_actions) == 1
        assert phase.expected_actions[0].action_type == "play_card"

    def test_phase_concurrent_mode(self):
        phase = Phase(
            name="simultaneous_bidding",
            concurrent_mode=ConcurrentMode.COMMIT_REVEAL,
        )
        assert phase.concurrent_mode == ConcurrentMode.COMMIT_REVEAL

    def test_phase_auto_resolve(self):
        phase = Phase(name="cleanup", auto_resolve=True)
        assert phase.auto_resolve is True

    def test_phase_with_metadata(self):
        phase = Phase(
            name="combat",
            metadata={"round": 3, "attack_value": 5},
        )
        assert phase.metadata["round"] == 3
        assert phase.metadata["attack_value"] == 5

    def test_phase_serialization(self):
        phase = Phase(
            name="draw",
            concurrent_mode=ConcurrentMode.SEQUENTIAL,
            auto_resolve=False,
        )
        data = phase.model_dump()
        assert data["name"] == "draw"
        assert data["concurrent_mode"] == "sequential"
        assert data["auto_resolve"] is False


class TestAction:
    """Tests for Action model."""

    def test_action_defaults(self):
        action = Action(
            action_type="draw_card",
            player_id=PlayerId("player-1"),
        )
        assert action.action_type == "draw_card"
        assert action.player_id == "player-1"
        assert action.payload == {}
        assert action.timestamp is None

    def test_action_with_payload(self):
        action = Action(
            action_type="play_card",
            player_id=PlayerId("player-2"),
            payload={"card_id": "card-123", "position": 5},
        )
        assert action.payload["card_id"] == "card-123"
        assert action.payload["position"] == 5

    def test_action_with_timestamp(self):
        now = datetime.utcnow()
        action = Action(
            action_type="move",
            player_id=PlayerId("player-1"),
            timestamp=now,
        )
        assert action.timestamp == now

    def test_action_serialization(self):
        action = Action(
            action_type="bid",
            player_id=PlayerId("player-3"),
            payload={"amount": 100},
        )
        data = action.model_dump()
        assert data["action_type"] == "bid"
        assert data["player_id"] == "player-3"
        assert data["payload"]["amount"] == 100


class TestEvent:
    """Tests for Event model."""

    def test_event_defaults(self):
        event = Event(event_type="card_drawn")
        assert event.event_type == "card_drawn"
        assert event.player_id is None
        assert event.payload == {}

    def test_event_with_player(self):
        event = Event(
            event_type="card_played",
            player_id=PlayerId("player-1"),
            payload={"card": "ace_of_spades"},
        )
        assert event.event_type == "card_played"
        assert event.player_id == "player-1"
        assert event.payload["card"] == "ace_of_spades"

    def test_event_serialization(self):
        event = Event(
            event_type="game_started",
            payload={"num_players": 4},
        )
        data = event.model_dump()
        assert data["event_type"] == "game_started"
        assert data["payload"]["num_players"] == 4


class TestPersistedEvent:
    """Tests for PersistedEvent model."""

    def test_persisted_event(self):
        event = PersistedEvent(
            match_id=MatchId("match-123"),
            sequence_number=0,
            event_type="game_started",
        )
        assert event.match_id == "match-123"
        assert event.sequence_number == 0
        assert event.event_type == "game_started"
        assert event.player_id is None
        assert event.payload == {}
        assert event.id is None
        assert isinstance(event.timestamp, datetime)

    def test_persisted_event_with_id(self):
        event = PersistedEvent(
            id=456,
            match_id=MatchId("match-789"),
            sequence_number=5,
            event_type="card_played",
            player_id=PlayerId("player-1"),
            payload={"card": "king_of_hearts"},
        )
        assert event.id == 456
        assert event.sequence_number == 5
        assert event.player_id == "player-1"


class TestGameStatus:
    """Tests for GameStatus enum."""

    def test_game_status_values(self):
        assert GameStatus.WAITING.value == "waiting"
        assert GameStatus.ACTIVE.value == "active"
        assert GameStatus.PAUSED.value == "paused"
        assert GameStatus.FINISHED.value == "finished"
        assert GameStatus.ABANDONED.value == "abandoned"


class TestGameState:
    """Tests for GameState model."""

    def test_game_state_creation(self):
        players = [
            Player(
                player_id=PlayerId("player-1"),
                display_name="Alice",
                seat_index=0,
            ),
            Player(
                player_id=PlayerId("player-2"),
                display_name="Bob",
                seat_index=1,
            ),
        ]
        phase = Phase(name="setup")

        state = GameState(
            match_id=MatchId("match-123"),
            game_id=GameId("tic-tac-toe"),
            players=players,
            current_phase=phase,
        )

        assert state.match_id == "match-123"
        assert state.game_id == "tic-tac-toe"
        assert len(state.players) == 2
        assert state.current_phase.name == "setup"
        assert state.status == GameStatus.ACTIVE
        assert state.turn_number == 0
        assert state.action_number == 0

    def test_game_state_defaults(self):
        players = [
            Player(
                player_id=PlayerId("player-1"),
                display_name="Alice",
                seat_index=0,
            ),
        ]
        phase = Phase(name="play")

        state = GameState(
            match_id=MatchId("match-456"),
            game_id=GameId("chess"),
            players=players,
            current_phase=phase,
        )

        assert isinstance(state.config, GameConfig)
        assert state.player_timers == {}
        assert state.game_data == {}
        assert state.scores == {}
        assert state.committed_actions == {}

    def test_game_state_with_data(self):
        players = [
            Player(
                player_id=PlayerId("player-1"),
                display_name="Alice",
                seat_index=0,
            ),
        ]
        phase = Phase(name="play")

        state = GameState(
            match_id=MatchId("match-789"),
            game_id=GameId("go"),
            players=players,
            current_phase=phase,
            status=GameStatus.ACTIVE,
            turn_number=10,
            action_number=20,
            game_data={"board": [[0, 1], [1, 0]]},
            scores={"player-1": 25.5},
            player_timers={"player-1": 180000},
        )

        assert state.turn_number == 10
        assert state.action_number == 20
        assert state.game_data["board"] == [[0, 1], [1, 0]]
        assert state.scores["player-1"] == 25.5
        assert state.player_timers["player-1"] == 180000

    def test_game_state_serialization(self):
        players = [
            Player(
                player_id=PlayerId("player-1"),
                display_name="Alice",
                seat_index=0,
            ),
        ]
        phase = Phase(name="play")

        state = GameState(
            match_id=MatchId("match-123"),
            game_id=GameId("checkers"),
            players=players,
            current_phase=phase,
        )

        data = state.model_dump()
        assert data["match_id"] == "match-123"
        assert data["game_id"] == "checkers"
        assert data["status"] == "active"
        assert len(data["players"]) == 1


class TestGameResult:
    """Tests for GameResult model."""

    def test_game_result(self):
        result = GameResult(
            winners=[PlayerId("player-1")],
            final_scores={"player-1": 100, "player-2": 75},
        )
        assert len(result.winners) == 1
        assert result.winners[0] == "player-1"
        assert result.final_scores["player-1"] == 100
        assert result.final_scores["player-2"] == 75
        assert result.reason == "normal"
        assert result.details == {}

    def test_game_result_draw(self):
        result = GameResult(
            winners=[PlayerId("player-1"), PlayerId("player-2")],
            final_scores={"player-1": 50, "player-2": 50},
            reason="draw",
        )
        assert len(result.winners) == 2
        assert result.reason == "draw"

    def test_game_result_with_details(self):
        result = GameResult(
            winners=[PlayerId("player-1")],
            final_scores={"player-1": 1, "player-2": 0},
            reason="timeout",
            details={"timed_out_player": "player-2"},
        )
        assert result.reason == "timeout"
        assert result.details["timed_out_player"] == "player-2"

    def test_game_result_serialization(self):
        result = GameResult(
            winners=[PlayerId("player-1")],
            final_scores={"player-1": 10},
        )
        data = result.model_dump()
        assert data["winners"] == ["player-1"]
        assert data["final_scores"]["player-1"] == 10
        assert data["reason"] == "normal"


class TestTransitionResult:
    """Tests for TransitionResult model."""

    def test_transition_result_minimal(self):
        next_phase = Phase(name="draw")
        result = TransitionResult(
            game_data={"deck": [1, 2, 3]},
            events=[Event(event_type="phase_changed")],
            next_phase=next_phase,
        )

        assert result.game_data["deck"] == [1, 2, 3]
        assert len(result.events) == 1
        assert result.events[0].event_type == "phase_changed"
        assert result.next_phase.name == "draw"
        assert result.scores == {}
        assert result.game_over is None

    def test_transition_result_with_scores(self):
        next_phase = Phase(name="scoring")
        result = TransitionResult(
            game_data={},
            events=[],
            next_phase=next_phase,
            scores={"player-1": 50, "player-2": 45},
        )

        assert result.scores["player-1"] == 50
        assert result.scores["player-2"] == 45

    def test_transition_result_game_over(self):
        next_phase = Phase(name="end")
        game_result = GameResult(
            winners=[PlayerId("player-1")],
            final_scores={"player-1": 100, "player-2": 90},
        )

        result = TransitionResult(
            game_data={},
            events=[Event(event_type="game_ended")],
            next_phase=next_phase,
            game_over=game_result,
        )

        assert result.game_over is not None
        assert result.game_over.winners == ["player-1"]
        assert result.game_over.final_scores["player-1"] == 100

    def test_transition_result_serialization(self):
        next_phase = Phase(name="next")
        result = TransitionResult(
            game_data={"key": "value"},
            events=[Event(event_type="test")],
            next_phase=next_phase,
        )

        data = result.model_dump()
        assert data["game_data"]["key"] == "value"
        assert len(data["events"]) == 1
        assert data["next_phase"]["name"] == "next"


class TestPlayerView:
    """Tests for PlayerView model."""

    def test_player_view(self):
        players = [
            Player(
                player_id=PlayerId("player-1"),
                display_name="Alice",
                seat_index=0,
            ),
            Player(
                player_id=PlayerId("player-2"),
                display_name="Bob",
                seat_index=1,
            ),
        ]
        phase = Phase(name="play")

        view = PlayerView(
            match_id=MatchId("match-123"),
            game_id=GameId("poker"),
            players=players,
            current_phase=phase,
            status=GameStatus.ACTIVE,
            turn_number=5,
            scores={"player-1": 100, "player-2": 150},
            player_timers={"player-1": 180000, "player-2": 200000},
            game_data={"pot": 500},
        )

        assert view.match_id == "match-123"
        assert view.game_id == "poker"
        assert len(view.players) == 2
        assert view.current_phase.name == "play"
        assert view.status == GameStatus.ACTIVE
        assert view.turn_number == 5
        assert view.valid_actions == []
        assert view.viewer_id is None
        assert view.is_spectator is False

    def test_player_view_with_viewer(self):
        players = [
            Player(
                player_id=PlayerId("player-1"),
                display_name="Alice",
                seat_index=0,
            ),
        ]
        phase = Phase(name="play")

        view = PlayerView(
            match_id=MatchId("match-456"),
            game_id=GameId("chess"),
            players=players,
            current_phase=phase,
            status=GameStatus.ACTIVE,
            turn_number=1,
            scores={},
            player_timers={},
            game_data={},
            valid_actions=[{"type": "move", "from": "e2", "to": "e4"}],
            viewer_id=PlayerId("player-1"),
        )

        assert view.viewer_id == "player-1"
        assert len(view.valid_actions) == 1
        assert view.valid_actions[0]["type"] == "move"

    def test_player_view_spectator(self):
        players = [
            Player(
                player_id=PlayerId("player-1"),
                display_name="Alice",
                seat_index=0,
            ),
        ]
        phase = Phase(name="play")

        view = PlayerView(
            match_id=MatchId("match-789"),
            game_id=GameId("go"),
            players=players,
            current_phase=phase,
            status=GameStatus.ACTIVE,
            turn_number=10,
            scores={},
            player_timers={},
            game_data={},
            viewer_id=PlayerId("spectator-1"),
            is_spectator=True,
        )

        assert view.is_spectator is True
        assert view.viewer_id == "spectator-1"

    def test_player_view_serialization(self):
        players = [
            Player(
                player_id=PlayerId("player-1"),
                display_name="Alice",
                seat_index=0,
            ),
        ]
        phase = Phase(name="play")

        view = PlayerView(
            match_id=MatchId("match-123"),
            game_id=GameId("test"),
            players=players,
            current_phase=phase,
            status=GameStatus.ACTIVE,
            turn_number=1,
            scores={},
            player_timers={},
            game_data={},
        )

        data = view.model_dump()
        assert data["match_id"] == "match-123"
        assert data["game_id"] == "test"
        assert data["status"] == "active"
        assert data["is_spectator"] is False
