import hashlib
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from httpx2 import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.main import app
from app.models import Upload
from app.services.upload_storage import LocalPrivateUploadStore, UploadStorageError
from app.services.uploads import (
    UploadExpiredError,
    cleanup_expired_uploads,
    create_upload_token,
    verify_upload_token,
)


async def register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def image_bytes(
    format_name: str = "PNG",
    *,
    color: str = "red",
    size=(8, 6),
    metadata: bytes = b"test-private-metadata",
) -> bytes:
    output = io.BytesIO()
    image = Image.new("RGB", size, color)
    exif = Image.Exif()
    exif[0x010E] = metadata.decode("ascii")
    image.save(output, format=format_name, exif=exif)
    return output.getvalue()


def upload_settings(tmp_path: Path, **updates: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "sqlite+aiosqlite:///:memory:",
        "upload_root": tmp_path,
        "upload_signing_secret": "upload-test-signing-secret-at-least-32-bytes",
        "upload_max_bytes": 1024 * 1024,
        "upload_max_pixels": 1_000_000,
        "upload_url_ttl_minutes": 10,
        "upload_pending_ttl_minutes": 60,
        "upload_ready_ttl_minutes": 120,
    }
    values.update(updates)
    return Settings(**values)


async def presign(
    client: AsyncClient,
    headers: dict[str, str],
    content: bytes,
    content_type: str,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/uploads/presign",
        headers=headers,
        json={
            "content_type": content_type,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def put_signed(client: AsyncClient, contract: dict[str, object], content: bytes) -> object:
    parts = urlsplit(str(contract["upload_url"]))
    return await client.put(
        f"{parts.path}?{parts.query}",
        content=content,
        headers={"Content-Type": str(contract["required_content_type"])},
    )


@pytest.mark.asyncio
async def test_private_upload_is_verified_normalized_and_idempotent(
    api_client: AsyncClient,
    session_factory,
    tmp_path: Path,
) -> None:
    settings = upload_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    owner = await register(api_client, "upload-owner@example.com")
    other = await register(api_client, "upload-other@example.com")
    content = image_bytes()
    contract = await presign(api_client, owner, content, "image/png")
    async with session_factory() as session:
        upload = await session.scalar(select(Upload))
        assert upload is not None
        token = parse_qs(urlsplit(str(contract["upload_url"])).query)["token"][0]
        verify_upload_token(upload, token, settings.upload_signing_secret.get_secret_value())

    first_put = await put_signed(api_client, contract, content)
    second_put = await put_signed(api_client, contract, content)
    assert first_put.status_code == 204, first_put.text
    assert second_put.status_code == 204, second_put.text
    signed_path = urlsplit(str(contract["upload_url"])).path
    assert (await api_client.get(signed_path)).status_code == 405
    assert (
        await api_client.post(f"/api/v1/uploads/{contract['upload_id']}/complete", headers=other)
    ).status_code == 404

    complete_url = f"/api/v1/uploads/{contract['upload_id']}/complete"
    completed = await api_client.post(complete_url, headers=owner)
    replay = await api_client.post(complete_url, headers=owner)
    assert completed.status_code == replay.status_code == 200
    assert completed.json() == replay.json()
    assert completed.json()["status"] == "ready"
    assert completed.json()["sha256"] == hashlib.sha256(content).hexdigest()
    assert completed.json()["width"] == 8
    assert completed.json()["height"] == 6
    assert "object_key" not in completed.json()

    sealed_files = list((tmp_path / "sealed").rglob("*.png"))
    assert len(sealed_files) == 1
    with Image.open(sealed_files[0]) as normalized:
        assert normalized.format == "PNG"
        assert normalized.getexif() == {}
    assert not list((tmp_path / "staging").rglob("*.upload"))
    assert (await put_signed(api_client, contract, content)).status_code == 409
    assert (await api_client.get(complete_url, headers=owner)).status_code == 405


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("declared_type", "actual_format"),
    [("image/png", "JPEG"), ("image/jpeg", "WEBP")],
)
async def test_complete_rejects_spoofed_mime(
    api_client: AsyncClient,
    tmp_path: Path,
    declared_type: str,
    actual_format: str,
) -> None:
    app.dependency_overrides[get_settings] = lambda: upload_settings(tmp_path)
    owner = await register(api_client, f"mime-{actual_format.lower()}@example.com")
    content = image_bytes(actual_format)
    contract = await presign(api_client, owner, content, declared_type)
    assert (await put_signed(api_client, contract, content)).status_code == 204
    response = await api_client.post(
        f"/api/v1/uploads/{contract['upload_id']}/complete", headers=owner
    )
    assert response.status_code == 422
    assert not list((tmp_path / "sealed").rglob("*"))


@pytest.mark.asyncio
async def test_integrity_mismatch_is_failed_and_cannot_be_reused(
    api_client: AsyncClient,
    session_factory,
    tmp_path: Path,
) -> None:
    settings = upload_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    owner = await register(api_client, "tamper@example.com")
    expected = image_bytes(metadata=b"test-private-metadata")
    tampered = image_bytes(metadata=b"test-private-metadatb")
    assert len(expected) == len(tampered)
    contract = await presign(api_client, owner, expected, "image/png")
    assert (await put_signed(api_client, contract, tampered)).status_code == 204
    complete_url = f"/api/v1/uploads/{contract['upload_id']}/complete"
    assert (await api_client.post(complete_url, headers=owner)).status_code == 422
    assert (await api_client.post(complete_url, headers=owner)).status_code == 409
    async with session_factory() as session:
        upload = await session.scalar(select(Upload))
        assert upload is not None
        assert upload.status == "failed"
        assert upload.last_error_code == "integrity_mismatch"


@pytest.mark.asyncio
async def test_size_pixel_and_expired_credentials_are_rejected(
    api_client: AsyncClient,
    session_factory,
    tmp_path: Path,
) -> None:
    settings = upload_settings(tmp_path, upload_max_pixels=1_000_000)
    app.dependency_overrides[get_settings] = lambda: settings
    owner = await register(api_client, "limits@example.com")
    too_large = await api_client.post(
        "/api/v1/uploads/presign",
        headers=owner,
        json={
            "content_type": "image/png",
            "size": settings.upload_max_bytes + 1,
            "sha256": "a" * 64,
        },
    )
    assert too_large.status_code == 422

    content = image_bytes(size=(1001, 1000))
    contract = await presign(api_client, owner, content, "image/png")
    assert (await put_signed(api_client, contract, content)).status_code == 204
    assert (
        await api_client.post(f"/api/v1/uploads/{contract['upload_id']}/complete", headers=owner)
    ).status_code == 422

    async with session_factory() as session:
        upload = await session.scalar(
            select(Upload).where(Upload.id == UUID(str(contract["upload_id"])))
        )
        assert upload is not None
        upload.upload_url_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        expired_token = create_upload_token(
            upload.id,
            upload.object_key,
            upload.upload_url_expires_at,
            settings.upload_signing_secret.get_secret_value(),
        )
        with pytest.raises(UploadExpiredError, match="expired"):
            verify_upload_token(
                upload, expired_token, settings.upload_signing_secret.get_secret_value()
            )


@pytest.mark.asyncio
async def test_delete_failure_is_retryable_and_cross_user_is_hidden(
    api_client: AsyncClient,
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app.dependency_overrides[get_settings] = lambda: upload_settings(tmp_path)
    owner = await register(api_client, "delete-owner@example.com")
    other = await register(api_client, "delete-other@example.com")
    content = image_bytes()
    contract = await presign(api_client, owner, content, "image/png")
    assert (await put_signed(api_client, contract, content)).status_code == 204
    upload_url = f"/api/v1/uploads/{contract['upload_id']}"
    assert (await api_client.get(upload_url, headers=other)).status_code == 404

    original_delete = LocalPrivateUploadStore.delete

    async def fail_delete(_self, _key) -> None:
        raise UploadStorageError("injected deletion failure")

    monkeypatch.setattr(LocalPrivateUploadStore, "delete", fail_delete)
    assert (await api_client.delete(upload_url, headers=owner)).status_code == 503
    async with session_factory() as session:
        upload = await session.scalar(select(Upload))
        assert upload is not None
        assert upload.status == "delete_pending"
        assert upload.delete_attempt_count == 1

    monkeypatch.setattr(LocalPrivateUploadStore, "delete", original_delete)
    assert (await api_client.delete(upload_url, headers=owner)).status_code == 204
    assert (await api_client.delete(upload_url, headers=owner)).status_code == 204
    response = await api_client.get(upload_url, headers=owner)
    assert response.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_expired_upload_cleanup_retries_and_keeps_tombstone(
    api_client: AsyncClient,
    session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = upload_settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: settings
    owner = await register(api_client, "cleanup@example.com")
    content = image_bytes()
    contract = await presign(api_client, owner, content, "image/png")
    assert (await put_signed(api_client, contract, content)).status_code == 204
    upload_id = UUID(str(contract["upload_id"]))
    async with session_factory() as session:
        upload = await session.get(Upload, upload_id)
        assert upload is not None
        upload.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    original_delete = LocalPrivateUploadStore.delete

    async def fail_delete(_self, _key) -> None:
        raise UploadStorageError("injected cleanup failure")

    monkeypatch.setattr(LocalPrivateUploadStore, "delete", fail_delete)
    async with session_factory() as session:
        result = await cleanup_expired_uploads(
            session, LocalPrivateUploadStore(tmp_path), now=datetime.now(UTC)
        )
    assert result.selected == result.failed == 1

    monkeypatch.setattr(LocalPrivateUploadStore, "delete", original_delete)
    async with session_factory() as session:
        result = await cleanup_expired_uploads(
            session, LocalPrivateUploadStore(tmp_path), now=datetime.now(UTC)
        )
        upload = await session.get(Upload, upload_id)
        assert upload is not None
        assert upload.status == "deleted"
        assert upload.delete_attempt_count == 2
        assert upload.deleted_at is not None
    assert result.selected == result.deleted == 1
    assert not list((tmp_path / "staging").rglob("*.upload"))
