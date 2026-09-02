import type { SQLiteDatabase } from "expo-sqlite";
import { buildLogSyncPayload, enqueueLogEvent } from "@/db/repositories/outboxRepository";
import type { FoodLog } from "@/types/log";
import { clearLocalAccount, activateLocalAccount } from "@/db/accountScope";

jest.mock("@/db/database", () => ({
  getDatabase: jest.fn(async () => ({
    withExclusiveTransactionAsync: async (task: (db: unknown) => Promise<void>) =>
      task({ runAsync: jest.fn().mockResolvedValue({ changes: 1 }) }),
  })),
}));

const LOG: FoodLog = {
  id: "00000000-0000-4000-8000-000000000010",
  date: "2026-07-15",
  mealType: "breakfast",
  foodItemId: "local-food-id",
  customName: "燕麦片",
  amount: 50,
  unit: "g",
  kcal: 190,
  protein: 6.5,
  fat: 3.5,
  carbs: 34,
  sugar: 0.5,
  sodium: 2.5,
  caffeine: 0,
  note: "早餐",
  createdAt: "2026-07-15T08:00:00.000Z",
  updatedAt: "2026-07-15T08:00:00.000Z",
};

function mockDatabase(existingCreateId: string | null): {
  db: SQLiteDatabase;
  runAsync: jest.Mock;
} {
  const runAsync = jest.fn().mockResolvedValue({ changes: 1 });
  const db = {
    getFirstAsync: jest
      .fn()
      .mockResolvedValue(
        existingCreateId ? { id: existingCreateId, payload: buildLogSyncPayload(LOG) } : null
      ),
    runAsync,
  } as unknown as SQLiteDatabase;
  return { db, runAsync };
}

describe("outbox repository", () => {
  beforeAll(async () => activateLocalAccount("user-1"));
  afterAll(() => clearLocalAccount());
  it("uses a custom nutrition snapshot instead of a device-local food id", () => {
    const payload = JSON.parse(buildLogSyncPayload(LOG));

    expect(payload.client_id).toBe(LOG.id);
    expect(payload.custom_name).toBe("燕麦片");
    expect(payload.food_item_id).toBeUndefined();
    expect(payload.nutrition).toMatchObject({ kcal: 190, protein: 6.5, carbs: 34 });
  });

  it("coalesces edits into an unsent create event", async () => {
    const { db, runAsync } = mockDatabase("create-event-id");

    await enqueueLogEvent(db, { ...LOG, amount: 60 }, "update", LOG.updatedAt);

    expect(runAsync).toHaveBeenCalledTimes(1);
    expect(runAsync.mock.calls[0][0]).toContain("UPDATE outbox_events");
    expect(runAsync.mock.calls[0][1]).toContain('"amount":60');
  });

  it("cancels an unsent create when the local record is deleted", async () => {
    const { db, runAsync } = mockDatabase("create-event-id");

    await enqueueLogEvent(db, LOG, "delete", LOG.updatedAt);

    expect(runAsync).toHaveBeenCalledWith(
      "DELETE FROM outbox_events WHERE owner_user_id = ? AND aggregate_id = ?",
      "user-1",
      LOG.id
    );
  });
});
