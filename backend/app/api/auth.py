from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.auth import create_access_token
from app.mock_data import MOCK_USERS
from app.models import NormalizedEmail

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str
    name: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest):
    """Login with email and password to get access token.

    For MVP: users in mock data use their name as password for testing.
    """
    normalized_password = credentials.password.strip()

    # Find user by email
    user = next((u for u in MOCK_USERS if u.email.lower() == credentials.email), None)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # For MVP, use name as password (plaintext for testing)
    # In production, compare hashed passwords
    if normalized_password != user.name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(data={"sub": user.id})

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
    )


@router.post("/refresh")
async def refresh_token():
    """Refresh access token (placeholder for future implementation)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Token refresh not yet implemented",
    )
