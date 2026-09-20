import type { AnalysisConfirmationResponse, AnalysisDraftResponse, LogResponse } from "@/api/types";
import { activateLocalAccount, clearLocalAccount, getCurrentUserId } from "@/db/accountScope";
import { migrateDatabase } from "@/db/migrations";
import {
  createAnalysisWorkflow,
  createImageAnalysisWorkflow,
  deleteAnalysisWorkflow,
  getLatestAnalysisWorkflow,
  updateAnalysisWorkflow,
} from "@/db/repositories/analysisWorkflowRepository";
import {
  applyAnalysisConfirmation,
  buildConfirmationRequest,
  confirmationBlockReason,
  createEditableDraft,
} from "@/features/ai/analysisWorkflow";
import type { AuthRequestScope } from "@/features/auth/authSession";
import { createTestDatabase } from "../test-support/sqlite";

const mockGetDatabase = jest.fn();
jest.mock("@/db/database", () => ({ getDatabase: () => mockGetDatabase() }));

function draftResponse(nutritionComplete = true): AnalysisDraftResponse {
  return {
    id: "draft-1",
    job_id: "job-1",
    status: "review",
    version: 2,
    log_date: "2026-09-14",
    result_schema_version: "draft-v1",
    expires_at: "2026-09-15T00:00:00Z",
    created_at: "2026-09-14T00:00:00Z",
    updated_at: "2026-09-14T00:00:00Z",
    entities: [
      {
        id: "entity-1",
        position: 0,
        raw_name: "苹果",
        normalized_name: "苹果",
        amount: 1,
        unit: "个",
        meal_type: "snack",
        confidence: 0.95,
        needs_review: false,
        matched_food_id: "food-1",
        catalog_revision: "catalog-v1",
        candidates: [
          {
            food_item_id: "food-1",
            catalog_revision: "catalog-v1",
            name: "苹果",
            brand: null,
            source: "catalog",
            source_reference: "test",
            nutrition_complete: nutritionComplete,
            score: 1,
            reason: "canonical_exact",
          },
        ],
      },
    ],
  };
}

function remoteLog(id: string, clientId: string): LogResponse {
  return {
    id,
    client_id: clientId,
    log_date: "2026-09-14",
    meal_type: "snack",
    food_item_id: "food-1",
    custom_name: null,
    display_name: "苹果",
    nutrition_source: "catalog",
    catalog_revision: "catalog-v1",
    nutrition_source_reference: "test",
    amount: 1,
    unit: "个",
    kcal: 104,
    protein: 0.6,
    fat: 0.4,
    carbs: 28,
    sugar: 20,
    sodium: 2,
    caffeine: 0,
    note: "AI 草稿确认",
    version: 1,
    created_at: "2026-09-14T00:00:00Z",
    updated_at: "2026-09-14T00:00:00Z",
  };
}

function confirmation(
  entries: { logId: string; clientId: string; mappedClientId?: string }[]
): AnalysisConfirmationResponse {
  return {
    confirmation_id: "confirmation-1",
    draft_id: "draft-1",
    confirmed_draft_version: 2,
    created_at: "2026-09-14T00:00:00Z",
    log_identities: entries.map((entry) => ({
      entity_id: "entity-1",
      client_id: entry.mappedClientId ?? entry.clientId,
      log_id: entry.logId,
    })),
    logs: entries.map((entry) => remoteLog(entry.logId, entry.clientId)),
  };
}

function scope(ownerUserId: string): AuthRequestScope {
  return {
    ownerUserId,
    epoch: 1,
    assertCurrent: () => undefined,
    request: jest.fn(),
  };
}

describe("AI analysis workflow", () => {
  afterEach(() => {
    clearLocalAccount();
    jest.clearAllMocks();
  });

  it("builds a stable confirmation only for complete selected catalog data", () => {
    const editable = createEditableDraft(draftResponse());
    editable.entities[0].logClientId = "client-1";
    editable.entities[0].amountText = "1.5";

    expect(confirmationBlockReason(editable)).toBeNull();
    expect(buildConfirmationRequest(editable, "confirmation-1")).toEqual({
      client_confirmation_id: "confirmation-1",
      expected_draft_version: 2,
      entities: [
        {
          source_entity_id: "entity-1",
          client_id: "client-1",
          food_item_id: "food-1",
          catalog_revision: "catalog-v1",
          amount: 1.5,
          unit: "个",
          meal_type: "snack",
        },
      ],
    });

    const incomplete = createEditableDraft(draftResponse(false));
    expect(confirmationBlockReason(incomplete)).toMatch(/营养数据不完整/);
    incomplete.entities[0].removed = true;
    expect(confirmationBlockReason(incomplete)).toBe("至少保留一项食品");
  });

  it("persists and restores account-scoped workflow identities", async () => {
    const fixture = createTestDatabase();
    mockGetDatabase.mockResolvedValue(fixture.db);
    try {
      await migrateDatabase(fixture.db);
      await activateLocalAccount("owner-1");
      const created = await createAnalysisWorkflow("午餐一个苹果", "2026-09-14");
      const updated = await updateAnalysisWorkflow(created.id, {
        phase: "processing",
        jobId: "job-1",
      });
      const restored = await getLatestAnalysisWorkflow();

      expect(updated.confirmationId).toBe(created.confirmationId);
      expect(restored?.id).toBe(created.id);
      expect(restored?.jobId).toBe("job-1");
      await deleteAnalysisWorkflow(created.id);
      expect(await getLatestAnalysisWorkflow()).toBeNull();
    } finally {
      fixture.close();
    }
  });

  it("persists a verified upload identity for image workflow recovery", async () => {
    const fixture = createTestDatabase();
    mockGetDatabase.mockResolvedValue(fixture.db);
    try {
      await migrateDatabase(fixture.db);
      await activateLocalAccount("owner-1");
      const created = await createImageAnalysisWorkflow(
        "upload-1",
        "file:///private-preview.jpg",
        "2026-09-16"
      );
      const restored = await getLatestAnalysisWorkflow();

      expect(created.sourceType).toBe("image");
      expect(restored?.uploadId).toBe("upload-1");
      expect(restored?.sourceImageUri).toBe("file:///private-preview.jpg");
      expect(restored?.phase).toBe("submitting");
    } finally {
      fixture.close();
    }
  });

  it("applies a confirmation without an outbox event or cursor advance", async () => {
    const fixture = createTestDatabase();
    mockGetDatabase.mockResolvedValue(fixture.db);
    try {
      await migrateDatabase(fixture.db);
      await activateLocalAccount("owner-1");
      const result = confirmation([{ logId: "server-1", clientId: "client-1" }]);

      await applyAnalysisConfirmation(scope(getCurrentUserId()), result);
      await applyAnalysisConfirmation(scope(getCurrentUserId()), result);

      expect(
        await fixture.db.getFirstAsync<{ count: number }>(
          "SELECT COUNT(*) AS count FROM food_logs WHERE owner_user_id = 'owner-1'"
        )
      ).toEqual({ count: 1 });
      expect(
        await fixture.db.getFirstAsync<{ count: number }>(
          "SELECT COUNT(*) AS count FROM outbox_events"
        )
      ).toEqual({ count: 0 });
      expect(
        await fixture.db.getFirstAsync<{ count: number }>(
          "SELECT COUNT(*) AS count FROM sync_cursors"
        )
      ).toEqual({ count: 0 });
      const stored = await fixture.db.getFirstAsync<{
        id: string;
        server_id: string;
        custom_name: string;
        sync_status: string;
      }>("SELECT id, server_id, custom_name, sync_status FROM food_logs");
      expect(stored).toEqual({
        id: "client-1",
        server_id: "server-1",
        custom_name: "苹果",
        sync_status: "synced",
      });
    } finally {
      fixture.close();
    }
  });

  it("rolls back every local log when one identity mapping is invalid", async () => {
    const fixture = createTestDatabase();
    mockGetDatabase.mockResolvedValue(fixture.db);
    try {
      await migrateDatabase(fixture.db);
      await activateLocalAccount("owner-1");
      const result = confirmation([
        { logId: "server-1", clientId: "client-1" },
        {
          logId: "server-2",
          clientId: "client-2",
          mappedClientId: "wrong-client",
        },
      ]);

      await expect(applyAnalysisConfirmation(scope(getCurrentUserId()), result)).rejects.toThrow(
        /does not match/
      );
      expect(
        await fixture.db.getFirstAsync<{ count: number }>("SELECT COUNT(*) AS count FROM food_logs")
      ).toEqual({ count: 0 });
    } finally {
      fixture.close();
    }
  });
});
