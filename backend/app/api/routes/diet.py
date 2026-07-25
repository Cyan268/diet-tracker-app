from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.dependencies import CurrentUserDep, DemoGuardDep, SessionDep
from app.repositories.diet import (
    get_log,
    get_log_by_client_id,
    list_logs,
    list_sync_changes,
    search_visible_foods,
)
from app.schemas.diet import (
    DailySummaryResponse,
    FoodCreateRequest,
    FoodResponse,
    LogContent,
    LogCreateRequest,
    LogResponse,
    LogUpdateRequest,
    SyncChangeResponse,
    SyncPageResponse,
)
from app.services.diet import (
    IdempotencyConflictError,
    InvalidLogContentError,
    ResourceNotFoundError,
    VersionConflictError,
    create_food,
    create_log,
    delete_log,
    get_daily_summary,
    replace_log,
)

router = APIRouter()


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="resource not found")


def _version_conflict() -> HTTPException:
    return HTTPException(status_code=409, detail="record version conflict")


@router.get("/foods", response_model=list[FoodResponse])
async def search_foods(
    current_user: CurrentUserDep,
    session: SessionDep,
    query: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[FoodResponse]:
    foods = await search_visible_foods(session, current_user.id, query.strip(), limit)
    return [FoodResponse.model_validate(food) for food in foods]


@router.post("/foods", response_model=FoodResponse, status_code=status.HTTP_201_CREATED)
async def add_food(
    request: FoodCreateRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    demo_guard: DemoGuardDep,
) -> FoodResponse:
    await demo_guard.enforce_rate(current_user, "write")
    await demo_guard.enforce_capacity(session, current_user, "private_foods")
    food = await create_food(session, current_user.id, request)
    return FoodResponse.model_validate(food)


@router.post(
    "/logs",
    response_model=LogResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Idempotent replay"}, 409: {"description": "Key conflict"}},
)
async def add_log(
    request: LogCreateRequest,
    response: Response,
    current_user: CurrentUserDep,
    session: SessionDep,
    demo_guard: DemoGuardDep,
) -> LogResponse:
    await demo_guard.enforce_rate(current_user, "write")
    if await get_log_by_client_id(session, current_user.id, request.client_id) is None:
        await demo_guard.enforce_capacity(session, current_user, "logs")
    try:
        log, created = await create_log(session, current_user.id, request)
    except IdempotencyConflictError as error:
        raise HTTPException(
            status_code=409,
            detail="client_id was already used with different content",
        ) from error
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except InvalidLogContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not created:
        response.status_code = status.HTTP_200_OK
    return LogResponse.model_validate(log)


@router.get("/logs", response_model=list[LogResponse])
async def read_logs(
    current_user: CurrentUserDep,
    session: SessionDep,
    date_from: date,
    date_to: date,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> list[LogResponse]:
    if date_to < date_from or date_to - date_from > timedelta(days=31):
        raise HTTPException(status_code=422, detail="date range must be between 0 and 31 days")
    logs = await list_logs(session, current_user.id, date_from, date_to, limit, offset)
    return [LogResponse.model_validate(log) for log in logs]


@router.get("/sync/changes", response_model=SyncPageResponse)
async def read_sync_changes(
    current_user: CurrentUserDep,
    session: SessionDep,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> SyncPageResponse:
    rows = await list_sync_changes(session, current_user.id, after, limit + 1)
    has_more = len(rows) > limit
    page = rows[:limit]
    changes = [
        SyncChangeResponse(
            cursor=row.id,
            operation=row.operation,
            server_id=row.aggregate_id,
            client_id=row.client_id,
            version=row.version,
            log=LogResponse.model_validate(row.payload) if row.payload is not None else None,
        )
        for row in page
    ]
    return SyncPageResponse(
        changes=changes,
        next_cursor=page[-1].id if page else after,
        has_more=has_more,
    )


@router.get("/logs/{log_id}", response_model=LogResponse)
async def read_log(
    log_id: UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> LogResponse:
    log = await get_log(session, log_id, current_user.id)
    if log is None:
        raise _not_found()
    return LogResponse.model_validate(log)


@router.put("/logs/{log_id}", response_model=LogResponse)
async def update_log(
    log_id: UUID,
    request: LogUpdateRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    demo_guard: DemoGuardDep,
) -> LogResponse:
    await demo_guard.enforce_rate(current_user, "write")
    content = LogContent.model_validate(request.model_dump(exclude={"expected_version"}))
    try:
        log = await replace_log(
            session,
            current_user.id,
            log_id,
            request.expected_version,
            content,
        )
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except VersionConflictError as error:
        raise _version_conflict() from error
    except InvalidLogContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return LogResponse.model_validate(log)


@router.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_log(
    log_id: UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    demo_guard: DemoGuardDep,
    expected_version: Annotated[int, Query(ge=1)],
) -> Response:
    await demo_guard.enforce_rate(current_user, "write")
    try:
        await delete_log(session, current_user.id, log_id, expected_version)
    except ResourceNotFoundError as error:
        raise _not_found() from error
    except VersionConflictError as error:
        raise _version_conflict() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stats/daily", response_model=DailySummaryResponse)
async def read_daily_summary(
    summary_date: date,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> DailySummaryResponse:
    return await get_daily_summary(session, current_user.id, summary_date)
