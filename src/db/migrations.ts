import type { SQLiteDatabase } from "expo-sqlite";
import { createTables } from "./schema";

interface Migration {
  version: number;
  name: string;
  up: (db: SQLiteDatabase) => Promise<void>;
}

const migrations: readonly Migration[] = [
  {
    version: 1,
    name: "initial_schema",
    up: createTables,
  },
  {
    version: 2,
    name: "add_sync_outbox",
    up: async (db) => {
      await db.execAsync(`
        ALTER TABLE user_profile ADD COLUMN owner_user_id TEXT;
        ALTER TABLE food_logs ADD COLUMN server_id TEXT;
        ALTER TABLE food_logs ADD COLUMN server_version INTEGER;
        ALTER TABLE food_logs ADD COLUMN owner_user_id TEXT;
        ALTER TABLE food_logs ADD COLUMN sync_status TEXT NOT NULL DEFAULT 'pending'
          CHECK (sync_status IN ('pending', 'synced', 'failed'));
        ALTER TABLE food_logs ADD COLUMN last_sync_error TEXT;

        CREATE TABLE outbox_events (
          id TEXT PRIMARY KEY NOT NULL,
          owner_user_id TEXT,
          aggregate_type TEXT NOT NULL,
          aggregate_id TEXT NOT NULL,
          operation TEXT NOT NULL CHECK (operation IN ('create', 'update', 'delete')),
          payload TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'processing', 'failed', 'blocked')),
          attempt_count INTEGER NOT NULL DEFAULT 0,
          next_attempt_at TEXT NOT NULL,
          last_error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE INDEX idx_outbox_ready
          ON outbox_events(status, next_attempt_at, created_at);
        CREATE INDEX idx_outbox_aggregate
          ON outbox_events(aggregate_type, aggregate_id);
        CREATE INDEX idx_outbox_owner
          ON outbox_events(owner_user_id, status, next_attempt_at);
        CREATE INDEX idx_food_logs_owner_date
          ON food_logs(owner_user_id, date);
        CREATE UNIQUE INDEX idx_user_profile_owner
          ON user_profile(owner_user_id) WHERE owner_user_id IS NOT NULL;

        INSERT INTO outbox_events (
          id, owner_user_id, aggregate_type, aggregate_id, operation, payload,
          status, attempt_count, next_attempt_at, created_at, updated_at
        )
        SELECT
          lower(hex(randomblob(16))),
          owner_user_id,
          'food_log',
          id,
          'create',
          json_object(
            'client_id', id,
            'log_date', date,
            'meal_type', meal_type,
            'custom_name', COALESCE(custom_name, '饮食记录'),
            'amount', amount,
            'unit', unit,
            'nutrition', json_object(
              'kcal', kcal,
              'protein', protein,
              'fat', fat,
              'carbs', carbs,
              'sugar', sugar,
              'sodium', sodium,
              'caffeine', caffeine
            ),
            'note', note
          ),
          'pending',
          0,
          updated_at,
          created_at,
          updated_at
        FROM food_logs;
      `);
    },
  },
  {
    version: 3,
    name: "add_pull_sync_and_conflicts",
    up: async (db) => {
      await db.execAsync(`
        CREATE TABLE sync_cursors (
          owner_user_id TEXT PRIMARY KEY NOT NULL,
          log_cursor INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE sync_conflicts (
          id TEXT PRIMARY KEY NOT NULL,
          owner_user_id TEXT NOT NULL,
          aggregate_id TEXT NOT NULL,
          remote_operation TEXT NOT NULL CHECK (remote_operation IN ('upsert', 'delete')),
          remote_cursor INTEGER NOT NULL,
          remote_payload TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(owner_user_id, aggregate_id)
        );

        CREATE INDEX idx_sync_conflicts_owner
          ON sync_conflicts(owner_user_id, updated_at);
      `);
    },
  },
  {
    version: 4,
    name: "freeze_outbox_requests",
    up: async (db) => {
      await db.execAsync(`
        ALTER TABLE outbox_events ADD COLUMN first_attempt_at TEXT;
        ALTER TABLE outbox_events ADD COLUMN request_path TEXT;
        ALTER TABLE outbox_events ADD COLUMN request_body TEXT;
        ALTER TABLE outbox_events ADD COLUMN queue_order INTEGER NOT NULL DEFAULT 0;
        UPDATE outbox_events SET queue_order = rowid;
        UPDATE outbox_events SET first_attempt_at = updated_at
          WHERE attempt_count > 0 OR status IN ('processing', 'failed', 'blocked');
        CREATE UNIQUE INDEX idx_outbox_order ON outbox_events(queue_order);
        CREATE INDEX idx_outbox_predecessor
          ON outbox_events(owner_user_id, aggregate_id, queue_order);
        ALTER TABLE food_logs ADD COLUMN remote_client_id TEXT;
        UPDATE food_logs SET remote_client_id = (
          SELECT json_extract(payload, '$.client_id') FROM outbox_events
          WHERE aggregate_id = food_logs.id AND owner_user_id = food_logs.owner_user_id
            AND operation = 'create' LIMIT 1
        );
        CREATE UNIQUE INDEX idx_food_logs_remote_client
          ON food_logs(owner_user_id, remote_client_id) WHERE remote_client_id IS NOT NULL;
      `);
    },
  },
];

export const LATEST_SCHEMA_VERSION = migrations.at(-1)?.version ?? 0;

export function getPendingMigrations(currentVersion: number): readonly Migration[] {
  if (!Number.isInteger(currentVersion) || currentVersion < 0) {
    throw new Error(`Invalid database version: ${currentVersion}`);
  }

  if (currentVersion > LATEST_SCHEMA_VERSION) {
    throw new Error(
      `Database version ${currentVersion} is newer than supported version ${LATEST_SCHEMA_VERSION}`
    );
  }

  return migrations.filter((migration) => migration.version > currentVersion);
}

export async function migrateDatabase(db: SQLiteDatabase): Promise<void> {
  const versionRow = await db.getFirstAsync<{ user_version: number }>("PRAGMA user_version;");
  const currentVersion = versionRow?.user_version ?? 0;
  const pendingMigrations = getPendingMigrations(currentVersion);

  for (const migration of pendingMigrations) {
    await db.execAsync("BEGIN IMMEDIATE;");
    try {
      await migration.up(db);
      await db.execAsync(`PRAGMA user_version = ${migration.version};`);
      await db.execAsync("COMMIT;");
    } catch (error) {
      await db.execAsync("ROLLBACK;").catch(() => undefined);
      throw new Error(`Database migration ${migration.version}_${migration.name} failed`, {
        cause: error,
      });
    }
  }
}
