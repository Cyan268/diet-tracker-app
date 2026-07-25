jest.mock("../src/db/database", () => ({ getDatabase: jest.fn() }));
jest.mock("@/db/accountScope", () => ({ getCurrentUserId: () => "user-1" }));
jest.mock("../src/db/transactions", () => ({ withWriteTransaction: jest.fn() }));
jest.mock("../src/db/repositories/outboxRepository", () => ({ enqueueLogEvent: jest.fn() }));
jest.mock("uuid", () => ({
  v4: jest.fn().mockReturnValueOnce("log-1").mockReturnValueOnce("log-2"),
}));

import { addLogs, type NewFoodLog } from "@/db/repositories/logRepository";

const mockRunAsync = jest.fn();
const { getDatabase: mockGetDatabase } = jest.requireMock("../src/db/database") as {
  getDatabase: jest.Mock;
};
const { withWriteTransaction: mockWithWriteTransaction } = jest.requireMock(
  "../src/db/transactions"
) as { withWriteTransaction: jest.Mock };
const { enqueueLogEvent: mockEnqueueLogEvent } = jest.requireMock(
  "../src/db/repositories/outboxRepository"
) as { enqueueLogEvent: jest.Mock };

function newLog(name: string): NewFoodLog {
  return {
    date: "2026-07-17",
    mealType: "lunch",
    customName: name,
    amount: 100,
    unit: "g",
    kcal: 100,
    protein: 10,
    fat: 2,
    carbs: 12,
    sugar: 0,
    sodium: 20,
    caffeine: 0,
  };
}

describe("addLogs", () => {
  beforeEach(() => {
    mockRunAsync.mockClear();
    mockGetDatabase.mockReset();
    mockGetDatabase.mockResolvedValue({ runAsync: mockRunAsync });
    mockEnqueueLogEvent.mockClear();
    mockWithWriteTransaction.mockReset();
    mockWithWriteTransaction.mockImplementation(async (database, task) => task(database));
  });

  it("writes all AI-confirmed records and outbox events in one transaction", async () => {
    const created = await addLogs([newLog("白米饭"), newLog("鸡胸肉")]);

    expect(mockWithWriteTransaction).toHaveBeenCalledTimes(1);
    expect(mockRunAsync).toHaveBeenCalledTimes(2);
    expect(mockEnqueueLogEvent).toHaveBeenCalledTimes(2);
    expect(created.map((log) => log.id)).toEqual(["log-1", "log-2"]);
  });
});
