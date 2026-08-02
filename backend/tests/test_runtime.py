from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import mock_data


def _completion_payload() -> dict:
    return {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Say hello."},
        ],
        "max_tokens": 64,
        "temperature": 0.25,
    }


def test_valid_completion_forwards_options_and_adds_one_usage_event(
    client: TestClient,
    active_key,
    recording_provider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = iter([100.0, 100.042])
    monkeypatch.setattr("app.api.runtime.perf_counter", lambda: next(clock))
    before_count = len(mock_data.MOCK_USAGE_EVENTS)
    payload = _completion_payload()

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.key}"},
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "chatcmpl_test"
    assert body["object"] == "chat.completion"
    assert body["model"] == payload["model"]
    assert body["choices"][0]["message"] == {
        "role": "assistant",
        "content": "Test response",
    }
    assert body["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }
    assert recording_provider.calls == [
        {
            "messages": payload["messages"],
            "model": payload["model"],
            "max_tokens": payload["max_tokens"],
            "temperature": payload["temperature"],
        }
    ]
    assert recording_provider.cost_calls == [
        {
            "input_tokens": 11,
            "output_tokens": 7,
            "model": payload["model"],
        }
    ]
    assert len(mock_data.MOCK_USAGE_EVENTS) == before_count + 1
    event = mock_data.MOCK_USAGE_EVENTS[-1]
    assert event.sub_key_id == active_key.id
    assert event.user_id == active_key.owner_id
    assert event.model == payload["model"]
    assert event.input_tokens == 11
    assert event.output_tokens == 7
    assert event.total_tokens == 18
    assert event.estimated_cost_eur == recording_provider.cost
    assert event.latency_ms == 42
    assert event.status == "success"


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_detail"),
    [
        ("missing_header", 401, "Missing or invalid authorization header"),
        ("invalid_key", 401, "Invalid or inactive API key"),
        ("revoked_key", 401, "Invalid or inactive API key"),
        ("forbidden_model", 403, "Model gpt-4-preview not allowed for this key"),
        ("expired_key", 401, "API key has expired"),
        ("malformed_expiry", 401, "Invalid or inactive API key"),
    ],
)
def test_pre_provider_rejections_do_not_add_success_usage(
    client: TestClient,
    active_key,
    recording_provider,
    case: str,
    expected_status: int,
    expected_detail: str,
) -> None:
    payload = _completion_payload()
    headers = {"Authorization": f"Bearer {active_key.key}"}

    if case == "missing_header":
        headers = {}
    elif case == "invalid_key":
        headers = {"Authorization": "Bearer tailer_sub_invalid"}
    elif case == "revoked_key":
        active_key.status = "revoked"
    elif case == "forbidden_model":
        payload["model"] = "gpt-4-preview"
    elif case == "expired_key":
        active_key.expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
    elif case == "malformed_expiry":
        active_key.expires_at = "not-a-date"

    before_count = len(mock_data.MOCK_USAGE_EVENTS)
    response = client.post(
        "/v1/chat/completions",
        headers=headers,
        json=payload,
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert recording_provider.calls == []
    assert recording_provider.cost_calls == []
    assert len(mock_data.MOCK_USAGE_EVENTS) == before_count


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "   "),
        ("messages", []),
        ("messages", [{"role": "invalid", "content": "hello"}]),
        ("messages", [{"role": "user", "content": "   "}]),
        ("max_tokens", 0),
        ("max_tokens", -1),
        ("temperature", -0.01),
        ("temperature", 2.01),
    ],
)
def test_invalid_runtime_payload_is_rejected_before_provider_and_usage(
    client: TestClient,
    active_key,
    recording_provider,
    field: str,
    value: object,
) -> None:
    payload = _completion_payload()
    payload[field] = value
    before_count = len(mock_data.MOCK_USAGE_EVENTS)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.key}"},
        json=payload,
    )

    assert response.status_code == 422
    assert recording_provider.calls == []
    assert recording_provider.cost_calls == []
    assert len(mock_data.MOCK_USAGE_EVENTS) == before_count


@pytest.mark.parametrize(
    ("usage_field", "invalid_value"),
    [
        ("prompt_tokens", -1),
        ("completion_tokens", -1),
        ("total_tokens", -1),
    ],
)
def test_invalid_provider_usage_does_not_add_success_event(
    client: TestClient,
    active_key,
    recording_provider,
    usage_field: str,
    invalid_value: int,
) -> None:
    setattr(recording_provider.result.usage, usage_field, invalid_value)
    before_count = len(mock_data.MOCK_USAGE_EVENTS)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.key}"},
        json=_completion_payload(),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Provider returned invalid usage data"}
    assert len(mock_data.MOCK_USAGE_EVENTS) == before_count


def test_invalid_provider_cost_does_not_add_success_event(
    client: TestClient, active_key, recording_provider
) -> None:
    recording_provider.cost = -0.01
    before_count = len(mock_data.MOCK_USAGE_EVENTS)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.key}"},
        json=_completion_payload(),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Provider returned invalid usage data"}
    assert len(mock_data.MOCK_USAGE_EVENTS) == before_count
