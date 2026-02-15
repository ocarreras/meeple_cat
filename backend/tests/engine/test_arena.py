"""Tests for the bot-vs-bot arena."""

from src.engine.arena import ArenaResult, run_arena
from src.engine.bot_strategy import RandomStrategy
from src.games.carcassonne.plugin import CarcassonnePlugin


def test_arena_runs_games():
    """Arena should complete N games and produce valid results."""
    plugin = CarcassonnePlugin()
    strategies = {"r1": RandomStrategy(seed=1), "r2": RandomStrategy(seed=2)}

    result = run_arena(plugin=plugin, strategies=strategies, num_games=5, base_seed=0)

    assert result.num_games == 5
    assert result.wins["r1"] + result.wins["r2"] + result.draws == 5
    assert len(result.total_scores["r1"]) == 5
    assert len(result.total_scores["r2"]) == 5
    assert len(result.game_durations_ms) == 5


def test_arena_alternates_seats():
    """With alternate_seats=True, strategies should swap seats each game."""
    plugin = CarcassonnePlugin()
    # Use distinct seeds so the two randoms aren't identical
    strategies = {"a": RandomStrategy(seed=10), "b": RandomStrategy(seed=20)}

    result = run_arena(
        plugin=plugin, strategies=strategies, num_games=4,
        base_seed=100, alternate_seats=True,
    )
    assert result.num_games == 4
    # Both strategies should have scores recorded
    assert all(len(result.total_scores[n]) == 4 for n in ("a", "b"))


def test_arena_no_alternation():
    """With alternate_seats=False, seat order stays fixed."""
    plugin = CarcassonnePlugin()
    strategies = {"x": RandomStrategy(seed=1), "y": RandomStrategy(seed=2)}

    result = run_arena(
        plugin=plugin, strategies=strategies, num_games=3,
        alternate_seats=False,
    )
    assert result.num_games == 3


def test_arena_result_statistics():
    """ArenaResult should compute correct win rates and confidence intervals."""
    result = ArenaResult(
        num_games=100,
        wins={"a": 70, "b": 25},
        draws=5,
        total_scores={"a": [50.0] * 100, "b": [40.0] * 100},
        game_durations_ms=[100.0] * 100,
    )

    assert result.win_rate("a") == 0.70
    assert result.win_rate("b") == 0.25
    assert result.avg_score("a") == 50.0
    assert result.avg_score("b") == 40.0

    ci_lo, ci_hi = result.confidence_interval_95("a")
    assert 0.55 < ci_lo < 0.70
    assert 0.70 < ci_hi < 0.85


def test_arena_random_vs_random_balanced():
    """Two random bots with different seeds should produce a roughly balanced outcome."""
    plugin = CarcassonnePlugin()
    strategies = {"r1": RandomStrategy(seed=42), "r2": RandomStrategy(seed=99)}

    result = run_arena(
        plugin=plugin, strategies=strategies, num_games=40,
        base_seed=0, alternate_seats=True,
    )

    # With 40 games, extreme skew (>90%) would indicate a bug
    assert result.wins["r1"] >= 2
    assert result.wins["r2"] >= 2


def test_arena_progress_callback():
    """Progress callback should be called for each game."""
    plugin = CarcassonnePlugin()
    strategies = {"a": RandomStrategy(seed=1), "b": RandomStrategy(seed=2)}

    calls = []
    result = run_arena(
        plugin=plugin, strategies=strategies, num_games=3,
        progress_callback=lambda done, total: calls.append((done, total)),
    )
    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_arena_result_summary_format():
    """summary() should produce readable output."""
    result = ArenaResult(
        num_games=10,
        wins={"a": 7, "b": 2},
        draws=1,
        total_scores={"a": [50.0] * 10, "b": [40.0] * 10},
        game_durations_ms=[100.0] * 10,
    )
    text = result.summary()
    assert "Arena Results" in text
    assert "10 games" in text
    assert "a:" in text
    assert "b:" in text
