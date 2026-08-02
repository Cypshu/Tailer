from datetime import datetime, timezone

from app.domain import (
    KeyRecord,
    ModelConfigRecord,
    ProviderCredentialRecord,
    UsageRecord,
    UserRecord,
)
from app.models import (
    CreatedSubApiKey,
    ModelConfig,
    ProviderCredential,
    SubApiKey,
    UsageEvent,
    User,
)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def user_response(record: UserRecord) -> User:
    return User(
        id=record.id,
        email=record.email,
        name=record.name,
        role=record.role,
        created_at=_iso_utc(record.created_at),
    )


def key_response(record: KeyRecord) -> SubApiKey:
    return SubApiKey(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        owner_id=record.owner_id,
        allowed_models=record.allowed_models,
        status=record.status,
        daily_request_limit=record.daily_request_limit,
        monthly_token_limit=record.monthly_token_limit,
        monthly_budget_eur=float(record.monthly_budget_eur),
        created_at=_iso_utc(record.created_at),
        expires_at=_iso_utc(record.expires_at),
    )


def created_key_response(record: KeyRecord, raw_key: str) -> CreatedSubApiKey:
    return CreatedSubApiKey(**key_response(record).model_dump(), key=raw_key)


def usage_response(record: UsageRecord) -> UsageEvent:
    return UsageEvent(
        id=record.id,
        timestamp=_iso_utc(record.created_at),
        sub_key_id=record.sub_api_key_id,
        user_id=record.user_id,
        model=record.model,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        total_tokens=record.total_tokens,
        estimated_cost_eur=float(record.estimated_cost_eur),
        latency_ms=record.latency_ms,
        status=record.status,
        provider=record.provider,
        provider_model=record.provider_model,
        error_code=record.error_code,
    )


def provider_credential_response(
    record: ProviderCredentialRecord,
) -> ProviderCredential:
    return ProviderCredential(
        id=record.id,
        project_id=record.project_id,
        provider=record.provider,
        name=record.name,
        secret_hint=record.secret_hint,
        key_version=record.key_version,
        status=record.status,
        created_at=_iso_utc(record.created_at),
        updated_at=_iso_utc(record.updated_at),
    )


def model_config_response(record: ModelConfigRecord) -> ModelConfig:
    return ModelConfig(
        id=record.id,
        project_id=record.project_id,
        public_model=record.public_model,
        provider=record.provider,
        provider_model=record.provider_model,
        credential_id=record.credential_id,
        input_cost_per_million_eur=record.input_cost_per_million_eur,
        output_cost_per_million_eur=record.output_cost_per_million_eur,
        enabled=record.enabled,
        created_at=_iso_utc(record.created_at),
        updated_at=_iso_utc(record.updated_at),
    )
