from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event, Thread
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.demo_seed import DEMO_RAW_KEYS, seed_demo_data
from app.domain import RequestAttemptRecord
from app.key_security import hash_sub_api_key
from app.models_db import SubApiKey, UsageEvent
from app.repositories.base import (
    PersistenceConflictError,
    PersistenceWriteError,
    UnitOfWorkFactory,
)
from app.repositories.memory import MemoryUnitOfWorkFactory
from app.repositories.sqlalchemy import SqlAlchemyUnitOfWorkFactory
from app.services import AuthenticationError, ConfigurationError, TailerService


def _record_counts(factory: UnitOfWorkFactory) -> tuple[int, int, int, int]:
    with factory() as uow:
        return (
            len(uow.users.list()),
            int(uow.projects.get_by_id(settings.default_project_id) is not None),
            len(uow.keys.list()),
            len(uow.usage.list(limit=None)),
        )


def _new_usage(factory: UnitOfWorkFactory, usage_id: str):
    with factory() as uow:
        template = uow.usage.get_by_id("usage_1")
    assert template is not None
    return replace(template, id=usage_id)


def _new_attempt(
    attempt_id: str,
    *,
    idempotency_key_digest: str | None = "a" * 64,
    request_fingerprint_digest: str | None = "b" * 64,
    state: str = "dispatch_claimed",
    now: datetime | None = None,
) -> RequestAttemptRecord:
    timestamp = now or datetime.now(timezone.utc)
    return RequestAttemptRecord(
        id=attempt_id,
        project_id=settings.default_project_id,
        sub_api_key_id="subkey_1",
        user_id="user_1",
        operation="chat.completions",
        idempotency_key_digest=idempotency_key_digest,
        request_fingerprint_digest=request_fingerprint_digest,
        dispatch_token_digest="c" * 64,
        state=state,  # type: ignore[arg-type]
        provider="mock",
        public_model="gpt-4o-mini",
        provider_model="gpt-4o-mini",
        provider_result_id=None,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        estimated_cost_eur=None,
        currency=None,
        latency_ms=None,
        error_code=None,
        error_http_status=None,
        error_public_message=None,
        error_retryable=None,
        idempotency_expires_at=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_demo_seed_is_idempotent(uow_factory: UnitOfWorkFactory) -> None:
    before = _record_counts(uow_factory)

    seed_demo_data(uow_factory, settings.sub_api_key_pepper)
    seed_demo_data(uow_factory, settings.sub_api_key_pepper)

    assert before == (3, 1, 3, 4)
    assert _record_counts(uow_factory) == before


def test_demo_seed_allows_pepper_rotation_without_rewriting_existing_keys(
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory() as uow:
        original = uow.keys.get_by_id("subkey_1")
    assert original is not None

    seed_demo_data(uow_factory, "rotated-test-pepper")

    with uow_factory() as uow:
        persisted = uow.keys.get_by_id("subkey_1")
    assert persisted is not None
    assert persisted.key_hash == original.key_hash
    assert _record_counts(uow_factory) == (3, 1, 3, 4)


def test_uow_commits_and_rolls_back_mutations(
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory() as uow:
        committed = uow.keys.set_status("subkey_1", "revoked")
        assert committed is not None
        uow.commit()

    with uow_factory() as uow:
        assert uow.keys.get_by_id("subkey_1").status == "revoked"  # type: ignore[union-attr]

    with pytest.raises(RuntimeError, match="force rollback"):
        with uow_factory() as uow:
            rolled_back = uow.keys.set_status("subkey_1", "paused")
            assert rolled_back is not None
            raise RuntimeError("force rollback")

    with uow_factory() as uow:
        assert uow.keys.get_by_id("subkey_1").status == "revoked"  # type: ignore[union-attr]


def test_attempt_claim_transition_and_usage_anchor_have_adapter_parity(
    uow_factory: UnitOfWorkFactory,
) -> None:
    attempt = _new_attempt("attempt_repository_transition")
    usage = replace(
        _new_usage(uow_factory, "usage_attempt_repository_transition"),
        request_attempt_id=attempt.id,
    )

    with uow_factory() as uow:
        uow.attempts.add(attempt)
        uow.commit()

    with uow_factory() as uow:
        by_id = uow.attempts.get_by_id(attempt.id)
        by_identity = uow.attempts.get_by_identity(
            attempt.sub_api_key_id,
            attempt.operation,
            attempt.idempotency_key_digest or "",
        )
        assert by_id == attempt
        assert by_identity == attempt
        assert not uow.attempts.transition(
            attempt.id,
            expected_state="dispatch_claimed",
            dispatch_token_digest="d" * 64,
            replacement=attempt,
        )

    terminal = replace(
        attempt,
        state="succeeded",
        provider_result_id="chatcmpl_test",
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        estimated_cost_eur=usage.estimated_cost_eur,
        currency=usage.currency,
        latency_ms=usage.latency_ms,
        idempotency_expires_at=attempt.created_at + timedelta(days=30),
        updated_at=attempt.created_at + timedelta(seconds=1),
    )
    with uow_factory() as uow:
        assert uow.attempts.transition(
            attempt.id,
            expected_state="dispatch_claimed",
            dispatch_token_digest=attempt.dispatch_token_digest,
            replacement=terminal,
        )
        uow.usage.add(usage)
        uow.commit()

    with uow_factory() as uow:
        persisted_attempt = uow.attempts.get_by_id(attempt.id)
        persisted_usage = uow.usage.get_by_request_attempt_id(attempt.id)
        assert persisted_attempt == terminal
        assert persisted_usage == usage
        assert not uow.attempts.transition(
            attempt.id,
            expected_state="dispatch_claimed",
            dispatch_token_digest=attempt.dispatch_token_digest,
            replacement=terminal,
        )
        with pytest.raises(PersistenceConflictError):
            uow.usage.add(replace(usage, id="usage_duplicate_attempt_anchor"))


def test_attempt_identity_uniqueness_allows_unkeyed_claims(
    uow_factory: UnitOfWorkFactory,
) -> None:
    first = _new_attempt("attempt_unique_first")
    with uow_factory() as uow:
        uow.attempts.add(first)
        uow.commit()

    with pytest.raises(PersistenceConflictError):
        with uow_factory() as uow:
            uow.attempts.add(
                replace(
                    first,
                    id="attempt_unique_conflict",
                    request_fingerprint_digest="e" * 64,
                )
            )

    with uow_factory() as uow:
        uow.attempts.add(
            _new_attempt(
                "attempt_unkeyed_first",
                idempotency_key_digest=None,
                request_fingerprint_digest=None,
            )
        )
        uow.attempts.add(
            _new_attempt(
                "attempt_unkeyed_second",
                idempotency_key_digest=None,
                request_fingerprint_digest=None,
            )
        )
        uow.commit()


@pytest.mark.parametrize(
    ("cost", "currency"),
    [
        (Decimal("1"), "USD"),
        (None, "EUR"),
        (Decimal("1"), None),
    ],
)
def test_attempt_cost_and_currency_must_form_an_eur_accounting_pair(
    uow_factory: UnitOfWorkFactory,
    cost: Decimal | None,
    currency: str | None,
) -> None:
    attempt = replace(
        _new_attempt(f"attempt_invalid_currency_{currency}_{cost}"),
        estimated_cost_eur=cost,
        currency=currency,
    )

    with pytest.raises(PersistenceConflictError):
        with uow_factory() as uow:
            uow.attempts.add(attempt)


def test_attempt_identity_retirement_is_state_and_time_conditional(
    uow_factory: UnitOfWorkFactory,
) -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    resolved = _new_attempt(
        "attempt_retirement_resolved",
        state="succeeded",
        now=now - timedelta(days=31),
    )
    resolved = replace(
        resolved,
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        estimated_cost_eur=Decimal("0.00000001"),
        currency="EUR",
        latency_ms=1,
        idempotency_expires_at=now,
    )
    unresolved = replace(
        _new_attempt(
            "attempt_retirement_unresolved",
            idempotency_key_digest="d" * 64,
            request_fingerprint_digest="e" * 64,
            state="finalization_failed",
            now=now - timedelta(days=31),
        ),
        idempotency_expires_at=now - timedelta(days=1),
    )
    with uow_factory() as uow:
        uow.attempts.add(resolved)
        uow.attempts.add(unresolved)
        uow.commit()

    with uow_factory() as uow:
        assert not uow.attempts.retire_expired_identity(
            resolved.id,
            expected_idempotency_key_digest=resolved.idempotency_key_digest or "",
            now=now - timedelta(microseconds=1),
        )
        assert not uow.attempts.retire_expired_identity(
            unresolved.id,
            expected_idempotency_key_digest=unresolved.idempotency_key_digest or "",
            now=now,
        )
        assert uow.attempts.retire_expired_identity(
            resolved.id,
            expected_idempotency_key_digest=resolved.idempotency_key_digest or "",
            now=now,
        )
        uow.commit()

    replacement_claim = _new_attempt("attempt_retirement_reuse", now=now)
    with uow_factory() as uow:
        retired = uow.attempts.get_by_id(resolved.id)
        assert retired is not None
        assert retired.idempotency_key_digest is None
        assert retired.request_fingerprint_digest is None
        assert uow.attempts.get_by_identity(
            replacement_claim.sub_api_key_id,
            replacement_claim.operation,
            replacement_claim.idempotency_key_digest or "",
        ) is None
        uow.attempts.add(replacement_claim)
        uow.commit()


def test_usage_attempt_link_rejects_mismatched_attribution(
    uow_factory: UnitOfWorkFactory,
) -> None:
    attempt = _new_attempt("attempt_attribution_mismatch")
    mismatched_usage = replace(
        _new_usage(uow_factory, "usage_attribution_mismatch"),
        sub_api_key_id="subkey_2",
        user_id="user_2",
        request_attempt_id=attempt.id,
    )
    with uow_factory() as uow:
        uow.attempts.add(attempt)
        uow.commit()

    with pytest.raises(PersistenceConflictError):
        with uow_factory() as uow:
            uow.usage.add(mismatched_usage)


def test_sqlalchemy_composite_fk_rejects_mismatched_attempt_attribution(
    sql_uow_factory: SqlAlchemyUnitOfWorkFactory,
) -> None:
    attempt = _new_attempt("attempt_sql_composite_attribution")
    usage = replace(
        _new_usage(sql_uow_factory, "usage_sql_composite_attribution"),
        sub_api_key_id="subkey_2",
        user_id="user_2",
        request_attempt_id=attempt.id,
    )
    with sql_uow_factory() as uow:
        uow.attempts.add(attempt)
        uow.commit()

    with pytest.raises(PersistenceConflictError):
        with sql_uow_factory() as uow:
            assert uow.session is not None
            uow.session.add(
                UsageEvent(
                    id=usage.id,
                    project_id=usage.project_id,
                    sub_api_key_id=usage.sub_api_key_id,
                    user_id=usage.user_id,
                    request_attempt_id=usage.request_attempt_id,
                    provider=usage.provider,
                    model=usage.model,
                    provider_model=usage.provider_model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    total_tokens=usage.total_tokens,
                    estimated_cost_eur=usage.estimated_cost_eur,
                    currency=usage.currency,
                    latency_ms=usage.latency_ms,
                    status=usage.status,
                    error_code=usage.error_code,
                    created_at=usage.created_at,
                )
            )
            uow.commit()


def test_sqlalchemy_sqlite_connections_enforce_foreign_keys(
    sql_uow_factory: SqlAlchemyUnitOfWorkFactory,
) -> None:
    with sql_uow_factory.session_factory() as session:
        assert session.scalar(text("PRAGMA foreign_keys")) == 1


@pytest.mark.parametrize(
    "operation",
    ["attempt-read", "usage-read", "transition", "retirement"],
)
def test_sqlalchemy_attempt_operations_normalize_expected_availability_failures(
    sql_uow_factory: SqlAlchemyUnitOfWorkFactory,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    attempt = _new_attempt("attempt_expected_repository_failure")
    sentinel = "attempt-driver-SENTINEL-secret"

    with sql_uow_factory() as uow:
        assert uow.session is not None
        rollback_spy = Mock(wraps=uow.session.rollback)
        monkeypatch.setattr(uow.session, "rollback", rollback_spy)

        def fail(*args, **kwargs):
            del args, kwargs
            raise OperationalError(
                "request_attempt operation",
                {},
                RuntimeError(sentinel),
            )

        if operation == "attempt-read":
            monkeypatch.setattr(uow.session, "get", fail)
            call = lambda: uow.attempts.get_by_id(attempt.id)
        elif operation == "usage-read":
            monkeypatch.setattr(uow.session, "scalar", fail)
            call = lambda: uow.usage.get_by_request_attempt_id(attempt.id)
        elif operation == "transition":
            monkeypatch.setattr(uow.session, "execute", fail)
            call = lambda: uow.attempts.transition(
                attempt.id,
                expected_state="dispatch_claimed",
                dispatch_token_digest=attempt.dispatch_token_digest,
                replacement=attempt,
            )
        else:
            monkeypatch.setattr(uow.session, "execute", fail)
            call = lambda: uow.attempts.retire_expired_identity(
                attempt.id,
                expected_idempotency_key_digest=attempt.idempotency_key_digest or "",
                now=attempt.created_at,
            )

        with pytest.raises(PersistenceWriteError) as exc_info:
            call()

        assert str(exc_info.value) in {
            "Persistence read failed",
            "Persistence write failed",
        }
        assert sentinel not in str(exc_info.value)
        assert rollback_spy.call_count == 1


@pytest.mark.parametrize(
    "repository_error",
    [PersistenceWriteError, PersistenceConflictError],
    ids=["write-unavailable", "integrity-conflict"],
)
def test_record_usage_normalizes_expected_failures_without_partial_write(
    uow_factory: UnitOfWorkFactory,
    failing_commit_factory,
    repository_error: type[RuntimeError],
) -> None:
    usage = _new_usage(uow_factory, f"usage_failed_{repository_error.__name__}")
    sentinel = "repository-driver-SENTINEL-secret"
    failure_factory = failing_commit_factory(
        lambda: repository_error(f"unsafe repository detail: {sentinel}")
    )

    with pytest.raises(ConfigurationError) as exc_info:
        TailerService(failure_factory).record_usage(usage)

    assert str(exc_info.value) == "Usage finalization is unavailable"
    assert sentinel not in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, repository_error)
    with uow_factory() as uow:
        assert uow.usage.get_by_id(usage.id) is None


def test_record_usage_does_not_normalize_unexpected_programming_failures(
    uow_factory: UnitOfWorkFactory,
    failing_commit_factory,
) -> None:
    usage = _new_usage(uow_factory, "usage_unexpected_failure")
    failure = RuntimeError("unexpected-programming-SENTINEL")
    failure_factory = failing_commit_factory(lambda: failure)

    with pytest.raises(RuntimeError) as exc_info:
        TailerService(failure_factory).record_usage(usage)

    assert exc_info.value is failure
    with uow_factory() as uow:
        assert uow.usage.get_by_id(usage.id) is None


@pytest.mark.parametrize("failure_phase", ["flush", "commit"])
def test_sqlalchemy_write_failures_are_safe_and_explicitly_rolled_back(
    sql_uow_factory: SqlAlchemyUnitOfWorkFactory,
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    usage = _new_usage(sql_uow_factory, f"usage_{failure_phase}_failure")
    sentinel = "database-driver-SENTINEL-secret"

    with sql_uow_factory() as uow:
        assert uow.session is not None
        session = uow.session
        rollback_spy = Mock(wraps=session.rollback)
        monkeypatch.setattr(session, "rollback", rollback_spy)

        def operational_failure() -> None:
            raise OperationalError(
                "INSERT INTO usage_events",
                {},
                RuntimeError(sentinel),
            )

        if failure_phase == "flush":
            original_flush = session.flush

            def flush_then_fail() -> None:
                original_flush()
                operational_failure()

            monkeypatch.setattr(session, "flush", flush_then_fail)
        else:
            uow.usage.add(usage)
            monkeypatch.setattr(session, "commit", operational_failure)

        with pytest.raises(PersistenceWriteError) as exc_info:
            if failure_phase == "flush":
                uow.usage.add(usage)
            else:
                uow.commit()

        assert str(exc_info.value) == "Persistence write failed"
        assert sentinel not in str(exc_info.value)
        assert rollback_spy.call_count == 1
        assert uow.usage.get_by_id(usage.id) is None

    with sql_uow_factory() as uow:
        assert uow.usage.get_by_id(usage.id) is None


def test_sqlalchemy_programming_errors_are_not_normalized(
    sql_uow_factory: SqlAlchemyUnitOfWorkFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usage = _new_usage(sql_uow_factory, "usage_programming_failure")
    sentinel = "programming-error-SENTINEL"
    programming_error = ProgrammingError(
        "COMMIT",
        {},
        RuntimeError(sentinel),
    )
    rollback_spy = None

    with pytest.raises(ProgrammingError) as exc_info:
        with sql_uow_factory() as uow:
            uow.usage.add(usage)
            assert uow.session is not None
            rollback_spy = Mock(wraps=uow.session.rollback)
            monkeypatch.setattr(uow.session, "rollback", rollback_spy)

            def fail_commit() -> None:
                raise programming_error

            monkeypatch.setattr(uow.session, "commit", fail_commit)
            uow.commit()

    assert exc_info.value is programming_error
    assert sentinel in str(exc_info.value)
    assert rollback_spy is not None
    assert rollback_spy.call_count == 1
    with sql_uow_factory() as uow:
        assert uow.usage.get_by_id(usage.id) is None


def test_memory_uow_normal_exit_without_commit_discards_mutation(
    memory_uow_factory: MemoryUnitOfWorkFactory,
) -> None:
    with memory_uow_factory() as uow:
        changed = uow.keys.set_status("subkey_1", "revoked")
        assert changed is not None

    with memory_uow_factory() as uow:
        persisted = uow.keys.get_by_id("subkey_1")
        assert persisted is not None
        assert persisted.status == "active"


def test_memory_uow_read_object_is_detached_without_commit(
    memory_uow_factory: MemoryUnitOfWorkFactory,
) -> None:
    with memory_uow_factory() as uow:
        key = uow.keys.get_by_id("subkey_1")
        assert key is not None

    key.status = "revoked"

    with memory_uow_factory() as uow:
        persisted = uow.keys.get_by_id("subkey_1")
        assert persisted is not None
        assert persisted.status == "active"


def test_memory_uow_explicit_commit_and_rollback_have_sql_parity(
    memory_uow_factory: MemoryUnitOfWorkFactory,
) -> None:
    with memory_uow_factory() as uow:
        committed = uow.keys.set_status("subkey_1", "revoked")
        assert committed is not None
        uow.commit()

        uncommitted = uow.keys.set_status("subkey_1", "paused")
        assert uncommitted is not None
        uow.rollback()
        restored = uow.keys.get_by_id("subkey_1")
        assert restored is not None
        assert restored.status == "revoked"

    with memory_uow_factory() as uow:
        persisted = uow.keys.get_by_id("subkey_1")
        assert persisted is not None
        assert persisted.status == "revoked"


def test_memory_uow_serializes_concurrent_transactions(
    memory_uow_factory: MemoryUnitOfWorkFactory,
) -> None:
    first_entered = Event()
    allow_first_commit = Event()
    second_attempted = Event()
    second_entered = Event()
    errors: list[BaseException] = []

    def first_transaction() -> None:
        try:
            with memory_uow_factory() as uow:
                changed = uow.keys.set_status("subkey_1", "revoked")
                assert changed is not None
                first_entered.set()
                assert allow_first_commit.wait(timeout=5)
                uow.commit()
        except BaseException as exc:  # pragma: no cover - reported in main thread
            errors.append(exc)

    def second_transaction() -> None:
        try:
            assert first_entered.wait(timeout=5)
            second_attempted.set()
            with memory_uow_factory() as uow:
                second_entered.set()
                first_key = uow.keys.get_by_id("subkey_1")
                assert first_key is not None
                assert first_key.status == "revoked"
                changed = uow.keys.set_status("subkey_2", "paused")
                assert changed is not None
                uow.commit()
        except BaseException as exc:  # pragma: no cover - reported in main thread
            errors.append(exc)

    first = Thread(target=first_transaction)
    second = Thread(target=second_transaction)
    first.start()
    second.start()
    assert first_entered.wait(timeout=5)
    assert second_attempted.wait(timeout=5)
    assert not second_entered.wait(timeout=0.1)

    allow_first_commit.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert second_entered.is_set()
    with memory_uow_factory() as uow:
        first_key = uow.keys.get_by_id("subkey_1")
        second_key = uow.keys.get_by_id("subkey_2")
        assert first_key is not None
        assert second_key is not None
        assert first_key.status == "revoked"
        assert second_key.status == "paused"


def test_hmac_digest_is_the_only_secret_used_for_repository_lookup(
    uow_factory: UnitOfWorkFactory,
) -> None:
    raw_key = DEMO_RAW_KEYS["subkey_1"]
    digest = hash_sub_api_key(raw_key, settings.sub_api_key_pepper)

    with uow_factory() as uow:
        key = uow.keys.get_by_hash(digest)
        wrong_key = uow.keys.get_by_hash(
            hash_sub_api_key(f"{raw_key}-wrong", settings.sub_api_key_pepper)
        )

    assert key is not None
    assert key.id == "subkey_1"
    assert key.key_hash == digest
    assert raw_key not in key.key_hash
    assert key.key_prefix
    assert key.key_prefix != raw_key
    assert wrong_key is None

    service = TailerService(uow_factory)
    assert service.authorize_runtime_key(raw_key, "gpt-4o-mini", 64).id == "subkey_1"
    with pytest.raises(AuthenticationError, match="Invalid or inactive API key"):
        service.authorize_runtime_key(f"{raw_key}-wrong", "gpt-4o-mini", 64)


def test_sqlalchemy_commit_survives_engine_reopen_and_stores_no_raw_secret(
    sql_uow_factory: SqlAlchemyUnitOfWorkFactory,
) -> None:
    raw_key = DEMO_RAW_KEYS["subkey_1"]
    engine = sql_uow_factory.session_factory.kw["bind"]
    database_url = engine.url

    with sql_uow_factory() as uow:
        changed = uow.keys.set_status("subkey_1", "revoked")
        assert changed is not None
        uow.commit()

    engine.dispose()
    reopened_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    reopened_factory = SqlAlchemyUnitOfWorkFactory(
        sessionmaker(
            bind=reopened_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    )
    try:
        with reopened_factory() as uow:
            persisted = uow.keys.get_by_id("subkey_1")
        assert persisted is not None
        assert persisted.status == "revoked"

        with reopened_factory.session_factory() as session:
            stored_hash = session.scalar(
                select(SubApiKey.key_hash).where(SubApiKey.id == "subkey_1")
            )
        assert stored_hash == hash_sub_api_key(raw_key, settings.sub_api_key_pepper)
        assert raw_key not in stored_hash
    finally:
        reopened_engine.dispose()
