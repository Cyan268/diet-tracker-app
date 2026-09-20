import hashlib
import io
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import pytest
from httpx2 import AsyncClient
from PIL import Image

from app.core.config import Settings, get_settings
from app.main import app
from app.models import AnalysisJob


async def register(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (12, 8), "green").save(output, format="PNG")
    return output.getvalue()


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        upload_root=tmp_path,
        upload_signing_secret="upload-test-signing-secret-at-least-32-bytes",
        credential_encryption_key="credential-test-key-that-is-at-least-32-bytes",
    )


async def create_ready_upload(client: AsyncClient, headers: dict[str, str], content: bytes) -> str:
    contract_response = await client.post(
        "/api/v1/uploads/presign",
        headers=headers,
        json={
            "content_type": "image/png",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    )
    assert contract_response.status_code == 201
    contract = contract_response.json()
    target = urlsplit(contract["upload_url"])
    put = await client.put(
        f"{target.path}?{target.query}",
        content=content,
        headers={"Content-Type": "image/png"},
    )
    assert put.status_code == 204
    complete = await client.post(
        f"/api/v1/uploads/{contract['upload_id']}/complete", headers=headers
    )
    assert complete.status_code == 200
    return contract["upload_id"]


def image_analysis_payload(upload_id: str, request_id: UUID | None = None) -> dict[str, object]:
    return {
        "client_request_id": str(request_id or uuid4()),
        "upload_id": upload_id,
        "log_date": "2026-09-16",
        "meal_type_hint": "lunch",
        "locale": "zh-CN",
        "consent_to_provider": True,
    }


@pytest.mark.asyncio
async def test_image_analysis_requires_consent_credential_and_owned_ready_upload(
    api_client: AsyncClient,
    session_factory,
    tmp_path: Path,
) -> None:
    test_settings = settings(tmp_path)
    app.dependency_overrides[get_settings] = lambda: test_settings
    owner = await register(api_client, "image-owner@example.com")
    other = await register(api_client, "image-other@example.com")
    content = png_bytes()
    upload_id = await create_ready_upload(api_client, owner, content)

    no_credential = await api_client.post(
        "/api/v1/ai/image-analyses",
        headers=owner,
        json=image_analysis_payload(upload_id),
    )
    assert no_credential.status_code == 409

    credential = await api_client.put(
        "/api/v1/ai/credentials",
        headers=owner,
        json={"api_key": "sk-test-image-provider-key-123456"},
    )
    assert credential.status_code == 200
    no_consent = image_analysis_payload(upload_id)
    no_consent["consent_to_provider"] = False
    assert (
        await api_client.post("/api/v1/ai/image-analyses", headers=owner, json=no_consent)
    ).status_code == 422
    assert (
        await api_client.post(
            "/api/v1/ai/image-analyses",
            headers=other,
            json=image_analysis_payload(upload_id),
        )
    ).status_code == 409

    other_credential = await api_client.put(
        "/api/v1/ai/credentials",
        headers=other,
        json={"api_key": "sk-test-other-provider-key-123456"},
    )
    assert other_credential.status_code == 200
    cross_user = await api_client.post(
        "/api/v1/ai/image-analyses",
        headers=other,
        json=image_analysis_payload(upload_id),
    )
    assert cross_user.status_code == 404

    request_id = uuid4()
    payload = image_analysis_payload(upload_id, request_id)
    created = await api_client.post("/api/v1/ai/image-analyses", headers=owner, json=payload)
    replay = await api_client.post("/api/v1/ai/image-analyses", headers=owner, json=payload)
    assert created.status_code == 202
    assert replay.status_code == 200
    assert replay.json()["job_id"] == created.json()["job_id"]

    async with session_factory() as session:
        job = await session.get(AnalysisJob, UUID(created.json()["job_id"]))
        assert job is not None
        assert job.input_type == "image"
        assert str(job.upload_id) == upload_id
        assert job.provider == "openai_image_responses"
        assert content not in job.input_ciphertext
        assert b"sealed/" not in job.input_ciphertext

    delete = await api_client.delete(f"/api/v1/uploads/{upload_id}", headers=owner)
    assert delete.status_code == 409


@pytest.mark.asyncio
async def test_image_analysis_rejects_pending_upload(
    api_client: AsyncClient,
    tmp_path: Path,
) -> None:
    app.dependency_overrides[get_settings] = lambda: settings(tmp_path)
    owner = await register(api_client, "image-pending@example.com")
    assert (
        await api_client.put(
            "/api/v1/ai/credentials",
            headers=owner,
            json={"api_key": "sk-test-pending-provider-key-123456"},
        )
    ).status_code == 200
    content = png_bytes()
    contract = await api_client.post(
        "/api/v1/uploads/presign",
        headers=owner,
        json={
            "content_type": "image/png",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    )
    response = await api_client.post(
        "/api/v1/ai/image-analyses",
        headers=owner,
        json=image_analysis_payload(contract.json()["upload_id"]),
    )
    assert response.status_code == 409
