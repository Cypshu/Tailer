from fastapi import APIRouter, HTTPException
from app.models import (
    DashboardStats,
    User,
    SubApiKey,
    UsageEvent,
    CreateUserRequest,
    CreateKeyRequest,
)
from app.mock_data import (
    MOCK_USERS,
    MOCK_KEYS,
    MOCK_USAGE_EVENTS,
    get_total_tokens_used,
    get_total_cost_estimated,
    get_active_keys_count,
)
import uuid
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    """Get admin dashboard statistics."""
    active_users = len([u for u in MOCK_USERS if u.role == "user"])
    return DashboardStats(
        active_keys=get_active_keys_count(),
        total_tokens_used=get_total_tokens_used(),
        total_cost_estimated=get_total_cost_estimated(),
        active_users=active_users,
        total_requests=len(MOCK_USAGE_EVENTS),
    )


@router.get("/users", response_model=list[User])
async def list_users():
    """Get all users."""
    return MOCK_USERS


@router.post("/users", response_model=User)
async def create_user(user_data: CreateUserRequest):
    """Create a new user."""
    new_user = User(
        id=f"user_{uuid.uuid4().hex[:12]}",
        email=user_data.email,
        name=user_data.name,
        role=user_data.role,
        created_at=datetime.utcnow().isoformat() + "Z",
    )
    MOCK_USERS.append(new_user)
    return new_user


@router.get("/users/{user_id}", response_model=User)
async def get_user(user_id: str):
    """Get a specific user."""
    user = next((u for u in MOCK_USERS if u.id == user_id), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/keys", response_model=list[SubApiKey])
async def list_keys():
    """Get all Sub-API Keys."""
    return MOCK_KEYS


@router.post("/keys", response_model=SubApiKey)
async def create_key(key_data: CreateKeyRequest):
    """Create a new Sub-API Key."""
    new_key = SubApiKey(
        id=f"subkey_{uuid.uuid4().hex[:12]}",
        name=key_data.name,
        key=f"tailer_sub_{uuid.uuid4().hex}",
        owner_id=key_data.owner_user_id,
        allowed_models=key_data.allowed_models,
        status="active",
        daily_request_limit=key_data.daily_request_limit,
        monthly_token_limit=key_data.monthly_token_limit,
        monthly_budget_eur=key_data.monthly_budget_eur,
        created_at=datetime.utcnow().isoformat() + "Z",
        expires_at=key_data.expires_at,
    )
    MOCK_KEYS.append(new_key)
    return new_key


@router.get("/keys/{key_id}", response_model=SubApiKey)
async def get_key(key_id: str):
    """Get a specific Sub-API Key."""
    key = next((k for k in MOCK_KEYS if k.id == key_id), None)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    return key


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: str):
    """Revoke a Sub-API Key."""
    key = next((k for k in MOCK_KEYS if k.id == key_id), None)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    key.status = "revoked"
    return {"status": "revoked", "key_id": key_id}


@router.get("/usage", response_model=list[UsageEvent])
async def get_usage_events(
    limit: int = 100, offset: int = 0, user_id: str = None, key_id: str = None
):
    """Get usage events with optional filtering."""
    events = MOCK_USAGE_EVENTS

    if user_id:
        events = [e for e in events if e.user_id == user_id]
    if key_id:
        events = [e for e in events if e.sub_key_id == key_id]

    return sorted(events, key=lambda e: e.timestamp, reverse=True)[offset : offset + limit]
