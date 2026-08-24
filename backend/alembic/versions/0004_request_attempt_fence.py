"""Add durable request-attempt fences and usage attribution.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def _batch_options() -> dict[str, object]:
    return {"recreate": "always" if _dialect_name() == "sqlite" else "auto"}


def upgrade() -> None:
    op.create_table(
        "request_attempts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("sub_api_key_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("idempotency_key_digest", sa.String(length=64), nullable=True),
        sa.Column(
            "request_fingerprint_digest", sa.String(length=64), nullable=True
        ),
        sa.Column("dispatch_token_digest", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("public_model", sa.String(), nullable=False),
        sa.Column("provider_model", sa.String(), nullable=False),
        sa.Column("provider_result_id", sa.String(length=255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_eur", sa.Numeric(18, 8), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_http_status", sa.Integer(), nullable=True),
        sa.Column("error_public_message", sa.String(length=200), nullable=True),
        sa.Column("error_retryable", sa.Boolean(), nullable=True),
        sa.Column(
            "idempotency_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('dispatch_claimed', 'succeeded', 'provider_failed', "
            "'provider_outcome_uncertain', 'finalization_failed')",
            name=op.f("ck_request_attempts_state_allowed"),
        ),
        sa.CheckConstraint(
            "(idempotency_key_digest IS NULL AND "
            "request_fingerprint_digest IS NULL) OR "
            "(idempotency_key_digest IS NOT NULL AND "
            "request_fingerprint_digest IS NOT NULL)",
            name=op.f("ck_request_attempts_identity_digest_pair"),
        ),
        sa.CheckConstraint(
            "idempotency_key_digest IS NULL OR "
            "length(idempotency_key_digest) = 64",
            name=op.f("ck_request_attempts_idempotency_digest_length"),
        ),
        sa.CheckConstraint(
            "request_fingerprint_digest IS NULL OR "
            "length(request_fingerprint_digest) = 64",
            name=op.f("ck_request_attempts_fingerprint_digest_length"),
        ),
        sa.CheckConstraint(
            "length(dispatch_token_digest) = 64",
            name=op.f("ck_request_attempts_dispatch_digest_length"),
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name=op.f("ck_request_attempts_input_tokens_nonnegative"),
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name=op.f("ck_request_attempts_output_tokens_nonnegative"),
        ),
        sa.CheckConstraint(
            "total_tokens IS NULL OR total_tokens >= 0",
            name=op.f("ck_request_attempts_total_tokens_nonnegative"),
        ),
        sa.CheckConstraint(
            "estimated_cost_eur IS NULL OR estimated_cost_eur >= 0",
            name=op.f("ck_request_attempts_estimated_cost_nonnegative"),
        ),
        sa.CheckConstraint(
            "currency IS NULL OR "
            "(length(currency) = 3 AND currency = upper(currency))",
            name=op.f("ck_request_attempts_currency_iso_code"),
        ),
        sa.CheckConstraint(
            "(estimated_cost_eur IS NULL AND currency IS NULL) OR "
            "(estimated_cost_eur IS NOT NULL AND currency IS NOT NULL AND "
            "currency = 'EUR')",
            name=op.f("ck_request_attempts_cost_currency_pair"),
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name=op.f("ck_request_attempts_latency_nonnegative"),
        ),
        sa.CheckConstraint(
            "error_http_status IS NULL OR "
            "(error_http_status >= 400 AND error_http_status <= 599)",
            name=op.f("ck_request_attempts_error_http_status_range"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_request_attempts_project_id_projects"),
        ),
        sa.ForeignKeyConstraint(
            ["sub_api_key_id"],
            ["sub_api_keys.id"],
            name=op.f("fk_request_attempts_sub_api_key_id_sub_api_keys"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_request_attempts_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_attempts")),
        sa.UniqueConstraint(
            "sub_api_key_id",
            "operation",
            "idempotency_key_digest",
            name="uq_request_attempts_identity",
        ),
        sa.UniqueConstraint(
            "id",
            "project_id",
            "sub_api_key_id",
            "user_id",
            name="uq_request_attempts_attribution",
        ),
    )
    op.create_index(
        "ix_request_attempts_state_updated_at",
        "request_attempts",
        ["state", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_request_attempts_project_created_at",
        "request_attempts",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_request_attempts_key_created_at",
        "request_attempts",
        ["sub_api_key_id", "created_at"],
        unique=False,
    )

    with op.batch_alter_table("usage_events", **_batch_options()) as batch_op:
        batch_op.add_column(
            sa.Column("request_attempt_id", sa.String(), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_usage_events_request_attempt_id", ["request_attempt_id"]
        )
        batch_op.create_foreign_key(
            "fk_usage_events_request_attempt_attribution",
            "request_attempts",
            ["request_attempt_id", "project_id", "sub_api_key_id", "user_id"],
            ["id", "project_id", "sub_api_key_id", "user_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_events", **_batch_options()) as batch_op:
        batch_op.drop_constraint(
            "fk_usage_events_request_attempt_attribution", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "uq_usage_events_request_attempt_id", type_="unique"
        )
        batch_op.drop_column("request_attempt_id")

    op.drop_index(
        "ix_request_attempts_key_created_at", table_name="request_attempts"
    )
    op.drop_index(
        "ix_request_attempts_project_created_at", table_name="request_attempts"
    )
    op.drop_index(
        "ix_request_attempts_state_updated_at", table_name="request_attempts"
    )
    op.drop_table("request_attempts")
