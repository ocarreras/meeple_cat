"""Complete tile catalog for the Carcassonne base game (24 types, 72 tiles)."""

from src.games.carcassonne.types import (
    EdgeType,
    FeatureType,
    TileDefinition,
    TileFeature,
)

C = EdgeType.CITY
R = EdgeType.ROAD
F = EdgeType.FIELD

# Tile definitions following the standard A-X naming convention.
#
# Edge order is always: N, E, S, W
# Meeple spots use the format: {feature_type}_{directions}[_suffix]
# internal_connections groups meeple spots that are part of the same feature segment on the tile.
# adjacent_cities on field features lists the city meeple spots the field borders (for end-game scoring).

TILE_CATALOG: list[TileDefinition] = [
    # A: Monastery with road south (x2)
    TileDefinition(
        tile_type_id="A",
        edges={"N": F, "E": F, "S": R, "W": F},
        features=[
            TileFeature(feature_type=FeatureType.MONASTERY, edges=[], is_monastery=True, meeple_spots=["monastery"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["S"], meeple_spots=["road_S"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["N", "E", "W"], meeple_spots=["field_NEW"], adjacent_cities=[]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_A",
    ),

    # B: Monastery, no road (x4)
    TileDefinition(
        tile_type_id="B",
        edges={"N": F, "E": F, "S": F, "W": F},
        features=[
            TileFeature(feature_type=FeatureType.MONASTERY, edges=[], is_monastery=True, meeple_spots=["monastery"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["N", "E", "S", "W"], meeple_spots=["field_NESW"], adjacent_cities=[]),
        ],
        internal_connections=[],
        count=4,
        image_id="tile_B",
    ),

    # C: Full city with pennant (x1) — city on all 4 edges, all connected
    TileDefinition(
        tile_type_id="C",
        edges={"N": C, "E": C, "S": C, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "E", "S", "W"], has_pennant=True, meeple_spots=["city_NESW"]),
        ],
        internal_connections=[],
        count=1,
        image_id="tile_C",
    ),

    # D: City N, road E-W (x4) — the starting tile
    TileDefinition(
        tile_type_id="D",
        edges={"N": C, "E": R, "S": F, "W": R},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N"], meeple_spots=["city_N"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["E", "W"], meeple_spots=["road_EW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_N"], adjacent_cities=["city_N"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["S"], meeple_spots=["field_S"], adjacent_cities=["city_N"]),
        ],
        internal_connections=[],
        count=4,
        image_id="tile_D",
    ),

    # E: City N (x5) — simple city on one edge
    TileDefinition(
        tile_type_id="E",
        edges={"N": C, "E": F, "S": F, "W": F},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N"], meeple_spots=["city_N"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E", "S", "W"], meeple_spots=["field_ESW"], adjacent_cities=["city_N"]),
        ],
        internal_connections=[],
        count=5,
        image_id="tile_E",
    ),

    # F: City E-W connected, with pennant (x2) — city spanning east and west
    TileDefinition(
        tile_type_id="F",
        edges={"N": F, "E": C, "S": F, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["E", "W"], has_pennant=True, meeple_spots=["city_EW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["N"], meeple_spots=["field_N"], adjacent_cities=["city_EW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["S"], meeple_spots=["field_S"], adjacent_cities=["city_EW"]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_F",
    ),

    # G: City N-S connected (x1) — city spanning north and south
    TileDefinition(
        tile_type_id="G",
        edges={"N": C, "E": F, "S": C, "W": F},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "S"], meeple_spots=["city_NS"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E"], meeple_spots=["field_E"], adjacent_cities=["city_NS"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["W"], meeple_spots=["field_W"], adjacent_cities=["city_NS"]),
        ],
        internal_connections=[],
        count=1,
        image_id="tile_G",
    ),

    # H: City N and city S, NOT connected (x3)
    TileDefinition(
        tile_type_id="H",
        edges={"N": C, "E": F, "S": C, "W": F},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N"], meeple_spots=["city_N"]),
            TileFeature(feature_type=FeatureType.CITY, edges=["S"], meeple_spots=["city_S"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E"], meeple_spots=["field_E"], adjacent_cities=["city_N", "city_S"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["W"], meeple_spots=["field_W"], adjacent_cities=["city_N", "city_S"]),
        ],
        internal_connections=[],
        count=3,
        image_id="tile_H",
    ),

    # I: City N and city E, NOT connected (x2)
    TileDefinition(
        tile_type_id="I",
        edges={"N": C, "E": F, "S": F, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N"], meeple_spots=["city_N"]),
            TileFeature(feature_type=FeatureType.CITY, edges=["W"], meeple_spots=["city_W"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E", "S"], meeple_spots=["field_ES"], adjacent_cities=["city_N", "city_W"]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_I",
    ),

    # J: City N, road E-S curve (x3)
    TileDefinition(
        tile_type_id="J",
        edges={"N": C, "E": R, "S": R, "W": F},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N"], meeple_spots=["city_N"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["E", "S"], meeple_spots=["road_ES"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["W"], meeple_spots=["field_W"], adjacent_cities=["city_N"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_ES"], adjacent_cities=["city_N"]),
        ],
        internal_connections=[],
        count=3,
        image_id="tile_J",
    ),

    # K: City N, road W-S curve (x3)
    TileDefinition(
        tile_type_id="K",
        edges={"N": C, "E": F, "S": R, "W": R},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N"], meeple_spots=["city_N"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["S", "W"], meeple_spots=["road_SW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E"], meeple_spots=["field_E"], adjacent_cities=["city_N"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SW"], adjacent_cities=["city_N"]),
        ],
        internal_connections=[],
        count=3,
        image_id="tile_K",
    ),

    # L: City N, road E-S-W T-junction (x3)
    TileDefinition(
        tile_type_id="L",
        edges={"N": C, "E": R, "S": R, "W": R},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N"], meeple_spots=["city_N"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["E"], meeple_spots=["road_E"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["S"], meeple_spots=["road_S"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["W"], meeple_spots=["road_W"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_NE"], adjacent_cities=["city_N"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SE"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SW"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_NW"], adjacent_cities=["city_N"]),
        ],
        internal_connections=[],
        count=3,
        image_id="tile_L",
    ),

    # M: City N-W connected, with pennant (x2)
    TileDefinition(
        tile_type_id="M",
        edges={"N": C, "E": F, "S": F, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "W"], has_pennant=True, meeple_spots=["city_NW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E", "S"], meeple_spots=["field_ES"], adjacent_cities=["city_NW"]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_M",
    ),

    # N: City N-W connected, no pennant (x3)
    TileDefinition(
        tile_type_id="N",
        edges={"N": C, "E": F, "S": F, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "W"], meeple_spots=["city_NW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E", "S"], meeple_spots=["field_ES"], adjacent_cities=["city_NW"]),
        ],
        internal_connections=[],
        count=3,
        image_id="tile_N",
    ),

    # O: City N-W connected, pennant, road E-S (x2)
    TileDefinition(
        tile_type_id="O",
        edges={"N": C, "E": R, "S": R, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "W"], has_pennant=True, meeple_spots=["city_NW"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["E", "S"], meeple_spots=["road_ES"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_NE"], adjacent_cities=["city_NW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SE"], adjacent_cities=[]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_O",
    ),

    # P: City N-W connected, no pennant, road E-S (x3)
    TileDefinition(
        tile_type_id="P",
        edges={"N": C, "E": R, "S": R, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "W"], meeple_spots=["city_NW"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["E", "S"], meeple_spots=["road_ES"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_NE"], adjacent_cities=["city_NW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SE"], adjacent_cities=[]),
        ],
        internal_connections=[],
        count=3,
        image_id="tile_P",
    ),

    # Q: City N-E-W connected, with pennant (x2) — three-sided city
    TileDefinition(
        tile_type_id="Q",
        edges={"N": C, "E": C, "S": F, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "E", "W"], has_pennant=True, meeple_spots=["city_NEW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["S"], meeple_spots=["field_S"], adjacent_cities=["city_NEW"]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_Q",
    ),

    # R: City N-E-W connected, pennant, road S (x2)
    TileDefinition(
        tile_type_id="R",
        edges={"N": C, "E": C, "S": R, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "E", "W"], has_pennant=True, meeple_spots=["city_NEW"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["S"], meeple_spots=["road_S"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SW"], adjacent_cities=["city_NEW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SE"], adjacent_cities=["city_NEW"]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_R",
    ),

    # S: City N-E-W connected, no pennant (x2) — three-sided city without pennant
    TileDefinition(
        tile_type_id="S",
        edges={"N": C, "E": C, "S": F, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "E", "W"], meeple_spots=["city_NEW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["S"], meeple_spots=["field_S"], adjacent_cities=["city_NEW"]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_S",
    ),

    # T: City N-E-W connected, no pennant, road S (x1) — three-sided city with road
    TileDefinition(
        tile_type_id="T",
        edges={"N": C, "E": C, "S": R, "W": C},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N", "E", "W"], meeple_spots=["city_NEW"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["S"], meeple_spots=["road_S"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SW"], adjacent_cities=["city_NEW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SE"], adjacent_cities=["city_NEW"]),
        ],
        internal_connections=[],
        count=1,
        image_id="tile_T",
    ),

    # U: Road N-S straight (x8)
    TileDefinition(
        tile_type_id="U",
        edges={"N": R, "E": F, "S": R, "W": F},
        features=[
            TileFeature(feature_type=FeatureType.ROAD, edges=["N", "S"], meeple_spots=["road_NS"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E"], meeple_spots=["field_E"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["W"], meeple_spots=["field_W"], adjacent_cities=[]),
        ],
        internal_connections=[],
        count=8,
        image_id="tile_U",
    ),

    # V: Road S-W curve (x9)
    TileDefinition(
        tile_type_id="V",
        edges={"N": F, "E": F, "S": R, "W": R},
        features=[
            TileFeature(feature_type=FeatureType.ROAD, edges=["S", "W"], meeple_spots=["road_SW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["N", "E"], meeple_spots=["field_NE"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SW"], adjacent_cities=[]),
        ],
        internal_connections=[],
        count=9,
        image_id="tile_V",
    ),

    # W: Road 3-way T-junction N-S-W (x4)
    TileDefinition(
        tile_type_id="W",
        edges={"N": R, "E": F, "S": R, "W": R},
        features=[
            TileFeature(feature_type=FeatureType.ROAD, edges=["N"], meeple_spots=["road_N"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["S"], meeple_spots=["road_S"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["W"], meeple_spots=["road_W"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["E"], meeple_spots=["field_NE"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SE"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_NW"], adjacent_cities=[]),
        ],
        internal_connections=[],
        count=4,
        image_id="tile_W",
    ),

    # X: Road 4-way crossroads (x1)
    TileDefinition(
        tile_type_id="X",
        edges={"N": R, "E": R, "S": R, "W": R},
        features=[
            TileFeature(feature_type=FeatureType.ROAD, edges=["N"], meeple_spots=["road_N"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["E"], meeple_spots=["road_E"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["S"], meeple_spots=["road_S"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["W"], meeple_spots=["road_W"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_NE"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SE"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_SW"], adjacent_cities=[]),
            TileFeature(feature_type=FeatureType.FIELD, edges=[], meeple_spots=["field_NW"], adjacent_cities=[]),
        ],
        internal_connections=[],
        count=1,
        image_id="tile_X",
    ),
]

# Quick lookup by tile type ID
TILE_LOOKUP: dict[str, TileDefinition] = {t.tile_type_id: t for t in TILE_CATALOG}

# Starting tile
STARTING_TILE_ID = "D"


def build_tile_bag(expansions: list[str] | None = None) -> list[str]:
    """Build the draw bag (list of tile_type_ids). Excludes one copy of the starting tile."""
    bag: list[str] = []
    for tile_def in TILE_CATALOG:
        count = tile_def.count
        if tile_def.tile_type_id == STARTING_TILE_ID:
            count -= 1  # One is used as the starting tile
        for _ in range(count):
            bag.append(tile_def.tile_type_id)
    return bag


def get_tile_total() -> int:
    """Total number of tiles in the base game."""
    return sum(t.count for t in TILE_CATALOG)


def get_rotated_features(tile_type_id: str, rotation: int) -> list[TileFeature]:
    """Get the features of a tile with rotation applied to edges and meeple spots."""
    from src.games.carcassonne.types import rotate_direction, rotate_meeple_spot

    tile_def = TILE_LOOKUP[tile_type_id]
    if rotation == 0:
        return tile_def.features

    rotated_features = []
    for feat in tile_def.features:
        rotated_edges = [rotate_direction(e, rotation) for e in feat.edges]
        rotated_spots = [rotate_meeple_spot(s, rotation) for s in feat.meeple_spots]
        rotated_adj = [rotate_meeple_spot(s, rotation) for s in feat.adjacent_cities]
        rotated_features.append(TileFeature(
            feature_type=feat.feature_type,
            edges=rotated_edges,
            has_pennant=feat.has_pennant,
            is_monastery=feat.is_monastery,
            meeple_spots=rotated_spots,
            adjacent_cities=rotated_adj,
        ))
    return rotated_features
