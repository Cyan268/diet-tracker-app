import type { UserProfile, DailyTargets } from "@/types/profile";

const ACTIVITY_MULTIPLIERS = {
  sedentary: 1.2,
  light: 1.375,
  moderate: 1.55,
  active: 1.725,
  very_active: 1.9,
} as const;

const GOAL_ADJUSTMENTS = {
  lose: -500,
  maintain: 0,
  gain: 300,
} as const;

export interface ProfileMetrics {
  bmr: number;
  tdee: number;
  bmi: number;
  targets: DailyTargets;
}

export function calcBMR(profile: UserProfile): number {
  const base = 10 * profile.weightKg + 6.25 * profile.heightCm - 5 * profile.age;
  return profile.gender === "male" ? base + 5 : base - 161;
}

export function calcDailyTargets(profile: UserProfile): DailyTargets {
  const bmr = calcBMR(profile);
  const multiplier = ACTIVITY_MULTIPLIERS[profile.activityLevel] ?? 1.55;
  const tdee = bmr * multiplier;
  const adjustment = GOAL_ADJUSTMENTS[profile.goal] ?? 0;
  const kcal = Math.round(tdee + adjustment);

  const protein = Math.round(profile.weightKg * 1.6);
  const fat = Math.round((kcal * 0.25) / 9);
  const carbs = Math.round((kcal - protein * 4 - fat * 9) / 4);

  return {
    kcal,
    protein,
    fat,
    carbs: Math.max(carbs, 0),
    sugar: 50,
    sodium: 2300,
    caffeine: 400,
  };
}

export function calcProfileMetrics(profile: UserProfile): ProfileMetrics {
  const bmr = calcBMR(profile);
  const multiplier = ACTIVITY_MULTIPLIERS[profile.activityLevel] ?? 1.55;
  const heightM = profile.heightCm / 100;

  return {
    bmr: Math.round(bmr),
    tdee: Math.round(bmr * multiplier),
    bmi: Math.round((profile.weightKg / heightM ** 2) * 10) / 10,
    targets: calcDailyTargets(profile),
  };
}
