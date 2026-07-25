import { amountToGrams, resolveFoodEntity } from "@/features/ai/foodTextAnalysis";
import type { FoodItem } from "@/types/nutrition";

const rice: FoodItem = {
  id: "rice",
  name: "白米饭",
  category: "主食",
  servingUnit: "碗",
  servingWeightG: 200,
  kcalPer100g: 116,
  proteinPer100g: 2.6,
  fatPer100g: 0.3,
  carbsPer100g: 25.6,
  sugarPer100g: 0,
  sodiumPer100g: 2,
  caffeinePer100g: 0,
  source: "seed",
  createdAt: "2026-07-17T00:00:00Z",
  updatedAt: "2026-07-17T00:00:00Z",
  kcal: 0,
  protein: 0,
  fat: 0,
  carbs: 0,
  sugar: 0,
  sodium: 0,
  caffeine: 0,
};

const entity = {
  raw_name: "米饭",
  normalized_name: "白米饭",
  amount: 1,
  unit: "碗",
  meal_type: "lunch" as const,
  confidence: 0.94,
  needs_review: false,
  evidence: "识别到名称和数量",
};

describe("AI food entity resolution", () => {
  it("converts a catalog serving into grams", () => {
    expect(amountToGrams(rice, 1.5, "碗")).toBe(300);
    expect(amountToGrams(rice, 125, "g")).toBe(125);
  });

  it("calculates nutrition only after matching the local catalog", () => {
    const result = resolveFoodEntity(entity, [rice]);

    expect(result.food?.id).toBe("rice");
    expect(result.grams).toBe(200);
    expect(result.nutrition?.kcal).toBe(232);
    expect(result.issue).toBeNull();
  });

  it("keeps unknown entities unresolved instead of inventing nutrition", () => {
    const result = resolveFoodEntity({ ...entity, normalized_name: "未知食物" }, [rice]);

    expect(result.food).toBeNull();
    expect(result.nutrition).toBeNull();
    expect(result.issue).toContain("没有匹配项");
  });
});
