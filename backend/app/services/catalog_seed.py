import json
from dataclasses import dataclass
from decimal import Decimal
from importlib.resources import files
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodAlias, FoodItem, FoodItemRevision
from app.services.food_matching import normalize_catalog_text

CATALOG_ASSET = "catalog-2026-09-08-v1.json"


@dataclass(frozen=True)
class CatalogSeedResult:
    revision: str
    created_items: int
    updated_items: int
    created_revisions: int
    created_aliases: int


def load_catalog() -> dict[str, Any]:
    asset = files("app.catalog").joinpath(CATALOG_ASSET)
    return json.loads(asset.read_text(encoding="utf-8"))


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _catalog_key(item: dict[str, Any]) -> str:
    brand = normalize_catalog_text(item["brand"] or "unbranded")
    name = normalize_catalog_text(item["name"])
    return f"global:{brand}:{name}"


def _stable_id(kind: str, key: str, revision: str | None = None) -> UUID:
    suffix = f":{revision}" if revision is not None else ""
    return uuid5(NAMESPACE_URL, f"nutripilot:food-catalog:{kind}:{key}{suffix}")


def _projection_values(item: dict[str, Any], revision: str, key: str) -> dict[str, Any]:
    return {
        "name": item["name"],
        "normalized_name": normalize_catalog_text(item["name"]),
        "brand": item["brand"],
        "brand_normalized": (
            normalize_catalog_text(item["brand"]) if item["brand"] is not None else None
        ),
        "category": item["category"],
        "catalog_key": key,
        "current_revision": revision,
        "source_reference": item["sourceReference"],
        "nutrition_basis_unit": item["basisUnit"],
        "nutrition_basis_quantity": _decimal(item["basisQuantity"]),
        "serving_unit": item["servingUnit"],
        "serving_weight_g": (
            _decimal(item["servingWeightG"]) if item["servingWeightG"] is not None else None
        ),
        "density_g_per_ml": (
            _decimal(item["densityGPerMl"]) if item["densityGPerMl"] is not None else None
        ),
        "nutrition_complete": item["nutritionComplete"],
        "kcal_per_100g": _decimal(item["kcal"]),
        "protein_per_100g": _decimal(item["proteinG"]),
        "fat_per_100g": _decimal(item["fatG"]),
        "carbs_per_100g": _decimal(item["carbsG"]),
        "sugar_per_100g": _decimal(item["sugarG"]),
        "sodium_per_100g": _decimal(item["sodiumMg"]),
        "caffeine_per_100g": _decimal(item["caffeineMg"]),
        "source": item["source"],
    }


def _revision(item: FoodItem, revision: str) -> FoodItemRevision:
    return FoodItemRevision(
        id=_stable_id("revision", item.catalog_key or str(item.id), revision),
        food_item_id=item.id,
        revision=revision,
        display_name=item.name,
        brand=item.brand,
        category=item.category,
        basis_unit=item.nutrition_basis_unit,
        basis_quantity=item.nutrition_basis_quantity,
        serving_unit=item.serving_unit,
        serving_weight_g=item.serving_weight_g,
        density_g_per_ml=item.density_g_per_ml,
        nutrition_complete=item.nutrition_complete,
        kcal=item.kcal_per_100g,
        protein_g=item.protein_per_100g,
        fat_g=item.fat_per_100g,
        carbs_g=item.carbs_per_100g,
        sugar_g=item.sugar_per_100g,
        sodium_mg=item.sodium_per_100g,
        caffeine_mg=item.caffeine_per_100g,
        source=item.source,
        source_reference=item.source_reference,
    )


async def seed_global_catalog(
    session: AsyncSession,
    *,
    catalog: dict[str, Any] | None = None,
) -> CatalogSeedResult:
    payload = catalog or load_catalog()
    revision = str(payload["revision"])
    created_items = updated_items = created_revisions = created_aliases = 0

    for spec in payload["items"]:
        key = _catalog_key(spec)
        food = await session.scalar(
            select(FoodItem).where(
                FoodItem.owner_user_id.is_(None),
                FoodItem.catalog_key == key,
            )
        )
        values = _projection_values(spec, revision, key)
        if food is None:
            food = FoodItem(
                id=_stable_id("item", key),
                owner_user_id=None,
                **values,
            )
            session.add(food)
            await session.flush()
            created_items += 1
        elif food.current_revision != revision:
            for field, value in values.items():
                setattr(food, field, value)
            updated_items += 1

        existing_revision = await session.scalar(
            select(FoodItemRevision.id).where(
                FoodItemRevision.food_item_id == food.id,
                FoodItemRevision.revision == revision,
            )
        )
        if existing_revision is None:
            session.add(_revision(food, revision))
            created_revisions += 1

        existing_aliases = set(
            (
                await session.scalars(
                    select(FoodAlias.normalized_alias).where(FoodAlias.food_item_id == food.id)
                )
            ).all()
        )
        for alias in spec.get("aliases", []):
            normalized_alias = normalize_catalog_text(alias)
            if not normalized_alias or normalized_alias in existing_aliases:
                continue
            session.add(
                FoodAlias(
                    id=_stable_id("alias", f"{key}:{normalized_alias}"),
                    food_item_id=food.id,
                    alias=alias,
                    normalized_alias=normalized_alias,
                    source=spec["source"],
                )
            )
            existing_aliases.add(normalized_alias)
            created_aliases += 1
        await session.flush()

    await session.commit()
    return CatalogSeedResult(
        revision=revision,
        created_items=created_items,
        updated_items=updated_items,
        created_revisions=created_revisions,
        created_aliases=created_aliases,
    )
