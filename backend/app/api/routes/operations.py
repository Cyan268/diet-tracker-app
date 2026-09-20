import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import SessionDep, SettingsDep
from app.schemas.operations import OperationalMetricsResponse
from app.services.operations import collect_operational_metrics

router = APIRouter()


async def require_operations_access(
    settings: SettingsDep,
    operations_token: Annotated[str | None, Header(alias="X-Operations-Token")] = None,
) -> None:
    configured = settings.operations_metrics_token
    if (
        not settings.operations_metrics_enabled
        or configured is None
        or operations_token is None
        or not secrets.compare_digest(operations_token, configured.get_secret_value())
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


OperationsAccessDep = Annotated[None, Depends(require_operations_access)]


@router.get("/metrics", response_model=OperationalMetricsResponse, include_in_schema=False)
async def read_operational_metrics(
    _access: OperationsAccessDep,
    session: SessionDep,
    settings: SettingsDep,
) -> OperationalMetricsResponse:
    return await collect_operational_metrics(session, settings)
