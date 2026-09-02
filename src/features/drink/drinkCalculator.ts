import type { DrinkOption, DrinkCalculation } from "@/types/drink";

export function calcDrink(base: DrinkOption, options: DrinkOption[]): DrinkCalculation {
  let kcal = base.kcalDelta;
  let sugar = base.sugarDelta;
  let caffeine = base.caffeineDelta;

  for (const opt of options) {
    kcal += opt.kcalDelta ?? 0;
    sugar += opt.sugarDelta ?? 0;
    caffeine += opt.caffeineDelta ?? 0;
  }

  return { kcal, sugar, caffeine };
}
