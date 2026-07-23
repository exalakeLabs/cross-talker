from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CROSS_TALKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    providers: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["openai", "anthropic"]
    )
    default_rounds: int = Field(default=1, ge=0)
    max_rounds: int = Field(default=5, ge=0)
    request_timeout_seconds: float = Field(default=60.0, gt=0)
    database_path: str = "data/cross_talker.db"

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", validation_alias="OPENAI_MODEL")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL"
    )

    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-sonnet-4-6", validation_alias="ANTHROPIC_MODEL"
    )
    anthropic_base_url: str = Field(
        default="https://api.anthropic.com/v1", validation_alias="ANTHROPIC_BASE_URL"
    )

    @field_validator("providers", mode="before")
    @classmethod
    def parse_providers(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
