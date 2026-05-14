import { getDailySummary, getLogsByDate } from "@/db/repositories/logRepository";
import type { DailySummary, FoodLog } from "@/types/log";

export async function getTodaySummary(date: string): Promise<DailySummary> {
  return getDailySummary(date);
}

export async function getTodayLogs(date: string): Promise<FoodLog[]> {
  return getLogsByDate(date);
}
