"""A user's later reflection on an original letter."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.letter import Letter


class Reflection(TimestampMixin, Base):
    """Text written in response to the letter it belongs to."""

    __tablename__ = "reflections"
    __table_args__ = (
        Index("ix_reflections_letter_created_at", "letter_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    letter_id: Mapped[UUID] = mapped_column(
        ForeignKey("letters.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    letter: Mapped[Letter] = relationship(back_populates="reflections")
