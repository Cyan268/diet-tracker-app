import { createTestDatabase } from "../test-support/sqlite";
import { migrateDatabase } from "@/db/migrations";
import { activateLocalAccount, clearLocalAccount } from "@/db/accountScope";
import { addLog } from "@/db/repositories/logRepository";
import { AuthSession, type StoredSession } from "@/features/auth/authSession";
import { syncPendingEvents } from "@/features/sync/outboxSyncService";
import { syncRemoteProfile } from "@/features/sync/profileSyncService";
import { pullRemoteChanges } from "@/features/sync/pullSyncService";
import type { FetchLike } from "@/api/http";

const mockGetDatabase = jest.fn();
jest.mock("@/db/database", () => ({ getDatabase: () => mockGetDatabase() }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
function response(status: number, body: unknown): Response {
  return { status, ok: status < 400, text: async () => JSON.stringify(body) } as Response;
}
function authFor(fetcher: FetchLike) {
  let stored: StoredSession | null = null;
  return new AuthSession(
    {
      read: async () => stored,
      write: async (value) => {
        stored = value;
      },
      clear: async () => {
        stored = null;
      },
    },
    fetcher,
    "https://api.test"
  );
}
function loginResponse(body: BodyInit | null | undefined) {
  const b = String(body).includes("b@example.test");
  return response(200, {
    access_token: b ? "token-b" : "token-a",
    refresh_token: b ? "refresh-b" : "refresh-a",
    user: {
      id: b ? "owner-b" : "owner-a",
      email: b ? "b@example.test" : "a@example.test",
      is_active: true,
      is_demo: false,
      created_at: "2026-08-31",
    },
  });
}

describe("in-flight sync account isolation", () => {
  let fixture: ReturnType<typeof createTestDatabase>;
  beforeEach(async () => {
    fixture = createTestDatabase();
    mockGetDatabase.mockResolvedValue(fixture.db);
    await migrateDatabase(fixture.db);
    await activateLocalAccount("owner-a");
  });
  afterEach(() => {
    clearLocalAccount();
    fixture.close();
  });

  it("lets B sync independently while discarding A's late create response", async () => {
    const started = deferred<void>();
    const finish = deferred<Response>();
    const fetcher = jest.fn<ReturnType<FetchLike>, Parameters<FetchLike>>(async (url, init) => {
      if (url.endsWith("/login")) return loginResponse(init?.body);
      if (url.endsWith("/logs") && init?.method === "POST") {
        started.resolve();
        return finish.promise;
      }
      if (url.includes("/sync/changes"))
        return response(200, { changes: [], next_cursor: 0, has_more: false });
      return response(404, { detail: "not found" });
    });
    const auth = authFor(fetcher);
    await auth.login("a@example.test", "test");
    await addLog({
      date: "2026-08-31",
      mealType: "lunch",
      customName: "only A",
      amount: 1,
      unit: "份",
      kcal: 1,
      protein: 0,
      fat: 0,
      carbs: 0,
      sugar: 0,
      sodium: 0,
      caffeine: 0,
    });
    const pending = syncPendingEvents(auth);
    const rejected = expect(pending).rejects.toThrow(/session changed/i);
    await started.promise;
    await auth.login("b@example.test", "test");
    await activateLocalAccount("owner-b");
    expect((await syncPendingEvents(auth)).processed).toBe(0);
    finish.resolve(response(201, { id: "a-remote", client_id: "a-client", version: 1 }));
    await rejected;
    const log = await fixture.db.getFirstAsync<{ server_id: string | null }>(
      "SELECT * FROM food_logs"
    );
    expect(log?.server_id).toBeNull();
    const events = await fixture.db.getAllAsync(
      "SELECT * FROM outbox_events WHERE owner_user_id = 'owner-a'"
    );
    expect(events).toHaveLength(1);
    const posts = fetcher.mock.calls.filter(
      ([url, init]) => url.endsWith("/logs") && init?.method === "POST"
    );
    expect(posts).toHaveLength(1);
    expect(posts[0][1]?.headers).toMatchObject({ Authorization: "Bearer token-a" });
  });

  it.each(["profile", "pull"] as const)("does not apply A's late %s to B", async (kind) => {
    const started = deferred<void>();
    const finish = deferred<Response>();
    const fetcher: FetchLike = async (url, init) => {
      if (url.endsWith("/login")) return loginResponse(init?.body);
      started.resolve();
      return finish.promise;
    };
    const auth = authFor(fetcher);
    await auth.login("a@example.test", "test");
    const pending =
      kind === "profile" ? syncRemoteProfile(auth.capture()) : pullRemoteChanges(auth.capture());
    const rejected = expect(pending).rejects.toThrow(/session changed/i);
    await started.promise;
    await auth.login("b@example.test", "test");
    await activateLocalAccount("owner-b");
    finish.resolve(
      response(
        200,
        kind === "profile"
          ? {
              gender: "male",
              age: 20,
              height_cm: 180,
              weight_kg: 70,
              activity_level: "light",
              goal: "maintain",
              created_at: "2026-08-31",
              updated_at: "2026-08-31",
            }
          : { changes: [], next_cursor: 100, has_more: false }
      )
    );
    await rejected;
    expect(await fixture.db.getAllAsync("SELECT * FROM user_profile")).toHaveLength(0);
    expect(await fixture.db.getAllAsync("SELECT * FROM sync_cursors")).toHaveLength(0);
  });
});
