from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class TimestampMixin:
    """Mixin to add created_at timestamp to models."""
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
