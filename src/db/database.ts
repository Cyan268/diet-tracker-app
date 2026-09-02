import * as SQLite from "expo-sqlite";

let opening: Promise<SQLite.SQLiteDatabase> | null = null;

export async function getDatabase(): Promise<SQLite.SQLiteDatabase> {
  if (!opening) {
    opening = (async () => {
      const db = await SQLite.openDatabaseAsync("diet-tracker.db");
      await db.execAsync("PRAGMA journal_mode = WAL;");
      await db.execAsync("PRAGMA foreign_keys = ON;");
      return db;
    })().catch((error) => {
      opening = null;
      throw error;
    });
  }
  return opening;
}
