import type { AuthUser } from "@/api/types";
import { ApiError } from "@/api/http";
import { AuthSession, SessionChangedError, type SessionStatus } from "./authSession";
import { SecureSessionStorage } from "./secureSessionStorage";
import { syncPendingEvents, type SyncResult } from "@/features/sync/outboxSyncService";
import { activateLocalAccount, clearLocalAccount } from "@/db/accountScope";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";
import { AppState } from "react-native";

type AuthStatus = "loading" | SessionStatus;

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  login(email: string, password: string): Promise<void>;
  register(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
  apiRequest<T>(path: string, init?: RequestInit): Promise<T>;
  syncNow(): Promise<SyncResult>;
  syncing: boolean;
  lastSyncAt: number | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const sessionRef = useRef<AuthSession | null>(null);
  if (!sessionRef.current) sessionRef.current = new AuthSession(new SecureSessionStorage());
  const session = sessionRef.current;
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null);
  const viewEpoch = useRef(0);

  useEffect(() => {
    const operation = ++viewEpoch.current;
    session
      .restore()
      .then((snapshot) => {
        if (operation !== viewEpoch.current) return;
        if (!snapshot.user) {
          clearLocalAccount();
          setUser(null);
          setStatus(snapshot.status);
          return;
        }
        return activateLocalAccount(snapshot.user.id).then(() => {
          if (operation !== viewEpoch.current) return;
          setUser(snapshot.user);
          setStatus(snapshot.status);
        });
      })
      .catch(() => {
        if (operation !== viewEpoch.current) return;
        clearLocalAccount();
        setUser(null);
        setStatus("unauthenticated");
      });
  }, [session]);

  const authenticate = useCallback(
    async (mode: "login" | "register", email: string, password: string) => {
      const operation = ++viewEpoch.current;
      clearLocalAccount();
      setUser(null);
      setStatus("unauthenticated");
      setLastSyncAt(null);
      setSyncing(false);
      const authenticatedUser = await session[mode](email, password);
      if (operation !== viewEpoch.current) throw new SessionChangedError();
      await activateLocalAccount(authenticatedUser.id);
      if (operation !== viewEpoch.current) throw new SessionChangedError();
      setUser(authenticatedUser);
      setStatus("authenticated");
    },
    [session]
  );

  const login = useCallback(
    (email: string, password: string) => authenticate("login", email, password),
    [authenticate]
  );
  const register = useCallback(
    (email: string, password: string) => authenticate("register", email, password),
    [authenticate]
  );
  const logout = useCallback(async () => {
    ++viewEpoch.current;
    clearLocalAccount();
    setUser(null);
    setLastSyncAt(null);
    setStatus("unauthenticated");
    setSyncing(false);
    await session.logout();
  }, [session]);
  const apiRequest = useCallback(
    <T,>(path: string, init?: RequestInit) => session.request<T>(path, init),
    [session]
  );
  const syncNow = useCallback(async () => {
    const operation = viewEpoch.current;
    setSyncing(true);
    try {
      const result = await syncPendingEvents(session);
      if (operation !== viewEpoch.current) throw new SessionChangedError();
      if (!result.pullFailed) setStatus("authenticated");
      setLastSyncAt(Date.now());
      return result;
    } catch (error) {
      if (operation === viewEpoch.current && error instanceof ApiError && error.status === 401) {
        ++viewEpoch.current;
        clearLocalAccount();
        setUser(null);
        setStatus("unauthenticated");
        setSyncing(false);
        await session.logout();
      }
      throw error;
    } finally {
      if (operation === viewEpoch.current) setSyncing(false);
    }
  }, [session]);

  useEffect(() => {
    if (status !== "authenticated" && status !== "offline") return;
    const trigger = () => syncNow().catch(() => undefined);
    trigger();
    const interval = setInterval(trigger, 60_000);
    const subscription = AppState.addEventListener("change", (nextState) => {
      if (nextState === "active") trigger();
    });
    return () => {
      clearInterval(interval);
      subscription.remove();
    };
  }, [status, syncNow]);

  return (
    <AuthContext.Provider
      value={{
        status,
        user,
        login,
        register,
        logout,
        apiRequest,
        syncNow,
        syncing,
        lastSyncAt,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
