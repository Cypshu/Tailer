import asyncio
from decimal import Decimal
import json

import httpx
import pytest

from app.providers import GeminiProvider, ProviderError


_API_KEY = "gemini-test-provider-secret-never-log"
_UPSTREAM_SECRET = "gemini-upstream-body-must-not-leak"


def _interaction_payload(*, status: str = "completed") -> dict:
    return {
        "id": "gemini_interaction_test",
        "model": "gemini-3.6-flash",
        "status": status,
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": " from Gemini"},
                ],
            }
        ],
        "usage": {
            "total_input_tokens": 11,
            "total_output_tokens": 7,
            "total_thought_tokens": 5,
            "total_tokens": 23,
        },
    }


def _call_provider(
    handler,
    *,
    messages: list[dict] | None = None,
    model: str = "gemini-3.6-flash",
    input_rate: Decimal = Decimal("0"),
    output_rate: Decimal = Decimal("0"),
):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GeminiProvider(
                _API_KEY,
                http_client=client,
                input_cost_per_million_eur=input_rate,
                output_cost_per_million_eur=output_rate,
            )
            result = await provider.chat_completions(
                messages=messages
                or [
                    {"role": "system", "content": "Be concise."},
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi"},
                    {"role": "user", "content": "Continue"},
                ],
                model=model,
                max_tokens=64,
                temperature=0.25,
            )
            return provider, result

    return asyncio.run(run())


def test_gemini_provider_sends_stateless_contract_and_parses_interaction() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_interaction_payload())

    provider, result = _call_provider(
        handler,
        input_rate=Decimal("2.5"),
        output_rate=Decimal("10"),
    )

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1/interactions"
    )
    assert request.headers["x-goog-api-key"] == _API_KEY
    assert request.headers["content-type"] == "application/json"
    assert "authorization" not in request.headers
    assert _API_KEY not in str(request.url)
    assert _API_KEY.encode() not in request.content
    assert json.loads(request.content) == {
        "model": "gemini-3.6-flash",
        "store": False,
        "input": [
            {
                "type": "user_input",
                "content": [{"type": "text", "text": "Hello"}],
            },
            {
                "type": "model_output",
                "content": [{"type": "text", "text": "Hi"}],
            },
            {
                "type": "user_input",
                "content": [{"type": "text", "text": "Continue"}],
            },
        ],
        "generation_config": {"max_output_tokens": 64},
        "system_instruction": "Be concise.",
    }
    assert result.id == "gemini_interaction_test"
    assert result.model == "gemini-3.6-flash"
    assert result.choices[0].message.role == "assistant"
    assert result.choices[0].message.content == "Hello from Gemini"
    assert result.choices[0].finish_reason == "stop"
    assert result.usage.prompt_tokens == 11
    # Completion accounting includes five Gemini thought tokens.
    assert result.usage.completion_tokens == 12
    assert result.usage.total_tokens == 23
    assert provider.calculate_cost(200_000, 50_000, result.model) == pytest.approx(1.0)
    assert _API_KEY not in repr(provider)


def test_gemini_provider_maps_incomplete_text_response_to_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_interaction_payload(status="incomplete"))

    _, result = _call_provider(handler)

    assert result.choices[0].finish_reason == "length"


def test_gemini_provider_accepts_incomplete_thought_only_response() -> None:
    payload = _interaction_payload(status="incomplete")
    payload.pop("id")
    payload["steps"] = [{"type": "thought", "signature": "opaque"}]
    payload["usage"] = {
        "total_input_tokens": 11,
        "total_output_tokens": 0,
        "total_thought_tokens": 64,
        "total_tokens": 75,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    _, result = _call_provider(handler)

    assert result.choices[0].message.content == ""
    assert result.choices[0].finish_reason == "length"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 64
    assert result.usage.total_tokens == 75


def test_gemini_provider_synthesizes_id_for_unstored_interaction() -> None:
    payload = _interaction_payload()
    payload.pop("id")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    _, result = _call_provider(handler)

    assert result.id.startswith("chatcmpl_gemini_")
    assert result.id == _call_provider(handler)[1].id


@pytest.mark.parametrize(
    ("status", "code", "message", "public_status", "retryable"),
    [
        (408, "provider_timeout", "Provider request timed out", 504, True),
        (401, "provider_authentication_failed", "Provider authentication failed", 502, False),
        (403, "provider_permission_denied", "Provider permission denied", 502, False),
        (404, "provider_not_found", "Provider resource was not found", 502, False),
        (429, "provider_rate_limited", "Provider rate limit exceeded", 429, True),
        (400, "provider_request_rejected", "Provider rejected the request", 502, False),
        (422, "provider_request_rejected", "Provider rejected the request", 502, False),
        (499, "provider_unavailable", "Provider is unavailable", 503, True),
        (500, "provider_unavailable", "Provider is unavailable", 503, True),
        (503, "provider_unavailable", "Provider is unavailable", 503, True),
        (504, "provider_timeout", "Provider request timed out", 504, True),
        (302, "provider_invalid_response", "Provider returned an invalid response", 502, False),
    ],
)
def test_gemini_provider_normalizes_http_errors_without_upstream_body(
    status: int,
    code: str,
    message: str,
    public_status: int,
    retryable: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"message": _UPSTREAM_SECRET}},
            headers={"x-request-id": _UPSTREAM_SECRET},
        )

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler)

    error = caught.value
    assert error.code == code
    assert error.public_message == message
    assert error.status_code == public_status
    assert error.retryable is retryable
    assert _UPSTREAM_SECRET not in repr(error)
    assert _API_KEY not in repr(error)


def test_gemini_provider_recognizes_api_key_invalid_inside_http_400() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "status": "INVALID_ARGUMENT",
                    "message": _UPSTREAM_SECRET,
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                            "reason": "API_KEY_INVALID",
                        }
                    ],
                }
            },
        )

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler)

    assert caught.value.code == "provider_authentication_failed"
    assert _UPSTREAM_SECRET not in repr(caught.value)


@pytest.mark.parametrize(
    ("exception_type", "code", "status_code"),
    [
        (httpx.ReadTimeout, "provider_timeout", 504),
        (httpx.ConnectError, "provider_unavailable", 503),
    ],
)
def test_gemini_provider_normalizes_transport_errors(
    exception_type,
    code: str,
    status_code: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception_type(_UPSTREAM_SECRET, request=request)

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler)

    assert caught.value.code == code
    assert caught.value.status_code == status_code
    assert _UPSTREAM_SECRET not in repr(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"id": "missing-fields"}),
        httpx.Response(
            200,
            json={
                **_interaction_payload(),
                "steps": [{"type": "thought", "content": []}],
            },
        ),
        httpx.Response(
            200,
            json={
                **_interaction_payload(),
                "usage": {
                    "total_input_tokens": 11,
                    "total_output_tokens": 7,
                    "total_tokens": 10,
                },
            },
        ),
        httpx.Response(
            200,
            json={**_interaction_payload(), "status": "queued"},
        ),
    ],
)
def test_gemini_provider_normalizes_invalid_success_responses(
    response: httpx.Response,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler)

    assert caught.value.code == "provider_invalid_response"


def test_gemini_provider_normalizes_logical_failure_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_interaction_payload(status="failed"))

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler)

    assert caught.value.code == "provider_request_rejected"


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "tool", "content": "unsupported tool result"}],
        [{"role": "system", "content": "system only"}],
        [{"role": "user", "content": "   "}],
    ],
)
def test_gemini_provider_rejects_untranslatable_messages_without_calling_upstream(
    messages: list[dict],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid messages must be rejected before provider I/O")

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler, messages=messages)

    assert caught.value.code == "provider_request_rejected"


def test_gemini_provider_rejects_invalid_model_without_calling_upstream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid model must be rejected before provider I/O")

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler, model="../../secret?key=leak")

    assert caught.value.code == "provider_request_rejected"


@pytest.mark.parametrize("rate", [Decimal("-0.1"), "NaN", "Infinity"])
def test_gemini_provider_rejects_invalid_prices(rate) -> None:
    with pytest.raises(ValueError, match="Provider price"):
        GeminiProvider(_API_KEY, input_cost_per_million_eur=rate)


def test_gemini_provider_rejects_invalid_token_counts() -> None:
    provider = GeminiProvider(_API_KEY)

    with pytest.raises(ValueError, match="Token counts"):
        provider.calculate_cost(-1, 0, "model")


def test_gemini_provider_rejects_plaintext_network_base_url() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        GeminiProvider(_API_KEY, base_url="http://provider.example.test/v1")
