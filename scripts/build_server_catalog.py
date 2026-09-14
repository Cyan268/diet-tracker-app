"""Build the versioned backend catalog from the checked-in client seed data."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON_FOODS_PATH = ROOT / "assets" / "seed" / "seed-foods.json"
DRINK_CATALOG_PATH = ROOT / "src" / "data" / "drinkCatalog.ts"
OUTPUT_PATH = ROOT / "backend" / "app" / "catalog" / "catalog-2026-09-08-v1.json"
DRINK_PATTERN = re.compile(
    r'^\s*drink\("(?P<brand>[^"]+)",\s*"(?P<name>[^"]+)",\s*'
    r"(?P<kcal>\d+),\s*(?P<sugar>\d+),\s*(?P<caffeine>\d+),\s*"
    r'"(?P<milk_mode>none|fixed|choice)"\),\s*$'
)

ALIASES = {
    "番茄": ["西红柿"],
    "鸡蛋（煮）": ["水煮蛋", "白煮蛋"],
    "牛奶（全脂）": ["全脂牛奶"],
    "酸奶（原味）": ["原味酸奶"],
    "鸡胸肉（水煮）": ["水煮鸡胸肉"],
    "猪肉（瘦）": ["瘦猪肉"],
    "牛肉（瘦）": ["瘦牛肉"],
    "坚果（混合）": ["混合坚果"],
}
BRAND_ALIASES = {
    "1点点": ["一点点"],
    "CoCo都可": ["coco", "都可"],
    "Manner Coffee": ["manner"],
    "M Stand": ["mstand"],
    "瑞幸咖啡": ["瑞幸", "luckin"],
}


def build_catalog() -> dict[str, object]:
    common_foods = json.loads(COMMON_FOODS_PATH.read_text(encoding="utf-8"))
    items: list[dict[str, object]] = []
    for food in common_foods:
        items.append(
            {
                "name": food["name"],
                "brand": None,
                "category": food["category"],
                "aliases": ALIASES.get(food["name"], []),
                "basisUnit": "g",
                "basisQuantity": 100,
                "servingUnit": food["servingUnit"],
                "servingWeightG": food["servingWeightG"],
                "densityGPerMl": None,
                "nutritionComplete": True,
                "kcal": food["kcalPer100g"],
                "proteinG": food["proteinPer100g"],
                "fatG": food["fatPer100g"],
                "carbsG": food["carbsPer100g"],
                "sugarG": food["sugarPer100g"],
                "sodiumMg": food["sodiumPer100g"],
                "caffeineMg": 0,
                "source": "curated_estimate",
                "sourceReference": "assets/seed/seed-foods.json@2026-09-08",
            }
        )

    for line in DRINK_CATALOG_PATH.read_text(encoding="utf-8").splitlines():
        match = DRINK_PATTERN.match(line)
        if match is None:
            continue
        values = match.groupdict()
        brand = values["brand"]
        name = values["name"]
        aliases = [f"{alias}{name}" for alias in BRAND_ALIASES.get(brand, [])]
        items.append(
            {
                "name": name,
                "brand": brand,
                "category": "现制饮品",
                "aliases": aliases,
                "basisUnit": "serving",
                "basisQuantity": 1,
                "servingUnit": "标准杯",
                "servingWeightG": None,
                "densityGPerMl": None,
                "nutritionComplete": False,
                "kcal": int(values["kcal"]),
                "proteinG": 0,
                "fatG": 0,
                "carbsG": 0,
                "sugarG": int(values["sugar"]),
                "sodiumMg": 0,
                "caffeineMg": int(values["caffeine"]),
                "source": "client_estimate",
                "sourceReference": "src/data/drinkCatalog.ts@2026-07-17",
            }
        )

    return {
        "revision": "catalog-2026-09-08-v1",
        "description": (
            "NutriPilot curated seed. Branded drinks are non-official estimates and "
            "remain blocked from nutrition logging until all required nutrients are known."
        ),
        "items": items,
    }


def main() -> None:
    catalog = build_catalog()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(catalog['items'])} items to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
