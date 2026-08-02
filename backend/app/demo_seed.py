from datetime import datetime, timezone
from decimal import Decimal

from app.auth import get_password_hash
from app.domain import KeyRecord, ProjectRecord, UsageRecord, UserRecord
from app.key_security import hash_sub_api_key, sub_api_key_prefix
from app.repositories.base import PersistenceConflictError, UnitOfWorkFactory


DEMO_PROJECT_ID = "proj_hackathon_2026"
DEMO_RAW_KEYS = {
    "subkey_1": "tailer_sub_xxxxxxxxxxxxx1",
    "subkey_2": "tailer_sub_xxxxxxxxxxxxx2",
    "subkey_3": "tailer_sub_xxxxxxxxxxxxx3",
}


class SeedCollisionError(RuntimeError):
    pass


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def build_demo_records(
    pepper: str,
) -> tuple[list[UserRecord], list[ProjectRecord], list[KeyRecord], list[UsageRecord]]:
    users = [
        UserRecord(
            id="user_1",
            email="team_alpha@hackathon.dev",
            name="Team Alpha",
            password_hash=get_password_hash("Team Alpha"),
            role="user",
            created_at=_utc("2026-07-01T10:00:00Z"),
        ),
        UserRecord(
            id="user_2",
            email="team_beta@hackathon.dev",
            name="Team Beta",
            password_hash=get_password_hash("Team Beta"),
            role="user",
            created_at=_utc("2026-07-01T11:00:00Z"),
        ),
        UserRecord(
            id="user_3",
            email="organizer@hackathon.dev",
            name="Hackathon Organizer",
            password_hash=get_password_hash("Hackathon Organizer"),
            role="admin",
            created_at=_utc("2026-06-30T09:00:00Z"),
        ),
    ]
    projects = [
        ProjectRecord(
            id=DEMO_PROJECT_ID,
            name="Hackathon 2026",
            description="Main hackathon event with managed LLM access",
            created_at=_utc("2026-06-30T09:00:00Z"),
            status="active",
        )
    ]
    key_specs = [
        ("subkey_1", "Team Alpha Hackathon Key", "user_1", ["gpt-4o-mini", "gpt-4-turbo"], 500, 1000000, "50.0", "2026-07-01T10:30:00Z"),
        ("subkey_2", "Team Beta Hackathon Key", "user_2", ["gpt-4o-mini"], 300, 500000, "25.0", "2026-07-01T11:15:00Z"),
        ("subkey_3", "Organizer Full Access", "user_3", ["gpt-4o-mini", "gpt-4-turbo", "gpt-4-preview"], 10000, 10000000, "500.0", "2026-06-30T09:30:00Z"),
    ]
    keys = []
    for key_id, name, owner_id, models, daily, monthly, budget, created_at in key_specs:
        raw_key = DEMO_RAW_KEYS[key_id]
        keys.append(
            KeyRecord(
                id=key_id,
                project_id=DEMO_PROJECT_ID,
                owner_id=owner_id,
                name=name,
                key_hash=hash_sub_api_key(raw_key, pepper),
                key_prefix=sub_api_key_prefix(raw_key),
                allowed_models=models,
                status="active",
                daily_request_limit=daily,
                monthly_token_limit=monthly,
                monthly_budget_eur=Decimal(budget),
                created_at=_utc(created_at),
                expires_at=_utc("2099-12-31T23:59:59Z"),
            )
        )

    usage_specs = [
        ("usage_1", "2026-07-04T10:15:00Z", "subkey_1", "user_1", "gpt-4o-mini", 120, 85, 205, "0.0012", 750),
        ("usage_2", "2026-07-04T09:45:00Z", "subkey_1", "user_1", "gpt-4o-mini", 250, 180, 430, "0.0026", 920),
        ("usage_3", "2026-07-04T08:30:00Z", "subkey_2", "user_2", "gpt-4o-mini", 180, 95, 275, "0.0017", 650),
        ("usage_4", "2026-07-04T07:20:00Z", "subkey_1", "user_1", "gpt-4-turbo", 1500, 500, 2000, "0.045", 1200),
    ]
    usage = [
        UsageRecord(
            id=usage_id,
            project_id=DEMO_PROJECT_ID,
            sub_api_key_id=key_id,
            user_id=user_id,
            provider="mock",
            model=model,
            provider_model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_eur=Decimal(cost),
            currency="EUR",
            latency_ms=latency_ms,
            status="success",
            created_at=_utc(timestamp),
        )
        for usage_id, timestamp, key_id, user_id, model, input_tokens, output_tokens, total_tokens, cost, latency_ms in usage_specs
    ]
    return users, projects, keys, usage


def _seed_demo_data_once(factory: UnitOfWorkFactory, pepper: str) -> None:
    users, projects, keys, usage = build_demo_records(pepper)
    with factory() as uow:
        for project in projects:
            existing = uow.projects.get_by_id(project.id)
            if existing is None:
                uow.projects.add(project)
            elif (existing.name, existing.status) != (project.name, project.status):
                raise SeedCollisionError(f"Project seed collision for {project.id}")

        for user in users:
            existing = uow.users.get_by_id(user.id)
            email_owner = uow.users.get_by_email(user.email)
            if existing is None and email_owner is None:
                uow.users.add(user)
            elif existing is None or email_owner is None or existing.id != email_owner.id:
                raise SeedCollisionError(f"User seed collision for {user.id}/{user.email}")
            elif (existing.email, existing.name, existing.role) != (
                user.email,
                user.name,
                user.role,
            ):
                raise SeedCollisionError(f"User seed collision for {user.id}")
            elif existing.password_hash is None and user.password_hash is not None:
                uow.users.set_password_hash(user.id, user.password_hash)

        for key in keys:
            existing = uow.keys.get_by_id(key.id)
            digest_owner = uow.keys.get_by_hash(key.key_hash)
            if existing is None and digest_owner is None:
                uow.keys.add(key)
            elif existing is None:
                raise SeedCollisionError(f"Key seed collision for {key.id}")
            elif digest_owner is not None and digest_owner.id != existing.id:
                raise SeedCollisionError(f"Key seed digest collision for {key.id}")
            elif (existing.owner_id, existing.project_id) != (
                key.owner_id,
                key.project_id,
            ):
                raise SeedCollisionError(f"Key seed collision for {key.id}")

        for event in usage:
            existing = uow.usage.get_by_id(event.id)
            if existing is None:
                uow.usage.add(event)
            elif (
                existing.project_id,
                existing.sub_api_key_id,
                existing.user_id,
            ) != (event.project_id, event.sub_api_key_id, event.user_id):
                raise SeedCollisionError(f"Usage seed collision for {event.id}")

        uow.commit()


def seed_demo_data(
    factory: UnitOfWorkFactory,
    pepper: str,
    *,
    conflict_retries: int = 3,
) -> None:
    """Insert demo rows idempotently and tolerate concurrent bootstrap races."""
    if conflict_retries < 1:
        raise ValueError("conflict_retries must be positive")

    for attempt in range(conflict_retries):
        try:
            _seed_demo_data_once(factory, pepper)
            return
        except PersistenceConflictError as exc:
            if attempt + 1 == conflict_retries:
                raise SeedCollisionError(
                    "Demo seed could not converge after concurrent writes"
                ) from exc
