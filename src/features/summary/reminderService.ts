import type { DailySummary } from "@/types/log";
import type { DailyTargets } from "@/types/profile";
import type { ReminderRule, Reminder } from "@/types/reminder";

const REMINDER_MESSAGES: Record<
  string,
  { icon: Reminder["icon"]; message: string; type: Reminder["type"] }
> = {
  kcal_high: {
    icon: "flame",
    message: "今日热量已超过目标，晚餐可适当减少高油高糖食物。",
    type: "warning",
  },
  protein_low: {
    icon: "fitness",
    message: "今天蛋白质摄入偏低，可以考虑补充鸡蛋、牛奶、豆制品或瘦肉。",
    type: "info",
  },
  sugar_high: {
    icon: "water",
    message: "今天糖摄入偏高，奶茶/甜饮建议减少糖度或小料。",
    type: "warning",
  },
  sodium_high: {
    icon: "warning",
    message: "今天钠摄入偏高，后续饮食建议少盐、少加工食品。",
    type: "warning",
  },
  caffeine_high: {
    icon: "cafe",
    message: "今天咖啡因摄入较高，晚上尽量避免咖啡、浓茶和能量饮料。",
    type: "warning",
  },
};

function getActualValue(metric: string, summary: DailySummary): number {
  switch (metric) {
    case "kcal":
      return summary.totalKcal;
    case "protein":
      return summary.totalProtein;
    case "sugar":
      return summary.totalSugar;
    case "sodium":
      return summary.totalSodium;
    case "caffeine":
      return summary.totalCaffeine;
    default:
      return 0;
  }
}

function getTargetValue(metric: string, targets: DailyTargets): number {
  switch (metric) {
    case "kcal":
      return targets.kcal;
    case "protein":
      return targets.protein;
    case "sugar":
      return targets.sugar;
    case "sodium":
      return targets.sodium;
    case "caffeine":
      return targets.caffeine;
    default:
      return 0;
  }
}

export function generateReminders(
  summary: DailySummary,
  targets: DailyTargets,
  rules: ReminderRule[]
): Reminder[] {
  const reminders: Reminder[] = [];

  for (const rule of rules) {
    if (!rule.enabled) continue;

    const actual = getActualValue(rule.metric, summary);
    const target = getTargetValue(rule.metric, targets);

    const threshold =
      rule.thresholdType === "ratio_of_target" ? target * rule.thresholdValue : rule.thresholdValue;

    let triggered = false;
    if (rule.ruleType === "too_high" && actual > threshold) triggered = true;
    if (rule.ruleType === "too_low" && actual < threshold && actual > 0) triggered = true;

    if (triggered) {
      const key = `${rule.metric}_${rule.ruleType === "too_high" ? "high" : "low"}`;
      const template = REMINDER_MESSAGES[key];
      if (template) {
        reminders.push(template);
      }
    }
  }

  return reminders;
}
