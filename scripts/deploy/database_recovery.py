#!/usr/bin/env python3
"""Create verified local PostgreSQL backups and restore them in isolation.

The restore drill always uses a disposable, network-isolated PostgreSQL
container. It never accepts a production database target or publishes a port.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from release_controller import (
    ReleaseError,
    ReleaseLock,
    Runner,
    atomic_write_bytes,
    atomic_write_json,
    compose_base,
    emit,
    file_sha256,
    load_json,
    resolved_compose,
)

FORMAT_VERSION = 1
DATABASE = "nutripilot"
DATABASE_USER = "nutripilot"
MINIMUM_BACKUP_BYTES = 100
FINGERPRINT_TABLES = (
    "users",
    "user_profiles",
    "food_logs",
    "ai_credentials",
    "assistant_conversations",
    "assistant_messages",
)


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fingerprint_sql() -> str:
    pairs = [
        "'schemaRevision', (SELECT version_num FROM alembic_version)",
        *(f"'{table}', (SELECT count(*) FROM {table})" for table in FINGERPRINT_TABLES),
    ]
    return "SELECT json_build_object(" + ", ".join(pairs) + ")::text"


def parse_fingerprint(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ReleaseError("database fingerprint is not valid JSON") from error
    required = {"schemaRevision", *FINGERPRINT_TABLES}
    if not isinstance(parsed, dict) or set(parsed) != required:
        raise ReleaseError("database fingerprint has an unexpected shape")
    if not isinstance(parsed["schemaRevision"], str):
        raise ReleaseError("database fingerprint has no schema revision")
    for table in FINGERPRINT_TABLES:
        value = parsed[table]
        if not isinstance(value, int) or value < 0:
            raise ReleaseError(f"database fingerprint has an invalid count for {table}")
    return parsed


def source_fingerprint(runner: Runner, compose: list[str]) -> dict[str, Any]:
    value = runner.run(
        [
            *compose,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            DATABASE_USER,
            "-d",
            DATABASE,
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            fingerprint_sql(),
        ]
    )
    return parse_fingerprint(value)


def validate_current_release(state_dir: Path, env_file: Path) -> dict[str, Any]:
    current = load_json(state_dir / "current.json")
    expected_hash = current.get("environmentFileSha256")
    if not isinstance(expected_hash, str) or file_sha256(env_file) != expected_hash:
        raise ReleaseError("environment file does not match the active release receipt")
    release = current.get("release")
    source_revision = current.get("sourceRevision")
    if not isinstance(release, str) or not isinstance(source_revision, str):
        raise ReleaseError("active release receipt has no immutable identity")
    return current


def postgres_image(resolved: dict[str, Any]) -> str:
    try:
        image = resolved["services"]["postgres"]["image"]
    except (KeyError, TypeError) as error:
        raise ReleaseError("resolved Compose config has no PostgreSQL image") from error
    if not isinstance(image, str) or "@sha256:" not in image:
        raise ReleaseError("PostgreSQL image must be pinned by digest")
    return image


def create_backup(
    runner: Runner,
    compose: list[str],
    backup_dir: Path,
    current: dict[str, Any],
    resolved: dict[str, Any],
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact = backup_dir / f"{stamp}-{current['release']}.dump"
    receipt_path = artifact.with_suffix(".receipt.json")
    if artifact.exists() or receipt_path.exists():
        raise ReleaseError("backup timestamp collision; retry after one second")

    fingerprint = source_fingerprint(runner, compose)
    payload = runner.run_bytes(
        [
            *compose,
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            DATABASE_USER,
            "-d",
            DATABASE,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
        ]
    )
    if len(payload) < MINIMUM_BACKUP_BYTES:
        raise ReleaseError("database backup is unexpectedly small")
    listing = runner.run_bytes(
        [*compose, "exec", "-T", "postgres", "pg_restore", "--list"],
        input_bytes=payload,
    )
    if b"Archive created at" not in listing:
        raise ReleaseError("pg_restore could not parse the database backup")

    atomic_write_bytes(artifact, payload)
    atomic_write_json(
        receipt_path,
        {
            "formatVersion": FORMAT_VERSION,
            "database": DATABASE,
            "status": "verified",
            "release": current["release"],
            "sourceRevision": current["sourceRevision"],
            "createdAt": now_iso(),
            "artifact": artifact.name,
            "sha256": file_sha256(artifact),
            "sizeBytes": artifact.stat().st_size,
            "postgresImage": postgres_image(resolved),
            "fingerprint": fingerprint,
            "storageClass": "local-only",
        },
    )
    emit("database.backup_verified", receipt=str(receipt_path), storageClass="local-only")
    return receipt_path


def validate_receipt(receipt_path: Path) -> tuple[dict[str, Any], Path]:
    receipt = load_json(receipt_path)
    if (
        receipt.get("formatVersion") != FORMAT_VERSION
        or receipt.get("database") != DATABASE
        or receipt.get("status") != "verified"
        or receipt.get("storageClass") != "local-only"
    ):
        raise ReleaseError("backup receipt is not a verified local NutriPilot backup")
    artifact_value = receipt.get("artifact")
    expected_hash = receipt.get("sha256")
    if not isinstance(artifact_value, str) or not isinstance(expected_hash, str):
        raise ReleaseError("backup receipt has no artifact digest")
    artifact = Path(artifact_value)
    if not artifact.is_absolute():
        artifact = receipt_path.parent / artifact
    if not artifact.is_file() or file_sha256(artifact) != expected_hash:
        raise ReleaseError("backup artifact is missing or does not match its receipt")
    if artifact.stat().st_size != receipt.get("sizeBytes"):
        raise ReleaseError("backup artifact size does not match its receipt")
    parse_fingerprint(json.dumps(receipt.get("fingerprint")))
    image = receipt.get("postgresImage")
    if not isinstance(image, str) or "@sha256:" not in image:
        raise ReleaseError("backup receipt has no immutable PostgreSQL image")
    return receipt, artifact.resolve()


def prune_local_backups(backup_dir: Path, keep: int) -> list[Path]:
    if keep < 1:
        raise ReleaseError("backup retention must keep at least one artifact")
    receipts = sorted(backup_dir.glob("*.receipt.json"), reverse=True)
    removed: list[Path] = []
    for receipt_path in receipts[keep:]:
        receipt, artifact = validate_receipt(receipt_path)
        if receipt.get("storageClass") != "local-only":
            raise ReleaseError("refusing to prune a non-local backup")
        artifact.unlink()
        receipt_path.unlink()
        removed.extend([artifact, receipt_path])
    return removed


def run_backup(args: argparse.Namespace, runner: Runner) -> None:
    env_file = Path(args.env_file).resolve()
    state_dir = Path(args.state_dir).resolve()
    backup_dir = Path(args.backup_dir).resolve()
    with ReleaseLock(state_dir):
        current = validate_current_release(state_dir, env_file)
        compose = compose_base(env_file)
        resolved = resolved_compose(runner, compose)
        runner.run([*compose, "up", "-d", "--wait", "postgres"])
        receipt = create_backup(runner, compose, backup_dir, current, resolved)
        removed = prune_local_backups(backup_dir, args.keep)
    emit(
        "database.backup_complete",
        receipt=str(receipt),
        prunedArtifacts=len(removed),
        disasterRecovery="not-provided",
    )


def wait_for_restore_database(runner: Runner, container: str) -> None:
    last_error: ReleaseError | None = None
    for _ in range(30):
        try:
            runner.run(
                [
                    "docker",
                    "exec",
                    container,
                    "pg_isready",
                    "-U",
                    "restore_admin",
                    "-d",
                    "nutripilot_restore",
                ]
            )
            return
        except ReleaseError as error:
            last_error = error
            time.sleep(2)
    raise ReleaseError("isolated restore database did not become ready") from last_error


def restore_fingerprint(runner: Runner, container: str) -> dict[str, Any]:
    value = runner.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "restore_admin",
            "-d",
            "nutripilot_restore",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            fingerprint_sql(),
        ]
    )
    return parse_fingerprint(value)


def run_restore_drill(args: argparse.Namespace, runner: Runner) -> None:
    receipt_path = Path(args.receipt).resolve()
    receipt, artifact = validate_receipt(receipt_path)
    container = f"nutripilot-restore-{os.getpid()}-{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(36)
    env_file: str | None = None
    report_path = receipt_path.with_name(receipt_path.name.replace(".receipt.json", ".drill.json"))
    started = time.monotonic()
    try:
        handle, env_file = tempfile.mkstemp(prefix="nutripilot-restore-", suffix=".env")
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("POSTGRES_DB=nutripilot_restore\n")
            stream.write("POSTGRES_USER=restore_admin\n")
            stream.write(f"POSTGRES_PASSWORD={password}\n")
        try:
            os.chmod(env_file, 0o600)
        except OSError:
            pass
        runner.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                container,
                "--network",
                "none",
                "--env-file",
                env_file,
                "--tmpfs",
                "/var/lib/postgresql/data:rw,noexec,nosuid,size=768m",
                receipt["postgresImage"],
            ]
        )
        wait_for_restore_database(runner, container)
        runner.run(["docker", "cp", str(artifact), f"{container}:/tmp/backup.dump"])
        runner.run(
            [
                "docker",
                "exec",
                container,
                "pg_restore",
                "-U",
                "restore_admin",
                "-d",
                "nutripilot_restore",
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                "/tmp/backup.dump",
            ]
        )
        restored = restore_fingerprint(runner, container)
        if restored != receipt["fingerprint"]:
            raise ReleaseError("restored database fingerprint does not match the source backup")
        atomic_write_json(
            report_path,
            {
                "formatVersion": FORMAT_VERSION,
                "status": "passed",
                "isolation": {
                    "container": "disposable",
                    "network": "none",
                    "publishedPorts": 0,
                    "productionOverwrite": False,
                },
                "receipt": str(receipt_path),
                "backupSha256": receipt["sha256"],
                "fingerprint": restored,
                "completedAt": now_iso(),
                "durationSeconds": round(time.monotonic() - started, 3),
            },
        )
        emit("database.restore_drill_passed", report=str(report_path))
    finally:
        if env_file is not None:
            try:
                os.unlink(env_file)
            except FileNotFoundError:
                pass
        subprocess.run(
            ["docker", "rm", "--force", container],
            check=False,
            capture_output=True,
        )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup")
    backup.add_argument("--env-file", required=True)
    backup.add_argument("--state-dir", required=True)
    backup.add_argument("--backup-dir", required=True)
    backup.add_argument("--keep", type=int, default=7)

    drill = subparsers.add_parser("restore-drill")
    drill.add_argument("--receipt", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    runner = Runner()
    try:
        if args.command == "backup":
            run_backup(args, runner)
        else:
            run_restore_drill(args, runner)
    except ReleaseError as error:
        emit("database.recovery_failed", error=str(error), command=args.command)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
