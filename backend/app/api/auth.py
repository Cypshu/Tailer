from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import create_access_token
from app.models import NormalizedEmail
from app.repositories.dependencies import get_service
from app.services import AuthenticationError, TailerService

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
def login(credentials: LoginRequest, service: TailerService = Depends(get_service)):
    """Authenticate a dashboard user and return a configured JWT."""
    try:
        user = service.authenticate(credentials.email, credentials.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

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
def refresh_token():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Token refresh not yet implemented",
    )
