export interface DrinkOption {
  id: string;
  brand: string;
  drinkName: string;
  optionType: "size" | "sugar" | "milk" | "topping";
  optionName: string;
  kcalDelta: number;
  sugarDelta: number;
  caffeineDelta: number;
}

export interface DrinkSelection {
  brand: string;
  drinkName: string;
  size?: DrinkOption;
  sugar?: DrinkOption;
  milk?: DrinkOption;
  toppings: DrinkOption[];
}

export interface DrinkCalculation {
  kcal: number;
  sugar: number;
  caffeine: number;
}
