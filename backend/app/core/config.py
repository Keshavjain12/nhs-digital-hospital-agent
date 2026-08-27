"""Application configuration.

Every setting is read from the environment. There are no default secrets: `JWT_SECRET`
has no fallback value, so a misconfigured deployment fails at startup rather than running
with a predictable signing key.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- Application ---------------------------------------------------------
    environment: Environment = Environment.DEVELOPMENT
    app_name: str = "NHS Digital Hospital Agent API"
    api_v1_prefix: str = "/api/v1"
    version: str = "0.1.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Database ------------------------------------------------------------
    database_url: PostgresDsn
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_echo: bool = False

    # --- Authentication ------------------------------------------------------
    # No default. A missing JWT_SECRET must stop the process, not weaken it.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_access_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_days: int = 14
    password_reset_ttl_minutes: int = 30
    max_failed_logins: int = 5
    account_lockout_minutes: int = 15

    # --- CORS ----------------------------------------------------------------
    # NoDecode suppresses pydantic-settings' default JSON decoding for complex types, so
    # the validator below receives the raw comma-separated string that a .env file holds.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # --- Integrations (ports; see docs/architecture/02-system-architecture.md) --
    fhir_mode: Literal["local", "sandbox"] = "local"
    fhir_base_url: str | None = None
    triage_engine: Literal["rules", "ml"] = "rules"
    notification_sink: Literal["console", "smtp"] = "console"
    llm_api_key: str | None = None
    llm_model: str = "claude-sonnet-5"

    # --- Demo / seeding ------------------------------------------------------
    # Used only by scripts/seed_demo.py. Never a default: seeding must be explicit.
    demo_password: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept CORS_ORIGINS as a comma-separated string, which is what .env files hold."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def debug_errors(self) -> bool:
        """Whether internal error detail may be echoed to the client.

        False everywhere except local development. Brief §11: never expose stack traces.
        """
        return self.environment is Environment.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values are supplied by the environment, not the caller
