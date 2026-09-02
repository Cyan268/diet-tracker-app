import argparse
import json
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError
from pydantic_settings import SettingsError

from app.core.config import Settings, load_settings

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _service_url_error(name: str, value: str, schemes: set[str]) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme not in schemes:
        return f"{name} must use one of: {', '.join(sorted(schemes))}"
    if parsed.hostname is None:
        return f"{name} must include a hostname"
    if parsed.hostname in LOCAL_HOSTS:
        return f"{name} must not use a loopback hostname in production"
    return None


def production_preflight_errors(
    settings: Settings,
    *,
    portfolio: bool,
    behind_proxy: bool,
    single_origin_web: bool = False,
    vps: bool = False,
) -> list[str]:
    errors: list[str] = []
    if settings.environment != "production":
        errors.append("environment must be production")
    if not settings.auth_protection_enabled:
        errors.append("authentication protection must be enabled")

    database_error = _service_url_error(
        "database_url",
        settings.database_url,
        {"postgresql+psycopg"},
    )
    if database_error:
        errors.append(database_error)
    redis_error = _service_url_error("redis_url", settings.redis_url, {"redis", "rediss"})
    if redis_error:
        errors.append(redis_error)

    if behind_proxy and not settings.trusted_proxy_cidrs:
        errors.append("trusted_proxy_cidrs must be configured behind a proxy")

    if vps:
        try:
            address = ip_address(settings.vps_proxy_address or "")
            networks = [ip_network(value) for value in settings.trusted_proxy_cidrs]
            if len(networks) != 1 or networks[0] != ip_network(
                f"{address}/{address.max_prefixlen}"
            ):
                errors.append("VPS must trust exactly its configured proxy host address")
        except ValueError:
            errors.append("VPS proxy address must be an explicit IP address")
        if settings.demo_reset_interval_minutes != 0:
            errors.append("VPS startup must not schedule automatic demo resets")
        if settings.cors_origins:
            errors.append("VPS same-origin deployment must use an empty CORS allowlist")
        if any("*" in host for host in settings.effective_allowed_hosts):
            errors.append("VPS allowed_hosts must not contain wildcard patterns")
        if settings.log_format != "json" or settings.database_echo:
            errors.append("VPS requires JSON logs and disabled SQL echo")

    for origin in settings.cors_origins:
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or parsed.hostname is None:
            errors.append(f"CORS origin must be an absolute HTTPS origin: {origin}")
        if origin == "*":
            errors.append("wildcard CORS origin is not allowed")

    if portfolio:
        if settings.public_registration_enabled:
            errors.append("portfolio deployment must disable public registration")
        if not settings.demo_protection_enabled:
            errors.append("portfolio deployment must enable demo protection")
        if not settings.cors_origins and not single_origin_web:
            errors.append("portfolio deployment must configure the HTTPS Web origin")
    if single_origin_web:
        if settings.web_dist_dir is None:
            errors.append("single-origin Web deployment must configure web_dist_dir")
        elif not (Path(settings.web_dist_dir) / "index.html").is_file():
            errors.append("single-origin Web deployment must contain web_dist_dir/index.html")
    return errors


def _validation_messages(error: ValidationError) -> list[str]:
    messages = []
    for item in error.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "settings"
        messages.append(f"{location}: {item['msg']}")
    return messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate NutriPilot production configuration")
    parser.add_argument(
        "--portfolio",
        action="store_true",
        help="require the public portfolio demo policy",
    )
    parser.add_argument(
        "--behind-proxy",
        action="store_true",
        help="require at least one trusted reverse-proxy CIDR",
    )
    parser.add_argument(
        "--single-origin-web",
        action="store_true",
        help="require an embedded Expo Web build instead of a separate CORS origin",
    )
    parser.add_argument("--vps", action="store_true", help="require the single-VPS safety contract")
    args = parser.parse_args(argv)

    try:
        settings = load_settings()
    except SettingsError:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "errors": ["settings: environment variable parsing failed"],
                }
            )
        )
        return 1
    except ValidationError as error:
        print(json.dumps({"status": "failed", "errors": _validation_messages(error)}))
        return 1
    except (OSError, ValueError):
        print(json.dumps({"status": "failed", "errors": ["settings: secret files unavailable"]}))
        return 1

    errors = production_preflight_errors(
        settings,
        portfolio=args.portfolio,
        behind_proxy=args.behind_proxy,
        single_origin_web=args.single_origin_web,
        vps=args.vps,
    )
    print(
        json.dumps(
            {
                "status": "failed" if errors else "ok",
                "checks": {
                    "portfolio": args.portfolio,
                    "behind_proxy": args.behind_proxy,
                    "single_origin_web": args.single_origin_web,
                    "vps": args.vps,
                },
                "errors": errors,
            }
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
