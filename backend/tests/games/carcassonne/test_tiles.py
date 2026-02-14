"""Unit tests for Carcassonne tile catalog and tile operations."""

import pytest

from src.games.carcassonne.tiles import (
    TILE_CATALOG,
    TILE_LOOKUP,
    STARTING_TILE_ID,
    build_tile_bag,
    get_tile_total,
    get_rotated_features,
)
from src.games.carcassonne.types import EdgeType, FeatureType, DIRECTIONS


class TestTileCatalog:
    """Tests for the tile catalog data."""

    def test_catalog_has_24_tile_types(self):
        """Verify TILE_CATALOG has 24 different tile types."""
        assert len(TILE_CATALOG) == 24

    def test_total_tile_count_is_72(self):
        """Verify the total count of tiles across all types is 72."""
        total = get_tile_total()
        assert total == 72

    def test_catalog_tile_count_sum(self):
        """Verify summing individual counts equals 72."""
        total_count = sum(tile_def.count for tile_def in TILE_CATALOG)
        assert total_count == 72

    def test_starting_tile_is_D(self):
        """Verify the starting tile ID is 'D'."""
        assert STARTING_TILE_ID == "D"

    def test_all_tiles_have_valid_edges(self):
        """Verify each tile has all four edge directions (N, E, S, W)."""
        for tile_def in TILE_CATALOG:
            assert set(tile_def.edges.keys()) == set(DIRECTIONS)
            # All edges should be valid EdgeType values
            for edge_type in tile_def.edges.values():
                assert edge_type in [EdgeType.CITY, EdgeType.ROAD, EdgeType.FIELD]

    def test_all_tiles_have_features(self):
        """Verify each tile has at least one feature."""
        for tile_def in TILE_CATALOG:
            assert len(tile_def.features) > 0

    def test_tile_lookup_contains_all_types(self):
        """Verify TILE_LOOKUP dict contains all tile types."""
        assert len(TILE_LOOKUP) == 24
        for tile_def in TILE_CATALOG:
            assert tile_def.tile_type_id in TILE_LOOKUP
            assert TILE_LOOKUP[tile_def.tile_type_id] == tile_def


class TestBuildTileBag:
    """Tests for building the tile draw bag."""

    def test_build_tile_bag_returns_71_tiles(self):
        """Verify build_tile_bag returns 71 tiles (72 - 1 starting tile)."""
        bag = build_tile_bag()
        assert len(bag) == 71

    def test_tile_bag_excludes_one_starting_tile(self):
        """Verify the tile bag has one less 'D' tile than the catalog specifies."""
        bag = build_tile_bag()
        d_count_in_bag = sum(1 for tile_id in bag if tile_id == "D")
        d_count_in_catalog = TILE_LOOKUP["D"].count
        assert d_count_in_bag == d_count_in_catalog - 1

    def test_tile_bag_contains_valid_tile_ids(self):
        """Verify all tiles in the bag are valid tile IDs."""
        bag = build_tile_bag()
        for tile_id in bag:
            assert tile_id in TILE_LOOKUP


class TestGetRotatedFeatures:
    """Tests for rotating tile features."""

    def test_rotation_0_returns_original_features(self):
        """Verify rotation of 0 degrees returns unchanged features."""
        tile_id = "D"
        original = TILE_LOOKUP[tile_id].features
        rotated = get_rotated_features(tile_id, 0)

        assert len(rotated) == len(original)
        for i, feat in enumerate(rotated):
            assert feat.feature_type == original[i].feature_type
            assert feat.edges == original[i].edges
            assert feat.has_pennant == original[i].has_pennant
            assert feat.is_monastery == original[i].is_monastery

    def test_rotation_90_rotates_edges(self):
        """Verify 90-degree rotation correctly rotates edge directions."""
        # Tile D: City N, Road E-W
        tile_id = "D"
        rotated = get_rotated_features(tile_id, 90)

        # Find the city feature
        city_features = [f for f in rotated if f.feature_type == FeatureType.CITY]
        assert len(city_features) == 1
        # City was on N, after 90 clockwise should be on E
        assert city_features[0].edges == ["E"]

        # Find the road feature
        road_features = [f for f in rotated if f.feature_type == FeatureType.ROAD]
        assert len(road_features) == 1
        # Road was on E-W, after 90 clockwise should be on S-N
        assert set(road_features[0].edges) == {"S", "N"}

    def test_rotation_180_rotates_edges(self):
        """Verify 180-degree rotation correctly rotates edge directions."""
        # Tile D: City N, Road E-W
        tile_id = "D"
        rotated = get_rotated_features(tile_id, 180)

        # Find the city feature
        city_features = [f for f in rotated if f.feature_type == FeatureType.CITY]
        assert len(city_features) == 1
        # City was on N, after 180 should be on S
        assert city_features[0].edges == ["S"]

        # Find the road feature
        road_features = [f for f in rotated if f.feature_type == FeatureType.ROAD]
        assert len(road_features) == 1
        # Road was on E-W, after 180 should still be on E-W
        assert set(road_features[0].edges) == {"E", "W"}

    def test_rotation_270_rotates_edges(self):
        """Verify 270-degree rotation correctly rotates edge directions."""
        # Tile D: City N, Road E-W
        tile_id = "D"
        rotated = get_rotated_features(tile_id, 270)

        # Find the city feature
        city_features = [f for f in rotated if f.feature_type == FeatureType.CITY]
        assert len(city_features) == 1
        # City was on N, after 270 clockwise (or 90 counter) should be on W
        assert city_features[0].edges == ["W"]

        # Find the road feature
        road_features = [f for f in rotated if f.feature_type == FeatureType.ROAD]
        assert len(road_features) == 1
        # Road was on E-W, after 270 clockwise should be on N-S
        assert set(road_features[0].edges) == {"N", "S"}

    def test_rotation_preserves_feature_count(self):
        """Verify rotation doesn't change the number of features."""
        for tile_id in ["A", "D", "L", "X"]:
            original_count = len(TILE_LOOKUP[tile_id].features)
            for rotation in [0, 90, 180, 270]:
                rotated = get_rotated_features(tile_id, rotation)
                assert len(rotated) == original_count

    def test_rotation_preserves_pennants(self):
        """Verify rotation preserves pennant status."""
        # Tile C has a pennant
        tile_id = "C"
        for rotation in [0, 90, 180, 270]:
            rotated = get_rotated_features(tile_id, rotation)
            city_features = [f for f in rotated if f.feature_type == FeatureType.CITY]
            assert city_features[0].has_pennant is True

    def test_rotation_preserves_monastery(self):
        """Verify rotation preserves monastery status."""
        # Tile A has a monastery
        tile_id = "A"
        for rotation in [0, 90, 180, 270]:
            rotated = get_rotated_features(tile_id, rotation)
            monastery_features = [f for f in rotated if f.feature_type == FeatureType.MONASTERY]
            assert len(monastery_features) == 1
            assert monastery_features[0].is_monastery is True

    def test_rotation_rotates_meeple_spots(self):
        """Verify meeple spots are rotated correctly."""
        # Tile D has city_N and road_EW spots
        tile_id = "D"

        # At 90 degrees
        rotated = get_rotated_features(tile_id, 90)
        city_features = [f for f in rotated if f.feature_type == FeatureType.CITY]
        assert "city_E" in city_features[0].meeple_spots

        road_features = [f for f in rotated if f.feature_type == FeatureType.ROAD]
        assert "road_NS" in road_features[0].meeple_spots


class TestSpecificTiles:
    """Tests for specific tile types."""

    def test_tile_D_starting_tile(self):
        """Test the starting tile D has expected properties."""
        tile_d = TILE_LOOKUP["D"]
        assert tile_d.edges["N"] == EdgeType.CITY
        assert tile_d.edges["E"] == EdgeType.ROAD
        assert tile_d.edges["S"] == EdgeType.FIELD
        assert tile_d.edges["W"] == EdgeType.ROAD
        assert tile_d.count == 4

    def test_tile_C_full_city_with_pennant(self):
        """Test tile C is a full city with pennant."""
        tile_c = TILE_LOOKUP["C"]
        assert all(edge == EdgeType.CITY for edge in tile_c.edges.values())
        assert tile_c.count == 1
        # Should have one city feature with pennant
        city_features = [f for f in tile_c.features if f.feature_type == FeatureType.CITY]
        assert len(city_features) == 1
        assert city_features[0].has_pennant is True

    def test_tile_U_straight_road(self):
        """Test tile U is a straight road N-S."""
        tile_u = TILE_LOOKUP["U"]
        assert tile_u.edges["N"] == EdgeType.ROAD
        assert tile_u.edges["E"] == EdgeType.FIELD
        assert tile_u.edges["S"] == EdgeType.ROAD
        assert tile_u.edges["W"] == EdgeType.FIELD
        assert tile_u.count == 8

    def test_tile_X_crossroads(self):
        """Test tile X is a 4-way crossroads."""
        tile_x = TILE_LOOKUP["X"]
        assert all(edge == EdgeType.ROAD for edge in tile_x.edges.values())
        assert tile_x.count == 1
