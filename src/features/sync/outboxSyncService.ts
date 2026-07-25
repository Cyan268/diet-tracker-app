import { ApiError, NetworkError } from "@/api/http";
import type { LogResponse } from "@/api/types";
import { getDatabase } from "@/db/database";
import { getReadyOutboxEvents } from "@/db/repositories/outboxRepository";
import type { FoodLogRow, OutboxEventRow } from "@/db/rows";
import type { AuthSession } from "@/features/auth/authSession";
import { pullRemoteChanges } from "./pullSyncService";
import { syncRemoteProfile } from "./profileSyncService";
import { withWriteTransaction } from "@/db/transactions";

export interface SyncResult {
  processed: number;
  succeeded: number;
  failed: number;
  blocked: number;
  pulled: number;
  conflicts: number;
  pullFailed: boolean;
}

let syncInFlight: Promise<SyncResult> | null = null;

function nextAttempt(attemptCount: number): string {
  const delaySeconds = Math.min(2 ** Math.min(attemptCount, 8), 300);
  return new Date(Date.now() + delaySeconds * 1000).toISOString();
}

async function markFailure(event: OutboxEventRow, error: unknown, blocked: boolean): Promise<void> {
  const db = await getDatabase();
  const message = error instanceof Error ? error.message : "unknown sync error";
  const now = new Date().toISOString();
  await db.runAsync(
    `UPDATE outbox_events
     SET status = ?, attempt_count = attempt_count + 1,
         next_attempt_at = ?, last_error = ?, updated_at = ?
     WHERE id = ?`,
    blocked ? "blocked" : "failed",
    blocked ? now : nextAttempt(event.attempt_count + 1),
    message.slice(0, 500),
    now,
    event.id
  );
  await db.runAsync(
    `UPDATE food_logs SET sync_status = 'failed', last_sync_error = ?
     WHERE id = ? AND owner_user_id = ?`,
    message.slice(0, 500),
    event.aggregate_id,
    event.owner_user_id
  );
}

async function completeEvent(event: OutboxEventRow, remote?: LogResponse): Promise<void> {
  const db = await getDatabase();
  const ownerUserId = event.owner_user_id;
  await withWriteTransaction(db, async (txn) => {
    if (remote) {
      await txn.runAsync(
        `UPDATE food_logs
         SET server_id = ?, server_version = ?, sync_status = 'synced', last_sync_error = NULL
         WHERE id = ? AND owner_user_id = ?`,
        remote.id,
        remote.version,
        event.aggregate_id,
        ownerUserId
      );
      if (event.operation === "create") {
        await txn.runAsync(
          `UPDATE outbox_events
           SET payload = json_set(payload, '$.server_id', ?, '$.expected_version', ?),
               status = 'pending', next_attempt_at = ?, updated_at = ?
           WHERE owner_user_id = ? AND aggregate_type = 'food_log'
             AND aggregate_id = ? AND operation = 'delete'`,
          remote.id,
          remote.version,
          new Date().toISOString(),
          new Date().toISOString(),
          ownerUserId,
          event.aggregate_id
        );
      }
    }
    await txn.runAsync("DELETE FROM outbox_events WHERE id = ?", event.id);
    const remaining = await txn.getFirstAsync<{ count: number }>(
      "SELECT COUNT(*) AS count FROM outbox_events WHERE owner_user_id = ? AND aggregate_id = ?",
      ownerUserId,
      event.aggregate_id
    );
    if ((remaining?.count ?? 0) > 0) {
      await txn.runAsync(
        "UPDATE food_logs SET sync_status = 'pending' WHERE id = ? AND owner_user_id = ?",
        event.aggregate_id,
        ownerUserId
      );
    }
  });
}

async function processCreate(event: OutboxEventRow, auth: AuthSession): Promise<void> {
  const remote = await auth.request<LogResponse>("/api/v1/logs", {
    method: "POST",
    body: event.payload,
  });
  await completeEvent(event, remote);
}

async function processUpdate(event: OutboxEventRow, auth: AuthSession): Promise<void> {
  const db = await getDatabase();
  const ownerUserId = event.owner_user_id;
  const local = await db.getFirstAsync<FoodLogRow>(
    "SELECT * FROM food_logs WHERE id = ? AND owner_user_id = ?",
    event.aggregate_id,
    ownerUserId
  );
  if (!local?.server_id || !local.server_version) {
    throw new Error("remote record is not available for update");
  }
  const content = JSON.parse(event.payload) as Record<string, unknown>;
  delete content.client_id;
  const remote = await auth.request<LogResponse>(`/api/v1/logs/${local.server_id}`, {
    method: "PUT",
    body: JSON.stringify({ ...content, expected_version: local.server_version }),
  });
  await completeEvent(event, remote);
}

async function processDelete(event: OutboxEventRow, auth: AuthSession): Promise<void> {
  const payload = JSON.parse(event.payload) as {
    server_id?: string | null;
    expected_version?: number | null;
  };
  if (!payload.server_id || !payload.expected_version) {
    throw new Error("remote record is not available for deletion");
  }
  try {
    await auth.request<void>(
      `/api/v1/logs/${payload.server_id}?expected_version=${payload.expected_version}`,
      { method: "DELETE" }
    );
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
  }
  await completeEvent(event);
}

async function claimEvent(event: OutboxEventRow): Promise<boolean> {
  const db = await getDatabase();
  const result = await db.runAsync(
    `UPDATE outbox_events SET status = 'processing', updated_at = ?
     WHERE id = ? AND owner_user_id = ? AND status IN ('pending', 'failed')`,
    new Date().toISOString(),
    event.id,
    event.owner_user_id
  );
  return result.changes === 1;
}

async function run(auth: AuthSession): Promise<SyncResult> {
  const db = await getDatabase();
  const now = new Date();
  const staleBefore = new Date(now.getTime() - 5 * 60 * 1000).toISOString();
  await db.runAsync(
    `UPDATE outbox_events
     SET status = 'failed', next_attempt_at = ?, last_error = 'interrupted sync recovered'
     WHERE status = 'processing' AND updated_at < ?`,
    now.toISOString(),
    staleBefore
  );
  const events = await getReadyOutboxEvents(db, now.toISOString());
  const result: SyncResult = {
    processed: 0,
    succeeded: 0,
    failed: 0,
    blocked: 0,
    pulled: 0,
    conflicts: 0,
    pullFailed: false,
  };

  for (const event of events) {
    if (!(await claimEvent(event))) continue;
    result.processed += 1;
    try {
      if (event.operation === "create") await processCreate(event, auth);
      if (event.operation === "update") await processUpdate(event, auth);
      if (event.operation === "delete") await processDelete(event, auth);
      result.succeeded += 1;
    } catch (error) {
      const blocked = error instanceof ApiError && [409, 422].includes(error.status);
      await markFailure(event, error, blocked);
      if (blocked) result.blocked += 1;
      else result.failed += 1;
    }
  }
  try {
    await syncRemoteProfile(auth);
  } catch (error) {
    if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)) {
      result.pullFailed = true;
    } else {
      throw error;
    }
  }
  try {
    const pulled = await pullRemoteChanges(auth);
    result.pulled = pulled.pulled;
    result.conflicts = pulled.conflicts;
  } catch (error) {
    if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)) {
      result.pullFailed = true;
    } else {
      throw error;
    }
  }
  return result;
}

export function syncPendingEvents(auth: AuthSession): Promise<SyncResult> {
  if (!syncInFlight) {
    syncInFlight = run(auth).finally(() => {
      syncInFlight = null;
    });
  }
  return syncInFlight;
}
