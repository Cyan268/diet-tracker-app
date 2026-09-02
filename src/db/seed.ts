import type { SQLiteDatabase } from "expo-sqlite";
import { v4 as uuidv4 } from "uuid";
import seedFoodsData from "../../assets/seed/seed-foods.json";
import seedDrinksData from "../../assets/seed/seed-drinks.json";
import { buildCatalogSeedOptions } from "../data/drinkCatalog";

interface SeedFood {
  name: string;
  brand?: string;
  category: string;
  servingUnit?: string;
  servingWeightG?: number;
  kcalPer100g: number;
  proteinPer100g: number;
  fatPer100g: number;
  carbsPer100g: number;
  sugarPer100g?: number;
  sodiumPer100g?: number;
  caffeinePer100g?: number;
}

interface SeedDrink {
  brand: string;
  drinkName: string;
  optionType: string;
  optionName: string;
  kcalDelta?: number;
  sugarDelta?: number;
  caffeineDelta?: number;
}

const seedFoods: readonly SeedFood[] = seedFoodsData;
const seedDrinks: readonly SeedDrink[] = [...seedDrinksData, ...buildCatalogSeedOptions()];

export async function seedDatabase(db: SQLiteDatabase): Promise<void> {
  const now = new Date().toISOString();

  const defaultRules = [
    { metric: "kcal", ruleType: "too_high", thresholdType: "ratio_of_target", threshold: 1.1 },
    { metric: "protein", ruleType: "too_low", thresholdType: "ratio_of_target", threshold: 0.6 },
    { metric: "sugar", ruleType: "too_high", thresholdType: "fixed", threshold: 50 },
    { metric: "sodium", ruleType: "too_high", thresholdType: "fixed", threshold: 2300 },
    { metric: "caffeine", ruleType: "too_high", thresholdType: "fixed", threshold: 400 },
  ];

  await db.execAsync("BEGIN TRANSACTION;");
  try {
    for (const food of seedFoods) {
      const existingFood = await db.getFirstAsync<{ id: string }>(
        "SELECT id FROM food_items WHERE source = ? AND name = ? LIMIT 1",
        "builtin",
        food.name
      );
      if (existingFood) continue;

      await db.runAsync(
        `INSERT INTO food_items (id, name, brand, category, serving_unit, serving_weight_g, kcal_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, sugar_per_100g, sodium_per_100g, caffeine_per_100g, source, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        uuidv4(),
        food.name,
        food.brand ?? null,
        food.category,
        food.servingUnit ?? null,
        food.servingWeightG ?? null,
        food.kcalPer100g,
        food.proteinPer100g,
        food.fatPer100g,
        food.carbsPer100g,
        food.sugarPer100g ?? 0,
        food.sodiumPer100g ?? 0,
        food.caffeinePer100g ?? 0,
        "builtin",
        now,
        now
      );
    }

    for (const drink of seedDrinks) {
      const existingDrink = await db.getFirstAsync<{ id: string }>(
        `SELECT id FROM drink_options
         WHERE brand = ? AND drink_name = ? AND option_type = ? AND option_name = ?
         LIMIT 1`,
        drink.brand,
        drink.drinkName,
        drink.optionType,
        drink.optionName
      );
      if (existingDrink) continue;

      await db.runAsync(
        `INSERT INTO drink_options (id, brand, drink_name, option_type, option_name, kcal_delta, sugar_delta, caffeine_delta)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        uuidv4(),
        drink.brand,
        drink.drinkName,
        drink.optionType,
        drink.optionName,
        drink.kcalDelta ?? 0,
        drink.sugarDelta ?? 0,
        drink.caffeineDelta ?? 0
      );
    }

    for (const rule of defaultRules) {
      const existingRule = await db.getFirstAsync<{ id: string }>(
        "SELECT id FROM reminder_rules WHERE metric = ? AND rule_type = ? LIMIT 1",
        rule.metric,
        rule.ruleType
      );
      if (existingRule) continue;

      await db.runAsync(
        `INSERT INTO reminder_rules (id, metric, rule_type, threshold_type, threshold_value, enabled)
         VALUES (?, ?, ?, ?, ?, 1)`,
        uuidv4(),
        rule.metric,
        rule.ruleType,
        rule.thresholdType,
        rule.threshold
      );
    }

    await db.execAsync("COMMIT;");
  } catch (e) {
    await db.execAsync("ROLLBACK;");
    throw e;
  }
}
