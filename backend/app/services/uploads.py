import base64
import binascii
import hashlib
import hmac
import io
import json
import logging
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisJob, Upload
from app.schemas.uploads import UploadPresignRequest
from app.services.upload_storage import (
    LocalPrivateUploadStore,
    UploadObjectNotFoundError,
    UploadStorageError,
)

SUPPORTED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
logger = logging.getLogger("nutripilot.uploads")


class UploadNotFoundError(ValueError):
    pass


class UploadConflictError(ValueError):
    pass


class UploadExpiredError(ValueError):
    pass


class UploadValidationError(ValueError):
    pass


class UploadCapacityError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedImage:
    raw_size: int
    raw_sha256: str
    width: int
    height: int
    normalized: bytes


@dataclass(frozen=True)
class UploadCleanupResult:
    selected: int
    deleted: int
    failed: int


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _token_payload(upload_id: UUID, object_key: str, expires_at: datetime) -> bytes:
    return json.dumps(
        {"id": str(upload_id), "key": object_key, "exp": int(_aware(expires_at).timestamp())},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def create_upload_token(upload_id: UUID, object_key: str, expires_at: datetime, secret: str) -> str:
    payload = _token_payload(upload_id, object_key, expires_at)
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + signature).rstrip(b"=").decode()


def verify_upload_token(
    upload: Upload, token: str, secret: str, now: datetime | None = None
) -> None:
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode())
        payload, supplied_signature = decoded[:-32], decoded[-32:]
        expected_signature = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
        claims = json.loads(payload)
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise UploadValidationError("invalid upload credential") from error
    if len(decoded) <= 32 or not hmac.compare_digest(supplied_signature, expected_signature):
        raise UploadValidationError("invalid upload credential")
    if claims.get("id") != str(upload.id) or claims.get("key") != upload.object_key:
        raise UploadValidationError("invalid upload credential")
    try:
        token_expiry = datetime.fromtimestamp(int(claims["exp"]), UTC)
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise UploadValidationError("invalid upload credential") from error
    database_expiry = _aware(upload.upload_url_expires_at)
    current_time = now or datetime.now(UTC)
    if token_expiry > database_expiry + timedelta(seconds=1):
        raise UploadValidationError("invalid upload credential")
    if token_expiry <= current_time or database_expiry <= current_time:
        raise UploadExpiredError("upload credential expired")


def verify_and_normalize_image(
    content: bytes, declared_content_type: str, max_bytes: int, max_pixels: int
) -> VerifiedImage:
    if not content or len(content) > max_bytes:
        raise UploadValidationError("image size is outside the allowed range")
    digest = hashlib.sha256(content).hexdigest()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                actual_content_type = SUPPORTED_FORMATS.get(source.format or "")
                if actual_content_type is None or actual_content_type != declared_content_type:
                    raise UploadValidationError("image content does not match its declared type")
                if getattr(source, "is_animated", False):
                    raise UploadValidationError("animated images are not supported")
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > max_pixels:
                    raise UploadValidationError("image dimensions exceed the allowed limit")
                source.verify()
            with Image.open(io.BytesIO(content)) as source:
                normalized_image = ImageOps.exif_transpose(source)
                normalized_image.load()
                if normalized_image.mode not in {"RGB", "RGBA"}:
                    normalized_image = normalized_image.convert(
                        "RGBA" if "transparency" in source.info else "RGB"
                    )
                output = io.BytesIO()
                normalized_image.save(output, format="PNG", optimize=True)
    except UploadValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
    ) as error:
        raise UploadValidationError("image could not be safely decoded") from error
    return VerifiedImage(len(content), digest, width, height, output.getvalue())


async def create_upload(
    session: AsyncSession,
    user_id: UUID,
    request: UploadPresignRequest,
    *,
    max_bytes: int,
    max_pending_per_user: int,
    upload_url_ttl_minutes: int,
    pending_ttl_minutes: int,
) -> Upload:
    if request.size > max_bytes:
        raise UploadValidationError("declared image size exceeds the allowed limit")
    pending = await session.scalar(
        select(func.count())
        .select_from(Upload)
        .where(Upload.user_id == user_id, Upload.status.in_(("pending", "delete_pending")))
    )
    if (pending or 0) >= max_pending_per_user:
        raise UploadCapacityError("too many pending uploads")
    now = datetime.now(UTC)
    upload_id = uuid4()
    upload = Upload(
        id=upload_id,
        user_id=user_id,
        object_key=f"staging/{user_id}/{upload_id}/{uuid4().hex}.upload",
        status="pending",
        declared_size=request.size,
        declared_sha256=request.sha256,
        content_type=request.content_type,
        upload_url_expires_at=now + timedelta(minutes=upload_url_ttl_minutes),
        expires_at=now + timedelta(minutes=pending_ttl_minutes),
    )
    session.add(upload)
    await session.commit()
    await session.refresh(upload)
    return upload


async def get_upload(session: AsyncSession, upload_id: UUID) -> Upload | None:
    return await session.get(Upload, upload_id)


async def get_owned_upload(session: AsyncSession, user_id: UUID, upload_id: UUID) -> Upload | None:
    return await session.scalar(
        select(Upload).where(Upload.id == upload_id, Upload.user_id == user_id)
    )


async def store_staging_content(
    session: AsyncSession,
    store: LocalPrivateUploadStore,
    upload_id: UUID,
    token: str,
    content: bytes,
    content_type: str | None,
    *,
    signing_secret: str,
    max_bytes: int,
) -> None:
    upload = await get_upload(session, upload_id)
    if upload is None:
        raise UploadNotFoundError("upload not found")
    verify_upload_token(upload, token, signing_secret)
    if upload.status != "pending":
        raise UploadConflictError("upload no longer accepts content")
    if content_type != upload.content_type:
        raise UploadValidationError("content type does not match the upload contract")
    if len(content) != upload.declared_size or len(content) > max_bytes:
        raise UploadValidationError("content length does not match the upload contract")
    await store.write_staging(upload.object_key, content)


async def complete_upload(
    session: AsyncSession,
    store: LocalPrivateUploadStore,
    user_id: UUID,
    upload_id: UUID,
    *,
    max_bytes: int,
    max_pixels: int,
    ready_ttl_minutes: int,
) -> Upload:
    upload = await get_owned_upload(session, user_id, upload_id)
    if upload is None:
        raise UploadNotFoundError("upload not found")
    if upload.status == "ready":
        return upload
    if upload.status != "pending":
        raise UploadConflictError("upload cannot be completed")
    if _aware(upload.expires_at) <= datetime.now(UTC):
        raise UploadExpiredError("upload expired")
    try:
        content = await store.read(upload.object_key)
    except UploadObjectNotFoundError as error:
        raise UploadConflictError("uploaded content is not available") from error
    verified = verify_and_normalize_image(content, upload.content_type, max_bytes, max_pixels)
    if verified.raw_size != upload.declared_size or verified.raw_sha256 != upload.declared_sha256:
        upload.status = "failed"
        upload.last_error_code = "integrity_mismatch"
        await session.commit()
        raise UploadValidationError("uploaded content failed integrity verification")
    sealed_key = f"sealed/{user_id}/{upload.id}/{verified.raw_sha256}.png"
    try:
        await store.seal(sealed_key, verified.normalized)
        upload.status = "ready"
        upload.verified_size = verified.raw_size
        upload.sha256 = verified.raw_sha256
        upload.width = verified.width
        upload.height = verified.height
        upload.sealed_object_key = sealed_key
        upload.sealed_object_version = hashlib.sha256(verified.normalized).hexdigest()
        upload.content_type = "image/png"
        upload.expires_at = datetime.now(UTC) + timedelta(minutes=ready_ttl_minutes)
        upload.last_error_code = None
        await session.commit()
        await session.refresh(upload)
    except Exception:
        await session.rollback()
        await store.delete(sealed_key)
        raise
    await store.delete(upload.object_key)
    return upload


async def delete_upload(
    session: AsyncSession,
    store: LocalPrivateUploadStore,
    user_id: UUID,
    upload_id: UUID,
) -> None:
    upload = await get_owned_upload(session, user_id, upload_id)
    if upload is None:
        raise UploadNotFoundError("upload not found")
    if upload.status == "deleted":
        return
    active_analysis = await session.scalar(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.upload_id == upload.id,
            AnalysisJob.status.in_(("queued", "running", "retry_wait")),
        )
    )
    if active_analysis:
        raise UploadConflictError("upload is in use by an active analysis")
    upload.status = "delete_pending"
    upload.delete_attempt_count += 1
    upload.last_error_code = None
    await session.commit()
    try:
        await store.delete(upload.object_key)
        await store.delete(upload.sealed_object_key)
    except UploadStorageError:
        upload.last_error_code = "object_delete_failed"
        await session.commit()
        raise
    upload.status = "deleted"
    upload.deleted_at = datetime.now(UTC)
    await session.commit()


async def cleanup_expired_uploads(
    session: AsyncSession,
    store: LocalPrivateUploadStore,
    *,
    limit: int = 100,
    now: datetime | None = None,
) -> UploadCleanupResult:
    """Delete expired private objects while retaining an auditable tombstone."""

    current_time = now or datetime.now(UTC)
    candidates = list(
        (
            await session.scalars(
                select(Upload)
                .where(
                    or_(
                        Upload.status == "delete_pending",
                        and_(
                            Upload.status.in_(("pending", "ready", "failed")),
                            Upload.expires_at <= current_time,
                        ),
                    ),
                    ~exists(
                        select(AnalysisJob.id).where(
                            AnalysisJob.upload_id == Upload.id,
                            AnalysisJob.status.in_(("queued", "running", "retry_wait")),
                        )
                    ),
                )
                .order_by(Upload.expires_at, Upload.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    deleted = 0
    failed = 0
    for upload in candidates:
        upload.status = "delete_pending"
        upload.delete_attempt_count += 1
        upload.last_error_code = None
        await session.commit()
        try:
            await store.delete(upload.object_key)
            await store.delete(upload.sealed_object_key)
        except UploadStorageError:
            failed += 1
            upload.last_error_code = "object_delete_failed"
            await session.commit()
            logger.exception("upload_cleanup_delete_failed upload_id=%s", upload.id)
            continue
        deleted += 1
        upload.status = "deleted"
        upload.deleted_at = current_time
        await session.commit()
        logger.info("upload_cleanup_deleted upload_id=%s", upload.id)
    return UploadCleanupResult(selected=len(candidates), deleted=deleted, failed=failed)
