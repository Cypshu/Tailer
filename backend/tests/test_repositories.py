from threading import Event, Thread

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.demo_seed import DEMO_RAW_KEYS, seed_demo_data
from app.key_security import hash_sub_api_key
from app.models_db import SubApiKey
from app.repositories.base import UnitOfWorkFactory
from app.repositories.memory import MemoryUnitOfWorkFactory
from app.repositories.sqlalchemy import SqlAlchemyUnitOfWorkFactory
from app.services import AuthenticationError, TailerService


def _record_counts(factory: UnitOfWorkFactory) -> tuple[int, int, int, int]:
    with factory() as uow:
        return (
            len(uow.users.list()),
            int(uow.projects.get_by_id(settings.default_project_id) is not None),
            len(uow.keys.list()),
            len(uow.usage.list(limit=None)),
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
    assert service.authorize_runtime_key(raw_key, "gpt-4o-mini").id == "subkey_1"
    with pytest.raises(AuthenticationError, match="Invalid or inactive API key"):
        service.authorize_runtime_key(f"{raw_key}-wrong", "gpt-4o-mini")


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
