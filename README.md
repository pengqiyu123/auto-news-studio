# Auto News Studio

AI 驱动的新闻情报与发布平台，面向微信公众号（公众号）运营场景。

一站式完成：多源采集 → 智能聚类 → 热度评分 → 预警追踪 → 深度分析 → 简报生成 → 微信草稿发布。

## 功能特性

### 情报层

- **多源采集**：RSS、Reddit、Hacker News、GitHub Trending、微博热搜、抖音热榜等 20+ 信息源
- **智能聚类**：Union-Find + Jaccard 相似度自动合并同源报道，减少信息噪音
- **多维评分**：速度（Velocity）× 0.4 + 覆盖（Coverage）× 0.35 + 新鲜（Freshness）× 0.25
- **预警系统**：四级预警状态机（new → watch → rising → breakout → cooling），自动追踪热点演变
- **实体追踪**：关注指定实体（公司、人物、产品），跨事件聚合相关信息

### 内容层

- **深度分析**：LLM 驱动的正文抓取与分析，生成事件深度摘要
- **简报生成**：自动汇总多个热点事件，生成结构化简报
- **TipTap 编辑器**：富文本编辑，支持 Markdown 序列化与微信 HTML 预览

### 发布层

- **微信草稿箱**：Playwright 浏览器自动化，将简报推送至微信公众号草稿箱
- **一键同步**：简报生成后可直接同步为微信草稿，支持预览与手动调整

### 运维层

- **来源健康监控**：实时监控每个信息源的状态、响应时间、成功率
- **运行日志**：分级日志查看，支持按级别和关键词过滤
- **三种自动化模式**：仅雷达 / 雷达+简报 / 全流程
- **版本更新提示**：读取 GitHub Releases，应用内提示可升级的新版本

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+, FastAPI, Uvicorn, APScheduler |
| 前端 | React 19, TypeScript 5.8, Vite 7, TipTap |
| LLM | OpenAI SDK（兼容 NVIDIA、SiliconFlow、DeepSeek 等多家中国服务商） |
| 微信发布 | Playwright 浏览器自动化 |
| 数据存储 | JSON 文件持久化（线程安全，原子写入） |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- Chromium（Playwright 依赖）

### 安装步骤（开发）

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/auto-news-studio.git
cd auto-news-studio

# 2. 创建 Python 虚拟环境
python -m venv .venv
.venv/Scripts/activate      # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. 安装 Python 依赖
pip install -r backend/requirements.txt

# 4. 安装 Playwright 浏览器
playwright install chromium

# 5. 安装前端依赖
cd frontend
npm install
cd ..

# 6. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Key

# 7. 构建前端
cd frontend
npm run build
cd ..

# 8. 启动
start.bat                   # Windows（推荐）
# 或手动启动：
# cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后会自动构建前端并打开浏览器访问 `http://127.0.0.1:8000`。

## 配置说明

### LLM 配置

在设置页面配置 LLM 提供商。支持以下服务商：

- OpenAI / Azure OpenAI
- NVIDIA NIM
- SiliconFlow（硅基流动）
- DeepSeek
- 智谱 AI（GLM）
- 零一万物（Yi）
- 阿里云百炼（Qwen）
- 月之暗面（Moonshot / Kimi）

每个提供商可配置 API Key、Base URL 和模型名称。系统按任务类型自动路由。

### 自动化模式

| 模式 | 说明 |
|------|------|
| `radar_only` | 仅采集和聚类，不生成简报 |
| `radar_and_draft` | 采集聚类 + 自动生成简报 |
| `full_pipeline` | 全流程：采集 → 简报 → 微信草稿 |

### 信息源

信息源通过 `backend/app/sources/` 目录下的模块自动注册。支持：

- **RSS** (`sources/rss/`)：标准 RSS/Atom 订阅源
- **热榜** (`sources/hotlists/`)：微博、抖音、知乎等平台热榜
- **监控** (`sources/monitors/`)：GitHub Trending、Hacker News 等

每个来源有独立权重（0.6-0.9），影响评分中的覆盖度计算。

## 目录结构

```
auto-news-studio/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI 应用入口、路由
│       ├── store.py             # 数据持久化（JSON + RLock）
│       ├── models.py            # Pydantic v2 数据模型
│       ├── intel_pipeline.py    # 情报管道：聚类、评分、预警
│       ├── connectors.py        # 多源采集驱动
│       ├── llm.py               # LLM 多提供商路由
│       ├── publishers.py        # 微信公众号发布自动化
│       ├── deep_dive.py         # 深度分析模块
│       ├── briefing.py          # 简报生成模块
│       ├── entity_extractor.py  # 实体识别与抽取
│       └── sources/             # 信息源注册
│           ├── registry.py
│           ├── rss/
│           ├── hotlists/
│           └── monitors/
├── frontend/
│   └── src/
│       ├── app.tsx              # 主应用（状态管理）
│       ├── components/          # 页面组件
│       ├── lib/                 # 工具函数
│       └── styles.css           # 全局样式
├── scripts/                     # 启动/停止脚本
├── start.bat                    # Windows 一键启动
├── .env.example                 # 环境变量模板
└── LICENSE                      # MIT License
```

## API

所有 API 端点位于 `/api/admin/` 下：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/dashboard` | 系统全景状态 |
| GET | `/api/admin/intel/stream` | 实时素材流 |
| GET | `/api/admin/intel/events` | 聚合热点事件 |
| GET | `/api/admin/intel/alerts` | 预警列表 |
| GET | `/api/admin/sources` | 来源健康状态 |
| POST | `/api/admin/jobs/run` | 触发操作 |
| PUT | `/api/admin/runtime/plan` | 配置自动化计划 |
| POST | `/api/admin/runtime/start` | 启动自动化 |
| POST | `/api/admin/runtime/stop` | 停止自动化 |

## Windows 分发版

- 分发对象：单用户、本机运行
- 安装方式：运行 `install.bat`
- 自检方式：运行 `doctor.bat`
- 备份恢复：见 [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md)
- 更新提示：项目发布新 GitHub Release 后，应用首页与设置页会提示新版本；若匿名请求遇到限流，可在 `.env` 中配置 `GITHUB_TOKEN`

## 注意事项

- **单用户设计**：当前无认证机制，默认仅适用于单用户本地部署
- **数据安全**：分发版配置保存在 `config/user-settings.json`，请勿公开分享
- **微信发布**：使用 Playwright 浏览器自动化，不会自动点击最终发布按钮，需手动确认
- **LLM 容错**：LLM 调用失败不会阻塞主管道，会降级为规则化简报

## License

[MIT](LICENSE)
