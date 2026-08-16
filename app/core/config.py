"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnvironment = Literal["development", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Validated runtime settings for ECI Platform.

    Values are sourced from environment variables and an optional local ``.env``
    file. Secrets must never be hard-coded or logged.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Enterprise Communication Intelligence Platform"
    app_version: str = "0.1.0"
    app_env: AppEnvironment = "development"
    app_host: str = "0.0.0.0"
    app_port: int = Field(default=8000, ge=1, le=65535)
    log_level: LogLevel = "INFO"
    api_v1_prefix: str = "/api/v1"
    ai_provider: str = "mock"
    foundry_project_endpoint: str | None = None
    foundry_model_deployment: str | None = None
    bedrock_region: str | None = None
    bedrock_model_id: str | None = None

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value: object) -> object:
        """Normalize environment names to lowercase."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        """Normalize log levels to uppercase."""
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("ai_provider", mode="before")
    @classmethod
    def normalize_ai_provider(cls, value: object) -> object:
        """Normalize provider names to lowercase."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("foundry_project_endpoint", mode="before")
    @classmethod
    def normalize_foundry_project_endpoint(cls, value: object) -> object:
        """Treat blank Foundry endpoints as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("foundry_model_deployment", mode="before")
    @classmethod
    def normalize_foundry_model_deployment(cls, value: object) -> object:
        """Treat blank Foundry deployment names as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("foundry_project_endpoint")
    @classmethod
    def validate_foundry_project_endpoint(cls, value: str | None) -> str | None:
        """Require an https Foundry project endpoint when one is provided."""
        if value is not None and not value.startswith("https://"):
            raise ValueError("FOUNDRY_PROJECT_ENDPOINT must be an https URL.")
        return value

    @field_validator("bedrock_region", mode="before")
    @classmethod
    def normalize_bedrock_region(cls, value: object) -> object:
        """Treat blank Bedrock regions as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("bedrock_model_id", mode="before")
    @classmethod
    def normalize_bedrock_model_id(cls, value: object) -> object:
        """Treat blank Bedrock model IDs as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def validate_foundry_settings_when_selected(self) -> Self:
        """Require Foundry settings only when that provider is selected."""
        if self.ai_provider != "microsoft_foundry":
            return self

        missing: list[str] = []
        if not self.foundry_project_endpoint:
            missing.append("FOUNDRY_PROJECT_ENDPOINT")
        if not self.foundry_model_deployment:
            missing.append("FOUNDRY_MODEL_DEPLOYMENT")
        if missing:
            names = " and ".join(missing)
            raise ValueError(f"{names} must be set when AI_PROVIDER=microsoft_foundry.")
        return self

    @model_validator(mode="after")
    def validate_bedrock_settings_when_selected(self) -> Self:
        """Require Bedrock settings only when that provider is selected."""
        if self.ai_provider != "amazon_bedrock":
            return self

        missing: list[str] = []
        if not self.bedrock_region:
            missing.append("BEDROCK_REGION")
        if not self.bedrock_model_id:
            missing.append("BEDROCK_MODEL_ID")
        if missing:
            names = " and ".join(missing)
            raise ValueError(f"{names} must be set when AI_PROVIDER=amazon_bedrock.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
