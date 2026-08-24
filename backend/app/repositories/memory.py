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
    RequestAttemptRecord,
    RequestAttemptState,
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
    attempts: list[RequestAttemptRecord] = field(default_factory=list)
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
        attempts=deepcopy(store.attempts),
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


_ATTEMPT_STATES = {
    "dispatch_claimed",
    "succeeded",
    "provider_failed",
    "provider_outcome_uncertain",
    "finalization_failed",
}
_RESOLVED_ATTEMPT_STATES = {"succeeded", "provider_failed"}
_ATTEMPT_MUTABLE_FIELDS = (
    "state",
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
    "updated_at",
)


def _is_valid_attempt(attempt: RequestAttemptRecord, store: MemoryStore) -> bool:
    key_digest = attempt.idempotency_key_digest
    fingerprint_digest = attempt.request_fingerprint_digest
    project_exists = any(item.id == attempt.project_id for item in store.projects)
    key_exists = any(item.id == attempt.sub_api_key_id for item in store.keys)
    user_exists = any(item.id == attempt.user_id for item in store.users)
    return (
        project_exists
        and key_exists
        and user_exists
        and attempt.state in _ATTEMPT_STATES
        and ((key_digest is None) == (fingerprint_digest is None))
        and (key_digest is None or len(key_digest) == 64)
        and (fingerprint_digest is None or len(fingerprint_digest) == 64)
        and len(attempt.dispatch_token_digest) == 64
        and (attempt.input_tokens is None or attempt.input_tokens >= 0)
        and (attempt.output_tokens is None or attempt.output_tokens >= 0)
        and (attempt.total_tokens is None or attempt.total_tokens >= 0)
        and (
            attempt.estimated_cost_eur is None
            or attempt.estimated_cost_eur >= 0
        )
        and (
            attempt.currency is None
            or (
                len(attempt.currency) == 3
                and attempt.currency == attempt.currency.upper()
            )
        )
        and (
            (attempt.estimated_cost_eur is None and attempt.currency is None)
            or (
                attempt.estimated_cost_eur is not None
                and attempt.currency == "EUR"
            )
        )
        and (attempt.latency_ms is None or attempt.latency_ms >= 0)
        and (
            attempt.error_http_status is None
            or 400 <= attempt.error_http_status <= 599
        )
    )


class MemoryRequestAttemptRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_by_id(self, attempt_id: str) -> RequestAttemptRecord | None:
        return next(
            (attempt for attempt in self.store.attempts if attempt.id == attempt_id),
            None,
        )

    def get_by_identity(
        self,
        sub_api_key_id: str,
        operation: str,
        idempotency_key_digest: str,
    ) -> RequestAttemptRecord | None:
        return next(
            (
                attempt
                for attempt in self.store.attempts
                if attempt.sub_api_key_id == sub_api_key_id
                and attempt.operation == operation
                and attempt.idempotency_key_digest == idempotency_key_digest
            ),
            None,
        )

    def add(self, attempt: RequestAttemptRecord) -> None:
        duplicate_id = any(item.id == attempt.id for item in self.store.attempts)
        duplicate_identity = (
            attempt.idempotency_key_digest is not None
            and any(
                item.sub_api_key_id == attempt.sub_api_key_id
                and item.operation == attempt.operation
                and item.idempotency_key_digest == attempt.idempotency_key_digest
                for item in self.store.attempts
            )
        )
        if duplicate_id or duplicate_identity or not _is_valid_attempt(
            attempt, self.store
        ):
            raise PersistenceConflictError("Persistence constraint conflict")
        self.store.attempts.append(attempt)

    def transition(
        self,
        attempt_id: str,
        *,
        expected_state: RequestAttemptState,
        dispatch_token_digest: str,
        replacement: RequestAttemptRecord,
    ) -> bool:
        current = self.get_by_id(attempt_id)
        if (
            current is None
            or current.state != expected_state
            or not compare_digest(
                current.dispatch_token_digest, dispatch_token_digest
            )
        ):
            return False
        if replacement.id != attempt_id:
            raise ValueError("Attempt transition changed immutable identity")
        candidate = deepcopy(current)
        for field_name in _ATTEMPT_MUTABLE_FIELDS:
            setattr(candidate, field_name, deepcopy(getattr(replacement, field_name)))
        if not _is_valid_attempt(candidate, self.store):
            raise PersistenceConflictError("Persistence constraint conflict")
        index = self.store.attempts.index(current)
        self.store.attempts[index] = candidate
        return True

    def retire_expired_identity(
        self,
        attempt_id: str,
        *,
        expected_idempotency_key_digest: str,
        now: datetime,
    ) -> bool:
        attempt = self.get_by_id(attempt_id)
        if (
            attempt is None
            or attempt.state not in _RESOLVED_ATTEMPT_STATES
            or attempt.idempotency_key_digest is None
            or not compare_digest(
                attempt.idempotency_key_digest, expected_idempotency_key_digest
            )
            or attempt.idempotency_expires_at is None
        ):
            return False
        normalized_now = (
            now.replace(tzinfo=timezone.utc)
            if now.tzinfo is None or now.utcoffset() is None
            else now.astimezone(timezone.utc)
        )
        expires_at = attempt.idempotency_expires_at
        normalized_expiry = (
            expires_at.replace(tzinfo=timezone.utc)
            if expires_at.tzinfo is None or expires_at.utcoffset() is None
            else expires_at.astimezone(timezone.utc)
        )
        if normalized_expiry > normalized_now:
            return False
        attempt.idempotency_key_digest = None
        attempt.request_fingerprint_digest = None
        attempt.updated_at = normalized_now
        return True


class MemoryUsageRepository:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def get_by_id(self, usage_id: str) -> UsageRecord | None:
        return next((event for event in self.store.usage if event.id == usage_id), None)

    def get_by_request_attempt_id(
        self, request_attempt_id: str
    ) -> UsageRecord | None:
        return next(
            (
                event
                for event in self.store.usage
                if event.request_attempt_id == request_attempt_id
            ),
            None,
        )

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
        duplicate = any(event.id == usage.id for event in self.store.usage)
        if usage.request_attempt_id is not None:
            attempt = next(
                (
                    item
                    for item in self.store.attempts
                    if item.id == usage.request_attempt_id
                ),
                None,
            )
            duplicate_attempt_link = any(
                event.request_attempt_id == usage.request_attempt_id
                for event in self.store.usage
            )
            matching_attribution = attempt is not None and (
                attempt.project_id,
                attempt.sub_api_key_id,
                attempt.user_id,
            ) == (usage.project_id, usage.sub_api_key_id, usage.user_id)
            if duplicate_attempt_link or not matching_attribution:
                raise PersistenceConflictError("Persistence constraint conflict")
        if duplicate:
            raise PersistenceConflictError("Persistence constraint conflict")
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
        self.attempts: MemoryRequestAttemptRepository
        self._working_store: MemoryStore | None = None
        self._active = False

    def _bind_repositories(self, store: MemoryStore) -> None:
        self.users = MemoryUserRepository(store)
        self.projects = MemoryProjectRepository(store)
        self.provider_credentials = MemoryProviderCredentialRepository(store)
        self.model_configs = MemoryModelConfigRepository(store)
        self.keys = MemoryKeyRepository(store)
        self.usage = MemoryUsageRepository(store)
        self.attempts = MemoryRequestAttemptRepository(store)

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
        self.store.attempts[:] = committed.attempts

    def rollback(self) -> None:
        self._require_working_store()
        self._working_store = _copy_store(self.store)
        self._bind_repositories(self._working_store)


class MemoryUnitOfWorkFactory:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def __call__(self) -> MemoryUnitOfWork:
        return MemoryUnitOfWork(self.store)
