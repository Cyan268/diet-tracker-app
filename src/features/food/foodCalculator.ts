import type { FoodItem, NutritionInfo } from "@/types/nutrition";

export function calcByGram(food: FoodItem, gram: number): NutritionInfo {
  const ratio = gram / 100;
  return {
    kcal: food.kcalPer100g * ratio,
    protein: food.proteinPer100g * ratio,
    fat: food.fatPer100g * ratio,
    carbs: food.carbsPer100g * ratio,
    sugar: food.sugarPer100g * ratio,
    sodium: food.sodiumPer100g * ratio,
    caffeine: food.caffeinePer100g * ratio,
  };
}
