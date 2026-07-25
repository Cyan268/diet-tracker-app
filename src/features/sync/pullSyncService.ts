import type { SyncChangeResponse, SyncPageResponse } from "@/api/types";
import { getCurrentUserId } from "@/db/accountScope";
import { getDatabase } from "@/db/database";
import type { FoodLogRow, OutboxEventRow } from "@/db/rows";
import type { AuthSession } from "@/features/auth/authSession";
import type { SQLiteDatabase } from "expo-sqlite";
import { v4 as uuidv4 } from "uuid";
import { withWriteTransaction } from "@/db/transactions";

export interface PullResult {
  pulled: number;
  conflicts: number;
}

async function findLocalLog(
  db: SQLiteDatabase,
  ownerUserId: string,
  change: SyncChangeResponse
): Promise<FoodLogRow | null> {
  return db.getFirstAsync<FoodLogRow>(
    `SELECT * FROM food_logs
     WHERE owner_user_id = ? AND (server_id = ? OR id = ?)
     LIMIT 1`,
    ownerUserId,
    change.server_id,
    change.client_id
  );
}

async function findLocalEvent(
  db: SQLiteDatabase,
  ownerUserId: string,
  aggregateId: string
): Promise<OutboxEventRow | null> {
  return db.getFirstAsync<OutboxEventRow>(
    `SELECT * FROM outbox_events
     WHERE owner_user_id = ? AND aggregate_id = ?
     ORDER BY created_at LIMIT 1`,
    ownerUserId,
    aggregateId
  );
}

async function recordConflict(
  db: SQLiteDatabase,
  ownerUserId: string,
  aggregateId: string,
  change: SyncChangeResponse
): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    `INSERT INTO sync_conflicts (
       id, owner_user_id, aggregate_id, remote_operation, remote_cursor,
       remote_payload, created_at, updated_at
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(owner_user_id, aggregate_id) DO UPDATE SET
       remote_operation = excluded.remote_operation,
       remote_cursor = excluded.remote_cursor,
       remote_payload = excluded.remote_payload,
       updated_at = excluded.updated_at`,
    uuidv4(),
    ownerUserId,
    aggregateId,
    change.operation,
    change.cursor,
    JSON.stringify(change),
    now,
    now
  );
  await db.runAsync(
    `UPDATE outbox_events
     SET status = 'blocked', last_error = 'remote record changed', updated_at = ?
     WHERE owner_user_id = ? AND aggregate_id = ?`,
    now,
    ownerUserId,
    aggregateId
  );
  await db.runAsync(
    `UPDATE food_logs
     SET sync_status = 'failed', last_sync_error = '云端记录已变化，请解决同步冲突'
     WHERE owner_user_id = ? AND id = ?`,
    ownerUserId,
    aggregateId
  );
}

export async function upsertRemoteLog(
  db: SQLiteDatabase,
  ownerUserId: string,
  localId: string,
  change: SyncChangeResponse
): Promise<void> {
  const log = change.log;
  if (!log) throw new Error("upsert sync change is missing its log snapshot");
  await db.runAsync(
    `INSERT INTO food_logs (
       id, owner_user_id, server_id, server_version, date, meal_type,
       food_item_id, custom_name, amount, unit, kcal, protein, fat, carbs,
       sugar, sodium, caffeine, note, created_at, updated_at, sync_status, last_sync_error
     ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'synced', NULL)
     ON CONFLICT(id) DO UPDATE SET
       server_id = excluded.server_id,
       server_version = excluded.server_version,
       date = excluded.date,
       meal_type = excluded.meal_type,
       food_item_id = NULL,
       custom_name = excluded.custom_name,
       amount = excluded.amount,
       unit = excluded.unit,
       kcal = excluded.kcal,
       protein = excluded.protein,
       fat = excluded.fat,
       carbs = excluded.carbs,
       sugar = excluded.sugar,
       sodium = excluded.sodium,
       caffeine = excluded.caffeine,
       note = excluded.note,
       updated_at = excluded.updated_at,
       sync_status = 'synced',
       last_sync_error = NULL
     WHERE food_logs.owner_user_id = excluded.owner_user_id`,
    localId,
    ownerUserId,
    change.server_id,
    change.version,
    log.log_date,
    log.meal_type,
    log.custom_name ?? "云端食品记录",
    log.amount,
    log.unit,
    log.kcal,
    log.protein,
    log.fat,
    log.carbs,
    log.sugar,
    log.sodium,
    log.caffeine,
    log.note,
    log.created_at,
    log.updated_at
  );
}

async function applyUpsert(
  db: SQLiteDatabase,
  ownerUserId: string,
  change: SyncChangeResponse
): Promise<number> {
  const local = await findLocalLog(db, ownerUserId, change);
  const aggregateId = local?.id ?? change.client_id;
  const event = await findLocalEvent(db, ownerUserId, aggregateId);

  if (event) {
    if (event.operation === "delete") {
      const payload = JSON.parse(event.payload) as { expected_version?: number | null };
      if (change.version > (payload.expected_version ?? 0)) {
        await recordConflict(db, ownerUserId, aggregateId, change);
        return 1;
      }
      await db.runAsync(
        `UPDATE outbox_events
         SET payload = json_set(payload, '$.server_id', ?, '$.expected_version', ?)
         WHERE id = ?`,
        change.server_id,
        change.version,
        event.id
      );
      return 0;
    }

    if (event.operation === "create" && local && local.server_id === null) {
      await db.runAsync(
        `UPDATE food_logs SET server_id = ?, server_version = ?
         WHERE id = ? AND owner_user_id = ?`,
        change.server_id,
        change.version,
        local.id,
        ownerUserId
      );
      return 0;
    }

    if (local && change.version > (local.server_version ?? 0)) {
      await recordConflict(db, ownerUserId, aggregateId, change);
      return 1;
    }
    return 0;
  }

  if (!local || change.version >= (local.server_version ?? 0)) {
    await upsertRemoteLog(db, ownerUserId, aggregateId, change);
  }
  return 0;
}

async function applyDelete(
  db: SQLiteDatabase,
  ownerUserId: string,
  change: SyncChangeResponse
): Promise<number> {
  const local = await findLocalLog(db, ownerUserId, change);
  const aggregateId = local?.id ?? change.client_id;
  const event = await findLocalEvent(db, ownerUserId, aggregateId);

  if (event?.operation === "delete") {
    await db.runAsync("DELETE FROM outbox_events WHERE id = ?", event.id);
    await db.runAsync(
      "DELETE FROM sync_conflicts WHERE owner_user_id = ? AND aggregate_id = ?",
      ownerUserId,
      aggregateId
    );
    return 0;
  }
  if (event) {
    await recordConflict(db, ownerUserId, aggregateId, change);
    return 1;
  }
  await db.runAsync(
    `DELETE FROM food_logs
     WHERE owner_user_id = ? AND (server_id = ? OR id = ?)`,
    ownerUserId,
    change.server_id,
    change.client_id
  );
  return 0;
}

async function applyPage(page: SyncPageResponse, ownerUserId: string): Promise<number> {
  const db = await getDatabase();
  let conflicts = 0;
  await withWriteTransaction(db, async (txn) => {
    for (const change of page.changes) {
      conflicts +=
        change.operation === "upsert"
          ? await applyUpsert(txn, ownerUserId, change)
          : await applyDelete(txn, ownerUserId, change);
    }
    const now = new Date().toISOString();
    await txn.runAsync(
      `INSERT INTO sync_cursors (owner_user_id, log_cursor, updated_at)
       VALUES (?, ?, ?)
       ON CONFLICT(owner_user_id) DO UPDATE SET
         log_cursor = excluded.log_cursor,
         updated_at = excluded.updated_at`,
      ownerUserId,
      page.next_cursor,
      now
    );
  });
  return conflicts;
}

export async function pullRemoteChanges(auth: AuthSession): Promise<PullResult> {
  const ownerUserId = getCurrentUserId();
  const db = await getDatabase();
  const cursorRow = await db.getFirstAsync<{ log_cursor: number }>(
    "SELECT log_cursor FROM sync_cursors WHERE owner_user_id = ?",
    ownerUserId
  );
  let cursor = cursorRow?.log_cursor ?? 0;
  let pulled = 0;
  let conflicts = 0;

  for (let pageNumber = 0; pageNumber < 100; pageNumber += 1) {
    const page = await auth.request<SyncPageResponse>(
      `/api/v1/sync/changes?after=${cursor}&limit=100`
    );
    if (page.next_cursor < cursor || (page.has_more && page.next_cursor === cursor)) {
      throw new Error("sync cursor did not advance");
    }
    conflicts += await applyPage(page, ownerUserId);
    pulled += page.changes.length;
    cursor = page.next_cursor;
    if (!page.has_more) return { pulled, conflicts };
  }
  throw new Error("sync exceeded the maximum page count");
}
