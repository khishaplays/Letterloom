"""Attachment metadata for a letter; file storage is handled separately."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.letter import Letter


class Attachment(Base):
    """Metadata and an opaque storage key for a letter attachment or memory."""

    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_attachments_size_nonnegative"),
        CheckConstraint(
            "length(trim(storage_key)) > 0",
            name="ck_attachments_storage_key_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    letter_id: Mapped[UUID] = mapped_column(
        ForeignKey("letters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    letter: Mapped[Letter] = relationship(back_populates="attachments")
