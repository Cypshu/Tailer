import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
)
from typing_extensions import TypedDict


def _validate_email(value: str) -> str:
    """Validate the normalized address without an optional runtime dependency."""
    if len(value) > 254 or value.count("@") != 1:
        raise ValueError("value is not a valid email address")

    local_part, domain = value.rsplit("@", 1)
    if (
        not local_part
        or len(local_part) > 64
        or local_part.startswith(".")
        or local_part.endswith(".")
        or ".." in local_part
        or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local_part)
    ):
        raise ValueError("value is not a valid email address")

    labels = domain.split(".")
    if len(labels) < 2 or any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not re.fullmatch(r"[a-z0-9-]+", label)
        for label in labels
    ):
        raise ValueError("value is not a valid email address")

    return value


NormalizedEmail = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, min_length=3),
    AfterValidator(_validate_email),
]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(gt=0)]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeMoney = Annotated[
    Decimal,
    Field(ge=0, max_digits=18, decimal_places=8),
]


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant", "tool"]
    content: NonEmptyString


class User(BaseModel):
    id: str
    email: str
    name: str
    role: Literal["admin", "user"]
    created_at: str


class SubApiKey(BaseModel):
    id: str
    name: str
    key_prefix: str
    owner_id: str
    allowed_models: list[str]
    status: Literal["active", "paused", "revoked", "expired"]
    rate_limit_per_minute: PositiveInt | None
    daily_request_limit: int
    monthly_token_limit: int
    monthly_budget_eur: float
    max_tokens_per_request: PositiveInt | None
    created_at: str
    expires_at: str


class CreatedSubApiKey(SubApiKey):
    """Creation-only representation containing the bearer secret once."""

    key: str


class UsageEvent(BaseModel):
    id: str
    timestamp: str
    sub_key_id: str
    user_id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_eur: float
    latency_ms: int
    status: Literal["success", "failed", "blocked", "rate_limited"]
    provider: str
    provider_model: str
    error_code: str | None = None


class CreateProviderCredentialRequest(BaseModel):
    provider: Literal["openai", "gemini"]
    name: NonEmptyString
    credential: Annotated[SecretStr, Field(min_length=1)]

    @field_validator("credential")
    @classmethod
    def require_nonblank_credential(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError("credential must not be blank")
        return SecretStr(secret)


class ProviderCredential(BaseModel):
    id: str
    project_id: str
    provider: str
    name: str
    secret_hint: str
    key_version: str
    status: Literal["active", "revoked"]
    created_at: str
    updated_at: str


class CreateModelConfigRequest(BaseModel):
    public_model: NonEmptyString
    provider_model: NonEmptyString
    credential_id: NonEmptyString
    input_cost_per_million_eur: NonNegativeMoney
    output_cost_per_million_eur: NonNegativeMoney


class ModelConfig(BaseModel):
    id: str
    project_id: str
    public_model: str
    provider: str
    provider_model: str
    credential_id: str | None
    input_cost_per_million_eur: Decimal
    output_cost_per_million_eur: Decimal
    enabled: bool
    created_at: str
    updated_at: str


class Project(BaseModel):
    id: str
    name: str
    description: str
    created_at: str
    status: Literal["active", "paused", "archived"]


class DashboardStats(BaseModel):
    active_keys: int
    total_tokens_used: int
    total_cost_estimated: float
    active_users: int
    total_requests: int


class CreateUserRequest(BaseModel):
    email: NormalizedEmail
    name: str
    role: Literal["admin", "user"] = "user"


class CreateKeyRequest(BaseModel):
    name: str
    owner_user_id: str
    allowed_models: Annotated[list[NonEmptyString], Field(min_length=1)]
    rate_limit_per_minute: PositiveInt | None = None
    daily_request_limit: PositiveInt = 500
    monthly_token_limit: PositiveInt = 1000000
    monthly_budget_eur: PositiveFloat = 50.0
    max_tokens_per_request: PositiveInt | None = None
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def require_future_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)

        if value <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return value


class ChatCompletionRequest(BaseModel):
    model: NonEmptyString
    messages: Annotated[list[ChatMessage], Field(min_length=1)]
    max_tokens: PositiveInt = 2000
    temperature: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] = 0.7


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    choices: list[dict]
    usage: dict
