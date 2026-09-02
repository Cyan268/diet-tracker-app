import { DatabaseSync, type SQLInputValue } from "node:sqlite";
import type { SQLiteDatabase } from "expo-sqlite";

// Real SQLite for repository SQL tests; this does not emulate Expo's browser Worker.
export function createTestDatabase(): { db: SQLiteDatabase; close: () => void } {
  const connection = new DatabaseSync(":memory:");
  const transaction = async (task: (db: SQLiteDatabase) => Promise<void>) => {
    connection.exec("BEGIN IMMEDIATE");
    try {
      await task(db);
      connection.exec("COMMIT");
    } catch (error) {
      connection.exec("ROLLBACK");
      throw error;
    }
  };
  const db = {
    execAsync: async (sql: string) => {
      connection.exec(sql);
    },
    runAsync: async (sql: string, ...values: SQLInputValue[]) => {
      const result = connection.prepare(sql).run(...values);
      return { changes: Number(result.changes), lastInsertRowId: Number(result.lastInsertRowid) };
    },
    getFirstAsync: async (sql: string, ...values: SQLInputValue[]) =>
      connection.prepare(sql).get(...values) ?? null,
    getAllAsync: async (sql: string, ...values: SQLInputValue[]) =>
      connection.prepare(sql).all(...values),
    withTransactionAsync: async (task: () => Promise<void>) => transaction(task),
    withExclusiveTransactionAsync: transaction,
  } as unknown as SQLiteDatabase;
  return { db, close: () => connection.close() };
}
