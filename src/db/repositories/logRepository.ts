import { getDatabase } from "../database";
import type { DailySummaryRow, FoodLogRow, MealBreakdownRow, NutritionTotalsRow } from "../rows";
import { v4 as uuidv4 } from "uuid";
import type { FoodLog, DailySummary } from "@/types/log";
import { enqueueLogEvent } from "./outboxRepository";
import { getCurrentUserId } from "../accountScope";
import { withWriteTransaction } from "../transactions";

type BindValue = string | number | null;

function rowToFoodLog(row: FoodLogRow): FoodLog {
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

export type NewFoodLog = Omit<FoodLog, "id" | "createdAt" | "updatedAt">;

export async function addLogs(logs: NewFoodLog[]): Promise<FoodLog[]> {
  if (logs.length === 0) return [];
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  const now = new Date().toISOString();
  const createdLogs = logs.map((log) => ({
    ...log,
    id: uuidv4(),
    createdAt: now,
    updatedAt: now,
  }));

  await withWriteTransaction(db, async (txn) => {
    for (const createdLog of createdLogs) {
      await txn.runAsync(
        `INSERT INTO food_logs (id, owner_user_id, date, meal_type, food_item_id, custom_name, amount, unit, kcal, protein, fat, carbs, sugar, sodium, caffeine, note, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        createdLog.id,
        ownerUserId,
        createdLog.date,
        createdLog.mealType,
        createdLog.foodItemId ?? null,
        createdLog.customName ?? null,
        createdLog.amount,
        createdLog.unit,
        createdLog.kcal,
        createdLog.protein,
        createdLog.fat,
        createdLog.carbs,
        createdLog.sugar,
        createdLog.sodium,
        createdLog.caffeine,
        createdLog.note ?? null,
        now,
        now
      );
      await enqueueLogEvent(txn, createdLog, "create", now);
    }
  });

  return createdLogs;
}

export async function addLog(log: NewFoodLog): Promise<FoodLog> {
  const [created] = await addLogs([log]);
  return created;
}

export async function getLogById(id: string): Promise<FoodLog | null> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<FoodLogRow>(
    "SELECT * FROM food_logs WHERE id = ? AND owner_user_id = ?",
    id,
    getCurrentUserId()
  );
  return row ? rowToFoodLog(row) : null;
}

export async function getLogsByDate(date: string): Promise<FoodLog[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<FoodLogRow>(
    "SELECT * FROM food_logs WHERE date = ? AND owner_user_id = ? ORDER BY created_at",
    date,
    getCurrentUserId()
  );
  return rows.map(rowToFoodLog);
}

export async function getDailySummary(date: string): Promise<DailySummary> {
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  const row = await db.getFirstAsync<NutritionTotalsRow>(
    `SELECT
       COALESCE(SUM(kcal), 0) as total_kcal,
       COALESCE(SUM(protein), 0) as total_protein,
       COALESCE(SUM(fat), 0) as total_fat,
       COALESCE(SUM(carbs), 0) as total_carbs,
       COALESCE(SUM(sugar), 0) as total_sugar,
       COALESCE(SUM(sodium), 0) as total_sodium,
       COALESCE(SUM(caffeine), 0) as total_caffeine
     FROM food_logs WHERE date = ? AND owner_user_id = ?`,
    date,
    ownerUserId
  );

  const mealRows = await db.getAllAsync<MealBreakdownRow>(
    `SELECT meal_type, COALESCE(SUM(kcal), 0) as total
     FROM food_logs WHERE date = ? AND owner_user_id = ? GROUP BY meal_type`,
    date,
    ownerUserId
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
  updates: Partial<
    Omit<
      Pick<
        FoodLog,
        | "amount"
        | "unit"
        | "kcal"
        | "protein"
        | "fat"
        | "carbs"
        | "sugar"
        | "sodium"
        | "caffeine"
        | "note"
      >,
      "note"
    >
  > & { note?: string | null }
): Promise<FoodLog | null> {
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  let result: FoodLog | null = null;
  await withWriteTransaction(db, async (txn) => {
    const existing = await txn.getFirstAsync<FoodLogRow>(
      "SELECT * FROM food_logs WHERE id = ? AND owner_user_id = ?",
      id,
      ownerUserId
    );
    if (!existing) return;

    const now = new Date().toISOString();
    const fields: string[] = [];
    const values: BindValue[] = [];

    if (updates.amount !== undefined) {
      fields.push("amount = ?");
      values.push(updates.amount);
    }
    if (updates.unit !== undefined) {
      fields.push("unit = ?");
      values.push(updates.unit);
    }
    if (updates.kcal !== undefined) {
      fields.push("kcal = ?");
      values.push(updates.kcal);
    }
    if (updates.protein !== undefined) {
      fields.push("protein = ?");
      values.push(updates.protein);
    }
    if (updates.fat !== undefined) {
      fields.push("fat = ?");
      values.push(updates.fat);
    }
    if (updates.carbs !== undefined) {
      fields.push("carbs = ?");
      values.push(updates.carbs);
    }
    if (updates.sugar !== undefined) {
      fields.push("sugar = ?");
      values.push(updates.sugar);
    }
    if (updates.sodium !== undefined) {
      fields.push("sodium = ?");
      values.push(updates.sodium);
    }
    if (updates.caffeine !== undefined) {
      fields.push("caffeine = ?");
      values.push(updates.caffeine);
    }
    if (updates.note !== undefined) {
      fields.push("note = ?");
      values.push(updates.note ?? null);
    }

    if (fields.length === 0) {
      result = rowToFoodLog(existing);
      return;
    }

    fields.push("updated_at = ?", "sync_status = 'pending'", "last_sync_error = NULL");
    values.push(now, id, ownerUserId);
    await txn.runAsync(
      `UPDATE food_logs SET ${fields.join(", ")} WHERE id = ? AND owner_user_id = ?`,
      ...values
    );

    const updated = await txn.getFirstAsync<FoodLogRow>(
      "SELECT * FROM food_logs WHERE id = ? AND owner_user_id = ?",
      id,
      ownerUserId
    );
    if (!updated) return;
    result = rowToFoodLog(updated);
    await enqueueLogEvent(txn, result, "update", now);
  });
  return result;
}

export async function deleteLog(id: string): Promise<void> {
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  await withWriteTransaction(db, async (txn) => {
    const existing = await txn.getFirstAsync<FoodLogRow>(
      "SELECT * FROM food_logs WHERE id = ? AND owner_user_id = ?",
      id,
      ownerUserId
    );
    if (!existing) return;
    const log = rowToFoodLog(existing);
    const now = new Date().toISOString();
    const deletePayload = JSON.stringify({
      server_id: existing.server_id,
      expected_version: existing.server_version,
    });
    await enqueueLogEvent(txn, log, "delete", now, deletePayload);
    await txn.runAsync("DELETE FROM food_logs WHERE id = ? AND owner_user_id = ?", id, ownerUserId);
  });
}

export async function getSummariesByDateRange(
  startDate: string,
  endDate: string
): Promise<DailySummary[]> {
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  const rows = await db.getAllAsync<DailySummaryRow>(
    `SELECT date,
       COALESCE(SUM(kcal), 0) as total_kcal,
       COALESCE(SUM(protein), 0) as total_protein,
       COALESCE(SUM(fat), 0) as total_fat,
       COALESCE(SUM(carbs), 0) as total_carbs,
       COALESCE(SUM(sugar), 0) as total_sugar,
       COALESCE(SUM(sodium), 0) as total_sodium,
       COALESCE(SUM(caffeine), 0) as total_caffeine
     FROM food_logs WHERE owner_user_id = ? AND date >= ? AND date <= ?
     GROUP BY date ORDER BY date`,
    ownerUserId,
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
  const rows = await db.getAllAsync<MealBreakdownRow>(
    `SELECT meal_type, COALESCE(SUM(kcal), 0) as total
     FROM food_logs WHERE date = ? AND owner_user_id = ? GROUP BY meal_type`,
    date,
    getCurrentUserId()
  );
  return rows.map((r) => ({ mealType: r.meal_type, kcal: r.total }));
}
