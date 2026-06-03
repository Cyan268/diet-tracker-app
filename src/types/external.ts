export interface ExternalFoodResult {
  name: string;
  brand?: string;
  category?: string;
  kcalPer100g: number;
  proteinPer100g: number;
  fatPer100g: number;
  carbsPer100g: number;
  sugarPer100g: number;
  sodiumPer100g: number;
  caffeinePer100g: number;
  source: string;
  externalId?: string;
}
