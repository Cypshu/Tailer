from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass
class UserRecord:
    id: str
    email: str
    name: str
    password_hash: str | None
    role: Literal["admin", "user"]
    created_at: datetime


@dataclass
class ProjectRecord:
    id: str
    name: str
    description: str
    status: Literal["active", "paused", "archived"]
    created_at: datetime


@dataclass(repr=False)
class ProviderCredentialRecord:
    """Encrypted provider credential metadata.

    ``ciphertext`` is intentionally excluded from ``repr`` so routine logging
    cannot accidentally disclose the encrypted secret. The raw credential is
    never part of this persistence record.
    """

    id: str
    project_id: str
    provider: str
    name: str
    ciphertext: str
    key_version: str
    secret_hint: str
    status: Literal["active", "revoked"]
    created_at: datetime
    updated_at: datetime

    def __repr__(self) -> str:
        return (
            "ProviderCredentialRecord("
            f"id={self.id!r}, project_id={self.project_id!r}, "
            f"provider={self.provider!r}, name={self.name!r}, "
            f"key_version={self.key_version!r}, secret_hint={self.secret_hint!r}, "
            f"status={self.status!r}, created_at={self.created_at!r}, "
            f"updated_at={self.updated_at!r}, ciphertext='<redacted>')"
        )


@dataclass
class ModelConfigRecord:
    id: str
    project_id: str
    public_model: str
    provider: str
    provider_model: str
    credential_id: str | None
    input_cost_per_million_eur: Decimal
    output_cost_per_million_eur: Decimal
    enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class KeyRecord:
    id: str
    project_id: str
    owner_id: str
    name: str
    key_hash: str
    key_prefix: str
    allowed_models: list[str]
    status: Literal["active", "paused", "revoked", "expired"]
    daily_request_limit: int
    monthly_token_limit: int
    monthly_budget_eur: Decimal
    created_at: datetime
    expires_at: datetime


@dataclass
class UsageRecord:
    id: str
    project_id: str
    sub_api_key_id: str
    user_id: str
    provider: str
    model: str
    provider_model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_eur: Decimal
    currency: str
    latency_ms: int
    status: Literal["success", "failed", "blocked", "rate_limited"]
    created_at: datetime
    error_code: str | None = None
