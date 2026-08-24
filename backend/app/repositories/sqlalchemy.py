from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import (
    IntegrityError,
    InterfaceError,
    OperationalError,
    TimeoutError as SqlAlchemyTimeoutError,
)
from sqlalchemy.orm import Session, sessionmaker

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
from app.models_db import (
    ModelConfig,
    Project,
    ProviderCredential,
    RequestAttempt,
    SubApiKey,
    UsageEvent,
    User,
)
from app.repositories.base import PersistenceConflictError, PersistenceWriteError


_EXPECTED_WRITE_ERRORS = (
    OperationalError,
    InterfaceError,
    SqlAlchemyTimeoutError,
)


def _rollback_after_failure(session: Session) -> None:
    try:
        session.rollback()
    except _EXPECTED_WRITE_ERRORS:
        # Preserve the original safe failure when the unavailable connection
        # also refuses the best-effort rollback.
        pass


def _flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        _rollback_after_failure(session)
        raise PersistenceConflictError("Persistence constraint conflict") from exc
    except _EXPECTED_WRITE_ERRORS as exc:
        _rollback_after_failure(session)
        raise PersistenceWriteError("Persistence write failed") from exc


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _db_datetime(value: datetime) -> datetime:
    return _as_utc(value)


def _user_record(row: User) -> UserRecord:
    return UserRecord(
        id=row.id,
        email=row.email,
        name=row.name,
        password_hash=row.password_hash,
        role=row.role,
        created_at=_as_utc(row.created_at),
    )


def _project_record(row: Project) -> ProjectRecord:
    return ProjectRecord(
        id=row.id,
        name=row.name,
        description=row.description or "",
        status=row.status,
        created_at=_as_utc(row.created_at),
    )


def _provider_credential_record(row: ProviderCredential) -> ProviderCredentialRecord:
    return ProviderCredentialRecord(
        id=row.id,
        project_id=row.project_id,
        provider=row.provider,
        name=row.name,
        ciphertext=row.ciphertext,
        key_version=row.key_version,
        secret_hint=row.secret_hint,
        status=row.status,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def _model_config_record(row: ModelConfig) -> ModelConfigRecord:
    return ModelConfigRecord(
        id=row.id,
        project_id=row.project_id,
        public_model=row.public_model,
        provider=row.provider,
        provider_model=row.provider_model,
        credential_id=row.credential_id,
        input_cost_per_million_eur=Decimal(row.input_cost_per_million_eur),
        output_cost_per_million_eur=Decimal(row.output_cost_per_million_eur),
        enabled=row.enabled,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def _key_record(row: SubApiKey) -> KeyRecord:
    return KeyRecord(
        id=row.id,
        project_id=row.project_id,
        owner_id=row.owner_id,
        name=row.name,
        key_hash=row.key_hash,
        key_prefix=row.key_prefix,
        allowed_models=list(row.allowed_models or []),
        status=row.status,
        rate_limit_per_minute=row.rate_limit_per_minute,
        daily_request_limit=row.daily_request_limit,
        monthly_token_limit=row.monthly_token_limit,
        monthly_budget_eur=Decimal(row.monthly_budget_eur),
        max_tokens_per_request=row.max_tokens_per_request,
        created_at=_as_utc(row.created_at),
        expires_at=_as_utc(row.expires_at),
    )


def _usage_record(row: UsageEvent) -> UsageRecord:
    return UsageRecord(
        id=row.id,
        project_id=row.project_id,
        sub_api_key_id=row.sub_api_key_id,
        user_id=row.user_id,
        provider=row.provider,
        model=row.model,
        provider_model=row.provider_model,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        total_tokens=row.total_tokens,
        estimated_cost_eur=Decimal(row.estimated_cost_eur),
        currency=row.currency,
        latency_ms=row.latency_ms,
        status=row.status,
        created_at=_as_utc(row.created_at),
        error_code=row.error_code,
        request_attempt_id=row.request_attempt_id,
    )


def _request_attempt_record(row: RequestAttempt) -> RequestAttemptRecord:
    return RequestAttemptRecord(
        id=row.id,
        project_id=row.project_id,
        sub_api_key_id=row.sub_api_key_id,
        user_id=row.user_id,
        operation=row.operation,
        idempotency_key_digest=row.idempotency_key_digest,
        request_fingerprint_digest=row.request_fingerprint_digest,
        dispatch_token_digest=row.dispatch_token_digest,
        state=row.state,
        provider=row.provider,
        public_model=row.public_model,
        provider_model=row.provider_model,
        provider_result_id=row.provider_result_id,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        total_tokens=row.total_tokens,
        estimated_cost_eur=(
            Decimal(row.estimated_cost_eur)
            if row.estimated_cost_eur is not None
            else None
        ),
        currency=row.currency,
        latency_ms=row.latency_ms,
        error_code=row.error_code,
        error_http_status=row.error_http_status,
        error_public_message=row.error_public_message,
        error_retryable=row.error_retryable,
        idempotency_expires_at=(
            _as_utc(row.idempotency_expires_at)
            if row.idempotency_expires_at is not None
            else None
        ),
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, user_id: str) -> UserRecord | None:
        row = self.session.get(User, user_id)
        return _user_record(row) if row is not None else None

    def get_by_email(self, email: str) -> UserRecord | None:
        row = self.session.scalar(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )
        return _user_record(row) if row is not None else None

    def list(self) -> list[UserRecord]:
        rows = self.session.scalars(select(User).order_by(User.created_at)).all()
        return [_user_record(row) for row in rows]

    def add(self, user: UserRecord) -> None:
        self.session.add(
            User(
                id=user.id,
                email=user.email,
                name=user.name,
                password_hash=user.password_hash,
                role=user.role,
                created_at=_db_datetime(user.created_at),
                updated_at=_db_datetime(user.created_at),
            )
        )
        _flush(self.session)

    def set_password_hash(self, user_id: str, password_hash: str) -> UserRecord | None:
        row = self.session.get(User, user_id)
        if row is None:
            return None
        row.password_hash = password_hash
        row.updated_at = datetime.now(timezone.utc)
        _flush(self.session)
        return _user_record(row)


class SqlAlchemyProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, project_id: str) -> ProjectRecord | None:
        row = self.session.get(Project, project_id)
        return _project_record(row) if row is not None else None

    def add(self, project: ProjectRecord) -> None:
        self.session.add(
            Project(
                id=project.id,
                name=project.name,
                description=project.description,
                status=project.status,
                created_at=_db_datetime(project.created_at),
                updated_at=_db_datetime(project.created_at),
            )
        )
        _flush(self.session)


class SqlAlchemyProviderCredentialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, credential_id: str) -> ProviderCredentialRecord | None:
        row = self.session.get(ProviderCredential, credential_id)
        return _provider_credential_record(row) if row is not None else None

    def list(
        self,
        *,
        project_id: str | None = None,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[ProviderCredentialRecord]:
        statement = select(ProviderCredential).order_by(
            ProviderCredential.created_at
        )
        if project_id is not None:
            statement = statement.where(
                ProviderCredential.project_id == project_id
            )
        if provider is not None:
            statement = statement.where(
                ProviderCredential.provider == provider.strip().lower()
            )
        if status is not None:
            statement = statement.where(ProviderCredential.status == status)
        rows = self.session.scalars(statement).all()
        return [_provider_credential_record(row) for row in rows]

    def add(self, credential: ProviderCredentialRecord) -> None:
        self.session.add(
            ProviderCredential(
                id=credential.id,
                project_id=credential.project_id,
                provider=credential.provider,
                name=credential.name,
                ciphertext=credential.ciphertext,
                key_version=credential.key_version,
                secret_hint=credential.secret_hint,
                status=credential.status,
                created_at=_db_datetime(credential.created_at),
                updated_at=_db_datetime(credential.updated_at),
            )
        )
        _flush(self.session)

    def set_status(
        self, credential_id: str, status: str
    ) -> ProviderCredentialRecord | None:
        row = self.session.get(ProviderCredential, credential_id)
        if row is None:
            return None
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
        _flush(self.session)
        return _provider_credential_record(row)


class SqlAlchemyModelConfigRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, config_id: str) -> ModelConfigRecord | None:
        row = self.session.get(ModelConfig, config_id)
        return _model_config_record(row) if row is not None else None

    def get_enabled(
        self, project_id: str, public_model: str
    ) -> ModelConfigRecord | None:
        row = self.session.scalar(
            select(ModelConfig).where(
                ModelConfig.project_id == project_id,
                ModelConfig.public_model == public_model,
                ModelConfig.enabled.is_(True),
            )
        )
        return _model_config_record(row) if row is not None else None

    def list(
        self,
        *,
        project_id: str | None = None,
        enabled: bool | None = None,
    ) -> list[ModelConfigRecord]:
        statement = select(ModelConfig).order_by(ModelConfig.created_at)
        if project_id is not None:
            statement = statement.where(ModelConfig.project_id == project_id)
        if enabled is not None:
            statement = statement.where(ModelConfig.enabled.is_(enabled))
        rows = self.session.scalars(statement).all()
        return [_model_config_record(row) for row in rows]

    def add(self, config: ModelConfigRecord) -> None:
        self.session.add(
            ModelConfig(
                id=config.id,
                project_id=config.project_id,
                public_model=config.public_model,
                provider=config.provider,
                provider_model=config.provider_model,
                credential_id=config.credential_id,
                input_cost_per_million_eur=config.input_cost_per_million_eur,
                output_cost_per_million_eur=config.output_cost_per_million_eur,
                enabled=config.enabled,
                created_at=_db_datetime(config.created_at),
                updated_at=_db_datetime(config.updated_at),
            )
        )
        _flush(self.session)

    def set_enabled(self, config_id: str, enabled: bool) -> ModelConfigRecord | None:
        row = self.session.get(ModelConfig, config_id)
        if row is None:
            return None
        row.enabled = enabled
        row.updated_at = datetime.now(timezone.utc)
        _flush(self.session)
        return _model_config_record(row)


class SqlAlchemyKeyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, key_id: str) -> KeyRecord | None:
        row = self.session.get(SubApiKey, key_id)
        return _key_record(row) if row is not None else None

    def get_by_hash(self, key_hash: str) -> KeyRecord | None:
        row = self.session.scalar(
            select(SubApiKey).where(SubApiKey.key_hash == key_hash)
        )
        return _key_record(row) if row is not None else None

    def list(self, owner_id: str | None = None) -> list[KeyRecord]:
        statement = select(SubApiKey).order_by(SubApiKey.created_at)
        if owner_id is not None:
            statement = statement.where(SubApiKey.owner_id == owner_id)
        rows = self.session.scalars(statement).all()
        return [_key_record(row) for row in rows]

    def add(self, key: KeyRecord) -> None:
        self.session.add(
            SubApiKey(
                id=key.id,
                project_id=key.project_id,
                owner_id=key.owner_id,
                name=key.name,
                key_hash=key.key_hash,
                key_prefix=key.key_prefix,
                allowed_models=list(key.allowed_models),
                allowed_pipelines=[],
                rate_limit_per_minute=key.rate_limit_per_minute,
                daily_request_limit=key.daily_request_limit,
                monthly_token_limit=key.monthly_token_limit,
                monthly_budget_eur=key.monthly_budget_eur,
                max_tokens_per_request=key.max_tokens_per_request,
                expires_at=_db_datetime(key.expires_at),
                status=key.status,
                created_at=_db_datetime(key.created_at),
                updated_at=_db_datetime(key.created_at),
            )
        )
        _flush(self.session)

    def set_status(self, key_id: str, status: str) -> KeyRecord | None:
        row = self.session.get(SubApiKey, key_id)
        if row is None:
            return None
        row.status = status
        row.updated_at = datetime.now(timezone.utc)
        _flush(self.session)
        return _key_record(row)


class SqlAlchemyRequestAttemptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _read(self, operation):
        try:
            return operation()
        except _EXPECTED_WRITE_ERRORS as exc:
            _rollback_after_failure(self.session)
            raise PersistenceWriteError("Persistence read failed") from exc

    def get_by_id(self, attempt_id: str) -> RequestAttemptRecord | None:
        row = self._read(lambda: self.session.get(RequestAttempt, attempt_id))
        return _request_attempt_record(row) if row is not None else None

    def get_by_identity(
        self,
        sub_api_key_id: str,
        operation: str,
        idempotency_key_digest: str,
    ) -> RequestAttemptRecord | None:
        row = self._read(
            lambda: self.session.scalar(
                select(RequestAttempt).where(
                    RequestAttempt.sub_api_key_id == sub_api_key_id,
                    RequestAttempt.operation == operation,
                    RequestAttempt.idempotency_key_digest
                    == idempotency_key_digest,
                )
            )
        )
        return _request_attempt_record(row) if row is not None else None

    def add(self, attempt: RequestAttemptRecord) -> None:
        self.session.add(
            RequestAttempt(
                id=attempt.id,
                project_id=attempt.project_id,
                sub_api_key_id=attempt.sub_api_key_id,
                user_id=attempt.user_id,
                operation=attempt.operation,
                idempotency_key_digest=attempt.idempotency_key_digest,
                request_fingerprint_digest=attempt.request_fingerprint_digest,
                dispatch_token_digest=attempt.dispatch_token_digest,
                state=attempt.state,
                provider=attempt.provider,
                public_model=attempt.public_model,
                provider_model=attempt.provider_model,
                provider_result_id=attempt.provider_result_id,
                input_tokens=attempt.input_tokens,
                output_tokens=attempt.output_tokens,
                total_tokens=attempt.total_tokens,
                estimated_cost_eur=attempt.estimated_cost_eur,
                currency=attempt.currency,
                latency_ms=attempt.latency_ms,
                error_code=attempt.error_code,
                error_http_status=attempt.error_http_status,
                error_public_message=attempt.error_public_message,
                error_retryable=attempt.error_retryable,
                idempotency_expires_at=(
                    _db_datetime(attempt.idempotency_expires_at)
                    if attempt.idempotency_expires_at is not None
                    else None
                ),
                created_at=_db_datetime(attempt.created_at),
                updated_at=_db_datetime(attempt.updated_at),
            )
        )
        _flush(self.session)

    def transition(
        self,
        attempt_id: str,
        *,
        expected_state: RequestAttemptState,
        dispatch_token_digest: str,
        replacement: RequestAttemptRecord,
    ) -> bool:
        if replacement.id != attempt_id:
            raise ValueError("Attempt transition changed immutable identity")
        statement = (
            update(RequestAttempt)
            .where(
                RequestAttempt.id == attempt_id,
                RequestAttempt.state == expected_state,
                RequestAttempt.dispatch_token_digest == dispatch_token_digest,
            )
            .values(
                state=replacement.state,
                provider_result_id=replacement.provider_result_id,
                input_tokens=replacement.input_tokens,
                output_tokens=replacement.output_tokens,
                total_tokens=replacement.total_tokens,
                estimated_cost_eur=replacement.estimated_cost_eur,
                currency=replacement.currency,
                latency_ms=replacement.latency_ms,
                error_code=replacement.error_code,
                error_http_status=replacement.error_http_status,
                error_public_message=replacement.error_public_message,
                error_retryable=replacement.error_retryable,
                idempotency_expires_at=(
                    _db_datetime(replacement.idempotency_expires_at)
                    if replacement.idempotency_expires_at is not None
                    else None
                ),
                updated_at=_db_datetime(replacement.updated_at),
            )
            .execution_options(synchronize_session=False)
        )
        try:
            result = self.session.execute(statement)
        except IntegrityError as exc:
            _rollback_after_failure(self.session)
            raise PersistenceConflictError("Persistence constraint conflict") from exc
        except _EXPECTED_WRITE_ERRORS as exc:
            _rollback_after_failure(self.session)
            raise PersistenceWriteError("Persistence write failed") from exc
        return result.rowcount == 1

    def retire_expired_identity(
        self,
        attempt_id: str,
        *,
        expected_idempotency_key_digest: str,
        now: datetime,
    ) -> bool:
        statement = (
            update(RequestAttempt)
            .where(
                RequestAttempt.id == attempt_id,
                RequestAttempt.state.in_(("succeeded", "provider_failed")),
                RequestAttempt.idempotency_key_digest
                == expected_idempotency_key_digest,
                RequestAttempt.idempotency_expires_at.is_not(None),
                RequestAttempt.idempotency_expires_at <= _db_datetime(now),
            )
            .values(
                idempotency_key_digest=None,
                request_fingerprint_digest=None,
                updated_at=_db_datetime(now),
            )
            .execution_options(synchronize_session=False)
        )
        try:
            result = self.session.execute(statement)
        except IntegrityError as exc:
            _rollback_after_failure(self.session)
            raise PersistenceConflictError("Persistence constraint conflict") from exc
        except _EXPECTED_WRITE_ERRORS as exc:
            _rollback_after_failure(self.session)
            raise PersistenceWriteError("Persistence write failed") from exc
        return result.rowcount == 1


class SqlAlchemyUsageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, usage_id: str) -> UsageRecord | None:
        row = self.session.get(UsageEvent, usage_id)
        return _usage_record(row) if row is not None else None

    def get_by_request_attempt_id(
        self, request_attempt_id: str
    ) -> UsageRecord | None:
        try:
            row = self.session.scalar(
                select(UsageEvent).where(
                    UsageEvent.request_attempt_id == request_attempt_id
                )
            )
        except _EXPECTED_WRITE_ERRORS as exc:
            _rollback_after_failure(self.session)
            raise PersistenceWriteError("Persistence read failed") from exc
        return _usage_record(row) if row is not None else None

    def list(
        self,
        *,
        user_id: str | None = None,
        key_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[UsageRecord]:
        statement = select(UsageEvent).order_by(UsageEvent.created_at.desc())
        if user_id is not None:
            statement = statement.where(UsageEvent.user_id == user_id)
        if key_id is not None:
            statement = statement.where(UsageEvent.sub_api_key_id == key_id)
        statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        rows = self.session.scalars(statement).all()
        return [_usage_record(row) for row in rows]

    def add(self, usage: UsageRecord) -> None:
        if usage.request_attempt_id is not None:
            try:
                attempt_attribution = self.session.execute(
                    select(
                        RequestAttempt.project_id,
                        RequestAttempt.sub_api_key_id,
                        RequestAttempt.user_id,
                    ).where(RequestAttempt.id == usage.request_attempt_id)
                ).one_or_none()
            except _EXPECTED_WRITE_ERRORS as exc:
                _rollback_after_failure(self.session)
                raise PersistenceWriteError("Persistence read failed") from exc
            if attempt_attribution is None or tuple(attempt_attribution) != (
                usage.project_id,
                usage.sub_api_key_id,
                usage.user_id,
            ):
                raise PersistenceConflictError("Persistence constraint conflict")
        self.session.add(
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
                created_at=_db_datetime(usage.created_at),
            )
        )
        _flush(self.session)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self):
        self.session = self.session_factory()
        self.users = SqlAlchemyUserRepository(self.session)
        self.projects = SqlAlchemyProjectRepository(self.session)
        self.provider_credentials = SqlAlchemyProviderCredentialRepository(self.session)
        self.model_configs = SqlAlchemyModelConfigRepository(self.session)
        self.keys = SqlAlchemyKeyRepository(self.session)
        self.usage = SqlAlchemyUsageRepository(self.session)
        self.attempts = SqlAlchemyRequestAttemptRepository(self.session)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.session is None:
            return
        if exc_type is not None:
            _rollback_after_failure(self.session)
        self.session.close()

    def commit(self) -> None:
        assert self.session is not None
        try:
            self.session.commit()
        except IntegrityError as exc:
            _rollback_after_failure(self.session)
            raise PersistenceConflictError("Persistence constraint conflict") from exc
        except _EXPECTED_WRITE_ERRORS as exc:
            _rollback_after_failure(self.session)
            raise PersistenceWriteError("Persistence write failed") from exc

    def rollback(self) -> None:
        assert self.session is not None
        self.session.rollback()


class SqlAlchemyUnitOfWorkFactory:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def __call__(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)
