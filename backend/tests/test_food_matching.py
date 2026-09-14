from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.models import FoodAlias, FoodItem, FoodItemRevision, User
from app.schemas.diet import FoodCreateRequest
from app.services.catalog_seed import seed_global_catalog
from app.services.diet import create_food
from app.services.food_matching import (
    match_visible_foods,
    normalize_catalog_text,
    nutrition_ratio,
)


def food(
    *,
    name: str,
    brand: str | None = None,
    owner_id=None,
    basis_unit: str = "g",
    basis_quantity: str = "100",
    serving_unit: str | None = None,
    serving_weight_g: str | None = None,
    density: str | None = None,
    nutrition_complete: bool = True,
) -> FoodItem:
    return FoodItem(
        id=uuid4(),
        owner_user_id=owner_id,
        name=name,
        normalized_name=normalize_catalog_text(name),
        brand=brand,
        brand_normalized=normalize_catalog_text(brand) if brand else None,
        category="test",
        catalog_key=f"test:{uuid4()}",
        current_revision="test-v1",
        source_reference="tests/test_food_matching.py",
        nutrition_basis_unit=basis_unit,
        nutrition_basis_quantity=Decimal(basis_quantity),
        density_g_per_ml=Decimal(density) if density else None,
        nutrition_complete=nutrition_complete,
        serving_unit=serving_unit,
        serving_weight_g=Decimal(serving_weight_g) if serving_weight_g else None,
        kcal_per_100g=Decimal("100"),
        protein_per_100g=Decimal("1"),
        fat_per_100g=Decimal("2"),
        carbs_per_100g=Decimal("3"),
        sugar_per_100g=Decimal("1"),
        sodium_per_100g=Decimal("5"),
        caffeine_per_100g=Decimal("10"),
        source="test-catalog",
    )


def test_catalog_normalization_and_unit_boundaries() -> None:
    assert normalize_catalog_text(" M Stand（咖啡） ") == "mstand咖啡"
    grams = food(name="牛奶", density="1.030")
    assert nutrition_ratio(grams, 100, "ml") == Decimal("1.030")

    missing_density = food(name="果汁")
    with pytest.raises(ValueError, match="without density"):
        nutrition_ratio(missing_density, 100, "ml")

    serving = food(
        name="伯牙绝弦",
        basis_unit="serving",
        basis_quantity="1",
        serving_unit="标准杯",
    )
    assert nutrition_ratio(serving, 2, "标准杯") == Decimal("2")
    with pytest.raises(ValueError, match="declared serving unit"):
        nutrition_ratio(serving, 500, "ml")

    incomplete = food(name="估算饮品", basis_unit="serving", nutrition_complete=False)
    with pytest.raises(ValueError, match="incomplete"):
        nutrition_ratio(incomplete, 1, "杯")


async def test_pg_trgm_matching_brand_ambiguity_and_private_scope(pg_session_factory) -> None:
    owner_a = User(id=uuid4(), email=f"match-a-{uuid4()}@example.test", password_hash="test")
    owner_b = User(id=uuid4(), email=f"match-b-{uuid4()}@example.test", password_hash="test")
    luckin = food(name="火星冰萃一号", brand="瑞幸咖啡")
    manner = food(name="火星冰萃二号", brand="Manner Coffee")
    private = food(name="私房燕麦奶", brand="个人配方", owner_id=owner_a.id)

    async with pg_session_factory() as session:
        transaction = await session.begin()
        session.add_all([owner_a, owner_b])
        await session.flush()
        session.add_all([luckin, manner, private])
        await session.flush()
        session.add_all(
            [
                FoodAlias(
                    food_item_id=luckin.id,
                    alias="唯一测试冰美式",
                    normalized_alias=normalize_catalog_text("唯一测试冰美式"),
                    source="test-catalog",
                ),
                FoodAlias(
                    food_item_id=manner.id,
                    alias="唯一测试冰美式",
                    normalized_alias=normalize_catalog_text("唯一测试冰美式"),
                    source="test-catalog",
                ),
                FoodAlias(
                    food_item_id=private.id,
                    alias="秘密燕麦",
                    normalized_alias=normalize_catalog_text("秘密燕麦"),
                    source="user",
                ),
            ]
        )
        await session.flush()

        ambiguous = await match_visible_foods(session, owner_a.id, "唯一测试冰美式")
        assert ambiguous.status == "ambiguous"
        assert ambiguous.preselected_food_item_id is None
        assert {candidate.reason for candidate in ambiguous.candidates[:2]} == {"alias_exact"}
        assert {candidate.source for candidate in ambiguous.candidates[:2]} == {"test-catalog"}

        branded = await match_visible_foods(
            session,
            owner_a.id,
            "唯一测试冰美式",
            brand="瑞 幸咖啡",
        )
        assert branded.status == "review"
        assert branded.preselected_food_item_id == luckin.id
        assert branded.candidates[0].catalog_revision == "test-v1"
        assert branded.candidates[0].source_reference == "tests/test_food_matching.py"

        fuzzy = await match_visible_foods(session, owner_a.id, "火星冰萃一号饮品")
        assert fuzzy.candidates
        assert fuzzy.candidates[0].reason in {"canonical_similar", "alias_similar"}

        assert (await match_visible_foods(session, owner_a.id, "秘密燕麦")).candidates
        assert (await match_visible_foods(session, owner_b.id, "秘密燕麦")).status == "no_match"
        assert (await match_visible_foods(session, owner_a.id, "月球岩石汤")).status == "no_match"

        assert await session.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='pg_trgm')")
        )
        trigram_indexes = await session.scalar(
            text(
                "SELECT count(*) FROM pg_indexes WHERE indexname IN "
                "('ix_food_items_normalized_name_trgm', 'ix_food_aliases_normalized_trgm')"
            )
        )
        assert trigram_indexes == 2
        await transaction.rollback()


async def test_private_food_creation_writes_immutable_revision(session_factory) -> None:
    owner_id = uuid4()
    async with session_factory() as session:
        session.add(
            User(
                id=owner_id,
                email=f"private-food-{owner_id}@example.test",
                password_hash="test",
            )
        )
        await session.commit()

    request = FoodCreateRequest(
        name="  自制燕麦碗（早餐） ",
        brand="我的厨房",
        category="meal",
        serving_unit="碗",
        serving_weight_g=350,
        kcal_per_100g=120,
        protein_per_100g=5,
        fat_per_100g=3,
        carbs_per_100g=20,
        sugar_per_100g=4,
        sodium_per_100g=80,
        caffeine_per_100g=0,
    )
    async with session_factory() as session:
        created = await create_food(session, owner_id, request)
        food_id = created.id

    async with session_factory() as session:
        created = await session.get(FoodItem, food_id)
        revision = await session.scalar(
            select(FoodItemRevision).where(FoodItemRevision.food_item_id == food_id)
        )
        assert created is not None
        assert created.normalized_name == "自制燕麦碗早餐"
        assert created.brand_normalized == "我的厨房"
        assert revision is not None
        assert revision.revision == "user-v1"
        assert revision.source_reference == "user-provided"


async def test_match_endpoint_returns_explainable_catalog_candidate(
    pg_api_client,
    pg_session_factory,
) -> None:
    async with pg_session_factory() as session:
        await seed_global_catalog(session)

    register = await pg_api_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"match-{uuid4().hex[:12]}@example.com",
            "password": "correct-horse-123",
        },
    )
    assert register.status_code == 201, register.text
    headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

    response = await pg_api_client.get(
        "/api/v1/foods/match",
        headers=headers,
        params={"query": "Luckin 生椰拿铁", "brand": "瑞幸咖啡"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review"
    assert body["preselected_food_item_id"] == body["candidates"][0]["food_item_id"]
    assert body["candidates"][0]["reason"] == "alias_exact"
    assert body["candidates"][0]["source"] == "client_estimate"
    assert body["candidates"][0]["nutrition_complete"] is False
