"""EinsteinDojoPlugin — implements the GamePlugin protocol for Ein Stein Dojo."""

from __future__ import annotations

from typing import ClassVar

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
from src.games.einstein_dojo.board import (
    apply_placement,
    create_empty_board,
    get_all_valid_placements,
    validate_placement,
)
from src.games.einstein_dojo.scoring import count_complete_hexes

TILES_PER_PLAYER = 16


class EinsteinDojoPlugin:
    """Ein Stein Dojo — abstract strategy game with Einstein hat tiles."""

    game_id: ClassVar[str] = "einstein_dojo"
    display_name: ClassVar[str] = "Ein Stein Dojo"
    min_players: ClassVar[int] = 2
    max_players: ClassVar[int] = 2
    description: ClassVar[str] = (
        "Place Einstein hat tiles on a hexagonal board to complete hexagons. "
        "A 2-player abstract strategy game."
    )
    config_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {},
    }
    disconnect_policy: ClassVar[str] = "forfeit_player"

    # ── Lifecycle ──

    def create_initial_state(
        self,
        players: list[Player],
        config: GameConfig,
    ) -> tuple[dict, Phase, list[Event]]:
        game_data: dict = {
            "board": create_empty_board(),
            "tiles_remaining": {p.player_id: TILES_PER_PLAYER for p in players},
            "scores": {p.player_id: 0 for p in players},
            "current_player_index": 0,
        }

        first_player = players[0]
        first_phase = Phase(
            name="place_tile",
            concurrent_mode=ConcurrentMode.SEQUENTIAL,
            expected_actions=[
                ExpectedAction(
                    player_id=first_player.player_id,
                    action_type="place_tile",
                ),
            ],
            auto_resolve=False,
            metadata={"player_index": 0},
        )

        events = [
            Event(event_type="game_started", payload={
                "players": [p.player_id for p in players],
                "tiles_per_player": TILES_PER_PLAYER,
            }),
        ]

        return game_data, first_phase, events

    def validate_config(self, options: dict) -> list[str]:
        return []

    # ── Core game loop ──

    def get_valid_actions(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
    ) -> list[dict]:
        if phase.name != "place_tile":
            return []

        expected_pid = phase.expected_actions[0].player_id if phase.expected_actions else None
        if player_id != expected_pid:
            return []

        if game_data["tiles_remaining"].get(player_id, 0) <= 0:
            return []

        return get_all_valid_placements(game_data["board"], player_id)

    def validate_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
    ) -> str | None:
        if phase.name == "place_tile":
            return self._validate_place_tile(game_data, action)
        return None

    def apply_action(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        if phase.name == "place_tile":
            return self._apply_place_tile(game_data, phase, action, players)

        if phase.name == "score_check":
            return self._apply_score_check(game_data, phase, action, players)

        raise ValueError(f"Unknown phase: {phase.name}")

    # ── View filtering ──

    def get_player_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId | None,
        players: list[Player],
    ) -> dict:
        # No hidden info — return everything
        return {
            "board": game_data["board"],
            "tiles_remaining": game_data["tiles_remaining"],
            "scores": game_data["scores"],
            "current_player_index": game_data["current_player_index"],
        }

    # ── Concurrent play (not used) ──

    def resolve_concurrent_actions(
        self,
        game_data: dict,
        phase: Phase,
        actions: dict[str, Action],
        players: list[Player],
    ) -> TransitionResult:
        raise NotImplementedError("Ein Stein Dojo is sequential only")

    # ── AI interface ──

    def state_to_ai_view(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> dict:
        view = self.get_player_view(game_data, phase, player_id, players)
        view["valid_actions"] = self.get_valid_actions(game_data, phase, player_id)
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
        return Action(action_type=action_type, player_id=player_id, payload=payload)

    # ── Forfeit handling ──

    def on_player_forfeit(
        self,
        game_data: dict,
        phase: Phase,
        player_id: PlayerId,
        players: list[Player],
    ) -> TransitionResult | None:
        if phase.name != "place_tile":
            return None

        # Skip the forfeited player's turn
        current_idx = game_data["current_player_index"]
        next_idx = (current_idx + 1) % len(players)
        game_data["current_player_index"] = next_idx

        next_player = players[next_idx]
        return TransitionResult(
            game_data=game_data,
            events=[Event(event_type="turn_skipped", player_id=player_id, payload={})],
            next_phase=Phase(
                name="place_tile",
                concurrent_mode=ConcurrentMode.SEQUENTIAL,
                expected_actions=[
                    ExpectedAction(
                        player_id=next_player.player_id,
                        action_type="place_tile",
                    ),
                ],
                auto_resolve=False,
                metadata={"player_index": next_idx},
            ),
            scores=game_data["scores"],
            game_over=None,
        )

    def get_spectator_summary(
        self,
        game_data: dict,
        phase: Phase,
        players: list[Player],
    ) -> dict:
        return {
            "scores": game_data["scores"],
            "tiles_remaining": game_data["tiles_remaining"],
            "pieces_placed": len(game_data["board"]["placed_pieces"]),
        }

    # ── Private handlers ──

    def _validate_place_tile(self, game_data: dict, action: Action) -> str | None:
        payload = action.payload
        anchor_q = payload.get("anchor_q")
        anchor_r = payload.get("anchor_r")
        orientation = payload.get("orientation")

        if anchor_q is None or anchor_r is None or orientation is None:
            return "Missing anchor_q, anchor_r, or orientation in payload"

        if not isinstance(orientation, int):
            return "orientation must be an integer"

        player_id = action.player_id
        if game_data["tiles_remaining"].get(player_id, 0) <= 0:
            return "No tiles remaining"

        return validate_placement(
            game_data["board"], player_id, orientation, anchor_q, anchor_r,
        )

    def _apply_place_tile(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        payload = action.payload
        anchor_q = payload["anchor_q"]
        anchor_r = payload["anchor_r"]
        orientation = payload["orientation"]
        player_id = action.player_id

        # Place the tile
        changed_hexes = apply_placement(
            game_data["board"], player_id, orientation, anchor_q, anchor_r,
        )

        # Decrement tile count
        game_data["tiles_remaining"][player_id] -= 1

        events = [
            Event(
                event_type="tile_placed",
                player_id=player_id,
                payload={
                    "anchor_q": anchor_q,
                    "anchor_r": anchor_r,
                    "orientation": orientation,
                    "changed_hexes": changed_hexes,
                },
            ),
        ]

        # Transition to score_check (auto-resolve)
        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=Phase(
                name="score_check",
                auto_resolve=True,
                metadata={"player_index": game_data["current_player_index"]},
            ),
            scores=game_data["scores"],
            game_over=None,
        )

    def _apply_score_check(
        self,
        game_data: dict,
        phase: Phase,
        action: Action,
        players: list[Player],
    ) -> TransitionResult:
        # Recalculate scores
        complete_counts = count_complete_hexes(game_data["board"])
        for player in players:
            game_data["scores"][player.player_id] = complete_counts.get(player.player_id, 0)

        events: list[Event] = []

        current_idx = game_data["current_player_index"]
        current_player = players[current_idx]

        # Check game end: current player used their last tile
        if game_data["tiles_remaining"][current_player.player_id] <= 0:
            return self._end_game(game_data, events, players)

        # Advance to next player
        next_idx = (current_idx + 1) % len(players)
        next_player = players[next_idx]
        game_data["current_player_index"] = next_idx

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=Phase(
                name="place_tile",
                concurrent_mode=ConcurrentMode.SEQUENTIAL,
                expected_actions=[
                    ExpectedAction(
                        player_id=next_player.player_id,
                        action_type="place_tile",
                    ),
                ],
                auto_resolve=False,
                metadata={"player_index": next_idx},
            ),
            scores=game_data["scores"],
            game_over=None,
        )

    def _end_game(
        self,
        game_data: dict,
        events: list[Event],
        players: list[Player],
    ) -> TransitionResult:
        scores = game_data["scores"]
        sorted_players = sorted(
            players,
            key=lambda p: scores.get(p.player_id, 0),
            reverse=True,
        )

        # Tiebreaker: player 2 (seat_index=1) wins ties
        top_score = scores.get(sorted_players[0].player_id, 0)
        winners = [p for p in sorted_players if scores.get(p.player_id, 0) == top_score]

        if len(winners) > 1:
            # Tie — player who went second (seat_index=1) wins
            winners = [p for p in winners if p.seat_index == 1]

        events.append(Event(
            event_type="game_ended",
            payload={
                "final_scores": {p.player_id: scores.get(p.player_id, 0) for p in players},
                "winners": [w.player_id for w in winners],
            },
        ))

        return TransitionResult(
            game_data=game_data,
            events=events,
            next_phase=Phase(name="game_over", auto_resolve=False),
            scores=scores,
            game_over=GameResult(
                winners=[w.player_id for w in winners],
                final_scores={p.player_id: scores.get(p.player_id, 0) for p in players},
                reason="normal",
            ),
        )
