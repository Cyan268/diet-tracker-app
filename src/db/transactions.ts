import type { SQLiteDatabase } from "expo-sqlite";
import { Platform } from "react-native";

const writeQueues = new WeakMap<SQLiteDatabase, Promise<void>>();

export async function withWriteTransaction<T>(
  database: SQLiteDatabase,
  task: (transaction: SQLiteDatabase) => Promise<T>,
  platform = Platform.OS
): Promise<T> {
  let result: T;
  const previous = writeQueues.get(database) ?? Promise.resolve();
  const current = previous.then(async () => {
    if (platform === "web") {
      await database.withTransactionAsync(async () => {
        result = await task(database);
      });
    } else {
      await database.withExclusiveTransactionAsync(async (txn) => {
        result = await task(txn);
      });
    }
  });
  // A rejected transaction must not poison subsequent writers.
  const tail = current.catch(() => undefined);
  writeQueues.set(database, tail);
  try {
    await current;
  } finally {
    if (writeQueues.get(database) === tail) writeQueues.delete(database);
  }
  return result!;
}
