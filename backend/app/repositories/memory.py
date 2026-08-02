from _thread import LockType
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hmac import compare_digest
from threading import Lock

from app.domain import (
    KeyRecord,
    ModelConfigRecord,
    ProjectRecord,
    ProviderCredentialRecord,
    UsageRecord,
    UserRecord,
)
from app.repositories.base import PersistenceConflictError


@dataclass
class MemoryStore:
    users: list[UserRecord] = field(default_factory=list)
    projects: list[ProjectRecord] = field(default_factory=list)
    provider_credentials: list[ProviderCredentialRecord] = field(default_factory=list)
    model_configs: list[ModelConfigRecord] = field(default_factory=list)
    keys: list[KeyRecord] = field(default_factory=list)
    usage: list[UsageRecord] = field(default_factory=list)
    _uow_lock: LockType = field(
        default_factory=Lock,
        init=False,
        repr=False,
        compare=False,
    )


def _copy_store(store: MemoryStore) -> MemoryStore:
    """Copy persisted values without copying the store's synchronization lock."""
    return MemoryStore(
        users=deepcopy(store.users),
        projects=deepcopy(store.projects),
        provider_credentials=deepcopy(store.provider_credentials),
        model_configs=deepcopy(store.model_configs),
        keys=deepcopy(store.keys),
        usage=deepcopy(store.usage),
    )


class MemoryUserRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_by_id(self, user_id: str) -> UserRecord | None:
        return next((user for user in self.store.users if user.id == user_id), None)

    def get_by_email(self, email: str) -> UserRecord | None:
        normalized = email.strip().lower()
        return next((user for user in self.store.users if user.email.lower() == normalized), None)

    def list(self) -> list[UserRecord]:
        return list(self.store.users)

    def add(self, user: UserRecord) -> None:
        self.store.users.append(user)

    def set_password_hash(self, user_id: str, password_hash: str) -> UserRecord | None:
        user = self.get_by_id(user_id)
        if user is not None:
            user.password_hash = password_hash
        return user


class MemoryProjectRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_by_id(self, project_id: str) -> ProjectRecord | None:
        return next((project for project in self.store.projects if project.id == project_id), None)

    def add(self, project: ProjectRecord) -> None:
        self.store.projects.append(project)


class MemoryProviderCredentialRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_by_id(self, credential_id: str) -> ProviderCredentialRecord | None:
        return next(
            (
                credential
                for credential in self.store.provider_credentials
                if credential.id == credential_id
            ),
            None,
        )

    def list(
        self,
        *,
        project_id: str | None = None,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[ProviderCredentialRecord]:
        credentials = self.store.provider_credentials
        if project_id is not None:
            credentials = [
                credential
                for credential in credentials
                if credential.project_id == project_id
            ]
        if provider is not None:
            normalized_provider = provider.strip().lower()
            credentials = [
                credential
                for credential in credentials
                if credential.provider == normalized_provider
            ]
        if status is not None:
            credentials = [
                credential for credential in credentials if credential.status == status
            ]
        return sorted(credentials, key=lambda credential: credential.created_at)

    def add(self, credential: ProviderCredentialRecord) -> None:
        project_exists = any(
            project.id == credential.project_id for project in self.store.projects
        )
        duplicate = any(
            existing.id == credential.id
            or (
                existing.project_id,
                existing.provider,
                existing.name,
            )
            == (credential.project_id, credential.provider, credential.name)
            for existing in self.store.provider_credentials
        )
        valid = (
            project_exists
            and credential.provider == credential.provider.strip().lower()
            and bool(credential.provider)
            and bool(credential.name.strip())
            and bool(credential.ciphertext)
            and bool(credential.key_version.strip())
            and bool(credential.secret_hint)
            and credential.status in {"active", "revoked"}
        )
        if duplicate or not valid:
            raise PersistenceConflictError("Persistence constraint conflict")
        self.store.provider_credentials.append(credential)

    def set_status(
        self, credential_id: str, status: str
    ) -> ProviderCredentialRecord | None:
        credential = self.get_by_id(credential_id)
        if credential is not None:
            if status not in {"active", "revoked"}:
                raise PersistenceConflictError("Persistence constraint conflict")
            credential.status = status  # type: ignore[assignment]
            credential.updated_at = datetime.now(timezone.utc)
        return credential


class MemoryModelConfigRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_by_id(self, config_id: str) -> ModelConfigRecord | None:
        return next(
            (config for config in self.store.model_configs if config.id == config_id),
            None,
        )

    def get_enabled(
        self, project_id: str, public_model: str
    ) -> ModelConfigRecord | None:
        return next(
            (
                config
                for config in self.store.model_configs
                if config.project_id == project_id
                and config.public_model == public_model
                and config.enabled
            ),
            None,
        )

    def list(
        self,
        *,
        project_id: str | None = None,
        enabled: bool | None = None,
    ) -> list[ModelConfigRecord]:
        configs = self.store.model_configs
        if project_id is not None:
            configs = [config for config in configs if config.project_id == project_id]
        if enabled is not None:
            configs = [config for config in configs if config.enabled is enabled]
        return sorted(configs, key=lambda config: config.created_at)

    def add(self, config: ModelConfigRecord) -> None:
        project_exists = any(
            project.id == config.project_id for project in self.store.projects
        )
        duplicate = any(
            existing.id == config.id
            or (existing.project_id, existing.public_model)
            == (config.project_id, config.public_model)
            for existing in self.store.model_configs
        )
        credential = (
            None
            if config.credential_id is None
            else next(
                (
                    item
                    for item in self.store.provider_credentials
                    if item.id == config.credential_id
                ),
                None,
            )
        )
        valid_credential = (
            config.provider == "mock" and config.credential_id is None
        ) or (
            config.provider != "mock"
            and credential is not None
            and credential.project_id == config.project_id
            and credential.provider == config.provider
        )
        valid = (
            project_exists
            and config.provider == config.provider.strip().lower()
            and bool(config.provider)
            and bool(config.public_model.strip())
            and bool(config.provider_model.strip())
            and valid_credential
            and config.input_cost_per_million_eur >= 0
            and config.output_cost_per_million_eur >= 0
        )
        if duplicate or not valid:
            raise PersistenceConflictError("Persistence constraint conflict")
        self.store.model_configs.append(config)

    def set_enabled(self, config_id: str, enabled: bool) -> ModelConfigRecord | None:
        config = self.get_by_id(config_id)
        if config is not None:
            config.enabled = enabled
            config.updated_at = datetime.now(timezone.utc)
        return config


class MemoryKeyRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_by_id(self, key_id: str) -> KeyRecord | None:
        return next((key for key in self.store.keys if key.id == key_id), None)

    def get_by_hash(self, key_hash: str) -> KeyRecord | None:
        return next(
            (
                key
                for key in self.store.keys
                if compare_digest(key.key_hash, key_hash)
            ),
            None,
        )

    def list(self, owner_id: str | None = None) -> list[KeyRecord]:
        if owner_id is None:
            return list(self.store.keys)
        return [key for key in self.store.keys if key.owner_id == owner_id]

    def add(self, key: KeyRecord) -> None:
        self.store.keys.append(key)

    def set_status(self, key_id: str, status: str) -> KeyRecord | None:
        key = self.get_by_id(key_id)
        if key is not None:
            key.status = status  # type: ignore[assignment]
        return key


class MemoryUsageRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_by_id(self, usage_id: str) -> UsageRecord | None:
        return next((event for event in self.store.usage if event.id == usage_id), None)

    def list(
        self,
        *,
        user_id: str | None = None,
        key_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[UsageRecord]:
        events = self.store.usage
        if user_id is not None:
            events = [event for event in events if event.user_id == user_id]
        if key_id is not None:
            events = [event for event in events if event.sub_api_key_id == key_id]
        ordered = sorted(events, key=lambda event: event.created_at, reverse=True)
        return ordered[offset:] if limit is None else ordered[offset : offset + limit]

    def add(self, usage: UsageRecord) -> None:
        self.store.usage.append(usage)


class MemoryUnitOfWork:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.users: MemoryUserRepository
        self.projects: MemoryProjectRepository
        self.provider_credentials: MemoryProviderCredentialRepository
        self.model_configs: MemoryModelConfigRepository
        self.keys: MemoryKeyRepository
        self.usage: MemoryUsageRepository
        self._working_store: MemoryStore | None = None
        self._active = False

    def _bind_repositories(self, store: MemoryStore) -> None:
        self.users = MemoryUserRepository(store)
        self.projects = MemoryProjectRepository(store)
        self.provider_credentials = MemoryProviderCredentialRepository(store)
        self.model_configs = MemoryModelConfigRepository(store)
        self.keys = MemoryKeyRepository(store)
        self.usage = MemoryUsageRepository(store)

    def _require_working_store(self) -> MemoryStore:
        if not self._active or self._working_store is None:
            raise RuntimeError("Memory unit of work is not active")
        return self._working_store

    def __enter__(self):
        if self._active:
            raise RuntimeError("Memory unit of work is already active")

        self.store._uow_lock.acquire()
        try:
            self._working_store = _copy_store(self.store)
            self._bind_repositories(self._working_store)
            self._active = True
        except BaseException:
            self._working_store = None
            self.store._uow_lock.release()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if not self._active:
            return

        # Like a SQLAlchemy Session, leaving the scope never commits implicitly.
        # The working copy can be discarded regardless of whether the scope
        # exits normally or because of an exception.
        self._working_store = None
        self._active = False
        self.store._uow_lock.release()

    def commit(self) -> None:
        working_store = self._require_working_store()
        committed = _copy_store(working_store)
        self.store.users[:] = committed.users
        self.store.projects[:] = committed.projects
        self.store.provider_credentials[:] = committed.provider_credentials
        self.store.model_configs[:] = committed.model_configs
        self.store.keys[:] = committed.keys
        self.store.usage[:] = committed.usage

    def rollback(self) -> None:
        self._require_working_store()
        self._working_store = _copy_store(self.store)
        self._bind_repositories(self._working_store)


class MemoryUnitOfWorkFactory:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def __call__(self) -> MemoryUnitOfWork:
        return MemoryUnitOfWork(self.store)
