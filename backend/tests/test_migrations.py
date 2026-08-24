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
    "request_attempts",
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
    assert _migration_revision(database_url) == "0004"
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
        attempt_columns = {
            column["name"]: column
            for column in inspector.get_columns("request_attempts")
        }
        assert set(attempt_columns) == {
            "id",
            "project_id",
            "sub_api_key_id",
            "user_id",
            "operation",
            "idempotency_key_digest",
            "request_fingerprint_digest",
            "dispatch_token_digest",
            "state",
            "provider",
            "public_model",
            "provider_model",
            "provider_result_id",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "estimated_cost_eur",
            "currency",
            "latency_ms",
            "error_code",
            "error_http_status",
            "error_public_message",
            "error_retryable",
            "idempotency_expires_at",
            "created_at",
            "updated_at",
        }
        assert attempt_columns["idempotency_key_digest"]["nullable"] is True
        assert attempt_columns["request_fingerprint_digest"]["nullable"] is True
        assert attempt_columns["dispatch_token_digest"]["nullable"] is False
        assert attempt_columns["idempotency_expires_at"]["nullable"] is True

        attempt_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("request_attempts")
        }
        assert (
            "sub_api_key_id",
            "operation",
            "idempotency_key_digest",
        ) in attempt_uniques
        assert ("id", "project_id", "sub_api_key_id", "user_id") in attempt_uniques

        attempt_checks = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("request_attempts")
        }
        assert attempt_checks == {
            "ck_request_attempts_state_allowed",
            "ck_request_attempts_identity_digest_pair",
            "ck_request_attempts_idempotency_digest_length",
            "ck_request_attempts_fingerprint_digest_length",
            "ck_request_attempts_dispatch_digest_length",
            "ck_request_attempts_input_tokens_nonnegative",
            "ck_request_attempts_output_tokens_nonnegative",
            "ck_request_attempts_total_tokens_nonnegative",
            "ck_request_attempts_estimated_cost_nonnegative",
            "ck_request_attempts_currency_iso_code",
            "ck_request_attempts_cost_currency_pair",
            "ck_request_attempts_latency_nonnegative",
            "ck_request_attempts_error_http_status_range",
        }

        attempt_foreign_keys = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in inspector.get_foreign_keys("request_attempts")
        }
        assert attempt_foreign_keys == {
            (("project_id",), "projects", ("id",)),
            (("sub_api_key_id",), "sub_api_keys", ("id",)),
            (("user_id",), "users", ("id",)),
        }

        attempt_indexes = {
            tuple(index["column_names"])
            for index in inspector.get_indexes("request_attempts")
        }
        assert attempt_indexes == {
            ("state", "updated_at"),
            ("project_id", "created_at"),
            ("sub_api_key_id", "created_at"),
        }

        usage_attempt_column = next(
            column
            for column in inspector.get_columns("usage_events")
            if column["name"] == "request_attempt_id"
        )
        assert usage_attempt_column["nullable"] is True
        usage_attempt_fk = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys("usage_events")
            if foreign_key["referred_table"] == "request_attempts"
        )
        assert usage_attempt_fk["constrained_columns"] == [
            "request_attempt_id",
            "project_id",
            "sub_api_key_id",
            "user_id",
        ]
        assert usage_attempt_fk["referred_columns"] == [
            "id",
            "project_id",
            "sub_api_key_id",
            "user_id",
        ]
        usage_uniques = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("usage_events")
        }
        assert ("request_attempt_id",) in usage_uniques
    finally:
        engine.dispose()
    command.check(config)

    command.downgrade(config, "0003")
    assert _table_names(database_url) == EXPECTED_TABLES - {"request_attempts"}
    assert _migration_revision(database_url) == "0003"
    engine = create_engine(database_url)
    try:
        usage_column_names = {
            column["name"] for column in inspect(engine).get_columns("usage_events")
        }
        assert "request_attempt_id" not in usage_column_names
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    assert _table_names(database_url) == EXPECTED_TABLES
    assert _migration_revision(database_url) == "0004"

    command.downgrade(config, "base")
    assert _table_names(database_url) == {"alembic_version"}

    command.upgrade(config, "head")
    assert _table_names(database_url) == EXPECTED_TABLES
    assert _migration_revision(database_url) == "0004"


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
            assert connection.scalar(
                text(
                    "SELECT request_attempt_id FROM usage_events "
                    "WHERE id = 'legacy_usage'"
                )
            ) is None
        latency_column = next(
            column
            for column in inspect(engine).get_columns("usage_events")
            if column["name"] == "latency_ms"
        )
        assert latency_column["nullable"] is False
    finally:
        engine.dispose()
    command.check(config)
