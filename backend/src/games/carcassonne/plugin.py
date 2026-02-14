"""CarcassonnePlugin — implements the GamePlugin protocol for Carcassonne."""

from __future__ import annotations

import random
from typing import ClassVar

from src.engine.errors import InvalidActionError
from src.engine.models import (
    Action,
    ConcurrentMode,
    Event,
    ExpectedAction,
    GameConfig,
    GameResult,
    Phase,
    Player,
    PlayerId,
    TransitionResult,
)
from src.games.carcassonne.board import (
    can_place_tile,
    recalculate_open_positions,
    tile_has_valid_placement,
)
from src.games.carcassonne.features import (
    check_monastery_completion,
    create_and_merge_features,
    initialize_features_from_tile,
    is_feature_complete,
)
from src.games.carcassonne.meeples import can_place_meeple, return_meeples
from src.games.carcassonne.scoring import score_completed_feature, score_end_game
from src.games.carcassonne.tiles import (
    STARTING_TILE_ID,
    TILE_LOOKUP,
    build_tile_bag,
    get_rotated_features,
)
from src.games.carcassonne.types import Position


class CarcassonnePlugin:
    """Carcassonne base game implementation."""

    game_id: ClassVar[str] = "carcassonne"
    display_name: ClassVar[str] = "Carcassonne"
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 5
    description: ClassVar[str] = (
        "Build a medieval landscape by placing tiles and claiming features with meeples."
    )
    config_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "expansions": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["inns_and_cathedrals", "traders_and_builders"],
                },
                "default": [],
            },
        },
    }

    # ------------------------------------------------------------------ #
    #  Lifecycle
    # ------------------------------------------------------------------ #

    def create_initial_state(
        self,
        players: list[Player],
        config: GameConfig,
    ) -> tuple[dict, Phase, list[Event]]:
        rng = random.Random(config.random_seed)

        expansions = config.options.get("expansions", [])
        tile_bag = build_tile_bag(expansions if expansions else None)
        rng.shuffle(tile_bag)

        # Place starting tile at (0,0)
        board: dict = {
            "tiles": {
                "0,0": {
                    "tile_type_id": STARTING_TILE_ID,
                    "rotation": 0,
                },
            },
            "open_positions": [],
        }
        board["open_positions"] = recalculate_open_positions(board["tiles"])

        features, tile_feature_map = initialize_features_from_tile(
            STARTING_TILE_ID, "0,0", rotation=0,
        )

        game_data: dict = {
            "board": board,
            "tile_bag": tile_bag,
            "current_tile": None,
            "last_placed_position": None,
            "features": features,
            "tile_feature_map": tile_feature_map,
            "meeple_supply": {p.player_id: 7 for p in players},
            "scores": {p.player_id: 0 for p in players},
            "current_player_index": 0,
            "rng_state": _serialize_rng_state(rng.getstate()),
        }

        first_phase = Phase(
            name="draw_tile",
            auto_resolve=True,
            metadata={"player_index": 0},
        )

        events = [
            Event(
                event_type="game_started",
                payload={"players": [p.player_id for p in players]},
            ),
            Event(
                event_type="starting_tile_placed",
                payload={"tile": STARTING_TILE_ID, "position": "0,0"},
            ),
        ]

        return game_data, first_phase, events

    def validate_config(self, options: dict) -> list[str]:
        errors: list[str] = []
        expansions = options.get("expansions", [])
        valid_expansions = {"inns_and_cathedrals", "traders_and_builders"}
        for exp in expansions:
            if exp not in valid_expansions:
                errors.append(f"Unknown expansion: {exp}")
        return errors

    # ------------------------------------------------------------------ #
    #  Valid actions
    # ------------------------------------------------------------------ #

    def get_valid_actions(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> list[dict]:
        if phase.name == "place_tile":
            return self._get_valid_tile_placements(game_data, player_id)
        elif phase.name == "place_meeple":
            return self._get_valid_meeple_placements(game_data, player_id)
        return []

    def _get_valid_tile_placements(
        self, game_data: dict, player_id: PlayerId,
    ) -> list[dict]:
        current_tile = game_data["current_tile"]
        if current_tile is None:
            return []

        board_tiles = game_data["board"]["tiles"]
        open_positions = game_data["board"]["open_positions"]
        has_meeples = game_data["meeple_supply"].get(player_id, 0) > 0
        placements: list[dict] = []

        for pos_key in open_positions:
            pos = Position.from_key(pos_key)
            for rotation in (0, 90, 180, 270):
                if can_place_tile(board_tiles, current_tile, pos_key, rotation):
                    # Compute approximate meeple spots for this rotation
                    meeple_spots: list[str] = []
                    if has_meeples:
                        rotated_features = get_rotated_features(current_tile, rotation)
                        seen: set[str] = set()
                        for feat in rotated_features:
                            for spot in feat.meeple_spots:
                                if spot not in seen:
                                    seen.add(spot)
                                    meeple_spots.append(spot)

                    placements.append({
                        "x": pos.x,
                        "y": pos.y,
                        "rotation": rotation,
                        "meeple_spots": meeple_spots,
                    })

        return placements

    def _get_valid_meeple_placements(
        self, game_data: dict, player_id: PlayerId,
    ) -> list[dict]:
        last_pos = game_data["last_placed_position"]
        if last_pos is None:
            return [{"skip": True}]

        placed_tile = game_data["board"]["tiles"][last_pos]
        tile_type_id = placed_tile["tile_type_id"]
        rotation = placed_tile["rotation"]

        rotated_features = get_rotated_features(tile_type_id, rotation)
        spots: list[dict] = []
        seen_spots: set[str] = set()

        for tile_feat in rotated_features:
            for spot in tile_feat.meeple_spots:
                if spot in seen_spots:
                    continue
                seen_spots.add(spot)
                if can_place_meeple(game_data, player_id, last_pos, spot):
                    spots.append({"meeple_spot": spot})

        spots.append({"skip": True})
        return spots

    # ------------------------------------------------------------------ #
    #  Validation
    # ------------------------------------------------------------------ #

    def validate_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
    ) -> str | None:
        if phase.name == "place_tile":
            return self._validate_place_tile(game_data, action)
        elif phase.name == "place_meeple":
            return self._validate_place_meeple(game_data, action)
        return None

    def _validate_place_tile(self, game_data: dict, action: Action) -> str | None:
        payload = action.payload
        x = payload.get("x")
        y = payload.get("y")
        rotation = payload.get("rotation")

        if x is None or y is None or rotation is None:
            return "Missing x, y, or rotation in payload"
        if rotation not in (0, 90, 180, 270):
            return f"Invalid rotation: {rotation}"

        pos_key = f"{x},{y}"
        current_tile = game_data["current_tile"]
        if current_tile is None:
            return "No tile drawn"

        board_tiles = game_data["board"]["tiles"]
        if not can_place_tile(board_tiles, current_tile, pos_key, rotation):
            return f"Cannot place tile {current_tile} at {pos_key} with rotation {rotation}"

        return None

    def _validate_place_meeple(self, game_data: dict, action: Action) -> str | None:
        payload = action.payload
        if payload.get("skip"):
            return None

        spot = payload.get("meeple_spot")
        if spot is None:
            return "Missing meeple_spot in payload"

        last_pos = game_data["last_placed_position"]
        if last_pos is None:
            return "No tile was placed this turn"

        if not can_place_meeple(game_data, action.player_id, last_pos, spot):
            return f"Cannot place meeple on spot {spot} at {last_pos}"

        return None

    # ------------------------------------------------------------------ #
    #  Apply action — dispatches to phase handlers
    # ------------------------------------------------------------------ #

    def apply_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
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
            raise InvalidActionError(f"Unknown phase: {phase.name}")

    # ---- draw_tile (auto-resolve) ----

    def _draw_tile(
        self, game_data: dict, phase: Phase, players: list[Player],
    ) -> TransitionResult:
        tile_bag = game_data["tile_bag"]

        if not tile_bag:
            return TransitionResult(
                game_data=game_data,
                events=[Event(event_type="tile_bag_empty")],
                next_phase=Phase(name="end_game_scoring", auto_resolve=True),
                scores=_float_scores(game_data["scores"]),
            )

        # Restore RNG for deterministic draws
        rng = _restore_rng(game_data["rng_state"])
        player_index = phase.metadata["player_index"]
        player = players[player_index]

        drawn_tile = tile_bag.pop(0)

        # Extremely rare: tile cannot be placed anywhere → discard and redraw
        open_positions = game_data["board"]["open_positions"]
        board_tiles = game_data["board"]["tiles"]
        while drawn_tile and not tile_has_valid_placement(
            board_tiles, open_positions, drawn_tile
        ):
            discard_event = Event(
                event_type="tile_discarded",
                player_id=player.player_id,
                payload={"tile": drawn_tile, "reason": "no_valid_placement"},
            )
            if not tile_bag:
                # All remaining tiles unplaceable → end game
                game_data["rng_state"] = _serialize_rng_state(rng.getstate())
                return TransitionResult(
                    game_data=game_data,
                    events=[discard_event, Event(event_type="tile_bag_empty")],
                    next_phase=Phase(name="end_game_scoring", auto_resolve=True),
                    scores=_float_scores(game_data["scores"]),
                )
            drawn_tile = tile_bag.pop(0)

        game_data["current_tile"] = drawn_tile
        game_data["rng_state"] = _serialize_rng_state(rng.getstate())

        events = [
            Event(
                event_type="tile_drawn",
                player_id=player.player_id,
                payload={"tile": drawn_tile, "tiles_remaining": len(tile_bag)},
            ),
        ]

        next_phase = Phase(
            name="place_tile",
            concurrent_mode=ConcurrentMode.SEQUENTIAL,
            expected_actions=[
                ExpectedAction(
                    player_id=player.player_id,
                    action_type="place_tile",
                ),
            ],
            metadata={"player_index": player_index},
        )

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=next_phase,
            scores=_float_scores(game_data["scores"]),
        )

    # ---- place_tile ----

    def _place_tile(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        x = action.payload["x"]
        y = action.payload["y"]
        rotation = action.payload["rotation"]
        pos_key = f"{x},{y}"
        tile_type_id = game_data["current_tile"]
        player_index = phase.metadata["player_index"]
        player = players[player_index]

        # Validate
        error = self._validate_place_tile(game_data, action)
        if error:
            raise InvalidActionError(error, action)

        # Place tile on board
        game_data["board"]["tiles"][pos_key] = {
            "tile_type_id": tile_type_id,
            "rotation": rotation,
        }
        game_data["board"]["open_positions"] = recalculate_open_positions(
            game_data["board"]["tiles"]
        )
        game_data["last_placed_position"] = pos_key
        game_data["current_tile"] = None

        # Create features and merge with adjacent
        merge_events = create_and_merge_features(
            game_data, tile_type_id, pos_key, rotation,
        )

        events = [
            Event(
                event_type="tile_placed",
                player_id=player.player_id,
                payload={
                    "tile": tile_type_id,
                    "x": x,
                    "y": y,
                    "rotation": rotation,
                },
            ),
            *merge_events,
        ]

        next_phase = Phase(
            name="place_meeple",
            concurrent_mode=ConcurrentMode.SEQUENTIAL,
            expected_actions=[
                ExpectedAction(
                    player_id=player.player_id,
                    action_type="place_meeple",
                ),
            ],
            metadata={"player_index": player_index},
        )

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=next_phase,
            scores=_float_scores(game_data["scores"]),
        )

    # ---- place_meeple ----

    def _place_meeple(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        player_index = phase.metadata["player_index"]
        player = players[player_index]
        events: list[Event] = []

        if not action.payload.get("skip"):
            # Validate
            error = self._validate_place_meeple(game_data, action)
            if error:
                raise InvalidActionError(error, action)

            spot = action.payload["meeple_spot"]
            pos = game_data["last_placed_position"]
            feature_id = game_data["tile_feature_map"][pos][spot]

            game_data["meeple_supply"][player.player_id] -= 1
            game_data["features"][feature_id]["meeples"].append({
                "player_id": player.player_id,
                "position": pos,
                "spot": spot,
            })

            events.append(Event(
                event_type="meeple_placed",
                player_id=player.player_id,
                payload={
                    "position": pos,
                    "spot": spot,
                    "feature_id": feature_id,
                },
            ))
        else:
            events.append(Event(
                event_type="meeple_skipped",
                player_id=player.player_id,
            ))

        next_phase = Phase(
            name="score_check",
            auto_resolve=True,
            metadata={"player_index": player_index},
        )

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=next_phase,
            scores=_float_scores(game_data["scores"]),
        )

    # ---- score_check (auto-resolve) ----

    def _score_check(
        self, game_data: dict, phase: Phase, players: list[Player],
    ) -> TransitionResult:
        events: list[Event] = []
        scores = dict(game_data["scores"])

        last_pos = game_data["last_placed_position"]
        checked_features: set[str] = set()

        # Check features on the placed tile for completion
        for spot, feature_id in game_data["tile_feature_map"].get(last_pos, {}).items():
            if feature_id in checked_features:
                continue
            checked_features.add(feature_id)

            feature = game_data["features"].get(feature_id)
            if feature is None:
                continue
            if feature.get("is_complete"):
                continue
            if not is_feature_complete(game_data, feature):
                continue

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

            meeple_events = return_meeples(game_data, feature)
            events.extend(meeple_events)

        # Check monasteries near the placed tile
        monastery_events, monastery_scores = check_monastery_completion(
            game_data, last_pos,
        )
        events.extend(monastery_events)
        for pid, points in monastery_scores.items():
            scores[pid] = scores.get(pid, 0) + points

        game_data["scores"] = scores

        # Advance to next player
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
            scores=_float_scores(scores),
        )

    # ---- end_game_scoring (auto-resolve) ----

    def _end_game_scoring(
        self, game_data: dict, phase: Phase, players: list[Player],
    ) -> TransitionResult:
        events: list[Event] = []
        scores = dict(game_data["scores"])

        end_scores = score_end_game(game_data)
        for pid, points in end_scores.items():
            scores[pid] = scores.get(pid, 0) + points
            events.append(Event(
                event_type="end_game_points",
                player_id=pid,
                payload={"points": points},
            ))

        game_data["scores"] = scores

        max_score = max(scores.values()) if scores else 0
        winners = [pid for pid, s in scores.items() if s == max_score]

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=Phase(name="game_over"),
            scores=_float_scores(scores),
            game_over=GameResult(
                winners=winners,
                final_scores=_float_scores(scores),
                reason="normal",
            ),
        )

    # ------------------------------------------------------------------ #
    #  Views
    # ------------------------------------------------------------------ #

    def get_player_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId | None,
        players: list[Player],
    ) -> dict:
        return {
            "board": game_data["board"],
            "features": game_data["features"],
            "current_tile": game_data["current_tile"],
            "tiles_remaining": len(game_data["tile_bag"]),
            "meeple_supply": game_data["meeple_supply"],
            "scores": game_data["scores"],
            "last_placed_position": game_data["last_placed_position"],
        }

    def get_spectator_summary(
        self,
        game_data: dict,
        phase: Phase,
        players: list[Player],
    ) -> dict:
        return self.get_player_view(game_data, phase, None, players)

    # ------------------------------------------------------------------ #
    #  Concurrent (not used — Carcassonne is sequential)
    # ------------------------------------------------------------------ #

    def resolve_concurrent_actions(
        self,
        game_data: dict,
        phase: Phase,
        actions: dict[str, Action],
        players: list[Player],
    ) -> TransitionResult:
        raise NotImplementedError("Carcassonne is sequential only")

    # ------------------------------------------------------------------ #
    #  AI interface
    # ------------------------------------------------------------------ #

    def state_to_ai_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> dict:
        view = self.get_player_view(game_data, phase, player_id, players)
        view["valid_actions"] = self.get_valid_actions(game_data, phase, player_id)
        view["my_meeples"] = game_data["meeple_supply"].get(player_id, 0)
        return view

    def parse_ai_action(
        self,
        response: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> Action:
        action_type = (
            phase.expected_actions[0].action_type
            if phase.expected_actions
            else phase.name
        )
        payload = response.get("action", {}).get("payload", response)
        return Action(
            action_type=action_type,
            player_id=player_id,
            payload=payload,
        )

    def on_player_disconnect(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> dict | None:
        return None


# ------------------------------------------------------------------ #
#  Helpers
# ------------------------------------------------------------------ #

def _float_scores(scores: dict[str, int | float]) -> dict[str, float]:
    """Convert int scores to float for TransitionResult compatibility."""
    return {k: float(v) for k, v in scores.items()}


def _serialize_rng_state(state: tuple) -> list:
    """Convert random.Random.getstate() to a JSON-serializable list."""
    version, internalstate, gauss_next = state
    return [version, list(internalstate), gauss_next]


def _restore_rng(serialized: list) -> random.Random:
    """Restore a random.Random from serialized state."""
    version, internalstate, gauss_next = serialized
    rng = random.Random()
    rng.setstate((version, tuple(internalstate), gauss_next))
    return rng
