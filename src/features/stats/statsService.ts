import { getSummariesByDateRange, getMealBreakdownByDate, getDailySummary } from "@/db/repositories/logRepository";
import { getToday } from "@/utils/date";
import type { DailySummary } from "@/types/log";

const MEAL_COLORS: Record<string, string> = {
  breakfast: "#FF9800",
  lunch: "#4CAF50",
  dinner: "#5C6BC0",
  snack: "#FF5722",
  drink: "#795548",
};

const MEAL_LABELS: Record<string, string> = {
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  snack: "加餐",
  drink: "饮品",
};

function getDateRange(endDate: string, days: number): string[] {
  const dates: string[] = [];
  const d = new Date(endDate + "T00:00:00");
  for (let i = days - 1; i >= 0; i--) {
    const nd = new Date(d);
    nd.setDate(nd.getDate() - i);
    const y = nd.getFullYear();
    const m = String(nd.getMonth() + 1).padStart(2, "0");
    const day = String(nd.getDate()).padStart(2, "0");
    dates.push(`${y}-${m}-${day}`);
  }
  return dates;
}

function weekdayLabel(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  const names = ["日", "一", "二", "三", "四", "五", "六"];
  return names[d.getDay()];
}

export interface WeeklyData {
  labels: string[];
  kcalData: number[];
  caffeineData: number[];
}

export async function getWeeklyData(): Promise<WeeklyData> {
  const today = getToday();
  const dates = getDateRange(today, 7);
  const startDate = dates[0];

  const summaries = await getSummariesByDateRange(startDate, today);
  const summaryMap = new Map<string, DailySummary>();
  for (const s of summaries) summaryMap.set(s.date, s);

  const labels: string[] = [];
  const kcalData: number[] = [];
  const caffeineData: number[] = [];

  for (const d of dates) {
    labels.push(weekdayLabel(d));
    const s = summaryMap.get(d);
    kcalData.push(s ? Math.round(s.totalKcal) : 0);
    caffeineData.push(s ? Math.round(s.totalCaffeine) : 0);
  }

  return { labels, kcalData, caffeineData };
}

export interface MealBreakdownItem {
  name: string;
  kcal: number;
  color: string;
}

export async function getTodayMealBreakdown(): Promise<MealBreakdownItem[]> {
  const today = getToday();
  const rows = await getMealBreakdownByDate(today);
  return rows
    .filter((r) => r.kcal > 0)
    .map((r) => ({
      name: MEAL_LABELS[r.mealType] ?? r.mealType,
      kcal: Math.round(r.kcal),
      color: MEAL_COLORS[r.mealType] ?? "#999",
    }));
}

export interface TodayOverview {
  totalKcal: number;
  totalProtein: number;
  totalFat: number;
  totalCarbs: number;
  drinkKcal: number;
  drinkRatio: number;
}

export async function getTodayOverview(): Promise<TodayOverview> {
  const today = getToday();
  const summary = await getDailySummary(today);
  const drinkKcal = summary.mealBreakdown.drink;
  const total = summary.totalKcal;
  return {
    totalKcal: Math.round(total),
    totalProtein: Math.round(summary.totalProtein),
    totalFat: Math.round(summary.totalFat),
    totalCarbs: Math.round(summary.totalCarbs),
    drinkKcal: Math.round(drinkKcal),
    drinkRatio: total > 0 ? drinkKcal / total : 0,
  };
}
