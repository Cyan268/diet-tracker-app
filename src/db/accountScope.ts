import { getDatabase } from "./database";
import { withWriteTransaction } from "./transactions";

let currentUserId: string | null = null;

export function getCurrentUserId(): string {
  if (!currentUserId) throw new Error("No active local account scope");
  return currentUserId;
}

export async function activateLocalAccount(userId: string): Promise<void> {
  currentUserId = userId;
  const db = await getDatabase();
  await withWriteTransaction(db, async (txn) => {
    await txn.runAsync(
      "UPDATE user_profile SET owner_user_id = ? WHERE owner_user_id IS NULL",
      userId
    );
    await txn.runAsync(
      "UPDATE food_logs SET owner_user_id = ? WHERE owner_user_id IS NULL",
      userId
    );
    await txn.runAsync(
      "UPDATE outbox_events SET owner_user_id = ? WHERE owner_user_id IS NULL",
      userId
    );
  });
}

export function clearLocalAccount(): void {
  currentUserId = null;
}
