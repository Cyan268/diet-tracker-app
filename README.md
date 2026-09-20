# NutriPilot

一款支持 Android、iOS 和 Web 的 AI 饮食记录应用。用户可以记录每日饮食、查看营养趋势，并通过自然语言快速生成待确认的饮食草稿。

## 功能

- 饮食记录、编辑、删除与每日营养统计
- 根据身高、体重、性别和活动水平计算个性化目标
- 20+ 常见茶饮与咖啡品牌、100+ 饮品和可选小料
- 本地食品搜索与 Open Food Facts 联网搜索
- 离线记录、自动同步和多设备冲突处理
- 自然语言识别食物、数量和餐次
- 私有图片上传、AI 图片识别与人工确认后入账
- 用户自行配置 OpenAI API Key
- AI 饮食助手和个性化营养周报
- CSV、JSON 数据导出与饮食提醒

AI 生成的内容只作为草稿，正式记录需要用户确认；营养数值由应用代码和食品目录计算。

## 技术栈

- Expo / React Native / TypeScript
- Expo Router、Expo SQLite、SecureStore
- FastAPI / SQLAlchemy / Alembic
- PostgreSQL / Redis
- OpenAI Responses API
- Docker Compose

## 本地运行

### 1. 启动后端

请先安装 Docker Desktop，然后在项目根目录执行：

```bash
docker compose up -d --build
```

后端接口文档：`http://127.0.0.1:8000/docs`

### 2. 启动 App

```bash
npm install
npm start
```

浏览器预览：

```bash
npm run web:preview
```

然后打开 `http://127.0.0.1:8082`。

Android 模拟器连接本机后端时，通常将 `.env.local` 中的地址配置为：

```env
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000/api/v1
```

真机需要改为电脑在同一局域网中的 IP 地址。

## 开发检查

前端：

```bash
npm run check
```

后端：

```bash
cd backend
python -m venv .venv
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
python -m pytest
```

## AI API Key

普通账号可以在 App 设置页保存自己的 OpenAI API Key。Key 只会发送到 NutriPilot 后端，并以 AES-GCM 加密后存入数据库，不会写入客户端公开环境变量。共享演示账号不能保存或使用私人 Key。

未配置 Key 时，应用会使用本地规则识别，手动记录和营养统计仍可正常使用。

## 说明

- 品牌饮品的配方和营养数据可能随门店、杯型和时间变化，请以品牌官方信息为准。
- 本项目提供的营养分析仅用于日常记录，不构成医疗、诊断或治疗建议。

## License

本项目采用 [MIT License](LICENSE)。
