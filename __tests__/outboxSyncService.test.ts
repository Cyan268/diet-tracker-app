import type { SQLiteDatabase } from "expo-sqlite";
import { ApiError } from "@/api/http";
import type { AuthSession } from "@/features/auth/authSession";
import { syncPendingEvents } from "@/features/sync/outboxSyncService";
import type { OutboxEventRow } from "@/db/rows";
import { clearLocalAccount, activateLocalAccount } from "@/db/accountScope";

const mockGetDatabase = jest.fn();
const mockPullRemoteChanges = jest.fn();
jest.mock("@/db/database", () => ({
  getDatabase: () => mockGetDatabase(),
}));
jest.mock("@/features/sync/pullSyncService", () => ({
  pullRemoteChanges: (...args: unknown[]) => mockPullRemoteChanges(...args),
}));
jest.mock("@/features/sync/profileSyncService", () => ({
  syncRemoteProfile: jest.fn().mockResolvedValue("unchanged"),
}));

const EVENT: OutboxEventRow = {
  id: "event-1",
  owner_user_id: "user-1",
  aggregate_type: "food_log",
  aggregate_id: "local-log-1",
  operation: "create",
  payload: JSON.stringify({ client_id: "local-log-1" }),
  status: "pending",
  attempt_count: 0,
  next_attempt_at: "2026-07-15T00:00:00.000Z",
  last_error: null,
  created_at: "2026-07-15T00:00:00.000Z",
  updated_at: "2026-07-15T00:00:00.000Z",
};

function createDatabase(event: OutboxEventRow): {
  db: SQLiteDatabase;
  runAsync: jest.Mock;
} {
  const runAsync = jest.fn().mockResolvedValue({ changes: 1 });
  const db = {
    getAllAsync: jest.fn().mockResolvedValue([event]),
    getFirstAsync: jest.fn().mockResolvedValue({ count: 0 }),
    runAsync,
    withExclusiveTransactionAsync: jest.fn(async (task) => task(db)),
  } as unknown as SQLiteDatabase;
  return { db, runAsync };
}

describe("outbox sync service", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockPullRemoteChanges.mockResolvedValue({ pulled: 0, conflicts: 0 });
  });
  afterAll(() => clearLocalAccount());

  it("claims and completes a create event", async () => {
    const { db, runAsync } = createDatabase(EVENT);
    mockGetDatabase.mockResolvedValue(db);
    await activateLocalAccount("user-1");
    const auth = {
      request: jest.fn().mockResolvedValue({ id: "server-log-1", version: 1 }),
    } as unknown as AuthSession;

    const result = await syncPendingEvents(auth);

    expect(result).toEqual({
      processed: 1,
      succeeded: 1,
      failed: 0,
      blocked: 0,
      pulled: 0,
      conflicts: 0,
      pullFailed: false,
    });
    expect(auth.request).toHaveBeenCalledWith("/api/v1/logs", {
      method: "POST",
      body: EVENT.payload,
    });
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("status = 'processing'"))).toBe(true);
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("DELETE FROM outbox_events"))).toBe(
      true
    );
  });

  it("blocks a validation conflict instead of retrying forever", async () => {
    const { db, runAsync } = createDatabase(EVENT);
    mockGetDatabase.mockResolvedValue(db);
    await activateLocalAccount("user-1");
    const auth = {
      request: jest.fn().mockRejectedValue(new ApiError(409, { detail: "conflict" })),
    } as unknown as AuthSession;

    const result = await syncPendingEvents(auth);

    expect(result.blocked).toBe(1);
    const failureCall = runAsync.mock.calls.find(([sql]) => sql.includes("attempt_count"));
    expect(failureCall?.[1]).toBe("blocked");
  });

  it("propagates an unauthorized pull so the auth state can return to login", async () => {
    const { db } = createDatabase(EVENT);
    mockGetDatabase.mockResolvedValue(db);
    await activateLocalAccount("user-1");
    const auth = {
      request: jest.fn().mockResolvedValue({ id: "server-log-1", version: 1 }),
    } as unknown as AuthSession;
    mockPullRemoteChanges.mockRejectedValue(new ApiError(401, { detail: "expired" }));

    await expect(syncPendingEvents(auth)).rejects.toMatchObject({ status: 401 });
  });
});
