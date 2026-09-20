from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status

from app.api.dependencies import CurrentUserDep, DemoGuardDep, SessionDep, SettingsDep
from app.schemas.uploads import UploadPresignRequest, UploadPresignResponse, UploadResponse
from app.services.upload_storage import LocalPrivateUploadStore, UploadStorageError
from app.services.uploads import (
    UploadCapacityError,
    UploadConflictError,
    UploadExpiredError,
    UploadNotFoundError,
    UploadValidationError,
    complete_upload,
    create_upload,
    create_upload_token,
    delete_upload,
    get_owned_upload,
    store_staging_content,
)

router = APIRouter()


def _store(settings: SettingsDep) -> LocalPrivateUploadStore:
    return LocalPrivateUploadStore(settings.upload_root)


def _translate(error: Exception) -> HTTPException:
    if isinstance(error, UploadNotFoundError):
        return HTTPException(status_code=404, detail="upload not found")
    if isinstance(error, UploadExpiredError):
        return HTTPException(status_code=410, detail=str(error))
    if isinstance(error, UploadConflictError):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, UploadCapacityError):
        return HTTPException(status_code=429, detail=str(error))
    if isinstance(error, UploadValidationError):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=503, detail="upload storage is temporarily unavailable")


@router.post(
    "/presign",
    response_model=UploadPresignResponse,
    status_code=status.HTTP_201_CREATED,
)
async def presign_upload(
    payload: UploadPresignRequest,
    request: Request,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    demo_guard: DemoGuardDep,
) -> UploadPresignResponse:
    await demo_guard.enforce_rate(current_user, "write")
    try:
        upload = await create_upload(
            session,
            current_user.id,
            payload,
            max_bytes=settings.upload_max_bytes,
            max_pending_per_user=settings.upload_max_pending_per_user,
            upload_url_ttl_minutes=settings.upload_url_ttl_minutes,
            pending_ttl_minutes=settings.upload_pending_ttl_minutes,
        )
    except (UploadCapacityError, UploadValidationError) as error:
        raise _translate(error) from error
    token = create_upload_token(
        upload.id,
        upload.object_key,
        upload.upload_url_expires_at,
        settings.upload_signing_secret.get_secret_value(),
    )
    base_url = str(request.url_for("put_upload_content", upload_id=str(upload.id)))
    return UploadPresignResponse(
        upload_id=upload.id,
        status="pending",
        upload_url=f"{base_url}?{urlencode({'token': token})}",
        required_content_type=payload.content_type,
        required_size=payload.size,
        upload_url_expires_at=upload.upload_url_expires_at,
        upload_expires_at=upload.expires_at,
    )


@router.put("/{upload_id}/content", status_code=status.HTTP_204_NO_CONTENT)
async def put_upload_content(
    upload_id: UUID,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    token: Annotated[str, Query(min_length=40, max_length=2000)],
    content_type: Annotated[str | None, Header(alias="Content-Type")] = None,
    content_length: Annotated[int | None, Header(alias="Content-Length", ge=0)] = None,
) -> Response:
    if content_length is not None and content_length > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="image is too large")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > settings.upload_max_bytes:
            raise HTTPException(status_code=413, detail="image is too large")
    try:
        await store_staging_content(
            session,
            _store(settings),
            upload_id,
            token,
            bytes(body),
            content_type,
            signing_secret=settings.upload_signing_secret.get_secret_value(),
            max_bytes=settings.upload_max_bytes,
        )
    except (
        UploadNotFoundError,
        UploadExpiredError,
        UploadConflictError,
        UploadValidationError,
        UploadStorageError,
    ) as error:
        raise _translate(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{upload_id}", response_model=UploadResponse)
async def read_upload(
    upload_id: UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> UploadResponse:
    upload = await get_owned_upload(session, current_user.id, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="upload not found")
    return UploadResponse.model_validate(upload)


@router.post("/{upload_id}/complete", response_model=UploadResponse)
async def finish_upload(
    upload_id: UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    demo_guard: DemoGuardDep,
) -> UploadResponse:
    await demo_guard.enforce_rate(current_user, "write")
    try:
        upload = await complete_upload(
            session,
            _store(settings),
            current_user.id,
            upload_id,
            max_bytes=settings.upload_max_bytes,
            max_pixels=settings.upload_max_pixels,
            ready_ttl_minutes=settings.upload_ready_ttl_minutes,
        )
    except (
        UploadNotFoundError,
        UploadExpiredError,
        UploadConflictError,
        UploadValidationError,
        UploadStorageError,
    ) as error:
        raise _translate(error) from error
    return UploadResponse.model_validate(upload)


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_upload(
    upload_id: UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    demo_guard: DemoGuardDep,
) -> Response:
    await demo_guard.enforce_rate(current_user, "write")
    try:
        await delete_upload(session, _store(settings), current_user.id, upload_id)
    except (UploadNotFoundError, UploadConflictError, UploadStorageError) as error:
        raise _translate(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
