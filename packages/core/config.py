"""Application configuration.

Settings load from environment variables (prefixed ``NAVIC_``) with sane
local defaults so the domain layer is usable in tests without infra.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NAVIC_", env_file=".env", extra="ignore")

    env: str = Field(default="local", description="local | staging | prod")
    debug: bool = Field(default=True)

    # Datastores (used once the serving/pipeline layers land; harmless defaults now).
    database_url: str = Field(
        default="postgresql+psycopg://navic:navic@localhost:5432/navic",
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    opensearch_url: str = Field(default="http://localhost:9200")

    # Object store (raw layer).
    s3_endpoint: str = Field(default="http://localhost:9000")
    s3_bucket: str = Field(default="navic-raw")
    s3_access_key: str = Field(default="minioadmin")
    s3_secret_key: str = Field(default="minioadmin")

    # Cost guardrails (spec 05/03).
    llm_daily_token_budget: int = Field(default=2_000_000)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
