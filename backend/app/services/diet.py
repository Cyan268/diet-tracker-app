import json
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodItem, FoodLog, UserProfile
from app.repositories.diet import (
    get_log,
    get_log_by_client_id,
    get_profile,
    get_visible_food,
)
from app.schemas.diet import (
    DailySummaryResponse,
    FoodCreateRequest,
    LogContent,
    LogCreateRequest,
    MealBreakdown,
    NutritionValues,
)
from app.schemas.profile import DailyTargetsResponse, ProfileUpsertRequest
from app.services.log_changes import lock_user_sync_state, record_log_change


class ResourceNotFoundError(ValueError):
    pass


class IdempotencyConflictError(ValueError):
    pass


class VersionConflictError(ValueError):
    pass


class InvalidLogContentError(ValueError):
    pass


@dataclass(frozen=True)
class NutritionSnapshot:
    kcal: Decimal
    protein: Decimal
    fat: Decimal
    carbs: Decimal
    sugar: Decimal
    sodium: Decimal
    caffeine: Decimal


def _decimal(value: float | Decimal) -> Decimal:
    return Decimal(str(value))


def calculate_daily_targets(profile: UserProfile) -> DailyTargetsResponse:
    weight = profile.weight_kg
    base = weight * Decimal(10) + profile.height_cm * Decimal("6.25") - profile.age * 5
    bmr = base + 5 if profile.gender == "male" else base - 161
    multipliers = {
        "sedentary": Decimal("1.2"),
        "light": Decimal("1.375"),
        "moderate": Decimal("1.55"),
        "active": Decimal("1.725"),
        "very_active": Decimal("1.9"),
    }
    adjustments = {"lose": -500, "maintain": 0, "gain": 300}
    kcal = int(
        (bmr * multipliers[profile.activity_level] + adjustments[profile.goal]).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    protein = int((weight * Decimal("1.6")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    fat = int((Decimal(kcal) * Decimal("0.25") / 9).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    carbs_value = Decimal(kcal - protein * 4 - fat * 9) / 4
    carbs = max(int(carbs_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)), 0)
    return DailyTargetsResponse(kcal=kcal, protein=protein, fat=fat, carbs=carbs)


async def upsert_profile(
    session: AsyncSession,
    user_id: UUID,
    request: ProfileUpsertRequest,
) -> UserProfile:
    profile = await get_profile(session, user_id)
    values = request.model_dump(mode="json")
    if profile is None:
        profile = UserProfile(user_id=user_id, **values)
        session.add(profile)
    else:
        for field, value in values.items():
            setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return profile


async def create_food(
    session: AsyncSession,
    user_id: UUID,
    request: FoodCreateRequest,
) -> FoodItem:
    food = FoodItem(owner_user_id=user_id, source="user", **request.model_dump())
    session.add(food)
    await session.commit()
    await session.refresh(food)
    return food


def _fingerprint(request: LogCreateRequest) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _custom_snapshot(nutrition: NutritionValues) -> NutritionSnapshot:
    return NutritionSnapshot(
        **{key: _decimal(value) for key, value in nutrition.model_dump().items()}
    )


def _catalog_snapshot(food: FoodItem, amount: float, unit: str) -> NutritionSnapshot:
    amount_decimal = _decimal(amount)
    if unit.lower() in {"g", "克"}:
        grams = amount_decimal
    elif food.serving_unit is not None and unit == food.serving_unit and food.serving_weight_g:
        grams = amount_decimal * food.serving_weight_g
    else:
        raise InvalidLogContentError("unit cannot be converted using this food item")

    ratio = grams / Decimal(100)
    return NutritionSnapshot(
        kcal=food.kcal_per_100g * ratio,
        protein=food.protein_per_100g * ratio,
        fat=food.fat_per_100g * ratio,
        carbs=food.carbs_per_100g * ratio,
        sugar=food.sugar_per_100g * ratio,
        sodium=food.sodium_per_100g * ratio,
        caffeine=food.caffeine_per_100g * ratio,
    )


async def _resolve_snapshot(
    session: AsyncSession,
    user_id: UUID,
    content: LogContent,
) -> NutritionSnapshot:
    if content.food_item_id is not None:
        food = await get_visible_food(session, content.food_item_id, user_id)
        if food is None:
            raise ResourceNotFoundError
        return _catalog_snapshot(food, content.amount, content.unit)
    if content.nutrition is None:
        raise InvalidLogContentError("nutrition is required for a custom food")
    return _custom_snapshot(content.nutrition)


async def create_log(
    session: AsyncSession,
    user_id: UUID,
    request: LogCreateRequest,
) -> tuple[FoodLog, bool]:
    state = await lock_user_sync_state(session, user_id)
    payload_hash = _fingerprint(request)
    existing = await get_log_by_client_id(session, user_id, request.client_id)
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise IdempotencyConflictError
        return existing, False

    snapshot = await _resolve_snapshot(session, user_id, request)
    values = request.model_dump(exclude={"client_id", "nutrition"}, mode="python")
    log = FoodLog(
        user_id=user_id,
        client_id=request.client_id,
        payload_hash=payload_hash,
        **values,
        **snapshot.__dict__,
    )
    session.add(log)
    try:
        await session.flush()
        await session.refresh(log)
        record_log_change(session, state, log, "upsert")
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        existing = await get_log_by_client_id(session, user_id, request.client_id)
        if existing is None or existing.payload_hash != payload_hash:
            raise IdempotencyConflictError from error
        return existing, False
    await session.refresh(log)
    return log, True


async def replace_log(
    session: AsyncSession,
    user_id: UUID,
    log_id: UUID,
    expected_version: int,
    content: LogContent,
) -> FoodLog:
    state = await lock_user_sync_state(session, user_id)
    if await get_log(session, log_id, user_id) is None:
        raise ResourceNotFoundError
    snapshot = await _resolve_snapshot(session, user_id, content)
    values = content.model_dump(exclude={"nutrition"}, mode="python")
    result = await session.execute(
        update(FoodLog)
        .where(
            FoodLog.id == log_id,
            FoodLog.user_id == user_id,
            FoodLog.version == expected_version,
        )
        .values(**values, **snapshot.__dict__, version=FoodLog.version + 1, updated_at=func.now())
    )
    if result.rowcount != 1:
        await session.rollback()
        raise VersionConflictError
    updated = await get_log(session, log_id, user_id)
    if updated is None:
        raise ResourceNotFoundError
    await session.refresh(updated)
    record_log_change(session, state, updated, "upsert")
    await session.commit()
    await session.refresh(updated)
    return updated


async def delete_log(
    session: AsyncSession,
    user_id: UUID,
    log_id: UUID,
    expected_version: int,
) -> None:
    state = await lock_user_sync_state(session, user_id)
    existing = await get_log(session, log_id, user_id)
    if existing is None:
        raise ResourceNotFoundError
    result = await session.execute(
        delete(FoodLog).where(
            FoodLog.id == log_id,
            FoodLog.user_id == user_id,
            FoodLog.version == expected_version,
        )
    )
    if result.rowcount != 1:
        await session.rollback()
        raise VersionConflictError
    record_log_change(session, state, existing, "delete")
    await session.commit()


async def get_daily_summary(
    session: AsyncSession,
    user_id: UUID,
    summary_date: date,
) -> DailySummaryResponse:
    total_statement = select(
        func.coalesce(func.sum(FoodLog.kcal), 0),
        func.coalesce(func.sum(FoodLog.protein), 0),
        func.coalesce(func.sum(FoodLog.fat), 0),
        func.coalesce(func.sum(FoodLog.carbs), 0),
        func.coalesce(func.sum(FoodLog.sugar), 0),
        func.coalesce(func.sum(FoodLog.sodium), 0),
        func.coalesce(func.sum(FoodLog.caffeine), 0),
    ).where(FoodLog.user_id == user_id, FoodLog.log_date == summary_date)
    totals = (await session.execute(total_statement)).one()
    meal_rows = (
        await session.execute(
            select(FoodLog.meal_type, func.coalesce(func.sum(FoodLog.kcal), 0))
            .where(FoodLog.user_id == user_id, FoodLog.log_date == summary_date)
            .group_by(FoodLog.meal_type)
        )
    ).all()
    breakdown = MealBreakdown(**{meal_type: float(total) for meal_type, total in meal_rows})
    return DailySummaryResponse(
        date=summary_date,
        total_kcal=float(totals[0]),
        total_protein=float(totals[1]),
        total_fat=float(totals[2]),
        total_carbs=float(totals[3]),
        total_sugar=float(totals[4]),
        total_sodium=float(totals[5]),
        total_caffeine=float(totals[6]),
        meal_breakdown=breakdown,
    )
