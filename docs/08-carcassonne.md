# 08 — Carcassonne Implementation

Carcassonne is the first game implemented on meeple.cat. It serves as the
validation that the game engine abstraction (01-game-engine.md) works for a
real, non-trivial board game.

> **Note (Feb 2025):** The canonical implementation is now in Rust at
> `game-engine/src/games/carcassonne/`. The Python code in this document
> served as the original design spec and was used to validate the Rust
> port (see `docs/09-rust-mcts-engine.md` for equivalence testing).
> The Python game plugin has been removed — all game logic runs in the
> Rust engine via gRPC.

**Game summary**: Players take turns drawing a tile, placing it on the board
(edges must match), optionally placing a meeple on a feature of the placed
tile, and scoring completed features. The game ends when all tiles are placed.

---

## 1. Tile System

### 1.1 Edge Types

Each tile has 4 edges (N, E, S, W). Each edge has a type:

```python
class EdgeType(str, Enum):
    CITY   = "city"
    ROAD   = "road"
    FIELD  = "field"
```

### 1.2 Tile Features

A tile contains one or more *features* — contiguous regions that can be
claimed by meeples. Features are the scoring units.

```python
class FeatureType(str, Enum):
    CITY      = "city"
    ROAD      = "road"
    FIELD     = "field"
    MONASTERY = "monastery"

class TileFeature(BaseModel):
    """A feature segment on a single tile."""
    feature_type: FeatureType
    edges: list[str]              # Which edges this feature touches: ["N", "E"]
    has_pennant: bool = False     # City bonus (shield symbol)
    is_monastery: bool = False    # Center feature, not edge-connected
    meeple_spots: list[str]      # Named positions where a meeple can go
                                  # e.g. ["city_NE", "road_S", "field_NW"]
```

### 1.3 Tile Definition

```python
class TileDefinition(BaseModel):
    """
    Static definition of a tile type. The base game has 24 unique tile types
    with varying quantities (72 tiles total).
    """
    tile_type_id: str             # e.g. "CRRF" (City, Road, Road, Field for N,E,S,W)
    edges: dict[str, EdgeType]    # {"N": "city", "E": "road", "S": "road", "W": "field"}
    features: list[TileFeature]   # All features on this tile
    count: int                    # How many of this type in the base game
    image_id: str                 # For frontend rendering

    # Connectivity within the tile:
    # Which features are connected WITHIN this tile.
    # E.g. a tile where North city and East city are the same city segment.
    internal_connections: list[list[str]]  # Groups of connected meeple_spots
```

### 1.4 Tile Rotation

Tiles can be placed in 4 rotations (0°, 90°, 180°, 270°). Rotation shifts
edges clockwise:

```python
def rotate_edges(edges: dict[str, EdgeType], rotation: int) -> dict[str, EdgeType]:
    """Rotate edge types clockwise by rotation degrees (0, 90, 180, 270)."""
    directions = ["N", "E", "S", "W"]
    steps = rotation // 90
    rotated = {}
    for i, d in enumerate(directions):
        source = directions[(i - steps) % 4]
        rotated[d] = edges[source]
    return rotated
```

### 1.5 Complete Tile Catalog (Base Game)

The base game has 72 tiles across 24 types. A few representative examples:

```python
TILE_CATALOG = [
    # Starting tile: city on top, road E-W
    TileDefinition(
        tile_type_id="D",
        edges={"N": EdgeType.CITY, "E": EdgeType.ROAD, "S": EdgeType.FIELD, "W": EdgeType.ROAD},
        features=[
            TileFeature(feature_type=FeatureType.CITY, edges=["N"], meeple_spots=["city_N"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["E", "W"], meeple_spots=["road_EW"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["S"], meeple_spots=["field_S_left", "field_S_right"]),
        ],
        internal_connections=[],
        count=4,  # 3 regular + 1 starting tile
        image_id="tile_D",
    ),

    # Monastery with road
    TileDefinition(
        tile_type_id="A",
        edges={"N": EdgeType.FIELD, "E": EdgeType.FIELD, "S": EdgeType.ROAD, "W": EdgeType.FIELD},
        features=[
            TileFeature(feature_type=FeatureType.MONASTERY, edges=[], is_monastery=True, meeple_spots=["monastery"]),
            TileFeature(feature_type=FeatureType.ROAD, edges=["S"], meeple_spots=["road_S"]),
            TileFeature(feature_type=FeatureType.FIELD, edges=["N", "E", "W"], meeple_spots=["field"]),
        ],
        internal_connections=[],
        count=2,
        image_id="tile_A",
    ),

    # Full city (all 4 edges city, with pennant)
    # ... (24 types total, defined in a separate data file)
]
```

The complete catalog lives in `game-engine/src/games/carcassonne/tiles.rs`.

---

## 2. Board Representation

### 2.1 Coordinate System

The board uses a sparse 2D coordinate grid. The starting tile is at (0, 0).
Coordinates extend in all directions.

```python
class Position(BaseModel):
    x: int
    y: int

    def neighbors(self) -> dict[str, "Position"]:
        return {
            "N": Position(x=self.x, y=self.y + 1),
            "E": Position(x=self.x + 1, y=self.y),
            "S": Position(x=self.x, y=self.y - 1),
            "W": Position(x=self.x - 1, y=self.y),
        }
```

### 2.2 Placed Tile

```python
class PlacedTile(BaseModel):
    """A tile that has been placed on the board."""
    tile_type_id: str
    position: Position
    rotation: int                  # 0, 90, 180, 270

    def get_edge(self, direction: str) -> EdgeType:
        """Get the edge type at the given direction after rotation."""
        rotated = rotate_edges(
            TILE_LOOKUP[self.tile_type_id].edges,
            self.rotation
        )
        return rotated[direction]

    def get_features_at_edge(self, direction: str) -> list[TileFeature]:
        """Get features touching the given edge, accounting for rotation."""
        ...
```

### 2.3 Board State

```python
class BoardState(BaseModel):
    """The game board — sparse grid of placed tiles."""
    tiles: dict[str, PlacedTile]   # Key: "x,y" string for JSON serialization
    # Precomputed for fast lookup:
    open_positions: set[str]       # Positions adjacent to placed tiles where a tile could go
```

---

## 3. Feature Tracking

This is the most complex part of Carcassonne. Features (cities, roads, fields)
span multiple tiles and can merge when tiles connect them.

### 3.1 Feature Graph

```python
class Feature(BaseModel):
    """
    A tracked feature on the board. Represents a road, city, field, or monastery
    that may span multiple tiles.

    Features are created when a tile is placed and merged when two features
    connect via a newly placed tile.
    """
    feature_id: str                        # UUID
    feature_type: FeatureType
    tiles: list[str]                       # Positions ("x,y") of tiles in this feature
    meeples: list[PlacedMeeple]            # Meeples on this feature
    is_complete: bool = False              # True when the feature is closed
    pennants: int = 0                      # Number of pennants (city only)

    # Edges that are still "open" (not connected to another tile)
    open_edges: list[tuple[str, str]]      # [(position, direction), ...]

class PlacedMeeple(BaseModel):
    player_id: PlayerId
    position: str                          # "x,y"
    spot: str                              # meeple_spot name on the tile
```

### 3.2 Feature Merge Algorithm

When a new tile is placed, its features may connect to existing features on
adjacent tiles. The merge algorithm:

```
1. For each edge of the new tile:
   a. Check if there's an adjacent tile at that edge
   b. If yes, find which feature the adjacent tile's edge belongs to
   c. Find which feature the new tile's edge belongs to
   d. If they're different features of the same type → MERGE

2. Merging two features:
   a. Combine tile lists, meeple lists, pennant counts
   b. Combine open_edge lists, REMOVING the edges that just connected
   c. Delete the smaller feature, keep the larger one (or arbitrary)
   d. Update all references

3. After all merges, check completeness:
   a. City: complete when open_edges is empty
   b. Road: complete when open_edges is empty
   c. Monastery: complete when all 8 surrounding positions have tiles
   d. Field: never "complete" during the game (scored at end only)
```

```python
def merge_features(
    features: dict[str, Feature],
    feature_a_id: str,
    feature_b_id: str,
) -> dict[str, Feature]:
    """Merge feature_b into feature_a. Remove feature_b."""
    a = features[feature_a_id]
    b = features[feature_b_id]

    assert a.feature_type == b.feature_type

    merged = Feature(
        feature_id=a.feature_id,
        feature_type=a.feature_type,
        tiles=list(set(a.tiles + b.tiles)),
        meeples=a.meeples + b.meeples,
        is_complete=False,  # Recalculated after
        pennants=a.pennants + b.pennants,
        open_edges=[],  # Recalculated after
    )

    # Recalculate open edges (remove the connecting edge pair)
    all_open = a.open_edges + b.open_edges
    # ... filter out the pair that just connected

    features[a.feature_id] = merged
    del features[b.id]
    return features
```

### 3.3 Feature-to-Tile Mapping

For fast lookup, maintain a reverse mapping:

```python
# In game_data:
{
    "features": { feature_id: Feature },
    "tile_feature_map": {
        "x,y": {
            "meeple_spot_name": "feature_id",
            ...
        }
    }
}
```

This allows O(1) lookup: "what feature does this meeple spot belong to?"

---

## 4. Meeple System

### 4.1 Meeple Inventory

Each player starts with 7 meeples (base game).

```python
# In game_data, per player:
{
    "meeple_supply": { player_id: int },       # Available meeples
    "placed_meeples": [ PlacedMeeple, ... ],   # On the board
}
```

### 4.2 Meeple Placement Rules

A meeple can be placed on the just-placed tile if:
1. The player has at least 1 available meeple
2. The chosen feature on the tile is not already claimed (no meeple on any
   tile in the same connected feature)

```python
def can_place_meeple(
    game_data: dict,
    player_id: PlayerId,
    position: str,
    meeple_spot: str,
) -> bool:
    """Check if a meeple can be placed on this spot."""
    # Player has meeples?
    if game_data["meeple_supply"][player_id] <= 0:
        return False

    # Feature already claimed?
    feature_id = game_data["tile_feature_map"][position][meeple_spot]
    feature = game_data["features"][feature_id]
    if feature.meeples:
        return False  # Someone already has a meeple on this feature

    return True
```

### 4.3 Meeple Return on Scoring

When a feature is completed, all meeples on it are returned to their owners:

```python
def return_meeples(game_data: dict, feature: Feature) -> list[Event]:
    """Return meeples from a completed feature and generate events."""
    events = []
    for meeple in feature.meeples:
        game_data["meeple_supply"][meeple.player_id] += 1
        events.append(Event(
            event_type="meeple_returned",
            player_id=meeple.player_id,
            payload={"position": meeple.position, "spot": meeple.spot},
        ))
    feature.meeples = []
    return events
```

---

## 5. Scoring

### 5.1 During-Game Scoring (Completed Features)

```python
def score_completed_feature(feature: Feature) -> dict[PlayerId, int]:
    """
    Score a completed feature and determine who gets points.

    Returns dict of player_id → points earned.
    If tied (same number of meeples), all tied players get full points.
    """
    if not feature.meeples:
        return {}

    # Count meeples per player
    meeple_counts: dict[PlayerId, int] = {}
    for m in feature.meeples:
        meeple_counts[m.player_id] = meeple_counts.get(m.player_id, 0) + 1

    max_count = max(meeple_counts.values())
    winners = [pid for pid, count in meeple_counts.items() if count == max_count]

    # Calculate points
    if feature.feature_type == FeatureType.CITY:
        points = len(feature.tiles) * 2 + feature.pennants * 2
    elif feature.feature_type == FeatureType.ROAD:
        points = len(feature.tiles)
    elif feature.feature_type == FeatureType.MONASTERY:
        points = 9  # Always 9 when complete (tile + 8 neighbors)
    else:
        return {}  # Fields scored at end only

    return {pid: points for pid in winners}
```

### 5.2 End-Game Scoring

At game end, score:
1. **Incomplete cities**: 1 point per tile + 1 per pennant (half the complete rate)
2. **Incomplete roads**: 1 point per tile
3. **Incomplete monasteries**: 1 point per tile (self + neighbors present)
4. **Fields**: 3 points per completed city the field touches

```python
def score_end_game(game_data: dict) -> dict[PlayerId, int]:
    """
    Score all incomplete features and fields at game end.
    """
    scores: dict[PlayerId, int] = {}

    for feature in game_data["features"].values():
        if feature.is_complete:
            continue  # Already scored

        if not feature.meeples:
            continue  # No one claims it

        meeple_counts = _count_meeples(feature)
        max_count = max(meeple_counts.values())
        winners = [pid for pid, c in meeple_counts.items() if c == max_count]

        if feature.feature_type == FeatureType.CITY:
            points = len(feature.tiles) + feature.pennants
        elif feature.feature_type == FeatureType.ROAD:
            points = len(feature.tiles)
        elif feature.feature_type == FeatureType.MONASTERY:
            # Count surrounding tiles
            pos = feature.tiles[0]  # Monastery is always 1 tile
            neighbors_present = _count_neighbors(game_data, pos)
            points = 1 + neighbors_present
        elif feature.feature_type == FeatureType.FIELD:
            # 3 points per completed city adjacent to this field
            adjacent_cities = _get_adjacent_completed_cities(game_data, feature)
            points = len(adjacent_cities) * 3
        else:
            continue

        for pid in winners:
            scores[pid] = scores.get(pid, 0) + points

    return scores
```

### 5.3 Field Scoring (The Tricky Part)

Fields are the most complex scoring in Carcassonne. A field is a contiguous
region of grass that borders one or more cities. At end-game, the player(s)
with the most farmers (meeples on fields) in a field score 3 points per
completed city that the field touches.

The tricky part: determining which cities a field "touches." This requires
tracking field-to-city adjacency:

```python
def _get_adjacent_completed_cities(
    game_data: dict, field: Feature
) -> list[str]:
    """
    Find all completed cities that border this field.

    A field borders a city if they share a tile AND the field and city
    segments are adjacent on that tile (not separated by a road).
    """
    adjacent_city_ids = set()

    for tile_pos in field.tiles:
        tile_features = game_data["tile_feature_map"][tile_pos]
        # Find city features on the same tile
        for spot, fid in tile_features.items():
            f = game_data["features"][fid]
            if f.feature_type == FeatureType.CITY and f.is_complete:
                # Check adjacency within the tile
                if _field_touches_city_on_tile(game_data, tile_pos, field.feature_id, fid):
                    adjacent_city_ids.add(fid)

    return list(adjacent_city_ids)
```

Field adjacency is determined by the tile's internal geometry — each tile
definition must specify which field segments are adjacent to which city
segments. This is encoded in the tile catalog.

---

## 6. Phases and Actions

### 6.1 Phase Flow

```
Game start:
  → "setup" (auto_resolve): place starting tile, shuffle bag
  → "draw_tile" (auto_resolve): draw tile for player 0
  → "place_tile" (sequential): player 0 places tile
  → "place_meeple" (sequential): player 0 optionally places meeple
  → "score_check" (auto_resolve): check/score completed features
  → "draw_tile" (auto_resolve): draw tile for player 1
  → ... (cycle through players)
  → "end_game_scoring" (auto_resolve): when bag is empty after last score_check
  → game_over
```

### 6.2 Action Types

```python
# place_tile action
{
    "action_type": "place_tile",
    "player_id": "player-1",
    "payload": {
        "x": 3,
        "y": -1,
        "rotation": 90     # 0, 90, 180, 270
    }
}

# place_meeple action
{
    "action_type": "place_meeple",
    "player_id": "player-1",
    "payload": {
        "meeple_spot": "city_N"    # Named spot on the tile
    }
}

# skip_meeple action (player chooses not to place)
{
    "action_type": "place_meeple",
    "player_id": "player-1",
    "payload": {
        "skip": true
    }
}
```

### 6.3 Valid Action Generation

```python
def get_valid_actions(
    self, game_data: dict, phase: Phase, player_id: PlayerId
) -> list[dict]:
    if phase.name == "place_tile":
        current_tile = game_data["current_tile"]
        valid_placements = []
        for pos in game_data["board"]["open_positions"]:
            for rotation in [0, 90, 180, 270]:
                if _can_place_tile(game_data, current_tile, pos, rotation):
                    valid_placements.append({
                        "x": _parse_x(pos),
                        "y": _parse_y(pos),
                        "rotation": rotation,
                    })
        return valid_placements

    elif phase.name == "place_meeple":
        last_placed = game_data["last_placed_position"]
        tile_def = _get_tile_def(game_data, last_placed)
        valid_spots = []
        for spot in tile_def.meeple_spots:
            if can_place_meeple(game_data, player_id, last_placed, spot):
                valid_spots.append({"meeple_spot": spot})
        valid_spots.append({"skip": True})  # Always can skip
        return valid_spots

    return []
```

---

## 7. CarcassonnePlugin Implementation

```python
class CarcassonnePlugin:
    game_id = GameId("carcassonne")
    display_name = "Carcassonne"
    min_players = 2
    max_players = 5
    description = "Build a medieval landscape by placing tiles and claiming features with meeples."
    config_schema = {
        "type": "object",
        "properties": {
            "expansions": {
                "type": "array",
                "items": {"type": "string", "enum": ["inns_and_cathedrals", "traders_and_builders"]},
                "default": [],
            },
        },
    }

    def create_initial_state(
        self, players: list[Player], config: GameConfig
    ) -> tuple[dict, Phase, list[Event]]:
        import random
        rng = random.Random(config.random_seed)

        # Build tile bag (exclude starting tile)
        tile_bag = _build_tile_bag(config.options.get("expansions", []))
        rng.shuffle(tile_bag)

        # Place starting tile
        starting_tile = "D"  # The classic Carcassonne starting tile
        board = {
            "tiles": {
                "0,0": {
                    "tile_type_id": starting_tile,
                    "position": {"x": 0, "y": 0},
                    "rotation": 0,
                }
            },
            "open_positions": ["0,1", "1,0", "0,-1", "-1,0"],
        }

        # Initialize features from starting tile
        features, tile_feature_map = _initialize_features_from_tile(
            starting_tile, "0,0", rotation=0
        )

        game_data = {
            "board": board,
            "tile_bag": tile_bag,
            "current_tile": None,
            "last_placed_position": None,
            "features": features,
            "tile_feature_map": tile_feature_map,
            "meeple_supply": {p.player_id: 7 for p in players},
            "current_player_index": 0,
            "rng_state": rng.getstate(),  # For deterministic replay
        }

        # First phase: draw a tile for player 0
        first_phase = Phase(
            name="draw_tile",
            auto_resolve=True,
            metadata={"player_index": 0},
        )

        events = [
            Event(event_type="game_started", payload={"players": [p.player_id for p in players]}),
            Event(event_type="starting_tile_placed", payload={"tile": starting_tile, "position": "0,0"}),
        ]

        return game_data, first_phase, events

    def apply_action(
        self, game_data: dict, phase: Phase, action: Action, players: list[Player]
    ) -> TransitionResult:

        if phase.name == "draw_tile":
            return self._draw_tile(game_data, phase, players)
        elif phase.name == "place_tile":
            return self._place_tile(game_data, phase, action, players)
        elif phase.name == "place_meeple":
            return self._place_meeple(game_data, phase, action, players)
        elif phase.name == "score_check":
            return self._score_check(game_data, phase, players)
        elif phase.name == "end_game_scoring":
            return self._end_game_scoring(game_data, phase, players)
        else:
            raise ValueError(f"Unknown phase: {phase.name}")

    def _draw_tile(
        self, game_data: dict, phase: Phase, players: list[Player]
    ) -> TransitionResult:
        """Auto-resolve: draw a tile from the bag for the current player."""
        tile_bag = game_data["tile_bag"]

        if not tile_bag:
            # No tiles left → end game scoring
            return TransitionResult(
                game_data=game_data,
                events=[Event(event_type="tile_bag_empty", payload={})],
                next_phase=Phase(name="end_game_scoring", auto_resolve=True),
                scores=game_data.get("scores", {}),
            )

        drawn_tile = tile_bag.pop(0)
        player_index = phase.metadata["player_index"]
        player = players[player_index]

        # Check if this tile can be placed ANYWHERE. If not, discard and draw again.
        # (Extremely rare in base game but possible.)
        if not _tile_has_valid_placement(game_data, drawn_tile):
            events = [Event(
                event_type="tile_discarded",
                player_id=player.player_id,
                payload={"tile": drawn_tile, "reason": "no_valid_placement"},
            )]
            game_data["tile_bag"] = tile_bag
            # Draw again (same player)
            return TransitionResult(
                game_data=game_data,
                events=events,
                next_phase=Phase(name="draw_tile", auto_resolve=True, metadata={"player_index": player_index}),
                scores=game_data.get("scores", {}),
            )

        game_data["current_tile"] = drawn_tile
        game_data["tile_bag"] = tile_bag

        events = [Event(
            event_type="tile_drawn",
            player_id=player.player_id,
            payload={"tile": drawn_tile, "tiles_remaining": len(tile_bag)},
        )]

        next_phase = Phase(
            name="place_tile",
            concurrent_mode=ConcurrentMode.SEQUENTIAL,
            expected_actions=[ExpectedAction(
                player_id=player.player_id,
                action_type="place_tile",
            )],
            metadata={"player_index": player_index},
        )

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=next_phase,
            scores=game_data.get("scores", {}),
        )

    def _place_tile(
        self, game_data: dict, phase: Phase, action: Action, players: list[Player]
    ) -> TransitionResult:
        """Player places their drawn tile on the board."""
        x = action.payload["x"]
        y = action.payload["y"]
        rotation = action.payload["rotation"]
        pos = f"{x},{y}"
        tile_type_id = game_data["current_tile"]
        player_index = phase.metadata["player_index"]
        player = players[player_index]

        # Place tile on board
        game_data["board"]["tiles"][pos] = {
            "tile_type_id": tile_type_id,
            "position": {"x": x, "y": y},
            "rotation": rotation,
        }
        game_data["board"]["open_positions"] = _recalculate_open_positions(game_data["board"])
        game_data["last_placed_position"] = pos
        game_data["current_tile"] = None

        # Create features for the new tile and merge with adjacent
        events = _create_and_merge_features(game_data, tile_type_id, pos, rotation)

        events.insert(0, Event(
            event_type="tile_placed",
            player_id=player.player_id,
            payload={"tile": tile_type_id, "x": x, "y": y, "rotation": rotation},
        ))

        # Next: optionally place meeple
        next_phase = Phase(
            name="place_meeple",
            concurrent_mode=ConcurrentMode.SEQUENTIAL,
            expected_actions=[ExpectedAction(
                player_id=player.player_id,
                action_type="place_meeple",
            )],
            metadata={"player_index": player_index},
        )

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=next_phase,
            scores=game_data.get("scores", {}),
        )

    def _place_meeple(
        self, game_data: dict, phase: Phase, action: Action, players: list[Player]
    ) -> TransitionResult:
        """Player places (or skips placing) a meeple."""
        player_index = phase.metadata["player_index"]
        player = players[player_index]
        events = []

        if not action.payload.get("skip"):
            spot = action.payload["meeple_spot"]
            pos = game_data["last_placed_position"]
            feature_id = game_data["tile_feature_map"][pos][spot]

            # Place meeple
            game_data["meeple_supply"][player.player_id] -= 1
            game_data["features"][feature_id]["meeples"].append({
                "player_id": player.player_id,
                "position": pos,
                "spot": spot,
            })

            events.append(Event(
                event_type="meeple_placed",
                player_id=player.player_id,
                payload={"position": pos, "spot": spot, "feature_id": feature_id},
            ))
        else:
            events.append(Event(
                event_type="meeple_skipped",
                player_id=player.player_id,
                payload={},
            ))

        # Next: check scoring
        next_phase = Phase(
            name="score_check",
            auto_resolve=True,
            metadata={"player_index": player_index},
        )

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=next_phase,
            scores=game_data.get("scores", {}),
        )

    def _score_check(
        self, game_data: dict, phase: Phase, players: list[Player]
    ) -> TransitionResult:
        """Auto-resolve: check for and score completed features."""
        events = []
        scores = dict(game_data.get("scores", {}))

        # Check all features that include the last placed tile
        last_pos = game_data["last_placed_position"]
        checked_features = set()

        for spot, feature_id in game_data["tile_feature_map"].get(last_pos, {}).items():
            if feature_id in checked_features:
                continue
            checked_features.add(feature_id)

            feature = game_data["features"][feature_id]
            if not _is_feature_complete(game_data, feature):
                continue

            # Score it
            feature["is_complete"] = True
            point_awards = score_completed_feature(feature)

            for pid, points in point_awards.items():
                scores[pid] = scores.get(pid, 0) + points
                events.append(Event(
                    event_type="feature_scored",
                    player_id=pid,
                    payload={
                        "feature_id": feature_id,
                        "feature_type": feature["feature_type"],
                        "points": points,
                        "tiles": feature["tiles"],
                    },
                ))

            # Return meeples
            meeple_events = return_meeples(game_data, feature)
            events.extend(meeple_events)

        # Also check monasteries near the last placed tile
        monastery_events, monastery_scores = _check_monastery_completion(game_data, last_pos)
        events.extend(monastery_events)
        for pid, points in monastery_scores.items():
            scores[pid] = scores.get(pid, 0) + points

        game_data["scores"] = scores

        # Next player
        player_index = phase.metadata["player_index"]
        next_player_index = (player_index + 1) % len(players)

        next_phase = Phase(
            name="draw_tile",
            auto_resolve=True,
            metadata={"player_index": next_player_index},
        )

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=next_phase,
            scores=scores,
        )

    def _end_game_scoring(
        self, game_data: dict, phase: Phase, players: list[Player]
    ) -> TransitionResult:
        """Score all incomplete features and fields."""
        events = []
        scores = dict(game_data.get("scores", {}))

        end_scores = score_end_game(game_data)
        for pid, points in end_scores.items():
            scores[pid] = scores.get(pid, 0) + points
            events.append(Event(
                event_type="end_game_points",
                player_id=pid,
                payload={"points": points},
            ))

        game_data["scores"] = scores

        # Determine winner
        max_score = max(scores.values()) if scores else 0
        winners = [pid for pid, s in scores.items() if s == max_score]

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=Phase(name="game_over", auto_resolve=True),
            scores=scores,
            game_over=GameResult(
                winners=winners,
                final_scores=scores,
                reason="normal",
            ),
        )

    # --- View filtering ---

    def get_player_view(
        self, game_data: dict, phase: Phase, player_id: PlayerId | None, players: list[Player]
    ) -> dict:
        """
        Carcassonne is mostly open information. Hidden:
        - Tile bag contents (show count only)
        - Drawn tile is visible to all once drawn

        For spectators: same view as players.
        """
        return {
            "board": game_data["board"],
            "features": game_data["features"],
            "current_tile": game_data["current_tile"],  # Visible to all
            "tiles_remaining": len(game_data["tile_bag"]),  # Count only, not contents
            "meeple_supply": game_data["meeple_supply"],
            "scores": game_data.get("scores", {}),
            "last_placed_position": game_data["last_placed_position"],
        }

    # --- Concurrent play: not used in Carcassonne ---

    def get_concurrent_action_mode(self, state) -> ConcurrentMode:
        return ConcurrentMode.SEQUENTIAL

    def resolve_concurrent_actions(self, *args):
        raise NotImplementedError("Carcassonne is sequential only")

    # --- AI ---

    def state_to_ai_view(
        self, game_data: dict, phase: Phase, player_id: PlayerId, players: list[Player]
    ) -> dict:
        """Structured view for bots."""
        view = self.get_player_view(game_data, phase, player_id, players)
        valid = self.get_valid_actions(game_data, phase, player_id)
        view["valid_actions"] = valid
        view["my_meeples"] = game_data["meeple_supply"].get(player_id, 0)
        return view

    def parse_ai_action(self, response: dict, phase: Phase, player_id: PlayerId) -> Action:
        return Action(
            action_type=phase.expected_actions[0].action_type if phase.expected_actions else phase.name,
            player_id=player_id,
            payload=response.get("action", {}).get("payload", response),
        )
```

---

## 8. Walkthrough: 3-Player Game (5 Turns)

Players: Alice (seat 0), Bob (seat 1), Carol (seat 2).
Starting tile: D (city N, road E-W) at (0,0).

### Turn 1: Alice

```
Phase: draw_tile (auto) → draws tile "V" (city N-W corner, field S-E)
Phase: place_tile → Alice places at (-1, 0), rotation 90
  - City edge matches (0,0) West edge? Let's say yes after rotation.
  - Board now: (0,0)=D, (-1,0)=V(r90)
Phase: place_meeple → Alice places meeple on city_NW feature
  - Alice meeples: 7 → 6
Phase: score_check (auto) → city not complete (still has open edges)
  - No scoring

Events:
  1. tile_drawn { tile: "V", tiles_remaining: 70 }
  2. tile_placed { tile: "V", x: -1, y: 0, rotation: 90 }
  3. feature_merged { features: ["feat-city-1", "feat-city-2"] → "feat-city-1" }
  4. meeple_placed { position: "-1,0", spot: "city_NW", feature: "feat-city-1" }
```

### Turn 2: Bob

```
Phase: draw_tile (auto) → draws tile "U" (road N-S, field E-W)
Phase: place_tile → Bob places at (0, -1), rotation 0
  - South of starting tile. Road connects to (0,0) south edge? (0,0) has field S.
  - Actually, (0,0) has road E-W, not S. So Bob places to connect road at (1,0).
  Let's fix: Bob places at (1, 0), rotation 0
  - Road connects to (0,0) East road edge
Phase: place_meeple → Bob places meeple on road feature
  - Bob meeples: 7 → 6
Phase: score_check (auto) → road not complete

Events:
  1. tile_drawn { tile: "U", tiles_remaining: 69 }
  2. tile_placed { tile: "U", x: 1, y: 0, rotation: 0 }
  3. meeple_placed { position: "1,0", spot: "road_NS", feature: "feat-road-1" }
```

### Turn 3: Carol

```
Phase: draw_tile (auto) → draws tile "B" (monastery, all field edges)
Phase: place_tile → Carol places at (0, 1), rotation 0
  - North of starting tile. Field edges match city edge of (0,0)? NO.
  - (0,0) has city N. Carol needs a tile with city on its south edge.
  Let's say Carol drew tile "E" (city S, field N-E-W) instead.
  Carol places at (0, 1), rotation 0 → city S matches (0,0) city N
Phase: place_meeple → Carol skips (the city is already claimed by Alice)
Phase: score_check (auto) → check if city completed: (0,0) city N + (0,1) city S
  - Is it complete? Only if all open edges are closed. The merged city now
    includes Alice's tiles too. Let's say it's not yet complete (still open edges).

Events:
  1. tile_drawn { tile: "E", tiles_remaining: 68 }
  2. tile_placed { tile: "E", x: 0, y: 1, rotation: 0 }
  3. feature_merged { features: [...] }
  4. meeple_skipped {}
```

### Turn 4: Alice (again)

```
Phase: draw_tile (auto) → draws tile "N" (city N, city S — separate cities)
Phase: place_tile → Alice places at (-1, 1) to extend her city
Phase: place_meeple → Alice skips (already has meeple on this city)
Phase: score_check → city now complete (all edges closed)!
  - Score: 4 tiles × 2 = 8 points + pennants
  - Alice gets 8 points (she has the only meeple)
  - Alice's meeple is returned. Alice meeples: 6 → 7

Events:
  1. tile_drawn { tile: "N", tiles_remaining: 67 }
  2. tile_placed { tile: "N", x: -1, y: 1, rotation: 0 }
  3. meeple_skipped {}
  4. feature_scored { feature_type: "city", points: 8, player: "alice" }
  5. meeple_returned { player: "alice", position: "-1,0", spot: "city_NW" }
  6. score_updated { alice: 8, bob: 0, carol: 0 }
```

### Turn 5: Bob

```
Phase: draw_tile (auto) → draws tile "A" (monastery with road S)
Phase: place_tile → Bob places at (2, 0), rotation 270
  - Road connects to his existing road
Phase: place_meeple → Bob places meeple on monastery
  - Bob meeples: 6 → 5
Phase: score_check → road not complete, monastery surrounded? No (needs 8 neighbors)

Events:
  1. tile_drawn { tile: "A", tiles_remaining: 66 }
  2. tile_placed { tile: "A", x: 2, y: 0, rotation: 270 }
  3. meeple_placed { position: "2,0", spot: "monastery", feature: "feat-mon-1" }
```

**Walkthrough validates**: The phase flow, feature merging, meeple placement
rules, scoring, and event generation all work correctly with the engine model.

---

## 9. Edge Cases

### 9.1 No Valid Placement for Drawn Tile

Extremely rare but possible. The tile is discarded and another is drawn.
Handled in `_draw_tile` — if no valid placement exists, discard and re-enter
draw_tile phase.

### 9.2 Player Has No Meeples

Player can still place tiles, just can't place meeples. The `place_meeple`
phase still runs (they must explicitly skip). `get_valid_actions` returns
only `[{"skip": True}]`.

### 9.3 Tile That Can Only Be Placed One Way

`get_valid_actions` for `place_tile` may return only 1 option. Player still
must confirm it (no auto-play for humans; bots can auto-select).

### 9.4 Feature Shared by 3+ Tiles Merging at Once

A single tile placement can merge multiple disconnected features. The merge
algorithm handles this by iterating all 4 edges and merging sequentially.
After each merge, feature IDs are updated, so subsequent merges reference
the correct (already-merged) feature.

### 9.5 Two Players Tied on a Feature

Both get full points. This is standard Carcassonne rules and handled by
`score_completed_feature` returning points for all tied players.

### 9.6 Forced Pass on Timeout

If a player times out during `place_tile`, the engine applies a random valid
placement (TimeoutBehavior.RANDOM_ACTION is recommended for Carcassonne).
If they time out during `place_meeple`, force a skip.

---

## 10. Frontend Components (Carcassonne-Specific)

### 10.1 Component Tree

```
<CarcassonneGame>
  <BoardView>                    # Main board with zoom/pan
    <TileGrid>                   # Renders placed tiles
      <PlacedTileView />         # Individual tile with rotation
      <MeepleOverlay />          # Meeple icons on tiles
      <OpenPositionMarker />     # Highlights valid placement spots
    </TileGrid>
  </BoardView>
  <GameSidebar>
    <CurrentTilePreview>         # Shows the tile to place, with rotation controls
      <RotateButton />
    </CurrentTilePreview>
    <MeepleInventory />          # Shows each player's remaining meeples
    <ScoreBoard />               # Current scores (reusable primitive)
    <TilesRemainingCounter />
    <TimerDisplay />             # Per-player timer (reusable primitive)
  </GameSidebar>
  <MeeplePlacementOverlay />     # When in place_meeple phase, overlay on last tile
</CarcassonneGame>
```

### 10.2 Board Rendering Strategy

Use **Canvas** (via a library like Pixi.js or raw HTML5 Canvas) for the board:
- Tiles are pre-rendered images
- Meeples are SVG overlays positioned by feature coordinates
- Zoom/pan via standard 2D camera transform
- Highlight valid positions with semi-transparent overlay

DOM rendering is fine for sidebar elements (scores, timer, tile preview).

### 10.3 Tile Art

Each tile type needs a square image (e.g. 200x200px). Tiles are rotated
via CSS/Canvas transform — only one image per tile type needed.

Meeple positions on each tile need pixel coordinates per rotation, stored
in a static mapping:

```typescript
const MEEPLE_POSITIONS: Record<string, Record<string, {x: number, y: number}>> = {
  "tile_D": {
    "city_N":     { x: 100, y: 20 },
    "road_EW":    { x: 100, y: 100 },
    "field_S_left": { x: 60, y: 170 },
    // ... per rotation, or compute from base + rotation transform
  },
  // ...
}
```

---

## 11. AI State Serialization

The AI receives a structured JSON view:

```json
{
  "board": {
    "tiles": {
      "0,0": { "type": "D", "rotation": 0 },
      "1,0": { "type": "U", "rotation": 0 }
    }
  },
  "current_tile": "V",
  "tiles_remaining": 65,
  "scores": { "me": 8, "opponent_1": 0, "opponent_2": 0 },
  "my_meeples": 6,
  "features": [
    {
      "type": "road",
      "tiles": ["0,0", "1,0"],
      "is_complete": false,
      "claimed_by": ["opponent_1"],
      "open_edges": 2
    }
  ],
  "valid_actions": [
    { "x": 0, "y": 1, "rotation": 0 },
    { "x": 0, "y": 1, "rotation": 90 },
    { "x": -1, "y": 1, "rotation": 0 }
  ]
}
```

This gives the bot everything it needs: board state, valid moves, feature
status, and resource counts. The bot responds with its chosen action from
the valid_actions list.

---

## 12. File Structure

> **Note:** The canonical implementation is in Rust. The Python file structure
> below was the original design; see `game-engine/src/games/carcassonne/` for
> the current Rust implementation.

```
game-engine/src/games/carcassonne/
├── mod.rs               # Module exports
├── plugin.rs            # CarcassonnePlugin implementing TypedGamePlugin
├── types.rs             # Carcassonne-specific types (state, tile, feature)
├── tiles.rs             # Complete tile catalog (24 types, 72 tiles)
├── board.rs             # Board state, placement validation, open positions
├── features.rs          # Feature tracking, merging, completion detection
├── scoring.rs           # Scoring logic (during-game + end-game)
├── meeples.rs           # Meeple placement and return logic
└── evaluator.rs         # Heuristic evaluation for MCTS bot AI
```
