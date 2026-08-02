from datetime import datetime, timezone
import math
from time import perf_counter
import uuid

from fastapi import APIRouter, Header, HTTPException, status

from app.models import ChatCompletionRequest, ChatCompletionResponse
from app.mock_data import MOCK_KEYS, MOCK_USAGE_EVENTS, UsageEvent
from app.providers import get_provider

router = APIRouter(tags=["runtime"])


def _is_expired(expires_at: str | datetime) -> bool:
    """Return whether a key expiry is at or before the current UTC time.

    Existing mock records store ISO-8601 strings. Accepting ``datetime`` as well
    keeps this boundary compatible with the typed request/model hardening.
    Invalid timestamps fail closed at the call site.
    """
    if isinstance(expires_at, datetime):
        expiration = expires_at
    else:
        expiration = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))

    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=timezone.utc)

    return expiration.astimezone(timezone.utc) <= datetime.now(timezone.utc)


def _validate_usage_values(*values: int | float) -> None:
    """Reject invalid provider metering before it reaches the usage ledger."""
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
    """Serialize validated API messages at the provider boundary."""
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
):
    """OpenAI-compatible chat completions endpoint.

    Validates Sub-API keys and delegates to the configured provider for actual completions.
    """

    # Extract and validate key from Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )

    key_str = authorization.replace("Bearer ", "").strip()

    # Look up key (do NOT return raw key to client)
    key = next((k for k in MOCK_KEYS if k.key == key_str and k.status == "active"), None)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )

    try:
        key_is_expired = _is_expired(key.expires_at)
    except (AttributeError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        ) from None

    if key_is_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
        )

    # Validate model is allowed for this key
    if request.model not in key.allowed_models:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model {request.model} not allowed for this key",
        )

    # Get provider and call it
    provider = get_provider()
    started_at = perf_counter()
    provider_result = await provider.chat_completions(
        messages=_provider_messages(request.messages),
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
    )
    latency_ms = max(0, round((perf_counter() - started_at) * 1000))

    _validate_usage_values(
        provider_result.usage.prompt_tokens,
        provider_result.usage.completion_tokens,
        provider_result.usage.total_tokens,
    )

    # Calculate cost
    estimated_cost = provider.calculate_cost(
        provider_result.usage.prompt_tokens,
        provider_result.usage.completion_tokens,
        request.model,
    )
    _validate_usage_values(estimated_cost)

    # Record usage event (for monitoring and billing)
    usage_event = UsageEvent(
        id=f"usage_{uuid.uuid4().hex[:12]}",
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        sub_key_id=key.id,
        user_id=key.owner_id,
        model=request.model,
        input_tokens=provider_result.usage.prompt_tokens,
        output_tokens=provider_result.usage.completion_tokens,
        total_tokens=provider_result.usage.total_tokens,
        estimated_cost_eur=estimated_cost,
        latency_ms=latency_ms,
        status="success",
    )
    MOCK_USAGE_EVENTS.append(usage_event)

    # Convert provider result to API response
    response = ChatCompletionResponse(
        id=provider_result.id,
        model=provider_result.model,
        choices=[
            {
                "index": c.index,
                "message": {
                    "role": c.message.role,
                    "content": c.message.content,
                },
                "finish_reason": c.finish_reason,
            }
            for c in provider_result.choices
        ],
        usage={
            "prompt_tokens": provider_result.usage.prompt_tokens,
            "completion_tokens": provider_result.usage.completion_tokens,
            "total_tokens": provider_result.usage.total_tokens,
        },
    )

    return response
