import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator
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
    key: str
    owner_id: str
    allowed_models: list[str]
    status: Literal["active", "paused", "revoked", "expired"]
    daily_request_limit: int
    monthly_token_limit: int
    monthly_budget_eur: float
    created_at: str
    expires_at: str


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
    status: Literal["success", "failed"]


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
    daily_request_limit: PositiveInt = 500
    monthly_token_limit: PositiveInt = 1000000
    monthly_budget_eur: PositiveFloat = 50.0
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
