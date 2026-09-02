import { AuthSession, type SessionStorage, type StoredSession } from "@/features/auth/authSession";
import type { FetchLike } from "@/api/http";

const USER = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "student@example.com",
  is_active: true,
  is_demo: false,
  created_at: "2026-07-15T00:00:00Z",
};

function jsonResponse(status: number, body?: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

class MemoryStorage implements SessionStorage {
  value: StoredSession | null;
  writes = 0;
  clears = 0;

  constructor(initial: StoredSession | null = null) {
    this.value = initial;
  }

  async read(): Promise<StoredSession | null> {
    return this.value;
  }

  async write(session: StoredSession): Promise<void> {
    this.value = session;
    this.writes += 1;
  }

  async clear(): Promise<void> {
    this.value = null;
    this.clears += 1;
  }
}

describe("AuthSession", () => {
  it("does not retry an old user's 401 with a newly logged-in user's token", async () => {
    const storage = new MemoryStorage();
    let finishOld!: (response: Response) => void;
    const oldResponse = new Promise<Response>((resolve) => {
      finishOld = resolve;
    });
    const other = { ...USER, id: "user-b", email: "b@example.com" };
    const fetcher = jest.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/login")) {
        const isB = String(init?.body).includes(other.email);
        return jsonResponse(200, {
          access_token: isB ? "access-b" : "access-a",
          refresh_token: isB ? "refresh-b" : "refresh-a",
          user: isB ? other : USER,
        });
      }
      if (url.endsWith("/protected")) return oldResponse;
      return jsonResponse(200, { access_token: "refreshed-b", refresh_token: "rotated-b" });
    });
    const session = new AuthSession(storage, fetcher, "https://api.test");
    await session.login(USER.email, "password");
    const pending = session.request("/protected");
    const rejected = expect(pending).rejects.toThrow(/session changed/i);
    await session.login(other.email, "password");
    finishOld(jsonResponse(401, { detail: "expired" }));
    await rejected;
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith("/refresh"))).toHaveLength(0);
    expect(storage.value?.user.id).toBe(other.id);
  });

  it("does not resurrect a session when an in-flight refresh returns after logout", async () => {
    const storage = new MemoryStorage({ refreshToken: "old", user: USER });
    let finish!: (response: Response) => void;
    const deferred = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const fetcher = jest.fn(async (url: string) =>
      url.endsWith("/refresh") ? deferred : jsonResponse(204)
    );
    const session = new AuthSession(storage, fetcher, "https://api.test");
    const restoring = session.restore();
    const rejected = expect(restoring).rejects.toThrow(/session changed/i);
    // Allow storage read and refresh dispatch before logout.
    await Promise.resolve();
    await Promise.resolve();
    await session.logout();
    finish(jsonResponse(200, { access_token: "late", refresh_token: "late-refresh" }));
    await rejected;
    expect(storage.value).toBeNull();
  });

  it("stores only the refresh session and sends the access token from memory", async () => {
    const storage = new MemoryStorage();
    const fetcher = jest
      .fn<ReturnType<FetchLike>, Parameters<FetchLike>>()
      .mockResolvedValueOnce(
        jsonResponse(200, {
          access_token: "access-1",
          refresh_token: "refresh-1",
          token_type: "bearer",
          expires_in: 900,
          user: USER,
        })
      )
      .mockResolvedValueOnce(jsonResponse(200, USER));
    const session = new AuthSession(storage, fetcher, "https://api.test");

    await session.login(USER.email, "correct-horse-123");
    await session.request("/api/v1/users/me");

    expect(storage.value).toEqual({ refreshToken: "refresh-1", user: USER });
    expect(JSON.stringify(storage.value)).not.toContain("access-1");
    expect(fetcher.mock.calls[1][1]?.headers).toMatchObject({
      Authorization: "Bearer access-1",
    });
  });

  it("rotates the refresh token while restoring a session", async () => {
    const storage = new MemoryStorage({ refreshToken: "refresh-old", user: USER });
    const fetcher = jest.fn<ReturnType<FetchLike>, Parameters<FetchLike>>(async () =>
      jsonResponse(200, {
        access_token: "access-new",
        refresh_token: "refresh-new",
        token_type: "bearer",
        expires_in: 900,
      })
    );

    const snapshot = await new AuthSession(storage, fetcher, "https://api.test").restore();

    expect(snapshot).toEqual({ status: "authenticated", user: USER });
    expect(storage.value?.refreshToken).toBe("refresh-new");
  });

  it("allows offline startup when a cached session exists", async () => {
    const storage = new MemoryStorage({ refreshToken: "refresh-old", user: USER });
    const fetcher = jest.fn<ReturnType<FetchLike>, Parameters<FetchLike>>(async () => {
      throw new TypeError("network unavailable");
    });

    const snapshot = await new AuthSession(storage, fetcher, "https://api.test").restore();

    expect(snapshot).toEqual({ status: "offline", user: USER });
    expect(storage.clears).toBe(0);
  });

  it("clears a session when the refresh token is rejected", async () => {
    const storage = new MemoryStorage({ refreshToken: "stolen", user: USER });
    const fetcher = jest.fn<ReturnType<FetchLike>, Parameters<FetchLike>>(async () =>
      jsonResponse(401, { detail: "invalid token" })
    );

    const snapshot = await new AuthSession(storage, fetcher, "https://api.test").restore();

    expect(snapshot).toEqual({ status: "unauthenticated", user: null });
    expect(storage.value).toBeNull();
  });

  it("retries a protected request once after a 401", async () => {
    const storage = new MemoryStorage();
    const fetcher = jest
      .fn<ReturnType<FetchLike>, Parameters<FetchLike>>()
      .mockResolvedValueOnce(
        jsonResponse(200, {
          access_token: "access-old",
          refresh_token: "refresh-old",
          token_type: "bearer",
          expires_in: 900,
          user: USER,
        })
      )
      .mockResolvedValueOnce(jsonResponse(401, { detail: "expired" }))
      .mockResolvedValueOnce(
        jsonResponse(200, {
          access_token: "access-new",
          refresh_token: "refresh-new",
          token_type: "bearer",
          expires_in: 900,
        })
      )
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    const session = new AuthSession(storage, fetcher, "https://api.test");
    await session.login(USER.email, "correct-horse-123");

    const result = await session.request<{ ok: boolean }>("/protected");

    expect(result).toEqual({ ok: true });
    expect(fetcher.mock.calls[3][1]?.headers).toMatchObject({
      Authorization: "Bearer access-new",
    });
    expect(storage.value?.refreshToken).toBe("refresh-new");
  });

  it("clears local credentials even if remote logout is offline", async () => {
    const storage = new MemoryStorage({ refreshToken: "refresh-old", user: USER });
    const fetcher = jest.fn<ReturnType<FetchLike>, Parameters<FetchLike>>(async () => {
      throw new TypeError("network unavailable");
    });
    const session = new AuthSession(storage, fetcher, "https://api.test");
    await session.restore();

    await session.logout();

    expect(storage.value).toBeNull();
  });
});
