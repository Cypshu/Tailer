from datetime import datetime, timezone
from decimal import Decimal
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    true,
)
from sqlalchemy.orm import declarative_base, relationship


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email = lower(trim(email))",
            name="email_normalized",
        ),
        CheckConstraint("role IN ('admin', 'user')", name="role_allowed"),
        Index("ix_users_role", "role"),
    )

    id = Column(String, primary_key=True, default=lambda: f"user_{uuid.uuid4().hex[:12]}")
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)  # nullable for future auth
    role = Column(String, default="user", server_default=text("'user'"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    sub_api_keys = relationship("SubApiKey", back_populates="owner")
    usage_events = relationship("UsageEvent", back_populates="user")


Index("uq_users_email_lower", func.lower(User.email), unique=True)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'archived')", name="status_allowed"
        ),
        Index("ix_projects_status", "status"),
    )

    id = Column(String, primary_key=True, default=lambda: f"proj_{uuid.uuid4().hex[:12]}")
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="active", server_default=text("'active'"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    sub_api_keys = relationship("SubApiKey", back_populates="project")
    usage_events = relationship("UsageEvent", back_populates="project")
    provider_credentials = relationship(
        "ProviderCredential", back_populates="project", viewonly=True
    )
    model_configs = relationship(
        "ModelConfig", back_populates="project", viewonly=True
    )


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        CheckConstraint(
            "provider = lower(trim(provider)) AND length(provider) > 0",
            name="provider_normalized",
        ),
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint("length(ciphertext) > 0", name="ciphertext_nonempty"),
        CheckConstraint("length(trim(key_version)) > 0", name="key_version_nonempty"),
        CheckConstraint("length(secret_hint) > 0", name="secret_hint_nonempty"),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="status_allowed",
        ),
        UniqueConstraint(
            "project_id",
            "provider",
            "name",
            name="uq_provider_credentials_project_provider_name",
        ),
        UniqueConstraint(
            "id",
            "project_id",
            "provider",
            name="uq_provider_credentials_identity_scope",
        ),
        Index(
            "ix_provider_credentials_project_provider_status",
            "project_id",
            "provider",
            "status",
        ),
    )

    id = Column(String, primary_key=True, default=lambda: f"cred_{uuid.uuid4().hex[:12]}")
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    provider = Column(String, nullable=False)
    name = Column(String, nullable=False)
    ciphertext = Column(Text, nullable=False)
    key_version = Column(String, nullable=False)
    secret_hint = Column(String, nullable=False)
    status = Column(String, default="active", server_default=text("'active'"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    project = relationship(
        "Project", back_populates="provider_credentials", viewonly=True
    )
    model_configs = relationship(
        "ModelConfig", back_populates="credential", viewonly=True
    )


class ModelConfig(Base):
    __tablename__ = "model_configs"
    __table_args__ = (
        CheckConstraint(
            "provider = lower(trim(provider)) AND length(provider) > 0",
            name="provider_normalized",
        ),
        CheckConstraint(
            "length(trim(public_model)) > 0", name="public_model_nonempty"
        ),
        CheckConstraint(
            "length(trim(provider_model)) > 0", name="provider_model_nonempty"
        ),
        CheckConstraint(
            "(provider = 'mock' AND credential_id IS NULL) OR "
            "(provider <> 'mock' AND credential_id IS NOT NULL)",
            name="credential_provider",
        ),
        CheckConstraint(
            "input_cost_per_million_eur >= 0", name="input_price_nonnegative"
        ),
        CheckConstraint(
            "output_cost_per_million_eur >= 0", name="output_price_nonnegative"
        ),
        ForeignKeyConstraint(
            ["credential_id", "project_id", "provider"],
            [
                "provider_credentials.id",
                "provider_credentials.project_id",
                "provider_credentials.provider",
            ],
            name="fk_model_configs_credential_scope_provider_credentials",
        ),
        UniqueConstraint(
            "project_id",
            "public_model",
            name="uq_model_configs_project_public_model",
        ),
        Index("ix_model_configs_project_enabled", "project_id", "enabled"),
        Index("ix_model_configs_credential_id", "credential_id"),
    )

    id = Column(
        String, primary_key=True, default=lambda: f"modelcfg_{uuid.uuid4().hex[:12]}"
    )
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    public_model = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    provider_model = Column(String, nullable=False)
    credential_id = Column(String, nullable=True)
    input_cost_per_million_eur = Column(Numeric(18, 8), nullable=False)
    output_cost_per_million_eur = Column(Numeric(18, 8), nullable=False)
    enabled = Column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    created_at = Column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    project = relationship(
        "Project", back_populates="model_configs", viewonly=True
    )
    credential = relationship(
        "ProviderCredential", back_populates="model_configs", viewonly=True
    )


class SubApiKey(Base):
    __tablename__ = "sub_api_keys"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'revoked', 'expired')",
            name="status_allowed",
        ),
        CheckConstraint("length(key_prefix) > 0", name="key_prefix_nonempty"),
        CheckConstraint(
            "rate_limit_per_minute IS NULL OR rate_limit_per_minute > 0",
            name="rate_limit_positive",
        ),
        CheckConstraint("daily_request_limit > 0", name="daily_limit_positive"),
        CheckConstraint("monthly_token_limit > 0", name="monthly_tokens_positive"),
        CheckConstraint("monthly_budget_eur > 0", name="monthly_budget_positive"),
        CheckConstraint(
            "max_tokens_per_request IS NULL OR max_tokens_per_request > 0",
            name="max_tokens_positive",
        ),
        Index("uq_sub_api_keys_key_hash", "key_hash", unique=True),
        Index("ix_sub_api_keys_owner_status", "owner_id", "status"),
        Index("ix_sub_api_keys_project_status", "project_id", "status"),
    )

    id = Column(String, primary_key=True, default=lambda: f"subkey_{uuid.uuid4().hex[:12]}")
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False)
    key_prefix = Column(String, nullable=False)  # safe display fragment; never the raw key
    allowed_models = Column(JSON, default=list, server_default=text("'[]'"), nullable=False)
    allowed_pipelines = Column(JSON, default=list, server_default=text("'[]'"), nullable=False)
    rate_limit_per_minute = Column(Integer, nullable=True)
    daily_request_limit = Column(Integer, nullable=False)
    monthly_token_limit = Column(Integer, nullable=False)
    monthly_budget_eur = Column(Numeric(18, 8), nullable=False)
    max_tokens_per_request = Column(Integer, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, default="active", server_default=text("'active'"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=_utc_now,
        onupdate=_utc_now,
        server_default=func.now(),
        nullable=False,
    )

    project = relationship("Project", back_populates="sub_api_keys")
    owner = relationship("User", back_populates="sub_api_keys")
    usage_events = relationship("UsageEvent", back_populates="sub_api_key")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_nonnegative"),
        CheckConstraint("total_tokens >= 0", name="total_tokens_nonnegative"),
        CheckConstraint("estimated_cost_eur >= 0", name="estimated_cost_nonnegative"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint(
            "status IN ('success', 'failed', 'blocked', 'rate_limited')",
            name="status_allowed",
        ),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="currency_iso_code",
        ),
        Index("ix_usage_events_created_at", "created_at"),
        Index("ix_usage_events_project_created_at", "project_id", "created_at"),
        Index("ix_usage_events_key_created_at", "sub_api_key_id", "created_at"),
        Index("ix_usage_events_user_created_at", "user_id", "created_at"),
        Index("ix_usage_events_status_created_at", "status", "created_at"),
    )

    id = Column(String, primary_key=True, default=lambda: f"usage_{uuid.uuid4().hex[:12]}")
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    sub_api_key_id = Column(String, ForeignKey("sub_api_keys.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)  # openai, anthropic, etc.
    model = Column(String, nullable=False)  # public model alias requested by the client
    provider_model = Column(String, nullable=False)  # concrete upstream model
    pipeline = Column(String, nullable=True)
    input_tokens = Column(Integer, default=0, server_default=text("0"), nullable=False)
    output_tokens = Column(Integer, default=0, server_default=text("0"), nullable=False)
    total_tokens = Column(Integer, default=0, server_default=text("0"), nullable=False)
    estimated_cost_eur = Column(
        Numeric(18, 8), default=Decimal("0"), server_default=text("0"), nullable=False
    )
    currency = Column(String(3), default="EUR", server_default=text("'EUR'"), nullable=False)
    latency_ms = Column(Integer, nullable=False)
    status = Column(String, default="success", server_default=text("'success'"), nullable=False)
    error_code = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=_utc_now, server_default=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="usage_events")
    sub_api_key = relationship("SubApiKey", back_populates="usage_events")
    user = relationship("User", back_populates="usage_events")
