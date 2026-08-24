from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Event, Thread
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.demo_seed import DEMO_RAW_KEYS
from app.domain import RequestAttemptRecord, UsageRecord
from app.main import app
from app.models import ChatCompletionRequest
from app.models_db import RequestAttempt
from app.providers import ProviderError
from app.repositories.base import PersistenceWriteError, UnitOfWorkFactory
from app.repositories.dependencies import get_uow_factory
from app.repositories.memory import MemoryUnitOfWorkFactory
from app.repositories.sqlalchemy import SqlAlchemyUnitOfWorkFactory
from app.services import (
    ConfigurationError,
    OwnedRuntimeAttempt,
    RuntimeAttemptContractError,
    RuntimeSuccessOutcome,
    TailerService,
)


def _completion_payload(*, prompt: str = "Say hello.") -> dict:
    return {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 64,
        "temperature": 0.25,
    }


def _runtime_headers(raw_key: str, idempotency_key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {raw_key}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


def _attempt_and_usage(
    factory: UnitOfWorkFactory,
    attempt_id: str,
) -> tuple[RequestAttemptRecord | None, UsageRecord | None]:
    with factory() as uow:
        return (
            uow.attempts.get_by_id(attempt_id),
            uow.usage.get_by_request_attempt_id(attempt_id),
        )


def _usage_ids(factory: UnitOfWorkFactory) -> set[str]:
    with factory() as uow:
        return {event.id for event in uow.usage.list(limit=None)}


def _attempt_count(factory: UnitOfWorkFactory) -> int:
    if isinstance(factory, MemoryUnitOfWorkFactory):
        return len(factory.store.attempts)
    assert isinstance(factory, SqlAlchemyUnitOfWorkFactory)
    with factory.session_factory() as session:
        return int(session.scalar(select(func.count(RequestAttempt.id))) or 0)


def _attempt_state_count(factory: UnitOfWorkFactory, state: str) -> int:
    if isinstance(factory, MemoryUnitOfWorkFactory):
        return sum(attempt.state == state for attempt in factory.store.attempts)
    assert isinstance(factory, SqlAlchemyUnitOfWorkFactory)
    with factory.session_factory() as session:
        return int(
            session.scalar(
                select(func.count(RequestAttempt.id)).where(
                    RequestAttempt.state == state
                )
            )
            or 0
        )


@contextmanager
def _client_for(factory: UnitOfWorkFactory) -> Iterator[TestClient]:
    previous = app.dependency_overrides.get(get_uow_factory)
    app.dependency_overrides[get_uow_factory] = lambda: factory
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_uow_factory, None)
        else:
            app.dependency_overrides[get_uow_factory] = previous


def _success_outcome() -> RuntimeSuccessOutcome:
    return RuntimeSuccessOutcome(
        provider_result_id="chatcmpl_test",
        input_tokens=11,
        output_tokens=7,
        total_tokens=18,
        estimated_cost_eur=Decimal("0.0123"),
        currency="EUR",
        latency_ms=42,
    )


def test_requests_without_idempotency_key_are_fresh_and_fully_attributed(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
) -> None:
    before_usage = _usage_ids(uow_factory)
    before_attempts = _attempt_count(uow_factory)
    headers = _runtime_headers(active_key.raw_key)
    payload = _completion_payload()

    first = client.post("/v1/chat/completions", headers=headers, json=payload)
    second = client.post("/v1/chat/completions", headers=headers, json=payload)

    assert first.status_code == second.status_code == 200
    first_id = first.headers["Tailer-Attempt-Id"]
    second_id = second.headers["Tailer-Attempt-Id"]
    assert first_id != second_id
    assert len(recording_provider.calls) == 2
    assert len(recording_provider.cost_calls) == 2

    for attempt_id in (first_id, second_id):
        attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
        assert attempt is not None
        assert usage is not None
        assert attempt.state == "succeeded"
        assert attempt.idempotency_key_digest is None
        assert attempt.request_fingerprint_digest is None
        assert attempt.provider == usage.provider == "recording"
        assert attempt.public_model == usage.model == payload["model"]
        assert attempt.provider_model == usage.provider_model == payload["model"]
        assert attempt.provider_result_id == "chatcmpl_test"
        assert (attempt.input_tokens, attempt.output_tokens, attempt.total_tokens) == (
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        ) == (11, 7, 18)
        assert attempt.estimated_cost_eur == usage.estimated_cost_eur == Decimal(
            "0.0123"
        )
        assert attempt.currency == usage.currency == "EUR"
        assert attempt.latency_ms == usage.latency_ms
        assert usage.request_attempt_id == attempt.id
        assert usage.status == "success"

    assert len(_usage_ids(uow_factory) - before_usage) == 2
    assert _attempt_count(uow_factory) == before_attempts + 2


@pytest.mark.parametrize("invalid_key", ["", "contains space", "x" * 256])
def test_invalid_idempotency_key_is_rejected_before_route_and_dispatch(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    invalid_key: str,
) -> None:
    before_usage = _usage_ids(uow_factory)
    before_attempts = _attempt_count(uow_factory)

    response = client.post(
        "/v1/chat/completions",
        headers=_runtime_headers(active_key.raw_key, invalid_key),
        json=_completion_payload(),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid Idempotency-Key"}
    assert "Tailer-Attempt-Id" not in response.headers
    assert recording_provider.calls == []
    assert recording_provider.cost_calls == []
    assert _usage_ids(uow_factory) == before_usage
    assert _attempt_count(uow_factory) == before_attempts


def test_schema_auth_policy_and_routing_failures_do_not_create_attempts(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_attempts = _attempt_count(uow_factory)
    before_usage = _usage_ids(uow_factory)
    valid_headers = _runtime_headers(active_key.raw_key, "preclaim-boundary")

    invalid_schema = client.post(
        "/v1/chat/completions",
        headers=valid_headers,
        json={**_completion_payload(), "max_tokens": 0},
    )
    missing_auth = client.post(
        "/v1/chat/completions",
        headers={"Idempotency-Key": "preclaim-boundary"},
        json=_completion_payload(),
    )
    policy_denial = client.post(
        "/v1/chat/completions",
        headers=valid_headers,
        json={**_completion_payload(), "model": "disallowed-model"},
    )

    def unavailable_route(*args, **kwargs):
        del args, kwargs
        raise ConfigurationError("Model route is unavailable")

    monkeypatch.setattr(
        TailerService,
        "resolve_runtime_provider",
        unavailable_route,
    )
    routing_failure = client.post(
        "/v1/chat/completions",
        headers=valid_headers,
        json=_completion_payload(),
    )

    assert [
        invalid_schema.status_code,
        missing_auth.status_code,
        policy_denial.status_code,
        routing_failure.status_code,
    ] == [422, 401, 403, 503]
    assert all(
        "Tailer-Attempt-Id" not in response.headers
        for response in (
            invalid_schema,
            missing_auth,
            policy_denial,
            routing_failure,
        )
    )
    assert recording_provider.calls == []
    assert recording_provider.cost_calls == []
    assert _attempt_count(uow_factory) == before_attempts
    assert _usage_ids(uow_factory) == before_usage


def test_success_duplicate_is_not_replayed_and_key_reuse_mismatch_is_rejected(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_idempotency_key = "success-key-privacy-sentinel"
    prompt_sentinel = "PROMPT_CONTENT_MUST_NOT_BE_STORED"
    headers = _runtime_headers(active_key.raw_key, raw_idempotency_key)
    payload = _completion_payload(prompt=prompt_sentinel)
    caplog.clear()

    first = client.post("/v1/chat/completions", headers=headers, json=payload)
    duplicate = client.post("/v1/chat/completions", headers=headers, json=payload)
    changed_payload = dict(payload, temperature=0.5)
    mismatch = client.post(
        "/v1/chat/completions",
        headers=headers,
        json=changed_payload,
    )

    assert first.status_code == 200
    attempt_id = first.headers["Tailer-Attempt-Id"]
    assert duplicate.status_code == 409
    assert duplicate.headers["Tailer-Attempt-Id"] == attempt_id
    assert duplicate.json() == {
        "detail": {
            "code": "completed_result_not_replayable",
            "message": "Request completed, but response content was not retained",
            "retryable": False,
        }
    }
    assert mismatch.status_code == 409
    assert mismatch.headers["Tailer-Attempt-Id"] == attempt_id
    assert mismatch.json() == {
        "detail": {
            "code": "idempotency_key_reused",
            "message": "Idempotency-Key was already used for a different request",
            "retryable": False,
        }
    }
    assert len(recording_provider.calls) == 1
    assert len(recording_provider.cost_calls) == 1

    attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
    assert attempt is not None
    assert usage is not None
    persisted_text = repr(asdict(attempt)) + repr(asdict(usage))
    assert raw_idempotency_key not in persisted_text
    assert prompt_sentinel not in persisted_text
    assert "Test response" not in persisted_text
    assert active_key.raw_key not in persisted_text
    handled_text = duplicate.text + mismatch.text + caplog.text
    assert raw_idempotency_key not in handled_text
    assert prompt_sentinel not in handled_text
    assert "Test response" not in handled_text
    assert active_key.raw_key not in handled_text
    assert attempt.idempotency_key_digest is not None
    assert attempt.request_fingerprint_digest is not None
    assert len(attempt.idempotency_key_digest) == 64
    assert len(attempt.request_fingerprint_digest) == 64
    assert len(attempt.dispatch_token_digest) == 64


def test_content_derived_mock_response_id_is_not_persisted(
    client: TestClient,
    active_key,
    uow_factory: UnitOfWorkFactory,
) -> None:
    prompt = "MOCK_PROMPT_DICTIONARY_SENTINEL"
    response = client.post(
        "/v1/chat/completions",
        headers=_runtime_headers(active_key.raw_key, "mock-id-privacy"),
        json=_completion_payload(prompt=prompt),
    )

    assert response.status_code == 200
    assert response.json()["id"].startswith("chatcmpl_mock_")
    attempt, usage = _attempt_and_usage(
        uow_factory,
        response.headers["Tailer-Attempt-Id"],
    )
    assert attempt is not None and usage is not None
    assert attempt.provider == "mock"
    assert attempt.provider_result_id is None
    persisted_text = repr(asdict(attempt)) + repr(asdict(usage))
    assert prompt not in persisted_text
    assert response.json()["id"] not in persisted_text


def test_fingerprint_uses_effective_defaults_and_ignores_unknown_input(
    client: TestClient,
    active_key,
    recording_provider,
) -> None:
    headers = _runtime_headers(active_key.raw_key, "canonical-effective-request")
    minimal_payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Canonical request"}],
    }
    explicit_payload = {
        **minimal_payload,
        "max_tokens": 2000,
        "temperature": 0.7,
        "ignored_future_field": "not part of the validated request",
    }

    first = client.post(
        "/v1/chat/completions",
        headers=headers,
        json=minimal_payload,
    )
    duplicate = client.post(
        "/v1/chat/completions",
        headers=headers,
        json=explicit_payload,
    )

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "completed_result_not_replayable"
    assert duplicate.headers["Tailer-Attempt-Id"] == first.headers[
        "Tailer-Attempt-Id"
    ]
    assert len(recording_provider.calls) == 1
    assert len(recording_provider.cost_calls) == 1


def test_idempotency_identity_is_scoped_to_the_authenticated_sub_api_key(
    client: TestClient,
    active_key,
    recording_provider,
) -> None:
    payload = _completion_payload()
    idempotency_key = "credential-scoped-identity"

    first = client.post(
        "/v1/chat/completions",
        headers=_runtime_headers(active_key.raw_key, idempotency_key),
        json=payload,
    )
    second = client.post(
        "/v1/chat/completions",
        headers=_runtime_headers(DEMO_RAW_KEYS["subkey_2"], idempotency_key),
        json=payload,
    )

    assert first.status_code == second.status_code == 200
    assert first.headers["Tailer-Attempt-Id"] != second.headers[
        "Tailer-Attempt-Id"
    ]
    assert len(recording_provider.calls) == 2
    assert len(recording_provider.cost_calls) == 2


def test_idempotency_key_is_case_sensitive_after_header_parsing(
    client: TestClient,
    active_key,
    recording_provider,
) -> None:
    payload = _completion_payload()

    uppercase = client.post(
        "/v1/chat/completions",
        headers=_runtime_headers(active_key.raw_key, "Case-Sensitive-Key"),
        json=payload,
    )
    lowercase = client.post(
        "/v1/chat/completions",
        headers=_runtime_headers(active_key.raw_key, "case-sensitive-key"),
        json=payload,
    )

    assert uppercase.status_code == lowercase.status_code == 200
    assert uppercase.headers["Tailer-Attempt-Id"] != lowercase.headers[
        "Tailer-Attempt-Id"
    ]
    assert len(recording_provider.calls) == 2
    assert len(recording_provider.cost_calls) == 2


def test_concurrent_keyed_duplicate_is_fenced_before_a_second_dispatch(
    client: TestClient,
    active_key,
    recording_provider,
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
) -> None:
    claim_barrier = Barrier(2)
    provider_entered = Event()
    allow_provider_completion = Event()
    duplicate_returned = Event()
    original_claim = TailerService.claim_runtime_attempt
    original_provider_call = recording_provider.chat_completions

    def synchronized_claim(service, key, route, identity):
        claim_barrier.wait(timeout=10)
        return original_claim(service, key, route, identity)

    async def blocked_provider_call(**kwargs):
        result = await original_provider_call(**kwargs)
        provider_entered.set()
        released = await run_in_threadpool(allow_provider_completion.wait, 10)
        assert released
        return result

    monkeypatch.setattr(TailerService, "claim_runtime_attempt", synchronized_claim)
    monkeypatch.setattr(
        recording_provider,
        "chat_completions",
        blocked_provider_call,
    )

    headers = _runtime_headers(active_key.raw_key, "concurrent-request")
    payload = _completion_payload()
    before_attempts = _attempt_count(uow_factory)
    before_usage = _usage_ids(uow_factory)
    responses = []
    errors: list[BaseException] = []

    def issue_request() -> None:
        try:
            response = client.post(
                "/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            responses.append(response)
            if response.status_code == 409:
                duplicate_returned.set()
        except BaseException as exc:  # pragma: no cover - diagnostic guard
            errors.append(exc)
            duplicate_returned.set()
            allow_provider_completion.set()

    first_thread = Thread(target=issue_request)
    second_thread = Thread(target=issue_request)
    first_thread.start()
    second_thread.start()
    assert provider_entered.wait(timeout=10)
    assert duplicate_returned.wait(timeout=10)
    assert len(recording_provider.calls) == 1
    assert recording_provider.cost_calls == []
    allow_provider_completion.set()
    first_thread.join(timeout=10)
    second_thread.join(timeout=10)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []
    assert sorted(response.status_code for response in responses) == [200, 409]
    success = next(response for response in responses if response.status_code == 200)
    duplicate = next(response for response in responses if response.status_code == 409)
    assert duplicate.headers["Tailer-Attempt-Id"] == success.headers[
        "Tailer-Attempt-Id"
    ]
    assert duplicate.json() == {
        "detail": {
            "code": "request_in_progress",
            "message": "Request is already in progress or fenced pending resolution",
            "retryable": True,
        }
    }
    assert len(recording_provider.calls) == 1
    assert len(recording_provider.cost_calls) == 1
    assert _attempt_count(uow_factory) == before_attempts + 1
    assert len(_usage_ids(uow_factory) - before_usage) == 1
    attempt, usage = _attempt_and_usage(
        uow_factory,
        success.headers["Tailer-Attempt-Id"],
    )
    assert attempt is not None and attempt.state == "succeeded"
    assert usage is not None and usage.request_attempt_id == attempt.id


@pytest.mark.parametrize(
    ("certainty", "code", "public_message", "status_code", "expected_state"),
    [
        (
            "not_executed",
            "provider_rate_limited",
            "Provider request was rate limited",
            429,
            "provider_failed",
        ),
        (
            "unknown",
            "provider_timeout",
            "Provider request timed out",
            503,
            "provider_outcome_uncertain",
        ),
    ],
)
def test_provider_failure_certainty_controls_durable_state_and_duplicate_contract(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    monkeypatch: pytest.MonkeyPatch,
    certainty: str,
    code: str,
    public_message: str,
    status_code: int,
    expected_state: str,
) -> None:
    original_provider_call = recording_provider.chat_completions

    async def fail_after_recording(**kwargs):
        await original_provider_call(**kwargs)
        raise ProviderError(
            code=code,
            public_message=public_message,
            status_code=status_code,
            retryable=certainty == "not_executed",
            execution_certainty=certainty,
        )

    monkeypatch.setattr(recording_provider, "chat_completions", fail_after_recording)
    headers = _runtime_headers(active_key.raw_key, f"failure-{certainty}")
    payload = _completion_payload()

    first = client.post("/v1/chat/completions", headers=headers, json=payload)
    duplicate = client.post("/v1/chat/completions", headers=headers, json=payload)

    assert first.status_code == status_code
    attempt_id = first.headers["Tailer-Attempt-Id"]
    assert first.json() == {
        "detail": {
            "code": code,
            "message": public_message,
            "retryable": certainty == "not_executed",
        }
    }
    assert duplicate.headers["Tailer-Attempt-Id"] == attempt_id
    assert len(recording_provider.calls) == 1
    assert recording_provider.cost_calls == []

    attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
    assert attempt is not None
    assert attempt.state == expected_state
    assert attempt.error_code == code
    assert attempt.error_http_status == status_code
    assert attempt.error_public_message == public_message
    assert attempt.error_retryable is (certainty == "not_executed")
    assert attempt.provider == "recording"
    assert attempt.public_model == payload["model"]
    assert attempt.provider_model == payload["model"]
    if certainty == "not_executed":
        assert duplicate.status_code == status_code
        assert duplicate.json() == first.json()
        assert usage is not None
        assert usage.request_attempt_id == attempt_id
        assert usage.status == "rate_limited"
        assert usage.provider == attempt.provider
        assert usage.model == attempt.public_model
        assert usage.provider_model == attempt.provider_model
        assert (
            attempt.input_tokens,
            attempt.output_tokens,
            attempt.total_tokens,
        ) == (usage.input_tokens, usage.output_tokens, usage.total_tokens) == (
            0,
            0,
            0,
        )
        assert attempt.estimated_cost_eur == usage.estimated_cost_eur == Decimal(
            "0"
        )
        assert attempt.currency == usage.currency == "EUR"
        assert attempt.latency_ms == usage.latency_ms
        assert usage.error_code == attempt.error_code
        assert attempt.idempotency_expires_at is not None
    else:
        assert duplicate.status_code == 503
        assert duplicate.json() == {
            "detail": {
                "code": "request_outcome_uncertain",
                "message": (
                    "Request outcome is uncertain and will not be re-executed "
                    "automatically"
                ),
                "retryable": False,
            }
        }
        assert usage is None
        assert attempt.input_tokens is None
        assert attempt.estimated_cost_eur is None
        assert attempt.currency is None
        assert attempt.idempotency_expires_at is None


@pytest.mark.parametrize(
    ("certainty", "expected_state", "duplicate_code"),
    [
        ("not_executed", "finalization_failed", None),
        (
            "unknown",
            "provider_outcome_uncertain",
            "request_outcome_uncertain",
        ),
    ],
)
def test_provider_failure_finalization_failure_preserves_safe_certainty_state(
    scripted_commit_factory,
    uow_factory: UnitOfWorkFactory,
    active_key,
    recording_provider,
    monkeypatch: pytest.MonkeyPatch,
    certainty: str,
    expected_state: str,
    duplicate_code: str | None,
) -> None:
    sentinel = "PROVIDER_FINALIZATION_DRIVER_SECRET"
    failing_factory = scripted_commit_factory(
        lambda: PersistenceWriteError(sentinel),
        fail_on_commit=2,
    )
    original_provider_call = recording_provider.chat_completions

    async def fail_after_recording(**kwargs):
        await original_provider_call(**kwargs)
        raise ProviderError(
            code="provider_rate_limited" if certainty == "not_executed" else "provider_timeout",
            public_message=(
                "Provider request was rate limited"
                if certainty == "not_executed"
                else "Provider request timed out"
            ),
            status_code=429 if certainty == "not_executed" else 504,
            retryable=True,
            execution_certainty=certainty,
        )

    monkeypatch.setattr(recording_provider, "chat_completions", fail_after_recording)
    headers = _runtime_headers(
        active_key.raw_key,
        f"provider-finalization-{certainty}",
    )
    before_usage = _usage_ids(uow_factory)
    with _client_for(failing_factory) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=headers,
            json=_completion_payload(),
        )
        duplicate = client.post(
            "/v1/chat/completions",
            headers=headers,
            json=_completion_payload(),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Usage finalization is unavailable"}
    attempt_id = response.headers["Tailer-Attempt-Id"]
    assert duplicate.headers["Tailer-Attempt-Id"] == attempt_id
    assert len(recording_provider.calls) == 1
    assert recording_provider.cost_calls == []
    assert _usage_ids(uow_factory) == before_usage
    attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
    assert attempt is not None and attempt.state == expected_state
    assert usage is None
    assert attempt.idempotency_expires_at is None
    assert attempt.error_retryable is True
    if certainty == "not_executed":
        assert duplicate.status_code == 503
        assert duplicate.json() == response.json()
        assert attempt.error_code == "provider_rate_limited"
        assert attempt.error_http_status == 429
        assert attempt.error_public_message == "Provider request was rate limited"
        assert (
            attempt.input_tokens,
            attempt.output_tokens,
            attempt.total_tokens,
        ) == (0, 0, 0)
        assert attempt.estimated_cost_eur == Decimal("0")
        assert attempt.currency == "EUR"
    else:
        assert duplicate.status_code == 503
        assert duplicate.json()["detail"]["code"] == duplicate_code
        assert attempt.error_code == "provider_timeout"
        assert attempt.error_http_status == 504
        assert attempt.error_public_message == "Provider request timed out"
        assert attempt.input_tokens is None
        assert attempt.estimated_cost_eur is None
        assert attempt.currency is None
    assert sentinel not in response.text + duplicate.text


@pytest.mark.parametrize(
    ("certainty", "status_code", "expected_state"),
    [
        ("not_executed", 429, "provider_failed"),
        ("unknown", 504, "provider_outcome_uncertain"),
    ],
)
def test_provider_failure_commit_acknowledgement_loss_is_confirmed_by_readback(
    scripted_commit_factory,
    uow_factory: UnitOfWorkFactory,
    active_key,
    recording_provider,
    monkeypatch: pytest.MonkeyPatch,
    certainty: str,
    status_code: int,
    expected_state: str,
) -> None:
    sentinel = "PROVIDER_ACKNOWLEDGEMENT_DRIVER_SECRET"
    failing_factory = scripted_commit_factory(
        lambda: PersistenceWriteError(sentinel),
        fail_on_commit=2,
        persist_before_failure=True,
    )
    original_provider_call = recording_provider.chat_completions
    code = (
        "provider_rate_limited"
        if certainty == "not_executed"
        else "provider_timeout"
    )
    public_message = (
        "Provider request was rate limited"
        if certainty == "not_executed"
        else "Provider request timed out"
    )

    async def fail_after_recording(**kwargs):
        await original_provider_call(**kwargs)
        raise ProviderError(
            code=code,
            public_message=public_message,
            status_code=status_code,
            retryable=True,
            execution_certainty=certainty,
        )

    monkeypatch.setattr(recording_provider, "chat_completions", fail_after_recording)
    headers = _runtime_headers(
        active_key.raw_key,
        f"provider-acknowledgement-{certainty}",
    )
    before_usage = _usage_ids(uow_factory)
    with _client_for(failing_factory) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=headers,
            json=_completion_payload(),
        )
        duplicate = client.post(
            "/v1/chat/completions",
            headers=headers,
            json=_completion_payload(),
        )

    assert response.status_code == status_code
    assert response.json() == {
        "detail": {
            "code": code,
            "message": public_message,
            "retryable": True,
        }
    }
    attempt_id = response.headers["Tailer-Attempt-Id"]
    assert duplicate.headers["Tailer-Attempt-Id"] == attempt_id
    assert len(recording_provider.calls) == 1
    assert recording_provider.cost_calls == []
    attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
    assert attempt is not None and attempt.state == expected_state
    if certainty == "not_executed":
        assert duplicate.status_code == status_code
        assert duplicate.json() == response.json()
        assert usage is not None
        assert usage.request_attempt_id == attempt_id
        assert len(_usage_ids(uow_factory) - before_usage) == 1
    else:
        assert duplicate.status_code == 503
        assert duplicate.json()["detail"]["code"] == "request_outcome_uncertain"
        assert usage is None
        assert _usage_ids(uow_factory) == before_usage
    assert sentinel not in response.text + duplicate.text


@pytest.mark.parametrize("persist_before_failure", [False, True], ids=["before", "after"])
def test_claim_commit_failure_dispatches_only_after_durable_ownership(
    scripted_commit_factory,
    uow_factory: UnitOfWorkFactory,
    active_key,
    recording_provider,
    persist_before_failure: bool,
) -> None:
    sentinel = "CLAIM_DRIVER_SECRET"
    failing_factory = scripted_commit_factory(
        lambda: PersistenceWriteError(sentinel),
        fail_on_commit=1,
        persist_before_failure=persist_before_failure,
    )
    before_usage = _usage_ids(uow_factory)
    with _client_for(failing_factory) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=_runtime_headers(active_key.raw_key, "claim-acknowledgement"),
            json=_completion_payload(),
        )

    if persist_before_failure:
        assert response.status_code == 200
        attempt_id = response.headers["Tailer-Attempt-Id"]
        attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
        assert attempt is not None and attempt.state == "succeeded"
        assert usage is not None
        assert len(recording_provider.calls) == 1
        assert len(recording_provider.cost_calls) == 1
        assert len(_usage_ids(uow_factory) - before_usage) == 1
    else:
        assert response.status_code == 503
        assert response.json() == {"detail": "Request attempt is unavailable"}
        assert "Tailer-Attempt-Id" not in response.headers
        assert recording_provider.calls == []
        assert recording_provider.cost_calls == []
        assert _usage_ids(uow_factory) == before_usage
    assert sentinel not in response.text
    assert active_key.raw_key not in response.text


@pytest.mark.parametrize("readback", ["unavailable", "token-mismatch"])
def test_claim_acknowledgement_loss_fails_closed_without_owner_confirmation(
    scripted_commit_factory,
    uow_factory: UnitOfWorkFactory,
    active_key,
    recording_provider,
    monkeypatch: pytest.MonkeyPatch,
    readback: str,
) -> None:
    sentinel = "CLAIM_READBACK_DRIVER_SECRET"
    failing_factory = scripted_commit_factory(
        lambda: PersistenceWriteError(sentinel),
        fail_on_commit=1,
        persist_before_failure=True,
    )
    original_read = TailerService._get_attempt_by_id

    if readback == "unavailable":
        def unavailable_read(service, attempt_id):
            del service, attempt_id
            raise PersistenceWriteError(sentinel)

        monkeypatch.setattr(
            TailerService,
            "_get_attempt_by_id",
            unavailable_read,
        )
    else:
        def mismatched_read(service, attempt_id):
            observed = original_read(service, attempt_id)
            assert observed is not None
            return replace(observed, dispatch_token_digest="f" * 64)

        monkeypatch.setattr(
            TailerService,
            "_get_attempt_by_id",
            mismatched_read,
        )

    before_claimed = _attempt_state_count(uow_factory, "dispatch_claimed")
    with _client_for(failing_factory) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=_runtime_headers(
                active_key.raw_key,
                f"claim-readback-{readback}",
            ),
            json=_completion_payload(),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Request attempt is unavailable"}
    assert "Tailer-Attempt-Id" not in response.headers
    assert recording_provider.calls == []
    assert recording_provider.cost_calls == []
    assert _attempt_state_count(
        uow_factory,
        "dispatch_claimed",
    ) == before_claimed + 1
    assert sentinel not in response.text


@pytest.mark.parametrize("persist_before_failure", [False, True], ids=["before", "after"])
def test_finalization_commit_failure_uses_readback_or_safe_fenced_failure(
    scripted_commit_factory,
    uow_factory: UnitOfWorkFactory,
    active_key,
    recording_provider,
    persist_before_failure: bool,
) -> None:
    sentinel = "FINALIZATION_DRIVER_SECRET"
    failing_factory = scripted_commit_factory(
        lambda: PersistenceWriteError(sentinel),
        fail_on_commit=2,
        persist_before_failure=persist_before_failure,
    )
    headers = _runtime_headers(active_key.raw_key, "finalization-acknowledgement")
    before_usage = _usage_ids(uow_factory)

    with _client_for(failing_factory) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=headers,
            json=_completion_payload(),
        )
        duplicate = client.post(
            "/v1/chat/completions",
            headers=headers,
            json=_completion_payload(),
        )

    attempt_id = response.headers["Tailer-Attempt-Id"]
    assert duplicate.headers["Tailer-Attempt-Id"] == attempt_id
    attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
    assert attempt is not None
    assert len(recording_provider.calls) == 1
    assert len(recording_provider.cost_calls) == 1
    if persist_before_failure:
        assert response.status_code == 200
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "completed_result_not_replayable"
        assert attempt.state == "succeeded"
        assert usage is not None
        assert len(_usage_ids(uow_factory) - before_usage) == 1
    else:
        assert response.status_code == 503
        assert response.json() == {"detail": "Usage finalization is unavailable"}
        assert duplicate.status_code == 503
        assert duplicate.json() == response.json()
        assert attempt.state == "finalization_failed"
        assert attempt.provider_result_id == "chatcmpl_test"
        assert (
            attempt.input_tokens,
            attempt.output_tokens,
            attempt.total_tokens,
        ) == (11, 7, 18)
        assert attempt.estimated_cost_eur == Decimal("0.0123")
        assert attempt.currency == "EUR"
        assert attempt.latency_ms is not None and attempt.latency_ms >= 0
        assert attempt.error_code == "usage_finalization_unavailable"
        assert attempt.error_http_status == 503
        assert attempt.error_public_message == "Usage finalization is unavailable"
        assert attempt.error_retryable is False
        assert attempt.idempotency_expires_at is None
        assert usage is None
        assert _usage_ids(uow_factory) == before_usage
    assert sentinel not in response.text + duplicate.text
    assert active_key.raw_key not in response.text + duplicate.text


def test_high_precision_cost_is_normalized_before_commit_acknowledgement_readback(
    scripted_commit_factory,
    uow_factory: UnitOfWorkFactory,
    active_key,
    recording_provider,
) -> None:
    recording_provider.cost = 0.123456789
    failing_factory = scripted_commit_factory(
        lambda: PersistenceWriteError("cost acknowledgement lost"),
        fail_on_commit=2,
        persist_before_failure=True,
    )

    with _client_for(failing_factory) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=_runtime_headers(active_key.raw_key, "precise-cost-readback"),
            json=_completion_payload(),
        )

    assert response.status_code == 200
    assert len(recording_provider.calls) == 1
    assert len(recording_provider.cost_calls) == 1
    attempt, usage = _attempt_and_usage(
        uow_factory,
        response.headers["Tailer-Attempt-Id"],
    )
    assert attempt is not None and usage is not None
    assert attempt.estimated_cost_eur == Decimal("0.12345679")
    assert usage.estimated_cost_eur == Decimal("0.12345679")


@pytest.mark.parametrize(
    "persist_before_failure",
    [False, True],
    ids=["commit-absent", "commit-present"],
)
def test_unavailable_finalization_readback_returns_fixed_failure_and_stays_fenced(
    scripted_commit_factory,
    uow_factory: UnitOfWorkFactory,
    active_key,
    recording_provider,
    monkeypatch: pytest.MonkeyPatch,
    persist_before_failure: bool,
) -> None:
    sentinel = "FINALIZATION_READBACK_DRIVER_SECRET"
    failing_factory = scripted_commit_factory(
        lambda: PersistenceWriteError(sentinel),
        fail_on_commit=2,
        persist_before_failure=persist_before_failure,
    )

    def unavailable_read(service, attempt_id):
        del service, attempt_id
        raise PersistenceWriteError(sentinel)

    monkeypatch.setattr(
        TailerService,
        "_read_attempt_and_usage",
        unavailable_read,
    )
    headers = _runtime_headers(
        active_key.raw_key,
        f"finalization-readback-{persist_before_failure}",
    )
    before_usage = _usage_ids(uow_factory)

    with _client_for(failing_factory) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=headers,
            json=_completion_payload(),
        )
        duplicate = client.post(
            "/v1/chat/completions",
            headers=headers,
            json=_completion_payload(),
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Usage finalization is unavailable"}
    attempt_id = response.headers["Tailer-Attempt-Id"]
    assert duplicate.headers["Tailer-Attempt-Id"] == attempt_id
    assert len(recording_provider.calls) == 1
    assert len(recording_provider.cost_calls) == 1
    attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
    assert attempt is not None
    if persist_before_failure:
        assert attempt.state == "succeeded"
        assert usage is not None
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == (
            "completed_result_not_replayable"
        )
        assert len(_usage_ids(uow_factory) - before_usage) == 1
    else:
        assert attempt.state == "dispatch_claimed"
        assert usage is None
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "request_in_progress"
        assert _usage_ids(uow_factory) == before_usage
    assert sentinel not in response.text + duplicate.text


def test_compensation_acknowledgement_loss_accepts_only_the_safe_fenced_state(
    uow_factory: UnitOfWorkFactory,
    active_key,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TailerService(uow_factory)
    request = ChatCompletionRequest.model_validate(_completion_payload())
    identity = service.prepare_runtime_attempt_identity(
        active_key.record,
        request,
        "compensation-acknowledgement",
    )
    route = service.resolve_runtime_provider(active_key.record, request.model)
    owned = service.claim_runtime_attempt(active_key.record, route, identity)
    original_write = service._write_attempt_outcome
    write_count = 0

    def ambiguous_writes(owned_attempt, replacement, usage):
        nonlocal write_count
        write_count += 1
        if write_count == 1:
            raise PersistenceWriteError("target commit failed before persistence")
        original_write(owned_attempt, replacement, usage)
        raise PersistenceWriteError("compensation acknowledgement was lost")

    monkeypatch.setattr(service, "_write_attempt_outcome", ambiguous_writes)

    with pytest.raises(RuntimeAttemptContractError) as exc_info:
        service.finalize_runtime_success(owned, _success_outcome())

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Usage finalization is unavailable"
    assert write_count == 2
    attempt, usage = _attempt_and_usage(uow_factory, owned.attempt_id)
    assert attempt is not None and attempt.state == "finalization_failed"
    assert attempt.error_code == "usage_finalization_unavailable"
    assert usage is None


def test_dispatch_token_ownership_and_double_finalization_are_fenced(
    uow_factory: UnitOfWorkFactory,
    active_key,
    recording_provider,
) -> None:
    service = TailerService(uow_factory)
    request = ChatCompletionRequest.model_validate(_completion_payload())
    identity = service.prepare_runtime_attempt_identity(
        active_key.record,
        request,
        "dispatch-owner",
    )
    route = service.resolve_runtime_provider(active_key.record, request.model)
    owned = service.claim_runtime_attempt(active_key.record, route, identity)
    wrong_owner = OwnedRuntimeAttempt(
        record=owned.record,
        dispatch_token=b"not-the-dispatch-owner".ljust(32, b"!"),
    )

    with pytest.raises(RuntimeAttemptContractError) as wrong_error:
        service.finalize_runtime_success(wrong_owner, _success_outcome())
    assert wrong_error.value.status_code == 503
    assert wrong_error.value.detail == "Usage finalization is unavailable"
    claimed, usage = _attempt_and_usage(uow_factory, owned.attempt_id)
    assert claimed is not None and claimed.state == "dispatch_claimed"
    assert usage is None

    service.finalize_runtime_success(owned, _success_outcome())
    with pytest.raises(RuntimeAttemptContractError) as duplicate_error:
        service.finalize_runtime_success(owned, _success_outcome())
    assert duplicate_error.value.status_code == 503
    finalized, usage = _attempt_and_usage(uow_factory, owned.attempt_id)
    assert finalized is not None and finalized.state == "succeeded"
    assert usage is not None
    with uow_factory() as uow:
        linked = [
            event
            for event in uow.usage.list(limit=None)
            if event.request_attempt_id == owned.attempt_id
        ]
    assert linked == [usage]
    owned_repr = repr(owned)
    assert "<redacted>" in owned_repr
    assert owned.dispatch_token.hex() not in owned_repr


def test_unexpected_finalization_programming_error_is_not_normalized(
    uow_factory: UnitOfWorkFactory,
    active_key,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TailerService(uow_factory)
    request = ChatCompletionRequest.model_validate(_completion_payload())
    identity = service.prepare_runtime_attempt_identity(
        active_key.record,
        request,
        "programming-error-boundary",
    )
    route = service.resolve_runtime_provider(active_key.record, request.model)
    owned = service.claim_runtime_attempt(active_key.record, route, identity)
    failure = TypeError("unexpected-finalization-programming-error")

    def fail_programming_boundary(*args, **kwargs):
        del args, kwargs
        raise failure

    monkeypatch.setattr(service, "_write_attempt_outcome", fail_programming_boundary)

    with pytest.raises(TypeError) as exc_info:
        service.finalize_runtime_success(owned, _success_outcome())

    assert exc_info.value is failure
    attempt, usage = _attempt_and_usage(uow_factory, owned.attempt_id)
    assert attempt is not None and attempt.state == "dispatch_claimed"
    assert usage is None


def test_resolved_identity_expires_at_the_configured_thirty_day_boundary(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("app.services._utc_now", lambda: now[0])
    monkeypatch.setattr(
        "app.services.settings.idempotency_retention_days",
        30,
    )
    headers = _runtime_headers(active_key.raw_key, "retention-boundary")
    payload = _completion_payload()

    first = client.post("/v1/chat/completions", headers=headers, json=payload)
    first_id = first.headers["Tailer-Attempt-Id"]
    now[0] += timedelta(days=30) - timedelta(microseconds=1)
    before_expiry = client.post(
        "/v1/chat/completions",
        headers=headers,
        json=payload,
    )
    now[0] += timedelta(microseconds=1)
    at_expiry = client.post("/v1/chat/completions", headers=headers, json=payload)

    assert first.status_code == at_expiry.status_code == 200
    assert before_expiry.status_code == 409
    assert before_expiry.headers["Tailer-Attempt-Id"] == first_id
    second_id = at_expiry.headers["Tailer-Attempt-Id"]
    assert second_id != first_id
    assert len(recording_provider.calls) == 2
    assert len(recording_provider.cost_calls) == 2

    old_attempt, old_usage = _attempt_and_usage(uow_factory, first_id)
    new_attempt, new_usage = _attempt_and_usage(uow_factory, second_id)
    assert old_attempt is not None and old_usage is not None
    assert new_attempt is not None and new_usage is not None
    assert old_attempt.idempotency_key_digest is None
    assert old_attempt.request_fingerprint_digest is None
    assert old_attempt.state == new_attempt.state == "succeeded"
    assert old_usage.request_attempt_id == first_id
    assert new_usage.request_attempt_id == second_id


def test_unresolved_attempt_never_expires_or_redispatches(
    client: TestClient,
    active_key,
    recording_provider,
    uow_factory: UnitOfWorkFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    monkeypatch.setattr("app.services._utc_now", lambda: now[0])
    original_provider_call = recording_provider.chat_completions

    async def uncertain_failure(**kwargs):
        await original_provider_call(**kwargs)
        raise ProviderError(
            code="provider_timeout",
            public_message="Provider request timed out",
            status_code=503,
            retryable=True,
            execution_certainty="unknown",
        )

    monkeypatch.setattr(recording_provider, "chat_completions", uncertain_failure)
    headers = _runtime_headers(active_key.raw_key, "unresolved-retention")
    payload = _completion_payload()

    first = client.post("/v1/chat/completions", headers=headers, json=payload)
    now[0] += timedelta(days=3650)
    duplicate = client.post("/v1/chat/completions", headers=headers, json=payload)

    attempt_id = first.headers["Tailer-Attempt-Id"]
    assert first.status_code == 503
    assert duplicate.status_code == 503
    assert duplicate.headers["Tailer-Attempt-Id"] == attempt_id
    assert duplicate.json()["detail"]["code"] == "request_outcome_uncertain"
    assert len(recording_provider.calls) == 1
    assert recording_provider.cost_calls == []
    attempt, usage = _attempt_and_usage(uow_factory, attempt_id)
    assert attempt is not None
    assert attempt.state == "provider_outcome_uncertain"
    assert attempt.idempotency_key_digest is not None
    assert attempt.request_fingerprint_digest is not None
    assert attempt.idempotency_expires_at is None
    assert usage is None
