import type { WeeklyReportResponse } from "@/api/types";

type WeeklyFacts = WeeklyReportResponse["facts"];

export function getWeeklyReportProviderLabel(
  report: Pick<WeeklyReportResponse, "provider" | "fallback_used">
): string {
  if (report.fallback_used) return "AI 异常 · 本地降级";
  if (report.provider.startsWith("openai")) return "AI 结构化周报";
  return "本地规则周报";
}

export function formatWeeklyChange(value: number | null): string {
  if (value === null) return "记录不足，暂不比较";
  if (Math.abs(value) < 0.05) return "与上周持平";
  return `较上周${value > 0 ? "增加" : "减少"} ${Math.abs(value).toFixed(1)}%`;
}

export function formatCoverage(daysWithRecords: number): string {
  return `${daysWithRecords}/7 天`;
}

export function formatWeeklyMealShare(
  facts: WeeklyFacts,
  mealType: WeeklyFacts["meal_structure"][number]["meal_type"]
): string {
  const item = facts.meal_structure.find((candidate) => candidate.meal_type === mealType);
  const percentage = (item?.kcal_ratio ?? 0) * 100;
  return `${percentage.toFixed(1)}%`;
}

export function formatTargetAdherence(facts: WeeklyFacts): string {
  const adherence = facts.target_adherence;
  if (!adherence.available || adherence.kcal_within_target_days === null) {
    return "资料或记录不足，暂不判断目标达标天数";
  }
  return (
    `热量目标范围内 ${adherence.kcal_within_target_days}/` +
    `${adherence.assessment_days} 个记录日（产品规则：目标 ±${adherence.tolerance_percent}%）`
  );
}
