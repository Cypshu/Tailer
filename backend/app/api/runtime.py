from fastapi import APIRouter, Header, HTTPException
from app.models import ChatCompletionRequest, ChatCompletionResponse
from app.mock_data import MOCK_KEYS, MOCK_USAGE_EVENTS, UsageEvent
import uuid
from datetime import datetime

router = APIRouter(tags=["runtime"])


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """OpenAI-compatible chat completions endpoint."""

    # Extract key from Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    key_str = authorization.replace("Bearer ", "").strip()

    # Validate the key exists and is active
    key = next((k for k in MOCK_KEYS if k.key == key_str and k.status == "active"), None)
    if not key:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    # Validate model is allowed
    if request.model not in key.allowed_models:
        raise HTTPException(
            status_code=403,
            detail=f"Model {request.model} not allowed for this key. Allowed: {key.allowed_models}",
        )

    # Mock token counts (in real app, would count actual tokens)
    input_tokens = len(" ".join(str(m.get("content", "")) for m in request.messages)) // 4
    output_tokens = min(request.max_tokens, 100)
    total_tokens = input_tokens + output_tokens

    # Mock cost calculation (simplified)
    estimated_cost = (input_tokens * 0.00001) + (output_tokens * 0.00003)

    # Record usage event
    usage_event = UsageEvent(
        id=f"usage_{uuid.uuid4().hex[:12]}",
        timestamp=datetime.utcnow().isoformat() + "Z",
        sub_key_id=key.id,
        user_id=key.owner_id,
        model=request.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_eur=estimated_cost,
        latency_ms=150,
        status="success",
    )
    MOCK_USAGE_EVENTS.append(usage_event)

    # Mock response (in real app, would call actual provider)
    response = ChatCompletionResponse(
        id=f"chatcmpl_{uuid.uuid4().hex[:12]}",
        model=request.model,
        choices=[
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Mock response from {request.model}. This is a placeholder until real provider integration is complete.",
                },
                "finish_reason": "stop",
            }
        ],
        usage={
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
    )

    return response


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "TAILER Backend"}
