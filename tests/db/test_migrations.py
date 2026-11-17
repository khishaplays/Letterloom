from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings


def test_initial_migration_creates_schema_and_matches_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    try:
        command.upgrade(config, "head")

        engine = create_engine(database_url)
        try:
            table_names = set(inspect(engine).get_table_names())
            assert {
                "users",
                "letters",
                "attachments",
                "reflections",
                "alembic_version",
            } <= table_names
        finally:
            engine.dispose()

        command.check(config)
    finally:
        get_settings.cache_clear()
