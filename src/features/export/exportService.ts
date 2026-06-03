import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { getDatabase } from "@/db/database";

interface ExportRow {
  date: string;
  meal_type: string;
  custom_name: string;
  amount: number;
  unit: string;
  kcal: number;
  protein: number;
  fat: number;
  carbs: number;
  sugar: number;
  sodium: number;
  caffeine: number;
  note: string;
}

const MEAL_LABELS: Record<string, string> = {
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  snack: "加餐",
  drink: "饮品",
};

async function fetchAllLogs(): Promise<ExportRow[]> {
  const db = await getDatabase();
  return db.getAllAsync<ExportRow>(
    `SELECT date, meal_type, custom_name, amount, unit, kcal, protein, fat, carbs, sugar, sodium, caffeine, note
     FROM food_logs ORDER BY date, created_at`
  );
}

function toCsv(rows: ExportRow[]): string {
  const header = "日期,餐次,食物名称,数量,单位,热量(kcal),蛋白质(g),脂肪(g),碳水(g),糖(g),钠(mg),咖啡因(mg),备注";
  const lines = rows.map((r) =>
    [
      r.date,
      MEAL_LABELS[r.meal_type] ?? r.meal_type,
      `"${(r.custom_name ?? "").replace(/"/g, '""')}"`,
      r.amount,
      r.unit,
      Math.round(r.kcal),
      Math.round(r.protein * 10) / 10,
      Math.round(r.fat * 10) / 10,
      Math.round(r.carbs * 10) / 10,
      Math.round(r.sugar * 10) / 10,
      Math.round(r.sodium),
      Math.round(r.caffeine),
      `"${(r.note ?? "").replace(/"/g, '""')}"`,
    ].join(",")
  );
  return [header, ...lines].join("\n");
}

function toJson(rows: ExportRow[]): string {
  const data = rows.map((r) => ({
    date: r.date,
    mealType: MEAL_LABELS[r.meal_type] ?? r.meal_type,
    name: r.custom_name,
    amount: r.amount,
    unit: r.unit,
    kcal: Math.round(r.kcal),
    protein: Math.round(r.protein * 10) / 10,
    fat: Math.round(r.fat * 10) / 10,
    carbs: Math.round(r.carbs * 10) / 10,
    sugar: Math.round(r.sugar * 10) / 10,
    sodium: Math.round(r.sodium),
    caffeine: Math.round(r.caffeine),
    note: r.note ?? null,
  }));
  return JSON.stringify(data, null, 2);
}

export async function exportData(format: "csv" | "json"): Promise<void> {
  const rows = await fetchAllLogs();

  if (rows.length === 0) {
    throw new Error("NO_DATA");
  }

  const content = format === "csv" ? toCsv(rows) : toJson(rows);
  const ext = format === "csv" ? "csv" : "json";
  const filename = `diet-export-${new Date().toISOString().slice(0, 10)}.${ext}`;
  const file = new File(Paths.cache, filename);

  await file.write(content);

  const canShare = await Sharing.isAvailableAsync();
  if (!canShare) {
    throw new Error("NO_SHARE");
  }

  await Sharing.shareAsync(file.uri, {
    mimeType: format === "csv" ? "text/csv" : "application/json",
    dialogTitle: "导出饮食记录",
  });
}
