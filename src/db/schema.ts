import type { SQLiteDatabase } from "expo-sqlite";

export async function createTables(db: SQLiteDatabase): Promise<void> {
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS user_profile (
      id TEXT PRIMARY KEY NOT NULL,
      gender TEXT NOT NULL,
      age INTEGER NOT NULL,
      height_cm REAL NOT NULL,
      weight_kg REAL NOT NULL,
      activity_level TEXT NOT NULL,
      goal TEXT NOT NULL,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS food_items (
      id TEXT PRIMARY KEY NOT NULL,
      name TEXT NOT NULL,
      brand TEXT,
      category TEXT,
      serving_unit TEXT,
      serving_weight_g REAL,
      kcal_per_100g REAL NOT NULL,
      protein_per_100g REAL NOT NULL,
      fat_per_100g REAL NOT NULL,
      carbs_per_100g REAL NOT NULL,
      sugar_per_100g REAL NOT NULL DEFAULT 0,
      sodium_per_100g REAL NOT NULL DEFAULT 0,
      caffeine_per_100g REAL NOT NULL DEFAULT 0,
      source TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS food_logs (
      id TEXT PRIMARY KEY NOT NULL,
      date TEXT NOT NULL,
      meal_type TEXT NOT NULL,
      food_item_id TEXT,
      custom_name TEXT,
      amount REAL NOT NULL,
      unit TEXT NOT NULL,
      kcal REAL NOT NULL,
      protein REAL NOT NULL,
      fat REAL NOT NULL,
      carbs REAL NOT NULL,
      sugar REAL NOT NULL DEFAULT 0,
      sodium REAL NOT NULL DEFAULT 0,
      caffeine REAL NOT NULL DEFAULT 0,
      note TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY (food_item_id) REFERENCES food_items(id)
    );

    CREATE TABLE IF NOT EXISTS drink_options (
      id TEXT PRIMARY KEY NOT NULL,
      brand TEXT NOT NULL,
      drink_name TEXT NOT NULL,
      option_type TEXT NOT NULL,
      option_name TEXT NOT NULL,
      kcal_delta REAL NOT NULL DEFAULT 0,
      sugar_delta REAL NOT NULL DEFAULT 0,
      caffeine_delta REAL NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS reminder_rules (
      id TEXT PRIMARY KEY NOT NULL,
      metric TEXT NOT NULL,
      rule_type TEXT NOT NULL,
      threshold_type TEXT NOT NULL,
      threshold_value REAL NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1
    );

    CREATE INDEX IF NOT EXISTS idx_food_logs_date ON food_logs(date);
    CREATE INDEX IF NOT EXISTS idx_food_items_name ON food_items(name);
  `);
}
