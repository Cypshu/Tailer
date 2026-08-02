from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "alembic_version",
    "projects",
    "sub_api_keys",
    "usage_events",
    "users",
}


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_sqlite_migration_upgrade_downgrade_upgrade_round_trip(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = (tmp_path / "tailer-migrations.db").as_posix()
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("TAILER_DATABASE_URL", database_url)
    config = _alembic_config()

    command.upgrade(config, "head")
    assert _table_names(database_url) == EXPECTED_TABLES

    command.downgrade(config, "base")
    assert _table_names(database_url) == {"alembic_version"}

    command.upgrade(config, "head")
    assert _table_names(database_url) == EXPECTED_TABLES
