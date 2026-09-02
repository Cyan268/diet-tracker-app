from fastapi import APIRouter, HTTPException

from app.api.dependencies import CurrentUserDep, DemoGuardDep, SessionDep
from app.models import UserProfile
from app.repositories.diet import get_profile
from app.schemas.auth import UserResponse
from app.schemas.profile import ProfileResponse, ProfileUpsertRequest
from app.services.diet import calculate_daily_targets, upsert_profile

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def read_current_user(current_user: CurrentUserDep) -> UserResponse:
    return UserResponse.model_validate(current_user)


def _profile_response(profile: UserProfile) -> ProfileResponse:
    return ProfileResponse.model_validate(
        {
            "gender": profile.gender,
            "age": profile.age,
            "height_cm": profile.height_cm,
            "weight_kg": profile.weight_kg,
            "activity_level": profile.activity_level,
            "goal": profile.goal,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
            "daily_targets": calculate_daily_targets(profile),
        }
    )


@router.get("/me/profile", response_model=ProfileResponse)
async def read_profile(
    current_user: CurrentUserDep,
    session: SessionDep,
) -> ProfileResponse:
    profile = await get_profile(session, current_user.id)
    if profile is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return _profile_response(profile)


@router.put("/me/profile", response_model=ProfileResponse)
async def put_profile(
    request: ProfileUpsertRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
    demo_guard: DemoGuardDep,
) -> ProfileResponse:
    await demo_guard.enforce_rate(current_user, "write")
    profile = await upsert_profile(session, current_user.id, request)
    return _profile_response(profile)
