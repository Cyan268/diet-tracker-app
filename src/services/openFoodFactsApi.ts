import type { ExternalFoodResult } from "@/types/external";

const API_BASE = "https://world.openfoodfacts.org/cgi/search.pl";

interface OffProduct {
  product_name?: string;
  brands?: string;
  categories?: string;
  code?: string;
  nutriments?: {
    "energy-kcal_100g"?: number;
    proteins_100g?: number;
    fat_100g?: number;
    carbohydrates_100g?: number;
    sugars_100g?: number;
    sodium_100g?: number;
    caffeine_100g?: number;
  };
}

interface OffResponse {
  products: OffProduct[];
  count?: number;
}

function mapProduct(product: OffProduct): ExternalFoodResult | null {
  const name = product.product_name?.trim();
  if (!name) return null;

  const n = product.nutriments;
  if (!n) return null;

  const kcal = n["energy-kcal_100g"];
  if (kcal === undefined || kcal === null) return null;

  return {
    name,
    brand: product.brands?.split(",")[0]?.trim() || undefined,
    category: product.categories?.split(",")[0]?.trim() || undefined,
    kcalPer100g: kcal,
    proteinPer100g: n.proteins_100g ?? 0,
    fatPer100g: n.fat_100g ?? 0,
    carbsPer100g: n.carbohydrates_100g ?? 0,
    sugarPer100g: n.sugars_100g ?? 0,
    sodiumPer100g: (n.sodium_100g ?? 0) * 1000, // API returns g, we store mg
    caffeinePer100g: n.caffeine_100g ?? 0,
    source: "openfoodfacts",
    externalId: product.code || undefined,
  };
}

export async function searchOpenFoodFacts(
  query: string,
  pageSize: number = 8
): Promise<ExternalFoodResult[]> {
  try {
    const params = new URLSearchParams({
      search_terms: query,
      search_simple: "1",
      action: "process",
      json: "1",
      page_size: String(pageSize),
      fields: "product_name,brands,categories,code,nutriments",
    });

    const response = await fetch(`${API_BASE}?${params.toString()}`, {
      headers: { "User-Agent": "DietTrackerApp/1.0" },
    });

    if (!response.ok) return [];

    const data: OffResponse = await response.json();
    if (!data.products) return [];

    return data.products
      .map(mapProduct)
      .filter((r): r is ExternalFoodResult => r !== null);
  } catch {
    return [];
  }
}
