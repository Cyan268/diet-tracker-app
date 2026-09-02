import re
from dataclasses import dataclass

from app.ai.provider import ProviderResult
from app.schemas.ai import FoodTextAnalyzeRequest, ParsedFoodEntity
from app.schemas.diet import MealType


@dataclass(frozen=True)
class FoodAlias:
    normalized_name: str
    aliases: tuple[str, ...]
    default_unit: str


FOOD_ALIASES = (
    FoodAlias("白米饭", ("白米饭", "米饭"), "碗"),
    FoodAlias("面条（煮熟）", ("煮面条", "面条", "面"), "碗"),
    FoodAlias("馒头", ("馒头",), "个"),
    FoodAlias("全麦面包", ("全麦面包", "面包"), "片"),
    FoodAlias("鸡蛋（煮）", ("水煮鸡蛋", "煮鸡蛋", "水煮蛋", "鸡蛋"), "个"),
    FoodAlias("牛奶（全脂）", ("全脂牛奶", "牛奶"), "杯"),
    FoodAlias("酸奶（原味）", ("原味酸奶", "酸奶"), "杯"),
    FoodAlias("苹果", ("苹果",), "个"),
    FoodAlias("香蕉", ("香蕉",), "根"),
    FoodAlias("橙子", ("橙子", "橙"), "个"),
    FoodAlias("鸡胸肉（水煮）", ("水煮鸡胸肉", "鸡胸肉"), "份"),
    FoodAlias("猪肉（瘦）", ("瘦猪肉", "猪肉"), "份"),
    FoodAlias("牛肉（瘦）", ("瘦牛肉", "牛肉"), "份"),
    FoodAlias("豆腐", ("豆腐",), "块"),
    FoodAlias("西兰花", ("西兰花",), "份"),
    FoodAlias("番茄", ("西红柿", "番茄"), "个"),
    FoodAlias("黄瓜", ("黄瓜",), "根"),
    FoodAlias("薯片", ("薯片",), "小包"),
    FoodAlias("巧克力", ("巧克力",), "块"),
    FoodAlias("坚果（混合）", ("混合坚果", "坚果"), "小把"),
)

UNIT_PATTERN = "克|g|千克|kg|碗|个|根|杯|份|片|块|小包|包|小把"
NUMBER_PATTERN = r"\d+(?:\.\d+)?"


def _normalize_chinese_quantities(text: str) -> str:
    replacements = {
        "半碗": "0.5碗",
        "半杯": "0.5杯",
        "半个": "0.5个",
        "一碗": "1碗",
        "一个": "1个",
        "一根": "1根",
        "一杯": "1杯",
        "一份": "1份",
        "一片": "1片",
        "一块": "1块",
        "一包": "1包",
        "一小把": "1小把",
        "两碗": "2碗",
        "两个": "2个",
        "两根": "2根",
        "两杯": "2杯",
        "两份": "2份",
        "两片": "2片",
        "两块": "2块",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _detect_meal_type(text: str, hint: MealType | None) -> MealType:
    rules = (
        (MealType.BREAKFAST, ("早餐", "早饭", "早上")),
        (MealType.LUNCH, ("午餐", "午饭", "中午")),
        (MealType.DINNER, ("晚餐", "晚饭", "晚上")),
        (MealType.SNACK, ("加餐", "零食", "夜宵")),
    )
    for meal_type, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return meal_type
    return hint or MealType.SNACK


def _quantity_near_alias(text: str, alias: str, default_unit: str) -> tuple[float, str, bool]:
    escaped_alias = re.escape(alias)
    before = re.search(
        rf"(?P<amount>{NUMBER_PATTERN})\s*(?P<unit>{UNIT_PATTERN})?\s*{escaped_alias}",
        text,
    )
    after = re.search(
        rf"{escaped_alias}\s*(?P<amount>{NUMBER_PATTERN})\s*(?P<unit>{UNIT_PATTERN})?",
        text,
    )
    match = before or after
    if match is None:
        return 1, default_unit, True
    amount = float(match.group("amount"))
    unit = match.group("unit") or default_unit
    if unit == "克":
        unit = "g"
    elif unit == "千克" or unit == "kg":
        amount *= 1000
        unit = "g"
    elif unit == "包" and default_unit == "小包":
        unit = "小包"
    return amount, unit, False


class RuleBasedFoodTextProvider:
    """A deterministic development provider implementing the production provider contract."""

    name = "rule_based_v1"
    model = "rule-based-v1"
    prompt_version = "rule-food-text-v1.0.0"

    async def extract(self, request: FoodTextAnalyzeRequest) -> ProviderResult:
        text = _normalize_chinese_quantities(request.text.strip())
        meal_type = _detect_meal_type(text, request.meal_type_hint)
        occupied: list[tuple[int, int]] = []
        entities: list[ParsedFoodEntity] = []

        candidates = sorted(
            ((alias, definition) for definition in FOOD_ALIASES for alias in definition.aliases),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        matched_foods: set[str] = set()
        for alias, definition in candidates:
            if definition.normalized_name in matched_foods:
                continue
            match = re.search(re.escape(alias), text)
            if match is None:
                continue
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            amount, unit, inferred_quantity = _quantity_near_alias(
                text, alias, definition.default_unit
            )
            entities.append(
                ParsedFoodEntity(
                    raw_name=alias,
                    normalized_name=definition.normalized_name,
                    amount=amount,
                    unit=unit,
                    meal_type=meal_type,
                    confidence=0.68 if inferred_quantity else 0.94,
                    needs_review=inferred_quantity,
                    evidence=(
                        f"识别到“{alias}”，未检测到数量，暂按 1{definition.default_unit}"
                        if inferred_quantity
                        else f"识别到“{alias}”及其相邻数量"
                    ),
                )
            )
            occupied.append((match.start(), match.end()))
            matched_foods.add(definition.normalized_name)

        return ProviderResult(entities=entities, model=self.model)
