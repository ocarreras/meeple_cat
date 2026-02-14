from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.event_store import EventStoreProtocol
    from src.engine.protocol import GamePlugin
    from src.engine.state_store import StateStoreProtocol
    from src.ws.broadcaster import Broadcaster

from src.engine.errors import GameNotActiveError, InvalidActionError, NotYourTurnError
from src.engine.models import (
    Action,
    GameState,
    GameStatus,
    MatchId,
    PersistedEvent,
    PlayerId,
    PlayerView,
    TransitionResult,
)


class GameSession:
    """
    Orchestrates a single game match.

    Responsibilities:
    - Validate action envelopes (game active, correct player's turn)
    - Delegate to plugin for validation and state transitions
    - Persist events and state
    - Broadcast views to players
    - Handle auto-resolve phases
    - Manage game completion
    """

    def __init__(
        self,
        match_id: MatchId,
        plugin: GamePlugin,
        state: GameState,
        event_store: EventStoreProtocol | None,
        state_store: StateStoreProtocol,
        broadcaster: Broadcaster,
    ) -> None:
        self.match_id = match_id
        self.plugin = plugin
        self.state = state
        self._event_store = event_store
        self._state_store = state_store
        self._broadcaster = broadcaster
        self._lock = asyncio.Lock()
        self._sequence_number = 0

    async def handle_action(self, action: Action) -> None:
        """
        Main entry point. Called when a player submits an action.

        Process:
        1. Validate envelope (game active, correct player)
        2. Plugin validates and applies action
        3. Persist events and state
        4. Broadcast views
        5. Auto-resolve loop for auto-resolve phases
        """
        async with self._lock:
            # 1. Validate envelope
            self._validate_envelope(action)

            # 2. Plugin validates + applies
            error = self.plugin.validate_action(
                self.state.game_data, self.state.current_phase, action
            )
            if error:
                raise InvalidActionError(error, action)

            result = self.plugin.apply_action(
                self.state.game_data,
                self.state.current_phase,
                action,
                self.state.players,
            )

            # 3. Apply result (persist, broadcast)
            await self._apply_result(result)

            # 4. Auto-resolve loop
            while (
                self.state.current_phase.auto_resolve
                and self.state.status == GameStatus.ACTIVE
            ):
                await self._auto_resolve_phase()

    def _validate_envelope(self, action: Action) -> None:
        """Check game is active and it's the right player's turn."""
        if self.state.status != GameStatus.ACTIVE:
            raise GameNotActiveError(f"Game is {self.state.status.value}")

        phase = self.state.current_phase
        if phase.expected_actions:
            expected = phase.expected_actions[0]
            if expected.player_id and action.player_id != expected.player_id:
                raise NotYourTurnError(
                    f"Expected {expected.player_id}, got {action.player_id}"
                )

    async def _apply_result(self, result: TransitionResult) -> None:
        """Update state, persist events, save to Redis, broadcast views."""
        # Update state
        self.state.game_data = result.game_data
        self.state.current_phase = result.next_phase
        self.state.scores = result.scores
        self.state.action_number += 1

        # Persist events
        persisted = []
        for event in result.events:
            persisted.append(
                PersistedEvent(
                    match_id=self.match_id,
                    sequence_number=self._sequence_number,
                    event_type=event.event_type,
                    player_id=event.player_id,
                    payload=event.payload,
                )
            )
            self._sequence_number += 1

        if persisted and self._event_store:
            await self._event_store.append_events(self.match_id, persisted)

        # Save hot state
        await self._state_store.save_state(self.state)

        # Broadcast
        await self._broadcast_views()

        # Game over?
        if result.game_over:
            await self._finish_game(result.game_over)

    async def _auto_resolve_phase(self) -> None:
        """Process an auto-resolve phase with a synthetic action."""
        phase = self.state.current_phase

        # Determine player for synthetic action
        player_id = PlayerId("system")
        if phase.metadata.get("player_index") is not None:
            idx = phase.metadata["player_index"]
            if idx < len(self.state.players):
                player_id = self.state.players[idx].player_id

        synthetic = Action(
            action_type=phase.name,
            player_id=player_id,
        )

        result = self.plugin.apply_action(
            self.state.game_data,
            self.state.current_phase,
            synthetic,
            self.state.players,
        )

        await self._apply_result(result)

    async def _broadcast_views(self) -> None:
        """Send each player their filtered view."""
        for player in self.state.players:
            view_data = self.plugin.get_player_view(
                self.state.game_data,
                self.state.current_phase,
                player.player_id,
                self.state.players,
            )
            valid_actions = []
            if self.state.status == GameStatus.ACTIVE:
                valid_actions = self.plugin.get_valid_actions(
                    self.state.game_data,
                    self.state.current_phase,
                    player.player_id,
                )

            view = PlayerView(
                match_id=self.match_id,
                game_id=self.state.game_id,
                players=self.state.players,
                current_phase=self.state.current_phase,
                status=self.state.status,
                turn_number=self.state.turn_number,
                scores=self.state.scores,
                player_timers=self.state.player_timers,
                game_data=view_data,
                valid_actions=valid_actions,
                viewer_id=player.player_id,
            )
            await self._broadcaster.send_state_update(
                self.match_id, player.player_id, view
            )

    async def _finish_game(self, result) -> None:
        """Mark game as finished and broadcast result."""
        self.state.status = GameStatus.FINISHED
        await self._state_store.save_state(self.state)
        await self._broadcaster.send_game_over(self.match_id, result)
