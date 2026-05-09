export type MealType = "breakfast" | "lunch" | "dinner" | "snack" | "drink";

export interface FoodLog {
  id: string;
  date: string;
  mealType: MealType;
  foodItemId?: string;
  customName?: string;
  amount: number;
  unit: string;
  kcal: number;
  protein: number;
  fat: number;
  carbs: number;
  sugar: number;
  sodium: number;
  caffeine: number;
  note?: string;
  createdAt: string;
  updatedAt: string;
}

export interface DailySummary {
  date: string;
  totalKcal: number;
  totalProtein: number;
  totalFat: number;
  totalCarbs: number;
  totalSugar: number;
  totalSodium: number;
  totalCaffeine: number;
  mealBreakdown: {
    breakfast: number;
    lunch: number;
    dinner: number;
    snack: number;
    drink: number;
  };
}
