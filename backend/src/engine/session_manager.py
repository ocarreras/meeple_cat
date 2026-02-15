from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.engine.protocol import GamePlugin
    from src.engine.state_store import StateStoreProtocol
    from src.ws.broadcaster import Broadcaster

from src.engine.event_store import EventStore
from src.engine.models import (
    GameConfig,
    GameId,
    GameState,
    GameStatus,
    MatchId,
    PersistedEvent,
    Player,
)
from src.engine.bot_runner import BotRunner
from src.engine.registry import PluginRegistry
from src.engine.session import GameSession

logger = logging.getLogger(__name__)


class GameSessionManager:
    """
    Manages the lifecycle of all active game sessions.

    Responsibilities:
    - Create new game sessions
    - Retrieve existing sessions
    - Recover sessions from Redis on startup
    - Clean up finished sessions
    """

    def __init__(
        self,
        registry: PluginRegistry,
        state_store: StateStoreProtocol,
        broadcaster: Broadcaster,
        db_session_factory: Callable[[], AsyncSession],
        bot_runner: BotRunner | None = None,
        grace_period_seconds: float = 30.0,
    ) -> None:
        self._registry = registry
        self._state_store = state_store
        self._broadcaster = broadcaster
        self._db_session_factory = db_session_factory
        self._bot_runner = bot_runner
        self._grace_period_seconds = grace_period_seconds
        self._sessions: dict[str, GameSession] = {}

    async def create_session(
        self,
        match_id: MatchId,
        game_id: GameId,
        players: list[Player],
        config: GameConfig,
    ) -> GameSession:
        """
        Create a new game session.

        Process:
        1. Get plugin from registry
        2. Call plugin.create_initial_state()
        3. Build GameState
        4. Persist initial events to DB
        5. Save state to Redis
        6. Run auto-resolve for initial phase (e.g., Carcassonne draws first tile)
        7. Store and return session
        """
        plugin = self._registry.get(game_id)
        game_data, phase, initial_events = plugin.create_initial_state(players, config)

        state = GameState(
            match_id=match_id,
            game_id=game_id,
            players=players,
            current_phase=phase,
            status=GameStatus.ACTIVE,
            config=config,
            game_data=game_data,
            scores={p.player_id: 0.0 for p in players},
        )

        # Persist initial events and save state
        async with self._db_session_factory() as db_session:
            event_store = EventStore(db_session)

            session = GameSession(
                match_id=match_id,
                plugin=plugin,
                state=state,
                event_store=event_store,
                state_store=self._state_store,
                broadcaster=self._broadcaster,
                db_session_factory=self._db_session_factory,
                grace_period_seconds=self._grace_period_seconds,
            )

            # Persist initial events
            persisted = []
            for i, event in enumerate(initial_events):
                persisted.append(
                    PersistedEvent(
                        match_id=match_id,
                        sequence_number=i,
                        event_type=event.event_type,
                        player_id=event.player_id,
                        payload=event.payload,
                    )
                )
            if persisted:
                await event_store.append_events(match_id, persisted)
                session._sequence_number = len(persisted)

            await self._state_store.save_state(state)
            await db_session.commit()

        session._bot_runner = self._bot_runner
        self._sessions[match_id] = session

        # Auto-resolve initial phase(s) — Carcassonne starts with draw_tile (auto)
        if state.current_phase.auto_resolve:
            async with self._db_session_factory() as db_session:
                session._event_store = EventStore(db_session)
                while (
                    session.state.current_phase.auto_resolve
                    and session.state.status == GameStatus.ACTIVE
                ):
                    await session._auto_resolve_phase()
                await db_session.commit()

        # Trigger bot move if the first player to act is a bot
        if self._bot_runner:
            self._bot_runner.schedule_bot_move_if_needed(session)

        logger.info(
            f"Created session for match {match_id} with game {game_id} and {len(players)} players"
        )
        return session

    def get_session(self, match_id: MatchId) -> GameSession | None:
        """Get an existing session by match ID."""
        return self._sessions.get(match_id)

    async def recover_sessions(self) -> int:
        """
        Recover active sessions from Redis on startup.

        Returns the number of sessions recovered.
        """
        match_ids = await self._state_store.list_active_matches()
        recovered = 0
        for match_id in match_ids:
            state = await self._state_store.load_state(match_id)
            if state is None or state.status != GameStatus.ACTIVE:
                continue
            try:
                plugin = self._registry.get(state.game_id)
                # Create session with a placeholder event_store
                # (real one injected per-action by WS handler)
                session = GameSession(
                    match_id=match_id,
                    plugin=plugin,
                    state=state,
                    event_store=None,  # Will be set per-action
                    state_store=self._state_store,
                    broadcaster=self._broadcaster,
                    db_session_factory=self._db_session_factory,
                    grace_period_seconds=self._grace_period_seconds,
                )
                # Recover sequence number from DB
                async with self._db_session_factory() as db_session:
                    es = EventStore(db_session)
                    events = await es.get_events(match_id)
                    session._sequence_number = len(events)

                session._bot_runner = self._bot_runner
                self._sessions[match_id] = session
                recovered += 1
                logger.info(f"Recovered session for match {match_id}")

                # Recover disconnect timers
                await self._recover_disconnect_timers(session)

                # Trigger bot move if it was a bot's turn when server restarted
                if self._bot_runner:
                    self._bot_runner.schedule_bot_move_if_needed(session)
            except Exception as e:
                logger.warning(f"Failed to recover {match_id}: {e}")

        logger.info(f"Recovered {recovered} active sessions")
        return recovered

    async def _recover_disconnect_timers(self, session: GameSession) -> None:
        """Restart grace period timers for players who were disconnected before restart."""
        if not session.state.disconnected_players:
            return

        now = datetime.now(timezone.utc).timestamp()

        for player_id, disconnect_ts in list(session.state.disconnected_players.items()):
            elapsed = now - disconnect_ts
            remaining = self._grace_period_seconds - elapsed

            if remaining <= 0:
                # Grace period already expired during downtime
                logger.info(
                    f"Grace period expired during downtime for {player_id} "
                    f"in match {session.match_id}, applying forfeit/abandon"
                )
                try:
                    async with self._db_session_factory() as db_session:
                        es = EventStore(db_session)
                        session._event_store = es
                        async with session._lock:
                            if session.state.status == GameStatus.ACTIVE:
                                await session._handle_forfeit_or_abandon(player_id)
                        await db_session.commit()
                except Exception as e:
                    logger.error(
                        f"Failed to apply post-downtime forfeit for {player_id} "
                        f"in match {session.match_id}: {e}",
                        exc_info=True,
                    )
            else:
                # Restart timer with remaining time
                logger.info(
                    f"Restarting grace timer for {player_id} in match "
                    f"{session.match_id} with {remaining:.1f}s remaining"
                )
                session._start_grace_timer(player_id, remaining)

    async def cleanup_stale_matches(self) -> int:
        """Mark old active matches without Redis state as abandoned.

        Called once at startup after recover_sessions().
        Returns the number of matches cleaned up.
        """
        try:
            from sqlalchemy import select, update
            from src.models.match import Match, MatchPlayer

            # Get all match IDs that have active Redis state
            active_redis_ids = set(await self._state_store.list_active_matches())

            cleaned = 0
            async with self._db_session_factory() as db_session:
                # Find active matches older than 24 hours
                cutoff = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                stmt = select(Match).where(
                    Match.status == "active",
                    Match.started_at < cutoff,
                )
                result = await db_session.execute(stmt)
                stale_matches = result.scalars().all()

                for match in stale_matches:
                    match_id_str = str(match.id)
                    if match_id_str in active_redis_ids:
                        continue  # Has active session, skip

                    match.status = "abandoned"
                    match.ended_at = datetime.now(timezone.utc)

                    # Update all players
                    mp_stmt = select(MatchPlayer).where(
                        MatchPlayer.match_id == match.id
                    )
                    mp_result = await db_session.execute(mp_stmt)
                    for mp in mp_result.scalars().all():
                        mp.result = "abandoned"

                    cleaned += 1
                    logger.info(f"Cleaned up stale match {match_id_str}")

                if cleaned > 0:
                    await db_session.commit()
                    logger.info(f"Cleaned up {cleaned} stale active matches")

            return cleaned
        except Exception as e:
            logger.error(f"Failed to clean up stale matches: {e}", exc_info=True)
            return 0

    def remove_session(self, match_id: MatchId) -> None:
        """Remove a session from memory (e.g., after game finishes)."""
        if match_id in self._sessions:
            del self._sessions[match_id]
            logger.info(f"Removed session for match {match_id}")
