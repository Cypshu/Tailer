from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.providers import ProviderError
from app.repositories.base import UnitOfWorkFactory
from app.services import TailerService


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


def _usage_ids(factory: UnitOfWorkFactory) -> set[str]:
    with factory() as uow:
        return {event.id for event in uow.usage.list(limit=None)}


def test_valid_completion_forwards_options_and_adds_one_usage_event(
    client: TestClient,
    active_key,
    recording_provider,
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
) -> None:
    clock = iter([100.0, 100.042])
    monkeypatch.setattr("app.api.runtime.perf_counter", lambda: next(clock))
    before_ids = _usage_ids(uow_factory)
    payload = _completion_payload()

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
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

    after_ids = _usage_ids(uow_factory)
    assert len(after_ids) == len(before_ids) + 1
    new_id = (after_ids - before_ids).pop()
    with uow_factory() as uow:
        event = uow.usage.get_by_id(new_id)
    assert event is not None
    assert event.sub_api_key_id == active_key.record.id
    assert event.user_id == active_key.record.owner_id
    assert event.model == payload["model"]
    assert event.provider_model == payload["model"]
    assert event.input_tokens == 11
    assert event.output_tokens == 7
    assert event.total_tokens == 18
    assert event.estimated_cost_eur == Decimal(str(recording_provider.cost))
    assert event.latency_ms == 42
    assert event.status == "success"


def test_provider_success_with_usage_finalization_failure_is_safe_and_not_retried(
    persistence_failure_client: TestClient,
    persistence_failure_harness,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    before_ids = _usage_ids(uow_factory)
    payload = _completion_payload()
    caplog.clear()

    response = persistence_failure_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json=payload,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Usage finalization is unavailable"}
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
    assert _usage_ids(uow_factory) == before_ids

    exposed_text = response.text + caplog.text
    assert persistence_failure_harness.driver_detail not in exposed_text
    assert persistence_failure_harness.sentinel_secret not in exposed_text
    assert active_key.raw_key not in exposed_text


def test_provider_failure_audit_finalization_uses_same_safe_contract(
    persistence_failure_client: TestClient,
    persistence_failure_harness,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_call = recording_provider.chat_completions
    provider_public_message = "Provider request was rate limited"

    async def fail_after_recording_call(**kwargs):
        await original_call(**kwargs)
        raise ProviderError(
            code="provider_rate_limited",
            public_message=provider_public_message,
            status_code=429,
            retryable=True,
            execution_certainty="not_executed",
        )

    monkeypatch.setattr(
        recording_provider,
        "chat_completions",
        fail_after_recording_call,
    )
    before_ids = _usage_ids(uow_factory)
    payload = _completion_payload()
    caplog.clear()

    response = persistence_failure_client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json=payload,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Usage finalization is unavailable"}
    assert recording_provider.calls == [
        {
            "messages": payload["messages"],
            "model": payload["model"],
            "max_tokens": payload["max_tokens"],
            "temperature": payload["temperature"],
        }
    ]
    assert recording_provider.cost_calls == []
    assert _usage_ids(uow_factory) == before_ids

    exposed_text = response.text + caplog.text
    assert persistence_failure_harness.driver_detail not in exposed_text
    assert persistence_failure_harness.sentinel_secret not in exposed_text
    assert provider_public_message not in exposed_text
    assert active_key.raw_key not in exposed_text


def test_request_at_max_tokens_policy_boundary_is_allowed_without_clamping(
    client: TestClient,
    active_key,
    recording_provider,
    mutate_key: Callable[..., None],
) -> None:
    payload = _completion_payload()
    mutate_key(
        active_key.record.id,
        max_tokens_per_request=payload["max_tokens"],
    )

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json=payload,
    )

    assert response.status_code == 200
    assert recording_provider.calls[0]["max_tokens"] == payload["max_tokens"]
    assert len(recording_provider.calls) == 1
    assert len(recording_provider.cost_calls) == 1


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_detail"),
    [
        ("missing_header", 401, "Missing or invalid authorization header"),
        ("invalid_key", 401, "Invalid or inactive API key"),
        ("revoked_key", 401, "Invalid or inactive API key"),
        ("forbidden_model", 403, "Model gpt-4-preview not allowed for this key"),
        (
            "max_tokens_exceeded",
            403,
            "Requested max_tokens (64) exceeds this key's limit (63)",
        ),
        ("expired_key", 401, "API key has expired"),
    ],
)
def test_pre_provider_rejections_do_not_add_success_usage(
    client: TestClient,
    active_key,
    recording_provider,
    mutate_key: Callable[..., None],
    uow_factory: UnitOfWorkFactory,
    case: str,
    expected_status: int,
    expected_detail: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _completion_payload()
    headers = {"Authorization": f"Bearer {active_key.raw_key}"}
    resolution_calls: list[tuple[str, str]] = []
    original_resolver = TailerService.resolve_runtime_provider

    def recording_resolver(
        service: TailerService,
        key,
        public_model: str,
    ):
        resolution_calls.append((key.id, public_model))
        return original_resolver(service, key, public_model)

    monkeypatch.setattr(
        TailerService,
        "resolve_runtime_provider",
        recording_resolver,
    )

    if case == "missing_header":
        headers = {}
    elif case == "invalid_key":
        headers = {"Authorization": "Bearer tailer_sub_invalid"}
    elif case == "revoked_key":
        mutate_key(active_key.record.id, status="revoked")
    elif case == "forbidden_model":
        payload["model"] = "gpt-4-preview"
    elif case == "max_tokens_exceeded":
        mutate_key(active_key.record.id, max_tokens_per_request=63)
    elif case == "expired_key":
        mutate_key(
            active_key.record.id,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )

    before_ids = _usage_ids(uow_factory)
    response = client.post(
        "/v1/chat/completions",
        headers=headers,
        json=payload,
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert resolution_calls == []
    assert recording_provider.calls == []
    assert recording_provider.cost_calls == []
    assert _usage_ids(uow_factory) == before_ids


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
    uow_factory: UnitOfWorkFactory,
    field: str,
    value: object,
) -> None:
    payload = _completion_payload()
    payload[field] = value
    before_ids = _usage_ids(uow_factory)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json=payload,
    )

    assert response.status_code == 422
    assert recording_provider.calls == []
    assert recording_provider.cost_calls == []
    assert _usage_ids(uow_factory) == before_ids


@pytest.mark.parametrize(
    ("usage_field", "invalid_value"),
    [
        ("prompt_tokens", -1),
        ("completion_tokens", -1),
        ("total_tokens", -1),
        ("prompt_tokens", True),
        ("completion_tokens", 1.5),
    ],
)
def test_invalid_provider_usage_does_not_add_success_event(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    usage_field: str,
    invalid_value: object,
) -> None:
    setattr(recording_provider.result.usage, usage_field, invalid_value)
    before_ids = _usage_ids(uow_factory)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json=_completion_payload(),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Provider returned invalid usage data"}
    assert _usage_ids(uow_factory) == before_ids
    attempt_id = response.headers["Tailer-Attempt-Id"]
    with uow_factory() as uow:
        attempt = uow.attempts.get_by_id(attempt_id)
        linked_usage = uow.usage.get_by_request_attempt_id(attempt_id)
    assert attempt is not None and attempt.state == "finalization_failed"
    assert attempt.error_code == "provider_invalid_usage"
    assert attempt.error_http_status == 502
    assert attempt.error_public_message == "Provider returned invalid usage data"
    assert attempt.error_retryable is False
    assert linked_usage is None


@pytest.mark.parametrize(
    "invalid_cost",
    [-0.01, float("nan"), float("inf"), 10_000_000_000.0],
)
def test_invalid_provider_cost_does_not_add_success_event(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    invalid_cost: float,
) -> None:
    recording_provider.cost = invalid_cost
    before_ids = _usage_ids(uow_factory)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json=_completion_payload(),
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "Provider returned invalid usage data"}
    assert _usage_ids(uow_factory) == before_ids
    attempt_id = response.headers["Tailer-Attempt-Id"]
    with uow_factory() as uow:
        attempt = uow.attempts.get_by_id(attempt_id)
        linked_usage = uow.usage.get_by_request_attempt_id(attempt_id)
    assert attempt is not None and attempt.state == "finalization_failed"
    assert attempt.error_code == "provider_invalid_usage"
    assert attempt.error_http_status == 502
    assert attempt.error_public_message == "Provider returned invalid usage data"
    assert attempt.error_retryable is False
    assert linked_usage is None
