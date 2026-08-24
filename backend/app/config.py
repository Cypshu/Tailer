from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_prefix="TAILER_",
        extra="ignore",
    )

    # Core application settings
    app_name: str = "TAILER"
    debug: bool = False
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    # Database configuration
    database_url: str = "postgresql://tailer_user:tailer_password@localhost:5432/tailer"
    repository_backend: Literal["memory", "sqlalchemy"] = "sqlalchemy"
    default_project_id: str = "proj_hackathon_2026"
    default_provider: str = "mock"

    # Provider routing
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1"
    provider_timeout_seconds: float = Field(default=30.0, gt=0)

    # Redis configuration
    redis_url: str = "redis://localhost:6379"

    # Security configuration
    secret_key: str = "your-secret-key-change-in-production"
    jwt_secret_key: str = "your-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30
    sub_api_key_pepper: str = "development-sub-api-key-pepper-change-in-production"
    idempotency_key_pepper: SecretStr = SecretStr(
        "development-idempotency-key-pepper-change-in-production"
    )
    idempotency_retention_days: int = Field(default=30, gt=0)
    credential_encryption_keys: dict[str, SecretStr] = Field(default_factory=dict)
    credential_active_key_version: str = "v1"

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> Any:
        """Handle common host env values without breaking startup."""
        if isinstance(value, bool) or value is None:
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False

        return value

    @field_validator("idempotency_key_pepper")
    @classmethod
    def require_idempotency_pepper(cls, value: SecretStr) -> SecretStr:
        normalized = value.get_secret_value().strip()
        if not normalized:
            raise ValueError("idempotency key pepper must not be blank")
        return SecretStr(normalized)


settings = Settings()
