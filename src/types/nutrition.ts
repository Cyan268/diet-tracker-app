export interface NutritionInfo {
  kcal: number;
  protein: number;
  fat: number;
  carbs: number;
  sugar: number;
  sodium: number;
  caffeine: number;
}

export interface FoodItem extends NutritionInfo {
  id: string;
  name: string;
  brand?: string;
  category?: string;
  servingUnit?: string;
  servingWeightG?: number;
  kcalPer100g: number;
  proteinPer100g: number;
  fatPer100g: number;
  carbsPer100g: number;
  sugarPer100g: number;
  sodiumPer100g: number;
  caffeinePer100g: number;
  source?: string;
  createdAt: string;
  updatedAt: string;
}
