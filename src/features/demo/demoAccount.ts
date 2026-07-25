import type { AuthUser } from "@/api/types";

export function isDemoAccount(user: Pick<AuthUser, "is_demo"> | null): boolean {
  return user?.is_demo === true;
}

export function canManageAiCredentials(
  user: Pick<AuthUser, "is_demo"> | null,
  status: string
): boolean {
  return status !== "offline" && !isDemoAccount(user);
}
