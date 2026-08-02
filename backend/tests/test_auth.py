from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.config import settings
from app.repositories.base import UnitOfWorkFactory


def test_liveness_and_repository_readiness(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "healthy"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_valid_login_normalizes_credentials_and_returns_identity(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "email": "  TEAM_ALPHA@HACKATHON.DEV  ",
            "password": "  Team Alpha  ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user_id"] == "user_1"
    assert body["email"] == "team_alpha@hackathon.dev"
    assert body["name"] == "Team Alpha"
    assert body["role"] == "user"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("missing@hackathon.dev", "Team Alpha"),
        ("team_alpha@hackathon.dev", "wrong password"),
    ],
)
def test_invalid_login_is_rejected(
    client: TestClient, email: str, password: str
) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_token_uses_declared_jwt_settings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "jwt_secret_key", "iteration-test-jwt-secret")
    monkeypatch.setattr(settings, "jwt_algorithm", "HS512")
    monkeypatch.setattr(settings, "jwt_expiration_minutes", 7)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "team_alpha@hackathon.dev",
            "password": "Team Alpha",
        },
    )
    token = response.json()["access_token"]

    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["sub"] == "user_1"
    assert "iat" in payload
    assert "exp" in payload
    assert payload["exp"] - payload["iat"] == 7 * 60
    assert payload["exp"] > datetime.now(timezone.utc).timestamp()


def test_authenticated_user_identity(client: TestClient, user_headers: dict[str, str]) -> None:
    response = client.get("/user/me", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {
        "id": "user_1",
        "email": "team_alpha@hackathon.dev",
        "name": "Team Alpha",
        "role": "user",
        "created_at": "2026-07-01T10:00:00Z",
    }


def test_user_key_and_usage_lists_are_owner_scoped(
    client: TestClient,
    user_headers: dict[str, str],
    uow_factory: UnitOfWorkFactory,
) -> None:
    keys_response = client.get("/user/keys", headers=user_headers)
    usage_response = client.get("/user/usage", headers=user_headers)

    assert keys_response.status_code == 200
    assert usage_response.status_code == 200
    assert keys_response.json()
    assert usage_response.json()
    assert {key["owner_id"] for key in keys_response.json()} == {"user_1"}
    assert {event["user_id"] for event in usage_response.json()} == {"user_1"}
    assert all("key" not in key and key["key_prefix"] for key in keys_response.json())

    with uow_factory() as uow:
        expected_keys = uow.keys.list(owner_id="user_1")
        expected_usage = uow.usage.list(user_id="user_1")
    assert len(keys_response.json()) == len(expected_keys)
    assert len(usage_response.json()) == len(expected_usage)


def test_user_cannot_read_another_users_key(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    response = client.get("/user/keys/subkey_2", headers=user_headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized to access this key"}


@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "offset=-1"])
def test_user_usage_rejects_invalid_pagination(
    client: TestClient,
    user_headers: dict[str, str],
    query: str,
) -> None:
    response = client.get(f"/user/usage?{query}", headers=user_headers)

    assert response.status_code == 422


def test_user_endpoint_rejects_invalid_bearer_token(client: TestClient) -> None:
    response = client.get(
        "/user/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}
