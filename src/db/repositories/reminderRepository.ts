import { getDatabase } from "../database";
import type { ReminderRule } from "@/types/reminder";

function rowToRule(row: any): ReminderRule {
  return {
    id: row.id,
    metric: row.metric,
    ruleType: row.rule_type,
    thresholdType: row.threshold_type,
    thresholdValue: row.threshold_value,
    enabled: row.enabled === 1,
  };
}

export async function getEnabledRules(): Promise<ReminderRule[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<any>(
    "SELECT * FROM reminder_rules WHERE enabled = 1"
  );
  return rows.map(rowToRule);
}

export async function getAllRules(): Promise<ReminderRule[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<any>(
    "SELECT * FROM reminder_rules ORDER BY metric"
  );
  return rows.map(rowToRule);
}

export async function updateRule(
  id: string,
  updates: { enabled?: boolean; thresholdValue?: number }
): Promise<void> {
  const db = await getDatabase();
  const fields: string[] = [];
  const values: any[] = [];

  if (updates.enabled !== undefined) {
    fields.push("enabled = ?");
    values.push(updates.enabled ? 1 : 0);
  }
  if (updates.thresholdValue !== undefined) {
    fields.push("threshold_value = ?");
    values.push(updates.thresholdValue);
  }

  if (fields.length === 0) return;

  values.push(id);
  await db.runAsync(
    `UPDATE reminder_rules SET ${fields.join(", ")} WHERE id = ?`,
    ...values
  );
}
