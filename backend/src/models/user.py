from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    display_name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
