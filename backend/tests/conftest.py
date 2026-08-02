from collections.abc import Iterator
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import mock_data
from app.main import app
from app.providers import (
    ChatCompletionChoice,
    ChatCompletionResult,
    ChatCompletionUsage,
    Message,
    MockProvider,
    set_provider,
)


_INITIAL_USERS = deepcopy(mock_data.MOCK_USERS)
_INITIAL_PROJECTS = deepcopy(mock_data.MOCK_PROJECTS)
_INITIAL_KEYS = deepcopy(mock_data.MOCK_KEYS)
_INITIAL_USAGE_EVENTS = deepcopy(mock_data.MOCK_USAGE_EVENTS)


def _reset_mock_data() -> None:
    """Restore list identities as well as their original model values."""
    mock_data.MOCK_USERS[:] = deepcopy(_INITIAL_USERS)
    mock_data.MOCK_PROJECTS[:] = deepcopy(_INITIAL_PROJECTS)
    mock_data.MOCK_KEYS[:] = deepcopy(_INITIAL_KEYS)
    mock_data.MOCK_USAGE_EVENTS[:] = deepcopy(_INITIAL_USAGE_EVENTS)


@pytest.fixture(autouse=True)
def isolated_application_state() -> Iterator[None]:
    _reset_mock_data()
    app.dependency_overrides.clear()
    set_provider(MockProvider())
    yield
    _reset_mock_data()
    app.dependency_overrides.clear()
    set_provider(MockProvider())


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    return _login_headers(client, "organizer@hackathon.dev", "Hackathon Organizer")


@pytest.fixture
def user_headers(client: TestClient) -> dict[str, str]:
    return _login_headers(client, "team_alpha@hackathon.dev", "Team Alpha")


@pytest.fixture
def active_key():
    key = mock_data.MOCK_KEYS[0]
    key.status = "active"
    key.expires_at = (
        datetime.now(timezone.utc) + timedelta(days=30)
    ).isoformat().replace("+00:00", "Z")
    return key


class RecordingProvider:
    """Deterministic provider spy used to prove boundary and state behavior."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.cost_calls: list[dict[str, Any]] = []
        self.result = ChatCompletionResult(
            id="chatcmpl_test",
            model="gpt-4o-mini",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=Message(role="assistant", content="Test response"),
                    finish_reason="stop",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            ),
        )
        self.cost = 0.0123

    async def chat_completions(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 100,
        **kwargs: Any,
    ) -> ChatCompletionResult:
        self.calls.append(
            {
                "messages": deepcopy(messages),
                "model": model,
                "max_tokens": max_tokens,
                **kwargs,
            }
        )
        self.result.model = model
        return self.result

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        self.cost_calls.append(
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": model,
            }
        )
        return self.cost


@pytest.fixture
def recording_provider() -> RecordingProvider:
    provider = RecordingProvider()
    set_provider(provider)
    return provider
