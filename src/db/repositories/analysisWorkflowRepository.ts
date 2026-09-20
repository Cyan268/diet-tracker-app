import { v4 as uuidv4 } from "uuid";
import { getCurrentUserId } from "../accountScope";
import { getDatabase } from "../database";
import type { AnalysisWorkflowRow } from "../rows";
import { withWriteTransaction } from "../transactions";

export type AnalysisWorkflowPhase = AnalysisWorkflowRow["phase"];

export interface AnalysisWorkflow {
  id: string;
  ownerUserId: string;
  sourceType: "text" | "image";
  sourceText: string;
  sourceImageUri: string | null;
  uploadId: string | null;
  logDate: string;
  phase: AnalysisWorkflowPhase;
  jobId: string | null;
  draftId: string | null;
  confirmationId: string;
  draftSnapshot: string | null;
  confirmationRequest: string | null;
  confirmationSnapshot: string | null;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
}

function fromRow(row: AnalysisWorkflowRow): AnalysisWorkflow {
  return {
    id: row.id,
    ownerUserId: row.owner_user_id,
    sourceType: row.source_type,
    sourceText: row.source_text,
    sourceImageUri: row.source_image_uri,
    uploadId: row.upload_id,
    logDate: row.log_date,
    phase: row.phase,
    jobId: row.job_id,
    draftId: row.draft_id,
    confirmationId: row.confirmation_id,
    draftSnapshot: row.draft_snapshot,
    confirmationRequest: row.confirmation_request,
    confirmationSnapshot: row.confirmation_snapshot,
    lastError: row.last_error,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export async function createAnalysisWorkflow(
  sourceText: string,
  logDate: string
): Promise<AnalysisWorkflow> {
  const ownerUserId = getCurrentUserId();
  const now = new Date().toISOString();
  const workflow: AnalysisWorkflow = {
    id: uuidv4(),
    ownerUserId,
    sourceType: "text",
    sourceText,
    sourceImageUri: null,
    uploadId: null,
    logDate,
    phase: "submitting",
    jobId: null,
    draftId: null,
    confirmationId: uuidv4(),
    draftSnapshot: null,
    confirmationRequest: null,
    confirmationSnapshot: null,
    lastError: null,
    createdAt: now,
    updatedAt: now,
  };
  const db = await getDatabase();
  await withWriteTransaction(db, async (txn) => {
    await txn.runAsync(
      `INSERT INTO analysis_workflows (
         id, owner_user_id, source_type, source_text, source_image_uri, upload_id,
         log_date, phase, job_id, draft_id,
         confirmation_id, draft_snapshot, confirmation_request,
         confirmation_snapshot, last_error, created_at, updated_at
       ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL, ?, NULL, NULL, NULL, NULL, ?, ?)`,
      workflow.id,
      ownerUserId,
      workflow.sourceType,
      sourceText,
      logDate,
      workflow.phase,
      workflow.confirmationId,
      now,
      now
    );
  });
  return workflow;
}

export async function createImageAnalysisWorkflow(
  uploadId: string,
  sourceImageUri: string,
  logDate: string
): Promise<AnalysisWorkflow> {
  const ownerUserId = getCurrentUserId();
  const now = new Date().toISOString();
  const workflow: AnalysisWorkflow = {
    id: uuidv4(),
    ownerUserId,
    sourceType: "image",
    sourceText: "",
    sourceImageUri,
    uploadId,
    logDate,
    phase: "submitting",
    jobId: null,
    draftId: null,
    confirmationId: uuidv4(),
    draftSnapshot: null,
    confirmationRequest: null,
    confirmationSnapshot: null,
    lastError: null,
    createdAt: now,
    updatedAt: now,
  };
  const db = await getDatabase();
  await withWriteTransaction(db, async (txn) => {
    await txn.runAsync(
      `INSERT INTO analysis_workflows (
         id, owner_user_id, source_type, source_text, source_image_uri, upload_id,
         log_date, phase, job_id, draft_id, confirmation_id, draft_snapshot,
         confirmation_request, confirmation_snapshot, last_error, created_at, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, NULL, NULL, ?, ?)`,
      workflow.id,
      ownerUserId,
      workflow.sourceType,
      workflow.sourceText,
      sourceImageUri,
      uploadId,
      logDate,
      workflow.phase,
      workflow.confirmationId,
      now,
      now
    );
  });
  return workflow;
}

export async function getLatestAnalysisWorkflow(): Promise<AnalysisWorkflow | null> {
  const db = await getDatabase();
  const row = await db.getFirstAsync<AnalysisWorkflowRow>(
    `SELECT * FROM analysis_workflows
     WHERE owner_user_id = ?
     ORDER BY updated_at DESC LIMIT 1`,
    getCurrentUserId()
  );
  return row ? fromRow(row) : null;
}

export async function updateAnalysisWorkflow(
  id: string,
  updates: Partial<
    Pick<
      AnalysisWorkflow,
      | "phase"
      | "jobId"
      | "draftId"
      | "draftSnapshot"
      | "confirmationRequest"
      | "confirmationSnapshot"
      | "lastError"
    >
  >
): Promise<AnalysisWorkflow> {
  const ownerUserId = getCurrentUserId();
  const db = await getDatabase();
  let updated: AnalysisWorkflow | null = null;
  await withWriteTransaction(db, async (txn) => {
    const row = await txn.getFirstAsync<AnalysisWorkflowRow>(
      "SELECT * FROM analysis_workflows WHERE id = ? AND owner_user_id = ?",
      id,
      ownerUserId
    );
    if (!row) throw new Error("analysis workflow not found for the active account");
    const current = fromRow(row);
    const next: AnalysisWorkflow = {
      ...current,
      ...updates,
      updatedAt: new Date().toISOString(),
    };
    updated = next;
    await txn.runAsync(
      `UPDATE analysis_workflows SET
         phase = ?, job_id = ?, draft_id = ?, draft_snapshot = ?,
         confirmation_request = ?, confirmation_snapshot = ?, last_error = ?,
         updated_at = ?
       WHERE id = ? AND owner_user_id = ?`,
      next.phase,
      next.jobId,
      next.draftId,
      next.draftSnapshot,
      next.confirmationRequest,
      next.confirmationSnapshot,
      next.lastError,
      next.updatedAt,
      id,
      ownerUserId
    );
  });
  return updated!;
}

export async function deleteAnalysisWorkflow(id: string): Promise<void> {
  const db = await getDatabase();
  await withWriteTransaction(db, async (txn) => {
    await txn.runAsync(
      "DELETE FROM analysis_workflows WHERE id = ? AND owner_user_id = ?",
      id,
      getCurrentUserId()
    );
  });
}
