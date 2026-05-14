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
