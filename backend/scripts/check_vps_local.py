"""Synthetic tests for the isolated U1 fixture only. Never a production smoke command."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from httpx2 import Client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8086")
    parser.add_argument(
        "--phase", choices=["http", "business", "spoof", "redis-down", "pg-down"], required=True
    )
    parser.add_argument("--web-dir", type=Path, default=Path("../dist"))
    args = parser.parse_args()
    if urlsplit(args.base_url).hostname not in {
        "localhost",
        "127.0.0.1",
        "172.30.91.2",
        "172.30.91.3",
    }:
        raise SystemExit("Refusing a target outside the isolated local fixture")
    checks = []
    with Client(base_url=args.base_url, headers={"Host": "localhost"}, timeout=15) as client:

        def check(label, method, path, expected, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code != expected:
                raise AssertionError(f"{label}: expected {expected}, got {response.status_code}")
            checks.append({"name": label, "status": response.status_code})
            return response

        if args.phase == "http":
            root = check("web", "GET", "/", 200)
            assert "<html" in root.text.lower()
            assert root.headers["cross-origin-opener-policy"] == "same-origin"
            assert root.headers["cross-origin-embedder-policy"] == "credentialless"
            check("spa", "GET", "/auth", 200)
            check("live", "GET", "/api/v1/health/live", 200)
            check("ready", "GET", "/api/v1/health/ready", 200)
            check("missing_asset", "GET", "/assets/no-such-file.wasm", 404)
            check("missing_api", "GET", "/api/v1/missing", 404)
            check("auth_required", "GET", "/api/v1/users/me", 401)
            check(
                "registration_closed",
                "POST",
                "/api/v1/auth/register",
                403,
                json={"email": "probe@example.com", "password": "local-only-password-123"},
            )
            check(
                "unknown_host_not_routed",
                "GET",
                "/api/v1/health/live",
                421,
                headers={"Host": "untrusted.invalid"},
            )
            check(
                "body_limit",
                "POST",
                "/api/v1/auth/login",
                413,
                content=b"x" * 1_100_000,
                headers={"Content-Type": "application/json"},
            )
            wasm = next(args.web_dir.rglob("*.wasm"))
            response = check("wasm", "GET", "/" + wasm.relative_to(args.web_dir).as_posix(), 200)
            assert response.headers["content-type"].startswith("application/wasm")
            assert response.content[:4] == b"\x00asm"
            cors = client.get(
                "/api/v1/meta/config", headers={"Origin": "https://untrusted.invalid"}
            )
            assert "access-control-allow-origin" not in cors.headers
            checks.append({"name": "no_cross_origin_grant", "status": cors.status_code})
        elif args.phase == "business":
            auth = check(
                "login",
                "POST",
                "/api/v1/auth/login",
                200,
                json={"email": "demo@nutripilot.example", "password": "U1-Local-Demo-Only-2026!"},
            ).json()
            client.headers["Authorization"] = "Bearer " + auth["access_token"]
            check("identity", "GET", "/api/v1/users/me", 200)
            payload = {
                "client_id": str(uuid4()),
                "log_date": "2026-08-31",
                "meal_type": "lunch",
                "custom_name": "U1 synthetic record",
                "amount": 1,
                "unit": "serving",
                "nutrition": {
                    "kcal": 120,
                    "protein": 10,
                    "fat": 3,
                    "carbs": 20,
                    "sugar": 1,
                    "sodium": 30,
                    "caffeine": 0,
                },
                "note": None,
            }
            log = check("create", "POST", "/api/v1/logs", 201, json=payload).json()
            replay = check("idempotent_replay", "POST", "/api/v1/logs", 200, json=payload).json()
            assert log["id"] == replay["id"]
            content = {key: value for key, value in payload.items() if key != "client_id"}
            content.update(expected_version=1, amount=2)
            path = "/api/v1/logs/" + log["id"]
            check("update", "PUT", path, 200, json=content)
            check("stale_version", "PUT", path, 409, json=content)
            check("delete", "DELETE", path + "?expected_version=2", 204)
            changes = check("sync", "GET", "/api/v1/sync/changes?after=0&limit=200", 200).json()
            own = [item for item in changes["changes"] if item["server_id"] == log["id"]]
            assert [item["operation"] for item in own] == ["upsert", "upsert", "delete"]
            check(
                "logout",
                "POST",
                "/api/v1/auth/logout",
                204,
                json={"refresh_token": auth["refresh_token"]},
            )
        elif args.phase == "spoof":
            # Distinct emails avoid the per-account bucket masking visitor-bucket bypass.
            for index in range(6):
                check(
                    f"spoof_{index + 1}",
                    "POST",
                    "/api/v1/auth/login",
                    401 if index < 5 else 429,
                    json={
                        "email": f"u1-{uuid4().hex}@example.com",
                        "password": "test-only-wrong-password",
                    },
                    headers={
                        "X-Forwarded-For": f"198.51.100.{index + 1}",
                        "Forwarded": f"for=203.0.113.{index + 1}",
                    },
                )
        elif args.phase == "redis-down":
            check("database_readiness_independent", "GET", "/api/v1/health/ready", 200)
            check(
                "auth_fails_closed",
                "POST",
                "/api/v1/auth/login",
                503,
                json={"email": "probe@example.com", "password": "test-only-password"},
            )
        elif args.phase == "pg-down":
            check("live_without_database", "GET", "/api/v1/health/live", 200)
            check("not_ready_without_database", "GET", "/api/v1/health/ready", 503)
    print(json.dumps({"phase": args.phase, "synthetic_local_only": True, "checks": checks}))


if __name__ == "__main__":
    main()
