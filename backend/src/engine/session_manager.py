from __future__ import annotations

import logging
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
    ) -> None:
        self._registry = registry
        self._state_store = state_store
        self._broadcaster = broadcaster
        self._db_session_factory = db_session_factory
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
                )
                # Recover sequence number from DB
                async with self._db_session_factory() as db_session:
                    es = EventStore(db_session)
                    events = await es.get_events(match_id)
                    session._sequence_number = len(events)

                self._sessions[match_id] = session
                recovered += 1
                logger.info(f"Recovered session for match {match_id}")
            except Exception as e:
                logger.warning(f"Failed to recover {match_id}: {e}")

        logger.info(f"Recovered {recovered} active sessions")
        return recovered

    def remove_session(self, match_id: MatchId) -> None:
        """Remove a session from memory (e.g., after game finishes)."""
        if match_id in self._sessions:
            del self._sessions[match_id]
            logger.info(f"Removed session for match {match_id}")
