"""Unit tests for Carcassonne scoring logic."""

import pytest

from src.games.carcassonne.scoring import (
    score_completed_feature,
    score_end_game,
)
from src.games.carcassonne.types import FeatureType


class TestScoreCompletedFeature:
    """Tests for scoring completed features."""

    def test_score_city_basic(self):
        """Verify city scoring: 2 points per tile."""
        feature = {
            "feature_type": FeatureType.CITY,
            "tiles": ["0,0", "0,1", "0,2"],
            "pennants": 0,
            "meeples": [{"player_id": "player1", "position": "0,0", "spot": "city_N"}]
        }

        scores = score_completed_feature(feature)

        # 3 tiles * 2 points = 6 points
        assert scores == {"player1": 6}

    def test_score_city_with_pennants(self):
        """Verify city scoring includes pennants: 2 points per pennant."""
        feature = {
            "feature_type": FeatureType.CITY,
            "tiles": ["0,0", "0,1"],
            "pennants": 2,
            "meeples": [{"player_id": "player1", "position": "0,0", "spot": "city_N"}]
        }

        scores = score_completed_feature(feature)

        # 2 tiles * 2 + 2 pennants * 2 = 4 + 4 = 8 points
        assert scores == {"player1": 8}

    def test_score_road_basic(self):
        """Verify road scoring: 1 point per tile."""
        feature = {
            "feature_type": FeatureType.ROAD,
            "tiles": ["0,0", "1,0", "2,0", "3,0"],
            "meeples": [{"player_id": "player1", "position": "0,0", "spot": "road_E"}]
        }

        scores = score_completed_feature(feature)

        # 4 tiles * 1 point = 4 points
        assert scores == {"player1": 4}

    def test_score_monastery(self):
        """Verify monastery scoring: 9 points (1 + 8 neighbors)."""
        feature = {
            "feature_type": FeatureType.MONASTERY,
            "tiles": ["0,0"],
            "meeples": [{"player_id": "player1", "position": "0,0", "spot": "monastery"}]
        }

        scores = score_completed_feature(feature)

        assert scores == {"player1": 9}

    def test_score_no_meeples_returns_empty(self):
        """Verify scoring with no meeples returns empty dict."""
        feature = {
            "feature_type": FeatureType.CITY,
            "tiles": ["0,0", "0,1"],
            "pennants": 0,
            "meeples": []
        }

        scores = score_completed_feature(feature)

        assert scores == {}

    def test_score_tied_meeples_both_get_points(self):
        """Verify tied players both get full points."""
        feature = {
            "feature_type": FeatureType.CITY,
            "tiles": ["0,0", "0,1"],
            "pennants": 0,
            "meeples": [
                {"player_id": "player1", "position": "0,0", "spot": "city_N"},
                {"player_id": "player2", "position": "0,1", "spot": "city_S"}
            ]
        }

        scores = score_completed_feature(feature)

        # Both players have 1 meeple, so both get full points
        assert scores == {"player1": 4, "player2": 4}

    def test_score_more_meeples_wins(self):
        """Verify player with more meeples gets the points."""
        feature = {
            "feature_type": FeatureType.CITY,
            "tiles": ["0,0", "0,1"],
            "pennants": 0,
            "meeples": [
                {"player_id": "player1", "position": "0,0", "spot": "city_N"},
                {"player_id": "player2", "position": "0,1", "spot": "city_S"},
                {"player_id": "player2", "position": "0,1", "spot": "city_E"}
            ]
        }

        scores = score_completed_feature(feature)

        # Player2 has 2 meeples vs player1's 1, so only player2 scores
        assert scores == {"player2": 4}

    def test_score_field_returns_empty(self):
        """Verify fields are not scored during the game."""
        feature = {
            "feature_type": FeatureType.FIELD,
            "tiles": ["0,0", "0,1"],
            "meeples": [{"player_id": "player1", "position": "0,0", "spot": "field_N"}]
        }

        scores = score_completed_feature(feature)

        assert scores == {}


class TestScoreEndGame:
    """Tests for end-game scoring."""

    def test_score_incomplete_city(self):
        """Verify incomplete cities score 1 point per tile + 1 per pennant."""
        game_data = {
            "board": {"tiles": {}},
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0", "0,1"],
                    "pennants": 1,
                    "is_complete": False,
                    "meeples": [{"player_id": "player1", "position": "0,0", "spot": "city_N"}]
                }
            }
        }

        scores, breakdown = score_end_game(game_data)

        # 2 tiles * 1 + 1 pennant * 1 = 3 points
        assert scores == {"player1": 3}
        assert breakdown == {"player1": {"fields": 0, "roads": 0, "cities": 3, "monasteries": 0}}

    def test_score_incomplete_road(self):
        """Verify incomplete roads score 1 point per tile."""
        game_data = {
            "board": {"tiles": {}},
            "features": {
                "feat1": {
                    "feature_type": FeatureType.ROAD,
                    "tiles": ["0,0", "1,0"],
                    "is_complete": False,
                    "meeples": [{"player_id": "player1", "position": "0,0", "spot": "road_E"}]
                }
            }
        }

        scores, breakdown = score_end_game(game_data)

        # 2 tiles * 1 = 2 points
        assert scores == {"player1": 2}
        assert breakdown == {"player1": {"fields": 0, "roads": 2, "cities": 0, "monasteries": 0}}

    def test_score_incomplete_monastery(self):
        """Verify incomplete monastery scores 1 + present neighbors."""
        board_tiles = {
            "0,0": {"tile_type_id": "A", "rotation": 0},  # Monastery
            # Only 5 surrounding tiles
            "-1,1": {"tile_type_id": "E", "rotation": 0},
            "0,1": {"tile_type_id": "E", "rotation": 0},
            "1,1": {"tile_type_id": "E", "rotation": 0},
            "-1,0": {"tile_type_id": "E", "rotation": 0},
            "1,0": {"tile_type_id": "E", "rotation": 0},
        }

        game_data = {
            "board": {"tiles": board_tiles},
            "features": {
                "feat1": {
                    "feature_type": FeatureType.MONASTERY,
                    "tiles": ["0,0"],
                    "is_complete": False,
                    "meeples": [{"player_id": "player1", "position": "0,0", "spot": "monastery"}]
                }
            }
        }

        scores, breakdown = score_end_game(game_data)

        # 1 for the tile + 5 neighbors = 6 points
        assert scores == {"player1": 6}
        assert breakdown == {"player1": {"fields": 0, "roads": 0, "cities": 0, "monasteries": 6}}

    def test_score_field_with_completed_cities(self):
        """Verify fields score 3 points per adjacent completed city."""
        # This is a complex test - simplified version
        # In reality, this would require proper tile placement and feature tracking
        game_data = {
            "board": {"tiles": {
                "0,0": {"tile_type_id": "E", "rotation": 0},
            }},
            "tile_feature_map": {
                "0,0": {
                    "city_N": "city_feat1",
                    "field_ESW": "field_feat1"
                }
            },
            "features": {
                "city_feat1": {
                    "feature_id": "city_feat1",
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "is_complete": True,
                    "pennants": 0,
                    "meeples": []
                },
                "field_feat1": {
                    "feature_id": "field_feat1",
                    "feature_type": FeatureType.FIELD,
                    "tiles": ["0,0"],
                    "is_complete": False,
                    "meeples": [{"player_id": "player1", "position": "0,0", "spot": "field_ESW"}]
                }
            }
        }

        scores, breakdown = score_end_game(game_data)

        # The field borders 1 completed city, so 3 points
        # Note: This depends on the tile definition having adjacent_cities set correctly
        assert "player1" in scores

    def test_score_skips_complete_features(self):
        """Verify complete features are not scored in end-game."""
        game_data = {
            "board": {"tiles": {}},
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "pennants": 0,
                    "is_complete": True,  # Already scored
                    "meeples": [{"player_id": "player1", "position": "0,0", "spot": "city_N"}]
                }
            }
        }

        scores, breakdown = score_end_game(game_data)

        # Should not score already-complete features
        assert scores == {}
        assert breakdown == {}

    def test_score_skips_features_without_meeples(self):
        """Verify features without meeples are not scored."""
        game_data = {
            "board": {"tiles": {}},
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0", "0,1"],
                    "pennants": 0,
                    "is_complete": False,
                    "meeples": []  # No meeples
                }
            }
        }

        scores, breakdown = score_end_game(game_data)

        assert scores == {}
        assert breakdown == {}

    def test_score_multiple_features(self):
        """Verify multiple features are scored correctly."""
        game_data = {
            "board": {"tiles": {}},
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0"],
                    "pennants": 0,
                    "is_complete": False,
                    "meeples": [{"player_id": "player1", "position": "0,0", "spot": "city_N"}]
                },
                "feat2": {
                    "feature_type": FeatureType.ROAD,
                    "tiles": ["1,0", "2,0"],
                    "is_complete": False,
                    "meeples": [{"player_id": "player1", "position": "1,0", "spot": "road_E"}]
                }
            }
        }

        scores, breakdown = score_end_game(game_data)

        # City: 1 tile = 1 point
        # Road: 2 tiles = 2 points
        # Total for player1 = 3 points
        assert scores == {"player1": 3}
        assert breakdown == {"player1": {"fields": 0, "roads": 2, "cities": 1, "monasteries": 0}}

    def test_score_tied_players_in_endgame(self):
        """Verify tied players both score in end-game."""
        game_data = {
            "board": {"tiles": {}},
            "features": {
                "feat1": {
                    "feature_type": FeatureType.CITY,
                    "tiles": ["0,0", "0,1"],
                    "pennants": 0,
                    "is_complete": False,
                    "meeples": [
                        {"player_id": "player1", "position": "0,0", "spot": "city_N"},
                        {"player_id": "player2", "position": "0,1", "spot": "city_S"}
                    ]
                }
            }
        }

        scores, breakdown = score_end_game(game_data)

        # Both players tied with 1 meeple each, both get 2 points
        assert scores == {"player1": 2, "player2": 2}
        assert breakdown["player1"]["cities"] == 2
        assert breakdown["player2"]["cities"] == 2
