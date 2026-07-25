import type { AuthUser } from "@/api/types";
import { ApiError } from "@/api/http";
import { AuthSession, type SessionStatus } from "./authSession";
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

  useEffect(() => {
    session
      .restore()
      .then((snapshot) => {
        if (!snapshot.user) {
          clearLocalAccount();
          setUser(null);
          setStatus(snapshot.status);
          return;
        }
        return activateLocalAccount(snapshot.user.id).then(() => {
          setUser(snapshot.user);
          setStatus(snapshot.status);
        });
      })
      .catch(() => {
        setUser(null);
        setStatus("unauthenticated");
      });
  }, [session]);

  const authenticate = useCallback(
    async (mode: "login" | "register", email: string, password: string) => {
      const authenticatedUser = await session[mode](email, password);
      await activateLocalAccount(authenticatedUser.id);
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
    await session.logout();
    clearLocalAccount();
    setUser(null);
    setLastSyncAt(null);
    setStatus("unauthenticated");
  }, [session]);
  const apiRequest = useCallback(
    <T,>(path: string, init?: RequestInit) => session.request<T>(path, init),
    [session]
  );
  const syncNow = useCallback(async () => {
    setSyncing(true);
    try {
      const result = await syncPendingEvents(session);
      if (!result.pullFailed) setStatus("authenticated");
      setLastSyncAt(Date.now());
      return result;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await session.logout();
        clearLocalAccount();
        setUser(null);
        setStatus("unauthenticated");
      }
      throw error;
    } finally {
      setSyncing(false);
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
