import type { SyncChangeResponse } from "@/api/types";
import { getCurrentUserId } from "@/db/accountScope";
import { getDatabase } from "@/db/database";
import type { FoodLogRow, OutboxEventRow, SyncConflictRow } from "@/db/rows";
import { buildLogSyncPayload } from "@/db/repositories/outboxRepository";
import { upsertRemoteLog } from "@/features/sync/pullSyncService";
import type { FoodLog } from "@/types/log";
import { withWriteTransaction } from "@/db/transactions";

export interface SyncConflict {
  id: string;
  aggregateId: string;
  remoteOperation: "upsert" | "delete";
  remote: SyncChangeResponse;
  local: FoodLog | null;
}

function rowToLog(row: FoodLogRow): FoodLog {
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

export async function countSyncConflicts(): Promise<number> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<{ count: number }>(
    "SELECT COUNT(*) AS count FROM sync_conflicts WHERE owner_user_id = ?",
    getCurrentUserId()
  );
  return row?.count ?? 0;
}

export async function listSyncConflicts(): Promise<SyncConflict[]> {
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  const rows = await db.getAllAsync<SyncConflictRow>(
    `SELECT * FROM sync_conflicts
     WHERE owner_user_id = ? ORDER BY updated_at DESC`,
    ownerUserId
  );
  return Promise.all(
    rows.map(async (row) => {
      const local = await db.getFirstAsync<FoodLogRow>(
        "SELECT * FROM food_logs WHERE owner_user_id = ? AND id = ?",
        ownerUserId,
        row.aggregate_id
      );
      return {
        id: row.id,
        aggregateId: row.aggregate_id,
        remoteOperation: row.remote_operation,
        remote: JSON.parse(row.remote_payload) as SyncChangeResponse,
        local: local ? rowToLog(local) : null,
      };
    })
  );
}

async function getConflictAndEvent(
  conflictId: string
): Promise<{ conflict: SyncConflictRow; event: OutboxEventRow; local: FoodLogRow | null }> {
  const db = await getDatabase();
  const ownerUserId = getCurrentUserId();
  const conflict = await db.getFirstAsync<SyncConflictRow>(
    "SELECT * FROM sync_conflicts WHERE id = ? AND owner_user_id = ?",
    conflictId,
    ownerUserId
  );
  if (!conflict) throw new Error("sync conflict not found");
  const event = await db.getFirstAsync<OutboxEventRow>(
    `SELECT * FROM outbox_events
     WHERE owner_user_id = ? AND aggregate_id = ? ORDER BY created_at LIMIT 1`,
    ownerUserId,
    conflict.aggregate_id
  );
  if (!event) throw new Error("local sync event not found");
  const local = await db.getFirstAsync<FoodLogRow>(
    "SELECT * FROM food_logs WHERE owner_user_id = ? AND id = ?",
    ownerUserId,
    conflict.aggregate_id
  );
  return { conflict, event, local };
}

export async function acceptRemoteVersion(conflictId: string): Promise<void> {
  const { conflict } = await getConflictAndEvent(conflictId);
  const remote = JSON.parse(conflict.remote_payload) as SyncChangeResponse;
  const db = await getDatabase();
  await withWriteTransaction(db, async (txn) => {
    await txn.runAsync(
      "DELETE FROM outbox_events WHERE owner_user_id = ? AND aggregate_id = ?",
      conflict.owner_user_id,
      conflict.aggregate_id
    );
    if (remote.operation === "upsert") {
      await upsertRemoteLog(txn, conflict.owner_user_id, conflict.aggregate_id, remote);
    } else {
      await txn.runAsync(
        "DELETE FROM food_logs WHERE owner_user_id = ? AND id = ?",
        conflict.owner_user_id,
        conflict.aggregate_id
      );
    }
    await txn.runAsync("DELETE FROM sync_conflicts WHERE id = ?", conflict.id);
  });
}

export async function keepLocalVersion(conflictId: string): Promise<void> {
  const { conflict, event, local } = await getConflictAndEvent(conflictId);
  const remote = JSON.parse(conflict.remote_payload) as SyncChangeResponse;
  const db = await getDatabase();
  const now = new Date().toISOString();
  await withWriteTransaction(db, async (txn) => {
    if (remote.operation === "upsert") {
      if (event.operation === "delete") {
        await txn.runAsync(
          `UPDATE outbox_events
           SET payload = json_set(payload, '$.server_id', ?, '$.expected_version', ?),
               status = 'pending', attempt_count = 0, next_attempt_at = ?,
               last_error = NULL, updated_at = ?
           WHERE id = ?`,
          remote.server_id,
          remote.version,
          now,
          now,
          event.id
        );
      } else {
        if (!local) throw new Error("local record not found");
        await txn.runAsync(
          `UPDATE food_logs
           SET server_id = ?, server_version = ?, sync_status = 'pending', last_sync_error = NULL
           WHERE id = ? AND owner_user_id = ?`,
          remote.server_id,
          remote.version,
          local.id,
          conflict.owner_user_id
        );
        await txn.runAsync(
          `UPDATE outbox_events
           SET operation = 'update', status = 'pending', attempt_count = 0,
               next_attempt_at = ?, last_error = NULL, updated_at = ?
           WHERE id = ?`,
          now,
          now,
          event.id
        );
      }
    } else {
      if (!local) throw new Error("local record not found");
      await txn.runAsync(
        `UPDATE food_logs
         SET server_id = NULL, server_version = NULL,
             sync_status = 'pending', last_sync_error = NULL
         WHERE id = ? AND owner_user_id = ?`,
        local.id,
        conflict.owner_user_id
      );
      await txn.runAsync(
        `UPDATE outbox_events
         SET operation = 'create', payload = ?, status = 'pending', attempt_count = 0,
             next_attempt_at = ?, last_error = NULL, updated_at = ?
         WHERE id = ?`,
        buildLogSyncPayload(rowToLog(local)),
        now,
        now,
        event.id
      );
    }
    await txn.runAsync("DELETE FROM sync_conflicts WHERE id = ?", conflict.id);
  });
}
