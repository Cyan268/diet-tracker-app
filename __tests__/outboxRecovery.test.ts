import { ApiError, NetworkError } from "@/api/http";
import { activateLocalAccount, clearLocalAccount } from "@/db/accountScope";
import { migrateDatabase } from "@/db/migrations";
import { addLog, updateLog, deleteLog, type NewFoodLog } from "@/db/repositories/logRepository";
import type { OutboxEventRow } from "@/db/rows";
import type { AuthSession } from "@/features/auth/authSession";
import { syncPendingEvents } from "@/features/sync/outboxSyncService";
import { createTestDatabase } from "../test-support/sqlite";

const mockGetDatabase = jest.fn();
jest.mock("@/db/database", () => ({ getDatabase: () => mockGetDatabase() }));
jest.mock("@/features/sync/profileSyncService", () => ({
  syncRemoteProfile: jest.fn().mockResolvedValue("unchanged"),
}));
jest.mock("@/features/sync/pullSyncService", () => ({
  pullRemoteChanges: jest.fn().mockResolvedValue({ pulled: 0, conflicts: 0 }),
}));

const MEAL: NewFoodLog = {
  date: "2026-08-31",
  mealType: "lunch",
  customName: "故障恢复测试饭",
  amount: 1,
  unit: "份",
  kcal: 120,
  protein: 10,
  fat: 3,
  carbs: 20,
  sugar: 1,
  sodium: 30,
  caffeine: 0,
};

function serverWithLostCreateResponse() {
  let original: string | null = null;
  let record: Record<string, unknown> | null = null;
  const request = jest.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      if (!original) {
        original = String(init.body);
        record = { ...JSON.parse(original), id: "server-1", version: 1 };
        throw new NetworkError(new Error("response lost after commit"));
      }
      if (original !== init.body) throw new ApiError(409, { detail: "idempotency conflict" });
      return record;
    }
    if (init?.method === "PUT") {
      record = {
        ...record,
        ...JSON.parse(String(init.body)),
        version: Number(record?.version) + 1,
      };
      return record;
    }
    if (init?.method === "DELETE") {
      record = null;
      return undefined;
    }
    throw new Error("unexpected test request");
  });
  const scope = { ownerUserId: "user-1", epoch: 1, assertCurrent: () => undefined, request };
  const auth = { request, capture: () => scope } as unknown as AuthSession;
  return { auth, request, current: () => record };
}

describe("Outbox response-loss recovery with real SQLite", () => {
  let fixture: ReturnType<typeof createTestDatabase>;
  beforeEach(async () => {
    fixture = createTestDatabase();
    mockGetDatabase.mockResolvedValue(fixture.db);
    await migrateDatabase(fixture.db);
    await activateLocalAccount("user-1");
  });
  afterEach(() => {
    clearLocalAccount();
    fixture.close();
  });

  const ready = async () => {
    await fixture.db.runAsync("UPDATE outbox_events SET next_attempt_at = '2000-01-01'");
  };

  it("re-reads a coalesced create when an edit happens between selection and claim", async () => {
    const log = await addLog(MEAL);
    const originalAll = fixture.db.getAllAsync.bind(fixture.db);
    let edited = false;
    jest
      .spyOn(fixture.db, "getAllAsync")
      .mockImplementation(async (sql: string, ...params: unknown[]) => {
        const rows = await originalAll(sql, ...(params as (string | number | null)[]));
        if (!edited && sql.includes("SELECT e.*")) {
          edited = true;
          await updateLog(log.id, { amount: 3 });
        }
        return rows;
      });
    const server = serverWithLostCreateResponse();
    await syncPendingEvents(server.auth);
    expect(JSON.parse(String(server.request.mock.calls[0][1]?.body)).amount).toBe(3);
  });

  it("freezes before the network await and does not send dependent edits early", async () => {
    const log = await addLog(MEAL);
    const request = jest.fn(async () => {
      const event = await fixture.db.getFirstAsync<OutboxEventRow>("SELECT * FROM outbox_events");
      expect(event?.first_attempt_at).toBeTruthy();
      expect(event?.attempt_count).toBe(1);
      expect(event?.status).toBe("processing");
      await updateLog(log.id, { amount: 4 });
      const after = await fixture.db.getFirstAsync<OutboxEventRow>(
        "SELECT * FROM outbox_events WHERE operation = 'create'"
      );
      expect(after?.payload).toBe(event?.payload);
      throw new NetworkError("interrupted");
    });
    const auth = {
      capture: () => ({ ownerUserId: "user-1", epoch: 1, assertCurrent: () => undefined, request }),
    } as unknown as AuthSession;
    await syncPendingEvents(auth);
    expect(request).toHaveBeenCalledTimes(1);
    expect(await fixture.db.getAllAsync("SELECT * FROM outbox_events")).toHaveLength(2);
  });

  it("still cancels a create that has never been attempted", async () => {
    const log = await addLog(MEAL);
    await updateLog(log.id, { amount: 2 });
    const create = await fixture.db.getFirstAsync<OutboxEventRow>("SELECT * FROM outbox_events");
    expect(JSON.parse(create!.payload)).not.toHaveProperty("server_id");
    expect(JSON.parse(create!.payload)).not.toHaveProperty("expected_version");
    await deleteLog(log.id);
    expect(await fixture.db.getAllAsync("SELECT * FROM outbox_events")).toHaveLength(0);
  });

  it("replays the original create before sending a later edit", async () => {
    const log = await addLog(MEAL);
    const server = serverWithLostCreateResponse();
    expect((await syncPendingEvents(server.auth)).failed).toBe(1);
    const before = await fixture.db.getFirstAsync<OutboxEventRow>("SELECT * FROM outbox_events");
    await updateLog(log.id, { amount: 2, kcal: 240 });
    const create = await fixture.db.getFirstAsync<OutboxEventRow>(
      "SELECT * FROM outbox_events WHERE operation = 'create'"
    );
    expect(create?.payload).toBe(before?.payload);
    await ready();
    expect((await syncPendingEvents(server.auth)).blocked).toBe(0);
    await ready();
    await syncPendingEvents(server.auth);
    expect(server.current()?.amount).toBe(2);
    expect(await fixture.db.getAllAsync("SELECT * FROM outbox_events")).toHaveLength(0);
    const posts = server.request.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(2);
    expect(posts[0][1]?.body).toBe(posts[1][1]?.body);
  });

  it("keeps an unknown create and deletion intent until cloud deletion succeeds", async () => {
    const log = await addLog(MEAL);
    const server = serverWithLostCreateResponse();
    await syncPendingEvents(server.auth);
    await deleteLog(log.id);
    const events = await fixture.db.getAllAsync<OutboxEventRow>("SELECT * FROM outbox_events");
    expect(events.map((event) => event.operation).sort()).toEqual(["create", "delete"]);
    await ready();
    await syncPendingEvents(server.auth);
    await ready();
    await syncPendingEvents(server.auth);
    expect(server.current()).toBeNull();
    expect(await fixture.db.getAllAsync("SELECT * FROM food_logs")).toHaveLength(0);
    expect(await fixture.db.getAllAsync("SELECT * FROM outbox_events")).toHaveLength(0);
  });

  it("does not silently rebase a pending edit when create replay returns a newer remote version", async () => {
    const log = await addLog(MEAL);
    const server = serverWithLostCreateResponse();
    await syncPendingEvents(server.auth);
    await updateLog(log.id, { amount: 2 });
    server.current()!.version = 3; // Another device changed the accepted create before replay.
    await ready();
    await syncPendingEvents(server.auth);
    const successor = await fixture.db.getFirstAsync<OutboxEventRow>(
      "SELECT * FROM outbox_events WHERE operation = 'update'"
    );
    expect(JSON.parse(successor!.payload).expected_version).toBe(1);
    expect(JSON.parse(successor!.payload).amount).toBe(2);
  });

  it("keeps an attempted update body/version frozen while a later edit waits", async () => {
    const log = await addLog(MEAL);
    const server = serverWithLostCreateResponse();
    await syncPendingEvents(server.auth);
    await ready();
    await syncPendingEvents(server.auth);
    await updateLog(log.id, { amount: 2 });
    server.request.mockImplementationOnce(async () => {
      throw new NetworkError("update response lost");
    });
    await syncPendingEvents(server.auth);
    const attempted = await fixture.db.getFirstAsync<OutboxEventRow>("SELECT * FROM outbox_events");
    await updateLog(log.id, { amount: 3 });
    await ready();
    await syncPendingEvents(server.auth);
    const replay = server.request.mock.calls.at(-1)!;
    expect(replay[1]?.body).toBe(attempted?.request_body);
    expect(JSON.parse(String(replay[1]?.body)).expected_version).toBe(1);
    expect(await fixture.db.getAllAsync("SELECT * FROM outbox_events")).toHaveLength(1);
  });
});
