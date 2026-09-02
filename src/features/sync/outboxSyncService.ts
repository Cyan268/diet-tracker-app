import { ApiError, NetworkError } from "@/api/http";
import type { LogResponse } from "@/api/types";
import { getDatabase } from "@/db/database";
import { getReadyOutboxEvents } from "@/db/repositories/outboxRepository";
import type { FoodLogRow, OutboxEventRow } from "@/db/rows";
import {
  SessionChangedError,
  type AuthSession,
  type AuthRequestScope,
} from "@/features/auth/authSession";
import { pullRemoteChanges } from "./pullSyncService";
import { syncRemoteProfile } from "./profileSyncService";
import { withWriteTransaction } from "@/db/transactions";
import { assertSyncScope, captureSyncScope } from "./syncScope";

export interface SyncResult {
  processed: number;
  succeeded: number;
  failed: number;
  blocked: number;
  pulled: number;
  conflicts: number;
  pullFailed: boolean;
}
const inFlight = new WeakMap<AuthSession, { epoch: number; promise: Promise<SyncResult> }>();

function nextAttempt(attemptCount: number): string {
  return new Date(Date.now() + Math.min(2 ** Math.min(attemptCount, 8), 300) * 1000).toISOString();
}

async function markFailure(
  event: OutboxEventRow,
  error: unknown,
  blocked: boolean,
  scope: AuthRequestScope
) {
  const db = await getDatabase();
  const message = error instanceof Error ? error.message : "unknown sync error";
  const now = new Date().toISOString();
  await withWriteTransaction(db, async (txn) => {
    assertSyncScope(scope);
    const changed = await txn.runAsync(
      `UPDATE outbox_events SET status = ?, next_attempt_at = ?, last_error = ?, updated_at = ?
       WHERE id = ? AND owner_user_id = ? AND status = 'processing' AND attempt_count = ?`,
      blocked ? "blocked" : "failed",
      blocked ? now : nextAttempt(event.attempt_count),
      message.slice(0, 500),
      now,
      event.id,
      scope.ownerUserId,
      event.attempt_count
    );
    if (changed.changes !== 1) return;
    await txn.runAsync(
      "UPDATE food_logs SET sync_status = 'failed', last_sync_error = ? WHERE id = ? AND owner_user_id = ?",
      message.slice(0, 500),
      event.aggregate_id,
      scope.ownerUserId
    );
    assertSyncScope(scope);
  });
}

async function completeEvent(event: OutboxEventRow, scope: AuthRequestScope, remote?: LogResponse) {
  const db = await getDatabase();
  await withWriteTransaction(db, async (txn) => {
    assertSyncScope(scope);
    const active = await txn.getFirstAsync<{ id: string }>(
      "SELECT id FROM outbox_events WHERE id = ? AND owner_user_id = ? AND status = 'processing' AND attempt_count = ?",
      event.id,
      scope.ownerUserId,
      event.attempt_count
    );
    if (!active) return;
    if (remote) {
      // A replayed POST may return a record edited on another device. Do not silently
      // rebase pending local intents onto that newer version; let normal conflicts surface.
      const acknowledgedVersion = event.operation === "create" ? 1 : remote.version;
      await txn.runAsync(
        `UPDATE food_logs SET server_id = ?, remote_client_id = COALESCE(?, remote_client_id),
         server_version = ?, sync_status = 'synced', last_sync_error = NULL
         WHERE id = ? AND owner_user_id = ?`,
        remote.id,
        remote.client_id ?? null,
        acknowledgedVersion,
        event.aggregate_id,
        scope.ownerUserId
      );
      // Only unsent successors may acquire a new expected version. Sent requests stay frozen.
      await txn.runAsync(
        `UPDATE outbox_events
         SET payload = json_set(payload, '$.server_id', ?, '$.expected_version', ?),
             next_attempt_at = ?, updated_at = ?
         WHERE owner_user_id = ? AND aggregate_id = ? AND operation != 'create'
           AND first_attempt_at IS NULL AND attempt_count = 0`,
        remote.id,
        acknowledgedVersion,
        new Date().toISOString(),
        new Date().toISOString(),
        scope.ownerUserId,
        event.aggregate_id
      );
    }
    await txn.runAsync(
      "DELETE FROM outbox_events WHERE id = ? AND owner_user_id = ?",
      event.id,
      scope.ownerUserId
    );
    const remaining = await txn.getFirstAsync<{ count: number }>(
      "SELECT COUNT(*) AS count FROM outbox_events WHERE owner_user_id = ? AND aggregate_id = ?",
      scope.ownerUserId,
      event.aggregate_id
    );
    if ((remaining?.count ?? 0) > 0) {
      await txn.runAsync(
        "UPDATE food_logs SET sync_status = 'pending' WHERE id = ? AND owner_user_id = ?",
        event.aggregate_id,
        scope.ownerUserId
      );
    }
    assertSyncScope(scope);
  });
}

async function claimEvent(
  candidate: OutboxEventRow,
  scope: AuthRequestScope
): Promise<OutboxEventRow | null> {
  const db = await getDatabase();
  let claimed: OutboxEventRow | null = null;
  await withWriteTransaction(db, async (txn) => {
    assertSyncScope(scope);
    // Re-read inside the write gate: UI edits may have coalesced after the ready query.
    const event = await txn.getFirstAsync<OutboxEventRow>(
      `SELECT e.* FROM outbox_events e WHERE e.id = ? AND e.owner_user_id = ?
       AND e.status IN ('pending', 'failed')
       AND NOT EXISTS (SELECT 1 FROM outbox_events p WHERE p.owner_user_id = e.owner_user_id
         AND p.aggregate_id = e.aggregate_id AND p.queue_order < e.queue_order)`,
      candidate.id,
      scope.ownerUserId
    );
    if (!event) return;
    let path = event.request_path;
    let body = event.request_body;
    if (!path) {
      if (event.operation === "create") {
        path = "/api/v1/logs";
        body = event.payload;
      } else {
        const content = JSON.parse(event.payload) as Record<string, unknown>;
        const local = await txn.getFirstAsync<FoodLogRow>(
          "SELECT * FROM food_logs WHERE id = ? AND owner_user_id = ?",
          event.aggregate_id,
          scope.ownerUserId
        );
        const serverId = content.server_id ?? local?.server_id;
        const version = content.expected_version ?? local?.server_version;
        if (!serverId || !version) return; // Wait for the predecessor; never discard an unknown deletion.
        path =
          event.operation === "delete"
            ? `/api/v1/logs/${serverId}?expected_version=${version}`
            : `/api/v1/logs/${serverId}`;
        delete content.client_id;
        delete content.server_id;
        body =
          event.operation === "delete"
            ? null
            : JSON.stringify({ ...content, expected_version: version });
      }
    }
    const now = new Date().toISOString();
    await txn.runAsync(
      `UPDATE outbox_events SET status = 'processing', attempt_count = attempt_count + 1,
       first_attempt_at = COALESCE(first_attempt_at, ?), request_path = ?, request_body = ?, updated_at = ?
       WHERE id = ? AND owner_user_id = ?`,
      now,
      path,
      body ?? null,
      now,
      event.id,
      scope.ownerUserId
    );
    claimed = {
      ...event,
      status: "processing",
      attempt_count: event.attempt_count + 1,
      first_attempt_at: event.first_attempt_at ?? now,
      request_path: path,
      request_body: body,
    };
    assertSyncScope(scope);
  });
  return claimed;
}

async function processEvent(event: OutboxEventRow, scope: AuthRequestScope) {
  assertSyncScope(scope);
  if (!event.request_path) throw new Error("outbox request was not frozen");
  if (event.operation === "delete") {
    try {
      await scope.request(event.request_path, { method: "DELETE" });
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) throw error;
    }
    await completeEvent(event, scope);
  } else {
    const remote = await scope.request<LogResponse>(event.request_path, {
      method: event.operation === "create" ? "POST" : "PUT",
      body: event.request_body,
    });
    await completeEvent(event, scope, remote);
  }
}

async function run(scope: AuthRequestScope): Promise<SyncResult> {
  const db = await getDatabase();
  const now = new Date();
  await withWriteTransaction(db, async (txn) => {
    assertSyncScope(scope);
    await txn.runAsync(
      `UPDATE outbox_events SET status = 'failed', next_attempt_at = ?, last_error = 'interrupted sync recovered'
       WHERE owner_user_id = ? AND status = 'processing' AND updated_at < ?`,
      now.toISOString(),
      scope.ownerUserId,
      new Date(now.getTime() - 5 * 60 * 1000).toISOString()
    );
    assertSyncScope(scope);
  });
  const events = await getReadyOutboxEvents(db, now.toISOString(), 20, scope.ownerUserId);
  assertSyncScope(scope);
  const result: SyncResult = {
    processed: 0,
    succeeded: 0,
    failed: 0,
    blocked: 0,
    pulled: 0,
    conflicts: 0,
    pullFailed: false,
  };
  for (const candidate of events) {
    const event = await claimEvent(candidate, scope);
    if (!event) continue;
    result.processed += 1;
    try {
      await processEvent(event, scope);
      result.succeeded += 1;
    } catch (error) {
      if (error instanceof SessionChangedError) throw error;
      assertSyncScope(scope);
      const blocked = error instanceof ApiError && [409, 422].includes(error.status);
      await markFailure(event, error, blocked, scope);
      if (blocked) result.blocked += 1;
      else result.failed += 1;
      if (error instanceof ApiError && error.status === 401) throw error;
    }
  }
  try {
    await syncRemoteProfile(scope);
  } catch (error) {
    if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500))
      result.pullFailed = true;
    else throw error;
  }
  try {
    const pulled = await pullRemoteChanges(scope);
    result.pulled = pulled.pulled;
    result.conflicts = pulled.conflicts;
  } catch (error) {
    if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500))
      result.pullFailed = true;
    else throw error;
  }
  assertSyncScope(scope);
  return result;
}

export function syncPendingEvents(auth: AuthSession): Promise<SyncResult> {
  const scope = captureSyncScope(auth);
  const active = inFlight.get(auth);
  if (active?.epoch === scope.epoch) return active.promise;
  const entry = { epoch: scope.epoch, promise: Promise.resolve({} as SyncResult) };
  entry.promise = run(scope).finally(() => {
    if (inFlight.get(auth) === entry) inFlight.delete(auth);
  });
  inFlight.set(auth, entry);
  return entry.promise;
}
