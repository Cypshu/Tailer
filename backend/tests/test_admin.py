from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.key_security import hash_sub_api_key
from app.repositories.base import UnitOfWorkFactory


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


@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "offset=-1"])
def test_admin_usage_rejects_invalid_pagination(
    client: TestClient,
    admin_headers: dict[str, str],
    query: str,
) -> None:
    response = client.get(f"/admin/usage?{query}", headers=admin_headers)

    assert response.status_code == 422


def test_admin_can_list_users(
    client: TestClient,
    admin_headers: dict[str, str],
    uow_factory: UnitOfWorkFactory,
) -> None:
    response = client.get("/admin/users", headers=admin_headers)

    assert response.status_code == 200
    with uow_factory() as uow:
        expected_ids = {user.id for user in uow.users.list()}
    assert {user["id"] for user in response.json()} == expected_ids


def test_create_user_normalizes_email(
    client: TestClient,
    admin_headers: dict[str, str],
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory() as uow:
        before_count = len(uow.users.list())

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
    with uow_factory() as uow:
        assert len(uow.users.list()) == before_count + 1
        assert uow.users.get_by_email("NEW.USER@EXAMPLE.COM") is not None


def test_create_user_rejects_case_insensitive_duplicate(
    client: TestClient,
    admin_headers: dict[str, str],
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory() as uow:
        before_count = len(uow.users.list())

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
    with uow_factory() as uow:
        assert len(uow.users.list()) == before_count


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
    client: TestClient,
    admin_headers: dict[str, str],
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory() as uow:
        before_count = len(uow.keys.list())
    payload = _valid_key_payload()

    response = client.post("/admin/keys", headers=admin_headers, json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["owner_id"] == payload["owner_user_id"]
    assert body["allowed_models"] == payload["allowed_models"]
    assert body["status"] == "active"
    assert body["key"].startswith("tailer_sub_")
    assert body["key_prefix"]
    assert body["key_prefix"] != body["key"]
    assert body["expires_at"].endswith("Z")
    key_id = body["id"]

    with uow_factory() as uow:
        stored = uow.keys.get_by_id(key_id)
        assert stored is not None
        assert len(uow.keys.list()) == before_count + 1
        assert stored.key_hash == hash_sub_api_key(body["key"])
        assert body["key"] not in stored.key_hash

    detail = client.get(f"/admin/keys/{key_id}", headers=admin_headers)
    listing = client.get("/admin/keys", headers=admin_headers)
    assert detail.status_code == 200
    assert "key" not in detail.json()
    assert detail.json()["key_prefix"] == body["key_prefix"]
    listed = next(key for key in listing.json() if key["id"] == key_id)
    assert "key" not in listed
    assert listed["key_prefix"] == body["key_prefix"]


def test_create_key_requires_existing_owner(
    client: TestClient,
    admin_headers: dict[str, str],
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory() as uow:
        before_count = len(uow.keys.list())
    payload = _valid_key_payload()
    payload["owner_user_id"] = "user_missing"

    response = client.post("/admin/keys", headers=admin_headers, json=payload)

    assert response.status_code == 404
    assert response.json() == {"detail": "Owner user not found"}
    with uow_factory() as uow:
        assert len(uow.keys.list()) == before_count


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
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory() as uow:
        before_count = len(uow.keys.list())
    payload = _valid_key_payload()
    payload[field] = value

    response = client.post("/admin/keys", headers=admin_headers, json=payload)

    assert response.status_code == 422
    with uow_factory() as uow:
        assert len(uow.keys.list()) == before_count
