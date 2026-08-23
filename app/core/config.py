"""Application configuration loaded from environment variables."""

import re
from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnvironment = Literal["development", "staging", "production"]
AuthMode = Literal["disabled", "oidc"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_PRODUCTION_DATABASE_SCHEME = "postgresql+psycopg"
_ALLOWED_DATABASE_SCHEMES = frozenset(
    {
        "postgresql+psycopg",
        "sqlite",
        "sqlite+pysqlite",
    }
)
_MICROSOFT_OAUTH_TENANT_ALIASES = frozenset({"common", "organizations", "consumers"})
_MICROSOFT_OAUTH_TENANT_GUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


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
        hide_input_in_errors=True,
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
    auth_mode: AuthMode = "disabled"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_required_permission: str = "communications:analyze"
    database_url: str | None = None
    oauth_authorization_session_ttl_seconds: int = Field(default=600, ge=60, le=1800)
    gmail_oauth_client_id: str | None = None
    gmail_oauth_client_secret: SecretStr | None = None
    gmail_oauth_redirect_uri: str | None = None
    microsoft_oauth_client_id: str | None = None
    microsoft_oauth_client_secret: SecretStr | None = None
    microsoft_oauth_redirect_uri: str | None = None
    microsoft_oauth_tenant: str | None = None

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

    @field_validator("auth_mode", mode="before")
    @classmethod
    def normalize_auth_mode(cls, value: object) -> object:
        """Normalize authentication mode names to lowercase."""
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("oidc_issuer", mode="before")
    @classmethod
    def normalize_oidc_issuer(cls, value: object) -> object:
        """Treat blank OIDC issuers as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("oidc_audience", mode="before")
    @classmethod
    def normalize_oidc_audience(cls, value: object) -> object:
        """Treat blank OIDC audiences as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("oidc_jwks_url", mode="before")
    @classmethod
    def normalize_oidc_jwks_url(cls, value: object) -> object:
        """Treat blank OIDC JWKS URLs as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("oidc_required_permission", mode="before")
    @classmethod
    def normalize_oidc_required_permission(cls, value: object) -> object:
        """Strip surrounding whitespace from the required permission."""
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("oidc_issuer")
    @classmethod
    def validate_oidc_issuer(cls, value: str | None) -> str | None:
        """Require an https OIDC issuer when one is provided."""
        if value is not None and not value.startswith("https://"):
            raise ValueError("OIDC_ISSUER must be an https URL.")
        return value

    @field_validator("oidc_jwks_url")
    @classmethod
    def validate_oidc_jwks_url(cls, value: str | None) -> str | None:
        """Require an https OIDC JWKS URL when one is provided."""
        if value is not None and not value.startswith("https://"):
            raise ValueError("OIDC_JWKS_URL must be an https URL.")
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        """Treat blank database URLs as unset. Never invent a local file path."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str | None) -> str | None:
        """Accept only supported database URL forms. Do not connect."""
        if value is None:
            return None
        parsed = urlparse(value)
        scheme = parsed.scheme.lower()
        if not scheme or scheme not in _ALLOWED_DATABASE_SCHEMES:
            raise ValueError("DATABASE_URL scheme is not supported.")
        if scheme == _PRODUCTION_DATABASE_SCHEME and not parsed.netloc:
            raise ValueError("DATABASE_URL is malformed.")
        if scheme.startswith("sqlite") and not parsed.path:
            raise ValueError("DATABASE_URL is malformed.")
        return value

    @field_validator("gmail_oauth_client_id", mode="before")
    @classmethod
    def normalize_gmail_oauth_client_id(cls, value: object) -> object:
        """Treat blank Gmail OAuth client IDs as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("gmail_oauth_client_secret", mode="before")
    @classmethod
    def normalize_gmail_oauth_client_secret(cls, value: object) -> object:
        """Treat blank Gmail OAuth client secrets as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("gmail_oauth_redirect_uri", mode="before")
    @classmethod
    def normalize_gmail_oauth_redirect_uri(cls, value: object) -> object:
        """Treat blank Gmail OAuth redirect URIs as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("gmail_oauth_redirect_uri")
    @classmethod
    def validate_gmail_oauth_redirect_uri(cls, value: str | None) -> str | None:
        """Require an absolute http(s) redirect URI with no fragment."""
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.fragment:
            raise ValueError("GMAIL_OAUTH_REDIRECT_URI must be an absolute http(s) URL.")
        return value

    @field_validator("microsoft_oauth_client_id", mode="before")
    @classmethod
    def normalize_microsoft_oauth_client_id(cls, value: object) -> object:
        """Treat blank Microsoft OAuth client IDs as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("microsoft_oauth_client_secret", mode="before")
    @classmethod
    def normalize_microsoft_oauth_client_secret(cls, value: object) -> object:
        """Treat blank Microsoft OAuth client secrets as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("microsoft_oauth_redirect_uri", mode="before")
    @classmethod
    def normalize_microsoft_oauth_redirect_uri(cls, value: object) -> object:
        """Treat blank Microsoft OAuth redirect URIs as unset."""
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("microsoft_oauth_tenant", mode="before")
    @classmethod
    def normalize_microsoft_oauth_tenant(cls, value: object) -> object:
        """Treat blank Microsoft OAuth tenants as unset and lowercase aliases."""
        if isinstance(value, str):
            stripped = value.strip().lower()
            return stripped or None
        return value

    @field_validator("microsoft_oauth_redirect_uri")
    @classmethod
    def validate_microsoft_oauth_redirect_uri(cls, value: str | None) -> str | None:
        """Require an absolute http(s) redirect URI with no fragment."""
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.fragment:
            raise ValueError("MICROSOFT_OAUTH_REDIRECT_URI must be an absolute http(s) URL.")
        return value

    @field_validator("microsoft_oauth_tenant")
    @classmethod
    def validate_microsoft_oauth_tenant(cls, value: str | None) -> str | None:
        """Accept v2 aliases or a directory GUID. Reject authority URLs."""
        if value is None:
            return None
        if value in _MICROSOFT_OAUTH_TENANT_ALIASES:
            return value
        if re.fullmatch(_MICROSOFT_OAUTH_TENANT_GUID, value) is None:
            raise ValueError(
                "MICROSOFT_OAUTH_TENANT must be common, organizations, consumers, "
                "or a directory GUID."
            )
        return value

    @model_validator(mode="after")
    def validate_gmail_oauth_settings_together(self) -> Self:
        """Require Gmail OAuth fields together when any one is provided.

        Ordinary mock/local startup does not set these variables. Partial
        configuration is rejected so a connect path is never half-enabled.
        """
        secret_value = None
        if self.gmail_oauth_client_secret is not None:
            secret_value = self.gmail_oauth_client_secret.get_secret_value()
        present = (
            self.gmail_oauth_client_id is not None,
            secret_value is not None,
            self.gmail_oauth_redirect_uri is not None,
        )
        if any(present) and not all(present):
            raise ValueError(
                "GMAIL_OAUTH_CLIENT_ID, GMAIL_OAUTH_CLIENT_SECRET, and "
                "GMAIL_OAUTH_REDIRECT_URI must be set together."
            )
        return self

    @property
    def gmail_oauth_is_configured(self) -> bool:
        """Return True when Gmail OAuth client settings are complete."""
        secret = self.gmail_oauth_client_secret
        return bool(
            self.gmail_oauth_client_id
            and secret is not None
            and secret.get_secret_value()
            and self.gmail_oauth_redirect_uri
        )

    @model_validator(mode="after")
    def validate_microsoft_oauth_settings_together(self) -> Self:
        """Require Microsoft OAuth fields together when any one is provided.

        Ordinary mock/local startup does not set these variables. Partial
        configuration is rejected so a connect path is never half-enabled.
        """
        secret_value = None
        if self.microsoft_oauth_client_secret is not None:
            secret_value = self.microsoft_oauth_client_secret.get_secret_value()
        present = (
            self.microsoft_oauth_client_id is not None,
            secret_value is not None,
            self.microsoft_oauth_redirect_uri is not None,
            self.microsoft_oauth_tenant is not None,
        )
        if any(present) and not all(present):
            raise ValueError(
                "MICROSOFT_OAUTH_CLIENT_ID, MICROSOFT_OAUTH_CLIENT_SECRET, "
                "MICROSOFT_OAUTH_REDIRECT_URI, and MICROSOFT_OAUTH_TENANT "
                "must be set together."
            )
        return self

    @property
    def microsoft_oauth_is_configured(self) -> bool:
        """Return True when Microsoft OAuth client settings are complete."""
        secret = self.microsoft_oauth_client_secret
        return bool(
            self.microsoft_oauth_client_id
            and secret is not None
            and secret.get_secret_value()
            and self.microsoft_oauth_redirect_uri
            and self.microsoft_oauth_tenant
        )

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

    @model_validator(mode="after")
    def validate_auth_settings(self) -> Self:
        """Fail closed in production and require complete OIDC settings when enabled."""
        if self.app_env == "production" and self.auth_mode != "oidc":
            raise ValueError("AUTH_MODE must be oidc when APP_ENV=production.")

        if self.auth_mode != "oidc":
            return self

        missing: list[str] = []
        if not self.oidc_issuer:
            missing.append("OIDC_ISSUER")
        if not self.oidc_audience:
            missing.append("OIDC_AUDIENCE")
        if not self.oidc_jwks_url:
            missing.append("OIDC_JWKS_URL")
        if missing:
            names = " and ".join(missing)
            raise ValueError(f"{names} must be set when AUTH_MODE=oidc.")
        if not self.oidc_required_permission:
            raise ValueError("OIDC_REQUIRED_PERMISSION must be set when AUTH_MODE=oidc.")
        return self

    @model_validator(mode="after")
    def validate_database_settings(self) -> Self:
        """Fail closed in production: PostgreSQL via psycopg is required."""
        if self.app_env != "production":
            return self

        if not self.database_url:
            raise ValueError("DATABASE_URL must be set when APP_ENV=production.")

        scheme = urlparse(self.database_url).scheme.lower()
        if scheme.startswith("sqlite"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg when APP_ENV=production.")
        if scheme != _PRODUCTION_DATABASE_SCHEME:
            raise ValueError("DATABASE_URL must use postgresql+psycopg when APP_ENV=production.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
