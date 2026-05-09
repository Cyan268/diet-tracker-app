# Diet Tracker App - 日常饮食记录

轻量级饮食记录 APP，支持三餐、零食、奶茶咖啡等饮品记录，自动估算热量和营养素。

## 技术栈

- React Native + Expo SDK 54
- TypeScript
- expo-router (file-based routing)
- SQLite (后续阶段)

## 项目结构

```
app/                  # expo-router 页面
  _layout.tsx         # 根布局
  (tabs)/             # 底部 Tab 导航
    _layout.tsx       # Tab 配置
    index.tsx         # 今日总览
    add.tsx           # 添加记录
    stats.tsx         # 统计
    profile.tsx       # 我的

src/
  components/         # 通用组件
  db/                 # 数据库相关
  features/           # 功能模块
  services/           # API 服务
  types/              # TypeScript 类型
  utils/              # 工具函数

assets/
  seed/               # 种子数据
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

按开发计划文件分阶段执行，当前进度：阶段 0（项目初始化）。
