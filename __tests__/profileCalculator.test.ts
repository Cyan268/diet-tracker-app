import { calcDailyTargets, calcProfileMetrics } from "@/features/profile/profileCalculator";
import type { UserProfile } from "@/types/profile";

function buildProfile(overrides: Partial<UserProfile> = {}): UserProfile {
  return {
    id: "profile-1",
    gender: "male",
    age: 25,
    heightCm: 175,
    weightKg: 70,
    activityLevel: "moderate",
    goal: "maintain",
    createdAt: "2026-07-15T00:00:00.000Z",
    updatedAt: "2026-07-15T00:00:00.000Z",
    ...overrides,
  };
}

describe("calcDailyTargets", () => {
  it("根据 Mifflin-St Jeor 公式、活动系数和宏量比例计算每日目标", () => {
    expect(calcDailyTargets(buildProfile())).toEqual({
      kcal: 2594,
      protein: 112,
      fat: 72,
      carbs: 375,
      sugar: 50,
      sodium: 2300,
      caffeine: 400,
    });
  });

  it("减脂目标会在 TDEE 基础上减少 500 kcal", () => {
    const maintain = calcDailyTargets(buildProfile({ goal: "maintain" }));
    const lose = calcDailyTargets(buildProfile({ goal: "lose" }));

    expect(maintain.kcal - lose.kcal).toBe(500);
  });

  it("不会返回负数碳水目标", () => {
    const targets = calcDailyTargets(
      buildProfile({
        gender: "female",
        age: 120,
        heightCm: 100,
        weightKg: 200,
        activityLevel: "sedentary",
        goal: "lose",
      })
    );

    expect(targets.carbs).toBeGreaterThanOrEqual(0);
  });

  it("同时返回可解释的 BMR、TDEE 和 BMI", () => {
    const metrics = calcProfileMetrics(buildProfile());

    expect(metrics).toMatchObject({
      bmr: 1674,
      tdee: 2594,
      bmi: 22.9,
      targets: calcDailyTargets(buildProfile()),
    });
  });
});
