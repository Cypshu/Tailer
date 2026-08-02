from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.mock_data import MOCK_KEYS, MOCK_USERS


def _future_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()


def _valid_key_payload() -> dict:
    return {
        "name": "Iteration test key",
        "owner_user_id": "user_1",
        "allowed_models": ["gpt-4o-mini"],
        "daily_request_limit": 25,
        "monthly_token_limit": 5000,
        "monthly_budget_eur": 10.5,
        "expires_at": _future_expiry(),
    }


def test_anonymous_admin_request_returns_401(client: TestClient) -> None:
    response = client.get("/admin/users")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_normal_user_admin_request_returns_403(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    response = client.get("/admin/users", headers=user_headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Admin access required"}


def test_admin_can_list_users(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    response = client.get("/admin/users", headers=admin_headers)

    assert response.status_code == 200
    assert {user["id"] for user in response.json()} == {user.id for user in MOCK_USERS}


def test_create_user_normalizes_email(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    before_count = len(MOCK_USERS)

    response = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "  NEW.USER@EXAMPLE.COM  ",
            "name": "New User",
            "role": "user",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "new.user@example.com"
    assert len(MOCK_USERS) == before_count + 1


def test_create_user_rejects_case_insensitive_duplicate(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    before_count = len(MOCK_USERS)

    response = client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "  TEAM_ALPHA@HACKATHON.DEV ",
            "name": "Duplicate",
            "role": "user",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "User with this email already exists"}
    assert len(MOCK_USERS) == before_count


@pytest.mark.parametrize(
    "email",
    ["missing-at.example.com", "missing-domain@", "two@@example.com"],
)
def test_create_user_rejects_invalid_email(
    client: TestClient, admin_headers: dict[str, str], email: str
) -> None:
    response = client.post(
        "/admin/users",
        headers=admin_headers,
        json={"email": email, "name": "Invalid", "role": "user"},
    )

    assert response.status_code == 422


def test_create_key_for_existing_owner(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    before_count = len(MOCK_KEYS)
    payload = _valid_key_payload()

    response = client.post("/admin/keys", headers=admin_headers, json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["owner_id"] == payload["owner_user_id"]
    assert body["allowed_models"] == payload["allowed_models"]
    assert body["status"] == "active"
    assert body["key"].startswith("tailer_sub_")
    assert body["expires_at"].endswith("Z")
    assert len(MOCK_KEYS) == before_count + 1


def test_create_key_requires_existing_owner(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    before_count = len(MOCK_KEYS)
    payload = _valid_key_payload()
    payload["owner_user_id"] = "user_missing"

    response = client.post("/admin/keys", headers=admin_headers, json=payload)

    assert response.status_code == 404
    assert response.json() == {"detail": "Owner user not found"}
    assert len(MOCK_KEYS) == before_count


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("allowed_models", []),
        ("allowed_models", ["   "]),
        ("daily_request_limit", 0),
        ("daily_request_limit", -1),
        ("monthly_token_limit", 0),
        ("monthly_token_limit", -1),
        ("monthly_budget_eur", 0),
        ("monthly_budget_eur", -0.01),
        ("expires_at", "2020-01-01T00:00:00Z"),
        ("expires_at", "not-a-date"),
    ],
)
def test_create_key_rejects_invalid_boundaries_without_mutation(
    client: TestClient,
    admin_headers: dict[str, str],
    field: str,
    value: object,
) -> None:
    before_count = len(MOCK_KEYS)
    payload = _valid_key_payload()
    payload[field] = value

    response = client.post("/admin/keys", headers=admin_headers, json=payload)

    assert response.status_code == 422
    assert len(MOCK_KEYS) == before_count
