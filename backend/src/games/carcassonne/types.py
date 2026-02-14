from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from src.engine.models import PlayerId


class EdgeType(str, Enum):
    CITY = "city"
    ROAD = "road"
    FIELD = "field"


class FeatureType(str, Enum):
    CITY = "city"
    ROAD = "road"
    FIELD = "field"
    MONASTERY = "monastery"


OPPOSITE_DIRECTION = {"N": "S", "E": "W", "S": "N", "W": "E"}
DIRECTIONS = ["N", "E", "S", "W"]


class TileFeature(BaseModel):
    """A feature segment on a single tile."""
    feature_type: FeatureType
    edges: list[str]  # Which edges this feature touches: ["N", "E"]
    has_pennant: bool = False
    is_monastery: bool = False
    meeple_spots: list[str]  # Named positions: ["city_N", "road_S"]
    # Which city meeple_spots are adjacent to this feature (for field scoring)
    adjacent_cities: list[str] = Field(default_factory=list)


class TileDefinition(BaseModel):
    """Static definition of a tile type."""
    tile_type_id: str
    edges: dict[str, EdgeType]  # {"N": EdgeType.CITY, ...}
    features: list[TileFeature]
    count: int
    image_id: str
    internal_connections: list[list[str]]  # Groups of connected meeple_spots


class Position(BaseModel):
    x: int
    y: int

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Position):
            return self.x == other.x and self.y == other.y
        return NotImplemented

    def to_key(self) -> str:
        return f"{self.x},{self.y}"

    @staticmethod
    def from_key(key: str) -> Position:
        x, y = key.split(",")
        return Position(x=int(x), y=int(y))

    def neighbor(self, direction: str) -> Position:
        if direction == "N":
            return Position(x=self.x, y=self.y + 1)
        elif direction == "E":
            return Position(x=self.x + 1, y=self.y)
        elif direction == "S":
            return Position(x=self.x, y=self.y - 1)
        elif direction == "W":
            return Position(x=self.x - 1, y=self.y)
        raise ValueError(f"Invalid direction: {direction}")

    def neighbors(self) -> dict[str, Position]:
        return {d: self.neighbor(d) for d in DIRECTIONS}

    def all_surrounding(self) -> list[Position]:
        """All 8 surrounding positions (for monastery check)."""
        return [
            Position(x=self.x + dx, y=self.y + dy)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if not (dx == 0 and dy == 0)
        ]


class PlacedMeeple(BaseModel):
    player_id: str  # PlayerId
    position: str   # "x,y"
    spot: str       # meeple_spot name


class Feature(BaseModel):
    """A tracked feature on the board spanning one or more tiles."""
    feature_id: str
    feature_type: FeatureType
    tiles: list[str]  # Positions "x,y"
    meeples: list[PlacedMeeple] = Field(default_factory=list)
    is_complete: bool = False
    pennants: int = 0
    open_edges: list[list[str]] = Field(default_factory=list)  # [["x,y", "N"], ...]


def rotate_edges(edges: dict[str, EdgeType], rotation: int) -> dict[str, EdgeType]:
    """Rotate edge types clockwise by rotation degrees (0, 90, 180, 270)."""
    steps = (rotation // 90) % 4
    rotated = {}
    for i, d in enumerate(DIRECTIONS):
        source = DIRECTIONS[(i - steps) % 4]
        rotated[d] = edges[source]
    return rotated


def rotate_direction(direction: str, rotation: int) -> str:
    """Rotate a single direction clockwise by rotation degrees."""
    steps = (rotation // 90) % 4
    idx = DIRECTIONS.index(direction)
    return DIRECTIONS[(idx + steps) % 4]


def rotate_compound_edge(edge: str, rotation: int) -> str:
    """Rotate an edge identifier that may be compound (e.g., 'E:N' for road-side fields).

    Simple edges like 'E' rotate normally.
    Compound edges like 'E:N' rotate both the direction and the side.
    """
    if ":" in edge:
        direction, side = edge.split(":")
        return f"{rotate_direction(direction, rotation)}:{rotate_direction(side, rotation)}"
    return rotate_direction(edge, rotation)


def rotate_meeple_spot(spot: str, rotation: int) -> str:
    """Rotate a meeple spot name by rotating its direction components.

    Meeple spots are named like 'city_N', 'road_EW', 'field_NW_left'.
    We need to rotate the direction letters within them.
    """
    if rotation == 0:
        return spot

    parts = spot.split("_")
    if len(parts) < 2:
        return spot  # e.g. "monastery"

    prefix = parts[0]
    direction_part = parts[1]
    suffix = "_".join(parts[2:])

    # Rotate each direction letter in the direction part
    rotated_dirs = ""
    for ch in direction_part:
        if ch in "NESW":
            rotated_dirs += rotate_direction(ch, rotation)
        else:
            rotated_dirs += ch

    # Sort direction letters for canonical form (N before E before S before W)
    dir_order = {"N": 0, "E": 1, "S": 2, "W": 3}
    rotated_dirs = "".join(sorted(rotated_dirs, key=lambda c: dir_order.get(c, 99)))

    result = f"{prefix}_{rotated_dirs}"
    if suffix:
        result += f"_{suffix}"
    return result
