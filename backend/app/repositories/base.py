from collections.abc import Callable
from datetime import datetime
from typing import Protocol, Self

from app.domain import (
    KeyRecord,
    ModelConfigRecord,
    ProjectRecord,
    ProviderCredentialRecord,
    RequestAttemptRecord,
    RequestAttemptState,
    UsageRecord,
    UserRecord,
)


class PersistenceConflictError(RuntimeError):
    """A durable uniqueness or integrity constraint rejected a write."""


class PersistenceWriteError(RuntimeError):
    """An expected persistence availability failure prevented a write."""


class UserRepository(Protocol):
    def get_by_id(self, user_id: str) -> UserRecord | None: ...
    def get_by_email(self, email: str) -> UserRecord | None: ...
    def list(self) -> list[UserRecord]: ...
    def add(self, user: UserRecord) -> None: ...
    def set_password_hash(self, user_id: str, password_hash: str) -> UserRecord | None: ...


class ProjectRepository(Protocol):
    def get_by_id(self, project_id: str) -> ProjectRecord | None: ...
    def add(self, project: ProjectRecord) -> None: ...


class ProviderCredentialRepository(Protocol):
    def get_by_id(self, credential_id: str) -> ProviderCredentialRecord | None: ...
    def list(
        self,
        *,
        project_id: str | None = None,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[ProviderCredentialRecord]: ...
    def add(self, credential: ProviderCredentialRecord) -> None: ...
    def set_status(
        self, credential_id: str, status: str
    ) -> ProviderCredentialRecord | None: ...


class ModelConfigRepository(Protocol):
    def get_by_id(self, config_id: str) -> ModelConfigRecord | None: ...
    def get_enabled(
        self, project_id: str, public_model: str
    ) -> ModelConfigRecord | None: ...
    def list(
        self,
        *,
        project_id: str | None = None,
        enabled: bool | None = None,
    ) -> list[ModelConfigRecord]: ...
    def add(self, config: ModelConfigRecord) -> None: ...
    def set_enabled(
        self, config_id: str, enabled: bool
    ) -> ModelConfigRecord | None: ...


class KeyRepository(Protocol):
    def get_by_id(self, key_id: str) -> KeyRecord | None: ...
    def get_by_hash(self, key_hash: str) -> KeyRecord | None: ...
    def list(self, owner_id: str | None = None) -> list[KeyRecord]: ...
    def add(self, key: KeyRecord) -> None: ...
    def set_status(self, key_id: str, status: str) -> KeyRecord | None: ...


class UsageRepository(Protocol):
    def get_by_id(self, usage_id: str) -> UsageRecord | None: ...
    def get_by_request_attempt_id(
        self, request_attempt_id: str
    ) -> UsageRecord | None: ...
    def list(
        self,
        *,
        user_id: str | None = None,
        key_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[UsageRecord]: ...
    def add(self, usage: UsageRecord) -> None: ...


class RequestAttemptRepository(Protocol):
    def get_by_id(self, attempt_id: str) -> RequestAttemptRecord | None: ...
    def get_by_identity(
        self,
        sub_api_key_id: str,
        operation: str,
        idempotency_key_digest: str,
    ) -> RequestAttemptRecord | None: ...
    def add(self, attempt: RequestAttemptRecord) -> None: ...
    def transition(
        self,
        attempt_id: str,
        *,
        expected_state: RequestAttemptState,
        dispatch_token_digest: str,
        replacement: RequestAttemptRecord,
    ) -> bool: ...
    def retire_expired_identity(
        self,
        attempt_id: str,
        *,
        expected_idempotency_key_digest: str,
        now: datetime,
    ) -> bool: ...


class AbstractUnitOfWork(Protocol):
    users: UserRepository
    projects: ProjectRepository
    provider_credentials: ProviderCredentialRepository
    model_configs: ModelConfigRepository
    keys: KeyRepository
    usage: UsageRepository
    attempts: RequestAttemptRepository

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], AbstractUnitOfWork]
