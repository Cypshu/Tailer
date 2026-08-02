"""Add encrypted provider credentials and model routing configuration.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-02 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(), nullable=False),
        sa.Column("secret_hint", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            server_default=sa.text("'active'"),
            nullable=False,
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
            "provider = lower(trim(provider)) AND length(provider) > 0",
            name=op.f("ck_provider_credentials_provider_normalized"),
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name=op.f("ck_provider_credentials_name_nonempty"),
        ),
        sa.CheckConstraint(
            "length(ciphertext) > 0",
            name=op.f("ck_provider_credentials_ciphertext_nonempty"),
        ),
        sa.CheckConstraint(
            "length(trim(key_version)) > 0",
            name=op.f("ck_provider_credentials_key_version_nonempty"),
        ),
        sa.CheckConstraint(
            "length(secret_hint) > 0",
            name=op.f("ck_provider_credentials_secret_hint_nonempty"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name=op.f("ck_provider_credentials_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_provider_credentials_project_id_projects"),
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_provider_credentials")
        ),
        sa.UniqueConstraint(
            "project_id",
            "provider",
            "name",
            name="uq_provider_credentials_project_provider_name",
        ),
        sa.UniqueConstraint(
            "id",
            "project_id",
            "provider",
            name="uq_provider_credentials_identity_scope",
        ),
    )
    op.create_index(
        "ix_provider_credentials_project_provider_status",
        "provider_credentials",
        ["project_id", "provider", "status"],
        unique=False,
    )

    op.create_table(
        "model_configs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("public_model", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_model", sa.String(), nullable=False),
        sa.Column("credential_id", sa.String(), nullable=True),
        sa.Column(
            "input_cost_per_million_eur", sa.Numeric(18, 8), nullable=False
        ),
        sa.Column(
            "output_cost_per_million_eur", sa.Numeric(18, 8), nullable=False
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.true(), nullable=False
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
            "provider = lower(trim(provider)) AND length(provider) > 0",
            name=op.f("ck_model_configs_provider_normalized"),
        ),
        sa.CheckConstraint(
            "length(trim(public_model)) > 0",
            name=op.f("ck_model_configs_public_model_nonempty"),
        ),
        sa.CheckConstraint(
            "length(trim(provider_model)) > 0",
            name=op.f("ck_model_configs_provider_model_nonempty"),
        ),
        sa.CheckConstraint(
            "(provider = 'mock' AND credential_id IS NULL) OR "
            "(provider <> 'mock' AND credential_id IS NOT NULL)",
            name=op.f("ck_model_configs_credential_provider"),
        ),
        sa.CheckConstraint(
            "input_cost_per_million_eur >= 0",
            name=op.f("ck_model_configs_input_price_nonnegative"),
        ),
        sa.CheckConstraint(
            "output_cost_per_million_eur >= 0",
            name=op.f("ck_model_configs_output_price_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["credential_id", "project_id", "provider"],
            [
                "provider_credentials.id",
                "provider_credentials.project_id",
                "provider_credentials.provider",
            ],
            name="fk_model_configs_credential_scope_provider_credentials",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_model_configs_project_id_projects"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_configs")),
        sa.UniqueConstraint(
            "project_id",
            "public_model",
            name="uq_model_configs_project_public_model",
        ),
    )
    op.create_index(
        "ix_model_configs_project_enabled",
        "model_configs",
        ["project_id", "enabled"],
        unique=False,
    )
    op.create_index(
        "ix_model_configs_credential_id",
        "model_configs",
        ["credential_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_model_configs_credential_id", table_name="model_configs")
    op.drop_index("ix_model_configs_project_enabled", table_name="model_configs")
    op.drop_table("model_configs")
    op.drop_index(
        "ix_provider_credentials_project_provider_status",
        table_name="provider_credentials",
    )
    op.drop_table("provider_credentials")
