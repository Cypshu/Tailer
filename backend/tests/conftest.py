from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from alembic import command
from alembic.config import Config
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import enable_sqlite_foreign_keys
from app.demo_seed import DEMO_RAW_KEYS, build_demo_records, seed_demo_data
from app.domain import KeyRecord
from app.main import app
from app.models_db import SubApiKey
from app.providers import (
    ChatCompletionChoice,
    ChatCompletionResult,
    ChatCompletionUsage,
    Message,
    MockProvider,
    set_provider,
)
from app.repositories.base import (
    AbstractUnitOfWork,
    PersistenceWriteError,
    UnitOfWorkFactory,
)
from app.repositories.dependencies import get_uow_factory
from app.repositories.memory import MemoryStore, MemoryUnitOfWorkFactory
from app.repositories.sqlalchemy import SqlAlchemyUnitOfWorkFactory


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


@pytest.fixture(autouse=True)
def isolated_application_state() -> Iterator[None]:
    """Keep FastAPI overrides and the process-global provider isolated per test."""
    app.dependency_overrides.clear()
    set_provider(MockProvider())
    yield
    app.dependency_overrides.clear()
    set_provider(MockProvider())


@pytest.fixture
def memory_uow_factory() -> MemoryUnitOfWorkFactory:
    users, projects, keys, usage = build_demo_records(settings.sub_api_key_pepper)
    return MemoryUnitOfWorkFactory(
        MemoryStore(users=users, projects=projects, keys=keys, usage=usage)
    )


@pytest.fixture
def sql_uow_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[SqlAlchemyUnitOfWorkFactory]:
    """Return a seeded adapter backed by a fresh database migrated to head."""
    database_path = (tmp_path / "tailer-api.db").as_posix()
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("TAILER_DATABASE_URL", database_url)
    command.upgrade(_alembic_config(), "head")

    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    enable_sqlite_foreign_keys(engine)

    factory = SqlAlchemyUnitOfWorkFactory(
        sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    )
    seed_demo_data(factory, settings.sub_api_key_pepper)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture(params=["memory", "sqlalchemy"], ids=["memory", "sqlalchemy"])
def uow_factory(request: pytest.FixtureRequest) -> UnitOfWorkFactory:
    """Exercise every client contract through both persistence adapters."""
    if request.param == "memory":
        return request.getfixturevalue("memory_uow_factory")
    return request.getfixturevalue("sql_uow_factory")


class _FailingCommitUnitOfWork:
    def __init__(
        self,
        owner: "_FailingCommitUnitOfWorkFactory",
    ) -> None:
        self._owner = owner
        self._delegate = owner.delegate_factory()

    def __enter__(self):
        entered = self._delegate.__enter__()
        self.users = entered.users
        self.projects = entered.projects
        self.provider_credentials = entered.provider_credentials
        self.model_configs = entered.model_configs
        self.keys = entered.keys
        self.usage = entered.usage
        self.attempts = entered.attempts
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._delegate.__exit__(exc_type, exc_value, traceback)

    def commit(self) -> None:
        self._owner.commit(self._delegate)

    def rollback(self) -> None:
        self._delegate.rollback()


class _FailingCommitUnitOfWorkFactory:
    def __init__(
        self,
        delegate_factory: UnitOfWorkFactory,
        failure_factory: Callable[[], BaseException],
        *,
        fail_on_commit: int = 1,
        persist_before_failure: bool = False,
    ) -> None:
        self.delegate_factory = delegate_factory
        self.failure_factory = failure_factory
        self.fail_on_commit = fail_on_commit
        self.persist_before_failure = persist_before_failure
        self._commit_count = 0
        self._lock = Lock()

    def __call__(self) -> AbstractUnitOfWork:
        return _FailingCommitUnitOfWork(self)

    def commit(self, delegate: AbstractUnitOfWork) -> None:
        with self._lock:
            self._commit_count += 1
            commit_number = self._commit_count
        if commit_number != self.fail_on_commit:
            delegate.commit()
            return
        if self.persist_before_failure:
            delegate.commit()
        raise self.failure_factory()


@pytest.fixture
def failing_commit_factory(
    uow_factory: UnitOfWorkFactory,
) -> Callable[[Callable[[], BaseException]], UnitOfWorkFactory]:
    def build(
        failure_factory: Callable[[], BaseException],
    ) -> UnitOfWorkFactory:
        return _FailingCommitUnitOfWorkFactory(uow_factory, failure_factory)

    return build


@pytest.fixture
def scripted_commit_factory(
    uow_factory: UnitOfWorkFactory,
) -> Callable[..., UnitOfWorkFactory]:
    def build(
        failure_factory: Callable[[], BaseException],
        *,
        fail_on_commit: int,
        persist_before_failure: bool = False,
    ) -> UnitOfWorkFactory:
        return _FailingCommitUnitOfWorkFactory(
            uow_factory,
            failure_factory,
            fail_on_commit=fail_on_commit,
            persist_before_failure=persist_before_failure,
        )

    return build


@dataclass(frozen=True)
class PersistenceFailureHarness:
    factory: UnitOfWorkFactory
    driver_detail: str
    sentinel_secret: str


@pytest.fixture
def persistence_failure_harness(
    scripted_commit_factory: Callable[..., UnitOfWorkFactory],
) -> PersistenceFailureHarness:
    driver_detail = "sqlite3.OperationalError: simulated commit failure"
    sentinel_secret = "tailer_sub_SENTINEL_FINALIZATION_SECRET"
    factory = scripted_commit_factory(
        lambda: PersistenceWriteError(f"{driver_detail}; {sentinel_secret}"),
        fail_on_commit=2,
    )
    return PersistenceFailureHarness(
        factory=factory,
        driver_detail=driver_detail,
        sentinel_secret=sentinel_secret,
    )


@pytest.fixture
def client(uow_factory: UnitOfWorkFactory) -> Iterator[TestClient]:
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def persistence_failure_client(
    persistence_failure_harness: PersistenceFailureHarness,
) -> Iterator[TestClient]:
    app.dependency_overrides[get_uow_factory] = (
        lambda: persistence_failure_harness.factory
    )
    with TestClient(app) as test_client:
        yield test_client


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    return _login_headers(client, "organizer@hackathon.dev", "Hackathon Organizer")


@pytest.fixture
def user_headers(client: TestClient) -> dict[str, str]:
    return _login_headers(client, "team_alpha@hackathon.dev", "Team Alpha")


@dataclass(frozen=True)
class RuntimeCredential:
    raw_key: str
    record: KeyRecord


@pytest.fixture
def active_key(uow_factory: UnitOfWorkFactory) -> RuntimeCredential:
    with uow_factory() as uow:
        key = uow.keys.get_by_id("subkey_1")
    assert key is not None
    return RuntimeCredential(raw_key=DEMO_RAW_KEYS[key.id], record=key)


@pytest.fixture
def mutate_key(
    uow_factory: UnitOfWorkFactory,
) -> Callable[..., None]:
    """Change seeded key state through the adapter or its test setup handle."""

    def mutate(key_id: str, **changes: object) -> None:
        if isinstance(uow_factory, MemoryUnitOfWorkFactory):
            with uow_factory() as uow:
                key = uow.keys.get_by_id(key_id)
                assert key is not None
                for field, value in changes.items():
                    setattr(key, field, value)
                uow.commit()
            return

        assert isinstance(uow_factory, SqlAlchemyUnitOfWorkFactory)
        with uow_factory.session_factory() as session:
            row = session.get(SubApiKey, key_id)
            assert row is not None
            for field, value in changes.items():
                setattr(row, field, value)
            session.commit()

    return mutate


class RecordingProvider:
    """Deterministic provider spy used to prove boundary and state behavior."""

    name = "recording"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.cost_calls: list[dict[str, Any]] = []
        self.result = ChatCompletionResult(
            id="chatcmpl_test",
            model="gpt-4o-mini",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=Message(role="assistant", content="Test response"),
                    finish_reason="stop",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            ),
            durable_provider_result_id="chatcmpl_test",
        )
        self.cost = 0.0123

    async def chat_completions(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 100,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        self.calls.append(
            {
                "messages": deepcopy(messages),
                "model": model,
                "max_tokens": max_tokens,
                **kwargs,
            }
        )
        self.result.model = model
        return self.result

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        self.cost_calls.append(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": model,
            }
        )
        return self.cost


@pytest.fixture
def recording_provider() -> RecordingProvider:
    provider = RecordingProvider()
    set_provider(provider)
    return provider
