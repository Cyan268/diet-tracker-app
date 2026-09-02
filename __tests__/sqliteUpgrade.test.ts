import { createTestDatabase } from "../test-support/sqlite";
import { getPendingMigrations, migrateDatabase } from "@/db/migrations";
import type { OutboxEventRow } from "@/db/rows";

test("v3 upgrade preserves payloads and conservatively freezes interrupted legacy attempts", async () => {
  const fixture = createTestDatabase();
  try {
    for (const migration of getPendingMigrations(0).filter((item) => item.version <= 3)) {
      await migration.up(fixture.db);
    }
    await fixture.db.execAsync("PRAGMA user_version = 3");
    for (const status of ["pending", "processing", "failed", "blocked"]) {
      await fixture.db.runAsync(
        `INSERT INTO outbox_events (id, owner_user_id, aggregate_type, aggregate_id, operation,
         payload, status, attempt_count, next_attempt_at, created_at, updated_at)
         VALUES (?, 'owner-a', 'food_log', ?, 'create', ?, ?, 0, 'now', 'same-time', 'now')`,
        status,
        status,
        JSON.stringify({ client_id: status, amount: 2 }),
        status
      );
    }
    await migrateDatabase(fixture.db);
    const rows = await fixture.db.getAllAsync<OutboxEventRow>(
      "SELECT * FROM outbox_events ORDER BY queue_order"
    );
    expect(rows.map((row) => row.id)).toEqual(["pending", "processing", "failed", "blocked"]);
    expect(rows[0].first_attempt_at).toBeNull();
    expect(rows.slice(1).every((row) => row.first_attempt_at === "now")).toBe(true);
    for (const row of rows) {
      expect(row.payload).toBe(JSON.stringify({ client_id: row.id, amount: 2 }));
      expect(row.request_path).toBeNull();
    }
  } finally {
    fixture.close();
  }
});
