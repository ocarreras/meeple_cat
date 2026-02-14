from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.user import User


class Match(TimestampMixin, Base):
    __tablename__ = "matches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    players: Mapped[list[MatchPlayer]] = relationship(
        "MatchPlayer",
        back_populates="match",
        cascade="all, delete-orphan",
    )


class MatchPlayer(Base):
    __tablename__ = "match_players"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    seat_index: Mapped[int] = mapped_column(Integer)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    match: Mapped[Match] = relationship("Match", back_populates="players")
    user: Mapped["User"] = relationship("User", lazy="joined")

    # Constraints
    __table_args__ = (
        UniqueConstraint("match_id", "seat_index", name="uq_match_seat"),
        UniqueConstraint("match_id", "user_id", name="uq_match_user"),
    )


class GameEvent(Base):
    __tablename__ = "game_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    match_id: Mapped[UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    player_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("match_id", "sequence_number", name="uq_match_sequence"),
        Index("idx_match_sequence", "match_id", "sequence_number"),
    )
