from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "alembic_version",
    "model_configs",
    "projects",
    "provider_credentials",
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


def _migration_revision(database_url: str) -> str:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert isinstance(revision, str)
        return revision
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
    assert _migration_revision(database_url) == "0003"
    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        scoped_foreign_key = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys("model_configs")
            if foreign_key["referred_table"] == "provider_credentials"
        )
        assert scoped_foreign_key["constrained_columns"] == [
            "credential_id",
            "project_id",
            "provider",
        ]
        assert scoped_foreign_key["referred_columns"] == [
            "id",
            "project_id",
            "provider",
        ]
        provider_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(
                "provider_credentials"
            )
        }
        assert ("id", "project_id", "provider") in provider_uniques
    finally:
        engine.dispose()
    command.check(config)

    command.downgrade(config, "base")
    assert _table_names(database_url) == {"alembic_version"}

    command.upgrade(config, "head")
    assert _table_names(database_url) == EXPECTED_TABLES
    assert _migration_revision(database_url) == "0003"


def test_contract_migration_backfills_legacy_null_latency(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = (tmp_path / "tailer-legacy-latency.db").as_posix()
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("TAILER_DATABASE_URL", database_url)
    config = _alembic_config()
    command.upgrade(config, "0001")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            statements = [
                """
                    INSERT INTO users
                        (id, email, name, role, created_at, updated_at)
                    VALUES
                        ('legacy_user', 'legacy@example.com', 'Legacy', 'user',
                         '2026-01-01 00:00:00', '2026-01-01 00:00:00')
                """,
                """
                    INSERT INTO projects
                        (id, name, status, created_at, updated_at)
                    VALUES
                        ('legacy_project', 'Legacy', 'active',
                         '2026-01-01 00:00:00', '2026-01-01 00:00:00')
                """,
                """
                    INSERT INTO sub_api_keys
                        (id, project_id, owner_id, name, key_hash, allowed_models,
                         allowed_pipelines, status, created_at, updated_at)
                    VALUES
                        ('legacy_key', 'legacy_project', 'legacy_user', 'Legacy',
                         'legacy_hash', '[\"gpt-4o-mini\"]', '[]', 'active',
                         '2026-01-01 00:00:00', '2026-01-01 00:00:00')
                """,
                """
                    INSERT INTO usage_events
                        (id, project_id, sub_api_key_id, user_id, provider, model,
                         latency_ms, status, created_at)
                    VALUES
                        ('legacy_usage', 'legacy_project', 'legacy_key', 'legacy_user',
                         'mock', 'gpt-4o-mini', NULL, 'success',
                         '2026-01-01 00:00:00')
                """,
            ]
            for statement in statements:
                connection.execute(text(statement))
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT latency_ms FROM usage_events "
                    "WHERE id = 'legacy_usage'"
                )
            ) == 0
        latency_column = next(
            column
            for column in inspect(engine).get_columns("usage_events")
            if column["name"] == "latency_ms"
        )
        assert latency_column["nullable"] is False
    finally:
        engine.dispose()
    command.check(config)
