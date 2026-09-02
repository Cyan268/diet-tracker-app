from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


async def test_password_is_hashed_with_argon2_and_can_be_verified() -> None:
    encoded = await hash_password("correct-horse-123")

    assert encoded.startswith("$argon2id$")
    assert await verify_password("correct-horse-123", encoded)
    assert not await verify_password("wrong-password", encoded)


def test_access_token_rejects_different_secret() -> None:
    settings = Settings(_env_file=None, jwt_secret="first-secret-that-is-at-least-32-bytes")
    other_settings = Settings(_env_file=None, jwt_secret="second-secret-that-is-at-least-32-bytes")
    token, _ = create_access_token(uuid4(), settings)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, other_settings)


def test_production_rejects_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="production JWT secret must be changed"):
        Settings(_env_file=None, environment="production")


def test_jwt_secret_must_be_at_least_32_characters() -> None:
    with pytest.raises(ValidationError, match="at least 32 items"):
        Settings(_env_file=None, jwt_secret="too-short")


def test_openai_provider_requires_server_side_api_key() -> None:
    with pytest.raises(ValidationError, match="openai_api_key is required"):
        Settings(_env_file=None, ai_provider="openai", openai_api_key=None)


def test_production_rejects_default_credential_encryption_key() -> None:
    with pytest.raises(
        ValidationError,
        match="production credential encryption key must be changed",
    ):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret="production-jwt-secret-that-is-at-least-32-bytes",
        )


def test_production_demo_protection_must_fail_closed() -> None:
    with pytest.raises(ValidationError, match="production demo protection must fail closed"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret="production-jwt-secret-that-is-at-least-32-bytes",
            credential_encryption_key="production-encryption-key-that-is-at-least-32-bytes",
            demo_protection_enabled=True,
            demo_protection_fail_closed=False,
        )


def test_production_authentication_protection_must_fail_closed() -> None:
    with pytest.raises(
        ValidationError,
        match="production authentication protection must fail closed",
    ):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret="production-jwt-secret-that-is-at-least-32-bytes",
            credential_encryption_key="production-encryption-key-that-is-at-least-32-bytes",
            demo_protection_enabled=False,
            auth_protection_enabled=True,
            auth_protection_fail_closed=False,
        )


def test_production_rejects_default_rate_limit_secret() -> None:
    with pytest.raises(ValidationError, match="production rate-limit HMAC secret must be changed"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret="production-jwt-secret-that-is-at-least-32-bytes",
            credential_encryption_key="production-encryption-key-that-is-at-least-32-bytes",
            demo_protection_enabled=False,
            auth_protection_enabled=True,
            auth_protection_fail_closed=True,
            allowed_hosts=["api.example.com"],
        )


def test_production_rejects_documented_secret_placeholders() -> None:
    with pytest.raises(ValidationError, match="production JWT secret must be changed"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret="<generate-at-least-32-random-characters>",
            credential_encryption_key="production-encryption-key-that-is-at-least-32-bytes",
            demo_protection_enabled=False,
            auth_protection_enabled=False,
            allowed_hosts=["api.example.com"],
        )


def test_production_requires_explicit_allowed_hosts() -> None:
    with pytest.raises(ValidationError, match="production allowed_hosts must be explicit"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret="production-jwt-secret-that-is-at-least-32-bytes",
            credential_encryption_key="production-encryption-key-that-is-at-least-32-bytes",
            demo_protection_enabled=False,
            auth_protection_enabled=False,
            allowed_hosts=["*"],
        )


def test_trusted_proxy_cidrs_are_validated_and_normalized() -> None:
    settings = Settings(_env_file=None, trusted_proxy_cidrs=["10.1.2.3/8", "2001:db8::1/64"])
    assert settings.trusted_proxy_cidrs == ["10.0.0.0/8", "2001:db8::/64"]

    with pytest.raises(ValidationError, match="does not appear to be an IPv4 or IPv6 network"):
        Settings(_env_file=None, trusted_proxy_cidrs=["not-a-network"])
    with pytest.raises(ValidationError, match="cannot trust every address"):
        Settings(_env_file=None, trusted_proxy_cidrs=["0.0.0.0/0"])


def test_render_postgres_url_selects_psycopg_driver() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:password@postgres.internal:5432/nutripilot",
    )

    assert settings.database_url.startswith("postgresql+psycopg://")


def test_platform_host_extends_the_production_allowlist() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql://user:password@postgres.internal:5432/nutripilot",
        redis_url="redis://redis.internal:6379/0",
        jwt_secret="production-jwt-secret-that-is-at-least-32-bytes",
        credential_encryption_key="production-encryption-key-that-is-at-least-32-bytes",
        rate_limit_hmac_secret="production-rate-limit-key-that-is-at-least-32-bytes",
        auth_protection_fail_closed=True,
        demo_protection_fail_closed=True,
        allowed_hosts=[],
        platform_external_host="NutriPilot-Demo.onrender.com.",
    )

    assert settings.effective_allowed_hosts == ["nutripilot-demo.onrender.com"]


def test_platform_host_rejects_a_url() -> None:
    with pytest.raises(ValidationError, match="hostname without scheme or port"):
        Settings(_env_file=None, platform_external_host="https://example.com")

    with pytest.raises(ValidationError, match="valid DNS hostname"):
        Settings(_env_file=None, platform_external_host="invalid host")


def test_automatic_demo_reset_requires_deployment_secret() -> None:
    with pytest.raises(ValidationError, match="demo_reset_password is required"):
        Settings(_env_file=None, demo_reset_interval_minutes=60, demo_reset_password=None)
