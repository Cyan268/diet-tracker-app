import { generateReminders } from "@/features/summary/reminderService";
import type { DailySummary } from "@/types/log";
import type { DailyTargets } from "@/types/profile";
import type { ReminderRule } from "@/types/reminder";

const summary: DailySummary = {
  date: "2026-07-15",
  totalKcal: 2100,
  totalProtein: 40,
  totalFat: 60,
  totalCarbs: 260,
  totalSugar: 55,
  totalSodium: 1800,
  totalCaffeine: 120,
  mealBreakdown: { breakfast: 400, lunch: 700, dinner: 700, snack: 100, drink: 200 },
};

const targets: DailyTargets = {
  kcal: 2000,
  protein: 100,
  fat: 65,
  carbs: 300,
  sugar: 50,
  sodium: 2300,
  caffeine: 400,
};

function buildRule(overrides: Partial<ReminderRule>): ReminderRule {
  return {
    id: "rule-1",
    metric: "kcal",
    ruleType: "too_high",
    thresholdType: "ratio_of_target",
    thresholdValue: 1,
    enabled: true,
    ...overrides,
  };
}

describe("generateReminders", () => {
  it("超过目标比例时生成热量提醒", () => {
    const reminders = generateReminders(summary, targets, [buildRule({})]);

    expect(reminders).toHaveLength(1);
    expect(reminders[0].type).toBe("warning");
    expect(reminders[0].message).toContain("热量");
  });

  it("低于固定蛋白质阈值时生成提醒", () => {
    const reminders = generateReminders(summary, targets, [
      buildRule({
        metric: "protein",
        ruleType: "too_low",
        thresholdType: "fixed",
        thresholdValue: 60,
      }),
    ]);

    expect(reminders).toHaveLength(1);
    expect(reminders[0].message).toContain("蛋白质");
  });

  it("没有任何摄入时不触发摄入不足提醒", () => {
    const reminders = generateReminders({ ...summary, totalProtein: 0 }, targets, [
      buildRule({
        metric: "protein",
        ruleType: "too_low",
        thresholdType: "fixed",
        thresholdValue: 60,
      }),
    ]);

    expect(reminders).toEqual([]);
  });

  it("忽略被禁用的规则", () => {
    const reminders = generateReminders(summary, targets, [buildRule({ enabled: false })]);

    expect(reminders).toEqual([]);
  });
});
