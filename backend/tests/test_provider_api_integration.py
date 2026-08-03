from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.credential_security import generate_credential_encryption_key
from app.providers import (
    ChatCompletionChoice,
    ChatCompletionResult,
    ChatCompletionUsage,
    Message,
    ProviderError,
)
from app.repositories.base import UnitOfWorkFactory


_PROVIDER_SECRET = "sk-test-provider-api-secret-never-log"
_UPSTREAM_ERROR_SECRET = "upstream-error-body-must-not-leak"
_PUBLIC_MODEL = "tailer-openai-integration"
_PROVIDER_MODEL = "gpt-provider-integration-model"
_GEMINI_PROVIDER_SECRET = "gemini-test-provider-api-secret-never-log"
_GEMINI_PUBLIC_MODEL = "tailer-gemini-integration"
_GEMINI_PROVIDER_MODEL = "gemini-3.6-flash"
_KEY_VERSION = "integration-v1"


def _configure_encryption(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "credential_encryption_keys",
        {_KEY_VERSION: generate_credential_encryption_key()},
    )
    monkeypatch.setattr(settings, "credential_active_key_version", _KEY_VERSION)


def _create_credential(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    name: str = "Integration OpenAI",
    secret: str = _PROVIDER_SECRET,
    provider: str = "openai",
) -> dict[str, Any]:
    response = client.post(
        "/admin/provider-credentials",
        headers=admin_headers,
        json={
            "provider": provider,
            "name": name,
            "credential": secret,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_model_config(
    client: TestClient,
    admin_headers: dict[str, str],
    credential_id: str,
    *,
    public_model: str = _PUBLIC_MODEL,
    provider_model: str = _PROVIDER_MODEL,
) -> dict[str, Any]:
    response = client.post(
        "/admin/model-configs",
        headers=admin_headers,
        json={
            "public_model": public_model,
            "provider_model": provider_model,
            "credential_id": credential_id,
            "input_cost_per_million_eur": "2.5",
            "output_cost_per_million_eur": "10",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _allow_public_model(
    mutate_key,
    active_key,
    public_model: str = _PUBLIC_MODEL,
) -> None:
    mutate_key(
        active_key.record.id,
        allowed_models=[*active_key.record.allowed_models, public_model],
    )


def _usage_ids(factory: UnitOfWorkFactory) -> set[str]:
    with factory() as uow:
        return {event.id for event in uow.usage.list(limit=None)}


def test_credential_creation_fails_closed_without_encryption_configuration(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
) -> None:
    monkeypatch.setattr(settings, "credential_encryption_keys", {})
    monkeypatch.setattr(settings, "credential_active_key_version", _KEY_VERSION)
    with uow_factory() as uow:
        before_ids = {item.id for item in uow.provider_credentials.list()}

    response = client.post(
        "/admin/provider-credentials",
        headers=admin_headers,
        json={
            "provider": "openai",
            "name": "Unconfigured OpenAI",
            "credential": _PROVIDER_SECRET,
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Provider credential encryption is not configured"
    }
    assert _PROVIDER_SECRET not in response.text
    with uow_factory() as uow:
        assert {item.id for item in uow.provider_credentials.list()} == before_ids


def test_credential_create_and_list_expose_only_safe_metadata(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _configure_encryption(monkeypatch)

    created = _create_credential(client, admin_headers)

    assert created["provider"] == "openai"
    assert created["name"] == "Integration OpenAI"
    assert created["status"] == "active"
    assert created["key_version"] == _KEY_VERSION
    assert created["secret_hint"].startswith("****")
    assert "credential" not in created
    assert "ciphertext" not in created
    assert _PROVIDER_SECRET not in str(created)

    with uow_factory() as uow:
        stored = uow.provider_credentials.get_by_id(created["id"])
    assert stored is not None
    assert stored.ciphertext
    assert stored.ciphertext != _PROVIDER_SECRET
    assert _PROVIDER_SECRET not in stored.ciphertext
    assert stored.ciphertext not in repr(stored)
    assert _PROVIDER_SECRET not in repr(stored)

    listing = client.get("/admin/provider-credentials", headers=admin_headers)

    assert listing.status_code == 200
    listed = next(item for item in listing.json() if item["id"] == created["id"])
    assert listed == created
    assert "credential" not in listed
    assert "ciphertext" not in listed
    assert _PROVIDER_SECRET not in listing.text
    assert stored.ciphertext not in listing.text
    assert _PROVIDER_SECRET not in caplog.text
    assert stored.ciphertext not in caplog.text


def test_duplicate_credential_name_returns_conflict_without_extra_row(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
) -> None:
    _configure_encryption(monkeypatch)
    created = _create_credential(client, admin_headers)

    duplicate = client.post(
        "/admin/provider-credentials",
        headers=admin_headers,
        json={
            "provider": "openai",
            "name": created["name"],
            "credential": "sk-test-second-secret",
        },
    )

    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Provider credential name already exists for this project"
    }
    with uow_factory() as uow:
        matching = [
            item
            for item in uow.provider_credentials.list()
            if item.name == created["name"]
        ]
    assert [item.id for item in matching] == [created["id"]]


def test_admin_can_create_list_and_disable_model_config(
    client: TestClient,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
) -> None:
    _configure_encryption(monkeypatch)
    credential = _create_credential(client, admin_headers)

    created = _create_model_config(client, admin_headers, credential["id"])

    assert created["public_model"] == _PUBLIC_MODEL
    assert created["provider"] == "openai"
    assert created["provider_model"] == _PROVIDER_MODEL
    assert created["credential_id"] == credential["id"]
    assert Decimal(created["input_cost_per_million_eur"]) == Decimal("2.5")
    assert Decimal(created["output_cost_per_million_eur"]) == Decimal("10")
    assert created["enabled"] is True

    listing = client.get("/admin/model-configs", headers=admin_headers)
    assert listing.status_code == 200
    listed = next(item for item in listing.json() if item["id"] == created["id"])
    assert {
        key: value
        for key, value in listed.items()
        if key
        not in {
            "input_cost_per_million_eur",
            "output_cost_per_million_eur",
        }
    } == {
        key: value
        for key, value in created.items()
        if key
        not in {
            "input_cost_per_million_eur",
            "output_cost_per_million_eur",
        }
    }
    assert Decimal(listed["input_cost_per_million_eur"]) == Decimal("2.5")
    assert Decimal(listed["output_cost_per_million_eur"]) == Decimal("10")

    disabled = client.delete(
        f"/admin/model-configs/{created['id']}", headers=admin_headers
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    with uow_factory() as uow:
        stored = uow.model_configs.get_by_id(created["id"])
        resolved = uow.model_configs.get_enabled(
            settings.default_project_id, _PUBLIC_MODEL
        )
    assert stored is not None
    assert stored.enabled is False
    assert resolved is None


def test_configured_alias_uses_decrypted_credential_provider_model_and_pricing(
    client: TestClient,
    admin_headers: dict[str, str],
    active_key,
    mutate_key,
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _configure_encryption(monkeypatch)
    _allow_public_model(mutate_key, active_key)
    credential = _create_credential(client, admin_headers)
    _create_model_config(client, admin_headers, credential["id"])
    with uow_factory() as uow:
        stored_credential = uow.provider_credentials.get_by_id(credential["id"])
    assert stored_credential is not None

    constructor_calls: list[dict[str, Any]] = []
    completion_calls: list[dict[str, Any]] = []
    cost_calls: list[dict[str, Any]] = []

    class FakeOpenAIProvider:
        name = "openai"

        def __init__(
            self,
            api_key: str,
            *,
            base_url: str,
            timeout_seconds: float,
            input_cost_per_million_eur: Decimal,
            output_cost_per_million_eur: Decimal,
        ) -> None:
            self.input_rate = Decimal(input_cost_per_million_eur)
            self.output_rate = Decimal(output_cost_per_million_eur)
            constructor_calls.append(
                {
                    "api_key": api_key,
                    "base_url": base_url,
                    "timeout_seconds": timeout_seconds,
                    "input_rate": self.input_rate,
                    "output_rate": self.output_rate,
                }
            )

        async def chat_completions(
            self,
            messages: list[dict],
            model: str,
            max_tokens: int = 100,
            temperature: float = 0.7,
            **kwargs: Any,
        ) -> ChatCompletionResult:
            completion_calls.append(
                {
                    "messages": messages,
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
            return ChatCompletionResult(
                id="chatcmpl_configured_route",
                model=model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=Message(role="assistant", content="Routed response"),
                        finish_reason="stop",
                    )
                ],
                usage=ChatCompletionUsage(
                    prompt_tokens=200_000,
                    completion_tokens=50_000,
                    total_tokens=250_000,
                ),
            )

        def calculate_cost(
            self, input_tokens: int, output_tokens: int, model: str
        ) -> float:
            cost_calls.append(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "model": model,
                }
            )
            return float(
                (
                    Decimal(input_tokens) * self.input_rate
                    + Decimal(output_tokens) * self.output_rate
                )
                / Decimal(1_000_000)
            )

    monkeypatch.setattr("app.services.OpenAIProvider", FakeOpenAIProvider)
    before_ids = _usage_ids(uow_factory)
    payload = {
        "model": _PUBLIC_MODEL,
        "messages": [{"role": "user", "content": "Use the configured route."}],
        "max_tokens": 64,
        "temperature": 0.25,
    }

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json=payload,
    )

    assert response.status_code == 200, response.text
    assert response.json()["model"] == _PROVIDER_MODEL
    assert constructor_calls == [
        {
            "api_key": _PROVIDER_SECRET,
            "base_url": settings.openai_base_url,
            "timeout_seconds": settings.provider_timeout_seconds,
            "input_rate": Decimal("2.50000000"),
            "output_rate": Decimal("10.00000000"),
        }
    ]
    assert completion_calls == [
        {
            "messages": payload["messages"],
            "model": _PROVIDER_MODEL,
            "max_tokens": 64,
            "temperature": 0.25,
        }
    ]
    assert cost_calls == [
        {
            "input_tokens": 200_000,
            "output_tokens": 50_000,
            "model": _PROVIDER_MODEL,
        }
    ]

    new_ids = _usage_ids(uow_factory) - before_ids
    assert len(new_ids) == 1
    with uow_factory() as uow:
        event = uow.usage.get_by_id(new_ids.pop())
    assert event is not None
    assert event.provider == "openai"
    assert event.model == _PUBLIC_MODEL
    assert event.provider_model == _PROVIDER_MODEL
    assert event.estimated_cost_eur == Decimal("1")
    assert event.status == "success"
    assert event.error_code is None
    assert _PROVIDER_SECRET not in response.text
    assert stored_credential.ciphertext not in response.text
    assert _PROVIDER_SECRET not in caplog.text
    assert stored_credential.ciphertext not in caplog.text


def test_gemini_alias_uses_encrypted_credential_and_durable_usage(
    client: TestClient,
    admin_headers: dict[str, str],
    active_key,
    mutate_key,
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _configure_encryption(monkeypatch)
    _allow_public_model(mutate_key, active_key, _GEMINI_PUBLIC_MODEL)
    credential = _create_credential(
        client,
        admin_headers,
        name="Integration Gemini",
        secret=_GEMINI_PROVIDER_SECRET,
        provider="gemini",
    )
    _create_model_config(
        client,
        admin_headers,
        credential["id"],
        public_model=_GEMINI_PUBLIC_MODEL,
        provider_model=_GEMINI_PROVIDER_MODEL,
    )
    with uow_factory() as uow:
        stored_credential = uow.provider_credentials.get_by_id(credential["id"])
    assert stored_credential is not None

    constructor_calls: list[dict[str, Any]] = []

    class FakeGeminiProvider:
        name = "gemini"

        def __init__(
            self,
            api_key: str,
            *,
            base_url: str,
            timeout_seconds: float,
            input_cost_per_million_eur: Decimal,
            output_cost_per_million_eur: Decimal,
        ) -> None:
            constructor_calls.append(
                {
                    "api_key": api_key,
                    "base_url": base_url,
                    "timeout_seconds": timeout_seconds,
                    "input_rate": Decimal(input_cost_per_million_eur),
                    "output_rate": Decimal(output_cost_per_million_eur),
                }
            )
            self.input_rate = Decimal(input_cost_per_million_eur)
            self.output_rate = Decimal(output_cost_per_million_eur)

        async def chat_completions(self, **kwargs: Any) -> ChatCompletionResult:
            return ChatCompletionResult(
                id="gemini_configured_route",
                model=kwargs["model"],
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=Message(
                            role="assistant", content="Routed Gemini response"
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=ChatCompletionUsage(
                    prompt_tokens=200_000,
                    completion_tokens=50_000,
                    total_tokens=250_000,
                ),
            )

        def calculate_cost(
            self, input_tokens: int, output_tokens: int, model: str
        ) -> float:
            return float(
                (
                    Decimal(input_tokens) * self.input_rate
                    + Decimal(output_tokens) * self.output_rate
                )
                / Decimal(1_000_000)
            )

    monkeypatch.setattr("app.services.GeminiProvider", FakeGeminiProvider)
    before_ids = _usage_ids(uow_factory)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json={
            "model": _GEMINI_PUBLIC_MODEL,
            "messages": [{"role": "user", "content": "Use Gemini."}],
            "max_tokens": 64,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["model"] == _GEMINI_PROVIDER_MODEL
    assert constructor_calls == [
        {
            "api_key": _GEMINI_PROVIDER_SECRET,
            "base_url": settings.gemini_base_url,
            "timeout_seconds": settings.provider_timeout_seconds,
            "input_rate": Decimal("2.50000000"),
            "output_rate": Decimal("10.00000000"),
        }
    ]

    new_ids = _usage_ids(uow_factory) - before_ids
    assert len(new_ids) == 1
    with uow_factory() as uow:
        event = uow.usage.get_by_id(new_ids.pop())
    assert event is not None
    assert event.provider == "gemini"
    assert event.model == _GEMINI_PUBLIC_MODEL
    assert event.provider_model == _GEMINI_PROVIDER_MODEL
    assert event.estimated_cost_eur == Decimal("1")
    assert event.status == "success"
    assert _GEMINI_PROVIDER_SECRET not in response.text
    assert stored_credential.ciphertext not in response.text
    assert _GEMINI_PROVIDER_SECRET not in caplog.text
    assert stored_credential.ciphertext not in caplog.text


@pytest.mark.parametrize(
    ("error", "expected_status", "usage_status"),
    [
        (
            ProviderError(
                code="provider_timeout",
                public_message="Provider request timed out",
                status_code=504,
                retryable=True,
            ),
            504,
            "failed",
        ),
        (
            ProviderError(
                code="provider_rate_limited",
                public_message="Provider rate limit exceeded",
                status_code=429,
                retryable=True,
            ),
            429,
            "rate_limited",
        ),
    ],
    ids=["timeout", "rate-limited"],
)
def test_provider_failures_are_sanitized_and_durably_metered(
    client: TestClient,
    admin_headers: dict[str, str],
    active_key,
    mutate_key,
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
    caplog: pytest.LogCaptureFixture,
    error: ProviderError,
    expected_status: int,
    usage_status: str,
) -> None:
    _configure_encryption(monkeypatch)
    _allow_public_model(mutate_key, active_key)
    credential = _create_credential(client, admin_headers)
    _create_model_config(client, admin_headers, credential["id"])
    with uow_factory() as uow:
        stored_credential = uow.provider_credentials.get_by_id(credential["id"])
    assert stored_credential is not None

    class FailingOpenAIProvider:
        name = "openai"

        def __init__(self, api_key: str, **kwargs: Any) -> None:
            assert api_key == _PROVIDER_SECRET

        async def chat_completions(self, **kwargs: Any) -> ChatCompletionResult:
            _ = _UPSTREAM_ERROR_SECRET
            raise error

        def calculate_cost(
            self, input_tokens: int, output_tokens: int, model: str
        ) -> float:
            raise AssertionError("Failed provider calls must not calculate cost")

    monkeypatch.setattr("app.services.OpenAIProvider", FailingOpenAIProvider)
    before_ids = _usage_ids(uow_factory)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json={
            "model": _PUBLIC_MODEL,
            "messages": [{"role": "user", "content": "Trigger a safe failure."}],
        },
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "detail": {
            "code": error.code,
            "message": error.public_message,
            "retryable": error.retryable,
        }
    }
    assert _PROVIDER_SECRET not in response.text
    assert stored_credential.ciphertext not in response.text
    assert _UPSTREAM_ERROR_SECRET not in response.text

    new_ids = _usage_ids(uow_factory) - before_ids
    assert len(new_ids) == 1
    with uow_factory() as uow:
        event = uow.usage.get_by_id(new_ids.pop())
    assert event is not None
    assert event.provider == "openai"
    assert event.model == _PUBLIC_MODEL
    assert event.provider_model == _PROVIDER_MODEL
    assert event.input_tokens == 0
    assert event.output_tokens == 0
    assert event.total_tokens == 0
    assert event.estimated_cost_eur == Decimal("0")
    assert event.status == usage_status
    assert event.error_code == error.code
    assert _PROVIDER_SECRET not in caplog.text
    assert stored_credential.ciphertext not in caplog.text
    assert _UPSTREAM_ERROR_SECRET not in caplog.text


def test_revoking_credential_disables_its_model_route(
    client: TestClient,
    admin_headers: dict[str, str],
    active_key,
    mutate_key,
    monkeypatch: pytest.MonkeyPatch,
    uow_factory: UnitOfWorkFactory,
) -> None:
    _configure_encryption(monkeypatch)
    _allow_public_model(mutate_key, active_key)
    credential = _create_credential(client, admin_headers)
    config = _create_model_config(client, admin_headers, credential["id"])

    revoked = client.delete(
        f"/admin/provider-credentials/{credential['id']}",
        headers=admin_headers,
    )

    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    with uow_factory() as uow:
        stored_credential = uow.provider_credentials.get_by_id(credential["id"])
        stored_config = uow.model_configs.get_by_id(config["id"])
    assert stored_credential is not None
    assert stored_credential.status == "revoked"
    assert stored_config is not None
    assert stored_config.enabled is False

    class UnexpectedProvider:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("A revoked credential route must not be instantiated")

    monkeypatch.setattr("app.services.OpenAIProvider", UnexpectedProvider)
    before_ids = _usage_ids(uow_factory)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {active_key.raw_key}"},
        json={
            "model": _PUBLIC_MODEL,
            "messages": [{"role": "user", "content": "Do not route this."}],
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Model route is unavailable"}
    assert _usage_ids(uow_factory) == before_ids
