import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.cli import serve_vps
from app.cli.vps_topology import topology_errors
from app.core import database
from app.core.config import load_settings
from app.models import AssistantMessage


def topology():
    log = {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}
    services = {
        name: {"logging": log, "networks": {"data": {}}}
        for name in ("api", "maintenance", "postgres", "redis", "proxy")
    }
    services["api"].update(
        {
            "image": "nutripilot:vps-test",
            "command": ["python", "-m", "app.cli.serve_vps"],
            "networks": {"edge": {"ipv4_address": "172.30.91.3"}, "data": {}},
            "environment": {
                "NUTRIPILOT_VPS_PROXY_ADDRESS": "172.30.91.2",
                "NUTRIPILOT_TRUSTED_PROXY_CIDRS": '["172.30.91.2/32"]',
                "NUTRIPILOT_ALLOWED_HOSTS": '["diet.example.com","127.0.0.1"]',
                "NUTRIPILOT_CORS_ORIGINS": "[]",
            },
        }
    )
    services["maintenance"].update({"image": "nutripilot:vps-test", "profiles": ["ops"]})
    services["proxy"].update(
        {
            "environment": {
                "NUTRIPILOT_SITE_ADDRESS": "diet.example.com",
                "NUTRIPILOT_API_UPSTREAM": "172.30.91.3:8000",
            },
            "networks": {"edge": {"ipv4_address": "172.30.91.2"}},
            "ports": [{"target": n, "published": str(n), "host_ip": "0.0.0.0"} for n in (80, 443)],
        }
    )
    return {
        "services": services,
        "networks": {
            "data": {"internal": True},
            "edge": {"ipam": {"config": [{"subnet": "172.30.91.0/28"}]}},
        },
    }


def test_topology_accepts_production_and_explicit_loopback_modes():
    config = topology()
    assert topology_errors(config) == []
    config["services"]["proxy"]["environment"]["NUTRIPILOT_SITE_ADDRESS"] = "http://localhost"
    config["services"]["api"]["environment"]["NUTRIPILOT_ALLOWED_HOSTS"] = (
        '["localhost","127.0.0.1"]'
    )
    for port in config["services"]["proxy"]["ports"]:
        port.update(host_ip="127.0.0.1", published=str(port["target"] + 8000))
    assert topology_errors(config, local=True) == []
    assert topology_errors(config)


@pytest.mark.parametrize("service", ["api", "postgres", "redis", "maintenance"])
def test_topology_rejects_published_backend_ports(service):
    config = topology()
    config["services"][service]["ports"] = [{"target": 5432, "published": "5432"}]
    assert f"{service} must not publish host ports" in topology_errors(config)


def test_topology_rejects_proxy_data_access_and_secret_environment():
    config = topology()
    config["services"]["proxy"]["networks"]["data"] = {}
    secret = "private-value-that-must-not-appear-in-diagnostics"
    config["services"]["api"]["environment"]["NUTRIPILOT_JWT_SECRET"] = secret
    errors = topology_errors(config)
    assert "proxy must not join the data network" in errors
    assert any("mounted as a secret" in item for item in errors)
    assert secret not in json.dumps(errors)


def test_topology_rejects_proxy_mismatch_and_unbounded_logs():
    config = topology()
    config["services"]["api"]["environment"]["NUTRIPILOT_TRUSTED_PROXY_CIDRS"] = '["172.30.0.0/16"]'
    config["services"]["redis"]["logging"] = {}
    assert len(topology_errors(config)) == 2


def test_mounted_settings_secrets_and_environment_precedence(tmp_path, monkeypatch):
    secret = "unit-test-mounted-secret-which-is-at-least-32-bytes"
    (tmp_path / "nutripilot_jwt_secret").write_text(secret)
    monkeypatch.setenv("NUTRIPILOT_SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("NUTRIPILOT_JWT_SECRET", raising=False)
    assert load_settings().jwt_secret.get_secret_value() == secret
    monkeypatch.setenv("NUTRIPILOT_JWT_SECRET", "unit-test-explicit-override-long-enough")
    assert load_settings().jwt_secret.get_secret_value() != secret


def test_missing_configured_secrets_directory_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("NUTRIPILOT_SECRETS_DIR", str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="secrets directory is unavailable"):
        load_settings()


def test_serve_only_executes_api_after_static_preflight(monkeypatch):
    calls = []
    monkeypatch.setattr(serve_vps, "preflight", lambda args: calls.append(args) or 0)
    monkeypatch.setattr(
        serve_vps.ScriptDirectory,
        "from_config",
        lambda _: SimpleNamespace(get_current_head=lambda: "test-head"),
    )
    monkeypatch.setattr(serve_vps.os, "execvp", lambda *args: calls.append(args))
    monkeypatch.setenv("NUTRIPILOT_REQUIRED_SCHEMA_REVISION", "before")
    assert serve_vps.main() == 0
    assert serve_vps.os.environ["NUTRIPILOT_REQUIRED_SCHEMA_REVISION"] == "test-head"
    command = calls[-1][1]
    assert "--no-proxy-headers" in command and "--no-access-log" in command
    assert "alembic" not in command and "reset_demo" not in str(calls)


def test_failed_preflight_does_not_start_api(monkeypatch):
    monkeypatch.setattr(serve_vps, "preflight", lambda _: 1)
    execute = MagicMock()
    monkeypatch.setattr(serve_vps.os, "execvp", execute)
    assert serve_vps.main() == 1
    execute.assert_not_called()


async def test_readiness_rejects_unmigrated_schema(monkeypatch):
    connection = AsyncMock()
    response = MagicMock()
    response.scalars.return_value.all.return_value = ["old-head"]
    connection.execute.return_value = response
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=connection)
    context.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(database, "engine", SimpleNamespace(connect=lambda: context))
    monkeypatch.setattr(database, "settings", SimpleNamespace(required_schema_revision="new-head"))
    with pytest.raises(SQLAlchemyError, match="schema is not ready"):
        await database.check_database()
    response.scalars.return_value.all.return_value = ["new-head"]
    await database.check_database()


def test_assistant_constraint_names_match_published_migration():
    names = {constraint.name for constraint in AssistantMessage.__table__.constraints}
    assert "uq_assistant_messages_conversation_sequence" in names
    assert "uq_assistant_messages_conversation_client_message" in names


def test_preflight_uses_running_proxy_for_caddy_validation():
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "deploy" / "preflight.sh"
    ).read_text()
    assert "ps --status running --services proxy" in script
    assert "exec -T proxy caddy validate" in script
    assert "run --rm --no-deps -T proxy caddy validate" in script
    assert 'MSYS2_ARG_CONV_EXCL="/etc/caddy/Caddyfile"' in script
