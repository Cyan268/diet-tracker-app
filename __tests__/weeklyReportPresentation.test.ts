import {
  formatCoverage,
  formatTargetAdherence,
  formatWeeklyMealShare,
  formatWeeklyChange,
  getWeeklyReportProviderLabel,
} from "@/features/stats/weeklyReportPresentation";

const facts = {
  meal_structure: [
    { meal_type: "breakfast", log_count: 1, total_kcal: 300, kcal_ratio: 0.3 },
    { meal_type: "lunch", log_count: 1, total_kcal: 500, kcal_ratio: 0.5 },
    { meal_type: "dinner", log_count: 0, total_kcal: 0, kcal_ratio: 0 },
    { meal_type: "snack", log_count: 0, total_kcal: 0, kcal_ratio: 0 },
    { meal_type: "drink", log_count: 1, total_kcal: 200, kcal_ratio: 0.2 },
  ],
  target_adherence: {
    available: true,
    assessment_days: 5,
    kcal_within_target_days: 3,
    tolerance_percent: 10,
    rule: "recorded_day_kcal_within_target_plus_or_minus_10_percent",
  },
} as Parameters<typeof formatWeeklyMealShare>[0];

describe("weekly report presentation", () => {
  it("does not invent a comparison when facts are incomplete", () => {
    expect(formatWeeklyChange(null)).toBe("记录不足，暂不比较");
    expect(formatCoverage(3)).toBe("3/7 天");
  });

  it("formats neutral percentage changes", () => {
    expect(formatWeeklyChange(12.34)).toBe("较上周增加 12.3%");
    expect(formatWeeklyChange(-8)).toBe("较上周减少 8.0%");
    expect(formatWeeklyChange(0)).toBe("与上周持平");
  });

  it("makes fallback state visible", () => {
    expect(
      getWeeklyReportProviderLabel({
        provider: "rule_based_weekly_report_v1",
        fallback_used: true,
      })
    ).toBe("AI 异常 · 本地降级");
  });

  it("shows deterministic meal structure and target-rule wording", () => {
    expect(formatWeeklyMealShare(facts, "drink")).toBe("20.0%");
    expect(formatTargetAdherence(facts)).toBe("热量目标范围内 3/5 个记录日（产品规则：目标 ±10%）");
    expect(
      formatTargetAdherence({
        ...facts,
        target_adherence: {
          ...facts.target_adherence,
          available: false,
          kcal_within_target_days: null,
        },
      })
    ).toBe("资料或记录不足，暂不判断目标达标天数");
  });
});
