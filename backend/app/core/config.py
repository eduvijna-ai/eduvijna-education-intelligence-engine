from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_API_SECRET = "local-development-only"
UNSAFE_API_SECRETS = frozenset(
    {
        LOCAL_API_SECRET,
        "change-me-for-non-local-use",
    }
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Process environment variables retain Pydantic's normal highest priority.
        # .env.development is the Founder-editable local file; .env remains a fallback.
        env_file=(".env", ".env.development"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "local"
    database_url: str = "sqlite:///./data/eduvijna.db"
    anythingllm_base_url: str | None = None
    anythingllm_api_key: str | None = None
    api_secret_key: str = Field(default=LOCAL_API_SECRET, min_length=8)
    mcp_api_key: str | None = None
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173"

    @model_validator(mode="after")
    def require_non_local_secret(self) -> Settings:
        environment = self.app_env.strip().lower()
        if environment != "local" and self.api_secret_key in UNSAFE_API_SECRETS:
            raise ValueError("API_SECRET_KEY must be explicitly configured outside local mode")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
