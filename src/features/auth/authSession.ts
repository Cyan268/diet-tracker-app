import { API_BASE_URL } from "@/api/config";
import { ApiError, NetworkError, requestJson, type FetchLike } from "@/api/http";
import type { AuthResponse, AuthUser, TokenResponse } from "@/api/types";

export interface StoredSession {
  refreshToken: string;
  user: AuthUser;
}
export interface SessionStorage {
  read(): Promise<StoredSession | null>;
  write(session: StoredSession): Promise<void>;
  clear(): Promise<void>;
}
export type SessionStatus = "authenticated" | "offline" | "unauthenticated";
export interface SessionSnapshot {
  status: SessionStatus;
  user: AuthUser | null;
}

export class SessionChangedError extends Error {
  constructor() {
    super("Session changed; discard work from the previous account");
    this.name = "SessionChangedError";
  }
}
export interface AuthRequestScope {
  readonly ownerUserId: string;
  readonly epoch: number;
  assertCurrent(): void;
  request<T>(path: string, init?: RequestInit): Promise<T>;
}

export class AuthSession {
  private accessToken: string | null = null;
  private storedSession: StoredSession | null = null;
  private epoch = 0;
  private refreshInFlight: { epoch: number; promise: Promise<boolean> } | null = null;
  private storageQueue: Promise<void> = Promise.resolve();

  constructor(
    private readonly storage: SessionStorage,
    private readonly fetcher: FetchLike = fetch,
    private readonly baseUrl: string = API_BASE_URL
  ) {}

  private assertEpoch(epoch: number): void {
    if (epoch !== this.epoch) throw new SessionChangedError();
  }

  // Serialize persistence so an older delayed write cannot overwrite a newer login/logout.
  private persist(epoch: number, operation: () => Promise<void>): Promise<void> {
    const task = this.storageQueue.then(async () => {
      this.assertEpoch(epoch);
      await operation();
    });
    this.storageQueue = task.catch(() => undefined);
    return task;
  }

  capture(): AuthRequestScope {
    if (!this.storedSession) throw new ApiError(401, { detail: "authentication required" });
    const epoch = this.epoch;
    const ownerUserId = this.storedSession.user.id;
    const assertCurrent = () => {
      this.assertEpoch(epoch);
      if (this.storedSession?.user.id !== ownerUserId) throw new SessionChangedError();
    };
    return Object.freeze({
      ownerUserId,
      epoch,
      assertCurrent,
      request: <T>(path: string, init?: RequestInit) =>
        this.requestInScope<T>(epoch, assertCurrent, path, init),
    });
  }

  async restore(): Promise<SessionSnapshot> {
    const epoch = ++this.epoch;
    const stored = await this.storage.read();
    this.assertEpoch(epoch);
    this.storedSession = stored;
    this.accessToken = null;
    if (!stored) return { status: "unauthenticated", user: null };
    try {
      if (!(await this.refreshAccessToken(epoch))) return { status: "unauthenticated", user: null };
      this.assertEpoch(epoch);
      return { status: "authenticated", user: stored.user };
    } catch (error) {
      if (error instanceof SessionChangedError) throw error;
      this.assertEpoch(epoch);
      if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)) {
        return { status: "offline", user: stored.user };
      }
      await this.clearLocalSession();
      return { status: "unauthenticated", user: null };
    }
  }

  async login(email: string, password: string): Promise<AuthUser> {
    return this.authenticate("/api/v1/auth/login", email, password);
  }
  async register(email: string, password: string): Promise<AuthUser> {
    return this.authenticate("/api/v1/auth/register", email, password);
  }
  private async authenticate(path: string, email: string, password: string): Promise<AuthUser> {
    const epoch = ++this.epoch;
    this.accessToken = null;
    this.storedSession = null;
    await this.persist(epoch, () => this.storage.clear());
    this.assertEpoch(epoch);
    const result = await requestJson<AuthResponse>(this.fetcher, `${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    this.assertEpoch(epoch);
    const stored = { refreshToken: result.refresh_token, user: result.user };
    await this.persist(epoch, () => this.storage.write(stored));
    this.assertEpoch(epoch);
    this.accessToken = result.access_token;
    this.storedSession = stored;
    return result.user;
  }

  private async performRefresh(epoch: number): Promise<boolean> {
    this.assertEpoch(epoch);
    const previous = this.storedSession;
    if (!previous) return false;
    try {
      const result = await requestJson<TokenResponse>(
        this.fetcher,
        `${this.baseUrl}/api/v1/auth/refresh`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: previous.refreshToken }),
        }
      );
      this.assertEpoch(epoch);
      const stored = { ...previous, refreshToken: result.refresh_token };
      await this.persist(epoch, () => this.storage.write(stored));
      this.assertEpoch(epoch);
      this.accessToken = result.access_token;
      this.storedSession = stored;
      return true;
    } catch (error) {
      this.assertEpoch(epoch);
      if (error instanceof ApiError && error.status === 401) {
        await this.clearLocalSession();
        return false;
      }
      throw error;
    }
  }

  private refreshAccessToken(epoch: number): Promise<boolean> {
    this.assertEpoch(epoch);
    if (!this.refreshInFlight || this.refreshInFlight.epoch !== epoch) {
      const entry = { epoch, promise: Promise.resolve(false) };
      entry.promise = this.performRefresh(epoch).finally(() => {
        if (this.refreshInFlight === entry) this.refreshInFlight = null;
      });
      this.refreshInFlight = entry;
    }
    return this.refreshInFlight.promise;
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    return this.capture().request<T>(path, init);
  }

  private async requestInScope<T>(
    epoch: number,
    assertCurrent: () => void,
    path: string,
    init: RequestInit = {}
  ): Promise<T> {
    assertCurrent();
    if (!this.accessToken && !(await this.refreshAccessToken(epoch))) {
      throw new ApiError(401, { detail: "authentication required" });
    }
    const send = async () => {
      assertCurrent();
      const token = this.accessToken;
      const result = await requestJson<T>(this.fetcher, `${this.baseUrl}${path}`, {
        ...init,
        headers: {
          ...(init.body ? { "Content-Type": "application/json" } : {}),
          ...init.headers,
          Authorization: `Bearer ${token}`,
        },
      });
      assertCurrent();
      return result;
    };
    try {
      return await send();
    } catch (error) {
      assertCurrent();
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      if (!(await this.refreshAccessToken(epoch))) throw error;
      return send();
    }
  }

  async logout(): Promise<void> {
    const refreshToken = this.storedSession?.refreshToken;
    await this.clearLocalSession();
    if (!refreshToken) return;
    try {
      await requestJson<void>(this.fetcher, `${this.baseUrl}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      /* Local logout succeeds even when offline. */
    }
  }
  private async clearLocalSession(): Promise<void> {
    const epoch = ++this.epoch;
    this.accessToken = null;
    this.storedSession = null;
    await this.persist(epoch, () => this.storage.clear());
  }
}
