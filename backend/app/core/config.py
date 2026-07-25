import os
import re
from decimal import Decimal
from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path
from typing import Literal

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_placeholder_secret(value: str) -> bool:
    lowered = value.lower()
    return any(
        marker in lowered
        for marker in ("development-only", "change-me", "replace-with", "<generate")
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="NUTRIPILOT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "NutriPilot API"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://nutripilot:nutripilot@localhost:5432/nutripilot"
    database_echo: bool = False
    redis_url: str = "redis://localhost:6379/0"
    public_registration_enabled: bool = True
    auth_protection_enabled: bool = True
    auth_protection_fail_closed: bool = False
    auth_rate_limit_window_seconds: int = Field(default=900, ge=10, le=86400)
    auth_login_attempts_per_window: int = Field(default=10, ge=1, le=1000)
    auth_register_attempts_per_window: int = Field(default=5, ge=1, le=1000)
    auth_visitor_requests_per_window: int = Field(default=30, ge=1, le=5000)
    trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    rate_limit_hmac_secret: SecretStr = Field(
        default=SecretStr("development-only-rate-limit-hmac-secret"),
        min_length=32,
    )
    demo_protection_enabled: bool = True
    demo_protection_fail_closed: bool = False
    demo_rate_limit_window_seconds: int = Field(default=60, ge=10, le=3600)
    demo_write_requests_per_window: int = Field(default=30, ge=1, le=1000)
    demo_ai_requests_per_window: int = Field(default=12, ge=1, le=1000)
    demo_max_logs: int = Field(default=100, ge=1, le=10000)
    demo_max_private_foods: int = Field(default=10, ge=1, le=1000)
    demo_max_conversations: int = Field(default=8, ge=1, le=1000)
    demo_max_messages_per_conversation: int = Field(default=40, ge=2, le=1000)
    demo_reset_interval_minutes: int = Field(default=0, ge=0, le=10080)
    demo_timezone_offset_minutes: int = Field(default=480, ge=-720, le=840)
    demo_reset_email: EmailStr = "demo@nutripilot.example"
    demo_reset_password: SecretStr | None = None
    demo_reset_lock_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    cors_origins: list[str] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=lambda: ["*"])
    platform_external_host: str | None = Field(
        default_factory=lambda: os.getenv("RENDER_EXTERNAL_HOSTNAME"),
        min_length=1,
        max_length=253,
    )
    web_dist_dir: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0, ge=0, le=1)
    release: str | None = Field(
        default_factory=lambda: os.getenv("RENDER_GIT_COMMIT"),
        min_length=1,
        max_length=200,
    )
    jwt_secret: SecretStr = Field(
        default=SecretStr("development-only-change-me-at-least-32-bytes"),
        min_length=32,
    )
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "nutripilot-api"
    jwt_audience: str = "nutripilot-mobile"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=90)
    credential_encryption_key: SecretStr = Field(
        default=SecretStr("development-only-encryption-key-change-me-at-least-32-bytes"),
        min_length=32,
    )
    ai_provider: Literal["rule_based", "openai"] = "rule_based"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = Field(default="gpt-5.6-luna", min_length=1, max_length=120)
    ai_timeout_seconds: float = Field(default=8, ge=1, le=60)
    ai_max_attempts: int = Field(default=2, ge=1, le=3)
    ai_retry_delay_seconds: float = Field(default=0.15, ge=0, le=2)
    ai_input_price_per_million_usd: Decimal | None = Field(default=None, ge=0)
    ai_output_price_per_million_usd: Decimal | None = Field(default=None, ge=0)

    @field_validator(
        "sentry_dsn",
        "release",
        "demo_reset_password",
        "platform_external_host",
        "web_dist_dir",
        mode="before",
    )
    @classmethod
    def empty_observability_values_are_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def select_async_postgres_driver(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("platform_external_host")
    @classmethod
    def validate_platform_external_host(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower().rstrip(".")
        if "://" in normalized or "/" in normalized or ":" in normalized or not normalized:
            raise ValueError("platform external host must be a hostname without scheme or port")
        hostname_pattern = re.compile(
            r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        )
        if hostname_pattern.fullmatch(normalized) is None:
            raise ValueError("platform external host must be a valid DNS hostname")
        return normalized

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def normalize_trusted_proxy_cidrs(cls, values: list[str]) -> list[str]:
        networks = [ip_network(value, strict=False) for value in values]
        if any(network.prefixlen == 0 for network in networks):
            raise ValueError("trusted proxy CIDR cannot trust every address")
        return [str(network) for network in networks]

    @model_validator(mode="after")
    def reject_insecure_production_settings(self) -> "Settings":
        if self.ai_provider == "openai" and (
            self.openai_api_key is None or not self.openai_api_key.get_secret_value()
        ):
            raise ValueError("openai_api_key is required when ai_provider is openai")
        if self.environment == "production":
            if self.debug:
                raise ValueError("debug must be disabled in production")
            if _is_placeholder_secret(self.jwt_secret.get_secret_value()):
                raise ValueError("production JWT secret must be changed")
            if _is_placeholder_secret(self.credential_encryption_key.get_secret_value()):
                raise ValueError("production credential encryption key must be changed")
            if self.demo_protection_enabled and not self.demo_protection_fail_closed:
                raise ValueError("production demo protection must fail closed")
            if self.auth_protection_enabled and not self.auth_protection_fail_closed:
                raise ValueError("production authentication protection must fail closed")
            uses_development_rate_secret = _is_placeholder_secret(
                self.rate_limit_hmac_secret.get_secret_value()
            )
            if self.auth_protection_enabled and uses_development_rate_secret:
                raise ValueError("production rate-limit HMAC secret must be changed")
            effective_allowed_hosts = {
                *self.allowed_hosts,
                *([self.platform_external_host] if self.platform_external_host else []),
            }
            if not effective_allowed_hosts or "*" in effective_allowed_hosts:
                raise ValueError("production allowed_hosts must be explicit")
        if self.demo_reset_interval_minutes > 0 and self.demo_reset_password is None:
            raise ValueError("demo_reset_password is required when automatic reset is enabled")
        return self

    @property
    def effective_allowed_hosts(self) -> list[str]:
        hosts = [*self.allowed_hosts]
        if self.platform_external_host and self.platform_external_host not in hosts:
            hosts.append(self.platform_external_host)
        return hosts


@lru_cache
def get_settings() -> Settings:
    return Settings()
