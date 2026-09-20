import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import RuleBasedFoodTextProvider
from app.ai.openai_image_responses import FOOD_IMAGE_PROMPT_VERSION
from app.ai.openai_responses import FOOD_TEXT_PROMPT_VERSION
from app.models import (
    AnalysisConfirmation,
    AnalysisCorrection,
    AnalysisDraft,
    AnalysisEntity,
    AnalysisJob,
    Upload,
)
from app.repositories.diet import get_visible_food
from app.schemas.ai import FoodTextAnalyzeRequest
from app.schemas.analysis import (
    AnalysisConfirmationResponse,
    AnalysisConfirmRequest,
    AnalysisCreateRequest,
    AnalysisDraftEntityResponse,
    AnalysisDraftResponse,
    AnalysisDraftUpdateRequest,
    AnalysisImageCreateRequest,
    AnalysisImageWorkerRequest,
)
from app.schemas.diet import FoodMatchCandidateResponse, LogCreateRequest, LogResponse
from app.services.analysis_input_encryption import encrypt_analysis_input
from app.services.diet import (
    IdempotencyConflictError,
    InvalidLogContentError,
    create_log_in_transaction,
)


class AnalysisNotFoundError(ValueError):
    pass


class AnalysisConflictError(ValueError):
    pass


class AnalysisValidationError(ValueError):
    pass


class AnalysisCapacityError(ValueError):
    pass


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


async def create_analysis_job(
    session: AsyncSession,
    *,
    user_id: UUID,
    request: AnalysisCreateRequest,
    master_secret: str,
    use_openai: bool,
    openai_model: str,
    input_ttl_minutes: int,
    max_pending_per_user: int,
) -> tuple[AnalysisJob, bool]:
    request_hash = _canonical_hash(request.model_dump(mode="json"))
    existing = await session.scalar(
        select(AnalysisJob).where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.client_request_id == request.client_request_id,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AnalysisConflictError("client_request_id was reused with different content")
        return existing, False

    pending = await session.scalar(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.status.in_(("queued", "running", "retry_wait")),
        )
    )
    if (pending or 0) >= max_pending_per_user:
        raise AnalysisCapacityError("too many pending analyses")

    job_id = uuid4()
    provider = "openai_responses" if use_openai else RuleBasedFoodTextProvider.name
    model = openai_model if use_openai else RuleBasedFoodTextProvider.model
    prompt_version = (
        FOOD_TEXT_PROMPT_VERSION if use_openai else RuleBasedFoodTextProvider.prompt_version
    )
    worker_request = FoodTextAnalyzeRequest.model_validate(
        request.model_dump(exclude={"client_request_id"})
    )
    job = AnalysisJob(
        id=job_id,
        user_id=user_id,
        client_request_id=request.client_request_id,
        request_hash=request_hash,
        input_type="text",
        input_ciphertext=encrypt_analysis_input(
            worker_request.model_dump(mode="json"),
            user_id,
            job_id,
            master_secret,
        ),
        input_key_version=1,
        input_expires_at=datetime.now(UTC) + timedelta(minutes=input_ttl_minutes),
        status="queued",
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        result_schema_version="draft-v1",
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        existing = await session.scalar(
            select(AnalysisJob).where(
                AnalysisJob.user_id == user_id,
                AnalysisJob.client_request_id == request.client_request_id,
            )
        )
        if existing is None or existing.request_hash != request_hash:
            raise AnalysisConflictError(
                "client_request_id was reused with different content"
            ) from error
        return existing, False
    await session.refresh(job)
    return job, True


async def create_image_analysis_job(
    session: AsyncSession,
    *,
    user_id: UUID,
    request: AnalysisImageCreateRequest,
    master_secret: str,
    openai_model: str,
    input_ttl_minutes: int,
    max_pending_per_user: int,
) -> tuple[AnalysisJob, bool]:
    request_hash = _canonical_hash(request.model_dump(mode="json"))
    existing = await session.scalar(
        select(AnalysisJob).where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.client_request_id == request.client_request_id,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise AnalysisConflictError("client_request_id was reused with different content")
        return existing, False

    upload = await session.scalar(
        select(Upload).where(Upload.id == request.upload_id, Upload.user_id == user_id)
    )
    if upload is None:
        raise AnalysisNotFoundError("upload not found")
    if (
        upload.status != "ready"
        or upload.sealed_object_key is None
        or _is_expired(upload.expires_at)
    ):
        raise AnalysisConflictError("upload is not ready for analysis")

    pending = await session.scalar(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.user_id == user_id,
            AnalysisJob.status.in_(("queued", "running", "retry_wait")),
        )
    )
    if (pending or 0) >= max_pending_per_user:
        raise AnalysisCapacityError("too many pending analyses")

    now = datetime.now(UTC)
    job_id = uuid4()
    worker_request = AnalysisImageWorkerRequest(
        upload_id=request.upload_id,
        log_date=request.log_date,
        meal_type_hint=request.meal_type_hint,
        locale=request.locale,
    )
    job = AnalysisJob(
        id=job_id,
        user_id=user_id,
        upload_id=upload.id,
        client_request_id=request.client_request_id,
        request_hash=request_hash,
        input_type="image",
        input_ciphertext=encrypt_analysis_input(
            worker_request.model_dump(mode="json"),
            user_id,
            job_id,
            master_secret,
        ),
        input_key_version=1,
        input_expires_at=now + timedelta(minutes=input_ttl_minutes),
        status="queued",
        provider="openai_image_responses",
        model=openai_model,
        prompt_version=FOOD_IMAGE_PROMPT_VERSION,
        result_schema_version="draft-v1",
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        existing = await session.scalar(
            select(AnalysisJob).where(
                AnalysisJob.user_id == user_id,
                AnalysisJob.client_request_id == request.client_request_id,
            )
        )
        if existing is None or existing.request_hash != request_hash:
            raise AnalysisConflictError(
                "client_request_id was reused with different content"
            ) from error
        return existing, False
    await session.refresh(job)
    return job, True


async def get_owned_job(session: AsyncSession, user_id: UUID, job_id: UUID) -> AnalysisJob | None:
    return await session.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job_id, AnalysisJob.user_id == user_id)
    )


async def get_job_draft_id(session: AsyncSession, job_id: UUID) -> UUID | None:
    return await session.scalar(select(AnalysisDraft.id).where(AnalysisDraft.job_id == job_id))


async def _draft_entities(session: AsyncSession, draft_id: UUID) -> list[AnalysisEntity]:
    return list(
        (
            await session.scalars(
                select(AnalysisEntity)
                .where(AnalysisEntity.draft_id == draft_id)
                .order_by(AnalysisEntity.position, AnalysisEntity.id)
            )
        ).all()
    )


async def get_owned_draft(
    session: AsyncSession,
    user_id: UUID,
    draft_id: UUID,
    *,
    for_update: bool = False,
) -> AnalysisDraft | None:
    statement = select(AnalysisDraft).where(
        AnalysisDraft.id == draft_id, AnalysisDraft.user_id == user_id
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def draft_response(session: AsyncSession, draft: AnalysisDraft) -> AnalysisDraftResponse:
    entities = await _draft_entities(session, draft.id)
    return AnalysisDraftResponse(
        id=draft.id,
        job_id=draft.job_id,
        status=draft.status,
        version=draft.version,
        log_date=draft.log_date,
        result_schema_version=draft.result_schema_version,
        expires_at=draft.expires_at,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
        entities=[
            AnalysisDraftEntityResponse(
                id=entity.id,
                position=entity.position,
                raw_name=entity.raw_name,
                normalized_name=entity.normalized_name,
                amount=float(entity.amount),
                unit=entity.unit,
                meal_type=entity.meal_type,
                confidence=(float(entity.confidence) if entity.confidence is not None else None),
                needs_review=entity.needs_review,
                matched_food_id=entity.matched_food_id,
                catalog_revision=entity.catalog_revision,
                candidates=[
                    FoodMatchCandidateResponse.model_validate(candidate)
                    for candidate in entity.candidates
                ],
            )
            for entity in entities
        ],
    )


async def update_analysis_draft(
    session: AsyncSession,
    *,
    user_id: UUID,
    draft_id: UUID,
    request: AnalysisDraftUpdateRequest,
) -> AnalysisDraft:
    draft = await get_owned_draft(session, user_id, draft_id, for_update=True)
    if draft is None:
        raise AnalysisNotFoundError
    if draft.status != "review":
        raise AnalysisConflictError("draft is no longer editable")
    if _is_expired(draft.expires_at):
        draft.status = "expired"
        await session.commit()
        raise AnalysisConflictError("draft has expired")
    if draft.version != request.expected_version:
        raise AnalysisConflictError("draft version conflict")

    entities = await _draft_entities(session, draft.id)
    by_id = {entity.id: entity for entity in entities}
    requested_ids = [item.entity_id for item in request.entities]
    if len(set(requested_ids)) != len(requested_ids) or set(requested_ids) != set(by_id):
        raise AnalysisValidationError("draft update must include each entity exactly once")

    for item in request.entities:
        entity = by_id[item.entity_id]
        if item.matched_food_id is not None:
            food = await get_visible_food(session, item.matched_food_id, user_id)
            if food is None:
                raise AnalysisNotFoundError
            if food.current_revision != item.catalog_revision:
                raise AnalysisConflictError("food catalog revision changed")
        entity.normalized_name = item.normalized_name
        entity.amount = item.amount
        entity.unit = item.unit
        entity.meal_type = item.meal_type.value
        entity.matched_food_id = item.matched_food_id
        entity.catalog_revision = item.catalog_revision
        entity.needs_review = item.matched_food_id is None
    draft.log_date = request.log_date
    draft.version += 1
    draft.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(draft)
    return draft


def _confirmation_response(confirmation: AnalysisConfirmation) -> AnalysisConfirmationResponse:
    return AnalysisConfirmationResponse(
        confirmation_id=confirmation.id,
        draft_id=confirmation.draft_id,
        confirmed_draft_version=confirmation.confirmed_draft_version,
        created_at=confirmation.created_at,
        log_identities=confirmation.log_ids,
        logs=[LogResponse.model_validate(log) for log in confirmation.result_snapshot["logs"]],
    )


def _add_correction(
    session: AsyncSession,
    confirmation_id: UUID,
    entity_id: UUID | None,
    field_name: str,
    before: object | None,
    after: object | None,
) -> None:
    session.add(
        AnalysisCorrection(
            confirmation_id=confirmation_id,
            entity_id=entity_id,
            field_name=field_name,
            before_value=before,
            after_value=after,
        )
    )


async def confirm_analysis_draft(
    session: AsyncSession,
    *,
    user_id: UUID,
    draft_id: UUID,
    request: AnalysisConfirmRequest,
) -> tuple[AnalysisConfirmationResponse, bool]:
    request_hash = _canonical_hash(request.model_dump(mode="json"))
    existing = await session.scalar(
        select(AnalysisConfirmation).where(
            AnalysisConfirmation.user_id == user_id,
            AnalysisConfirmation.client_confirmation_id == request.client_confirmation_id,
        )
    )
    if existing is not None:
        if existing.draft_id != draft_id or existing.request_hash != request_hash:
            raise AnalysisConflictError("client_confirmation_id was reused with different content")
        return _confirmation_response(existing), False

    draft = await get_owned_draft(session, user_id, draft_id, for_update=True)
    if draft is None:
        raise AnalysisNotFoundError
    existing = await session.scalar(
        select(AnalysisConfirmation).where(AnalysisConfirmation.draft_id == draft.id)
    )
    if existing is not None:
        if (
            existing.client_confirmation_id == request.client_confirmation_id
            and existing.request_hash == request_hash
        ):
            return _confirmation_response(existing), False
        raise AnalysisConflictError("draft was already confirmed")
    if draft.status == "confirmed":
        raise AnalysisConflictError("draft was already confirmed")
    if draft.status != "review":
        raise AnalysisConflictError("draft is no longer confirmable")
    if _is_expired(draft.expires_at):
        draft.status = "expired"
        await session.commit()
        raise AnalysisConflictError("draft has expired")
    if draft.version != request.expected_draft_version:
        raise AnalysisConflictError("draft version conflict")

    source_entities = await _draft_entities(session, draft.id)
    source_by_id = {entity.id: entity for entity in source_entities}
    source_ids = [item.source_entity_id for item in request.entities if item.source_entity_id]
    if len(set(source_ids)) != len(source_ids) or not set(source_ids) <= set(source_by_id):
        raise AnalysisValidationError("confirmation contains an invalid source entity")
    client_ids = [item.client_id for item in request.entities]
    if len(set(client_ids)) != len(client_ids):
        raise AnalysisValidationError("confirmation client_id values must be unique")

    confirmation = AnalysisConfirmation(
        user_id=user_id,
        draft_id=draft.id,
        client_confirmation_id=request.client_confirmation_id,
        request_hash=request_hash,
        confirmed_draft_version=draft.version,
        log_ids=[],
        result_snapshot={},
    )
    session.add(confirmation)
    await session.flush()

    logs = []
    mappings: list[dict[str, str | None]] = []
    retained = set(source_ids)
    for source in source_entities:
        if source.id not in retained:
            _add_correction(
                session,
                confirmation.id,
                source.id,
                "entity_removed",
                {"name": source.normalized_name},
                None,
            )

    for item in request.entities:
        food = await get_visible_food(session, item.food_item_id, user_id)
        if food is None:
            raise AnalysisNotFoundError
        if food.current_revision != item.catalog_revision:
            raise AnalysisConflictError("food catalog revision changed")
        try:
            log, created = await create_log_in_transaction(
                session,
                user_id,
                LogCreateRequest(
                    client_id=item.client_id,
                    log_date=draft.log_date,
                    meal_type=item.meal_type,
                    food_item_id=item.food_item_id,
                    amount=item.amount,
                    unit=item.unit,
                    note="AI 草稿确认",
                ),
            )
        except IdempotencyConflictError as error:
            raise AnalysisConflictError("a confirmation log client_id is already in use") from error
        except InvalidLogContentError as error:
            raise AnalysisValidationError(str(error)) from error
        if not created:
            raise AnalysisConflictError("a confirmation log client_id is already in use")
        logs.append(log)
        mappings.append(
            {
                "entity_id": str(item.source_entity_id) if item.source_entity_id else None,
                "client_id": str(item.client_id),
                "log_id": str(log.id),
            }
        )
        source = source_by_id.get(item.source_entity_id)
        if source is None:
            _add_correction(
                session,
                confirmation.id,
                None,
                "entity_added",
                None,
                {"food_item_id": str(item.food_item_id), "name": food.name},
            )
            continue
        changes = (
            ("name", source.normalized_name, food.name),
            ("amount", float(source.amount), item.amount),
            ("unit", source.unit, item.unit),
            ("meal_type", source.meal_type, item.meal_type.value),
            (
                "food_match",
                str(source.matched_food_id) if source.matched_food_id else None,
                str(item.food_item_id),
            ),
        )
        for field_name, before, after in changes:
            if before != after:
                _add_correction(
                    session,
                    confirmation.id,
                    source.id,
                    field_name,
                    before,
                    after,
                )

    await session.flush()
    log_payloads = [LogResponse.model_validate(log).model_dump(mode="json") for log in logs]
    confirmation.log_ids = mappings
    confirmation.result_snapshot = {"logs": log_payloads}
    draft.status = "confirmed"
    draft.updated_at = datetime.now(UTC)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        existing = await session.scalar(
            select(AnalysisConfirmation).where(
                AnalysisConfirmation.user_id == user_id,
                AnalysisConfirmation.client_confirmation_id == request.client_confirmation_id,
            )
        )
        if (
            existing is None
            or existing.draft_id != draft_id
            or existing.request_hash != request_hash
        ):
            raise AnalysisConflictError("draft confirmation conflict") from error
        return _confirmation_response(existing), False
    await session.refresh(confirmation)
    return _confirmation_response(confirmation), True


async def discard_analysis_draft(session: AsyncSession, *, user_id: UUID, draft_id: UUID) -> None:
    draft = await get_owned_draft(session, user_id, draft_id, for_update=True)
    if draft is None:
        raise AnalysisNotFoundError
    if draft.status == "confirmed":
        raise AnalysisConflictError("confirmed logs must be deleted through the log API")
    if draft.status == "cancelled":
        return
    draft.status = "cancelled"
    draft.updated_at = datetime.now(UTC)
    await session.commit()
