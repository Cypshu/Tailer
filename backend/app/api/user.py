from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.auth import decode_access_token
from app.models import SubApiKey, UsageEvent, User
from app.repositories.dependencies import get_service
from app.serialization import key_response, usage_response, user_response
from app.services import NotFoundError, TailerService

router = APIRouter(prefix="/user", tags=["user"])


def get_current_user_id(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if not token_data or not token_data.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data.user_id


@router.get("/me", response_model=User)
def get_current_user(
    user_id: str = Depends(get_current_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        return user_response(service.get_user(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/keys", response_model=list[SubApiKey])
def get_my_keys(
    user_id: str = Depends(get_current_user_id),
    service: TailerService = Depends(get_service),
):
    return [key_response(key) for key in service.list_keys(owner_id=user_id)]


@router.get("/keys/{key_id}", response_model=SubApiKey)
def get_key(
    key_id: str,
    user_id: str = Depends(get_current_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        key = service.get_key(key_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if key.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this key")
    return key_response(key)


@router.get("/usage", response_model=list[UsageEvent])
def get_my_usage(
    user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: TailerService = Depends(get_service),
):
    return [
        usage_response(event)
        for event in service.list_usage(user_id=user_id, limit=limit, offset=offset)
    ]


@router.get("/stats")
def get_user_stats(
    user_id: str = Depends(get_current_user_id),
    service: TailerService = Depends(get_service),
):
    return service.user_stats(user_id)
