from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from hashlib import sha256
import hmac
import json
import re
import secrets
import uuid

from pydantic import SecretStr

from app.auth import get_password_hash, verify_password
from app.config import settings
from app.credential_security import (
    CredentialCipher,
    CredentialDecryptionError,
    CredentialEncryptionConfigurationError,
    CredentialKeyUnavailableError,
    EncryptedCredential,
    credential_secret_hint,
)
from app.domain import (
    KeyRecord,
    ModelConfigRecord,
    ProviderCredentialRecord,
    RequestAttemptRecord,
    UsageRecord,
    UserRecord,
)
from app.key_security import generate_sub_api_key, hash_sub_api_key, sub_api_key_prefix
from app.models import (
    CreateKeyRequest,
    CreateModelConfigRequest,
    CreateProviderCredentialRequest,
    CreateUserRequest,
    ChatCompletionRequest,
)
from app.policies import PolicyCode, evaluate_static_request_policy
from app.providers import (
    GeminiProvider,
    OpenAIProvider,
    Provider,
    ProviderError,
    ProviderExecutionCertainty,
    get_provider,
)
from app.repositories.base import (
    PersistenceConflictError,
    PersistenceWriteError,
    UnitOfWorkFactory,
)


class DomainError(RuntimeError):
    pass


class AuthenticationError(DomainError):
    pass


class AuthorizationError(DomainError):
    def __init__(self, message: str, *, code: PolicyCode | None = None) -> None:
        super().__init__(message)
        self.code = code


class ConflictError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ConfigurationError(DomainError):
    pass


RuntimeErrorDetail = str | dict[str, str | bool]


class RuntimeAttemptContractError(DomainError):
    """A fixed, sanitized runtime-attempt response owned by the service."""

    def __init__(
        self,
        status_code: int,
        detail: RuntimeErrorDetail,
        *,
        attempt_id: str | None = None,
    ) -> None:
        super().__init__(detail if isinstance(detail, str) else detail["message"])
        self.status_code = status_code
        self.detail = detail
        self.attempt_id = attempt_id


@dataclass(frozen=True)
class RuntimeAttemptIdentity:
    operation: str
    idempotency_key_digest: str | None
    request_fingerprint_digest: str | None


@dataclass(frozen=True, repr=False)
class OwnedRuntimeAttempt:
    record: RequestAttemptRecord
    dispatch_token: bytes = field(repr=False)

    @property
    def attempt_id(self) -> str:
        return self.record.id

    def __repr__(self) -> str:
        return (
            "OwnedRuntimeAttempt("
            f"attempt_id={self.record.id!r}, dispatch_token='<redacted>')"
        )


@dataclass(frozen=True)
class RuntimeSuccessOutcome:
    provider_result_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_eur: Decimal
    currency: str
    latency_ms: int


@dataclass(frozen=True)
class RuntimeProviderFailureOutcome:
    code: str
    public_message: str
    status_code: int
    retryable: bool
    execution_certainty: ProviderExecutionCertainty
    latency_ms: int

    @classmethod
    def from_error(
        cls,
        error: ProviderError,
        *,
        latency_ms: int,
    ) -> "RuntimeProviderFailureOutcome":
        return cls(
            code=error.code,
            public_message=error.public_message,
            status_code=error.status_code,
            retryable=error.retryable,
            execution_certainty=error.execution_certainty,
            latency_ms=latency_ms,
        )


@dataclass(frozen=True)
class CreatedKey:
    record: KeyRecord
    raw_key: str


@dataclass(frozen=True)
class ResolvedProviderRoute:
    provider: Provider = field(repr=False)
    provider_name: str
    public_model: str
    provider_model: str


_RUNTIME_OPERATION = "chat.completions"
_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[\x21-\x7e]{1,255}$")
_PROVIDER_RESULT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,255}$")
_EXPECTED_PERSISTENCE_ERRORS = (
    PersistenceConflictError,
    PersistenceWriteError,
)
_ATTEMPT_UNAVAILABLE_DETAIL = "Request attempt is unavailable"
_FINALIZATION_UNAVAILABLE_DETAIL = "Usage finalization is unavailable"
_INVALID_USAGE_DETAIL = "Provider returned invalid usage data"
_COST_QUANTUM = Decimal("0.00000001")
_MAX_STORABLE_COST_EUR = Decimal("9999999999.99999999")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _idempotency_hmac(domain: str, *parts: str) -> str:
    pepper = settings.idempotency_key_pepper.get_secret_value().encode("utf-8")
    payload = b"\0".join(
        [f"tailer:{domain}:v1".encode("ascii"), *(part.encode("utf-8") for part in parts)]
    )
    return hmac.new(pepper, payload, sha256).hexdigest()


def _canonical_request(request: ChatCompletionRequest) -> str:
    return json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _dispatch_token_digest(token: bytes) -> str:
    return sha256(token).hexdigest()


def _safe_provider_result_id(value: str) -> str | None:
    return value if _PROVIDER_RESULT_ID_PATTERN.fullmatch(value) else None


def _attempt_response_detail(
    *,
    code: str,
    message: str,
    retryable: bool,
) -> dict[str, str | bool]:
    return {"code": code, "message": message, "retryable": retryable}


def _configured_credential_cipher() -> CredentialCipher:
    try:
        key_registry = {
            version: (
                key.get_secret_value() if isinstance(key, SecretStr) else key
            )
            for version, key in settings.credential_encryption_keys.items()
        }
        return CredentialCipher(
            key_registry,
            settings.credential_active_key_version,
        )
    except CredentialEncryptionConfigurationError as exc:
        raise ConfigurationError(
            "Provider credential encryption is not configured"
        ) from exc


class TailerService:
    def __init__(self, factory: UnitOfWorkFactory) -> None:
        self.factory = factory

    def authenticate(self, email: str, password: str) -> UserRecord:
        with self.factory() as uow:
            user = uow.users.get_by_email(email)
        if user is None or user.password_hash is None:
            raise AuthenticationError("Invalid credentials")
        try:
            password_matches = verify_password(password.strip(), user.password_hash)
        except (TypeError, ValueError):
            password_matches = False
        if not password_matches:
            raise AuthenticationError("Invalid credentials")
        return user

    def require_admin(self, user_id: str) -> UserRecord:
        with self.factory() as uow:
            user = uow.users.get_by_id(user_id)
        if user is None or user.role != "admin":
            raise AuthorizationError("Admin access required")
        return user

    def get_user(self, user_id: str) -> UserRecord:
        with self.factory() as uow:
            user = uow.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    def list_users(self) -> list[UserRecord]:
        with self.factory() as uow:
            return uow.users.list()

    def create_user(self, request: CreateUserRequest) -> UserRecord:
        try:
            with self.factory() as uow:
                if uow.users.get_by_email(request.email) is not None:
                    raise ConflictError("User with this email already exists")
                user = UserRecord(
                    id=f"user_{uuid.uuid4().hex[:12]}",
                    email=request.email,
                    name=request.name,
                    password_hash=get_password_hash(request.name),
                    role=request.role,
                    created_at=datetime.now(timezone.utc),
                )
                uow.users.add(user)
                uow.commit()
                return user
        except PersistenceConflictError as exc:
            raise ConflictError("User with this email already exists") from exc

    def list_keys(self, owner_id: str | None = None) -> list[KeyRecord]:
        with self.factory() as uow:
            return uow.keys.list(owner_id=owner_id)

    def get_key(self, key_id: str) -> KeyRecord:
        with self.factory() as uow:
            key = uow.keys.get_by_id(key_id)
        if key is None:
            raise NotFoundError("Key not found")
        return key

    def create_key(self, request: CreateKeyRequest) -> CreatedKey:
        with self.factory() as uow:
            project = uow.projects.get_by_id(settings.default_project_id)
            if project is None or project.status != "active":
                raise ConfigurationError("Default project is unavailable")
            if uow.users.get_by_id(request.owner_user_id) is None:
                raise NotFoundError("Owner user not found")

            raw_key = generate_sub_api_key()
            now = datetime.now(timezone.utc)
            key = KeyRecord(
                id=f"subkey_{uuid.uuid4().hex[:12]}",
                project_id=project.id,
                owner_id=request.owner_user_id,
                name=request.name,
                key_hash=hash_sub_api_key(raw_key),
                key_prefix=sub_api_key_prefix(raw_key),
                allowed_models=list(request.allowed_models),
                status="active",
                rate_limit_per_minute=request.rate_limit_per_minute,
                daily_request_limit=request.daily_request_limit,
                monthly_token_limit=request.monthly_token_limit,
                monthly_budget_eur=Decimal(str(request.monthly_budget_eur)),
                max_tokens_per_request=request.max_tokens_per_request,
                created_at=now,
                expires_at=request.expires_at,
            )
            uow.keys.add(key)
            uow.commit()
            return CreatedKey(record=key, raw_key=raw_key)

    def revoke_key(self, key_id: str) -> KeyRecord:
        with self.factory() as uow:
            key = uow.keys.set_status(key_id, "revoked")
            if key is None:
                raise NotFoundError("Key not found")
            uow.commit()
            return key

    def list_provider_credentials(self) -> list[ProviderCredentialRecord]:
        with self.factory() as uow:
            return uow.provider_credentials.list(
                project_id=settings.default_project_id
            )

    def create_provider_credential(
        self,
        request: CreateProviderCredentialRequest,
    ) -> ProviderCredentialRecord:
        cipher = _configured_credential_cipher()
        credential_id = f"cred_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        secret = request.credential.get_secret_value()
        encrypted = cipher.encrypt(
            secret,
            credential_id=credential_id,
            project_id=settings.default_project_id,
            provider=request.provider,
        )
        record = ProviderCredentialRecord(
            id=credential_id,
            project_id=settings.default_project_id,
            provider=request.provider,
            name=request.name,
            ciphertext=encrypted.ciphertext,
            key_version=encrypted.key_version,
            secret_hint=credential_secret_hint(secret),
            status="active",
            created_at=now,
            updated_at=now,
        )
        try:
            with self.factory() as uow:
                project = uow.projects.get_by_id(settings.default_project_id)
                if project is None or project.status != "active":
                    raise ConfigurationError("Default project is unavailable")
                uow.provider_credentials.add(record)
                uow.commit()
        except PersistenceConflictError as exc:
            raise ConflictError(
                "Provider credential name already exists for this project"
            ) from exc
        return record

    def revoke_provider_credential(
        self,
        credential_id: str,
    ) -> ProviderCredentialRecord:
        with self.factory() as uow:
            credential = uow.provider_credentials.get_by_id(credential_id)
            if (
                credential is None
                or credential.project_id != settings.default_project_id
            ):
                raise NotFoundError("Provider credential not found")
            revoked = uow.provider_credentials.set_status(credential_id, "revoked")
            assert revoked is not None
            for config in uow.model_configs.list(
                project_id=settings.default_project_id
            ):
                if config.credential_id == credential_id and config.enabled:
                    uow.model_configs.set_enabled(config.id, False)
            uow.commit()
            return revoked

    def list_model_configs(self) -> list[ModelConfigRecord]:
        with self.factory() as uow:
            return uow.model_configs.list(project_id=settings.default_project_id)

    def create_model_config(
        self,
        request: CreateModelConfigRequest,
    ) -> ModelConfigRecord:
        now = datetime.now(timezone.utc)
        try:
            with self.factory() as uow:
                project = uow.projects.get_by_id(settings.default_project_id)
                if project is None or project.status != "active":
                    raise ConfigurationError("Default project is unavailable")
                credential = uow.provider_credentials.get_by_id(
                    request.credential_id
                )
                if (
                    credential is None
                    or credential.project_id != project.id
                    or credential.status != "active"
                ):
                    raise NotFoundError("Active provider credential not found")
                record = ModelConfigRecord(
                    id=f"modelcfg_{uuid.uuid4().hex[:12]}",
                    project_id=project.id,
                    public_model=request.public_model,
                    provider=credential.provider,
                    provider_model=request.provider_model,
                    credential_id=credential.id,
                    input_cost_per_million_eur=request.input_cost_per_million_eur,
                    output_cost_per_million_eur=request.output_cost_per_million_eur,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
                uow.model_configs.add(record)
                uow.commit()
                return record
        except PersistenceConflictError as exc:
            raise ConflictError(
                "Model alias already exists for this project"
            ) from exc

    def disable_model_config(self, config_id: str) -> ModelConfigRecord:
        with self.factory() as uow:
            config = uow.model_configs.get_by_id(config_id)
            if config is None or config.project_id != settings.default_project_id:
                raise NotFoundError("Model configuration not found")
            disabled = uow.model_configs.set_enabled(config_id, False)
            assert disabled is not None
            uow.commit()
            return disabled

    def list_usage(
        self,
        *,
        user_id: str | None = None,
        key_id: str | None = None,
        limit: int | None = 100,
        offset: int = 0,
    ) -> list[UsageRecord]:
        with self.factory() as uow:
            return uow.usage.list(
                user_id=user_id,
                key_id=key_id,
                limit=limit,
                offset=offset,
            )

    def dashboard_stats(self) -> dict[str, int | float]:
        with self.factory() as uow:
            users = uow.users.list()
            keys = uow.keys.list()
            usage = uow.usage.list(limit=None)
        return {
            "active_keys": sum(key.status == "active" for key in keys),
            "total_tokens_used": sum(event.total_tokens for event in usage),
            "total_cost_estimated": float(
                sum((event.estimated_cost_eur for event in usage), Decimal("0"))
            ),
            "active_users": sum(user.role == "user" for user in users),
            "total_requests": len(usage),
        }

    def user_stats(self, user_id: str) -> dict[str, int | float]:
        keys = self.list_keys(owner_id=user_id)
        usage = self.list_usage(user_id=user_id, limit=None)
        total_tokens = sum(event.total_tokens for event in usage)
        total_cost_decimal = sum(
            (event.estimated_cost_eur for event in usage), Decimal("0")
        )
        monthly_token_limit = sum(key.monthly_token_limit for key in keys)
        monthly_budget_decimal = sum(
            (key.monthly_budget_eur for key in keys), Decimal("0")
        )
        total_cost = float(total_cost_decimal)
        monthly_budget = float(monthly_budget_decimal)
        return {
            "api_keys": len(keys),
            "total_tokens_used": total_tokens,
            "estimated_cost": total_cost,
            "total_requests": len(usage),
            "monthly_token_limit": monthly_token_limit,
            "monthly_budget": monthly_budget,
            "token_usage_percent": (
                total_tokens / monthly_token_limit * 100
                if monthly_token_limit > 0
                else 0
            ),
            "budget_usage_percent": (
                total_cost / monthly_budget * 100 if monthly_budget > 0 else 0
            ),
        }

    def authorize_runtime_key(
        self,
        raw_key: str,
        model: str,
        max_tokens: int,
    ) -> KeyRecord:
        digest = hash_sub_api_key(raw_key)
        with self.factory() as uow:
            key = uow.keys.get_by_hash(digest)
            project = (
                uow.projects.get_by_id(key.project_id) if key is not None else None
            )
        if key is None or key.status != "active":
            raise AuthenticationError("Invalid or inactive API key")
        if key.expires_at <= datetime.now(timezone.utc):
            raise AuthenticationError("API key has expired")
        decision = evaluate_static_request_policy(
            allowed_models=key.allowed_models,
            requested_model=model,
            max_tokens_per_request=key.max_tokens_per_request,
            requested_max_tokens=max_tokens,
        )
        if not decision.allowed:
            raise AuthorizationError(
                decision.message or "Request is not allowed for this key",
                code=decision.code,
            )
        if project is None or project.status != "active":
            raise ConfigurationError("Key project is unavailable")
        return key

    def resolve_runtime_provider(
        self,
        key: KeyRecord,
        public_model: str,
    ) -> ResolvedProviderRoute:
        with self.factory() as uow:
            config = uow.model_configs.get_enabled(key.project_id, public_model)
            if config is None:
                configured_alias = next(
                    (
                        candidate
                        for candidate in uow.model_configs.list(
                            project_id=key.project_id
                        )
                        if candidate.public_model == public_model
                    ),
                    None,
                )
                credential = None
            else:
                configured_alias = config
                credential = (
                    uow.provider_credentials.get_by_id(config.credential_id)
                    if config.credential_id is not None
                    else None
                )

        if config is None:
            if configured_alias is not None or settings.default_provider != "mock":
                raise ConfigurationError("Model route is unavailable")
            provider = get_provider()
            return ResolvedProviderRoute(
                provider=provider,
                provider_name=getattr(provider, "name", "mock"),
                public_model=public_model,
                provider_model=public_model,
            )

        if config.provider == "mock":
            provider = get_provider()
            return ResolvedProviderRoute(
                provider=provider,
                provider_name=getattr(provider, "name", "mock"),
                public_model=public_model,
                provider_model=config.provider_model,
            )

        if config.provider not in {"openai", "gemini"}:
            raise ConfigurationError("Configured provider is unsupported")
        if (
            credential is None
            or credential.status != "active"
            or credential.project_id != config.project_id
            or credential.provider != config.provider
        ):
            raise ConfigurationError("Provider credential is unavailable")

        try:
            cipher = _configured_credential_cipher()
            raw_credential = cipher.decrypt(
                EncryptedCredential(
                    ciphertext=credential.ciphertext,
                    key_version=credential.key_version,
                ),
                credential_id=credential.id,
                project_id=credential.project_id,
                provider=credential.provider,
            )
            provider_class = (
                OpenAIProvider if config.provider == "openai" else GeminiProvider
            )
            provider_base_url = (
                settings.openai_base_url
                if config.provider == "openai"
                else settings.gemini_base_url
            )
            provider = provider_class(
                raw_credential,
                base_url=provider_base_url,
                timeout_seconds=settings.provider_timeout_seconds,
                input_cost_per_million_eur=(config.input_cost_per_million_eur),
                output_cost_per_million_eur=(config.output_cost_per_million_eur),
            )
        except (
            CredentialDecryptionError,
            CredentialEncryptionConfigurationError,
            CredentialKeyUnavailableError,
            ValueError,
        ) as exc:
            raise ConfigurationError(
                "Provider credential could not be loaded"
            ) from exc

        return ResolvedProviderRoute(
            provider=provider,
            provider_name=config.provider,
            public_model=public_model,
            provider_model=config.provider_model,
        )

    def prepare_runtime_attempt_identity(
        self,
        key: KeyRecord,
        request: ChatCompletionRequest,
        idempotency_key: str | None,
    ) -> RuntimeAttemptIdentity:
        if idempotency_key is None:
            return RuntimeAttemptIdentity(
                operation=_RUNTIME_OPERATION,
                idempotency_key_digest=None,
                request_fingerprint_digest=None,
            )
        if _IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key) is None:
            raise RuntimeAttemptContractError(400, "Invalid Idempotency-Key")

        identity = RuntimeAttemptIdentity(
            operation=_RUNTIME_OPERATION,
            idempotency_key_digest=_idempotency_hmac(
                "idempotency-key",
                key.id,
                _RUNTIME_OPERATION,
                idempotency_key,
            ),
            request_fingerprint_digest=_idempotency_hmac(
                "request-fingerprint",
                _RUNTIME_OPERATION,
                _canonical_request(request),
            ),
        )
        assert identity.idempotency_key_digest is not None
        try:
            existing = self._get_attempt_by_identity(key.id, identity)
        except _EXPECTED_PERSISTENCE_ERRORS as exc:
            raise RuntimeAttemptContractError(
                503, _ATTEMPT_UNAVAILABLE_DETAIL
            ) from exc
        if existing is None:
            return identity

        now = _utc_now()
        if self._attempt_identity_is_expired(existing, now):
            try:
                with self.factory() as uow:
                    retired = uow.attempts.retire_expired_identity(
                        existing.id,
                        expected_idempotency_key_digest=(
                            identity.idempotency_key_digest
                        ),
                        now=now,
                    )
                    if retired:
                        uow.commit()
            except _EXPECTED_PERSISTENCE_ERRORS:
                try:
                    observed = self._get_attempt_by_identity(key.id, identity)
                except _EXPECTED_PERSISTENCE_ERRORS as read_error:
                    raise RuntimeAttemptContractError(
                        503,
                        _ATTEMPT_UNAVAILABLE_DETAIL,
                        attempt_id=existing.id,
                    ) from read_error
                if observed is None:
                    return identity
                raise RuntimeAttemptContractError(
                    503,
                    _ATTEMPT_UNAVAILABLE_DETAIL,
                    attempt_id=observed.id,
                )
            if retired:
                return identity
            try:
                existing = self._get_attempt_by_identity(key.id, identity)
            except _EXPECTED_PERSISTENCE_ERRORS as exc:
                raise RuntimeAttemptContractError(
                    503,
                    _ATTEMPT_UNAVAILABLE_DETAIL,
                    attempt_id=existing.id,
                ) from exc
            if existing is None:
                return identity

        self._raise_duplicate_attempt(existing, identity)
        raise AssertionError("Duplicate attempt handling must raise")

    def claim_runtime_attempt(
        self,
        key: KeyRecord,
        route: ResolvedProviderRoute,
        identity: RuntimeAttemptIdentity,
    ) -> OwnedRuntimeAttempt:
        now = _utc_now()
        dispatch_token = secrets.token_bytes(32)
        dispatch_digest = _dispatch_token_digest(dispatch_token)
        attempt = RequestAttemptRecord(
            id=f"attempt_{uuid.uuid4().hex}",
            project_id=key.project_id,
            sub_api_key_id=key.id,
            user_id=key.owner_id,
            operation=identity.operation,
            idempotency_key_digest=identity.idempotency_key_digest,
            request_fingerprint_digest=identity.request_fingerprint_digest,
            dispatch_token_digest=dispatch_digest,
            state="dispatch_claimed",
            provider=route.provider_name,
            public_model=route.public_model,
            provider_model=route.provider_model,
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
            created_at=now,
            updated_at=now,
        )
        try:
            with self.factory() as uow:
                uow.attempts.add(attempt)
                uow.commit()
        except PersistenceConflictError as exc:
            if identity.idempotency_key_digest is not None:
                try:
                    existing = self._get_attempt_by_identity(key.id, identity)
                except _EXPECTED_PERSISTENCE_ERRORS as read_error:
                    raise RuntimeAttemptContractError(
                        503, _ATTEMPT_UNAVAILABLE_DETAIL
                    ) from read_error
                if existing is not None:
                    self._raise_duplicate_attempt(existing, identity)
            raise RuntimeAttemptContractError(
                503, _ATTEMPT_UNAVAILABLE_DETAIL
            ) from exc
        except PersistenceWriteError as exc:
            try:
                observed = self._get_attempt_by_id(attempt.id)
            except _EXPECTED_PERSISTENCE_ERRORS as read_error:
                raise RuntimeAttemptContractError(
                    503, _ATTEMPT_UNAVAILABLE_DETAIL
                ) from read_error
            if (
                observed is None
                or observed.state != "dispatch_claimed"
                or not hmac.compare_digest(
                    observed.dispatch_token_digest, dispatch_digest
                )
            ):
                raise RuntimeAttemptContractError(
                    503, _ATTEMPT_UNAVAILABLE_DETAIL
                ) from exc
            attempt = observed

        return OwnedRuntimeAttempt(record=attempt, dispatch_token=dispatch_token)

    def finalize_runtime_success(
        self,
        owned: OwnedRuntimeAttempt,
        outcome: RuntimeSuccessOutcome,
    ) -> None:
        outcome = self._normalize_success_outcome(outcome)
        now = _utc_now()
        attempt = owned.record
        target = replace(
            attempt,
            state="succeeded",
            provider_result_id=_safe_provider_result_id(
                outcome.provider_result_id or ""
            ),
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            total_tokens=outcome.total_tokens,
            estimated_cost_eur=outcome.estimated_cost_eur,
            currency=outcome.currency,
            latency_ms=outcome.latency_ms,
            error_code=None,
            error_http_status=None,
            error_public_message=None,
            error_retryable=None,
            idempotency_expires_at=self._resolved_identity_expiry(attempt, now),
            updated_at=now,
        )
        usage = UsageRecord(
            id=f"usage_{uuid.uuid4().hex[:12]}",
            project_id=attempt.project_id,
            sub_api_key_id=attempt.sub_api_key_id,
            user_id=attempt.user_id,
            provider=attempt.provider,
            model=attempt.public_model,
            provider_model=attempt.provider_model,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            total_tokens=outcome.total_tokens,
            estimated_cost_eur=outcome.estimated_cost_eur,
            currency=outcome.currency,
            latency_ms=outcome.latency_ms,
            status="success",
            created_at=now,
            error_code=None,
            request_attempt_id=attempt.id,
        )
        compensation = replace(
            target,
            state="finalization_failed",
            error_code="usage_finalization_unavailable",
            error_http_status=503,
            error_public_message=_FINALIZATION_UNAVAILABLE_DETAIL,
            error_retryable=False,
            idempotency_expires_at=None,
        )
        self._finalize_runtime_attempt(
            owned,
            target=target,
            usage=usage,
            compensation=compensation,
        )

    def finalize_runtime_provider_failure(
        self,
        owned: OwnedRuntimeAttempt,
        outcome: RuntimeProviderFailureOutcome,
    ) -> None:
        now = _utc_now()
        attempt = owned.record
        if outcome.execution_certainty == "not_executed":
            target = replace(
                attempt,
                state="provider_failed",
                provider_result_id=None,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                estimated_cost_eur=Decimal("0"),
                currency="EUR",
                latency_ms=outcome.latency_ms,
                error_code=outcome.code,
                error_http_status=outcome.status_code,
                error_public_message=outcome.public_message,
                error_retryable=outcome.retryable,
                idempotency_expires_at=self._resolved_identity_expiry(
                    attempt, now
                ),
                updated_at=now,
            )
            usage = UsageRecord(
                id=f"usage_{uuid.uuid4().hex[:12]}",
                project_id=attempt.project_id,
                sub_api_key_id=attempt.sub_api_key_id,
                user_id=attempt.user_id,
                provider=attempt.provider,
                model=attempt.public_model,
                provider_model=attempt.provider_model,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                estimated_cost_eur=Decimal("0"),
                currency="EUR",
                latency_ms=outcome.latency_ms,
                status=(
                    "rate_limited"
                    if outcome.code == "provider_rate_limited"
                    else "failed"
                ),
                created_at=now,
                error_code=outcome.code,
                request_attempt_id=attempt.id,
            )
            compensation = replace(
                target,
                state="finalization_failed",
                idempotency_expires_at=None,
            )
        else:
            target = replace(
                attempt,
                state="provider_outcome_uncertain",
                provider_result_id=None,
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                estimated_cost_eur=None,
                currency=None,
                latency_ms=outcome.latency_ms,
                error_code=outcome.code,
                error_http_status=outcome.status_code,
                error_public_message=outcome.public_message,
                error_retryable=outcome.retryable,
                idempotency_expires_at=None,
                updated_at=now,
            )
            usage = None
            compensation = target

        self._finalize_runtime_attempt(
            owned,
            target=target,
            usage=usage,
            compensation=compensation,
        )

    def mark_runtime_invalid_usage(
        self,
        owned: OwnedRuntimeAttempt,
        *,
        provider_result_id: str | None,
        latency_ms: int,
    ) -> None:
        now = _utc_now()
        target = replace(
            owned.record,
            state="finalization_failed",
            provider_result_id=_safe_provider_result_id(provider_result_id or ""),
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            estimated_cost_eur=None,
            currency=None,
            latency_ms=latency_ms,
            error_code="provider_invalid_usage",
            error_http_status=502,
            error_public_message=_INVALID_USAGE_DETAIL,
            error_retryable=False,
            idempotency_expires_at=None,
            updated_at=now,
        )
        try:
            self._write_attempt_outcome(owned, target, None)
        except _EXPECTED_PERSISTENCE_ERRORS:
            try:
                observed, usage = self._read_attempt_and_usage(owned.attempt_id)
            except _EXPECTED_PERSISTENCE_ERRORS:
                return
            if observed == target and usage is None:
                return

    def _get_attempt_by_id(self, attempt_id: str) -> RequestAttemptRecord | None:
        with self.factory() as uow:
            return uow.attempts.get_by_id(attempt_id)

    def _get_attempt_by_identity(
        self,
        sub_api_key_id: str,
        identity: RuntimeAttemptIdentity,
    ) -> RequestAttemptRecord | None:
        assert identity.idempotency_key_digest is not None
        with self.factory() as uow:
            return uow.attempts.get_by_identity(
                sub_api_key_id,
                identity.operation,
                identity.idempotency_key_digest,
            )

    @staticmethod
    def _attempt_identity_is_expired(
        attempt: RequestAttemptRecord,
        now: datetime,
    ) -> bool:
        return (
            attempt.state in {"succeeded", "provider_failed"}
            and attempt.idempotency_expires_at is not None
            and _normalized_utc(attempt.idempotency_expires_at)
            <= _normalized_utc(now)
        )

    @staticmethod
    def _raise_duplicate_attempt(
        attempt: RequestAttemptRecord,
        identity: RuntimeAttemptIdentity,
    ) -> None:
        fingerprint = identity.request_fingerprint_digest
        if (
            fingerprint is None
            or attempt.request_fingerprint_digest is None
            or not hmac.compare_digest(
                attempt.request_fingerprint_digest, fingerprint
            )
        ):
            raise RuntimeAttemptContractError(
                409,
                _attempt_response_detail(
                    code="idempotency_key_reused",
                    message=(
                        "Idempotency-Key was already used for a different request"
                    ),
                    retryable=False,
                ),
                attempt_id=attempt.id,
            )
        if attempt.state == "dispatch_claimed":
            raise RuntimeAttemptContractError(
                409,
                _attempt_response_detail(
                    code="request_in_progress",
                    message=(
                        "Request is already in progress or fenced pending resolution"
                    ),
                    retryable=True,
                ),
                attempt_id=attempt.id,
            )
        if attempt.state == "succeeded":
            raise RuntimeAttemptContractError(
                409,
                _attempt_response_detail(
                    code="completed_result_not_replayable",
                    message=(
                        "Request completed, but response content was not retained"
                    ),
                    retryable=False,
                ),
                attempt_id=attempt.id,
            )
        if attempt.state == "provider_failed":
            if (
                attempt.error_code is None
                or attempt.error_public_message is None
                or attempt.error_http_status is None
                or attempt.error_retryable is None
            ):
                raise RuntimeError("Provider-failed attempt metadata is incomplete")
            raise RuntimeAttemptContractError(
                attempt.error_http_status,
                _attempt_response_detail(
                    code=attempt.error_code,
                    message=attempt.error_public_message,
                    retryable=attempt.error_retryable,
                ),
                attempt_id=attempt.id,
            )
        if attempt.state == "provider_outcome_uncertain":
            raise RuntimeAttemptContractError(
                503,
                _attempt_response_detail(
                    code="request_outcome_uncertain",
                    message=(
                        "Request outcome is uncertain and will not be "
                        "re-executed automatically"
                    ),
                    retryable=False,
                ),
                attempt_id=attempt.id,
            )
        if attempt.state == "finalization_failed":
            raise RuntimeAttemptContractError(
                503,
                _FINALIZATION_UNAVAILABLE_DETAIL,
                attempt_id=attempt.id,
            )
        raise RuntimeError("Request attempt has an unsupported state")

    @staticmethod
    def _normalize_success_outcome(
        outcome: RuntimeSuccessOutcome,
    ) -> RuntimeSuccessOutcome:
        token_values = (
            outcome.input_tokens,
            outcome.output_tokens,
            outcome.total_tokens,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 0
            for value in token_values
        ):
            raise ValueError("Runtime success token counts are invalid")
        if (
            not isinstance(outcome.estimated_cost_eur, Decimal)
            or not outcome.estimated_cost_eur.is_finite()
            or outcome.estimated_cost_eur < 0
            or outcome.estimated_cost_eur > _MAX_STORABLE_COST_EUR
            or outcome.currency != "EUR"
            or isinstance(outcome.latency_ms, bool)
            or not isinstance(outcome.latency_ms, int)
            or outcome.latency_ms < 0
        ):
            raise ValueError("Runtime success accounting metadata is invalid")
        try:
            normalized_cost = outcome.estimated_cost_eur.quantize(
                _COST_QUANTUM,
                rounding=ROUND_HALF_EVEN,
            )
        except InvalidOperation:
            raise ValueError(
                "Runtime success accounting metadata is invalid"
            ) from None
        return replace(outcome, estimated_cost_eur=normalized_cost)

    @staticmethod
    def _resolved_identity_expiry(
        attempt: RequestAttemptRecord,
        now: datetime,
    ) -> datetime | None:
        if attempt.idempotency_key_digest is None:
            return None
        return now + timedelta(days=settings.idempotency_retention_days)

    def _write_attempt_outcome(
        self,
        owned: OwnedRuntimeAttempt,
        replacement: RequestAttemptRecord,
        usage: UsageRecord | None,
    ) -> None:
        dispatch_digest = _dispatch_token_digest(owned.dispatch_token)
        with self.factory() as uow:
            transitioned = uow.attempts.transition(
                owned.attempt_id,
                expected_state="dispatch_claimed",
                dispatch_token_digest=dispatch_digest,
                replacement=replacement,
            )
            if not transitioned:
                raise PersistenceConflictError("Attempt transition conflict")
            if usage is not None:
                uow.usage.add(usage)
            uow.commit()

    def _read_attempt_and_usage(
        self,
        attempt_id: str,
    ) -> tuple[RequestAttemptRecord | None, UsageRecord | None]:
        with self.factory() as uow:
            return (
                uow.attempts.get_by_id(attempt_id),
                uow.usage.get_by_request_attempt_id(attempt_id),
            )

    @staticmethod
    def _outcome_is_confirmed(
        observed_attempt: RequestAttemptRecord | None,
        observed_usage: UsageRecord | None,
        intended_attempt: RequestAttemptRecord,
        intended_usage: UsageRecord | None,
    ) -> bool:
        return (
            observed_attempt == intended_attempt
            and observed_usage == intended_usage
        )

    def _finalize_runtime_attempt(
        self,
        owned: OwnedRuntimeAttempt,
        *,
        target: RequestAttemptRecord,
        usage: UsageRecord | None,
        compensation: RequestAttemptRecord,
    ) -> None:
        try:
            self._write_attempt_outcome(owned, target, usage)
            return
        except _EXPECTED_PERSISTENCE_ERRORS:
            pass

        try:
            observed_attempt, observed_usage = self._read_attempt_and_usage(
                owned.attempt_id
            )
        except _EXPECTED_PERSISTENCE_ERRORS as exc:
            raise RuntimeAttemptContractError(
                503,
                _FINALIZATION_UNAVAILABLE_DETAIL,
                attempt_id=owned.attempt_id,
            ) from exc
        if self._outcome_is_confirmed(
            observed_attempt,
            observed_usage,
            target,
            usage,
        ):
            return

        dispatch_digest = _dispatch_token_digest(owned.dispatch_token)
        if (
            observed_attempt is None
            or observed_attempt.state != "dispatch_claimed"
            or not hmac.compare_digest(
                observed_attempt.dispatch_token_digest, dispatch_digest
            )
            or observed_usage is not None
        ):
            raise RuntimeAttemptContractError(
                503,
                _FINALIZATION_UNAVAILABLE_DETAIL,
                attempt_id=owned.attempt_id,
            )

        try:
            self._write_attempt_outcome(owned, compensation, None)
        except _EXPECTED_PERSISTENCE_ERRORS:
            try:
                observed_attempt, observed_usage = self._read_attempt_and_usage(
                    owned.attempt_id
                )
            except _EXPECTED_PERSISTENCE_ERRORS as exc:
                raise RuntimeAttemptContractError(
                    503,
                    _FINALIZATION_UNAVAILABLE_DETAIL,
                    attempt_id=owned.attempt_id,
                ) from exc
            if self._outcome_is_confirmed(
                observed_attempt,
                observed_usage,
                target,
                usage,
            ):
                return
            if not self._outcome_is_confirmed(
                observed_attempt,
                observed_usage,
                compensation,
                None,
            ):
                raise RuntimeAttemptContractError(
                    503,
                    _FINALIZATION_UNAVAILABLE_DETAIL,
                    attempt_id=owned.attempt_id,
                )

        raise RuntimeAttemptContractError(
            503,
            _FINALIZATION_UNAVAILABLE_DETAIL,
            attempt_id=owned.attempt_id,
        )

    def record_usage(self, usage: UsageRecord) -> None:
        try:
            with self.factory() as uow:
                if uow.projects.get_by_id(usage.project_id) is None:
                    raise ConfigurationError("Usage project is unavailable")
                if uow.keys.get_by_id(usage.sub_api_key_id) is None:
                    raise ConfigurationError("Usage key is unavailable")
                uow.usage.add(usage)
                uow.commit()
        except (PersistenceConflictError, PersistenceWriteError) as exc:
            raise ConfigurationError("Usage finalization is unavailable") from exc
