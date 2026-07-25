import type { SQLiteDatabase } from "expo-sqlite";
import { withWriteTransaction } from "../src/db/transactions";

describe("withWriteTransaction", () => {
  test("uses the regular transaction API on web", async () => {
    const database = {
      withTransactionAsync: jest.fn(async (task: () => Promise<void>) => task()),
      withExclusiveTransactionAsync: jest.fn(),
    };
    const task = jest.fn(async () => undefined);

    await withWriteTransaction(database as unknown as SQLiteDatabase, task, "web");

    expect(database.withTransactionAsync).toHaveBeenCalledTimes(1);
    expect(database.withExclusiveTransactionAsync).not.toHaveBeenCalled();
    expect(task).toHaveBeenCalledWith(database);
  });

  test("keeps exclusive transactions on native platforms", async () => {
    const transaction = { runAsync: jest.fn() } as unknown as SQLiteDatabase;
    const database = {
      withTransactionAsync: jest.fn(),
      withExclusiveTransactionAsync: jest.fn(
        async (task: (value: SQLiteDatabase) => Promise<void>) => task(transaction)
      ),
    };
    const task = jest.fn(async () => undefined);

    await withWriteTransaction(database as unknown as SQLiteDatabase, task, "android");

    expect(database.withExclusiveTransactionAsync).toHaveBeenCalledTimes(1);
    expect(database.withTransactionAsync).not.toHaveBeenCalled();
    expect(task).toHaveBeenCalledWith(transaction);
  });
});
