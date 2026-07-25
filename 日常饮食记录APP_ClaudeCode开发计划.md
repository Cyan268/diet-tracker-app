# 日常饮食记录 APP 开发计划（ClaudeCode 执行版）

## 0. 项目定位

做一个轻量级饮食记录 APP，用户可以记录三餐、零食、奶茶咖啡等饮品，并基于个人信息估算每日热量、宏量营养素、糖、钠、咖啡因等指标。当用户当天摄入某些指标超标或明显不足时，系统给出温和提醒。

开发策略：先做本地可运行 MVP，再接入外部食品/饮品数据源，最后做提醒、统计图表和体验优化。不要一开始就追求完整营养数据库。

---

## 1. 核心功能

### 1.1 三餐记录

- 早餐、午餐、晚餐分别记录。
- 支持食物名称、重量/份数、备注。
- 自动估算热量、蛋白质、脂肪、碳水、糖、钠等。
- 每餐生成小计，首页生成当天总计。

### 1.2 正餐外摄入记录

- 记录零食、夜宵、水果、甜点等。
- 统一归类为 `snack` 或 “加餐”。
- 参与当天总热量和营养素统计。

### 1.3 奶茶、咖啡、饮品记录

需要比普通食物更细，字段包括：

- 品牌
- 饮品名称
- 杯型
- 糖度
- 温度
- 奶基
- 小料
- 咖啡因估算
- 热量估算

计算方式：

```text
饮品总热量 = 基础饮品热量 + 杯型修正 + 糖度修正 + 奶基修正 + 小料修正
饮品咖啡因 = 基础饮品咖啡因 + 咖啡份数修正 + 茶基修正
```

### 1.4 用户资料与提醒

用户资料包括：

- 性别
- 年龄
- 身高
- 体重
- 活动水平
- 目标：减脂 / 维持 / 增肌

系统根据资料估算每日目标热量和营养素目标。当出现热量超标、糖/钠/咖啡因偏高、蛋白质明显不足时，在首页显示提醒。

---

## 2. 推荐技术栈

建议使用：

```text
React Native + Expo + TypeScript + SQLite
```

原因：

- Expo 适合快速做移动端原型。
- TypeScript 适合维护复杂数据结构。
- SQLite 适合本地饮食记录、统计和缓存。
- ClaudeCode 对 React Native / TypeScript 项目生成和修改比较友好。

推荐依赖：

```bash
npx create-expo-app diet-tracker-app --template
npm install zustand zod react-hook-form
npx expo install expo-sqlite
npm install react-native-chart-kit
```

---

## 3. 项目目录结构

```text
app/
  _layout.tsx
  (tabs)/
    index.tsx              # 今日总览
    add.tsx                # 添加记录入口
    stats.tsx              # 统计
    profile.tsx            # 我的/资料

src/
  components/
    MetricCard.tsx
    ReminderCard.tsx
    FoodLogItem.tsx

  db/
    database.ts
    schema.ts
    seed.ts
    repositories/
      foodRepository.ts
      logRepository.ts
      profileRepository.ts

  features/
    food/
      AddFoodScreen.tsx
      FoodSearchScreen.tsx
    drink/
      AddDrinkScreen.tsx
      drinkCalculator.ts
    summary/
      summaryService.ts
      reminderService.ts
    profile/
      profileCalculator.ts

  services/
    foodDataCentralApi.ts
    openFoodFactsApi.ts
    drinkSearchService.ts

  types/
    nutrition.ts
    log.ts
    profile.ts

  utils/
    date.ts
    number.ts

assets/
  seed-foods.json
  seed-drinks.json
```

---

## 4. 数据表设计

### 4.1 user_profile

保存用户身体信息和目标。

字段建议：

```sql
id TEXT PRIMARY KEY,
gender TEXT,
age INTEGER,
height_cm REAL,
weight_kg REAL,
activity_level TEXT,
goal TEXT,
created_at TEXT,
updated_at TEXT
```

### 4.2 food_items

保存基础食物和饮品数据库。

```sql
id TEXT PRIMARY KEY,
name TEXT NOT NULL,
brand TEXT,
category TEXT,
serving_unit TEXT,
serving_weight_g REAL,
kcal_per_100g REAL,
protein_per_100g REAL,
fat_per_100g REAL,
carbs_per_100g REAL,
sugar_per_100g REAL,
sodium_per_100g REAL,
caffeine_per_100g REAL,
source TEXT,
created_at TEXT,
updated_at TEXT
```

### 4.3 food_logs

保存每天实际记录。

```sql
id TEXT PRIMARY KEY,
date TEXT NOT NULL,
meal_type TEXT NOT NULL, -- breakfast/lunch/dinner/snack/drink
food_item_id TEXT,
custom_name TEXT,
amount REAL,
unit TEXT,
kcal REAL,
protein REAL,
fat REAL,
carbs REAL,
sugar REAL,
sodium REAL,
caffeine REAL,
note TEXT,
created_at TEXT,
updated_at TEXT
```

### 4.4 drink_options

保存饮品杯型、糖度、小料等修正项。

```sql
id TEXT PRIMARY KEY,
brand TEXT,
drink_name TEXT,
option_type TEXT, -- size/sugar/milk/topping
option_name TEXT,
kcal_delta REAL,
sugar_delta REAL,
caffeine_delta REAL
```

### 4.5 reminder_rules

保存提醒规则。

```sql
id TEXT PRIMARY KEY,
metric TEXT,
rule_type TEXT, -- too_high/too_low
threshold_type TEXT, -- fixed/ratio_of_target
threshold_value REAL,
enabled INTEGER
```

---

## 5. 页面设计

### 5.1 首页：今日总览

展示：

- 今日目标热量
- 当前摄入热量
- 蛋白质、脂肪、碳水进度
- 糖、钠、咖啡因卡片
- 今日提醒卡片
- 今天的饮食记录列表

### 5.2 添加页

入口分为：

- 添加早餐
- 添加午餐
- 添加晚餐
- 添加加餐
- 添加饮品

### 5.3 添加普通食物页

流程：

1. 选择餐次。
2. 搜索食物。
3. 输入重量或份数。
4. 展示估算热量和营养素。
5. 保存到当天记录。

### 5.4 添加饮品页

表单字段：

- 品牌
- 饮品名称
- 杯型
- 糖度
- 奶基
- 小料
- 备注

保存前展示：

- 预计热量
- 预计糖
- 预计咖啡因

### 5.5 统计页

展示：

- 今日总摄入
- 三餐热量占比
- 一周热量趋势
- 一周咖啡因趋势
- 饮品热量占比

### 5.6 我的页面

展示：

- 用户资料
- 目标设置
- 提醒规则设置
- 数据导出入口

---

## 6. 计算逻辑

### 6.1 普通食物折算

```ts
function calcByGram(nutritionPer100g, gram) {
  return {
    kcal: (nutritionPer100g.kcal * gram) / 100,
    protein: (nutritionPer100g.protein * gram) / 100,
    fat: (nutritionPer100g.fat * gram) / 100,
    carbs: (nutritionPer100g.carbs * gram) / 100,
    sugar: (nutritionPer100g.sugar * gram) / 100,
    sodium: (nutritionPer100g.sodium * gram) / 100,
    caffeine: (nutritionPer100g.caffeine * gram) / 100,
  };
}
```

### 6.2 饮品计算

```ts
function calcDrink(baseDrink, options) {
  const result = { ...baseDrink };

  for (const option of options) {
    result.kcal += option.kcal_delta ?? 0;
    result.sugar += option.sugar_delta ?? 0;
    result.caffeine += option.caffeine_delta ?? 0;
  }

  return result;
}
```

### 6.3 每日汇总

按 `date` 聚合所有 `food_logs`：

```sql
SELECT
  SUM(kcal) AS total_kcal,
  SUM(protein) AS total_protein,
  SUM(fat) AS total_fat,
  SUM(carbs) AS total_carbs,
  SUM(sugar) AS total_sugar,
  SUM(sodium) AS total_sodium,
  SUM(caffeine) AS total_caffeine
FROM food_logs
WHERE date = ?;
```

---

## 7. 提醒规则

MVP 阶段建议先做首页提醒，不做强推送。

示例规则：

| 指标   | 触发条件                 | 文案示例                                                   |
| ------ | ------------------------ | ---------------------------------------------------------- |
| 热量   | 今日摄入 > 目标热量 110% | 今日热量已超过目标，晚餐可适当减少高油高糖食物。           |
| 蛋白质 | 晚上时蛋白质 < 目标 60%  | 今天蛋白质摄入偏低，可以考虑补充鸡蛋、牛奶、豆制品或瘦肉。 |
| 糖     | 糖摄入 > 用户设定阈值    | 今天糖摄入偏高，奶茶/甜饮建议减少糖度或小料。              |
| 钠     | 钠摄入 > 用户设定阈值    | 今天钠摄入偏高，后续饮食建议少盐、少加工食品。             |
| 咖啡因 | 咖啡因接近或超过阈值     | 今天咖啡因摄入较高，晚上尽量避免咖啡、浓茶和能量饮料。     |

注意：提醒文案必须温和，不能像医疗诊断。

---

## 8. 外部数据源接入策略

### 8.1 普通食物

优先级：

1. 本地内置常见食物表。
2. USDA FoodData Central。
3. 用户手动新增。

### 8.2 包装食品

优先级：

1. Open Food Facts。
2. 条形码扫描。
3. 用户手动录入营养成分表。

### 8.3 奶茶咖啡

优先级：

1. 内置常见品牌饮品样例。
2. 品牌官网公开菜单。
3. 用户自定义饮品。
4. 后续再做网页搜索/爬取/人工确认。

说明：饮品品牌数据变化快，不建议第一版就做复杂爬虫。第一版可以用 seed 数据覆盖常见饮品组合。

---

## 9. ClaudeCode 开发阶段

### 阶段 0：项目初始化

任务：创建 Expo + TypeScript 项目，配置 expo-router 和底部 Tab。
验收：APP 能启动，有首页、添加、统计、我的四个页面。

### 阶段 1：基础 UI

任务：实现 MetricCard、ReminderCard、FoodLogItem 等组件。
验收：首页能展示静态假数据。

### 阶段 2：数据库

任务：接入 SQLite，创建表，写 seed 数据和 repository。
验收：应用启动自动建表，能插入和查询测试数据。

### 阶段 3：饮食记录

任务：实现早餐/午餐/晚餐/加餐记录。
验收：添加记录后首页今日总览更新。

### 阶段 4：饮品记录

任务：实现品牌、饮品、杯型、糖度、小料选择和计算。
验收：能保存饮品记录，并计算热量、糖、咖啡因。

### 阶段 5：用户资料

任务：实现资料表单和目标热量估算。
验收：修改资料后首页目标热量变化。

### 阶段 6：提醒系统

任务：根据今日汇总和用户目标生成提醒。
验收：糖、咖啡因、热量、蛋白质等异常时显示提醒卡片。

### 阶段 7：统计图表

任务：实现日/周趋势图。
验收：能查看一周热量趋势和咖啡因趋势。

### 阶段 8：联网搜索

任务：接入 USDA / Open Food Facts 查询，并将结果缓存到本地。
验收：搜索外部食物后可添加到记录。

### 阶段 9：打磨展示版

任务：完善空状态、加载状态、错误提示、编辑/删除、数据导出。
验收：可以完整演示 3 分钟。

---

## 10. 可直接发给 ClaudeCode 的 Prompt

### Prompt 1：项目初始化

```text
请创建一个 Expo + React Native + TypeScript 的饮食记录 APP 项目。要求使用 expo-router 做底部 Tab 导航，包含：首页、添加、统计、我的四个页面。请给出完整目录结构和每个文件代码，保证 npm install 后可以运行。
```

### Prompt 2：数据库建表

```text
请在当前项目中接入 expo-sqlite，创建 user_profile、food_items、food_logs、drink_options、reminder_rules 表。要求封装 database.ts、schema.ts、seed.ts，并提供 repository 层的增删改查方法。所有 SQL 需要幂等，应用启动时自动初始化。
```

### Prompt 3：饮食记录

```text
请实现添加饮食记录功能：用户选择 breakfast/lunch/dinner/snack，搜索 food_items，输入克数或份数，系统自动计算 kcal、protein、fat、carbs、sugar、sodium、caffeine，并保存到 food_logs。保存后首页今日总览自动更新。
```

### Prompt 4：饮品记录

```text
请实现饮品记录页面：用户选择品牌、饮品名称、杯型、糖度、小料，系统根据 seed-drinks.json 和 drink_options 表计算总热量、糖和咖啡因。请把计算逻辑独立到 drinkCalculator.ts，并写几个示例测试数据。
```

### Prompt 5：提醒系统

```text
请实现 reminderService：输入用户资料、今日 summary 和 reminder_rules，输出提醒卡片数组。提醒包括热量超标、蛋白质不足、糖摄入偏高、钠摄入偏高、咖啡因偏高。首页展示这些提醒，文案要温和，不要像医疗诊断。
```

---

## 11. 展示 Demo 流程

1. 打开 APP，进入“我的”，填写性别、年龄、身高、体重、活动水平和目标。
2. 回到首页，看到今日目标热量和营养素目标。
3. 添加早餐：鸡蛋、牛奶、面包。
4. 添加加餐：水果或零食。
5. 添加饮品：品牌、饮品、杯型、糖度、小料。
6. 首页显示糖或咖啡因提醒。
7. 进入统计页，查看一周热量趋势和咖啡因趋势。

---

## 12. 后续加分功能

- 拍照识别食物。
- 条形码扫描包装食品。
- 常吃模板。
- 饮品热量占比分析。
- 连续多日趋势提醒。
- CSV / JSON 数据导出。
- AI 周报总结。

---

## 13. 风险控制

| 风险                    | 解决方案                             |
| ----------------------- | ------------------------------------ |
| 营养数据不准            | 标注“估算值”，允许用户手动修改       |
| 饮品数据难获取          | 第一版用内置样例表，后续再接联网搜索 |
| 提醒过于绝对            | 文案用“建议/可能/参考”，加入免责声明 |
| 功能过多做不完          | 先完成本地 MVP，再做联网和图表       |
| ClaudeCode 一次生成太多 | 按阶段小任务生成，每阶段运行验证     |

---

## 14. 项目亮点总结

这个 APP 的亮点不只是记录热量，而是：

1. 把三餐、加餐、饮品分开记录，符合真实生活场景。
2. 对奶茶、咖啡等饮品做更细粒度建模，支持品牌、杯型、糖度、小料和咖啡因。
3. 根据用户个人资料生成当日提醒，具备一定个性化能力。
4. 数据采用本地 SQLite 保存，后续可扩展联网食品数据库。
5. 项目结构清晰，适合用 ClaudeCode 分阶段开发。

备注：本项目中的营养和咖啡因计算均定位为生活记录与大致估算，不构成医学、诊断或治疗建议。
