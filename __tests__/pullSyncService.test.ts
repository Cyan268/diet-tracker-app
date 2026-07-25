import type { SyncChangeResponse, SyncPageResponse } from "@/api/types";
import { activateLocalAccount, clearLocalAccount } from "@/db/accountScope";
import type { FoodLogRow, OutboxEventRow } from "@/db/rows";
import type { AuthSession } from "@/features/auth/authSession";
import { pullRemoteChanges } from "@/features/sync/pullSyncService";
import type { SQLiteDatabase } from "expo-sqlite";

const mockGetDatabase = jest.fn();
jest.mock("@/db/database", () => ({ getDatabase: () => mockGetDatabase() }));

const REMOTE: SyncChangeResponse = {
  cursor: 7,
  operation: "upsert",
  server_id: "server-1",
  client_id: "local-1",
  version: 2,
  log: {
    id: "server-1",
    client_id: "local-1",
    log_date: "2026-07-15",
    meal_type: "breakfast",
    food_item_id: null,
    custom_name: "云端早餐",
    amount: 1,
    unit: "份",
    kcal: 120,
    protein: 10,
    fat: 5,
    carbs: 20,
    sugar: 2,
    sodium: 300,
    caffeine: 0,
    note: null,
    version: 2,
    created_at: "2026-07-15T00:00:00Z",
    updated_at: "2026-07-15T01:00:00Z",
  },
};

function page(change: SyncChangeResponse): SyncPageResponse {
  return { changes: [change], next_cursor: change.cursor, has_more: false };
}

function createDatabase(
  local: FoodLogRow | null,
  event: OutboxEventRow | null,
  collisionOwnerUserId: string | null = null
): { db: SQLiteDatabase; runAsync: jest.Mock } {
  const runAsync = jest.fn().mockResolvedValue({ changes: 1 });
  const db = {
    getFirstAsync: jest.fn(async (sql: string) => {
      if (sql.includes("sync_cursors")) return { log_cursor: 0 };
      if (sql.includes("SELECT owner_user_id FROM food_logs")) {
        return collisionOwnerUserId ? { owner_user_id: collisionOwnerUserId } : null;
      }
      if (sql.includes("FROM food_logs")) return local;
      if (sql.includes("FROM outbox_events")) return event;
      return null;
    }),
    runAsync,
    withExclusiveTransactionAsync: jest.fn(async (task) => task(db)),
  } as unknown as SQLiteDatabase;
  return { db, runAsync };
}

describe("pull sync service", () => {
  beforeEach(() => jest.clearAllMocks());
  afterAll(() => clearLocalAccount());

  it("atomically inserts a remote log and advances the account cursor", async () => {
    const { db, runAsync } = createDatabase(null, null);
    mockGetDatabase.mockResolvedValue(db);
    await activateLocalAccount("user-1");
    const auth = { request: jest.fn().mockResolvedValue(page(REMOTE)) } as unknown as AuthSession;

    const result = await pullRemoteChanges(auth);

    expect(result).toEqual({ pulled: 1, conflicts: 0 });
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("INSERT INTO food_logs"))).toBe(true);
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("INSERT INTO sync_cursors"))).toBe(
      true
    );
  });

  it("uses a fresh local id when a rotated account reuses a deterministic client id", async () => {
    const { db, runAsync } = createDatabase(null, null, "previous-demo-user");
    mockGetDatabase.mockResolvedValue(db);
    await activateLocalAccount("new-demo-user");
    const auth = { request: jest.fn().mockResolvedValue(page(REMOTE)) } as unknown as AuthSession;

    const result = await pullRemoteChanges(auth);

    expect(result).toEqual({ pulled: 1, conflicts: 0 });
    const insert = runAsync.mock.calls.find(([sql]) => sql.includes("INSERT INTO food_logs"));
    expect(insert).toBeDefined();
    expect(insert?.[1]).not.toBe(REMOTE.client_id);
    expect(insert?.[2]).toBe("new-demo-user");
  });

  it("preserves a pending local edit and records a newer remote version as conflict", async () => {
    const local = {
      id: "local-1",
      owner_user_id: "user-1",
      server_id: "server-1",
      server_version: 1,
    } as FoodLogRow;
    const event = {
      id: "event-1",
      owner_user_id: "user-1",
      aggregate_id: "local-1",
      operation: "update",
      payload: "{}",
    } as OutboxEventRow;
    const { db, runAsync } = createDatabase(local, event);
    mockGetDatabase.mockResolvedValue(db);
    await activateLocalAccount("user-1");
    const auth = { request: jest.fn().mockResolvedValue(page(REMOTE)) } as unknown as AuthSession;

    const result = await pullRemoteChanges(auth);

    expect(result).toEqual({ pulled: 1, conflicts: 1 });
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("INSERT INTO sync_conflicts"))).toBe(
      true
    );
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("status = 'blocked'"))).toBe(true);
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("INSERT INTO food_logs"))).toBe(false);
  });

  it("applies a remote tombstone when no local write is pending", async () => {
    const tombstone: SyncChangeResponse = { ...REMOTE, cursor: 8, operation: "delete", log: null };
    const local = {
      id: "local-1",
      owner_user_id: "user-1",
      server_id: "server-1",
      server_version: 2,
    } as FoodLogRow;
    const { db, runAsync } = createDatabase(local, null);
    mockGetDatabase.mockResolvedValue(db);
    await activateLocalAccount("user-1");
    const auth = {
      request: jest.fn().mockResolvedValue(page(tombstone)),
    } as unknown as AuthSession;

    const result = await pullRemoteChanges(auth);

    expect(result.conflicts).toBe(0);
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("DELETE FROM food_logs"))).toBe(true);
  });
});
