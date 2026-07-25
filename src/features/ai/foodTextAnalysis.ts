import type { FoodTextAnalyzeResponse } from "@/api/types";
import type { FoodItem, NutritionInfo } from "@/types/nutrition";
import { calcByGram } from "@/features/food/foodCalculator";

export type ParsedFoodEntity = FoodTextAnalyzeResponse["entities"][number];

export interface ResolvedFoodEntity {
  entity: ParsedFoodEntity;
  food: FoodItem | null;
  grams: number | null;
  nutrition: NutritionInfo | null;
  issue: string | null;
}

function normalized(value: string): string {
  return value.replace(/[\s（）()]/g, "").toLocaleLowerCase("zh-CN");
}

export function amountToGrams(food: FoodItem, amount: number, unit: string): number | null {
  if (unit.toLocaleLowerCase("zh-CN") === "g" || unit === "克") return amount;
  if (food.servingUnit === unit && food.servingWeightG) return amount * food.servingWeightG;
  return null;
}

export function resolveFoodEntity(entity: ParsedFoodEntity, foods: FoodItem[]): ResolvedFoodEntity {
  const target = normalized(entity.normalized_name);
  const food = foods.find((item) => normalized(item.name) === target) ?? null;
  if (!food) {
    return {
      entity,
      food: null,
      grams: null,
      nutrition: null,
      issue: "本地食品库中没有匹配项，请改用手动记录。",
    };
  }
  const grams = amountToGrams(food, entity.amount, entity.unit);
  if (grams === null) {
    return {
      entity,
      food,
      grams: null,
      nutrition: null,
      issue: `无法把 ${entity.unit} 换算为克，请改用手动记录。`,
    };
  }
  return {
    entity,
    food,
    grams,
    nutrition: calcByGram(food, grams),
    issue: null,
  };
}
