import { getDatabase } from "../database";
import { v4 as uuidv4 } from "uuid";
import type { FoodLog, DailySummary } from "@/types/log";

function rowToFoodLog(row: any): FoodLog {
  return {
    id: row.id,
    date: row.date,
    mealType: row.meal_type,
    foodItemId: row.food_item_id ?? undefined,
    customName: row.custom_name ?? undefined,
    amount: row.amount,
    unit: row.unit,
    kcal: row.kcal,
    protein: row.protein,
    fat: row.fat,
    carbs: row.carbs,
    sugar: row.sugar,
    sodium: row.sodium,
    caffeine: row.caffeine,
    note: row.note ?? undefined,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export async function addLog(
  log: Omit<FoodLog, "id" | "createdAt" | "updatedAt">
): Promise<FoodLog> {
  const db = await getDatabase();
  const id = uuidv4();
  const now = new Date().toISOString();

  await db.runAsync(
    `INSERT INTO food_logs (id, date, meal_type, food_item_id, custom_name, amount, unit, kcal, protein, fat, carbs, sugar, sodium, caffeine, note, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    id,
    log.date,
    log.mealType,
    log.foodItemId ?? null,
    log.customName ?? null,
    log.amount,
    log.unit,
    log.kcal,
    log.protein,
    log.fat,
    log.carbs,
    log.sugar,
    log.sodium,
    log.caffeine,
    log.note ?? null,
    now,
    now
  );

  return { ...log, id, createdAt: now, updatedAt: now };
}

export async function getLogById(id: string): Promise<FoodLog | null> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<any>("SELECT * FROM food_logs WHERE id = ?", id);
  return row ? rowToFoodLog(row) : null;
}

export async function getLogsByDate(date: string): Promise<FoodLog[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<any>(
    "SELECT * FROM food_logs WHERE date = ? ORDER BY created_at",
    date
  );
  return rows.map(rowToFoodLog);
}

export async function getDailySummary(date: string): Promise<DailySummary> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<any>(
    `SELECT
       COALESCE(SUM(kcal), 0) as total_kcal,
       COALESCE(SUM(protein), 0) as total_protein,
       COALESCE(SUM(fat), 0) as total_fat,
       COALESCE(SUM(carbs), 0) as total_carbs,
       COALESCE(SUM(sugar), 0) as total_sugar,
       COALESCE(SUM(sodium), 0) as total_sodium,
       COALESCE(SUM(caffeine), 0) as total_caffeine
     FROM food_logs WHERE date = ?`,
    date
  );

  const mealRows = await db.getAllAsync<any>(
    `SELECT meal_type, COALESCE(SUM(kcal), 0) as total
     FROM food_logs WHERE date = ? GROUP BY meal_type`,
    date
  );

  const mealBreakdown = {
    breakfast: 0,
    lunch: 0,
    dinner: 0,
    snack: 0,
    drink: 0,
  };
  for (const r of mealRows) {
    if (r.meal_type in mealBreakdown) {
      mealBreakdown[r.meal_type as keyof typeof mealBreakdown] = r.total;
    }
  }

  return {
    date,
    totalKcal: row?.total_kcal ?? 0,
    totalProtein: row?.total_protein ?? 0,
    totalFat: row?.total_fat ?? 0,
    totalCarbs: row?.total_carbs ?? 0,
    totalSugar: row?.total_sugar ?? 0,
    totalSodium: row?.total_sodium ?? 0,
    totalCaffeine: row?.total_caffeine ?? 0,
    mealBreakdown,
  };
}

export async function updateLog(
  id: string,
  updates: Partial<Pick<FoodLog, "amount" | "unit" | "kcal" | "protein" | "fat" | "carbs" | "sugar" | "sodium" | "caffeine" | "note">>
): Promise<FoodLog | null> {
  const db = await getDatabase();
  const existing = await db.getFirstAsync<any>("SELECT * FROM food_logs WHERE id = ?", id);
  if (!existing) return null;

  const now = new Date().toISOString();
  const fields: string[] = [];
  const values: any[] = [];

  if (updates.amount !== undefined) { fields.push("amount = ?"); values.push(updates.amount); }
  if (updates.unit !== undefined) { fields.push("unit = ?"); values.push(updates.unit); }
  if (updates.kcal !== undefined) { fields.push("kcal = ?"); values.push(updates.kcal); }
  if (updates.protein !== undefined) { fields.push("protein = ?"); values.push(updates.protein); }
  if (updates.fat !== undefined) { fields.push("fat = ?"); values.push(updates.fat); }
  if (updates.carbs !== undefined) { fields.push("carbs = ?"); values.push(updates.carbs); }
  if (updates.sugar !== undefined) { fields.push("sugar = ?"); values.push(updates.sugar); }
  if (updates.sodium !== undefined) { fields.push("sodium = ?"); values.push(updates.sodium); }
  if (updates.caffeine !== undefined) { fields.push("caffeine = ?"); values.push(updates.caffeine); }
  if (updates.note !== undefined) { fields.push("note = ?"); values.push(updates.note); }

  if (fields.length === 0) return rowToFoodLog(existing);

  fields.push("updated_at = ?");
  values.push(now);
  values.push(id);

  await db.runAsync(
    `UPDATE food_logs SET ${fields.join(", ")} WHERE id = ?`,
    ...values
  );

  const updated = await db.getFirstAsync<any>("SELECT * FROM food_logs WHERE id = ?", id);
  return updated ? rowToFoodLog(updated) : null;
}

export async function deleteLog(id: string): Promise<void> {
  const db = await getDatabase();
  await db.runAsync("DELETE FROM food_logs WHERE id = ?", id);
}

export async function getSummariesByDateRange(
  startDate: string,
  endDate: string
): Promise<DailySummary[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<any>(
    `SELECT date,
       COALESCE(SUM(kcal), 0) as total_kcal,
       COALESCE(SUM(protein), 0) as total_protein,
       COALESCE(SUM(fat), 0) as total_fat,
       COALESCE(SUM(carbs), 0) as total_carbs,
       COALESCE(SUM(sugar), 0) as total_sugar,
       COALESCE(SUM(sodium), 0) as total_sodium,
       COALESCE(SUM(caffeine), 0) as total_caffeine
     FROM food_logs WHERE date >= ? AND date <= ?
     GROUP BY date ORDER BY date`,
    startDate,
    endDate
  );

  return rows.map((row) => ({
    date: row.date,
    totalKcal: row.total_kcal,
    totalProtein: row.total_protein,
    totalFat: row.total_fat,
    totalCarbs: row.total_carbs,
    totalSugar: row.total_sugar,
    totalSodium: row.total_sodium,
    totalCaffeine: row.total_caffeine,
    mealBreakdown: { breakfast: 0, lunch: 0, dinner: 0, snack: 0, drink: 0 },
  }));
}

export async function getMealBreakdownByDate(
  date: string
): Promise<{ mealType: string; kcal: number }[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<any>(
    `SELECT meal_type, COALESCE(SUM(kcal), 0) as total
     FROM food_logs WHERE date = ? GROUP BY meal_type`,
    date
  );
  return rows.map((r) => ({ mealType: r.meal_type, kcal: r.total }));
}
