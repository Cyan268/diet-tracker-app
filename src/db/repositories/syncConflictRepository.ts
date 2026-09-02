import type { SyncChangeResponse } from "@/api/types";
import { getCurrentUserId } from "@/db/accountScope";
import { getDatabase } from "@/db/database";
import type { FoodLogRow, OutboxEventRow, SyncConflictRow } from "@/db/rows";
import type { SQLiteDatabase } from "expo-sqlite";
import { v4 as uuidv4 } from "uuid";
import { buildLogSyncPayload, enqueueLogEvent } from "@/db/repositories/outboxRepository";
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
  db: SQLiteDatabase,
  ownerUserId: string,
  conflictId: string
): Promise<{ conflict: SyncConflictRow; event: OutboxEventRow; local: FoodLogRow | null }> {
  const conflict = await db.getFirstAsync<SyncConflictRow>(
    "SELECT * FROM sync_conflicts WHERE id = ? AND owner_user_id = ?",
    conflictId,
    ownerUserId
  );
  if (!conflict) throw new Error("sync conflict not found");
  const event = await db.getFirstAsync<OutboxEventRow>(
    `SELECT * FROM outbox_events
     WHERE owner_user_id = ? AND aggregate_id = ? ORDER BY queue_order DESC LIMIT 1`,
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
  const ownerUserId = getCurrentUserId();
  const db = await getDatabase();
  await withWriteTransaction(db, async (txn) => {
    const { conflict } = await getConflictAndEvent(txn, ownerUserId, conflictId);
    const remote = JSON.parse(conflict.remote_payload) as SyncChangeResponse;
    await txn.runAsync(
      "DELETE FROM outbox_events WHERE owner_user_id = ? AND aggregate_id = ?",
      ownerUserId,
      conflict.aggregate_id
    );
    if (remote.operation === "upsert") {
      await upsertRemoteLog(txn, ownerUserId, conflict.aggregate_id, remote);
    } else {
      await txn.runAsync(
        "DELETE FROM food_logs WHERE owner_user_id = ? AND id = ?",
        ownerUserId,
        conflict.aggregate_id
      );
    }
    await txn.runAsync(
      "DELETE FROM sync_conflicts WHERE id = ? AND owner_user_id = ?",
      conflict.id,
      ownerUserId
    );
  });
}

export async function keepLocalVersion(conflictId: string): Promise<void> {
  const ownerUserId = getCurrentUserId();
  const db = await getDatabase();
  const now = new Date().toISOString();
  await withWriteTransaction(db, async (txn) => {
    const { conflict, event, local } = await getConflictAndEvent(txn, ownerUserId, conflictId);
    const remote = JSON.parse(conflict.remote_payload) as SyncChangeResponse;
    // Explicit conflict resolution replaces the queue with a NEW event; never mutate a frozen request.
    await txn.runAsync(
      "DELETE FROM outbox_events WHERE owner_user_id = ? AND aggregate_id = ?",
      ownerUserId,
      conflict.aggregate_id
    );
    if (event.operation === "delete") {
      if (remote.operation === "upsert") {
        await enqueueLogEvent(
          txn,
          { id: conflict.aggregate_id } as FoodLog,
          "delete",
          now,
          JSON.stringify({ server_id: remote.server_id, expected_version: remote.version }),
          ownerUserId
        );
      }
    } else {
      if (!local) throw new Error("local record not found");
      const clientId = remote.operation === "delete" ? uuidv4() : remote.client_id;
      await txn.runAsync(
        `UPDATE food_logs SET server_id = ?, server_version = ?, remote_client_id = ?,
         sync_status = 'pending', last_sync_error = NULL WHERE id = ? AND owner_user_id = ?`,
        remote.operation === "delete" ? null : remote.server_id,
        remote.operation === "delete" ? null : remote.version,
        clientId,
        local.id,
        ownerUserId
      );
      const payload = JSON.stringify({
        ...JSON.parse(buildLogSyncPayload(rowToLog(local))),
        client_id: clientId,
        ...(remote.operation === "upsert"
          ? { server_id: remote.server_id, expected_version: remote.version }
          : {}),
      });
      await enqueueLogEvent(
        txn,
        rowToLog(local),
        remote.operation === "delete" ? "create" : "update",
        now,
        payload,
        ownerUserId
      );
    }
    await txn.runAsync(
      "DELETE FROM sync_conflicts WHERE id = ? AND owner_user_id = ?",
      conflict.id,
      ownerUserId
    );
  });
}
