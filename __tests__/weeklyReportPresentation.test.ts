import {
  formatCoverage,
  formatWeeklyChange,
  getWeeklyReportProviderLabel,
} from "@/features/stats/weeklyReportPresentation";

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
});
