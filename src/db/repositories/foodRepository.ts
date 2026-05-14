import { getDatabase } from "../database";
import type { FoodItem } from "@/types/nutrition";

function rowToFoodItem(row: any): FoodItem {
  return {
    id: row.id,
    name: row.name,
    brand: row.brand ?? undefined,
    category: row.category ?? undefined,
    servingUnit: row.serving_unit ?? undefined,
    servingWeightG: row.serving_weight_g ?? undefined,
    kcalPer100g: row.kcal_per_100g,
    proteinPer100g: row.protein_per_100g,
    fatPer100g: row.fat_per_100g,
    carbsPer100g: row.carbs_per_100g,
    sugarPer100g: row.sugar_per_100g,
    sodiumPer100g: row.sodium_per_100g,
    caffeinePer100g: row.caffeine_per_100g,
    source: row.source ?? undefined,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    kcal: 0,
    protein: 0,
    fat: 0,
    carbs: 0,
    sugar: 0,
    sodium: 0,
    caffeine: 0,
  };
}

export async function getAllFoods(): Promise<FoodItem[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<any>("SELECT * FROM food_items ORDER BY name");
  return rows.map(rowToFoodItem);
}

export async function searchFoods(keyword: string): Promise<FoodItem[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<any>(
    "SELECT * FROM food_items WHERE name LIKE ? ORDER BY name",
    `%${keyword}%`
  );
  return rows.map(rowToFoodItem);
}

export async function getFoodById(id: string): Promise<FoodItem | null> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<any>("SELECT * FROM food_items WHERE id = ?", id);
  return row ? rowToFoodItem(row) : null;
}
