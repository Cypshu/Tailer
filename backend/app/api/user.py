from fastapi import APIRouter, HTTPException
from app.models import User, SubApiKey, UsageEvent
from app.mock_data import MOCK_USERS, MOCK_KEYS, get_user_keys, get_user_usage_events

router = APIRouter(prefix="/user", tags=["user"])

# In a real app, this would come from JWT token
CURRENT_USER_ID = "user_1"


@router.get("/me", response_model=User)
async def get_current_user():
    """Get the current logged-in user."""
    user = next((u for u in MOCK_USERS if u.id == CURRENT_USER_ID), None)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/keys", response_model=list[SubApiKey])
async def get_my_keys():
    """Get the current user's Sub-API Keys."""
    return get_user_keys(CURRENT_USER_ID)


@router.get("/keys/{key_id}", response_model=SubApiKey)
async def get_key(key_id: str):
    """Get a specific key belonging to current user."""
    key = next((k for k in MOCK_KEYS if k.id == key_id), None)
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    if key.owner_id != CURRENT_USER_ID:
        raise HTTPException(status_code=403, detail="Not authorized to access this key")
    return key


@router.get("/usage", response_model=list[UsageEvent])
async def get_my_usage(limit: int = 100, offset: int = 0):
    """Get the current user's usage events."""
    events = get_user_usage_events(CURRENT_USER_ID)
    return sorted(events, key=lambda e: e.timestamp, reverse=True)[offset : offset + limit]


@router.get("/stats")
async def get_user_stats():
    """Get user-specific statistics."""
    user_keys = get_user_keys(CURRENT_USER_ID)
    user_usage = get_user_usage_events(CURRENT_USER_ID)

    total_tokens = sum(e.total_tokens for e in user_usage)
    total_cost = sum(e.estimated_cost_eur for e in user_usage)
    monthly_token_limit = sum(k.monthly_token_limit for k in user_keys)
    monthly_budget = sum(k.monthly_budget_eur for k in user_keys)

    return {
        "api_keys": len(user_keys),
        "total_tokens_used": total_tokens,
        "estimated_cost": total_cost,
        "total_requests": len(user_usage),
        "monthly_token_limit": monthly_token_limit,
        "monthly_budget": monthly_budget,
        "token_usage_percent": (total_tokens / monthly_token_limit * 100) if monthly_token_limit > 0 else 0,
        "budget_usage_percent": (total_cost / monthly_budget * 100) if monthly_budget > 0 else 0,
    }
