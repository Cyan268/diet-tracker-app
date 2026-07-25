export type CatalogMilkMode = "none" | "fixed" | "choice";

export interface CatalogDrink {
  brand: string;
  drinkName: string;
  kcal: number;
  sugar: number;
  caffeine: number;
  milkMode: CatalogMilkMode;
}

export interface CatalogSeedOption {
  brand: string;
  drinkName: string;
  optionType: "size" | "sugar" | "milk";
  optionName: string;
  kcalDelta: number;
  sugarDelta: number;
  caffeineDelta: number;
}

/**
 * 现制饮品会随地区、杯型、冷热和配方调整。这里保存的是用于记录的标准杯估算值，
 * 不是品牌官方营养数据库。品牌代表产品参考官网公开菜单，数值在 UI 中始终标注“估算”。
 */
export const DRINK_CATALOG_VERSION = "2026-07-17";

const drink = (
  brand: string,
  drinkName: string,
  kcal: number,
  sugar: number,
  caffeine: number,
  milkMode: CatalogMilkMode
): CatalogDrink => ({ brand, drinkName, kcal, sugar, caffeine, milkMode });

export const DRINK_CATALOG: readonly CatalogDrink[] = [
  // 茶饮品牌
  drink("蜜雪冰城", "冰鲜柠檬水", 150, 31, 0, "none"),
  drink("蜜雪冰城", "棒打鲜橙", 210, 38, 0, "none"),
  drink("蜜雪冰城", "满杯百香果", 230, 42, 25, "none"),
  drink("蜜雪冰城", "茉莉奶绿", 310, 32, 70, "fixed"),
  drink("蜜雪冰城", "珍珠奶茶", 360, 38, 75, "fixed"),
  drink("蜜雪冰城", "草莓摇摇奶昔", 330, 45, 0, "fixed"),
  drink("蜜雪冰城", "雪王雪顶咖啡", 260, 28, 120, "fixed"),

  drink("古茗", "超A芝士葡萄", 390, 52, 35, "fixed"),
  drink("古茗", "超A芝士桃桃", 350, 49, 30, "fixed"),
  drink("古茗", "古茗奶茶", 330, 35, 75, "fixed"),
  drink("古茗", "云岭茉莉白", 230, 22, 95, "fixed"),
  drink("古茗", "杨枝甘露轻盈版", 310, 42, 0, "fixed"),
  drink("古茗", "大橘美式", 120, 23, 145, "none"),
  drink("古茗", "鲜奶拿铁", 190, 12, 130, "choice"),

  drink("1点点", "四季奶青", 320, 34, 80, "fixed"),
  drink("1点点", "波霸奶茶", 390, 42, 80, "fixed"),
  drink("1点点", "四季春珍波椰", 410, 45, 90, "fixed"),
  drink("1点点", "红茶玛奇朵", 300, 32, 95, "fixed"),
  drink("1点点", "冰淇淋红茶", 270, 31, 90, "fixed"),
  drink("1点点", "柠檬养乐多", 210, 38, 0, "none"),

  drink("霸王茶姬", "伯牙绝弦", 240, 21, 110, "fixed"),
  drink("霸王茶姬", "桂馥兰香", 250, 22, 105, "fixed"),
  drink("霸王茶姬", "花田乌龙", 245, 23, 100, "fixed"),
  drink("霸王茶姬", "青沫观音", 235, 20, 115, "fixed"),
  drink("霸王茶姬", "寻香山茶", 245, 22, 105, "fixed"),
  drink("霸王茶姬", "去云南·玫瑰普洱", 260, 24, 100, "fixed"),

  drink("茉莉奶白", "一朵茉莉花", 230, 21, 95, "fixed"),
  drink("茉莉奶白", "茉莉奶白", 250, 23, 95, "fixed"),
  drink("茉莉奶白", "茉莉奶白冰茶", 270, 29, 70, "fixed"),
  drink("茉莉奶白", "白兰轻乳茶", 240, 22, 95, "fixed"),
  drink("茉莉奶白", "栀子奶白", 245, 22, 90, "fixed"),

  drink("喜茶", "多肉葡萄", 380, 50, 35, "fixed"),
  drink("喜茶", "多肉桃李", 330, 45, 30, "fixed"),
  drink("喜茶", "芒芒甘露", 360, 49, 20, "fixed"),
  drink("喜茶", "烤黑糖波波真乳茶", 420, 45, 80, "fixed"),
  drink("喜茶", "绿妍轻柠茶", 170, 31, 60, "none"),
  drink("喜茶", "羽衣纤体瓶", 150, 24, 20, "none"),

  drink("茶百道", "杨枝甘露", 360, 48, 10, "fixed"),
  drink("茶百道", "豆乳玉麒麟", 410, 42, 80, "fixed"),
  drink("茶百道", "招牌芋圆奶茶", 430, 44, 75, "fixed"),
  drink("茶百道", "茉莉奶绿", 300, 31, 75, "fixed"),
  drink("茶百道", "西瓜啵啵", 240, 41, 20, "none"),
  drink("茶百道", "超级杯水果茶", 300, 52, 35, "none"),

  drink("奈雪的茶", "霸气橙子", 250, 43, 35, "none"),
  drink("奈雪的茶", "霸气葡萄", 380, 50, 35, "fixed"),
  drink("奈雪的茶", "霸气玉油柑", 180, 32, 30, "none"),
  drink("奈雪的茶", "瘦瘦小绿瓶", 150, 24, 10, "none"),
  drink("奈雪的茶", "超能牛油果酸奶昔", 360, 32, 0, "fixed"),

  drink("沪上阿姨", "血糯米奶茶", 430, 40, 70, "fixed"),
  drink("沪上阿姨", "厚芋泥波波奶茶", 450, 43, 75, "fixed"),
  drink("沪上阿姨", "杨枝甘露", 350, 47, 5, "fixed"),
  drink("沪上阿姨", "浅浅清茉", 230, 22, 90, "fixed"),
  drink("沪上阿姨", "鲜果茶", 240, 42, 25, "none"),

  drink("书亦烧仙草", "书亦烧仙草", 460, 43, 70, "fixed"),
  drink("书亦烧仙草", "芋泥全家福", 480, 45, 75, "fixed"),
  drink("书亦烧仙草", "杨枝甘露", 350, 47, 5, "fixed"),
  drink("书亦烧仙草", "葡萄芋圆冻冻", 330, 50, 25, "none"),
  drink("书亦烧仙草", "茉莉轻乳茶", 230, 22, 90, "fixed"),

  drink("CoCo都可", "鲜百香双响炮", 410, 53, 35, "none"),
  drink("CoCo都可", "奶茶三兄弟", 480, 48, 80, "fixed"),
  drink("CoCo都可", "珍珠奶茶", 390, 41, 75, "fixed"),
  drink("CoCo都可", "生椰杨枝甘露", 360, 47, 5, "fixed"),
  drink("CoCo都可", "四季春青茶", 100, 18, 70, "none"),

  drink("益禾堂", "烤奶", 360, 38, 75, "fixed"),
  drink("益禾堂", "益杯烧仙草", 450, 44, 70, "fixed"),
  drink("益禾堂", "泷珠奶茶", 410, 43, 75, "fixed"),
  drink("益禾堂", "芒果啵啵", 300, 47, 20, "none"),
  drink("益禾堂", "手作芋圆奶茶", 430, 42, 75, "fixed"),

  drink("茶颜悦色", "幽兰拿铁", 330, 31, 90, "fixed"),
  drink("茶颜悦色", "声声乌龙", 290, 28, 95, "fixed"),
  drink("茶颜悦色", "筝筝纸鸢", 300, 29, 90, "fixed"),
  drink("茶颜悦色", "桂花弄", 280, 27, 90, "fixed"),
  drink("茶颜悦色", "蔓越阑珊", 310, 36, 70, "fixed"),

  drink("乐乐茶", "脏脏茶", 460, 45, 80, "fixed"),
  drink("乐乐茶", "葡萄酪酪", 390, 51, 35, "fixed"),
  drink("乐乐茶", "杨枝甘露", 360, 48, 5, "fixed"),
  drink("乐乐茶", "草莓酪酪", 370, 46, 25, "fixed"),
  drink("乐乐茶", "茉莉轻乳茶", 235, 22, 90, "fixed"),

  drink("甜啦啦", "一桶水果茶", 320, 55, 35, "none"),
  drink("甜啦啦", "杨枝甘露", 350, 48, 5, "fixed"),
  drink("甜啦啦", "黑糖珍珠奶茶", 420, 44, 75, "fixed"),
  drink("甜啦啦", "芋泥波波奶茶", 440, 43, 75, "fixed"),
  drink("甜啦啦", "冰鲜柠檬水", 150, 31, 0, "none"),

  // 咖啡品牌
  drink("瑞幸咖啡", "生椰拿铁", 179, 12, 118, "fixed"),
  drink("瑞幸咖啡", "茉莉花香拿铁", 85, 7, 236, "fixed"),
  drink("瑞幸咖啡", "轻椰茉莉拿铁", 120, 9, 179, "fixed"),
  drink("瑞幸咖啡", "丝绒拿铁", 376, 25, 130, "fixed"),
  drink("瑞幸咖啡", "拿铁", 268, 13, 99, "choice"),
  drink("瑞幸咖啡", "标准美式", 15, 0, 180, "none"),
  drink("瑞幸咖啡", "橙C美式", 120, 22, 160, "none"),

  drink("Manner Coffee", "美式", 15, 0, 170, "none"),
  drink("Manner Coffee", "拿铁", 190, 11, 140, "choice"),
  drink("Manner Coffee", "燕麦拿铁", 210, 10, 140, "fixed"),
  drink("Manner Coffee", "澳白", 160, 9, 150, "choice"),
  drink("Manner Coffee", "Dirty", 180, 10, 130, "fixed"),

  drink("M Stand", "美式", 15, 0, 170, "none"),
  drink("M Stand", "拿铁", 200, 12, 145, "choice"),
  drink("M Stand", "澳白", 170, 10, 150, "choice"),
  drink("M Stand", "椰青冰萃", 140, 22, 130, "none"),
  drink("M Stand", "黑糖碧根果拿铁", 330, 29, 140, "fixed"),

  drink("星巴克", "冷萃咖啡", 10, 0, 200, "none"),
  drink("星巴克", "馥芮白", 170, 10, 160, "choice"),
  drink("星巴克", "焦糖玛奇朵", 310, 34, 150, "fixed"),
  drink("星巴克", "摩卡", 350, 35, 150, "fixed"),
  drink("星巴克", "抹茶星冰乐", 390, 49, 70, "fixed"),

  drink("幸运咖", "冰美式", 15, 0, 170, "none"),
  drink("幸运咖", "拿铁", 190, 11, 130, "choice"),
  drink("幸运咖", "椰椰拿铁", 220, 17, 130, "fixed"),
  drink("幸运咖", "厚乳拿铁", 260, 19, 130, "fixed"),
  drink("幸运咖", "雪顶咖啡", 290, 31, 120, "fixed"),

  // 无奶基饮品集合，覆盖用户提到的混合果汁场景
  drink("鲜榨/混合果汁", "鲜榨橙汁", 180, 34, 0, "none"),
  drink("鲜榨/混合果汁", "西瓜汁", 150, 30, 0, "none"),
  drink("鲜榨/混合果汁", "芒果汁", 230, 42, 0, "none"),
  drink("鲜榨/混合果汁", "苹果胡萝卜汁", 190, 35, 0, "none"),
  drink("鲜榨/混合果汁", "莓果混合果汁", 210, 37, 0, "none"),
  drink("鲜榨/混合果汁", "羽衣甘蓝混合果蔬汁", 140, 22, 0, "none"),
];

export const BRAND_PRIORITY = [
  "通用",
  "蜜雪冰城",
  "古茗",
  "1点点",
  "霸王茶姬",
  "茉莉奶白",
  "喜茶",
  "茶百道",
  "奈雪的茶",
  "沪上阿姨",
  "书亦烧仙草",
  "CoCo都可",
  "益禾堂",
  "茶颜悦色",
  "乐乐茶",
  "甜啦啦",
  "瑞幸咖啡",
  "Manner Coffee",
  "M Stand",
  "幸运咖",
  "星巴克",
  "鲜榨/混合果汁",
] as const;

export function buildCatalogSeedOptions(): CatalogSeedOption[] {
  return DRINK_CATALOG.flatMap((item) => {
    const base: CatalogSeedOption = {
      brand: item.brand,
      drinkName: item.drinkName,
      optionType: "size",
      optionName: "标准杯（估算）",
      kcalDelta: item.kcal,
      sugarDelta: item.sugar,
      caffeineDelta: item.caffeine,
    };

    const estimatedAddedSugar = Math.round(item.sugar * 0.65);
    const sugarOptions: CatalogSeedOption[] =
      item.brand === "鲜榨/混合果汁"
        ? [
            {
              brand: item.brand,
              drinkName: item.drinkName,
              optionType: "sugar",
              optionName: "不另外加糖（保留水果天然糖）",
              kcalDelta: 0,
              sugarDelta: 0,
              caffeineDelta: 0,
            },
          ]
        : item.sugar === 0
          ? []
          : [
              {
                brand: item.brand,
                drinkName: item.drinkName,
                optionType: "sugar",
                optionName: "不另外加糖（估算）",
                kcalDelta: -estimatedAddedSugar * 4,
                sugarDelta: -estimatedAddedSugar,
                caffeineDelta: 0,
              },
              {
                brand: item.brand,
                drinkName: item.drinkName,
                optionType: "sugar",
                optionName: "半糖（估算差值）",
                kcalDelta: -Math.round(estimatedAddedSugar * 0.5) * 4,
                sugarDelta: -Math.round(estimatedAddedSugar * 0.5),
                caffeineDelta: 0,
              },
              {
                brand: item.brand,
                drinkName: item.drinkName,
                optionType: "sugar",
                optionName: "标准糖",
                kcalDelta: 0,
                sugarDelta: 0,
                caffeineDelta: 0,
              },
            ];

    const milkOptions: CatalogSeedOption[] =
      item.milkMode === "none"
        ? [
            {
              brand: item.brand,
              drinkName: item.drinkName,
              optionType: "milk",
              optionName: "无",
              kcalDelta: 0,
              sugarDelta: 0,
              caffeineDelta: 0,
            },
          ]
        : item.milkMode === "fixed"
          ? [
              {
                brand: item.brand,
                drinkName: item.drinkName,
                optionType: "milk",
                optionName: "按门店默认",
                kcalDelta: 0,
                sugarDelta: 0,
                caffeineDelta: 0,
              },
            ]
          : [
              {
                brand: item.brand,
                drinkName: item.drinkName,
                optionType: "milk",
                optionName: "按门店默认",
                kcalDelta: 0,
                sugarDelta: 0,
                caffeineDelta: 0,
              },
              {
                brand: item.brand,
                drinkName: item.drinkName,
                optionType: "milk",
                optionName: "换燕麦奶（估算差值）",
                kcalDelta: 20,
                sugarDelta: 1,
                caffeineDelta: 0,
              },
              {
                brand: item.brand,
                drinkName: item.drinkName,
                optionType: "milk",
                optionName: "换椰奶（估算差值）",
                kcalDelta: 30,
                sugarDelta: 2,
                caffeineDelta: 0,
              },
            ];

    return [base, ...sugarOptions, ...milkOptions];
  });
}
