import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodAlias, FoodItem

MATCH_RECALL_THRESHOLD = 0.2
PRESELECT_THRESHOLD = 0.92
AMBIGUITY_MARGIN = 0.05


def normalize_catalog_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


@dataclass(frozen=True)
class FoodMatchCandidate:
    food_item_id: UUID
    catalog_revision: str
    name: str
    brand: str | None
    source: str
    source_reference: str | None
    nutrition_complete: bool
    score: float
    reason: str


@dataclass(frozen=True)
class FoodMatchDecision:
    status: str
    preselected_food_item_id: UUID | None
    candidates: tuple[FoodMatchCandidate, ...]


async def match_visible_foods(
    session: AsyncSession,
    user_id: UUID,
    query: str,
    *,
    brand: str | None = None,
    limit: int = 5,
) -> FoodMatchDecision:
    normalized_query = normalize_catalog_text(query)
    normalized_brand = normalize_catalog_text(brand) if brand else None
    if not normalized_query:
        return FoodMatchDecision("no_match", None, ())

    alias_similarity = (
        select(func.max(func.similarity(FoodAlias.normalized_alias, normalized_query)))
        .where(FoodAlias.food_item_id == FoodItem.id)
        .correlate(FoodItem)
        .scalar_subquery()
    )
    alias_exact = (
        select(literal(1))
        .where(
            FoodAlias.food_item_id == FoodItem.id,
            FoodAlias.normalized_alias == normalized_query,
        )
        .correlate(FoodItem)
        .exists()
    )
    canonical_similarity = func.similarity(FoodItem.normalized_name, normalized_query)
    fuzzy_score = func.greatest(canonical_similarity, func.coalesce(alias_similarity, 0.0))
    sort_score = case(
        (FoodItem.normalized_name == normalized_query, 1.0),
        (alias_exact, 0.98),
        else_=fuzzy_score,
    )
    statement = (
        select(
            FoodItem,
            canonical_similarity.label("canonical_similarity"),
            func.coalesce(alias_similarity, 0.0).label("alias_similarity"),
            alias_exact.label("alias_exact"),
        )
        .where(
            or_(FoodItem.owner_user_id.is_(None), FoodItem.owner_user_id == user_id),
            or_(
                FoodItem.normalized_name == normalized_query,
                alias_exact,
                canonical_similarity >= MATCH_RECALL_THRESHOLD,
                alias_similarity >= MATCH_RECALL_THRESHOLD,
            ),
        )
        .order_by(sort_score.desc(), FoodItem.brand_normalized, FoodItem.id)
        .limit(limit)
    )
    if normalized_brand is not None:
        statement = statement.where(FoodItem.brand_normalized == normalized_brand)

    candidates: list[FoodMatchCandidate] = []
    for food, canonical_score, alias_score, is_alias_exact in await session.execute(statement):
        if food.normalized_name == normalized_query:
            score, reason = 1.0, "canonical_exact"
        elif is_alias_exact:
            score, reason = 0.98, "alias_exact"
        elif float(alias_score) > float(canonical_score):
            score, reason = float(alias_score), "alias_similar"
        else:
            score, reason = float(canonical_score), "canonical_similar"
        candidates.append(
            FoodMatchCandidate(
                food_item_id=food.id,
                catalog_revision=food.current_revision,
                name=food.name,
                brand=food.brand,
                source=food.source,
                source_reference=food.source_reference,
                nutrition_complete=food.nutrition_complete,
                score=round(score, 4),
                reason=reason,
            )
        )

    if not candidates:
        return FoodMatchDecision("no_match", None, ())
    runner_up = candidates[1].score if len(candidates) > 1 else 0.0
    ambiguous = len(candidates) > 1 and candidates[0].score - runner_up < AMBIGUITY_MARGIN
    preselected = (
        candidates[0].food_item_id
        if candidates[0].score >= PRESELECT_THRESHOLD and not ambiguous
        else None
    )
    return FoodMatchDecision(
        "ambiguous" if ambiguous else "review",
        preselected,
        tuple(candidates),
    )


def nutrition_ratio(food: FoodItem, amount: float | Decimal, unit: str) -> Decimal:
    if not food.nutrition_complete:
        raise ValueError("catalog nutrition is incomplete and requires manual input")
    amount_decimal = Decimal(str(amount))
    normalized_unit = normalize_catalog_text(unit)
    serving_unit = normalize_catalog_text(food.serving_unit) if food.serving_unit else None
    basis_quantity = food.nutrition_basis_quantity

    if food.nutrition_basis_unit == "g":
        if normalized_unit in {"g", "克"}:
            grams = amount_decimal
        elif normalized_unit in {"ml", "毫升"}:
            if food.density_g_per_ml is None:
                raise ValueError("ml cannot be converted to g without density")
            grams = amount_decimal * food.density_g_per_ml
        elif serving_unit is not None and normalized_unit == serving_unit and food.serving_weight_g:
            grams = amount_decimal * food.serving_weight_g
        else:
            raise ValueError("unit cannot be converted using this food revision")
        return grams / basis_quantity

    if food.nutrition_basis_unit == "ml":
        if normalized_unit in {"ml", "毫升"}:
            millilitres = amount_decimal
        elif normalized_unit in {"g", "克"}:
            if food.density_g_per_ml is None:
                raise ValueError("g cannot be converted to ml without density")
            millilitres = amount_decimal / food.density_g_per_ml
        else:
            raise ValueError("unit cannot be converted using this food revision")
        return millilitres / basis_quantity

    if serving_unit is not None and normalized_unit == serving_unit:
        return amount_decimal / basis_quantity
    if normalized_unit in {"g", "克"} and food.serving_weight_g:
        return amount_decimal / food.serving_weight_g / basis_quantity
    raise ValueError("serving-based nutrition requires the declared serving unit")
