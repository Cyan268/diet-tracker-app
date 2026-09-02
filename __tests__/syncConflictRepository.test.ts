import type { SyncChangeResponse } from "@/api/types";
import { activateLocalAccount, clearLocalAccount } from "@/db/accountScope";
import { keepLocalVersion } from "@/db/repositories/syncConflictRepository";
import type { FoodLogRow, OutboxEventRow, SyncConflictRow } from "@/db/rows";
import type { SQLiteDatabase } from "expo-sqlite";

const mockGetDatabase = jest.fn();
jest.mock("@/db/database", () => ({ getDatabase: () => mockGetDatabase() }));

const tombstone: SyncChangeResponse = {
  cursor: 12,
  operation: "delete",
  server_id: "server-1",
  client_id: "local-1",
  version: 2,
  log: null,
};

const conflict: SyncConflictRow = {
  id: "conflict-1",
  owner_user_id: "user-1",
  aggregate_id: "local-1",
  remote_operation: "delete",
  remote_cursor: 12,
  remote_payload: JSON.stringify(tombstone),
  created_at: "2026-07-15T00:00:00Z",
  updated_at: "2026-07-15T00:00:00Z",
};

const event = {
  id: "event-1",
  owner_user_id: "user-1",
  aggregate_id: "local-1",
  operation: "update",
  payload: "{}",
} as OutboxEventRow;

const local: FoodLogRow = {
  id: "local-1",
  owner_user_id: "user-1",
  server_id: "server-1",
  server_version: 1,
  date: "2026-07-15",
  meal_type: "breakfast",
  food_item_id: null,
  custom_name: "本机早餐",
  amount: 1,
  unit: "份",
  kcal: 100,
  protein: 10,
  fat: 3,
  carbs: 20,
  sugar: 2,
  sodium: 200,
  caffeine: 0,
  note: null,
  created_at: "2026-07-15T00:00:00Z",
  updated_at: "2026-07-15T01:00:00Z",
  sync_status: "failed",
  last_sync_error: "conflict",
};

describe("sync conflict repository", () => {
  afterAll(() => clearLocalAccount());

  it("turns a local edit into a new create when the remote record was deleted", async () => {
    const runAsync = jest.fn().mockResolvedValue({ changes: 1 });
    const db = {
      getFirstAsync: jest.fn(async (sql: string) => {
        if (sql.includes("SELECT id, payload FROM outbox_events")) return null;
        if (sql.includes("FROM sync_conflicts")) return conflict;
        if (sql.includes("FROM outbox_events")) return event;
        if (sql.includes("FROM food_logs")) return local;
        return null;
      }),
      runAsync,
      withExclusiveTransactionAsync: jest.fn(async (task) => task(db)),
    } as unknown as SQLiteDatabase;
    mockGetDatabase.mockResolvedValue(db);
    await activateLocalAccount("user-1");

    await keepLocalVersion("conflict-1");

    const recreate = runAsync.mock.calls.find(([sql]) => sql.includes("INSERT INTO outbox_events"));
    expect(recreate).toBeDefined();
    expect(JSON.parse(recreate?.[5] as string)).toMatchObject({
      custom_name: "本机早餐",
    });
    expect(JSON.parse(recreate?.[5] as string).client_id).not.toBe("local-1");
    expect(
      runAsync.mock.calls.some(
        ([sql, serverId]) => sql.includes("remote_client_id") && serverId === null
      )
    ).toBe(true);
    expect(runAsync.mock.calls.some(([sql]) => sql.includes("DELETE FROM sync_conflicts"))).toBe(
      true
    );
  });
});
