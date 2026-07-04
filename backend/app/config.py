from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        env_prefix="",
    )

    app_name: str = "TAILER"
    debug: bool = True
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"

    # Database configuration
    database_url: str = "postgresql://tailer_user:tailer_password@localhost:5432/tailer"

    # Redis configuration
    redis_url: str = "redis://localhost:6379"


settings = Settings()
