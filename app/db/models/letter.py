"""Letter database model and derived unlock state."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.db.models.attachment import Attachment
    from app.db.models.reflection import Reflection
    from app.db.models.user import User


class Letter(TimestampMixin, Base):
    """A user's written message, optionally sealed until a future time."""

    __tablename__ = "letters"
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) > 0", name="ck_letters_title_not_blank"
        ),
        CheckConstraint(
            "sealed_at IS NULL OR "
            "(unlock_at IS NOT NULL AND unlock_at > sealed_at)",
            name="ck_letters_sealed_unlock_after_sealed",
        ),
        Index("ix_letters_user_created_at", "user_id", "created_at"),
        Index("ix_letters_user_unlock_at", "user_id", "unlock_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unlock_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="letters")
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="letter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reflections: Mapped[list[Reflection]] = relationship(
        back_populates="letter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def is_unlocked_at(self, current_time: datetime) -> bool:
        """Return unlock eligibility without storing a redundant unlocked flag.

        Callers must pass an aware datetime, normally the current UTC time.
        """

        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("current_time must include a timezone")
        return (
            self.sealed_at is not None
            and self.unlock_at is not None
            and current_time >= self.unlock_at
        )
