from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.auth import decode_access_token
from app.models import (
    CreatedSubApiKey,
    CreateKeyRequest,
    CreateModelConfigRequest,
    CreateProviderCredentialRequest,
    CreateUserRequest,
    DashboardStats,
    ModelConfig,
    ProviderCredential,
    SubApiKey,
    UsageEvent,
    User,
)
from app.repositories.dependencies import get_service
from app.serialization import (
    created_key_response,
    key_response,
    model_config_response,
    provider_credential_response,
    usage_response,
    user_response,
)
from app.services import (
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    TailerService,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_user_id(
    authorization: Optional[str] = Header(None),
    service: TailerService = Depends(get_service),
) -> str:
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
    try:
        service.require_admin(token_data.user_id)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return token_data.user_id


@router.get("/dashboard/stats", response_model=DashboardStats)
def get_dashboard_stats(
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    return DashboardStats(**service.dashboard_stats())


@router.get("/users", response_model=list[User])
def list_users(
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    return [user_response(user) for user in service.list_users()]


@router.post("/users", response_model=User)
def create_user(
    user_data: CreateUserRequest,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        return user_response(service.create_user(user_data))
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/users/{user_id}", response_model=User)
def get_user(
    user_id: str,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        return user_response(service.get_user(user_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/keys", response_model=list[SubApiKey])
def list_keys(
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    return [key_response(key) for key in service.list_keys()]


@router.post("/keys", response_model=CreatedSubApiKey)
def create_key(
    key_data: CreateKeyRequest,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        created = service.create_key(key_data)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return created_key_response(created.record, created.raw_key)


@router.get("/keys/{key_id}", response_model=SubApiKey)
def get_key(
    key_id: str,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        return key_response(service.get_key(key_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/keys/{key_id}")
def revoke_key(
    key_id: str,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        service.revoke_key(key_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "revoked", "key_id": key_id}


@router.get(
    "/provider-credentials",
    response_model=list[ProviderCredential],
)
def list_provider_credentials(
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    return [
        provider_credential_response(credential)
        for credential in service.list_provider_credentials()
    ]


@router.post(
    "/provider-credentials",
    response_model=ProviderCredential,
)
def create_provider_credential(
    credential_data: CreateProviderCredentialRequest,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        credential = service.create_provider_credential(credential_data)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return provider_credential_response(credential)


@router.delete(
    "/provider-credentials/{credential_id}",
    response_model=ProviderCredential,
)
def revoke_provider_credential(
    credential_id: str,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        credential = service.revoke_provider_credential(credential_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return provider_credential_response(credential)


@router.get("/model-configs", response_model=list[ModelConfig])
def list_model_configs(
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    return [
        model_config_response(config) for config in service.list_model_configs()
    ]


@router.post("/model-configs", response_model=ModelConfig)
def create_model_config(
    config_data: CreateModelConfigRequest,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        config = service.create_model_config(config_data)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return model_config_response(config)


@router.delete("/model-configs/{config_id}", response_model=ModelConfig)
def disable_model_config(
    config_id: str,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    try:
        config = service.disable_model_config(config_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return model_config_response(config)


@router.get("/usage", response_model=list[UsageEvent])
def get_usage_events(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user_id: str | None = None,
    key_id: str | None = None,
    admin_id: str = Depends(get_admin_user_id),
    service: TailerService = Depends(get_service),
):
    return [
        usage_response(event)
        for event in service.list_usage(
            user_id=user_id,
            key_id=key_id,
            limit=limit,
            offset=offset,
        )
    ]
