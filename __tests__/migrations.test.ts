import type { SQLiteDatabase } from "expo-sqlite";
import { getPendingMigrations, LATEST_SCHEMA_VERSION, migrateDatabase } from "@/db/migrations";

function createMockDatabase(currentVersion: number): {
  db: SQLiteDatabase;
  execAsync: jest.Mock<Promise<void>, [string]>;
} {
  const execAsync = jest.fn<Promise<void>, [string]>().mockResolvedValue(undefined);
  const db = {
    getFirstAsync: jest.fn().mockResolvedValue({ user_version: currentVersion }),
    execAsync,
  } as unknown as SQLiteDatabase;

  return { db, execAsync };
}

describe("database migrations", () => {
  it("为全新或旧版数据库返回按顺序排列的待执行迁移", () => {
    expect(getPendingMigrations(0).map((migration) => migration.version)).toEqual([1, 2, 3]);
    expect(getPendingMigrations(1).map((migration) => migration.version)).toEqual([2, 3]);
    expect(getPendingMigrations(LATEST_SCHEMA_VERSION)).toEqual([]);
  });

  it("拒绝由更高版本应用创建的数据库", () => {
    expect(() => getPendingMigrations(LATEST_SCHEMA_VERSION + 1)).toThrow(/newer than supported/);
  });

  it("迁移成功后在事务内更新版本并提交", async () => {
    const { db, execAsync } = createMockDatabase(0);

    await migrateDatabase(db);

    const statements = execAsync.mock.calls.map(([sql]) => sql);
    expect(statements[0]).toBe("BEGIN IMMEDIATE;");
    expect(statements.some((sql) => sql.includes("CREATE TABLE IF NOT EXISTS food_logs"))).toBe(
      true
    );
    expect(statements).toContain("PRAGMA user_version = 1;");
    expect(statements).toContain("PRAGMA user_version = 2;");
    expect(statements.some((sql) => sql.includes("CREATE TABLE outbox_events"))).toBe(true);
    expect(statements.some((sql) => sql.includes("owner_user_id"))).toBe(true);
    expect(statements.some((sql) => sql.includes("CREATE TABLE sync_cursors"))).toBe(true);
    expect(statements.some((sql) => sql.includes("CREATE TABLE sync_conflicts"))).toBe(true);
    expect(statements.at(-1)).toBe("COMMIT;");
  });

  it("迁移失败时回滚且不提交新版本", async () => {
    const { db, execAsync } = createMockDatabase(0);
    execAsync.mockImplementation(async (sql) => {
      if (sql.includes("CREATE TABLE IF NOT EXISTS")) throw new Error("schema failure");
    });

    await expect(migrateDatabase(db)).rejects.toThrow("1_initial_schema failed");

    const statements = execAsync.mock.calls.map(([sql]) => sql);
    expect(statements).toContain("ROLLBACK;");
    expect(statements).not.toContain("PRAGMA user_version = 1;");
    expect(statements).not.toContain("COMMIT;");
  });

  it("v2 Outbox 迁移失败时保留 v1 版本", async () => {
    const { db, execAsync } = createMockDatabase(1);
    execAsync.mockImplementation(async (sql) => {
      if (sql.includes("ALTER TABLE user_profile")) throw new Error("alter failure");
    });

    await expect(migrateDatabase(db)).rejects.toThrow("2_add_sync_outbox failed");

    const statements = execAsync.mock.calls.map(([sql]) => sql);
    expect(statements).toContain("ROLLBACK;");
    expect(statements).not.toContain("PRAGMA user_version = 2;");
  });

  it("v3 拉取同步迁移失败时保留 v2 版本", async () => {
    const { db, execAsync } = createMockDatabase(2);
    execAsync.mockImplementation(async (sql) => {
      if (sql.includes("CREATE TABLE sync_cursors")) throw new Error("cursor failure");
    });

    await expect(migrateDatabase(db)).rejects.toThrow("3_add_pull_sync_and_conflicts failed");

    const statements = execAsync.mock.calls.map(([sql]) => sql);
    expect(statements).toContain("ROLLBACK;");
    expect(statements).not.toContain("PRAGMA user_version = 3;");
  });
});
