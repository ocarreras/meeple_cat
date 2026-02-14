from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.engine.models import MatchId, PersistedEvent


class EventStoreProtocol(Protocol):
    """Protocol for event persistence."""

    async def append_events(
        self, match_id: MatchId, events: list[PersistedEvent]
    ) -> None:
        """Append events to the event log for a match."""
        ...

    async def get_events(
        self, match_id: MatchId, from_sequence: int = 0
    ) -> list[PersistedEvent]:
        """Retrieve events for a match, optionally starting from a sequence number."""
        ...


class EventStore:
    """Database-backed event store implementation."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def append_events(
        self, match_id: MatchId, events: list[PersistedEvent]
    ) -> None:
        """Append events to the database."""
        from uuid import UUID

        from src.models.match import GameEvent

        # Convert match_id string to UUID for database
        match_uuid = UUID(match_id)

        # Create GameEvent rows from PersistedEvent objects
        for event in events:
            db_event = GameEvent(
                match_id=match_uuid,
                sequence_number=event.sequence_number,
                event_type=event.event_type,
                player_id=event.player_id,  # Keep as string (can be None)
                payload=event.payload,
                timestamp=event.timestamp,
            )
            self.db_session.add(db_event)

        # Flush to database (commit happens at session level)
        await self.db_session.flush()

    async def get_events(
        self, match_id: MatchId, from_sequence: int = 0
    ) -> list[PersistedEvent]:
        """Retrieve events from the database."""
        from uuid import UUID

        from sqlalchemy import select

        from src.models.match import GameEvent

        # Convert match_id string to UUID for database
        match_uuid = UUID(match_id)

        # Query events
        stmt = (
            select(GameEvent)
            .where(GameEvent.match_id == match_uuid)
            .where(GameEvent.sequence_number >= from_sequence)
            .order_by(GameEvent.sequence_number)
        )

        result = await self.db_session.execute(stmt)
        db_events = result.scalars().all()

        # Convert GameEvent rows to PersistedEvent objects
        return [
            PersistedEvent(
                id=event.id,
                match_id=match_id,  # Return as string
                sequence_number=event.sequence_number,
                event_type=event.event_type,
                player_id=event.player_id,
                payload=event.payload,
                timestamp=event.timestamp,
            )
            for event in db_events
        ]
