import type { Ionicons } from "@expo/vector-icons";

export interface ReminderRule {
  id: string;
  metric: string;
  ruleType: "too_high" | "too_low";
  thresholdType: "fixed" | "ratio_of_target";
  thresholdValue: number;
  enabled: boolean;
}

export interface Reminder {
  icon: keyof typeof Ionicons.glyphMap;
  message: string;
  type: "warning" | "info";
}
