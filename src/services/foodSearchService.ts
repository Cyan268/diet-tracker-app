import { searchFoods } from "@/db/repositories/foodRepository";
import { searchOpenFoodFacts } from "./openFoodFactsApi";
import type { FoodItem } from "@/types/nutrition";
import type { ExternalFoodResult } from "@/types/external";

export interface SearchResults {
  local: FoodItem[];
  external: ExternalFoodResult[];
}

export async function searchAllFoods(keyword: string): Promise<SearchResults> {
  const trimmed = keyword.trim();
  if (!trimmed) return { local: [], external: [] };

  const [local, external] = await Promise.all([
    searchFoods(trimmed),
    searchOpenFoodFacts(trimmed).catch(() => []),
  ]);

  return { local, external };
}
