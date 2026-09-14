from copy import deepcopy

from sqlalchemy import func, select

from app.models import FoodAlias, FoodItem, FoodItemRevision
from app.services.catalog_seed import load_catalog, seed_global_catalog


def test_packaged_catalog_has_complete_and_guarded_items() -> None:
    catalog = load_catalog()
    items = catalog["items"]

    assert catalog["revision"] == "catalog-2026-09-08-v1"
    assert len(items) == 136
    assert sum(item["nutritionComplete"] for item in items) == 20
    assert sum(not item["nutritionComplete"] for item in items) == 116
    assert any(item["brand"] == "霸王茶姬" and item["name"] == "伯牙绝弦" for item in items)


async def test_catalog_seed_is_idempotent(session_factory) -> None:
    async with session_factory() as session:
        first = await seed_global_catalog(session)
        second = await seed_global_catalog(session)
        item_count = await session.scalar(select(func.count()).select_from(FoodItem))
        revision_count = await session.scalar(select(func.count()).select_from(FoodItemRevision))
        alias_count = await session.scalar(select(func.count()).select_from(FoodAlias))

    assert first.created_items == 136
    assert first.created_revisions == 136
    assert first.created_aliases > 0
    assert second.created_items == 0
    assert second.updated_items == 0
    assert second.created_revisions == 0
    assert second.created_aliases == 0
    assert item_count == revision_count == 136
    assert alias_count == first.created_aliases


async def test_new_catalog_revision_preserves_old_snapshot(session_factory) -> None:
    original = load_catalog()
    v1 = {"revision": "test-v1", "items": [deepcopy(original["items"][0])]}
    v2 = deepcopy(v1)
    v2["revision"] = "test-v2"
    v2["items"][0]["kcal"] = 999

    async with session_factory() as session:
        await seed_global_catalog(session, catalog=v1)
        await seed_global_catalog(session, catalog=v2)
        food = await session.scalar(select(FoodItem))
        revisions = (
            await session.scalars(select(FoodItemRevision).order_by(FoodItemRevision.revision))
        ).all()

    assert food is not None
    assert food.current_revision == "test-v2"
    assert food.kcal_per_100g == 999
    assert [revision.revision for revision in revisions] == ["test-v1", "test-v2"]
    assert revisions[0].kcal != revisions[1].kcal
