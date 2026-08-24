from decimal import Decimal
from time import perf_counter

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from starlette.concurrency import run_in_threadpool

from app.models import ChatCompletionRequest, ChatCompletionResponse
from app.providers import ProviderError
from app.repositories.dependencies import get_service
from app.services import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    RuntimeAttemptContractError,
    RuntimeProviderFailureOutcome,
    RuntimeSuccessOutcome,
    TailerService,
)

router = APIRouter(tags=["runtime"])
_MAX_STORABLE_COST_EUR = Decimal("9999999999.99999999")


def _validate_token_counts(*values: int) -> None:
    if any(
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
        for value in values
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Provider returned invalid usage data",
        )


def _validate_cost(value: int | float) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Provider returned invalid usage data",
        )
    normalized = Decimal(str(value))
    if (
        not normalized.is_finite()
        or normalized < 0
        or normalized > _MAX_STORABLE_COST_EUR
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


def _attempt_headers(attempt_id: str | None) -> dict[str, str] | None:
    return (
        {"Tailer-Attempt-Id": attempt_id}
        if attempt_id is not None
        else None
    )


def _attempt_http_exception(error: RuntimeAttemptContractError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail=error.detail,
        headers=_attempt_headers(error.attempt_id),
    )


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
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
        identity = await run_in_threadpool(
            service.prepare_runtime_attempt_identity,
            key,
            request,
            idempotency_key,
        )
    except RuntimeAttemptContractError as exc:
        raise _attempt_http_exception(exc) from exc

    try:
        route = await run_in_threadpool(
            service.resolve_runtime_provider,
            key,
            request.model,
        )
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        owned_attempt = await run_in_threadpool(
            service.claim_runtime_attempt,
            key,
            route,
            identity,
        )
    except RuntimeAttemptContractError as exc:
        raise _attempt_http_exception(exc) from exc

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
        try:
            await run_in_threadpool(
                service.finalize_runtime_provider_failure,
                owned_attempt,
                RuntimeProviderFailureOutcome.from_error(
                    exc,
                    latency_ms=latency_ms,
                ),
            )
        except RuntimeAttemptContractError as persistence_error:
            raise _attempt_http_exception(persistence_error) from persistence_error
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "code": exc.code,
                "message": exc.public_message,
                "retryable": exc.retryable,
            },
            headers=_attempt_headers(owned_attempt.attempt_id),
        ) from exc
    latency_ms = max(0, round((perf_counter() - started_at) * 1000))

    try:
        _validate_token_counts(
            provider_result.usage.prompt_tokens,
            provider_result.usage.completion_tokens,
            provider_result.usage.total_tokens,
        )
    except HTTPException as exc:
        await run_in_threadpool(
            service.mark_runtime_invalid_usage,
            owned_attempt,
            provider_result_id=provider_result.durable_provider_result_id,
            latency_ms=latency_ms,
        )
        exc.headers = _attempt_headers(owned_attempt.attempt_id)
        raise
    estimated_cost = provider.calculate_cost(
        provider_result.usage.prompt_tokens,
        provider_result.usage.completion_tokens,
        route.provider_model,
    )
    try:
        _validate_cost(estimated_cost)
    except HTTPException as exc:
        await run_in_threadpool(
            service.mark_runtime_invalid_usage,
            owned_attempt,
            provider_result_id=provider_result.durable_provider_result_id,
            latency_ms=latency_ms,
        )
        exc.headers = _attempt_headers(owned_attempt.attempt_id)
        raise

    try:
        await run_in_threadpool(
            service.finalize_runtime_success,
            owned_attempt,
            RuntimeSuccessOutcome(
                provider_result_id=provider_result.durable_provider_result_id,
                input_tokens=provider_result.usage.prompt_tokens,
                output_tokens=provider_result.usage.completion_tokens,
                total_tokens=provider_result.usage.total_tokens,
                estimated_cost_eur=Decimal(str(estimated_cost)),
                currency="EUR",
                latency_ms=latency_ms,
            ),
        )
    except RuntimeAttemptContractError as exc:
        raise _attempt_http_exception(exc) from exc

    response.headers["Tailer-Attempt-Id"] = owned_attempt.attempt_id

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
