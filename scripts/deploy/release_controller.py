#!/usr/bin/env python3
"""Deterministic single-VPS release and application-only rollback controller.

This host-side tool never reads secret file contents and never downgrades the
database. Production execution requires an immutable manifest and creates or
validates a release-bound backup receipt when the candidate requires a backup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FORMAT_VERSION = 1
SCHEMA_QUERY = "SELECT version_num FROM alembic_version"
SENSITIVE_ENV_KEYS = {
    "NUTRIPILOT_DATABASE_URL",
    "NUTRIPILOT_JWT_SECRET",
    "NUTRIPILOT_CREDENTIAL_ENCRYPTION_KEY",
    "NUTRIPILOT_RATE_LIMIT_HMAC_SECRET",
    "NUTRIPILOT_DEMO_RESET_PASSWORD",
}


class ReleaseError(RuntimeError):
    """A release invariant or command failed."""


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def emit(event: str, **details: Any) -> None:
    print(json.dumps({"event": event, **details}, ensure_ascii=False, sort_keys=True))


class Runner:
    def run_bytes(self, args: list[str], *, input_bytes: bytes | None = None) -> bytes:
        completed = subprocess.run(
            args,
            check=False,
            input=input_bytes,
            capture_output=True,
        )
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout)[-3000:].decode(
                "utf-8", errors="replace"
            )
            raise ReleaseError(f"command failed ({args[0]}): {message.strip()}")
        return completed.stdout

    def run(self, args: list[str], *, input_text: str | None = None) -> str:
        output = self.run_bytes(
            args,
            input_bytes=input_text.encode("utf-8") if input_text is not None else None,
        )
        return output.decode("utf-8").strip()


class ReleaseLock(AbstractContextManager["ReleaseLock"]):
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.path = state_dir / ".release.lock"

    def __enter__(self) -> ReleaseLock:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.path.mkdir()
        except FileExistsError as error:
            raise ReleaseError(
                f"release lock already exists at {self.path}; "
                "inspect its owner.json before recovery"
            ) from error
        atomic_write_json(
            self.path / "owner.json",
            {"pid": os.getpid(), "host": socket.gethostname(), "acquiredAt": now_iso()},
        )
        return self

    def __exit__(self, *_: object) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseError(f"cannot read JSON document: {path}") from error
    if not isinstance(value, dict):
        raise ReleaseError(f"JSON document must be an object: {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_safe_image_ref(reference: str, *, local: bool) -> None:
    if not reference or reference.endswith(":latest") or reference == "latest":
        raise ReleaseError("mutable or empty image references are forbidden")
    if not local and "@sha256:" not in reference:
        raise ReleaseError(f"production manifest requires digest reference: {reference}")


def validate_manifest(manifest: dict[str, Any], *, local: bool) -> None:
    if manifest.get("formatVersion") != FORMAT_VERSION:
        raise ReleaseError("unsupported release manifest format")
    release = manifest.get("release")
    source = manifest.get("sourceRevision")
    if (
        not isinstance(release, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release) is None
    ):
        raise ReleaseError("release must be a safe identifier")
    if not local and (not isinstance(source, str) or re.fullmatch(r"[0-9a-f]{40}", source) is None):
        raise ReleaseError("production sourceRevision must be a full Git SHA")
    if not local and release != source:
        raise ReleaseError("production release must equal sourceRevision")
    image = manifest.get("image")
    if not isinstance(image, dict):
        raise ReleaseError("image record is required")
    ensure_safe_image_ref(str(image.get("reference", "")), local=local)
    if not str(image.get("id", "")).startswith("sha256:"):
        raise ReleaseError("image ID is required")
    schema = manifest.get("schema")
    if not isinstance(schema, dict):
        raise ReleaseError("schema compatibility record is required")
    target = schema.get("target")
    compatible = schema.get("compatible")
    if not isinstance(target, str) or not target:
        raise ReleaseError("target schema is required")
    if not isinstance(compatible, list) or target not in compatible:
        raise ReleaseError("compatible schemas must contain the target schema")
    components = manifest.get("components")
    if not isinstance(components, dict) or set(components) != {"proxy", "postgres", "redis"}:
        raise ReleaseError("proxy, postgres, and redis component records are required")
    for component in components.values():
        if not isinstance(component, dict):
            raise ReleaseError("invalid component record")
        ensure_safe_image_ref(str(component.get("reference", "")), local=local)
        if not str(component.get("id", "")).startswith("sha256:"):
            raise ReleaseError("component image ID is required")


def image_record(runner: Runner, source_reference: str, *, local: bool) -> dict[str, Any]:
    raw = runner.run(["docker", "image", "inspect", source_reference])
    values = json.loads(raw)
    if not isinstance(values, list) or len(values) != 1:
        raise ReleaseError(f"image inspect returned an unexpected result: {source_reference}")
    value = values[0]
    digests = sorted(value.get("RepoDigests") or [])
    reference = source_reference if local else (digests[0] if digests else "")
    ensure_safe_image_ref(reference, local=local)
    labels = (value.get("Config") or {}).get("Labels") or {}
    return {
        "sourceReference": source_reference,
        "reference": reference,
        "id": value["Id"],
        "repoDigests": digests,
        "sizeBytes": value.get("Size"),
        "labels": {
            "org.opencontainers.image.revision": labels.get("org.opencontainers.image.revision"),
            "io.nutripilot.release": labels.get("io.nutripilot.release"),
        },
    }


def create_manifest(args: argparse.Namespace, runner: Runner) -> dict[str, Any]:
    local = args.local
    application = image_record(runner, args.image, local=local)
    if application["labels"]["io.nutripilot.release"] != args.release:
        raise ReleaseError("application image release label does not match --release")
    if application["labels"]["org.opencontainers.image.revision"] != args.source_revision:
        raise ReleaseError("application image revision label does not match --source-revision")
    component_sources = {
        "proxy": args.proxy_image,
        "postgres": args.postgres_image,
        "redis": args.redis_image,
    }
    manifest = {
        "formatVersion": FORMAT_VERSION,
        "release": args.release,
        "sourceRevision": args.source_revision,
        "createdAt": now_iso(),
        "requiresBackup": args.requires_backup,
        "image": application,
        "components": {
            name: image_record(runner, reference, local=local)
            for name, reference in component_sources.items()
        },
        "schema": {
            "target": args.schema,
            "compatible": sorted(set(args.compatible_schema + [args.schema])),
            "rollbackPolicy": "application-only; never run database downgrade",
        },
    }
    validate_manifest(manifest, local=local)
    output = Path(args.output).resolve()
    if output.exists():
        raise ReleaseError(f"refusing to overwrite manifest: {output}")
    atomic_write_json(output, manifest)
    emit("manifest.created", path=str(output), release=args.release)
    return manifest


def compose_base(env_file: Path) -> list[str]:
    compose_file = Path(__file__).resolve().parents[2] / "deploy" / "compose.prod.yml"
    return [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
        "--profile",
        "ops",
    ]


def resolved_compose(runner: Runner, compose: list[str]) -> dict[str, Any]:
    runner.run([*compose, "config", "--quiet"])
    raw = runner.run([*compose, "config", "--format", "json"])
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ReleaseError("resolved Compose output must be an object")
    return value


def validate_resolved_compose(config: dict[str, Any], manifest: dict[str, Any]) -> None:
    services = config.get("services") or {}
    expected = {
        "api": manifest["image"]["reference"],
        "maintenance": manifest["image"]["reference"],
        "proxy": manifest["components"]["proxy"]["reference"],
        "postgres": manifest["components"]["postgres"]["reference"],
        "redis": manifest["components"]["redis"]["reference"],
    }
    for service, reference in expected.items():
        actual = (services.get(service) or {}).get("image")
        if actual != reference:
            raise ReleaseError(
                f"Compose {service} image does not match manifest: {actual!r} != {reference!r}"
            )
    environment = (services.get("api") or {}).get("environment") or {}
    if environment.get("NUTRIPILOT_RELEASE") != manifest["release"]:
        raise ReleaseError("Compose release identifier does not match manifest")
    leaked = sorted(SENSITIVE_ENV_KEYS.intersection(environment))
    if leaked:
        raise ReleaseError(f"sensitive values must not be in Compose environment: {leaked}")


def inspect_id(runner: Runner, reference: str) -> str:
    values = json.loads(runner.run(["docker", "image", "inspect", reference]))
    return values[0]["Id"]


def ensure_images(
    runner: Runner, compose: list[str], manifest: dict[str, Any], *, local: bool
) -> None:
    if not local:
        runner.run([*compose, "pull", "api", "maintenance", "proxy", "postgres", "redis"])
    records = [manifest["image"], *manifest["components"].values()]
    for record in records:
        if inspect_id(runner, record["reference"]) != record["id"]:
            raise ReleaseError(f"local image ID does not match manifest: {record['reference']}")


def full_preflight(
    runner: Runner,
    compose: list[str],
    resolved: dict[str, Any],
    manifest: dict[str, Any],
    *,
    local: bool,
) -> None:
    topology = [
        *compose,
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "maintenance",
        "python",
        "-m",
        "app.cli.vps_topology",
    ]
    if local:
        topology.append("--local")
    runner.run(topology, input_text=json.dumps(resolved))
    runner.run(
        [
            *compose,
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "maintenance",
            "python",
            "-m",
            "app.cli.production_preflight",
            "--portfolio",
            "--behind-proxy",
            "--single-origin-web",
            "--vps",
        ]
    )
    proxy = (resolved.get("services") or {}).get("proxy") or {}
    environment = proxy.get("environment") or {}
    caddyfile = next(
        (
            volume.get("source")
            for volume in proxy.get("volumes") or []
            if volume.get("target") == "/etc/caddy/Caddyfile"
        ),
        None,
    )
    if not caddyfile:
        raise ReleaseError("resolved Compose config has no Caddyfile bind mount")
    runner.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/data",
            "--tmpfs",
            "/config",
            "--env",
            f"NUTRIPILOT_SITE_ADDRESS={environment.get('NUTRIPILOT_SITE_ADDRESS', '')}",
            "--env",
            f"NUTRIPILOT_API_UPSTREAM={environment.get('NUTRIPILOT_API_UPSTREAM', '')}",
            "--mount",
            f"type=bind,source={caddyfile},target=/etc/caddy/Caddyfile,readonly",
            manifest["components"]["proxy"]["reference"],
            "caddy",
            "validate",
            "--config",
            "/etc/caddy/Caddyfile",
        ]
    )


def query_schema(runner: Runner, compose: list[str]) -> str | None:
    exists = runner.run(
        [
            *compose,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "nutripilot",
            "-d",
            "nutripilot",
            "-At",
            "-c",
            "SELECT to_regclass('public.alembic_version')",
        ]
    )
    if not exists:
        return None
    value = runner.run(
        [
            *compose,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "nutripilot",
            "-d",
            "nutripilot",
            "-At",
            "-c",
            SCHEMA_QUERY,
        ]
    )
    revisions = [item.strip() for item in value.splitlines() if item.strip()]
    if len(revisions) != 1:
        raise ReleaseError(f"expected one database revision, got {revisions}")
    return revisions[0]


def validate_backup_receipt(path: Path, manifest: dict[str, Any]) -> None:
    receipt = load_json(path)
    if (
        receipt.get("formatVersion") != 1
        or receipt.get("database") != "nutripilot"
        or receipt.get("status") != "verified"
        or receipt.get("forRelease") != manifest["release"]
        or receipt.get("sourceRevision") != manifest["sourceRevision"]
    ):
        raise ReleaseError("backup receipt is not verified and bound to this release")
    artifact_value = receipt.get("artifact")
    expected_hash = receipt.get("sha256")
    if not isinstance(artifact_value, str) or not isinstance(expected_hash, str):
        raise ReleaseError("backup receipt has no artifact digest")
    artifact = Path(artifact_value)
    if not artifact.is_absolute():
        artifact = path.parent / artifact
    if not artifact.is_file() or file_sha256(artifact) != expected_hash:
        raise ReleaseError("backup artifact is missing or does not match its receipt")


def create_verified_backup(
    runner: Runner,
    compose: list[str],
    state_dir: Path,
    manifest: dict[str, Any],
) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = state_dir / "backups"
    artifact = backup_dir / f"{stamp}-{manifest['release']}.dump"
    receipt_path = artifact.with_suffix(".receipt.json")
    payload = runner.run_bytes(
        [
            *compose,
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            "nutripilot",
            "-d",
            "nutripilot",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
        ]
    )
    if len(payload) < 100:
        raise ReleaseError("database backup is unexpectedly small")
    listing = runner.run_bytes(
        [*compose, "exec", "-T", "postgres", "pg_restore", "--list"],
        input_bytes=payload,
    )
    if b"Archive created at" not in listing:
        raise ReleaseError("pg_restore could not verify the database backup")
    atomic_write_bytes(artifact, payload)
    atomic_write_json(
        receipt_path,
        {
            "formatVersion": 1,
            "database": "nutripilot",
            "status": "verified",
            "forRelease": manifest["release"],
            "sourceRevision": manifest["sourceRevision"],
            "createdAt": now_iso(),
            "artifact": artifact.name,
            "sha256": file_sha256(artifact),
            "sizeBytes": artifact.stat().st_size,
        },
    )
    emit("release.backup_verified", receipt=str(receipt_path))
    return receipt_path


def smoke(base_url: str) -> None:
    base = base_url.rstrip("/")
    if not (
        base.startswith("https://")
        or base.startswith("http://localhost:")
        or base.startswith("http://127.0.0.1:")
    ):
        raise ReleaseError("smoke URL must use HTTPS or loopback HTTP")
    headers: dict[str, str] = {}
    for path in [
        "/",
        "/auth",
        "/api/v1/health/live",
        "/api/v1/health/ready",
        "/api/v1/meta/config",
    ]:
        try:
            with urllib.request.urlopen(base + path, timeout=15) as response:
                if response.status != 200:
                    raise ReleaseError(f"smoke path returned {response.status}: {path}")
                if path == "/":
                    headers = {key.lower(): value for key, value in response.headers.items()}
        except (urllib.error.URLError, TimeoutError) as error:
            raise ReleaseError(f"smoke request failed: {path}") from error
    if headers.get("cross-origin-opener-policy") != "same-origin":
        raise ReleaseError("smoke response is missing COOP")
    if headers.get("cross-origin-embedder-policy") != "credentialless":
        raise ReleaseError("smoke response is missing COEP")


def state_paths(state_dir: Path) -> tuple[Path, Path]:
    return state_dir / "current.json", state_dir / "previous.json"


def promote(state_dir: Path, manifest: dict[str, Any], env_file: Path) -> None:
    current, previous = state_paths(state_dir)
    if current.exists():
        atomic_write_json(previous, load_json(current))
    deployed = dict(manifest)
    deployed["appliedAt"] = now_iso()
    deployed["environmentFileSha256"] = file_sha256(env_file)
    atomic_write_json(current, deployed)


def swap_for_rollback(state_dir: Path, env_file: Path) -> None:
    current, previous = state_paths(state_dir)
    current_value = load_json(current)
    previous_value = load_json(previous)
    previous_value["appliedAt"] = now_iso()
    previous_value["environmentFileSha256"] = file_sha256(env_file)
    atomic_write_json(current, previous_value)
    atomic_write_json(previous, current_value)


def run_apply(args: argparse.Namespace, runner: Runner) -> None:
    env_file = Path(args.env_file).resolve()
    manifest = load_json(Path(args.candidate).resolve())
    validate_manifest(manifest, local=args.local)
    state_dir = Path(args.state_dir).resolve()
    with ReleaseLock(state_dir):
        compose = compose_base(env_file)
        resolved = resolved_compose(runner, compose)
        validate_resolved_compose(resolved, manifest)
        emit("release.config_validated", release=manifest["release"])
        ensure_images(runner, compose, manifest, local=args.local)
        full_preflight(runner, compose, resolved, manifest, local=args.local)
        runner.run([*compose, "up", "-d", "--wait", "postgres", "redis"])
        if manifest.get("requiresBackup"):
            receipt = (
                Path(args.backup_receipt).resolve()
                if args.backup_receipt
                else create_verified_backup(runner, compose, state_dir, manifest)
            )
            validate_backup_receipt(receipt, manifest)
        schema_before = query_schema(runner, compose)
        emit("release.schema_before", revision=schema_before)
        runner.run([*compose, "stop", "proxy", "api"])
        emit("release.maintenance_window_started", release=manifest["release"])
        runner.run([*compose, "run", "--rm", "maintenance", "alembic", "upgrade", "head"])
        runner.run([*compose, "run", "--rm", "maintenance", "alembic", "check"])
        schema_after = query_schema(runner, compose)
        if schema_after != manifest["schema"]["target"]:
            raise ReleaseError(f"database revision {schema_after!r} does not match manifest target")
        runner.run([*compose, "up", "-d", "--wait", "api", "proxy"])
        smoke(args.smoke_url)
        promote(state_dir, manifest, env_file)
        emit(
            "release.applied",
            release=manifest["release"],
            schemaBefore=schema_before,
            schemaAfter=schema_after,
        )


def run_rollback(args: argparse.Namespace, runner: Runner) -> None:
    env_file = Path(args.env_file).resolve()
    state_dir = Path(args.state_dir).resolve()
    current_path, previous_path = state_paths(state_dir)
    with ReleaseLock(state_dir):
        target = load_json(previous_path)
        validate_manifest(target, local=args.local)
        compose = compose_base(env_file)
        resolved = resolved_compose(runner, compose)
        validate_resolved_compose(resolved, target)
        ensure_images(runner, compose, target, local=args.local)
        full_preflight(runner, compose, resolved, target, local=args.local)
        runner.run([*compose, "up", "-d", "--wait", "postgres", "redis"])
        revision = query_schema(runner, compose)
        if revision not in target["schema"]["compatible"]:
            raise ReleaseError(
                f"rollback image is incompatible with current schema {revision!r}; "
                "no services changed"
            )
        runner.run([*compose, "stop", "proxy", "api"])
        runner.run([*compose, "up", "-d", "--wait", "api", "proxy"])
        smoke(args.smoke_url)
        if not current_path.exists():
            raise ReleaseError("current release manifest disappeared during rollback")
        swap_for_rollback(state_dir, env_file)
        emit(
            "rollback.applied",
            release=target["release"],
            schema=revision,
            databaseDowngrade=False,
        )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subparsers = root.add_subparsers(dest="command", required=True)

    manifest = subparsers.add_parser("manifest", help="Create an immutable release manifest")
    manifest.add_argument("--release", required=True)
    manifest.add_argument("--source-revision", required=True)
    manifest.add_argument("--image", required=True)
    manifest.add_argument("--proxy-image", required=True)
    manifest.add_argument("--postgres-image", required=True)
    manifest.add_argument("--redis-image", required=True)
    manifest.add_argument("--schema", required=True)
    manifest.add_argument("--compatible-schema", action="append", default=[])
    manifest.add_argument("--requires-backup", action="store_true")
    manifest.add_argument("--local", action="store_true")
    manifest.add_argument("--output", required=True)

    for name in ["apply", "rollback"]:
        operation = subparsers.add_parser(name)
        operation.add_argument("--env-file", required=True)
        operation.add_argument("--state-dir", required=True)
        operation.add_argument("--smoke-url", required=True)
        operation.add_argument("--local", action="store_true")
        if name == "apply":
            operation.add_argument("--candidate", required=True)
            operation.add_argument("--backup-receipt")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    runner = Runner()
    try:
        if args.command == "manifest":
            create_manifest(args, runner)
        elif args.command == "apply":
            run_apply(args, runner)
        else:
            run_rollback(args, runner)
    except ReleaseError as error:
        emit("release.failed", error=str(error), command=args.command)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
