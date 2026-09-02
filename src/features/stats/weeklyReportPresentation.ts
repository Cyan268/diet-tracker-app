import type { WeeklyReportResponse } from "@/api/types";

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
