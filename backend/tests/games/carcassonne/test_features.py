"""Unit tests for Carcassonne feature tracking and merging."""

import pytest

from src.games.carcassonne.features import (
    initialize_features_from_tile,
    create_and_merge_features,
    is_feature_complete,
    check_monastery_completion,
)
from src.games.carcassonne.types import FeatureType, Position


class TestInitializeFeaturesFromTile:
    """Tests for initializing features from the starting tile."""

    def test_initialize_starting_tile_d(self):
        """Verify starting tile D creates correct features."""
        features, tile_feature_map = initialize_features_from_tile("D", "0,0", 0)

        # Tile D has: 1 city, 1 road, 2 fields
        assert len(features) == 4

        # Check feature types
        feature_types = [f["feature_type"] for f in features.values()]
        assert feature_types.count(FeatureType.CITY) == 1
        assert feature_types.count(FeatureType.ROAD) == 1
        assert feature_types.count(FeatureType.FIELD) == 2

    def test_initialize_creates_open_edges(self):
        """Verify initialization creates open edges for features."""
        features, tile_feature_map = initialize_features_from_tile("D", "0,0", 0)

        # Find the city feature (touches N edge)
        city_features = [f for f in features.values() if f["feature_type"] == FeatureType.CITY]
        assert len(city_features) == 1
        city_feature = city_features[0]

        # Should have one open edge at N
        assert len(city_feature["open_edges"]) == 1
        assert city_feature["open_edges"][0] == ["0,0", "N"]

    def test_initialize_creates_tile_feature_map(self):
        """Verify tile_feature_map is created correctly."""
        features, tile_feature_map = initialize_features_from_tile("D", "0,0", 0)

        assert "0,0" in tile_feature_map
        # Tile D has meeple spots: city_N, road_EW, field_N, field_S
        assert "city_N" in tile_feature_map["0,0"]
        assert "road_EW" in tile_feature_map["0,0"]
        assert "field_N" in tile_feature_map["0,0"]
        assert "field_S" in tile_feature_map["0,0"]

    def test_initialize_counts_pennants(self):
        """Verify pennants are counted correctly."""
        # Tile C has a pennant
        features, _ = initialize_features_from_tile("C", "0,0", 0)

        city_features = [f for f in features.values() if f["feature_type"] == FeatureType.CITY]
        assert len(city_features) == 1
        assert city_features[0]["pennants"] == 1

    def test_initialize_no_pennant(self):
        """Verify tiles without pennants have pennants=0."""
        # Tile E has no pennant
        features, _ = initialize_features_from_tile("E", "0,0", 0)

        city_features = [f for f in features.values() if f["feature_type"] == FeatureType.CITY]
        assert len(city_features) == 1
        assert city_features[0]["pennants"] == 0

    def test_initialize_with_rotation(self):
        """Verify initialization respects rotation."""
        # Tile D rotated 90: City on E instead of N
        features, tile_feature_map = initialize_features_from_tile("D", "0,0", 90)

        # Find the city feature
        city_features = [f for f in features.values() if f["feature_type"] == FeatureType.CITY]
        city_feature = city_features[0]

        # Should have open edge at E
        assert city_feature["open_edges"][0] == ["0,0", "E"]


class TestCreateAndMergeFeatures:
    """Tests for creating and merging features when placing tiles."""

    def test_create_features_for_new_tile(self):
        """Verify features are created for a newly placed tile."""
        game_data = {
            "features": {},
            "tile_feature_map": {},
            "board": {
                "tiles": {
                    "0,0": {"tile_type_id": "D", "rotation": 0}
                }
            }
        }

        # Initialize the starting tile first
        features, tile_feature_map = initialize_features_from_tile("D", "0,0", 0)
        game_data["features"] = features
        game_data["tile_feature_map"] = tile_feature_map

        # Place tile E at 0,1 (north of starting tile)
        # E rotated 180 has City on S which matches D's City on N
        events = create_and_merge_features(game_data, "E", "0,1", 180)

        # Should have created features for tile E
        assert "0,1" in game_data["tile_feature_map"]

    def test_merge_matching_city_features(self):
        """Verify city features merge when tiles connect."""
        game_data = {
            "features": {},
            "tile_feature_map": {},
            "board": {
                "tiles": {
                    "0,0": {"tile_type_id": "D", "rotation": 0}
                }
            }
        }

        features, tile_feature_map = initialize_features_from_tile("D", "0,0", 0)
        game_data["features"] = features
        game_data["tile_feature_map"] = tile_feature_map

        initial_feature_count = len(game_data["features"])

        # Add the new tile to board before merging
        game_data["board"]["tiles"]["0,1"] = {"tile_type_id": "E", "rotation": 180}

        # Place tile E at 0,1 with rotation 180 (City on S)
        events = create_and_merge_features(game_data, "E", "0,1", 180)

        # Should have merge event
        merge_events = [e for e in events if e.event_type == "feature_merged"]
        assert len(merge_events) >= 1
        assert merge_events[0].payload["feature_type"] == FeatureType.CITY

    def test_merge_combines_tiles(self):
        """Verify merging combines tile lists."""
        game_data = {
            "features": {},
            "tile_feature_map": {},
            "board": {
                "tiles": {
                    "0,0": {"tile_type_id": "D", "rotation": 0}
                }
            }
        }

        features, tile_feature_map = initialize_features_from_tile("D", "0,0", 0)
        game_data["features"] = features
        game_data["tile_feature_map"] = tile_feature_map

        game_data["board"]["tiles"]["0,1"] = {"tile_type_id": "E", "rotation": 180}

        events = create_and_merge_features(game_data, "E", "0,1", 180)

        # Find the merged city feature
        city_features = [f for f in game_data["features"].values()
                         if f["feature_type"] == FeatureType.CITY]

        # After merging, should have one city feature with both tiles
        merged_city = None
        for feat in city_features:
            if len(feat["tiles"]) > 1:
                merged_city = feat
                break

        assert merged_city is not None
        assert set(merged_city["tiles"]) == {"0,0", "0,1"}

    def test_merge_combines_pennants(self):
        """Verify merging combines pennant counts."""
        game_data = {
            "features": {},
            "tile_feature_map": {},
            "board": {
                "tiles": {
                    "0,0": {"tile_type_id": "F", "rotation": 0}  # City E-W with pennant
                }
            }
        }

        features, tile_feature_map = initialize_features_from_tile("F", "0,0", 0)
        game_data["features"] = features
        game_data["tile_feature_map"] = tile_feature_map

        # Place another F tile to the east (also has pennant)
        game_data["board"]["tiles"]["1,0"] = {"tile_type_id": "F", "rotation": 0}

        events = create_and_merge_features(game_data, "F", "1,0", 0)

        # Find the merged city feature
        city_features = [f for f in game_data["features"].values()
                         if f["feature_type"] == FeatureType.CITY and len(f["tiles"]) > 1]

        assert len(city_features) >= 1
        # Should have 2 pennants (one from each tile)
        merged_city = city_features[0]
        assert merged_city["pennants"] == 2

    def test_merge_removes_connecting_open_edges(self):
        """Verify merging removes the connecting open edges."""
        game_data = {
            "features": {},
            "tile_feature_map": {},
            "board": {
                "tiles": {
                    "0,0": {"tile_type_id": "D", "rotation": 0}
                }
            }
        }

        features, tile_feature_map = initialize_features_from_tile("D", "0,0", 0)
        game_data["features"] = features
        game_data["tile_feature_map"] = tile_feature_map

        game_data["board"]["tiles"]["0,1"] = {"tile_type_id": "E", "rotation": 180}

        # Before merge, city at 0,0 has open edge at N
        city_feature_before = [f for f in game_data["features"].values()
                               if f["feature_type"] == FeatureType.CITY][0]
        assert ["0,0", "N"] in city_feature_before["open_edges"]

        events = create_and_merge_features(game_data, "E", "0,1", 180)

        # After merge, the connecting edges should be removed
        city_features = [f for f in game_data["features"].values()
                         if f["feature_type"] == FeatureType.CITY and len(f["tiles"]) > 1]

        if city_features:
            merged_city = city_features[0]
            # The N edge of 0,0 and S edge of 0,1 should be removed
            assert ["0,0", "N"] not in merged_city["open_edges"]
            assert ["0,1", "S"] not in merged_city["open_edges"]


class TestIsFeatureComplete:
    """Tests for feature completion detection."""

    def test_city_with_no_open_edges_is_complete(self):
        """Verify a city with no open edges is complete."""
        game_data = {"board": {"tiles": {}}}
        feature = {
            "feature_type": FeatureType.CITY,
            "tiles": ["0,0", "0,1"],
            "open_edges": [],
            "pennants": 0
        }

        assert is_feature_complete(game_data, feature) is True

    def test_city_with_open_edges_is_incomplete(self):
        """Verify a city with open edges is incomplete."""
        game_data = {"board": {"tiles": {}}}
        feature = {
            "feature_type": FeatureType.CITY,
            "tiles": ["0,0"],
            "open_edges": [["0,0", "N"]],
            "pennants": 0
        }

        assert is_feature_complete(game_data, feature) is False

    def test_road_with_no_open_edges_is_complete(self):
        """Verify a road with no open edges is complete."""
        game_data = {"board": {"tiles": {}}}
        feature = {
            "feature_type": FeatureType.ROAD,
            "tiles": ["0,0", "1,0"],
            "open_edges": []
        }

        assert is_feature_complete(game_data, feature) is True

    def test_road_with_open_edges_is_incomplete(self):
        """Verify a road with open edges is incomplete."""
        game_data = {"board": {"tiles": {}}}
        feature = {
            "feature_type": FeatureType.ROAD,
            "tiles": ["0,0"],
            "open_edges": [["0,0", "E"]],
        }

        assert is_feature_complete(game_data, feature) is False

    def test_monastery_with_8_neighbors_is_complete(self):
        """Verify a monastery with all 8 surrounding tiles is complete."""
        # Create a board with monastery at 0,0 and all 8 surrounding tiles
        board_tiles = {
            "0,0": {"tile_type_id": "A", "rotation": 0},  # Monastery
            # 8 surrounding tiles
            "-1,1": {"tile_type_id": "E", "rotation": 0},
            "0,1": {"tile_type_id": "E", "rotation": 0},
            "1,1": {"tile_type_id": "E", "rotation": 0},
            "-1,0": {"tile_type_id": "E", "rotation": 0},
            "1,0": {"tile_type_id": "E", "rotation": 0},
            "-1,-1": {"tile_type_id": "E", "rotation": 0},
            "0,-1": {"tile_type_id": "E", "rotation": 0},
            "1,-1": {"tile_type_id": "E", "rotation": 0},
        }

        game_data = {"board": {"tiles": board_tiles}}
        feature = {
            "feature_type": FeatureType.MONASTERY,
            "tiles": ["0,0"]
        }

        assert is_feature_complete(game_data, feature) is True

    def test_monastery_with_7_neighbors_is_incomplete(self):
        """Verify a monastery with only 7 surrounding tiles is incomplete."""
        board_tiles = {
            "0,0": {"tile_type_id": "A", "rotation": 0},  # Monastery
            # Only 7 surrounding tiles
            "-1,1": {"tile_type_id": "E", "rotation": 0},
            "0,1": {"tile_type_id": "E", "rotation": 0},
            "1,1": {"tile_type_id": "E", "rotation": 0},
            "-1,0": {"tile_type_id": "E", "rotation": 0},
            "1,0": {"tile_type_id": "E", "rotation": 0},
            "-1,-1": {"tile_type_id": "E", "rotation": 0},
            "0,-1": {"tile_type_id": "E", "rotation": 0},
            # Missing 1,-1
        }

        game_data = {"board": {"tiles": board_tiles}}
        feature = {
            "feature_type": FeatureType.MONASTERY,
            "tiles": ["0,0"]
        }

        assert is_feature_complete(game_data, feature) is False

    def test_field_is_never_complete(self):
        """Verify fields are never complete during the game."""
        game_data = {"board": {"tiles": {}}}
        feature = {
            "feature_type": FeatureType.FIELD,
            "tiles": ["0,0", "0,1"],
            "open_edges": []
        }

        assert is_feature_complete(game_data, feature) is False


class TestCheckMonasteryCompletion:
    """Tests for monastery completion checking."""

    def test_check_monastery_completion_when_complete(self):
        """Verify monastery completion is detected and scored."""
        # Set up a monastery that will be completed
        board_tiles = {
            "0,0": {"tile_type_id": "A", "rotation": 0},  # Monastery
            # 7 surrounding tiles already placed
            "-1,1": {"tile_type_id": "E", "rotation": 0},
            "0,1": {"tile_type_id": "E", "rotation": 0},
            "1,1": {"tile_type_id": "E", "rotation": 0},
            "-1,0": {"tile_type_id": "E", "rotation": 0},
            "1,0": {"tile_type_id": "E", "rotation": 0},
            "-1,-1": {"tile_type_id": "E", "rotation": 0},
            "0,-1": {"tile_type_id": "E", "rotation": 0},
        }

        game_data = {
            "board": {"tiles": board_tiles},
            "features": {},
            "tile_feature_map": {},
            "meeple_supply": {"player1": 7}
        }

        # Initialize monastery feature
        features, tile_feature_map = initialize_features_from_tile("A", "0,0", 0)
        game_data["features"] = features
        game_data["tile_feature_map"] = tile_feature_map

        # Add a meeple to the monastery
        monastery_feature = [f for f in features.values()
                            if f["feature_type"] == FeatureType.MONASTERY][0]
        monastery_feature["meeples"] = [{"player_id": "player1", "position": "0,0", "spot": "monastery"}]

        # Place the 8th surrounding tile
        board_tiles["1,-1"] = {"tile_type_id": "E", "rotation": 0}

        events, scores = check_monastery_completion(game_data, "1,-1")

        # Should have scored the monastery
        assert "player1" in scores
        assert scores["player1"] == 9

        # Should have scoring event
        score_events = [e for e in events if e.event_type == "feature_scored"]
        assert len(score_events) == 1
        assert score_events[0].player_id == "player1"

    def test_check_monastery_no_completion(self):
        """Verify no scoring when monastery is not complete."""
        board_tiles = {
            "0,0": {"tile_type_id": "A", "rotation": 0},  # Monastery
            # Only 6 surrounding tiles
            "-1,1": {"tile_type_id": "E", "rotation": 0},
            "0,1": {"tile_type_id": "E", "rotation": 0},
            "1,1": {"tile_type_id": "E", "rotation": 0},
            "-1,0": {"tile_type_id": "E", "rotation": 0},
            "1,0": {"tile_type_id": "E", "rotation": 0},
            "-1,-1": {"tile_type_id": "E", "rotation": 0},
        }

        game_data = {
            "board": {"tiles": board_tiles},
            "features": {},
            "tile_feature_map": {},
            "meeple_supply": {"player1": 7}
        }

        features, tile_feature_map = initialize_features_from_tile("A", "0,0", 0)
        game_data["features"] = features
        game_data["tile_feature_map"] = tile_feature_map

        # Place a tile that doesn't complete the monastery
        board_tiles["0,-1"] = {"tile_type_id": "E", "rotation": 0}

        events, scores = check_monastery_completion(game_data, "0,-1")

        # Should not score
        assert scores == {}
