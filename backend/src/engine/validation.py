from __future__ import annotations

from src.engine.models import GameConfig, Phase, Player, PlayerId
from src.engine.protocol import GamePlugin


def validate_plugin(plugin: GamePlugin) -> list[str]:
    """Run sanity checks on a plugin. Returns list of errors (empty = OK)."""
    errors: list[str] = []

    # Check required attributes
    for attr in ("game_id", "display_name", "min_players", "max_players"):
        if not hasattr(plugin, attr):
            errors.append(f"Missing attribute: {attr}")

    if errors:
        return errors  # Can't proceed without metadata

    # Test create_initial_state with min players
    try:
        players = [
            Player(
                player_id=PlayerId(f"test-{i}"),
                display_name=f"Test {i}",
                seat_index=i,
            )
            for i in range(plugin.min_players)
        ]
        config = GameConfig(random_seed=42)
        game_data, phase, events = plugin.create_initial_state(players, config)

        if not isinstance(game_data, dict):
            errors.append("create_initial_state must return dict as game_data")

        if not isinstance(phase, Phase):
            errors.append("create_initial_state must return Phase as second element")

        if not phase.auto_resolve and not phase.expected_actions:
            errors.append(
                "First phase is not auto_resolve but has no expected_actions"
            )

        # Verify get_valid_actions doesn't crash
        for p in players:
            plugin.get_valid_actions(game_data, phase, p.player_id)

        # Verify get_player_view doesn't crash
        for p in players:
            plugin.get_player_view(game_data, phase, p.player_id, players)

        # Verify determinism
        game_data2, phase2, events2 = plugin.create_initial_state(players, config)
        if game_data != game_data2:
            errors.append("create_initial_state is not deterministic with same seed")

    except Exception as e:
        errors.append(f"create_initial_state failed: {e}")

    return errors
