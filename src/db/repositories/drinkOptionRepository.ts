import { getDatabase } from "../database";
import type { DrinkOptionRow } from "../rows";
import type { DrinkOption } from "@/types/drink";
import { BRAND_PRIORITY } from "@/data/drinkCatalog";

const OPTION_PRIORITY: Record<string, readonly string[]> = {
  sugar: [
    "无糖",
    "不另外加糖（估算）",
    "不另外加糖（保留水果天然糖）",
    "少糖",
    "三分糖",
    "半糖",
    "半糖（估算差值）",
    "五分糖",
    "七分糖",
    "标准糖",
  ],
  milk: ["无", "按门店默认", "全脂牛奶", "脱脂牛奶", "燕麦奶", "椰奶"],
  topping: [
    "珍珠",
    "小珍珠",
    "脆啵啵",
    "椰果",
    "布丁",
    "仙草",
    "芋圆",
    "马蹄",
    "西米",
    "红豆",
    "芋泥",
    "茶冻",
    "桂花冻",
    "寒天晶球",
    "麻薯",
    "奶盖",
  ],
};

function rowToDrinkOption(row: DrinkOptionRow): DrinkOption {
  return {
    id: row.id,
    brand: row.brand,
    drinkName: row.drink_name,
    optionType: row.option_type,
    optionName: row.option_name,
    kcalDelta: row.kcal_delta,
    sugarDelta: row.sugar_delta,
    caffeineDelta: row.caffeine_delta,
  };
}

export async function getBrands(): Promise<string[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<{ brand: string }>(
    "SELECT DISTINCT brand FROM drink_options ORDER BY brand"
  );
  const priority = new Map<string, number>(BRAND_PRIORITY.map((brand, index) => [brand, index]));
  return rows
    .map((r) => r.brand)
    .sort(
      (a, b) =>
        (priority.get(a) ?? Number.MAX_SAFE_INTEGER) -
          (priority.get(b) ?? Number.MAX_SAFE_INTEGER) || a.localeCompare(b, "zh-CN")
    );
}

export async function getDrinkNames(brand: string): Promise<string[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<{ drink_name: string }>(
    "SELECT DISTINCT drink_name FROM drink_options WHERE brand = ? AND drink_name <> '*' ORDER BY drink_name",
    brand
  );
  return rows.map((r) => r.drink_name);
}

export async function getOptions(
  brand: string,
  drinkName: string,
  optionType: string
): Promise<DrinkOption[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<DrinkOptionRow>(
    `SELECT * FROM drink_options
     WHERE (brand = ? AND drink_name = ? AND option_type = ?)
        OR (brand = ? AND drink_name = '*' AND option_type = ?)
     ORDER BY id`,
    brand,
    drinkName,
    optionType,
    brand,
    optionType
  );
  return rows.map(rowToDrinkOption);
}

export async function getOptionsWithFallback(
  brand: string,
  drinkName: string,
  optionType: string
): Promise<DrinkOption[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<DrinkOptionRow>(
    `SELECT * FROM drink_options
     WHERE option_type = ?
       AND (
         (brand = ? AND (drink_name = ? OR drink_name = '*'))
         OR (brand = '通用' AND (drink_name = '*' OR drink_name = ?))
       )
     ORDER BY
       CASE WHEN brand = ? THEN 0 WHEN brand = '通用' THEN 1 ELSE 2 END,
       CASE WHEN drink_name = ? THEN 0 WHEN drink_name = '*' THEN 1 ELSE 2 END,
       id`,
    optionType,
    brand,
    drinkName,
    drinkName,
    brand,
    drinkName
  );
  return resolveDrinkOptions(rows.map(rowToDrinkOption), brand, drinkName, optionType);
}

export function resolveDrinkOptions(
  options: DrinkOption[],
  brand: string,
  drinkName: string,
  optionType: string
): DrinkOption[] {
  const exactOptions = options.filter(
    (option) => option.brand === brand && option.drinkName === drinkName
  );

  // 糖度和奶基是互斥配置。单品声明了自己的规则后，不能再混入通用选项。
  const exactOverridesFallback = ["sugar", "milk"].includes(optionType);
  const candidates = exactOverridesFallback && exactOptions.length > 0 ? exactOptions : options;
  const uniqueByName = new Map<string, DrinkOption>();
  for (const option of candidates) {
    if (!uniqueByName.has(option.optionName)) uniqueByName.set(option.optionName, option);
  }

  const names = OPTION_PRIORITY[optionType] ?? [];
  const priority = new Map(names.map((name, index) => [name, index]));
  return [...uniqueByName.values()].sort(
    (a, b) =>
      (priority.get(a.optionName) ?? Number.MAX_SAFE_INTEGER) -
        (priority.get(b.optionName) ?? Number.MAX_SAFE_INTEGER) ||
      a.optionName.localeCompare(b.optionName, "zh-CN")
  );
}
