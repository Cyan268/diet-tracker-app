import { calcByGram } from "@/features/food/foodCalculator";
import type { FoodItem } from "@/types/nutrition";

const food: FoodItem = {
  id: "food-1",
  name: "测试食物",
  kcal: 0,
  protein: 0,
  fat: 0,
  carbs: 0,
  sugar: 0,
  sodium: 0,
  caffeine: 0,
  kcalPer100g: 200,
  proteinPer100g: 10,
  fatPer100g: 8,
  carbsPer100g: 20,
  sugarPer100g: 4,
  sodiumPer100g: 300,
  caffeinePer100g: 40,
  createdAt: "2026-07-15T00:00:00.000Z",
  updatedAt: "2026-07-15T00:00:00.000Z",
};

describe("calcByGram", () => {
  it("按克数等比例换算全部营养素", () => {
    expect(calcByGram(food, 50)).toEqual({
      kcal: 100,
      protein: 5,
      fat: 4,
      carbs: 10,
      sugar: 2,
      sodium: 150,
      caffeine: 20,
    });
  });

  it("零克食物的营养值均为零", () => {
    expect(calcByGram(food, 0)).toEqual({
      kcal: 0,
      protein: 0,
      fat: 0,
      carbs: 0,
      sugar: 0,
      sodium: 0,
      caffeine: 0,
    });
  });
});
