# Letterloom

A digital time capsule for your future self. Letterloom currently provides a small FastAPI foundation, PostgreSQL configuration, and Alembic migration setup. Capsule and account features are not implemented yet.

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

## Database migrations

Migration configuration reads `DATABASE_URL` through the application settings. Create a migration after adding SQLAlchemy models, then apply it:

```bash
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

The initial project has no application tables or migration revisions yet. Import new model modules from `migrations/env.py` before autogenerating migrations so Alembic can see their metadata.

## Tests

Install development dependencies as above, then run:

```bash
pytest
```
