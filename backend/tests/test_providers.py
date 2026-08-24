import asyncio
from decimal import Decimal
import json

import httpx
import pytest

from app.providers import MockProvider, OpenAIProvider, ProviderError


_API_KEY = "sk-test-provider-secret"
_UPSTREAM_SECRET = "sk-upstream-body-must-not-leak"


def _completion_payload() -> dict:
    return {
        "id": "chatcmpl_openai_test",
        "model": "gpt-provider-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from OpenAI"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
        },
    }


def _call_provider(
    handler,
    *,
    input_rate: Decimal = Decimal("0"),
    output_rate: Decimal = Decimal("0"),
):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenAIProvider(
                _API_KEY,
                http_client=client,
                input_cost_per_million_eur=input_rate,
                output_cost_per_million_eur=output_rate,
            )
            result = await provider.chat_completions(
                messages=[{"role": "user", "content": "Hello"}],
                model="gpt-provider-model",
                max_tokens=64,
                temperature=0.25,
            )
            return provider, result

    return asyncio.run(run())


def test_openai_provider_sends_supported_contract_and_parses_completion() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion_payload())

    provider, result = _call_provider(
        handler,
        input_rate=Decimal("2.5"),
        output_rate=Decimal("10"),
    )

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {_API_KEY}"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "gpt-provider-model",
        "max_completion_tokens": 64,
        "temperature": 0.25,
    }
    assert result.id == "chatcmpl_openai_test"
    assert result.durable_provider_result_id == "chatcmpl_openai_test"
    assert result.model == "gpt-provider-model"
    assert result.choices[0].message.role == "assistant"
    assert result.choices[0].message.content == "Hello from OpenAI"
    assert result.choices[0].finish_reason == "stop"
    assert result.usage.prompt_tokens == 11
    assert result.usage.completion_tokens == 7
    assert result.usage.total_tokens == 18
    assert provider.calculate_cost(200_000, 50_000, result.model) == pytest.approx(1.0)
    assert _API_KEY not in repr(provider)


@pytest.mark.parametrize(
    (
        "status",
        "code",
        "message",
        "public_status",
        "retryable",
        "execution_certainty",
    ),
    [
        (408, "provider_timeout", "Provider request timed out", 504, True, "unknown"),
        (
            401,
            "provider_authentication_failed",
            "Provider authentication failed",
            502,
            False,
            "not_executed",
        ),
        (
            403,
            "provider_permission_denied",
            "Provider permission denied",
            502,
            False,
            "not_executed",
        ),
        (
            404,
            "provider_not_found",
            "Provider resource was not found",
            502,
            False,
            "not_executed",
        ),
        (
            429,
            "provider_rate_limited",
            "Provider rate limit exceeded",
            429,
            True,
            "not_executed",
        ),
        (
            400,
            "provider_request_rejected",
            "Provider rejected the request",
            502,
            False,
            "not_executed",
        ),
        (
            422,
            "provider_request_rejected",
            "Provider rejected the request",
            502,
            False,
            "not_executed",
        ),
        (500, "provider_unavailable", "Provider is unavailable", 503, True, "unknown"),
        (503, "provider_unavailable", "Provider is unavailable", 503, True, "unknown"),
        (
            302,
            "provider_invalid_response",
            "Provider returned an invalid response",
            502,
            False,
            "unknown",
        ),
    ],
)
def test_openai_provider_normalizes_http_errors_without_upstream_body(
    status: int,
    code: str,
    message: str,
    public_status: int,
    retryable: bool,
    execution_certainty: str,
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
    assert error.execution_certainty == execution_certainty
    assert str(error) == message
    assert _UPSTREAM_SECRET not in repr(error)
    assert _API_KEY not in repr(error)


@pytest.mark.parametrize(
    ("exception_type", "code", "message", "status_code"),
    [
        (httpx.ReadTimeout, "provider_timeout", "Provider request timed out", 504),
        (httpx.ConnectError, "provider_unavailable", "Provider is unavailable", 503),
    ],
)
def test_openai_provider_normalizes_transport_errors(
    exception_type,
    code: str,
    message: str,
    status_code: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exception_type(_UPSTREAM_SECRET, request=request)

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler)

    error = caught.value
    assert error.code == code
    assert error.public_message == message
    assert error.status_code == status_code
    assert error.execution_certainty == "unknown"
    assert _UPSTREAM_SECRET not in repr(error)
    assert _API_KEY not in repr(error)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"id": "missing-fields"}),
        httpx.Response(
            200,
            json={
                **_completion_payload(),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": None},
                        "finish_reason": "stop",
                    }
                ],
            },
        ),
        httpx.Response(
            200,
            json={
                **_completion_payload(),
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": -1,
                },
            },
        ),
    ],
)
def test_openai_provider_normalizes_invalid_success_responses(
    response: httpx.Response,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(ProviderError) as caught:
        _call_provider(handler)

    assert caught.value.code == "provider_invalid_response"
    assert caught.value.public_message == "Provider returned an invalid response"
    assert caught.value.status_code == 502
    assert caught.value.execution_certainty == "unknown"


def test_provider_error_defaults_execution_certainty_to_unknown() -> None:
    error = ProviderError(
        code="custom_provider_failure",
        public_message="Provider failed",
        status_code=502,
        retryable=False,
    )

    assert error.execution_certainty == "unknown"


@pytest.mark.parametrize("status_code", [400, 599])
def test_provider_error_accepts_exact_safe_field_boundaries(status_code: int) -> None:
    code = "a" + ("0" * 63)
    public_message = "x" * 200

    error = ProviderError(
        code=code,
        public_message=public_message,
        status_code=status_code,
        retryable=True,
        execution_certainty="not_executed",
    )

    assert error.code == code
    assert error.public_message == public_message
    assert error.status_code == status_code
    assert error.retryable is True
    assert error.execution_certainty == "not_executed"


@pytest.mark.parametrize(
    "code",
    [None, "", "Provider_error", "1provider_error", "provider-error", "a" * 65],
)
def test_provider_error_rejects_invalid_code(code) -> None:
    with pytest.raises(ValueError, match="Provider error code"):
        ProviderError(
            code=code,
            public_message="Provider failed",
            status_code=502,
            retryable=False,
        )


@pytest.mark.parametrize(
    "public_message",
    [None, "", "x" * 201, "unsafe\nmessage", "unsafe\tmessage", "unsafe\x7fmessage"],
)
def test_provider_error_rejects_invalid_public_message(public_message) -> None:
    with pytest.raises(ValueError, match="Provider public message"):
        ProviderError(
            code="custom_provider_failure",
            public_message=public_message,
            status_code=502,
            retryable=False,
        )


@pytest.mark.parametrize("status_code", [None, True, 399, 600, 502.0])
def test_provider_error_rejects_invalid_http_status(status_code) -> None:
    with pytest.raises(ValueError, match="Provider HTTP status"):
        ProviderError(
            code="custom_provider_failure",
            public_message="Provider failed",
            status_code=status_code,
            retryable=False,
        )


@pytest.mark.parametrize("retryable", [None, 0, 1, "false"])
def test_provider_error_rejects_non_boolean_retryability(retryable) -> None:
    with pytest.raises(ValueError, match="Provider retryability"):
        ProviderError(
            code="custom_provider_failure",
            public_message="Provider failed",
            status_code=502,
            retryable=retryable,
        )


@pytest.mark.parametrize(
    "execution_certainty",
    [None, "", "executed", "NOT_EXECUTED", 1, True],
)
def test_provider_error_rejects_invalid_execution_certainty(
    execution_certainty,
) -> None:
    with pytest.raises(ValueError, match="Provider execution certainty"):
        ProviderError(
            code="custom_provider_failure",
            public_message="Provider failed",
            status_code=502,
            retryable=False,
            execution_certainty=execution_certainty,
        )


@pytest.mark.parametrize("rate", [Decimal("-0.1"), "NaN", "Infinity"])
def test_openai_provider_rejects_invalid_prices(rate) -> None:
    with pytest.raises(ValueError, match="Provider price"):
        OpenAIProvider(_API_KEY, input_cost_per_million_eur=rate)


def test_openai_provider_rejects_invalid_token_counts() -> None:
    provider = OpenAIProvider(_API_KEY)

    with pytest.raises(ValueError, match="Token counts"):
        provider.calculate_cost(-1, 0, "model")


def test_openai_provider_rejects_plaintext_network_base_url() -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        OpenAIProvider(_API_KEY, base_url="http://provider.example.test/v1")


def test_mock_provider_id_is_deterministic() -> None:
    async def complete():
        return await MockProvider().chat_completions(
            messages=[{"role": "user", "content": "stable input"}],
            model="stable-model",
        )

    first = asyncio.run(complete())
    second = asyncio.run(complete())
    assert first.id == second.id
    assert first.durable_provider_result_id is None
    assert second.durable_provider_result_id is None
