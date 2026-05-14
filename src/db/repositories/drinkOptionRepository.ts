import { getDatabase } from "../database";
import type { DrinkOption } from "@/types/drink";

function rowToDrinkOption(row: any): DrinkOption {
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
  return rows.map((r) => r.brand);
}

export async function getDrinkNames(brand: string): Promise<string[]> {
  const db = await getDatabase();
  const rows = await db.getAllAsync<{ drink_name: string }>(
    "SELECT DISTINCT drink_name FROM drink_options WHERE brand = ? ORDER BY drink_name",
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
  const rows = await db.getAllAsync<any>(
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
  const rows = await db.getAllAsync<any>(
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
  return rows.map(rowToDrinkOption);
}
