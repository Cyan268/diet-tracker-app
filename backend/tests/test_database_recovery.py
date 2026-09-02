import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPTS = ROOT / "scripts" / "deploy"
sys.path.insert(0, str(DEPLOY_SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "database_recovery", DEPLOY_SCRIPTS / "database_recovery.py"
)
assert SPEC and SPEC.loader
database_recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(database_recovery)


def fingerprint(users=1):
    return {
        "schemaRevision": "20260831_0009",
        "users": users,
        "user_profiles": users,
        "food_logs": 3,
        "ai_credentials": 0,
        "assistant_conversations": 2,
        "assistant_messages": 4,
    }


def write_receipt(tmp_path, *, users=1):
    artifact = tmp_path / "backup.dump"
    artifact.write_bytes(b"x" * 200)
    receipt = tmp_path / "backup.receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "formatVersion": 1,
                "database": "nutripilot",
                "status": "verified",
                "storageClass": "local-only",
                "artifact": artifact.name,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "sizeBytes": artifact.stat().st_size,
                "postgresImage": "postgres@sha256:" + "a" * 64,
                "fingerprint": fingerprint(users),
            }
        ),
        encoding="utf-8",
    )
    return receipt, artifact


def test_fingerprint_shape_is_strict():
    assert database_recovery.parse_fingerprint(json.dumps(fingerprint())) == fingerprint()

    invalid = fingerprint()
    invalid["users"] = -1
    with pytest.raises(database_recovery.ReleaseError, match="invalid count"):
        database_recovery.parse_fingerprint(json.dumps(invalid))


def test_backup_records_hash_image_and_source_fingerprint(tmp_path):
    payload = b"x" * 200

    class BackupRunner:
        def run(self, args, *, input_text=None):
            assert "psql" in args
            return json.dumps(fingerprint())

        def run_bytes(self, args, *, input_bytes=None):
            if "pg_dump" in args:
                return payload
            assert input_bytes == payload
            return b"; Archive created at 2026-09-02"

    current = {"release": "a" * 40, "sourceRevision": "a" * 40}
    resolved = {"services": {"postgres": {"image": "postgres@sha256:" + "b" * 64}}}
    receipt_path = database_recovery.create_backup(
        BackupRunner(), ["docker", "compose"], tmp_path, current, resolved
    )
    receipt, artifact = database_recovery.validate_receipt(receipt_path)
    assert receipt["fingerprint"] == fingerprint()
    assert receipt["postgresImage"] == resolved["services"]["postgres"]["image"]
    assert artifact.read_bytes() == payload


def test_receipt_rejects_tampered_backup(tmp_path):
    receipt, artifact = write_receipt(tmp_path)
    artifact.write_bytes(b"tampered")
    with pytest.raises(database_recovery.ReleaseError, match="does not match"):
        database_recovery.validate_receipt(receipt)


def test_restore_drill_is_disposable_networkless_and_compares_counts(tmp_path, monkeypatch):
    receipt, _ = write_receipt(tmp_path)
    commands = []
    cleanup = []

    class DrillRunner:
        def run(self, args, *, input_text=None):
            commands.append(args)
            if "psql" in args:
                return json.dumps(fingerprint())
            return "ok"

    monkeypatch.setattr(
        database_recovery.subprocess,
        "run",
        lambda args, **_kwargs: cleanup.append(args),
    )
    database_recovery.run_restore_drill(SimpleNamespace(receipt=str(receipt)), DrillRunner())

    docker_run = next(command for command in commands if command[:2] == ["docker", "run"])
    assert docker_run[docker_run.index("--network") + 1] == "none"
    assert "-p" not in docker_run and "--publish" not in docker_run
    assert any("pg_restore" in command for command in commands)
    assert cleanup and cleanup[0][:3] == ["docker", "rm", "--force"]

    report = json.loads((tmp_path / "backup.drill.json").read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["isolation"]["productionOverwrite"] is False


def test_restore_drill_rejects_count_mismatch_and_still_cleans_up(tmp_path, monkeypatch):
    receipt, _ = write_receipt(tmp_path, users=1)
    cleanup = []

    class MismatchRunner:
        def run(self, args, *, input_text=None):
            if "psql" in args:
                return json.dumps(fingerprint(users=0))
            return "ok"

    monkeypatch.setattr(
        database_recovery.subprocess,
        "run",
        lambda args, **_kwargs: cleanup.append(args),
    )
    with pytest.raises(database_recovery.ReleaseError, match="does not match"):
        database_recovery.run_restore_drill(SimpleNamespace(receipt=str(receipt)), MismatchRunner())
    assert cleanup and cleanup[0][:3] == ["docker", "rm", "--force"]
