import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import (
    AiCallLog,
    AiCredential,
    AssistantConversation,
    AssistantMessage,
    FoodItem,
    FoodLog,
    RefreshToken,
    SyncChange,
    User,
    UserProfile,
)
from app.repositories.users import get_user_by_email
from app.schemas.diet import LogCreateRequest, LogResponse, NutritionValues
from app.services.auth import normalize_email

DEMO_SEED_VERSION = "demo-seed-v1"


class DemoAccountConflictError(ValueError):
    pass


class DemoResetRequiredError(ValueError):
    pass


@dataclass(frozen=True)
class DemoSeedResult:
    user_id: UUID
    email: str
    anchor_date: date
    log_count: int
    private_food_count: int
    reset: bool


@dataclass(frozen=True)
class DemoLogSpec:
    day_offset: int
    meal_type: str
    name: str
    nutrition: NutritionValues


def _nutrition(
    kcal: float,
    protein: float,
    fat: float,
    carbs: float,
    sugar: float,
    sodium: float,
    caffeine: float = 0,
) -> NutritionValues:
    return NutritionValues(
        kcal=kcal,
        protein=protein,
        fat=fat,
        carbs=carbs,
        sugar=sugar,
        sodium=sodium,
        caffeine=caffeine,
    )


def build_demo_log_specs() -> list[DemoLogSpec]:
    specs: list[DemoLogSpec] = []
    for day_offset in range(13, -1, -1):
        specs.extend(
            [
                DemoLogSpec(
                    day_offset,
                    "breakfast",
                    "燕麦牛奶碗",
                    _nutrition(400, 20, 13, 54, 10, 230),
                ),
                DemoLogSpec(
                    day_offset,
                    "lunch",
                    "鸡胸肉杂粮饭",
                    _nutrition(650, 43, 18, 76, 6, 710),
                ),
                DemoLogSpec(
                    day_offset,
                    "dinner",
                    "三文鱼蔬菜餐",
                    _nutrition(560, 33, 17, 68, 8, 640),
                ),
            ]
        )
        if day_offset >= 7 or day_offset in {0, 2, 4, 6}:
            specs.append(
                DemoLogSpec(
                    day_offset,
                    "snack",
                    "酸奶水果杯",
                    _nutrition(180, 6, 5, 29, 17, 85),
                )
            )

    drinks = {
        12: ("喜茶 多肉葡萄（演示）", _nutrition(230, 2, 1, 54, 43, 45, 25)),
        9: ("瑞幸 生椰拿铁（演示）", _nutrition(190, 5, 8, 24, 15, 105, 135)),
        7: ("霸王茶姬 伯牙绝弦（演示）", _nutrition(210, 4, 7, 33, 24, 90, 95)),
        5: ("Manner 冰美式（演示）", _nutrition(15, 1, 0, 2, 0, 10, 180)),
        2: ("古茗 水果茶（演示）", _nutrition(170, 1, 0, 42, 35, 35, 20)),
    }
    for day_offset, (name, nutrition) in drinks.items():
        specs.append(DemoLogSpec(day_offset, "drink", name, nutrition))
    return specs


async def _remove_existing_demo_data(session: AsyncSession, user_id: UUID) -> None:
    conversation_ids = select(AssistantConversation.id).where(
        AssistantConversation.user_id == user_id
    )
    await session.execute(
        delete(AssistantMessage).where(AssistantMessage.conversation_id.in_(conversation_ids))
    )
    for model, owner_column in (
        (AssistantConversation, AssistantConversation.user_id),
        (AiCredential, AiCredential.user_id),
        (AiCallLog, AiCallLog.user_id),
        (RefreshToken, RefreshToken.user_id),
        (SyncChange, SyncChange.user_id),
        (FoodLog, FoodLog.user_id),
        (FoodItem, FoodItem.owner_user_id),
        (UserProfile, UserProfile.user_id),
    ):
        await session.execute(delete(model).where(owner_column == user_id))
    await session.execute(delete(User).where(User.id == user_id))
    await session.flush()


def _payload_hash(request: LogCreateRequest) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


async def seed_demo_account(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    anchor_date: date,
    reset_existing: bool = False,
) -> DemoSeedResult:
    normalized_email = normalize_email(email)
    if len(password) < 10:
        raise ValueError("demo password must contain at least 10 characters")

    existing = await get_user_by_email(session, normalized_email)
    did_reset = existing is not None
    if existing is not None:
        if not existing.is_demo:
            raise DemoAccountConflictError("email belongs to a non-demo account")
        if not reset_existing:
            raise DemoResetRequiredError("demo account exists; pass reset_existing=True")
        await _remove_existing_demo_data(session, existing.id)

    user = User(
        # A reset deliberately rotates the user id so previously issued access
        # tokens no longer resolve to an active account.
        id=uuid4(),
        email=normalized_email,
        password_hash=await hash_password(password),
        is_active=True,
        is_demo=True,
    )
    session.add(user)
    # These models deliberately use explicit foreign-key ids instead of ORM
    # relationships, so SQLAlchemy cannot infer their insert dependency graph.
    # Flush the parent first while keeping the whole seed operation in the same
    # transaction; a later failure will still roll everything back.
    await session.flush()
    session.add(
        UserProfile(
            user_id=user.id,
            gender="female",
            age=23,
            height_cm=Decimal("165"),
            weight_kg=Decimal("55"),
            activity_level="moderate",
            goal="maintain",
        )
    )
    private_foods = [
        FoodItem(
            id=uuid5(NAMESPACE_URL, f"nutripilot:{DEMO_SEED_VERSION}:{normalized_email}:food:1"),
            owner_user_id=user.id,
            name="宿舍鸡胸肉饭",
            brand="演示自定义",
            category="meal",
            serving_unit="份",
            serving_weight_g=Decimal("420"),
            kcal_per_100g=Decimal("154.8"),
            protein_per_100g=Decimal("10.2"),
            fat_per_100g=Decimal("4.3"),
            carbs_per_100g=Decimal("18.1"),
            sugar_per_100g=Decimal("1.4"),
            sodium_per_100g=Decimal("169"),
            caffeine_per_100g=Decimal("0"),
            source="demo_seed",
        ),
        FoodItem(
            id=uuid5(NAMESPACE_URL, f"nutripilot:{DEMO_SEED_VERSION}:{normalized_email}:food:2"),
            owner_user_id=user.id,
            name="自制酸奶水果杯",
            brand="演示自定义",
            category="snack",
            serving_unit="杯",
            serving_weight_g=Decimal("260"),
            kcal_per_100g=Decimal("69.2"),
            protein_per_100g=Decimal("2.3"),
            fat_per_100g=Decimal("1.9"),
            carbs_per_100g=Decimal("11.2"),
            sugar_per_100g=Decimal("6.5"),
            sodium_per_100g=Decimal("32.7"),
            caffeine_per_100g=Decimal("0"),
            source="demo_seed",
        ),
    ]
    session.add_all(private_foods)

    logs: list[FoodLog] = []
    for index, spec in enumerate(build_demo_log_specs()):
        log_date = anchor_date - timedelta(days=spec.day_offset)
        client_id = uuid5(
            NAMESPACE_URL,
            f"nutripilot:{DEMO_SEED_VERSION}:{normalized_email}:{anchor_date}:{index}",
        )
        request = LogCreateRequest(
            client_id=client_id,
            log_date=log_date,
            meal_type=spec.meal_type,
            custom_name=spec.name,
            amount=1,
            unit="份",
            nutrition=spec.nutrition,
            note=f"[{DEMO_SEED_VERSION}] 可安全重置的演示记录",
        )
        nutrition = spec.nutrition
        log = FoodLog(
            id=uuid5(NAMESPACE_URL, f"{client_id}:server"),
            user_id=user.id,
            client_id=client_id,
            log_date=log_date,
            meal_type=spec.meal_type,
            custom_name=spec.name,
            amount=Decimal("1"),
            unit="份",
            kcal=_decimal(nutrition.kcal),
            protein=_decimal(nutrition.protein),
            fat=_decimal(nutrition.fat),
            carbs=_decimal(nutrition.carbs),
            sugar=_decimal(nutrition.sugar),
            sodium=_decimal(nutrition.sodium),
            caffeine=_decimal(nutrition.caffeine),
            note=request.note,
            payload_hash=_payload_hash(request),
            version=1,
        )
        logs.append(log)
    session.add_all(logs)
    await session.flush()
    session.add_all(
        [
            SyncChange(
                user_id=user.id,
                aggregate_id=log.id,
                client_id=log.client_id,
                operation="upsert",
                version=log.version,
                payload=LogResponse.model_validate(log).model_dump(mode="json"),
            )
            for log in logs
        ]
    )
    await session.commit()
    return DemoSeedResult(
        user_id=user.id,
        email=user.email,
        anchor_date=anchor_date,
        log_count=len(logs),
        private_food_count=len(private_foods),
        reset=did_reset,
    )
