import { buildCatalogSeedOptions, DRINK_CATALOG } from "@/data/drinkCatalog";
import { resolveDrinkOptions } from "@/db/repositories/drinkOptionRepository";
import type { DrinkOption } from "@/types/drink";

function option(overrides: Partial<DrinkOption>): DrinkOption {
  return {
    id: Math.random().toString(),
    brand: "通用",
    drinkName: "*",
    optionType: "milk",
    optionName: "全脂牛奶",
    kcalDelta: 80,
    sugarDelta: 5,
    caffeineDelta: 0,
    ...overrides,
  };
}

describe("drink catalog", () => {
  it("覆盖主流品牌并且每个品牌至少包含多款饮品", () => {
    const brandCounts = new Map<string, number>();
    for (const item of DRINK_CATALOG) {
      brandCounts.set(item.brand, (brandCounts.get(item.brand) ?? 0) + 1);
      expect(item.kcal).toBeGreaterThanOrEqual(0);
      expect(item.sugar).toBeGreaterThanOrEqual(0);
      expect(item.caffeine).toBeGreaterThanOrEqual(0);
    }

    expect(brandCounts.size).toBeGreaterThanOrEqual(20);
    expect([...brandCounts.values()].every((count) => count >= 5)).toBe(true);
  });

  it("为不加奶饮品生成明确的无奶基配置", () => {
    const seeds = buildCatalogSeedOptions();
    const americanoMilk = seeds.filter(
      (item) =>
        item.brand === "瑞幸咖啡" && item.drinkName === "标准美式" && item.optionType === "milk"
    );

    expect(americanoMilk).toHaveLength(1);
    expect(americanoMilk[0].optionName).toBe("无");
  });

  it("单品奶基规则覆盖通用奶基并去除重名选项", () => {
    const resolved = resolveDrinkOptions(
      [
        option({ id: "generic-milk" }),
        option({ id: "generic-none", optionName: "无", kcalDelta: 0, sugarDelta: 0 }),
        option({
          id: "exact-none",
          brand: "瑞幸咖啡",
          drinkName: "标准美式",
          optionName: "无",
          kcalDelta: 0,
          sugarDelta: 0,
        }),
      ],
      "瑞幸咖啡",
      "标准美式",
      "milk"
    );

    expect(resolved.map((item) => item.optionName)).toEqual(["无"]);
  });
});
