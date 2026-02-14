from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.models.user import User


class GameRoom(TimestampMixin, Base):
    __tablename__ = "game_rooms"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    game_id: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="waiting", index=True)
    max_players: Mapped[int] = mapped_column(Integer)
    match_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("matches.id"), nullable=True
    )

    # Relationships
    seats: Mapped[list[GameRoomSeat]] = relationship(
        "GameRoomSeat",
        back_populates="room",
        cascade="all, delete-orphan",
        order_by="GameRoomSeat.seat_index",
    )
    creator: Mapped["User"] = relationship("User", lazy="joined")


class GameRoomSeat(Base):
    __tablename__ = "game_room_seats"

    room_id: Mapped[UUID] = mapped_column(
        ForeignKey("game_rooms.id", ondelete="CASCADE"),
        primary_key=True,
    )
    seat_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    room: Mapped[GameRoom] = relationship("GameRoom", back_populates="seats")
    user: Mapped["User | None"] = relationship("User", lazy="joined")
