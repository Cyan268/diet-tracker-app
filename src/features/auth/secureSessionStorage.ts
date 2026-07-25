import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";
import type { SessionStorage, StoredSession } from "./authSession";

const SESSION_KEY = "nutripilot.auth.session.v1";

function isStoredSession(value: unknown): value is StoredSession {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<StoredSession>;
  return (
    typeof candidate.refreshToken === "string" &&
    !!candidate.user &&
    typeof candidate.user.id === "string" &&
    typeof candidate.user.email === "string"
  );
}

export class SecureSessionStorage implements SessionStorage {
  async read(): Promise<StoredSession | null> {
    const raw =
      Platform.OS === "web"
        ? globalThis.sessionStorage.getItem(SESSION_KEY)
        : await SecureStore.getItemAsync(SESSION_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (isStoredSession(parsed)) return parsed;
    } catch {
      // Corrupted credentials are removed below.
    }
    await this.clear();
    return null;
  }

  async write(session: StoredSession): Promise<void> {
    if (Platform.OS === "web") {
      globalThis.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
      return;
    }
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(session), {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    });
  }

  async clear(): Promise<void> {
    if (Platform.OS === "web") {
      globalThis.sessionStorage.removeItem(SESSION_KEY);
      return;
    }
    await SecureStore.deleteItemAsync(SESSION_KEY);
  }
}
