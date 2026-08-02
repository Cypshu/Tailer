from typing import Any

from pydantic import field_validator
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
    debug: bool = True
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    # Database configuration
    database_url: str = "postgresql://tailer_user:tailer_password@localhost:5432/tailer"

    # Redis configuration
    redis_url: str = "redis://localhost:6379"

    # Security configuration
    secret_key: str = "your-secret-key-change-in-production"
    jwt_secret_key: str = "your-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30

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


settings = Settings()
