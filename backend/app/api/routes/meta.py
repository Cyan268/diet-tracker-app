from fastapi import APIRouter

from app.api.dependencies import SettingsDep
from app.schemas.meta import PublicRuntimeConfigResponse

router = APIRouter()


@router.get("/config", response_model=PublicRuntimeConfigResponse)
async def public_runtime_config(settings: SettingsDep) -> PublicRuntimeConfigResponse:
    return PublicRuntimeConfigResponse(
        registration_enabled=settings.public_registration_enabled,
    )
