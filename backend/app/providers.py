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
from typing import Any, Protocol

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


class ProviderError(Exception):
    """A sanitized provider failure safe to expose through the runtime API."""

    def __init__(
        self,
        *,
        code: str,
        public_message: str,
        status_code: int,
        retryable: bool,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message
        self.status_code = status_code
        self.retryable = retryable


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


_PROVIDER_ERRORS: dict[str, tuple[str, int, bool]] = {
    "provider_timeout": ("Provider request timed out", 504, True),
    "provider_unavailable": ("Provider is unavailable", 503, True),
    "provider_authentication_failed": ("Provider authentication failed", 502, False),
    "provider_permission_denied": ("Provider permission denied", 502, False),
    "provider_not_found": ("Provider resource was not found", 502, False),
    "provider_rate_limited": ("Provider rate limit exceeded", 429, True),
    "provider_request_rejected": ("Provider rejected the request", 502, False),
    "provider_invalid_response": ("Provider returned an invalid response", 502, False),
}


def _provider_error(code: str) -> ProviderError:
    public_message, status_code, retryable = _PROVIDER_ERRORS[code]
    return ProviderError(
        code=code,
        public_message=public_message,
        status_code=status_code,
        retryable=retryable,
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
