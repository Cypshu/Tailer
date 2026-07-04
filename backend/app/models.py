from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


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
    email: str
    name: str
    role: Literal["admin", "user"] = "user"


class CreateKeyRequest(BaseModel):
    name: str
    owner_user_id: str
    allowed_models: list[str]
    daily_request_limit: int = 500
    monthly_token_limit: int = 1000000
    monthly_budget_eur: float = 50.0
    expires_at: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict]
    max_tokens: int = 2000
    temperature: float = 0.7


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    choices: list[dict]
    usage: dict
