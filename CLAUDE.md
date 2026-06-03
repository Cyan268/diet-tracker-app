# Diet Tracker App - 日常饮食记录

轻量级饮食记录 APP，支持三餐、零食、奶茶咖啡等饮品记录，自动估算热量和营养素。

## 技术栈

- React Native + Expo SDK 54
- TypeScript
- expo-router (file-based routing)
- expo-sqlite (本地数据库)
- zustand (状态管理，待接入)
- zod (数据校验，待接入)

## 项目结构

```
app/                  # expo-router 页面
  _layout.tsx         # 根布局（含数据库初始化）
  add-food.tsx        # 添加食物页面（含联网搜索）
  add-drink.tsx       # 添加饮品页面
  edit-log.tsx        # 编辑饮食记录
  edit-profile.tsx    # 编辑个人资料
  reminder-settings.tsx # 提醒设置
  (tabs)/             # 底部 Tab 导航
    _layout.tsx       # Tab 配置
    index.tsx         # 今日总览（含提醒）
    add.tsx           # 添加记录入口
    stats.tsx         # 统计（图表展示）
    profile.tsx       # 我的（含目标展示）

src/
  components/         # 通用组件
    MetricCard.tsx    # 营养指标卡片
    ReminderCard.tsx  # 提醒卡片
    FoodLogItem.tsx   # 饮食记录条目（支持滑动删除）
    EmptyState.tsx    # 空状态组件
  db/                 # 数据库相关
    database.ts       # SQLite 连接
    schema.ts         # 建表 SQL
    seed.ts           # 种子数据插入
    repositories/     # 数据访问层
  features/           # 功能模块
    drink/            # 饮品计算
    export/           # 数据导出（CSV/JSON）
    food/             # 食物计算
    profile/          # 用户资料计算（BMR/TDEE）
    stats/            # 统计数据聚合
    summary/          # 每日汇总 + 提醒服务
  services/           # 外部 API 服务
    openFoodFactsApi.ts   # Open Food Facts 搜索
    foodSearchService.ts  # 本地+联网联合搜索
  types/              # TypeScript 类型
    external.ts       # 外部食物数据类型
    ...
  utils/              # 工具函数

assets/
  seed/               # 种子数据 JSON
```

## 常用命令

```bash
npm start          # 启动开发服务器
npm run android    # Android 运行
npm run ios        # iOS 运行
npm run web        # Web 运行
npx tsc --noEmit   # 类型检查
```

## 开发阶段

按开发计划文件分阶段执行，当前进度：全部完成。

- [x] 阶段 0：项目初始化
- [x] 阶段 1：基础 UI 组件（MetricCard、ReminderCard、FoodLogItem）
- [x] 阶段 2：数据库（SQLite 建表、种子数据、Repository 层）
- [x] 阶段 3：饮食记录（食物搜索、克数输入、营养素计算、保存）
- [x] 阶段 4：饮品记录（品牌/饮品/杯型/糖度/小料选择、热量计算）
- [x] 阶段 5：用户资料（BMR/TDEE 计算、目标热量估算）
- [x] 阶段 6：提醒系统（热量/蛋白质/糖/钠/咖啡因提醒）
- [x] 阶段 7：统计图表（一周趋势折线图、三餐占比饼图、饮品热量占比）
- [x] 阶段 8：联网搜索（Open Food Facts API、本地缓存、双源搜索）
- [x] 阶段 9：编辑/删除记录（滑动删除、点击编辑、营养素重算）
- [x] 阶段 9：提醒设置页面（开关规则、调整阈值）
- [x] 阶段 9：数据导出（CSV/JSON 格式，通过系统分享）
- [x] 阶段 9：空状态优化（EmptyState 组件、搜索无结果提示）
