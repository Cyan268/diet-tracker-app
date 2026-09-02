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
  payloadOverride?: string,
  ownerUserId = getCurrentUserId()
): Promise<void> {
  const payload = payloadOverride ?? buildLogSyncPayload(log);
  const existingCreate = await db.getFirstAsync<{ id: string; payload: string }>(
    `SELECT id, payload FROM outbox_events
     WHERE owner_user_id = ? AND aggregate_type = 'food_log' AND aggregate_id = ?
       AND operation = 'create' AND status = 'pending'
       AND first_attempt_at IS NULL AND attempt_count = 0
     LIMIT 1`,
    ownerUserId,
    log.id
  );

  if (existingCreate && operation !== "delete") {
    const content = JSON.parse(payload) as Record<string, unknown>;
    delete content.server_id;
    delete content.expected_version;
    content.client_id = JSON.parse(existingCreate.payload).client_id;
    await db.runAsync(
      `UPDATE outbox_events
       SET payload = ?, status = 'pending', next_attempt_at = ?, last_error = NULL, updated_at = ?
       WHERE id = ?`,
      JSON.stringify(content),
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
       AND (operation = ? OR (? = 'delete' AND operation = 'update'))
       AND status = 'pending' AND first_attempt_at IS NULL AND attempt_count = 0`,
    ownerUserId,
    log.id,
    operation,
    operation
  );
  await db.runAsync(
    `INSERT INTO outbox_events (
       id, owner_user_id, aggregate_type, aggregate_id, operation, payload,
       status, attempt_count, next_attempt_at, last_error, created_at, updated_at, queue_order
     ) VALUES (?, ?, 'food_log', ?, ?, ?, 'pending', 0, ?, NULL, ?, ?,
       (SELECT COALESCE(MAX(queue_order), 0) + 1 FROM outbox_events))`,
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
  limit = 20,
  ownerUserId = getCurrentUserId()
): Promise<OutboxEventRow[]> {
  return db.getAllAsync<OutboxEventRow>(
    `SELECT e.* FROM outbox_events e
     WHERE e.owner_user_id = ? AND e.status IN ('pending', 'failed') AND e.next_attempt_at <= ?
       AND NOT EXISTS (SELECT 1 FROM outbox_events p
         WHERE p.owner_user_id = e.owner_user_id AND p.aggregate_id = e.aggregate_id
           AND p.queue_order < e.queue_order)
     ORDER BY e.queue_order LIMIT ?`,
    ownerUserId,
    now,
    limit
  );
}
