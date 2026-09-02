from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cli.production_preflight import (
    _validation_messages,
    main,
    production_preflight_errors,
)
from app.core.config import Settings

WEB_FIXTURE = Path(__file__).parent / "fixtures" / "web-dist"
MISSING_WEB_FIXTURE = Path(__file__).parent / "fixtures" / "missing-web-dist"


def production_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "environment": "production",
        "database_url": (
            "postgresql+psycopg://nutripilot:password@postgres.internal:5432/nutripilot"
        ),
        "redis_url": "rediss://redis.internal:6379/0",
        "jwt_secret": "production-jwt-secret-that-is-at-least-32-bytes",
        "credential_encryption_key": "production-encryption-key-that-is-at-least-32-bytes",
        "rate_limit_hmac_secret": "production-rate-limit-key-that-is-at-least-32-bytes",
        "allowed_hosts": ["api.example.com"],
        "cors_origins": ["https://app.example.com"],
        "public_registration_enabled": False,
        "auth_protection_enabled": True,
        "auth_protection_fail_closed": True,
        "demo_protection_enabled": True,
        "demo_protection_fail_closed": True,
        "trusted_proxy_cidrs": ["10.0.0.0/8"],
    }
    values.update(overrides)
    return Settings(**values)


def test_portfolio_proxy_preflight_accepts_hardened_configuration() -> None:
    errors = production_preflight_errors(
        production_settings(),
        portfolio=True,
        behind_proxy=True,
    )

    assert errors == []


def test_single_origin_portfolio_accepts_embedded_web_without_cors() -> None:
    errors = production_preflight_errors(
        production_settings(cors_origins=[], web_dist_dir=WEB_FIXTURE),
        portfolio=True,
        behind_proxy=False,
        single_origin_web=True,
    )

    assert errors == []


def test_render_builtin_environment_values_are_used_as_fallbacks(monkeypatch) -> None:
    monkeypatch.delenv("NUTRIPILOT_PLATFORM_EXTERNAL_HOST", raising=False)
    monkeypatch.delenv("NUTRIPILOT_RELEASE", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "nutripilot-demo.onrender.com")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "06bb662")

    settings = Settings(_env_file=None)

    assert settings.platform_external_host == "nutripilot-demo.onrender.com"
    assert settings.release == "06bb662"

    monkeypatch.setenv("NUTRIPILOT_PLATFORM_EXTERNAL_HOST", "portfolio.example.com")
    monkeypatch.setenv("NUTRIPILOT_RELEASE", "explicit-release")
    overridden_settings = Settings(_env_file=None)

    assert overridden_settings.platform_external_host == "portfolio.example.com"
    assert overridden_settings.release == "explicit-release"


def test_single_origin_preflight_requires_built_index() -> None:
    errors = production_preflight_errors(
        production_settings(cors_origins=[], web_dist_dir=MISSING_WEB_FIXTURE),
        portfolio=True,
        behind_proxy=False,
        single_origin_web=True,
    )

    assert "single-origin Web deployment must contain web_dist_dir/index.html" in errors


def test_preflight_reports_network_and_portfolio_policy_errors() -> None:
    settings = production_settings(
        environment="test",
        database_url="sqlite:///local.db",
        redis_url="redis://127.0.0.1:6379/0",
        auth_protection_enabled=False,
        public_registration_enabled=True,
        demo_protection_enabled=False,
        trusted_proxy_cidrs=[],
        cors_origins=["http://app.example.com"],
    )

    errors = production_preflight_errors(settings, portfolio=True, behind_proxy=True)

    assert "environment must be production" in errors
    assert "authentication protection must be enabled" in errors
    assert any(error.startswith("database_url must use") for error in errors)
    assert "redis_url must not use a loopback hostname in production" in errors
    assert "trusted_proxy_cidrs must be configured behind a proxy" in errors
    assert "portfolio deployment must disable public registration" in errors
    assert "portfolio deployment must enable demo protection" in errors
    assert any(error.startswith("CORS origin must be") for error in errors)


def test_validation_output_does_not_echo_secret_input() -> None:
    secret = "replace-with-a-real-secret-that-must-not-be-printed"
    with pytest.raises(ValidationError) as raised:
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret=secret,
        )

    rendered = " ".join(_validation_messages(raised.value))
    assert secret not in rendered


def test_main_redacts_invalid_environment_value(monkeypatch, capsys) -> None:
    sensitive_invalid_value = "[super-sensitive-invalid-host-value]"
    monkeypatch.setenv("NUTRIPILOT_ALLOWED_HOSTS", sensitive_invalid_value)

    assert main([]) == 1
    output = capsys.readouterr().out
    assert '"status": "failed"' in output
    assert "environment variable parsing failed" in output
    assert sensitive_invalid_value not in output


def test_vps_preflight_rejects_broad_proxy_trust_and_automatic_reset() -> None:
    settings = production_settings(
        vps_proxy_address="172.30.91.2",
        demo_reset_interval_minutes=60,
        demo_reset_password="test-only-demo-password",
    )
    errors = production_preflight_errors(settings, portfolio=True, behind_proxy=True, vps=True)
    assert "VPS must trust exactly its configured proxy host address" in errors
    assert "VPS startup must not schedule automatic demo resets" in errors
    assert "VPS same-origin deployment must use an empty CORS allowlist" in errors


def test_vps_preflight_accepts_one_explicit_proxy_only() -> None:
    settings = production_settings(
        vps_proxy_address="172.30.91.2",
        trusted_proxy_cidrs=["172.30.91.2/32"],
        cors_origins=[],
        web_dist_dir=WEB_FIXTURE,
    )
    assert (
        production_preflight_errors(
            settings,
            portfolio=True,
            behind_proxy=True,
            single_origin_web=True,
            vps=True,
        )
        == []
    )


def test_vps_preflight_rejects_mismatched_or_missing_proxy() -> None:
    for address in (None, "172.30.91.3"):
        settings = production_settings(
            vps_proxy_address=address,
            trusted_proxy_cidrs=["172.30.91.2/32"],
            cors_origins=[],
        )
        assert production_preflight_errors(settings, portfolio=True, behind_proxy=True, vps=True)
