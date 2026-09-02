import type { SQLiteDatabase } from "expo-sqlite";
import { withWriteTransaction } from "../src/db/transactions";

describe("withWriteTransaction", () => {
  test("serializes web callbacks and releases the gate after rollback", async () => {
    let release!: () => void;
    let entered!: () => void;
    const ready = new Promise<void>((resolve) => {
      entered = resolve;
    });
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const order: string[] = [];
    const db = {
      withTransactionAsync: async (task: () => Promise<void>) => task(),
    } as SQLiteDatabase;
    const first = withWriteTransaction(
      db,
      async () => {
        order.push("first");
        entered();
        await gate;
        throw new Error("rollback");
      },
      "web"
    );
    const rejected = expect(first).rejects.toThrow("rollback");
    await ready;
    const second = withWriteTransaction(
      db,
      async () => {
        order.push("second");
      },
      "web"
    );
    await Promise.resolve();
    expect(order).toEqual(["first"]);
    release();
    await rejected;
    await second;
    expect(order).toEqual(["first", "second"]);
  });
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
