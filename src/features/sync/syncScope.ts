import { getCurrentUserId } from "@/db/accountScope";
import {
  SessionChangedError,
  type AuthRequestScope,
  type AuthSession,
} from "@/features/auth/authSession";

export function assertSyncScope(scope: AuthRequestScope): void {
  scope.assertCurrent();
  try {
    if (getCurrentUserId() === scope.ownerUserId) return;
  } catch {
    /* A cleared local scope also invalidates in-flight work. */
  }
  throw new SessionChangedError();
}

export function captureSyncScope(auth: AuthSession): AuthRequestScope {
  const scope = auth.capture();
  assertSyncScope(scope);
  return scope;
}
