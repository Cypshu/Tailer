from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
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
    UsageRecord,
    UserRecord,
)
from app.key_security import generate_sub_api_key, hash_sub_api_key, sub_api_key_prefix
from app.models import (
    CreateKeyRequest,
    CreateModelConfigRequest,
    CreateProviderCredentialRequest,
    CreateUserRequest,
)
from app.providers import GeminiProvider, OpenAIProvider, Provider, get_provider
from app.repositories.base import PersistenceConflictError, UnitOfWorkFactory


class DomainError(RuntimeError):
    pass


class AuthenticationError(DomainError):
    pass


class AuthorizationError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class NotFoundError(DomainError):
    pass


class ConfigurationError(DomainError):
    pass


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
                daily_request_limit=request.daily_request_limit,
                monthly_token_limit=request.monthly_token_limit,
                monthly_budget_eur=Decimal(str(request.monthly_budget_eur)),
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

    def authorize_runtime_key(self, raw_key: str, model: str) -> KeyRecord:
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
        if model not in key.allowed_models:
            raise AuthorizationError(f"Model {model} not allowed for this key")
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

    def record_usage(self, usage: UsageRecord) -> None:
        with self.factory() as uow:
            if uow.projects.get_by_id(usage.project_id) is None:
                raise ConfigurationError("Usage project is unavailable")
            if uow.keys.get_by_id(usage.sub_api_key_id) is None:
                raise ConfigurationError("Usage key is unavailable")
            uow.usage.add(usage)
            uow.commit()
