import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "release_controller", ROOT / "scripts" / "deploy" / "release_controller.py"
)
assert SPEC and SPEC.loader
release_controller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_controller)


def manifest(*, local=True, release="candidate", schema="20260831_0009"):
    source = "source" if local else "a" * 40
    release = release if local else source
    image_reference = "nutripilot:test" if local else "ghcr.io/example/app@sha256:" + "b" * 64
    component_reference = "component:test" if local else "example@sha256:" + "c" * 64
    record = {"reference": component_reference, "id": "sha256:" + "d" * 64}
    return {
        "formatVersion": 1,
        "release": release,
        "sourceRevision": source,
        "requiresBackup": False,
        "image": {"reference": image_reference, "id": "sha256:" + "e" * 64},
        "components": {"proxy": record, "postgres": record, "redis": record},
        "schema": {"target": schema, "compatible": [schema]},
    }


def test_manifest_requires_immutable_production_identity():
    value = manifest(local=False)
    release_controller.validate_manifest(value, local=False)

    value["release"] = "friendly-name"
    with pytest.raises(release_controller.ReleaseError, match="equal sourceRevision"):
        release_controller.validate_manifest(value, local=False)

    value = manifest(local=False)
    value["image"]["reference"] = "ghcr.io/example/app:latest"
    with pytest.raises(release_controller.ReleaseError, match="forbidden"):
        release_controller.validate_manifest(value, local=False)


def test_manifest_rejects_unsafe_release_and_incompatible_target():
    value = manifest()
    value["release"] = "../escape"
    with pytest.raises(release_controller.ReleaseError, match="safe identifier"):
        release_controller.validate_manifest(value, local=True)

    value = manifest()
    value["schema"]["compatible"] = ["older"]
    with pytest.raises(release_controller.ReleaseError, match="contain the target"):
        release_controller.validate_manifest(value, local=True)


def test_compose_must_match_manifest_without_secret_environment():
    value = manifest()
    services = {
        "api": {
            "image": value["image"]["reference"],
            "environment": {"NUTRIPILOT_RELEASE": value["release"]},
        },
        "maintenance": {"image": value["image"]["reference"]},
        **{
            name: {"image": value["components"][name]["reference"]}
            for name in ("proxy", "postgres", "redis")
        },
    }
    release_controller.validate_resolved_compose({"services": services}, value)

    services["api"]["environment"]["NUTRIPILOT_JWT_SECRET"] = "never-log-this"
    with pytest.raises(release_controller.ReleaseError, match="must not be") as error:
        release_controller.validate_resolved_compose({"services": services}, value)
    assert "never-log-this" not in str(error.value)


def test_preflight_runs_candidate_caddy_binary_explicitly():
    value = manifest()
    commands = []

    class RecordingRunner:
        def run(self, args, *, input_text=None):
            commands.append(args)
            return ""

    resolved = {
        "services": {
            "proxy": {
                "environment": {
                    "NUTRIPILOT_SITE_ADDRESS": "http://localhost",
                    "NUTRIPILOT_API_UPSTREAM": "172.30.92.3:8000",
                },
                "volumes": [
                    {
                        "source": "D:/project/deploy/Caddyfile",
                        "target": "/etc/caddy/Caddyfile",
                    }
                ],
            }
        }
    }
    release_controller.full_preflight(
        RecordingRunner(), ["docker", "compose"], resolved, value, local=True
    )
    assert commands[-1][-5:-1] == [
        value["components"]["proxy"]["reference"],
        "caddy",
        "validate",
        "--config",
    ]


def test_release_lock_rejects_concurrent_owner_and_cleans_up(tmp_path):
    with release_controller.ReleaseLock(tmp_path):
        owner = json.loads((tmp_path / ".release.lock" / "owner.json").read_text())
        assert owner["pid"] > 0
        with pytest.raises(release_controller.ReleaseError, match="already exists"):
            with release_controller.ReleaseLock(tmp_path):
                pass
    assert not (tmp_path / ".release.lock").exists()


def test_promotion_and_application_rollback_swap_are_atomic(tmp_path):
    env_file = tmp_path / "release.env"
    env_file.write_text("NUTRIPILOT_RELEASE=test\n")
    previous = manifest(release="previous")
    candidate = manifest(release="candidate")

    release_controller.promote(tmp_path, previous, env_file)
    release_controller.promote(tmp_path, candidate, env_file)
    current_path, previous_path = release_controller.state_paths(tmp_path)
    assert release_controller.load_json(current_path)["release"] == "candidate"
    assert release_controller.load_json(previous_path)["release"] == "previous"

    release_controller.swap_for_rollback(tmp_path, env_file)
    assert release_controller.load_json(current_path)["release"] == "previous"
    assert release_controller.load_json(previous_path)["release"] == "candidate"


def test_backup_creation_verifies_archive_and_binds_receipt(tmp_path):
    payload = b"x" * 200

    class BackupRunner:
        def run_bytes(self, args, *, input_bytes=None):
            if "pg_dump" in args:
                return payload
            assert input_bytes == payload
            return b"; Archive created at 2026-09-01"

    value = manifest()
    receipt = release_controller.create_verified_backup(
        BackupRunner(), ["docker", "compose"], tmp_path, value
    )
    release_controller.validate_backup_receipt(receipt, value)

    receipt_value = release_controller.load_json(receipt)
    receipt_value["forRelease"] = "different"
    release_controller.atomic_write_json(receipt, receipt_value)
    with pytest.raises(release_controller.ReleaseError, match="bound to this release"):
        release_controller.validate_backup_receipt(receipt, value)


def test_migration_failure_never_starts_candidate_or_promotes(tmp_path, monkeypatch):
    value = manifest()
    candidate = tmp_path / "candidate.json"
    release_controller.atomic_write_json(candidate, value)
    env_file = tmp_path / "release.env"
    env_file.write_text("safe=test\n")
    events = []

    class FailingRunner:
        def run(self, args, *, input_text=None):
            events.append(args)
            if "alembic" in args and "upgrade" in args:
                raise release_controller.ReleaseError("migration failed")
            return ""

    monkeypatch.setattr(release_controller, "resolved_compose", lambda *_: {"services": {}})
    monkeypatch.setattr(release_controller, "validate_resolved_compose", lambda *_: None)
    monkeypatch.setattr(release_controller, "ensure_images", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(release_controller, "full_preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(release_controller, "query_schema", lambda *_: "20260831_0009")
    monkeypatch.setattr(release_controller, "smoke", lambda *_: None)
    args = SimpleNamespace(
        env_file=str(env_file),
        candidate=str(candidate),
        state_dir=str(tmp_path / "state"),
        backup_receipt=None,
        smoke_url="http://localhost:8087",
        local=True,
    )

    with pytest.raises(release_controller.ReleaseError, match="migration failed"):
        release_controller.run_apply(args, FailingRunner())
    assert not (tmp_path / "state" / "current.json").exists()
    assert not any("api" in call and "up" in call for call in events)
