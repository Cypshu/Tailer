from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: f"user_{uuid.uuid4().hex[:12]}")
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)  # nullable for future auth
    role = Column(String, default="user", nullable=False)  # admin or user
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    sub_api_keys = relationship("SubApiKey", back_populates="owner")
    usage_events = relationship("UsageEvent", back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: f"proj_{uuid.uuid4().hex[:12]}")
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="active", nullable=False)  # active, paused, archived
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    sub_api_keys = relationship("SubApiKey", back_populates="project")
    usage_events = relationship("UsageEvent", back_populates="project")


class SubApiKey(Base):
    __tablename__ = "sub_api_keys"

    id = Column(String, primary_key=True, default=lambda: f"subkey_{uuid.uuid4().hex[:12]}")
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    key_hash = Column(String, unique=True, nullable=False, index=True)
    key_prefix = Column(String, nullable=True)  # for display purposes
    allowed_models = Column(JSON, default=list, nullable=False)
    allowed_pipelines = Column(JSON, default=list, nullable=False)
    rate_limit_per_minute = Column(Integer, nullable=True)
    daily_request_limit = Column(Integer, nullable=True)
    monthly_token_limit = Column(Integer, nullable=True)
    monthly_budget_eur = Column(Float, nullable=True)
    max_tokens_per_request = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    status = Column(String, default="active", nullable=False)  # active, paused, revoked, expired
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    project = relationship("Project", back_populates="sub_api_keys")
    owner = relationship("User", back_populates="sub_api_keys")
    usage_events = relationship("UsageEvent", back_populates="sub_api_key")


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id = Column(String, primary_key=True, default=lambda: f"usage_{uuid.uuid4().hex[:12]}")
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    sub_api_key_id = Column(String, ForeignKey("sub_api_keys.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)  # openai, anthropic, etc.
    model = Column(String, nullable=False)
    pipeline = Column(String, nullable=True)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    estimated_cost_eur = Column(Float, default=0.0, nullable=False)
    latency_ms = Column(Integer, nullable=True)
    status = Column(String, default="success", nullable=False)  # success, failed, rate_limited, etc.
    error_code = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    project = relationship("Project", back_populates="usage_events")
    sub_api_key = relationship("SubApiKey", back_populates="usage_events")
    user = relationship("User", back_populates="usage_events")
