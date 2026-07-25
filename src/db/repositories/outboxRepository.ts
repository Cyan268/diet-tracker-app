import type { SQLiteDatabase } from "expo-sqlite";
import { v4 as uuidv4 } from "uuid";
import type { FoodLog } from "@/types/log";
import type { OutboxEventRow } from "../rows";
import { getCurrentUserId } from "../accountScope";

export type OutboxOperation = OutboxEventRow["operation"];

export function buildLogSyncPayload(log: FoodLog): string {
  return JSON.stringify({
    client_id: log.id,
    log_date: log.date,
    meal_type: log.mealType,
    custom_name: log.customName ?? "饮食记录",
    amount: log.amount,
    unit: log.unit,
    nutrition: {
      kcal: log.kcal,
      protein: log.protein,
      fat: log.fat,
      carbs: log.carbs,
      sugar: log.sugar,
      sodium: log.sodium,
      caffeine: log.caffeine,
    },
    note: log.note ?? null,
  });
}

export async function enqueueLogEvent(
  db: SQLiteDatabase,
  log: FoodLog,
  operation: OutboxOperation,
  now: string,
  payloadOverride?: string
): Promise<void> {
  const ownerUserId = getCurrentUserId();
  const payload = payloadOverride ?? buildLogSyncPayload(log);
  const existingCreate = await db.getFirstAsync<{ id: string }>(
    `SELECT id FROM outbox_events
     WHERE owner_user_id = ? AND aggregate_type = 'food_log' AND aggregate_id = ?
       AND operation = 'create' AND status IN ('pending', 'failed')
     LIMIT 1`,
    ownerUserId,
    log.id
  );

  if (existingCreate && operation !== "delete") {
    await db.runAsync(
      `UPDATE outbox_events
       SET payload = ?, status = 'pending', next_attempt_at = ?, last_error = NULL, updated_at = ?
       WHERE id = ?`,
      payload,
      now,
      now,
      existingCreate.id
    );
    return;
  }

  if (existingCreate && operation === "delete") {
    await db.runAsync(
      "DELETE FROM outbox_events WHERE owner_user_id = ? AND aggregate_id = ?",
      ownerUserId,
      log.id
    );
    return;
  }

  await db.runAsync(
    `DELETE FROM outbox_events
     WHERE owner_user_id = ? AND aggregate_type = 'food_log' AND aggregate_id = ?
       AND operation = ? AND status IN ('pending', 'failed')`,
    ownerUserId,
    log.id,
    operation
  );
  await db.runAsync(
    `INSERT INTO outbox_events (
       id, owner_user_id, aggregate_type, aggregate_id, operation, payload,
       status, attempt_count, next_attempt_at, last_error, created_at, updated_at
     ) VALUES (?, ?, 'food_log', ?, ?, ?, 'pending', 0, ?, NULL, ?, ?)`,
    uuidv4(),
    ownerUserId,
    log.id,
    operation,
    payload,
    now,
    now,
    now
  );
}

export async function getReadyOutboxEvents(
  db: SQLiteDatabase,
  now: string,
  limit = 20
): Promise<OutboxEventRow[]> {
  const ownerUserId = getCurrentUserId();
  return db.getAllAsync<OutboxEventRow>(
    `SELECT * FROM outbox_events
     WHERE owner_user_id = ? AND status IN ('pending', 'failed') AND next_attempt_at <= ?
     ORDER BY created_at LIMIT ?`,
    ownerUserId,
    now,
    limit
  );
}
