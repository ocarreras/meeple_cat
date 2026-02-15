from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.engine.bot_runner import BotRunner
    from src.engine.event_store import EventStoreProtocol
    from src.engine.protocol import GamePlugin
    from src.engine.state_store import StateStoreProtocol
    from src.ws.broadcaster import Broadcaster

from src.engine.errors import (
    GameNotActiveError,
    InvalidActionError,
    NotYourTurnError,
    PlayerForfeitedError,
)
from src.engine.models import (
    Action,
    Event,
    GameResult,
    GameState,
    GameStatus,
    MatchId,
    PersistedEvent,
    PlayerId,
    PlayerView,
    TransitionResult,
)
from src.engine.protocol import DISCONNECT_POLICY_FORFEIT_PLAYER

logger = logging.getLogger(__name__)


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
    - Handle player disconnect/reconnect with grace period
    """

    def __init__(
        self,
        match_id: MatchId,
        plugin: GamePlugin,
        state: GameState,
        event_store: EventStoreProtocol | None,
        state_store: StateStoreProtocol,
        broadcaster: Broadcaster,
        db_session_factory: Callable[[], AsyncSession] | None = None,
        grace_period_seconds: float = 30.0,
    ) -> None:
        self.match_id = match_id
        self.plugin = plugin
        self.state = state
        self._event_store = event_store
        self._state_store = state_store
        self._broadcaster = broadcaster
        self._bot_runner: BotRunner | None = None
        self._lock = asyncio.Lock()
        self._sequence_number = 0
        self._db_session_factory = db_session_factory
        self._grace_period_seconds = grace_period_seconds
        self._disconnect_timers: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ #
    #  Action handling
    # ------------------------------------------------------------------ #

    async def handle_action(self, action: Action) -> None:
        """
        Main entry point. Called when a player submits an action.

        Process:
        1. Validate envelope (game active, correct player)
        2. Plugin validates and applies action
        3. Persist events and state
        4. Broadcast views
        5. Auto-resolve loop for auto-resolve phases
        6. Skip forfeited players if needed
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
            await self._run_auto_resolve()

            # 5. Skip forfeited players if needed
            await self._skip_forfeited_player_turn()

        # 6. After lock release, check if a bot needs to move next
        if self._bot_runner is not None:
            self._bot_runner.schedule_bot_move_if_needed(self)

    def _validate_envelope(self, action: Action) -> None:
        """Check game is active, player is not forfeited, and it's the right player's turn."""
        if self.state.status != GameStatus.ACTIVE:
            raise GameNotActiveError(f"Game is {self.state.status.value}")

        if action.player_id in self.state.forfeited_players:
            raise PlayerForfeitedError(
                f"Player {action.player_id} has been forfeited"
            )

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

    async def _run_auto_resolve(self) -> None:
        """Run auto-resolve phases until we hit a non-auto-resolve or game ends."""
        while (
            self.state.current_phase.auto_resolve
            and self.state.status == GameStatus.ACTIVE
        ):
            await self._auto_resolve_phase()

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
            if (
                self.state.status == GameStatus.ACTIVE
                and player.player_id not in self.state.forfeited_players
            ):
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
                forfeited_players=self.state.forfeited_players,
                disconnected_players=list(self.state.disconnected_players.keys()),
            )
            await self._broadcaster.send_state_update(
                self.match_id, player.player_id, view
            )

    async def _finish_game(self, result: GameResult) -> None:
        """Mark game as finished/abandoned, update DB, broadcast result."""
        if result.reason == "abandonment":
            self.state.status = GameStatus.ABANDONED
        else:
            self.state.status = GameStatus.FINISHED
        await self._state_store.save_state(self.state)
        await self._broadcaster.send_game_over(self.match_id, result)

        # Cancel all pending disconnect timers
        for timer in self._disconnect_timers.values():
            timer.cancel()
        self._disconnect_timers.clear()

        # Sync to Postgres
        await self._sync_match_to_db(result)

    async def _sync_match_to_db(self, result: GameResult) -> None:
        """Update Match and MatchPlayer records in Postgres."""
        if self._db_session_factory is None:
            logger.warning(
                f"No db_session_factory for match {self.match_id}, skipping DB sync"
            )
            return

        try:
            from sqlalchemy import select
            from src.models.match import Match, MatchPlayer

            async with self._db_session_factory() as db_session:
                match_uuid = UUID(self.match_id)

                # Update Match status
                stmt = select(Match).where(Match.id == match_uuid)
                db_result = await db_session.execute(stmt)
                match = db_result.scalar_one_or_none()
                if match:
                    match.status = self.state.status.value
                    match.ended_at = datetime.now(timezone.utc)

                # Update MatchPlayer results
                stmt = select(MatchPlayer).where(MatchPlayer.match_id == match_uuid)
                db_result = await db_session.execute(stmt)
                match_players = db_result.scalars().all()

                winners_set = set(result.winners)
                forfeited_set = set(self.state.forfeited_players)
                is_abandoned = result.reason == "abandonment"

                for mp in match_players:
                    pid = str(mp.user_id)
                    mp.score = result.final_scores.get(pid)

                    if is_abandoned:
                        mp.result = "abandoned"
                    elif pid in forfeited_set:
                        mp.result = "forfeit"
                    elif pid in winners_set:
                        mp.result = "win"
                    else:
                        mp.result = "loss"

                await db_session.commit()
                logger.info(
                    f"Synced match {self.match_id} to DB: "
                    f"status={self.state.status.value}, winners={result.winners}"
                )
        except Exception as e:
            logger.error(f"Failed to sync match {self.match_id} to DB: {e}", exc_info=True)

    # ------------------------------------------------------------------ #
    #  Disconnect / Reconnect handling
    # ------------------------------------------------------------------ #

    async def handle_player_disconnect(self, player_id: PlayerId) -> None:
        """Called when a player's WebSocket disconnects."""
        async with self._lock:
            if self.state.status != GameStatus.ACTIVE:
                return
            if player_id in self.state.forfeited_players:
                return
            if player_id in self.state.disconnected_players:
                return  # Already tracked

            # Record disconnect
            now = datetime.now(timezone.utc).timestamp()
            self.state.disconnected_players[player_id] = now

            # Persist event
            await self._persist_event(Event(
                event_type="player_disconnected",
                player_id=player_id,
                payload={"timestamp": now},
            ))

            await self._state_store.save_state(self.state)

            # Notify other players
            await self._broadcaster.send_player_disconnected(
                self.match_id, player_id, self._grace_period_seconds
            )
            await self._broadcast_views()

            logger.info(
                f"Player {player_id} disconnected from match {self.match_id}, "
                f"grace period {self._grace_period_seconds}s"
            )

        # Start grace period timer (outside lock)
        self._start_grace_timer(player_id, self._grace_period_seconds)

    async def handle_player_reconnect(self, player_id: PlayerId) -> None:
        """Called when a previously disconnected player reconnects."""
        async with self._lock:
            if player_id not in self.state.disconnected_players:
                return

            # Cancel grace timer
            timer = self._disconnect_timers.pop(player_id, None)
            if timer:
                timer.cancel()

            # Record reconnect
            disconnect_time = self.state.disconnected_players.pop(player_id, 0)
            elapsed = datetime.now(timezone.utc).timestamp() - disconnect_time

            await self._persist_event(Event(
                event_type="player_reconnected",
                player_id=player_id,
                payload={"elapsed_seconds": round(elapsed, 1)},
            ))

            await self._state_store.save_state(self.state)

            # Notify other players
            await self._broadcaster.send_player_reconnected(
                self.match_id, player_id
            )
            await self._broadcast_views()

            logger.info(
                f"Player {player_id} reconnected to match {self.match_id} "
                f"after {elapsed:.1f}s"
            )

    def _start_grace_timer(
        self, player_id: PlayerId, delay_seconds: float
    ) -> None:
        """Start an async timer that triggers forfeit/abandon after delay."""
        # Cancel existing timer for this player if any
        existing = self._disconnect_timers.pop(player_id, None)
        if existing:
            existing.cancel()

        task = asyncio.create_task(
            self._grace_period_expired(player_id, delay_seconds)
        )
        self._disconnect_timers[player_id] = task

    async def _grace_period_expired(
        self, player_id: PlayerId, delay_seconds: float
    ) -> None:
        """Timer callback: forfeit or abandon after grace period."""
        try:
            await asyncio.sleep(delay_seconds)
        except asyncio.CancelledError:
            return

        # Need own DB session since this runs outside any request
        if self._db_session_factory is None:
            logger.warning(
                f"No db_session_factory for grace period expiry in match {self.match_id}"
            )
            return

        try:
            from src.engine.event_store import EventStore

            async with self._db_session_factory() as db_session:
                async with self._lock:
                    # Re-check: player may have reconnected or game may have ended
                    if self.state.status != GameStatus.ACTIVE:
                        return
                    if player_id not in self.state.disconnected_players:
                        return

                    self._event_store = EventStore(db_session)
                    self._disconnect_timers.pop(player_id, None)

                    await self._handle_forfeit_or_abandon(player_id)

                    await db_session.commit()

        except Exception as e:
            logger.error(
                f"Error handling grace period expiry for {player_id} "
                f"in match {self.match_id}: {e}",
                exc_info=True,
            )

    async def _handle_forfeit_or_abandon(self, player_id: PlayerId) -> None:
        """Apply forfeit or abandon policy for a disconnected player.

        Must be called with self._lock held.
        """
        # Count active (non-forfeited) players excluding this one
        all_player_ids = {p.player_id for p in self.state.players}
        forfeited_after = set(self.state.forfeited_players) | {player_id}
        active_players = all_player_ids - forfeited_after

        if len(active_players) <= 1:
            # 2-player game or last man standing
            if len(active_players) == 1:
                winner = active_players.pop()
                # Add this player to forfeited list
                self.state.forfeited_players.append(player_id)
                self.state.disconnected_players.pop(player_id, None)
                self.state.game_data["forfeited_players"] = list(
                    self.state.forfeited_players
                )

                await self._persist_event(Event(
                    event_type="player_forfeited",
                    player_id=player_id,
                    payload={"reason": "disconnect_timeout"},
                ))

                await self._broadcaster.send_player_forfeited(
                    self.match_id, player_id
                )

                result = GameResult(
                    winners=[winner],
                    final_scores={k: float(v) for k, v in self.state.scores.items()},
                    reason="forfeit",
                )
                await self._finish_game(result)
            else:
                # No active players left
                await self._abandon_game()
            return

        # More than 1 active player remains: apply policy
        policy = getattr(self.plugin, "disconnect_policy", DISCONNECT_POLICY_FORFEIT_PLAYER)

        if policy != DISCONNECT_POLICY_FORFEIT_PLAYER:
            # ABANDON_ALL
            await self._abandon_game()
            return

        # FORFEIT_PLAYER: mark player as forfeited, continue game
        self.state.forfeited_players.append(player_id)
        self.state.disconnected_players.pop(player_id, None)
        self.state.game_data["forfeited_players"] = list(
            self.state.forfeited_players
        )

        await self._persist_event(Event(
            event_type="player_forfeited",
            player_id=player_id,
            payload={"reason": "disconnect_timeout"},
        ))

        await self._state_store.save_state(self.state)

        await self._broadcaster.send_player_forfeited(
            self.match_id, player_id
        )

        # If it's the forfeited player's turn, skip them
        await self._skip_forfeited_player_turn()

        await self._broadcast_views()

        # Check if next player is a bot
        if self._bot_runner is not None:
            self._bot_runner.schedule_bot_move_if_needed(self)

    async def _abandon_game(self) -> None:
        """Abandon the game — no winners."""
        await self._persist_event(Event(
            event_type="game_abandoned",
            payload={"reason": "all_disconnected"},
        ))

        result = GameResult(
            winners=[],
            final_scores={k: float(v) for k, v in self.state.scores.items()},
            reason="abandonment",
        )
        await self._finish_game(result)

    async def _skip_forfeited_player_turn(self) -> None:
        """If the current expected player is forfeited, ask plugin to skip."""
        max_iterations = len(self.state.players) + 1  # Safety guard
        iterations = 0

        while (
            self.state.status == GameStatus.ACTIVE
            and self.state.current_phase.expected_actions
            and not self.state.current_phase.auto_resolve
            and iterations < max_iterations
        ):
            expected_pid = self.state.current_phase.expected_actions[0].player_id
            if expected_pid not in self.state.forfeited_players:
                break

            iterations += 1

            result = self.plugin.on_player_forfeit(
                self.state.game_data,
                self.state.current_phase,
                expected_pid,
                self.state.players,
            )

            if result is None:
                logger.warning(
                    f"Plugin returned None for on_player_forfeit, "
                    f"cannot skip {expected_pid} in match {self.match_id}"
                )
                break

            await self._apply_result(result)

            # Run auto-resolve after skip
            await self._run_auto_resolve()

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    async def _persist_event(self, event: Event) -> None:
        """Persist a single event to the event store."""
        persisted = PersistedEvent(
            match_id=self.match_id,
            sequence_number=self._sequence_number,
            event_type=event.event_type,
            player_id=event.player_id,
            payload=event.payload,
        )
        self._sequence_number += 1

        if self._event_store:
            await self._event_store.append_events(self.match_id, [persisted])
