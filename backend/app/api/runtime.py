from datetime import datetime, timezone
from decimal import Decimal
import math
from time import perf_counter
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.domain import UsageRecord
from app.models import ChatCompletionRequest, ChatCompletionResponse
from app.providers import ProviderError
from app.repositories.dependencies import get_service
from app.services import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    TailerService,
)

router = APIRouter(tags=["runtime"])


def _validate_usage_values(*values: int | float) -> None:
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
        for value in values
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Provider returned invalid usage data",
        )


def _provider_messages(messages: list[object]) -> list[dict]:
    return [
        message.copy()
        if isinstance(message, dict)
        else message.model_dump()  # type: ignore[attr-defined]
        for message in messages
    ]


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    service: TailerService = Depends(get_service),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    raw_key = authorization.removeprefix("Bearer ").strip()
    try:
        key = await run_in_threadpool(
            service.authorize_runtime_key,
            raw_key,
            request.model,
            request.max_tokens,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        route = await run_in_threadpool(
            service.resolve_runtime_provider,
            key,
            request.model,
        )
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    provider = route.provider
    started_at = perf_counter()
    try:
        provider_result = await provider.chat_completions(
            messages=_provider_messages(request.messages),
            model=route.provider_model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
    except ProviderError as exc:
        latency_ms = max(0, round((perf_counter() - started_at) * 1000))
        failure = UsageRecord(
            id=f"usage_{uuid.uuid4().hex[:12]}",
            project_id=key.project_id,
            sub_api_key_id=key.id,
            user_id=key.owner_id,
            provider=route.provider_name,
            model=request.model,
            provider_model=route.provider_model,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            estimated_cost_eur=Decimal("0"),
            currency="EUR",
            latency_ms=latency_ms,
            status=(
                "rate_limited"
                if exc.code == "provider_rate_limited"
                else "failed"
            ),
            created_at=datetime.now(timezone.utc),
            error_code=exc.code,
        )
        try:
            await run_in_threadpool(service.record_usage, failure)
        except ConfigurationError as persistence_error:
            raise HTTPException(
                status_code=503,
                detail=str(persistence_error),
            ) from persistence_error
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.public_message,
                "retryable": exc.retryable,
            },
        ) from exc
    latency_ms = max(0, round((perf_counter() - started_at) * 1000))

    _validate_usage_values(
        provider_result.usage.prompt_tokens,
        provider_result.usage.completion_tokens,
        provider_result.usage.total_tokens,
    )
    estimated_cost = provider.calculate_cost(
        provider_result.usage.prompt_tokens,
        provider_result.usage.completion_tokens,
        route.provider_model,
    )
    _validate_usage_values(estimated_cost)

    usage = UsageRecord(
        id=f"usage_{uuid.uuid4().hex[:12]}",
        project_id=key.project_id,
        sub_api_key_id=key.id,
        user_id=key.owner_id,
        provider=route.provider_name,
        model=request.model,
        provider_model=provider_result.model,
        input_tokens=provider_result.usage.prompt_tokens,
        output_tokens=provider_result.usage.completion_tokens,
        total_tokens=provider_result.usage.total_tokens,
        estimated_cost_eur=Decimal(str(estimated_cost)),
        currency="EUR",
        latency_ms=latency_ms,
        status="success",
        created_at=datetime.now(timezone.utc),
    )
    try:
        await run_in_threadpool(service.record_usage, usage)
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatCompletionResponse(
        id=provider_result.id,
        model=provider_result.model,
        choices=[
            {
                "index": choice.index,
                "message": {
                    "role": choice.message.role,
                    "content": choice.message.content,
                },
                "finish_reason": choice.finish_reason,
            }
            for choice in provider_result.choices
        ],
        usage={
            "prompt_tokens": provider_result.usage.prompt_tokens,
            "completion_tokens": provider_result.usage.completion_tokens,
            "total_tokens": provider_result.usage.total_tokens,
        },
    )
