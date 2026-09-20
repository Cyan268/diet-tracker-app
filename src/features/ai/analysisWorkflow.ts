import type {
  AnalysisConfirmRequest,
  AnalysisConfirmationResponse,
  AnalysisDraftEntityResponse,
  AnalysisDraftResponse,
  SyncChangeResponse,
} from "@/api/types";
import { ApiError, NetworkError } from "@/api/http";
import { getDatabase } from "@/db/database";
import { withWriteTransaction } from "@/db/transactions";
import type { AuthRequestScope } from "@/features/auth/authSession";
import { assertSyncScope } from "@/features/sync/syncScope";
import { upsertRemoteLog } from "@/features/sync/pullSyncService";
import type { MealType } from "@/types/log";
import { v4 as uuidv4 } from "uuid";

export interface EditableAnalysisEntity {
  source: AnalysisDraftEntityResponse;
  amountText: string;
  unit: string;
  mealType: MealType;
  selectedFoodId: string | null;
  selectedRevision: string | null;
  logClientId: string;
  removed: boolean;
}

export interface EditableAnalysisDraft {
  id: string;
  version: number;
  logDate: string;
  expiresAt: string;
  entities: EditableAnalysisEntity[];
}

export function createEditableDraft(response: AnalysisDraftResponse): EditableAnalysisDraft {
  return {
    id: response.id,
    version: response.version,
    logDate: response.log_date,
    expiresAt: response.expires_at,
    entities: response.entities.map((entity) => ({
      source: entity,
      amountText: String(entity.amount),
      unit: entity.unit,
      mealType: entity.meal_type,
      selectedFoodId: entity.matched_food_id,
      selectedRevision: entity.catalog_revision,
      logClientId: uuidv4(),
      removed: false,
    })),
  };
}

export function parseEditableDraft(value: string): EditableAnalysisDraft {
  const parsed = JSON.parse(value) as EditableAnalysisDraft;
  if (!parsed.id || !Array.isArray(parsed.entities)) throw new Error("cached draft is invalid");
  return parsed;
}

export function confirmationBlockReason(draft: EditableAnalysisDraft): string | null {
  const active = draft.entities.filter((entity) => !entity.removed);
  if (active.length === 0) return "至少保留一项食品";
  for (const entity of active) {
    const amount = Number(entity.amountText);
    if (!Number.isFinite(amount) || amount <= 0) return "份量必须是大于 0 的数字";
    if (!entity.unit.trim()) return "请填写单位";
    if (!entity.selectedFoodId || !entity.selectedRevision) return "每一项都必须选择食品候选";
    const selected = entity.source.candidates.find(
      (candidate) => candidate.food_item_id === entity.selectedFoodId
    );
    if (!selected) return "所选食品已不在候选列表，请重新分析";
    if (!selected.nutrition_complete) return `${selected.name} 的营养数据不完整，不能直接确认`;
  }
  return null;
}

export function buildConfirmationRequest(
  draft: EditableAnalysisDraft,
  confirmationId: string
): AnalysisConfirmRequest {
  const reason = confirmationBlockReason(draft);
  if (reason) throw new Error(reason);
  return {
    client_confirmation_id: confirmationId,
    expected_draft_version: draft.version,
    entities: draft.entities
      .filter((entity) => !entity.removed)
      .map((entity) => ({
        source_entity_id: entity.source.id,
        client_id: entity.logClientId,
        food_item_id: entity.selectedFoodId!,
        catalog_revision: entity.selectedRevision!,
        amount: Number(entity.amountText),
        unit: entity.unit.trim(),
        meal_type: entity.mealType,
      })),
  };
}

export async function applyAnalysisConfirmation(
  scope: AuthRequestScope,
  confirmation: AnalysisConfirmationResponse
): Promise<void> {
  assertSyncScope(scope);
  const logsById = new Map(confirmation.logs.map((log) => [log.id, log]));
  if (confirmation.log_identities.length !== confirmation.logs.length) {
    throw new Error("confirmation identity mapping is incomplete");
  }
  const db = await getDatabase();
  await withWriteTransaction(db, async (txn) => {
    assertSyncScope(scope);
    for (const identity of confirmation.log_identities) {
      const log = logsById.get(identity.log_id);
      if (!log || log.client_id !== identity.client_id) {
        throw new Error("confirmation identity mapping does not match its log snapshot");
      }
      const change: SyncChangeResponse = {
        cursor: 0,
        operation: "upsert",
        server_id: identity.log_id,
        client_id: identity.client_id,
        version: log.version,
        log,
      };
      await upsertRemoteLog(txn, scope.ownerUserId, identity.client_id, change);
    }
    assertSyncScope(scope);
  });
}

export function analysisErrorMessage(error: unknown): string {
  if (error instanceof NetworkError) return "网络连接中断，任务状态已保留，可以稍后继续。";
  if (error instanceof ApiError) {
    const body = error.body as { detail?: unknown } | null;
    const detail = typeof body?.detail === "string" ? body.detail : null;
    if (error.status === 409) return detail ?? "草稿已变化，请刷新后再确认。";
    if (error.status === 429) return "排队任务较多，请等待已有任务完成。";
    if (error.status === 404) return "任务或草稿已失效，请重新分析。";
    if (error.status >= 500) return "AI 服务暂时不可用，任务状态已保留。";
  }
  return error instanceof Error ? error.message : "发生未知错误，请稍后重试。";
}
