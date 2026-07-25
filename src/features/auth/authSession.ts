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

export class AuthSession {
  private accessToken: string | null = null;
  private storedSession: StoredSession | null = null;
  private refreshInFlight: Promise<boolean> | null = null;

  constructor(
    private readonly storage: SessionStorage,
    private readonly fetcher: FetchLike = fetch,
    private readonly baseUrl: string = API_BASE_URL
  ) {}

  async restore(): Promise<SessionSnapshot> {
    this.storedSession = await this.storage.read();
    if (!this.storedSession) return { status: "unauthenticated", user: null };
    try {
      const refreshed = await this.refreshAccessToken();
      if (!refreshed) return { status: "unauthenticated", user: null };
      return { status: "authenticated", user: this.storedSession.user };
    } catch (error) {
      if (error instanceof NetworkError || (error instanceof ApiError && error.status >= 500)) {
        return { status: "offline", user: this.storedSession.user };
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
    const result = await requestJson<AuthResponse>(this.fetcher, `${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const storedSession = { refreshToken: result.refresh_token, user: result.user };
    await this.storage.write(storedSession);
    this.accessToken = result.access_token;
    this.storedSession = storedSession;
    return result.user;
  }

  private async performRefresh(): Promise<boolean> {
    if (!this.storedSession) return false;
    try {
      const result = await requestJson<TokenResponse>(
        this.fetcher,
        `${this.baseUrl}/api/v1/auth/refresh`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: this.storedSession.refreshToken }),
        }
      );
      const storedSession = { ...this.storedSession, refreshToken: result.refresh_token };
      await this.storage.write(storedSession);
      this.accessToken = result.access_token;
      this.storedSession = storedSession;
      return true;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await this.clearLocalSession();
        return false;
      }
      throw error;
    }
  }

  private async refreshAccessToken(): Promise<boolean> {
    if (!this.refreshInFlight) {
      this.refreshInFlight = this.performRefresh().finally(() => {
        this.refreshInFlight = null;
      });
    }
    return this.refreshInFlight;
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.accessToken && !(await this.refreshAccessToken())) {
      throw new ApiError(401, { detail: "authentication required" });
    }
    const send = () =>
      requestJson<T>(this.fetcher, `${this.baseUrl}${path}`, {
        ...init,
        headers: {
          ...(init.body ? { "Content-Type": "application/json" } : {}),
          ...init.headers,
          Authorization: `Bearer ${this.accessToken}`,
        },
      });
    try {
      return await send();
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      if (!(await this.refreshAccessToken())) throw error;
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
      // Local logout must succeed even when the device is offline.
    }
  }

  private async clearLocalSession(): Promise<void> {
    this.accessToken = null;
    this.storedSession = null;
    await this.storage.clear();
  }
}
