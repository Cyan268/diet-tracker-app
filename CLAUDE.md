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
  (tabs)/             # 底部 Tab 导航
    _layout.tsx       # Tab 配置
    index.tsx         # 今日总览（已接入数据库）
    add.tsx           # 添加记录
    stats.tsx         # 统计
    profile.tsx       # 我的

src/
  components/         # 通用组件
    MetricCard.tsx    # 营养指标卡片
    ReminderCard.tsx  # 提醒卡片
    FoodLogItem.tsx   # 饮食记录条目
  db/                 # 数据库相关
    database.ts       # SQLite 连接
    schema.ts         # 建表 SQL
    seed.ts           # 种子数据插入
    repositories/     # 数据访问层
  features/           # 功能模块
    summary/          # 每日汇总
  types/              # TypeScript 类型
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

按开发计划文件分阶段执行，当前进度：阶段 2 完成。

- [x] 阶段 0：项目初始化
- [x] 阶段 1：基础 UI 组件（MetricCard、ReminderCard、FoodLogItem）
- [x] 阶段 2：数据库（SQLite 建表、种子数据、Repository 层）
- [ ] 阶段 3：饮食记录（早餐/午餐/晚餐/加餐记录）
- [ ] 阶段 4：饮品记录
- [ ] 阶段 5：用户资料
- [ ] 阶段 6：提醒系统
- [ ] 阶段 7：统计图表
- [ ] 阶段 8：联网搜索
- [ ] 阶段 9：打磨展示版
