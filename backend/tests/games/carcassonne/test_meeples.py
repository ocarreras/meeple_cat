"""Unit tests for Carcassonne meeple placement and return logic."""

import pytest

from src.games.carcassonne.meeples import can_place_meeple, return_meeples
from src.games.carcassonne.types import FeatureType


class TestCanPlaceMeeple:
    """Tests for meeple placement validation."""

    def test_can_place_when_feature_unclaimed_and_supply_available(self):
        """Verify can place meeple when feature unclaimed and player has meeples."""
        game_data = {
            "meeple_supply": {"player1": 5},
            "tile_feature_map": {
                "0,0": {"city_N": "feat1"}
            },
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "meeples": []  # Unclaimed
                }
            }
        }

        result = can_place_meeple(game_data, "player1", "0,0", "city_N")

        assert result is True

    def test_cannot_place_when_no_meeples_in_supply(self):
        """Verify cannot place meeple when player has no meeples left."""
        game_data = {
            "meeple_supply": {"player1": 0},  # No meeples
            "tile_feature_map": {
                "0,0": {"city_N": "feat1"}
            },
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "meeples": []
                }
            }
        }

        result = can_place_meeple(game_data, "player1", "0,0", "city_N")

        assert result is False

    def test_cannot_place_when_feature_already_claimed(self):
        """Verify cannot place meeple when feature already has meeples."""
        game_data = {
            "meeple_supply": {"player1": 5},
            "tile_feature_map": {
                "0,0": {"city_N": "feat1"}
            },
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "meeples": [  # Already claimed
                        {"player_id": "player2", "position": "0,0", "spot": "city_N"}
                    ]
                }
            }
        }

        result = can_place_meeple(game_data, "player1", "0,0", "city_N")

        assert result is False

    def test_cannot_place_when_spot_not_found(self):
        """Verify cannot place meeple on non-existent spot."""
        game_data = {
            "meeple_supply": {"player1": 5},
            "tile_feature_map": {
                "0,0": {"city_N": "feat1"}
            },
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "meeples": []
                }
            }
        }

        # Try to place on a spot that doesn't exist
        result = can_place_meeple(game_data, "player1", "0,0", "invalid_spot")

        assert result is False

    def test_cannot_place_when_position_not_found(self):
        """Verify cannot place meeple on non-existent position."""
        game_data = {
            "meeple_supply": {"player1": 5},
            "tile_feature_map": {
                "0,0": {"city_N": "feat1"}
            },
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "meeples": []
                }
            }
        }

        # Try to place on a position that doesn't exist
        result = can_place_meeple(game_data, "player1", "5,5", "city_N")

        assert result is False

    def test_cannot_place_when_feature_not_found(self):
        """Verify cannot place meeple when feature doesn't exist."""
        game_data = {
            "meeple_supply": {"player1": 5},
            "tile_feature_map": {
                "0,0": {"city_N": "nonexistent_feat"}
            },
            "features": {}  # Feature doesn't exist
        }

        result = can_place_meeple(game_data, "player1", "0,0", "city_N")

        assert result is False

    def test_can_place_on_same_feature_claimed_by_self_fails(self):
        """Verify cannot place second meeple on own claimed feature."""
        game_data = {
            "meeple_supply": {"player1": 5},
            "tile_feature_map": {
                "0,0": {"city_N": "feat1"}
            },
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "meeples": [
                        {"player_id": "player1", "position": "0,0", "spot": "city_N"}
                    ]
                }
            }
        }

        # Even though it's the same player, they can't add another meeple
        result = can_place_meeple(game_data, "player1", "0,0", "city_N")

        assert result is False


class TestReturnMeeples:
    """Tests for returning meeples from features."""

    def test_return_meeples_increments_supply(self):
        """Verify returning meeples increments player supply."""
        game_data = {
            "meeple_supply": {"player1": 5}
        }

        feature = {
            "meeples": [
                {"player_id": "player1", "position": "0,0", "spot": "city_N"}
            ]
        }

        events = return_meeples(game_data, feature)

        # Supply should be incremented
        assert game_data["meeple_supply"]["player1"] == 6

    def test_return_meeples_clears_feature_meeples(self):
        """Verify returning meeples clears the feature's meeple list."""
        game_data = {
            "meeple_supply": {"player1": 5}
        }

        feature = {
            "meeples": [
                {"player_id": "player1", "position": "0,0", "spot": "city_N"}
            ]
        }

        events = return_meeples(game_data, feature)

        # Feature should have no meeples
        assert feature["meeples"] == []

    def test_return_meeples_returns_events(self):
        """Verify return_meeples returns events for each meeple."""
        game_data = {
            "meeple_supply": {"player1": 5}
        }

        feature = {
            "meeples": [
                {"player_id": "player1", "position": "0,0", "spot": "city_N"}
            ]
        }

        events = return_meeples(game_data, feature)

        assert len(events) == 1
        assert events[0].event_type == "meeple_returned"
        assert events[0].player_id == "player1"
        assert events[0].payload["position"] == "0,0"
        assert events[0].payload["spot"] == "city_N"

    def test_return_multiple_meeples(self):
        """Verify multiple meeples are returned correctly."""
        game_data = {
            "meeple_supply": {"player1": 5, "player2": 4}
        }

        feature = {
            "meeples": [
                {"player_id": "player1", "position": "0,0", "spot": "city_N"},
                {"player_id": "player2", "position": "0,1", "spot": "city_S"}
            ]
        }

        events = return_meeples(game_data, feature)

        # Both players should get meeples back
        assert game_data["meeple_supply"]["player1"] == 6
        assert game_data["meeple_supply"]["player2"] == 5

        # Should have 2 return events
        assert len(events) == 2
        player_ids = [e.player_id for e in events]
        assert "player1" in player_ids
        assert "player2" in player_ids

    def test_return_no_meeples(self):
        """Verify returning from feature with no meeples is safe."""
        game_data = {
            "meeple_supply": {"player1": 5}
        }

        feature = {
            "meeples": []
        }

        events = return_meeples(game_data, feature)

        # Supply unchanged
        assert game_data["meeple_supply"]["player1"] == 5

        # No events
        assert events == []

    def test_return_meeples_initializes_missing_supply(self):
        """Verify return_meeples handles missing supply entry gracefully."""
        game_data = {
            "meeple_supply": {}  # Player not in supply dict
        }

        feature = {
            "meeples": [
                {"player_id": "player1", "position": "0,0", "spot": "city_N"}
            ]
        }

        events = return_meeples(game_data, feature)

        # Should create entry and set to 1
        assert game_data["meeple_supply"]["player1"] == 1

    def test_return_meeples_multiple_from_same_player(self):
        """Verify returning multiple meeples from the same player works."""
        game_data = {
            "meeple_supply": {"player1": 3}
        }

        feature = {
            "meeples": [
                {"player_id": "player1", "position": "0,0", "spot": "city_N"},
                {"player_id": "player1", "position": "0,1", "spot": "city_S"}
            ]
        }

        events = return_meeples(game_data, feature)

        # Player should get both meeples back
        assert game_data["meeple_supply"]["player1"] == 5

        # Should have 2 return events
        assert len(events) == 2
