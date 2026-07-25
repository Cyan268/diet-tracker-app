import type { DrinkOption } from "@/types/drink";
import type { MealType } from "@/types/log";
import type { ActivityLevel, Gender, Goal } from "@/types/profile";
import type { ReminderRule } from "@/types/reminder";

export interface FoodItemRow {
  id: string;
  name: string;
  brand: string | null;
  category: string | null;
  serving_unit: string | null;
  serving_weight_g: number | null;
  kcal_per_100g: number;
  protein_per_100g: number;
  fat_per_100g: number;
  carbs_per_100g: number;
  sugar_per_100g: number;
  sodium_per_100g: number;
  caffeine_per_100g: number;
  source: string | null;
  created_at: string;
  updated_at: string;
}

export interface FoodLogRow {
  id: string;
  date: string;
  meal_type: MealType;
  food_item_id: string | null;
  custom_name: string | null;
  amount: number;
  unit: string;
  kcal: number;
  protein: number;
  fat: number;
  carbs: number;
  sugar: number;
  sodium: number;
  caffeine: number;
  note: string | null;
  created_at: string;
  updated_at: string;
  server_id: string | null;
  server_version: number | null;
  sync_status: "pending" | "synced" | "failed";
  last_sync_error: string | null;
  owner_user_id: string | null;
}

export interface OutboxEventRow {
  id: string;
  owner_user_id: string | null;
  aggregate_type: "food_log";
  aggregate_id: string;
  operation: "create" | "update" | "delete";
  payload: string;
  status: "pending" | "processing" | "failed" | "blocked";
  attempt_count: number;
  next_attempt_at: string;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface SyncConflictRow {
  id: string;
  owner_user_id: string;
  aggregate_id: string;
  remote_operation: "upsert" | "delete";
  remote_cursor: number;
  remote_payload: string;
  created_at: string;
  updated_at: string;
}

export interface UserProfileRow {
  id: string;
  gender: Gender;
  age: number;
  height_cm: number;
  weight_kg: number;
  activity_level: ActivityLevel;
  goal: Goal;
  created_at: string;
  updated_at: string;
  owner_user_id: string | null;
}

export interface DrinkOptionRow {
  id: string;
  brand: string;
  drink_name: string;
  option_type: DrinkOption["optionType"];
  option_name: string;
  kcal_delta: number;
  sugar_delta: number;
  caffeine_delta: number;
}

export interface ReminderRuleRow {
  id: string;
  metric: string;
  rule_type: ReminderRule["ruleType"];
  threshold_type: ReminderRule["thresholdType"];
  threshold_value: number;
  enabled: number;
}

export interface NutritionTotalsRow {
  total_kcal: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  total_sugar: number;
  total_sodium: number;
  total_caffeine: number;
}

export interface DailySummaryRow extends NutritionTotalsRow {
  date: string;
}

export interface MealBreakdownRow {
  meal_type: MealType;
  total: number;
}
