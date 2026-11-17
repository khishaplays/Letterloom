from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Attachment, Letter, Reflection, User


def test_letter_children_have_a_clear_owner_through_the_letter(
    db_session: Session,
) -> None:
    user = User(email="reader@example.test")
    letter = Letter(user=user, title="For later", content="A note to my future self")
    attachment = Attachment(
        letter=letter,
        original_filename="photo.jpg",
        media_type="image/jpeg",
        size_bytes=2048,
        storage_key="users/letter/photo-1",
    )
    reflection = Reflection(letter=letter, content="I remember writing this.")
    db_session.add(user)
    db_session.commit()

    assert letter.user is user
    assert user.letters == [letter]
    assert attachment.letter is letter
    assert reflection.letter is letter
    assert attachment.letter.user is user
    assert reflection.letter.user is user
    assert letter.created_at is not None
    assert letter.updated_at is not None


def test_unlock_eligibility_is_derived_from_seal_and_unlock_times() -> None:
    now = datetime.now(timezone.utc)
    draft = Letter(
        title="Draft", content="Not sealed", unlock_at=now + timedelta(days=1)
    )
    sealed = Letter(
        title="Sealed",
        content="Wait until later",
        sealed_at=now,
        unlock_at=now + timedelta(days=1),
    )

    assert not draft.is_unlocked_at(now + timedelta(days=2))
    just_before_unlock = now + timedelta(days=1) - timedelta(microseconds=1)
    assert not sealed.is_unlocked_at(just_before_unlock)
    assert sealed.is_unlocked_at(now + timedelta(days=1))
    with pytest.raises(ValueError, match="timezone"):
        sealed.is_unlocked_at(datetime.now())


def test_database_rejects_sealed_letter_without_a_later_unlock_time(
    db_session: Session,
) -> None:
    user = User(email="writer@example.test")
    invalid_letter = Letter(
        user=user,
        title="Invalid seal",
        content="The database should reject this state.",
        sealed_at=datetime.now(timezone.utc),
        unlock_at=None,
    )
    db_session.add(invalid_letter)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_cascades_deletion_from_owner_to_letter_records(
    db_session: Session,
) -> None:
    user = User(email="owner@example.test")
    letter = Letter(user=user, title="Delete with owner", content="Example")
    letter.attachments.append(
        Attachment(
            original_filename="note.txt",
            size_bytes=0,
            storage_key="users/letter/note-1",
        )
    )
    letter.reflections.append(Reflection(content="A reflection"))
    db_session.add(user)
    db_session.commit()
    user_id = user.id

    db_session.execute(delete(User).where(User.id == user_id))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Letter)) == 0
    assert db_session.scalar(select(func.count()).select_from(Attachment)) == 0
    assert db_session.scalar(select(func.count()).select_from(Reflection)) == 0


def test_attachment_rejects_a_missing_parent_letter(db_session: Session) -> None:
    attachment = Attachment(
        letter_id=uuid4(),
        original_filename="orphan.txt",
        size_bytes=10,
        storage_key="unowned/object",
    )
    db_session.add(attachment)

    with pytest.raises(IntegrityError):
        db_session.commit()
