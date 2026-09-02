import type { SQLiteDatabase } from "expo-sqlite";
import { activateLocalAccount, clearLocalAccount, getCurrentUserId } from "@/db/accountScope";
import { getLogsByDate } from "@/db/repositories/logRepository";

const mockGetDatabase = jest.fn();
jest.mock("@/db/database", () => ({
  getDatabase: () => mockGetDatabase(),
}));

describe("local account isolation", () => {
  afterEach(() => clearLocalAccount());

  it("claims legacy rows and filters log queries by the active user", async () => {
    const runAsync = jest.fn().mockResolvedValue({ changes: 1 });
    const getAllAsync = jest.fn().mockResolvedValue([]);
    const db = {
      runAsync,
      getAllAsync,
      withExclusiveTransactionAsync: jest.fn(async (task) => task(db)),
    } as unknown as SQLiteDatabase;
    mockGetDatabase.mockResolvedValue(db);

    await activateLocalAccount("user-a");
    await getLogsByDate("2026-07-15");

    expect(runAsync).toHaveBeenCalledWith(
      "UPDATE food_logs SET owner_user_id = ? WHERE owner_user_id IS NULL",
      "user-a"
    );
    expect(getAllAsync).toHaveBeenCalledWith(
      "SELECT * FROM food_logs WHERE date = ? AND owner_user_id = ? ORDER BY created_at",
      "2026-07-15",
      "user-a"
    );
  });

  it("does not allow repository access without an active account", () => {
    clearLocalAccount();
    expect(() => getCurrentUserId()).toThrow("No active local account scope");
  });
});
