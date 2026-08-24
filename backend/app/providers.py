"""Provider boundary for chat-completion services.

Provider implementations translate their upstream contract into the small,
provider-neutral result types used by the runtime API.  Upstream failures are
normalized into :class:`ProviderError`; its public fields are deliberately
static so provider responses and credentials never escape through API errors.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import math
import re
from typing import Any, Literal, Protocol

import httpx


@dataclass
class Message:
    role: str
    content: str


@dataclass
class ChatCompletionChoice:
    index: int
    message: Message
    finish_reason: str


@dataclass
class ChatCompletionUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ChatCompletionResult:
    id: str
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage
    durable_provider_result_id: str | None = None


ProviderExecutionCertainty = Literal["not_executed", "unknown"]
_PROVIDER_ERROR_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_PROVIDER_EXECUTION_CERTAINTIES = frozenset({"not_executed", "unknown"})


class ProviderError(Exception):
    """A sanitized provider failure safe to expose through the runtime API."""

    def __init__(
        self,
        *,
        code: str,
        public_message: str,
        status_code: int,
        retryable: bool,
        execution_certainty: ProviderExecutionCertainty = "unknown",
    ) -> None:
        if (
            not isinstance(code, str)
            or _PROVIDER_ERROR_CODE_PATTERN.fullmatch(code) is None
        ):
            raise ValueError("Provider error code is invalid")
        if (
            not isinstance(public_message, str)
            or not 1 <= len(public_message) <= 200
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in public_message
            )
        ):
            raise ValueError("Provider public message is invalid")
        if (
            isinstance(status_code, bool)
            or not isinstance(status_code, int)
            or not 400 <= status_code <= 599
        ):
            raise ValueError("Provider HTTP status must be between 400 and 599")
        if not isinstance(retryable, bool):
            raise ValueError("Provider retryability must be a boolean")
        if (
            not isinstance(execution_certainty, str)
            or execution_certainty not in _PROVIDER_EXECUTION_CERTAINTIES
        ):
            raise ValueError(
                "Provider execution certainty must be 'not_executed' or 'unknown'"
            )
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message
        self.status_code = status_code
        self.retryable = retryable
        self.execution_certainty: ProviderExecutionCertainty = execution_certainty


class Provider(Protocol):
    """Interface for LLM providers."""

    name: str

    async def chat_completions(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        """Send a chat completion request to the provider."""
        ...

    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate estimated cost in EUR for a request."""
        ...


class MockProvider:
    """Mock provider that returns placeholder responses without external I/O."""

    name = "mock"

    async def chat_completions(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        """Return a deterministic-shape mock response."""
        # Count tokens approximately (4 chars per token is common).
        message_text = " ".join(str(message.get("content", "")) for message in messages)
        input_tokens = len(message_text) // 4
        output_tokens = max(0, min(max_tokens, 100))

        return ChatCompletionResult(
            id=(
                "chatcmpl_mock_"
                + sha256(f"{model}\0{message_text}".encode("utf-8")).hexdigest()[:12]
            ),
            model=model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=Message(
                        role="assistant",
                        content=(
                            f"Mock response from {model}. This is a placeholder "
                            "until real provider integration is complete."
                        ),
                    ),
                    finish_reason="stop",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate mock cost (not realistic, for demo only)."""
        # Simplified: input tokens at EUR 0.00001, output at EUR 0.00003.
        return (input_tokens * 0.00001) + (output_tokens * 0.00003)


class OpenAIProvider:
    """OpenAI Chat Completions adapter using an injected server-side API key."""

    name = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        input_cost_per_million_eur: Decimal | float | int | str = Decimal("0"),
        output_cost_per_million_eur: Decimal | float | int | str = Decimal("0"),
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_key = api_key.strip()
        if not normalized_key:
            raise ValueError("OpenAI API key must not be empty")
        if not base_url.strip():
            raise ValueError("OpenAI base URL must not be empty")
        try:
            parsed_base_url = httpx.URL(base_url)
        except httpx.InvalidURL:
            raise ValueError("OpenAI base URL is invalid") from None
        if parsed_base_url.scheme != "https" and http_client is None:
            raise ValueError(
                "OpenAI base URL must use HTTPS for network requests"
            )
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Provider timeout must be a positive finite number")

        self._api_key = normalized_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._input_rate = _nonnegative_decimal_rate(input_cost_per_million_eur)
        self._output_rate = _nonnegative_decimal_rate(output_cost_per_million_eur)
        self._http_client = http_client

    async def chat_completions(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        """Call ``POST /v1/chat/completions`` and normalize its response."""
        payload = {
            "messages": messages,
            "model": model,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
        except httpx.TimeoutException:
            raise _provider_error("provider_timeout") from None
        except httpx.RequestError:
            raise _provider_error("provider_unavailable") from None

        if response.status_code == 408:
            raise _provider_error("provider_timeout")
        if response.status_code == 401:
            raise _provider_error("provider_authentication_failed")
        if response.status_code == 403:
            raise _provider_error("provider_permission_denied")
        if response.status_code == 404:
            raise _provider_error("provider_not_found")
        if response.status_code == 429:
            raise _provider_error("provider_rate_limited")
        if response.status_code >= 500:
            raise _provider_error("provider_unavailable")
        if 400 <= response.status_code < 500:
            raise _provider_error("provider_request_rejected")
        if response.status_code < 200 or response.status_code >= 300:
            raise _provider_error("provider_invalid_response")

        try:
            response_payload = response.json()
            return _parse_openai_completion(response_payload)
        except (TypeError, ValueError, KeyError, IndexError):
            raise _provider_error("provider_invalid_response") from None

    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost from model-configured per-million-token EUR rates."""
        if (
            isinstance(input_tokens, bool)
            or isinstance(output_tokens, bool)
            or not isinstance(input_tokens, int)
            or not isinstance(output_tokens, int)
            or input_tokens < 0
            or output_tokens < 0
        ):
            raise ValueError("Token counts must be non-negative integers")
        cost = (
            Decimal(input_tokens) * self._input_rate
            + Decimal(output_tokens) * self._output_rate
        ) / Decimal(1_000_000)
        return float(cost)


class GeminiProvider:
    """Gemini Interactions API adapter using a server-side API key.

    TAILER sends the complete OpenAI-style message history as a stateless Gemini
    interaction.  System messages become ``system_instruction``; user and
    assistant messages become explicit interaction steps.  Requests set
    ``store=false`` so Gemini does not retain Interaction state for continuation.
    """

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://generativelanguage.googleapis.com/v1",
        timeout_seconds: float = 30.0,
        input_cost_per_million_eur: Decimal | float | int | str = Decimal("0"),
        output_cost_per_million_eur: Decimal | float | int | str = Decimal("0"),
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_key = api_key.strip()
        if not normalized_key:
            raise ValueError("Gemini API key must not be empty")
        if not base_url.strip():
            raise ValueError("Gemini base URL must not be empty")
        try:
            parsed_base_url = httpx.URL(base_url)
        except httpx.InvalidURL:
            raise ValueError("Gemini base URL is invalid") from None
        if parsed_base_url.scheme != "https" and http_client is None:
            raise ValueError(
                "Gemini base URL must use HTTPS for network requests"
            )
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Provider timeout must be a positive finite number")

        self._api_key = normalized_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._input_rate = _nonnegative_decimal_rate(input_cost_per_million_eur)
        self._output_rate = _nonnegative_decimal_rate(output_cost_per_million_eur)
        self._http_client = http_client

    async def chat_completions(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        """Call the stable Gemini Interactions API and normalize its response."""
        # Gemini 3.6 deprecates sampling parameters.  TAILER keeps accepting the
        # OpenAI-compatible temperature field, but does not forward it here.
        _ = temperature
        try:
            payload = _gemini_interaction_payload(messages, model, max_tokens)
        except (TypeError, ValueError):
            raise _provider_error("provider_request_rejected") from None

        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        try:
            if self._http_client is not None:
                response = await self._http_client.post(
                    f"{self._base_url}/interactions",
                    headers=headers,
                    json=payload,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(
                        f"{self._base_url}/interactions",
                        headers=headers,
                        json=payload,
                    )
        except httpx.TimeoutException:
            raise _provider_error("provider_timeout") from None
        except httpx.RequestError:
            raise _provider_error("provider_unavailable") from None

        error_code = _gemini_http_error_code(response)
        if error_code is not None:
            raise _provider_error(error_code)

        try:
            return _parse_gemini_interaction(response.json())
        except (TypeError, ValueError, KeyError, IndexError):
            raise _provider_error("provider_invalid_response") from None

    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost from model-configured per-million-token EUR rates."""
        if (
            isinstance(input_tokens, bool)
            or isinstance(output_tokens, bool)
            or not isinstance(input_tokens, int)
            or not isinstance(output_tokens, int)
            or input_tokens < 0
            or output_tokens < 0
        ):
            raise ValueError("Token counts must be non-negative integers")
        cost = (
            Decimal(input_tokens) * self._input_rate
            + Decimal(output_tokens) * self._output_rate
        ) / Decimal(1_000_000)
        return float(cost)


_GEMINI_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _gemini_interaction_payload(
    messages: list[dict],
    model: str,
    max_tokens: int,
) -> dict[str, Any]:
    if not isinstance(model, str) or not _GEMINI_MODEL_PATTERN.fullmatch(model.strip()):
        raise ValueError("Gemini model identifier is invalid")
    if (
        isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or max_tokens <= 0
    ):
        raise ValueError("Gemini max tokens must be a positive integer")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Gemini messages must be a non-empty array")

    system_messages: list[str] = []
    interaction_steps: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Gemini message must be an object")
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Gemini message content must be a non-empty string")
        if role == "system":
            system_messages.append(content)
            continue
        if role == "user":
            step_type = "user_input"
        elif role == "assistant":
            step_type = "model_output"
        else:
            # TAILER does not yet carry the Gemini function call/result IDs
            # required to translate OpenAI tool messages faithfully.
            raise ValueError("Gemini message role is unsupported")
        interaction_steps.append(
            {
                "type": step_type,
                "content": [{"type": "text", "text": content}],
            }
        )

    if not interaction_steps:
        raise ValueError("Gemini interaction requires a non-system message")

    payload: dict[str, Any] = {
        "model": model.strip(),
        "store": False,
        "input": interaction_steps,
        "generation_config": {"max_output_tokens": max_tokens},
    }
    if system_messages:
        payload["system_instruction"] = "\n\n".join(system_messages)
    return payload


def _gemini_http_error_code(response: httpx.Response) -> str | None:
    status_code = response.status_code
    if 200 <= status_code < 300:
        return None
    if status_code == 400 and _gemini_api_key_is_invalid(response):
        return "provider_authentication_failed"
    if status_code == 401:
        return "provider_authentication_failed"
    if status_code == 403:
        return "provider_permission_denied"
    if status_code == 404:
        return "provider_not_found"
    if status_code == 429:
        return "provider_rate_limited"
    if status_code in {408, 504}:
        return "provider_timeout"
    if status_code == 499 or status_code >= 500:
        return "provider_unavailable"
    if 400 <= status_code < 500:
        return "provider_request_rejected"
    return "provider_invalid_response"


def _gemini_api_key_is_invalid(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    if error.get("status") in {"UNAUTHENTICATED", "API_KEY_INVALID"}:
        return True
    details = error.get("details")
    if not isinstance(details, list):
        return False
    return any(
        isinstance(detail, dict) and detail.get("reason") == "API_KEY_INVALID"
        for detail in details
    )


def _parse_gemini_interaction(payload: Any) -> ChatCompletionResult:
    if not isinstance(payload, dict):
        raise ValueError("response must be an object")

    raw_completion_id = payload.get("id")
    if raw_completion_id is not None and (
        not isinstance(raw_completion_id, str) or not raw_completion_id
    ):
        raise ValueError("id must be a string")
    model = _required_string(payload, "model")
    interaction_status = _required_string(payload, "status")
    if interaction_status in {"failed", "cancelled", "budget_exceeded"}:
        raise _provider_error(
            "provider_request_rejected",
            execution_certainty="unknown",
        )
    if interaction_status not in {"completed", "incomplete"}:
        raise ValueError("interaction status is invalid")

    raw_steps = payload["steps"]
    raw_usage = payload["usage"]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("steps must be a non-empty array")
    if not isinstance(raw_usage, dict):
        raise ValueError("usage must be an object")

    text_parts: list[str] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            raise ValueError("step must be an object")
        if raw_step.get("type") != "model_output":
            continue
        raw_content = raw_step.get("content")
        if not isinstance(raw_content, list):
            raise ValueError("model output content must be an array")
        for raw_part in raw_content:
            if not isinstance(raw_part, dict):
                raise ValueError("model output part must be an object")
            if raw_part.get("type") != "text":
                continue
            text_parts.append(_required_string(raw_part, "text", allow_empty=True))

    content = "".join(text_parts)
    # Gemini can spend the complete output budget on thought tokens and return
    # an incomplete interaction without visible text.  That is a valid length
    # stop, not a malformed upstream response; preserve it as an empty assistant
    # message so callers can distinguish it from a provider failure.
    if not content and interaction_status != "incomplete":
        raise ValueError("interaction did not return text")

    prompt_tokens = _nonnegative_integer(raw_usage, "total_input_tokens")
    visible_output_tokens = _nonnegative_integer(raw_usage, "total_output_tokens")
    total_tokens = _nonnegative_integer(raw_usage, "total_tokens")
    if total_tokens < prompt_tokens + visible_output_tokens:
        raise ValueError("total tokens cannot be less than component tokens")
    # Gemini reports thought tokens separately.  Treat every token beyond input
    # as completion usage so cost accounting does not silently omit reasoning.
    completion_tokens = total_tokens - prompt_tokens
    completion_id = raw_completion_id or (
        "chatcmpl_gemini_"
        + sha256(
            f"{model}\0{content}\0{prompt_tokens}\0{completion_tokens}\0{total_tokens}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
    )

    return ChatCompletionResult(
        id=completion_id,
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=Message(role="assistant", content=content),
                finish_reason=(
                    "length" if interaction_status == "incomplete" else "stop"
                ),
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        durable_provider_result_id=raw_completion_id,
    )


def _nonnegative_decimal_rate(value: Decimal | float | int | str) -> Decimal:
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Provider price must be a non-negative finite number") from None
    if not rate.is_finite() or rate < 0:
        raise ValueError("Provider price must be a non-negative finite number")
    return rate


def _parse_openai_completion(payload: Any) -> ChatCompletionResult:
    if not isinstance(payload, dict):
        raise ValueError("response must be an object")

    completion_id = _required_string(payload, "id")
    model = _required_string(payload, "model")
    raw_choices = payload["choices"]
    raw_usage = payload["usage"]
    if not isinstance(raw_choices, list) or not raw_choices:
        raise ValueError("choices must be a non-empty array")
    if not isinstance(raw_usage, dict):
        raise ValueError("usage must be an object")

    choices: list[ChatCompletionChoice] = []
    for raw_choice in raw_choices:
        if not isinstance(raw_choice, dict):
            raise ValueError("choice must be an object")
        raw_message = raw_choice["message"]
        if not isinstance(raw_message, dict):
            raise ValueError("message must be an object")
        choices.append(
            ChatCompletionChoice(
                index=_nonnegative_integer(raw_choice, "index"),
                message=Message(
                    role=_required_string(raw_message, "role"),
                    content=_required_string(raw_message, "content", allow_empty=True),
                ),
                finish_reason=_required_string(raw_choice, "finish_reason"),
            )
        )

    prompt_tokens = _nonnegative_integer(raw_usage, "prompt_tokens")
    completion_tokens = _nonnegative_integer(raw_usage, "completion_tokens")
    total_tokens = _nonnegative_integer(raw_usage, "total_tokens")
    if total_tokens < prompt_tokens + completion_tokens:
        raise ValueError("total tokens cannot be less than component tokens")

    return ChatCompletionResult(
        id=completion_id,
        model=model,
        choices=choices,
        usage=ChatCompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        durable_provider_result_id=completion_id,
    )


def _required_string(
    payload: dict[str, Any],
    field: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = payload[field]
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"{field} must be a string")
    return value


def _nonnegative_integer(payload: dict[str, Any], field: str) -> int:
    value = payload[field]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


_PROVIDER_ERRORS: dict[
    str,
    tuple[str, int, bool, ProviderExecutionCertainty],
] = {
    "provider_timeout": ("Provider request timed out", 504, True, "unknown"),
    "provider_unavailable": ("Provider is unavailable", 503, True, "unknown"),
    "provider_authentication_failed": (
        "Provider authentication failed",
        502,
        False,
        "not_executed",
    ),
    "provider_permission_denied": (
        "Provider permission denied",
        502,
        False,
        "not_executed",
    ),
    "provider_not_found": (
        "Provider resource was not found",
        502,
        False,
        "not_executed",
    ),
    "provider_rate_limited": (
        "Provider rate limit exceeded",
        429,
        True,
        "not_executed",
    ),
    "provider_request_rejected": (
        "Provider rejected the request",
        502,
        False,
        "not_executed",
    ),
    "provider_invalid_response": (
        "Provider returned an invalid response",
        502,
        False,
        "unknown",
    ),
}


def _provider_error(
    code: str,
    *,
    execution_certainty: ProviderExecutionCertainty | None = None,
) -> ProviderError:
    public_message, status_code, retryable, default_certainty = _PROVIDER_ERRORS[code]
    return ProviderError(
        code=code,
        public_message=public_message,
        status_code=status_code,
        retryable=retryable,
        execution_certainty=(
            default_certainty
            if execution_certainty is None
            else execution_certainty
        ),
    )


# Global provider instance retained for deterministic tests and the mock runtime.
_provider: Provider = MockProvider()


def get_provider() -> Provider:
    """Get the current provider instance."""
    return _provider


def set_provider(provider: Provider) -> None:
    """Set the provider instance for tests or explicit mock operation."""
    global _provider
    _provider = provider
