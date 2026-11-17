# Letterloom

A digital time capsule for your future self. Letterloom currently provides a FastAPI foundation and the initial database schema for users, letters, attachments, and reflections. Authentication and the product API are not implemented yet.

## Requirements

- Python 3.12
- PostgreSQL for database-backed work and migrations

## Local setup

Create and activate a virtual environment, then install the application and development dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and set `DATABASE_URL` to your local PostgreSQL connection string. The example has no username or password; configure credentials through your local environment or a local-only `.env` file. Do not commit `.env`.

Start the API from the repository root:

```bash
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive API documentation is at `/docs`.

## Health endpoint

`GET /health` returns `{"status": "ok"}` when the application process can serve requests. It does not check PostgreSQL connectivity.

## Database schema

The schema is intentionally small and keeps ownership easy to follow:

- `users` stores a UUID primary key, a unique email address, and creation/update timestamps. The user record is an ownership anchor; authentication is out of scope for this phase.
- `letters` belongs to one user and stores a title, content, timestamps, and optional sealing and unlock timestamps. Deleting a user cascades to their letters.
- `attachments` belongs to one letter and stores the original filename, optional media type, byte size, and an opaque unique `storage_key`. It contains metadata only; it does not upload or store file contents.
- `reflections` belongs to one letter and stores reflection text and creation/update timestamps.

Attachments and reflections inherit their owner's identity through their required letter relationship. They do not duplicate `user_id`, which avoids inconsistent ownership values. Deleting a letter cascades to its attachments and reflections.

A draft has no `sealed_at`. A sealed letter has a `sealed_at` and must have an `unlock_at` later than the seal time. The database check constraint enforces that rule. No `status` or `is_unlocked` field is stored: unlock eligibility is derived from the seal and unlock timestamps, with `Letter.is_unlocked_at()` providing a backend-side check for a supplied timezone-aware time. Use UTC for application timestamps. This model check does not replace the future API's responsibility to verify the requesting user's ownership before returning letter content.

The schema indexes letters by owner and creation/unlock time, and reflections by letter and creation time to support common list queries. Foreign keys and `ON DELETE CASCADE` keep child rows attached to existing parents and clean up dependent records.

## Database migrations

Migration configuration reads `DATABASE_URL` through the application settings. The initial migration creates the tables, constraints, indexes, and foreign keys listed above. Review generated migration files before applying them. For future model changes, create and inspect a revision, then apply it:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Alembic compares the connected database schema with SQLAlchemy metadata to propose changes; it does not decide whether those changes are correct. All model classes are imported in `migrations/env.py` so the metadata includes their tables. Review each generated revision, especially data changes and destructive operations, before applying it. To roll back one revision, use `alembic downgrade -1` after considering its effect on stored data.

The production database is PostgreSQL. Tests use SQLite and do not require a running PostgreSQL server.

## Tests

Install development dependencies as above, then run:

```bash
pytest
```
