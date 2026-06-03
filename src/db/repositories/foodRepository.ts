import { getDatabase } from "../database";
import { v4 as uuidv4 } from "uuid";
import type { FoodItem } from "@/types/nutrition";
import type { ExternalFoodResult } from "@/types/external";

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

export async function saveExternalFood(result: ExternalFoodResult): Promise<FoodItem> {
  const db = await getDatabase();
  const now = new Date().toISOString();

  // Check if already cached by name+source
  const existing = await db.getFirstAsync<any>(
    "SELECT * FROM food_items WHERE source = ? AND name = ?",
    result.source,
    result.name
  );

  if (existing) return rowToFoodItem(existing);

  const id = uuidv4();
  await db.runAsync(
    `INSERT INTO food_items (id, name, brand, category, serving_unit, serving_weight_g, kcal_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, sugar_per_100g, sodium_per_100g, caffeine_per_100g, source, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    id,
    result.name,
    result.brand ?? null,
    result.category ?? null,
    null,
    null,
    result.kcalPer100g,
    result.proteinPer100g,
    result.fatPer100g,
    result.carbsPer100g,
    result.sugarPer100g,
    result.sodiumPer100g,
    result.caffeinePer100g,
    result.source,
    now,
    now
  );

  return rowToFoodItem({
    id,
    name: result.name,
    brand: result.brand ?? null,
    category: result.category ?? null,
    serving_unit: null,
    serving_weight_g: null,
    kcal_per_100g: result.kcalPer100g,
    protein_per_100g: result.proteinPer100g,
    fat_per_100g: result.fatPer100g,
    carbs_per_100g: result.carbsPer100g,
    sugar_per_100g: result.sugarPer100g,
    sodium_per_100g: result.sodiumPer100g,
    caffeine_per_100g: result.caffeinePer100g,
    source: result.source,
    created_at: now,
    updated_at: now,
  });
}
