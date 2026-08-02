"""Align persistence metadata with the frozen API contract.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-02 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


# Revision 0001 created unnamed unique constraints on SQLite. Supplying a
# convention lets batch mode address those constraints while rebuilding the
# table. PostgreSQL assigned deterministic names that are handled separately.
LEGACY_NAMING_CONVENTION = {
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _batch_options() -> dict[str, object]:
    return {
        "recreate": "always" if _dialect_name() == "sqlite" else "auto",
        "naming_convention": LEGACY_NAMING_CONVENTION,
    }


def _legacy_unique_name(table_name: str, column_name: str) -> str:
    return f"uq_{table_name}_{column_name}"


def _drop_legacy_unique(
    batch_op: object, table_name: str, column_name: str
) -> None:
    if _dialect_name() == "postgresql":
        # Databases originally created without a metadata naming convention use
        # PostgreSQL's ``*_key`` name. Fresh installs use our ``uq_*`` name.
        op.execute(
            sa.text(
                f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS "
                f"{table_name}_{column_name}_key"
            )
        )
        op.execute(
            sa.text(
                f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS "
                f"uq_{table_name}_{column_name}"
            )
        )
        return

    batch_op.drop_constraint(
        _legacy_unique_name(table_name, column_name), type_="unique"
    )


def _upgrade_users() -> None:
    # Application input is normalized already. Normalize historical rows before
    # replacing the case-sensitive duplicate structures with one lower index.
    op.execute(sa.text("UPDATE users SET email = lower(trim(email))"))
    op.drop_index("ix_users_email", table_name="users")

    with op.batch_alter_table("users", **_batch_options()) as batch_op:
        _drop_legacy_unique(batch_op, "users", "email")
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
            postgresql_using="created_at AT TIME ZONE 'UTC'",
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
            postgresql_using="updated_at AT TIME ZONE 'UTC'",
        )
        batch_op.create_check_constraint(
            op.f("ck_users_email_normalized"), "email = lower(trim(email))"
        )
        batch_op.create_check_constraint(
            op.f("ck_users_role_allowed"), "role IN ('admin', 'user')"
        )

    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)


def _upgrade_projects() -> None:
    with op.batch_alter_table("projects", **_batch_options()) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
            postgresql_using="created_at AT TIME ZONE 'UTC'",
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
            postgresql_using="updated_at AT TIME ZONE 'UTC'",
        )
        batch_op.create_check_constraint(
            op.f("ck_projects_status_allowed"),
            "status IN ('active', 'paused', 'archived')",
        )

    op.create_index("ix_projects_status", "projects", ["status"], unique=False)


def _upgrade_sub_api_keys() -> None:
    # Prefixes are display-only. Hash-derived prefixes do not reveal a raw key.
    op.execute(
        sa.text(
            "UPDATE sub_api_keys "
            "SET key_prefix = substr(key_hash, 1, 12) "
            "WHERE key_prefix IS NULL OR trim(key_prefix) = ''"
        )
    )
    op.execute(
        sa.text(
            "UPDATE sub_api_keys SET daily_request_limit = 500 "
            "WHERE daily_request_limit IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE sub_api_keys SET monthly_token_limit = 1000000 "
            "WHERE monthly_token_limit IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE sub_api_keys SET monthly_budget_eur = 50 "
            "WHERE monthly_budget_eur IS NULL"
        )
    )
    # An absent expiry represented an unlimited legacy key. A far-future UTC
    # value preserves that behavior while making the new contract non-null.
    op.execute(
        sa.text(
            "UPDATE sub_api_keys SET expires_at = '9999-12-31 23:59:59' "
            "WHERE expires_at IS NULL"
        )
    )
    op.drop_index("ix_sub_api_keys_key_hash", table_name="sub_api_keys")

    with op.batch_alter_table("sub_api_keys", **_batch_options()) as batch_op:
        _drop_legacy_unique(batch_op, "sub_api_keys", "key_hash")
        batch_op.alter_column(
            "key_prefix", existing_type=sa.String(), existing_nullable=True, nullable=False
        )
        batch_op.alter_column(
            "daily_request_limit",
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "monthly_token_limit",
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "monthly_budget_eur",
            existing_type=sa.Float(),
            type_=sa.Numeric(18, 8),
            existing_nullable=True,
            nullable=False,
            postgresql_using="monthly_budget_eur::numeric(18, 8)",
        )
        batch_op.alter_column(
            "expires_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
            nullable=False,
            postgresql_using="expires_at AT TIME ZONE 'UTC'",
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
            postgresql_using="created_at AT TIME ZONE 'UTC'",
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
            postgresql_using="updated_at AT TIME ZONE 'UTC'",
        )
        batch_op.create_check_constraint(
            op.f("ck_sub_api_keys_status_allowed"),
            "status IN ('active', 'paused', 'revoked', 'expired')",
        )
        batch_op.create_check_constraint(
            op.f("ck_sub_api_keys_key_prefix_nonempty"), "length(key_prefix) > 0"
        )
        batch_op.create_check_constraint(
            op.f("ck_sub_api_keys_rate_limit_positive"),
            "rate_limit_per_minute IS NULL OR rate_limit_per_minute > 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_sub_api_keys_daily_limit_positive"),
            "daily_request_limit > 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_sub_api_keys_monthly_tokens_positive"),
            "monthly_token_limit > 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_sub_api_keys_monthly_budget_positive"),
            "monthly_budget_eur > 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_sub_api_keys_max_tokens_positive"),
            "max_tokens_per_request IS NULL OR max_tokens_per_request > 0",
        )

    op.create_index(
        "uq_sub_api_keys_key_hash",
        "sub_api_keys",
        ["key_hash"],
        unique=True,
    )
    op.create_index(
        "ix_sub_api_keys_owner_status",
        "sub_api_keys",
        ["owner_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_sub_api_keys_project_status",
        "sub_api_keys",
        ["project_id", "status"],
        unique=False,
    )


def _upgrade_usage_events() -> None:
    op.add_column(
        "usage_events", sa.Column("provider_model", sa.String(), nullable=True)
    )
    op.add_column(
        "usage_events",
        sa.Column("currency", sa.String(length=3), server_default="EUR", nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE usage_events SET provider_model = model "
            "WHERE provider_model IS NULL"
        )
    )
    op.execute(
        sa.text("UPDATE usage_events SET currency = 'EUR' WHERE currency IS NULL")
    )
    op.execute(
        sa.text("UPDATE usage_events SET latency_ms = 0 WHERE latency_ms IS NULL")
    )

    with op.batch_alter_table("usage_events", **_batch_options()) as batch_op:
        batch_op.alter_column(
            "provider_model",
            existing_type=sa.String(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "currency",
            existing_type=sa.String(length=3),
            existing_nullable=True,
            nullable=False,
            server_default="EUR",
        )
        batch_op.alter_column(
            "estimated_cost_eur",
            existing_type=sa.Float(),
            type_=sa.Numeric(18, 8),
            existing_nullable=False,
            existing_server_default=sa.text("0.0"),
            server_default=sa.text("0"),
            postgresql_using="estimated_cost_eur::numeric(18, 8)",
        )
        batch_op.alter_column(
            "latency_ms",
            existing_type=sa.Integer(),
            existing_nullable=True,
            nullable=False,
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            server_default=sa.func.now(),
            postgresql_using="created_at AT TIME ZONE 'UTC'",
        )
        batch_op.create_check_constraint(
            op.f("ck_usage_events_input_tokens_nonnegative"), "input_tokens >= 0"
        )
        batch_op.create_check_constraint(
            op.f("ck_usage_events_output_tokens_nonnegative"), "output_tokens >= 0"
        )
        batch_op.create_check_constraint(
            op.f("ck_usage_events_total_tokens_nonnegative"), "total_tokens >= 0"
        )
        batch_op.create_check_constraint(
            op.f("ck_usage_events_estimated_cost_nonnegative"),
            "estimated_cost_eur >= 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_usage_events_latency_nonnegative"),
            "latency_ms IS NULL OR latency_ms >= 0",
        )
        batch_op.create_check_constraint(
            op.f("ck_usage_events_status_allowed"),
            "status IN ('success', 'failed', 'blocked', 'rate_limited')",
        )
        batch_op.create_check_constraint(
            op.f("ck_usage_events_currency_iso_code"),
            "length(currency) = 3 AND currency = upper(currency)",
        )

    op.create_index(
        "ix_usage_events_project_created_at",
        "usage_events",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_events_key_created_at",
        "usage_events",
        ["sub_api_key_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_events_user_created_at",
        "usage_events",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_events_status_created_at",
        "usage_events",
        ["status", "created_at"],
        unique=False,
    )


def upgrade() -> None:
    _upgrade_users()
    _upgrade_projects()
    _upgrade_sub_api_keys()
    _upgrade_usage_events()


def _downgrade_usage_events() -> None:
    op.drop_index("ix_usage_events_status_created_at", table_name="usage_events")
    op.drop_index("ix_usage_events_user_created_at", table_name="usage_events")
    op.drop_index("ix_usage_events_key_created_at", table_name="usage_events")
    op.drop_index("ix_usage_events_project_created_at", table_name="usage_events")

    with op.batch_alter_table("usage_events", **_batch_options()) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_usage_events_currency_iso_code"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_usage_events_status_allowed"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_usage_events_latency_nonnegative"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_usage_events_estimated_cost_nonnegative"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_usage_events_total_tokens_nonnegative"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_usage_events_output_tokens_nonnegative"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_usage_events_input_tokens_nonnegative"), type_="check"
        )
        batch_op.alter_column(
            "estimated_cost_eur",
            existing_type=sa.Numeric(18, 8),
            type_=sa.Float(),
            existing_nullable=False,
            existing_server_default=sa.text("0"),
            server_default=sa.text("0.0"),
            postgresql_using="estimated_cost_eur::double precision",
        )
        batch_op.alter_column(
            "latency_ms",
            existing_type=sa.Integer(),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            server_default=None,
            postgresql_using="created_at AT TIME ZONE 'UTC'",
        )
        batch_op.drop_column("currency")
        batch_op.drop_column("provider_model")


def _downgrade_sub_api_keys() -> None:
    op.drop_index("ix_sub_api_keys_project_status", table_name="sub_api_keys")
    op.drop_index("ix_sub_api_keys_owner_status", table_name="sub_api_keys")
    op.drop_index("uq_sub_api_keys_key_hash", table_name="sub_api_keys")

    legacy_name = _legacy_unique_name("sub_api_keys", "key_hash")
    with op.batch_alter_table("sub_api_keys", **_batch_options()) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_sub_api_keys_max_tokens_positive"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_sub_api_keys_monthly_budget_positive"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_sub_api_keys_monthly_tokens_positive"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_sub_api_keys_daily_limit_positive"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_sub_api_keys_rate_limit_positive"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_sub_api_keys_key_prefix_nonempty"), type_="check"
        )
        batch_op.drop_constraint(
            op.f("ck_sub_api_keys_status_allowed"), type_="check"
        )
        batch_op.alter_column(
            "key_prefix", existing_type=sa.String(), existing_nullable=False, nullable=True
        )
        batch_op.alter_column(
            "daily_request_limit",
            existing_type=sa.Integer(),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            "monthly_token_limit",
            existing_type=sa.Integer(),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.alter_column(
            "monthly_budget_eur",
            existing_type=sa.Numeric(18, 8),
            type_=sa.Float(),
            existing_nullable=False,
            nullable=True,
            postgresql_using="monthly_budget_eur::double precision",
        )
        batch_op.alter_column(
            "expires_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            nullable=True,
            postgresql_using="expires_at AT TIME ZONE 'UTC'",
        )
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            server_default=None,
            postgresql_using="created_at AT TIME ZONE 'UTC'",
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            server_default=None,
            postgresql_using="updated_at AT TIME ZONE 'UTC'",
        )
        batch_op.create_unique_constraint(legacy_name, ["key_hash"])

    op.create_index(
        "ix_sub_api_keys_key_hash",
        "sub_api_keys",
        ["key_hash"],
        unique=True,
    )


def _downgrade_projects() -> None:
    op.drop_index("ix_projects_status", table_name="projects")
    with op.batch_alter_table("projects", **_batch_options()) as batch_op:
        batch_op.drop_constraint(op.f("ck_projects_status_allowed"), type_="check")
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            server_default=None,
            postgresql_using="created_at AT TIME ZONE 'UTC'",
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            server_default=None,
            postgresql_using="updated_at AT TIME ZONE 'UTC'",
        )


def _downgrade_users() -> None:
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("uq_users_email_lower", table_name="users")

    legacy_name = _legacy_unique_name("users", "email")
    with op.batch_alter_table("users", **_batch_options()) as batch_op:
        batch_op.drop_constraint(op.f("ck_users_role_allowed"), type_="check")
        batch_op.drop_constraint(op.f("ck_users_email_normalized"), type_="check")
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            server_default=None,
            postgresql_using="created_at AT TIME ZONE 'UTC'",
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            server_default=None,
            postgresql_using="updated_at AT TIME ZONE 'UTC'",
        )
        batch_op.create_unique_constraint(legacy_name, ["email"])

    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    _downgrade_usage_events()
    _downgrade_sub_api_keys()
    _downgrade_projects()
    _downgrade_users()
