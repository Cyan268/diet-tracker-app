import type { SQLiteDatabase } from "expo-sqlite";
import { Platform } from "react-native";

export async function withWriteTransaction(
  database: SQLiteDatabase,
  task: (transaction: SQLiteDatabase) => Promise<void>,
  platform = Platform.OS
): Promise<void> {
  if (platform === "web") {
    await database.withTransactionAsync(() => task(database));
    return;
  }
  await database.withExclusiveTransactionAsync(task);
}
