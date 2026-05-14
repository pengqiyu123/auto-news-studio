# Auto News Studio

面向微信公众号运营场景的新闻情报与发布平台。

项目固定维护一套共享业务数据：多源采集 → 智能聚类 → 热度评分 → 预警追踪 → 深度分析 → 文章整理 / 简报整理 → 微信草稿箱同步。

当前同时支持两种使用方式：

- **传统模式**：前端总览页中的内置脚本 / 规则驱动三档自动化控制台
- **Agent 模式**：外部 AI 工具读取仓库与 `AGENT.md` 后，直接调用项目真实接口驱动工作流

另外，Agent 模式下现已支持一条**独立的 HTML 结构化采集链**：

- **Agent HTML 模式**：用于品牌新闻页、博客页、更新页的 HTML 持续抓取、结构化存储、版本追踪与独立事件历史

## 功能特性

### 情报层

- **多源采集**：RSS、Reddit、Hacker News、GitHub Trending、微博热搜、抖音热榜等 20+ 信息源
- **智能聚类**：Union-Find + Jaccard 相似度自动合并同源报道，减少信息噪音
- **多维评分**：速度（Velocity）× 0.4 + 覆盖（Coverage）× 0.35 + 新鲜（Freshness）× 0.25
- **预警系统**：四级预警状态机（new → watch → rising → breakout → cooling），自动追踪热点演变
- **实体追踪**：关注指定实体（公司、人物、产品），跨事件聚合相关信息

### 内容层

- **深度分析**：LLM 驱动的正文抓取与分析，生成事件深度摘要
- **Agent HTML 采集**：独立抓取 HTML 列表页与详情页，支持规则优先、AI 兜底的文章发现
- **结构化版本链**：同一 HTML 文档支持 revision 历史，便于判断新消息、旧消息与内容更新
- **共享文章记录**：事件可整理为共享文章 / 简报记录，复用同一套主数据与交付链
- **TipTap 编辑器**：富文本编辑，支持 Markdown 序列化与微信 HTML 预览

### 发布层

- **微信草稿箱**：Playwright 浏览器自动化，将文章记录同步到微信公众号草稿箱
- **发表记录抓取**：支持从公众号后台读取真实发表记录
- **抖音创作者中心**：支持打开文章发布页、结构探测、自动填充标题/摘要/正文与触发 AI 配图
- **重复上传保护**：同一篇同一 revision 不会重复上传

### 运维层

- **来源健康监控**：实时监控每个信息源的状态、响应时间、成功率
- **运行日志**：分级日志查看，支持按级别和关键词过滤
- **三种传统自动化模式**：仅雷达 / 雷达+简报 / 全流程
- **外部 AI 驱动说明**：根目录 `AGENT.md` 说明了 AI 如何安全、真实地操作本项目
- **版本更新提示**：读取 GitHub Releases，应用内提示可升级的新版本

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+, FastAPI, Uvicorn, APScheduler |
| 前端 | React 19, TypeScript 5.8, Vite 7, TipTap |
| LLM | OpenAI SDK（兼容 NVIDIA、SiliconFlow、DeepSeek 等多家中国服务商） |
| 微信发布 | Playwright 浏览器自动化 |
| 数据存储 | 单一 `data/state.json` 持久化（线程安全，原子写入） |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- Chromium（Playwright 依赖）

### 安装步骤（开发）

```bash
# 1. 克隆仓库
git clone https://github.com/pengqiyu123/auto-news-studio.git
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

# 8. 测试（推荐最小回归集）
.venv/Scripts/python -m pytest backend/tests/test_intel_pipeline.py backend/tests/test_admin_pagination.py backend/tests/test_agent_upload_guard.py
cd frontend && npm run test -- --run
cd ..

# 9. 启动
start.bat                   # Windows（推荐，要求 frontend/dist 已存在）
# 或手动启动：
# cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动后会检查 `frontend/dist` 是否存在；若前端已完成构建，会启动后端并自动打开一个受管仪表盘页。重复执行 `start.bat` 时会优先唤醒现有仪表盘页，而不是继续堆新标签。

说明：

- 本地开发、分发打包、发版前回归，统一使用项目 `.venv`，不要依赖机器全局 `pytest`
- 只要改了后端 Python 代码，手工 API 验证前都先执行一次 `stop.bat` 再 `start.bat`，避免误打到旧进程

## 外部 AI 驱动

如果你希望使用 Codex、Claude Code 或其他可读取项目文件的 AI 工具驱动工作流：

1. 让 AI 先阅读根目录的 [AGENT.md](AGENT.md)
2. AI 按 `AGENT.md` 中定义的**真实接口**调用项目
3. 所有结果继续写回同一个 `data/state.json`

这条路径不会创建第二套数据库，也不会引入第二套 Agent 产品壳。外部 AI 负责判断和写作，项目负责真实数据、真实浏览器链和真实日志。

严格要求：

- Agent 模式必须严格按项目既有链路执行：`sources/sync -> intel/events -> deep-dive -> brief -> agent/articles -> 平台执行`
- `开始今日的工作` 仅代表 Agent 对话口令，不是前端传统模式按钮，也不是 `/api/admin/runtime/start` 的别名
- 微信公众号、抖音创作者中心都属于下游平台执行环节，不是新的内容入口链路
- 不要跳过 `event -> deep-dive -> brief -> article` 这一组共享主链，也不要把“直接打开平台编辑页并填内容”当作正式入库方式
- 所有平台动作都只能消费已经写入共享 `briefs` 总账的记录，不能脱离项目主链单独生成一篇“游离文章”
- 微信公众号上传必须严格使用单标签页链路：每次都先回公众号后台首页，再从“新的创作 -> 文章”进入编辑页
- 不允许通过新建标签页规避微信流程问题；如果失败重试，必须重新走“首页 -> 文章 -> 编辑页”

### 快速口令

在 Agent 模式下，可以直接对 AI 说：`开始今日的工作`。

这句话约定代表按项目既有主链执行一次当天全流程，而不是只做单步操作，也不是启动传统模式调度器：

`sources/sync -> intel/events -> deep-dive -> brief -> agent/articles -> 平台执行`

默认含义：

- 先确认传统调度器已停止，避免和 Agent 链路冲突
- 获取当天最新情报并筛选值得写的主题
- 完成深挖、生成本地素材简报、撰写长文并写回共享 `briefs`
- 最后再进入目标平台执行步骤

如果用户没有额外指定平台，优先按当前项目默认交付链执行微信公众号草稿箱。

### Agent 手工回归清单

1. 先执行 `stop.bat`，再执行 `start.bat`
2. `GET /api/health`，确认后端在线
3. `GET /api/admin/runtime/status`，确认传统调度器已停止
4. `POST /api/admin/sources/sync?triggered_by=agent`
5. `GET /api/admin/intel/events?page=1&page_size=50`
6. `POST /api/admin/intel/events/{event_id}/deep-dive?triggered_by=agent`
7. `POST /api/admin/intel/events/{event_id}/brief?triggered_by=agent`，这里只生成本地素材记录
8. `POST /api/admin/agent/articles`，并设置 `publish_to_wechat_draft=true`
9. 如需执行下游平台动作，也必须基于第 8 步写入后的共享文章记录继续，不要绕过总账直接把内容塞进平台页
10. 不要对传统简报调用 `POST /api/admin/briefs/{brief_id}/wechat-draft`
11. 如需检查微信端，`check-drafts` 和 `check-publish-history` 必须串行执行，不能并发抢浏览器锁

### Agent HTML 手工回归清单

1. `POST /api/admin/agent-html/targets`
2. `GET /api/admin/agent-html/targets`
3. `POST /api/admin/agent-html/targets/{target_id}/run`
4. `POST /api/admin/agent-html/mainline-sync`
5. `GET /api/admin/agent-html/runs`
6. `GET /api/admin/agent-html/discovery`
7. `GET /api/admin/intel/events`
8. `GET /api/admin/agent-html/documents`
9. 如页面结构变更，使用 `POST /api/admin/agent-html/documents/{document_id}/reextract`

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

以下模式仅对应**项目内置传统自动化**：

| 模式 | 说明 |
|------|------|
| `radar_only` | 仅采集和聚类，不生成简报 |
| `radar_and_draft` | 采集聚类 + 自动生成简报 |
| `full_pipeline` | 全流程：采集 → 简报 → 微信草稿 |

说明：

- 外部 AI 驱动流程不是 `AutomationMode` 的第四档
- Agent 路径通过 `AGENT.md` + 真实 API 执行
- Studio 与 Agent 共用同一份 `data/state.json`

### 信息源

信息源通过 `backend/app/sources/` 目录下的模块自动注册。支持：

- **RSS** (`sources/rss/`)：标准 RSS/Atom 订阅源
- **热榜** (`sources/hotlists/`)：微博、抖音、知乎等平台热榜
- **监控** (`sources/monitors/`)：GitHub Trending、Hacker News 等

每个来源有独立权重（0.6-0.9），影响评分中的覆盖度计算。

### 传统模式补源

传统模式优先使用稳定、低维护的 `RSS/Atom` 源，不把需要登录、纯 HTML 页面解析、社媒时间线当作常规自动化输入。

项目内提供了一个品牌官方源审计脚本，用于：

- 扫描品牌官网、新闻页、博客页
- 探测 `RSS/Atom` 与 `WordPress REST` 线索
- 直接复用当前采集逻辑验证候选源
- 输出结构化报告，帮助筛选“当前可直连”的传统模式源

常用命令：

```bash
.venv/Scripts/python scripts/validate_brand_sources.py
.venv/Scripts/python scripts/validate_brand_sources.py --brand OpenAI --brand Apple
```

输出位置：

- `runtime/brand-source-audit/brand_sources_latest.json`
- `runtime/brand-source-audit/brand_sources_latest.md`

说明：

- “有用”严格指当前项目驱动可直连成功
- “没有”可能是没有 RSS，也可能是站点证书、超时、403/404 等导致当前环境不可用
- 经过验证可用的新传统源，可再通过 `/api/admin/sources` 写入项目状态

### Agent HTML 模式

Agent HTML 模式是独立于传统 RSS 的结构化采集链，适合以下场景：

- 品牌官方新闻页没有 RSS，但页面结构稳定
- 需要判断同一篇官方文章后续是否更新
- 需要让多篇相关文章形成独立发展轨迹
- 需要把 HTML 文章补充进现有 `raw_items -> discovery -> events -> alerts` 主链

关键特性：

- 与传统 `raw_items / intel_events` 完全分离
- 采集与维护使用独立接口 `/api/admin/agent-html/...`
- 已支持将 HTML 成果写入主链：`POST /api/admin/agent-html/mainline-sync`
- 列表页与详情页 HTML 都会缓存到 `runtime/agent_html_cache/`
- 同一文档优先使用 `canonical_url + content_hash` 判定
- 同一文档更新时追加 revision，不覆盖旧内容
- HTML 成功写入主链后，会按 RSS 风格 `raw_items` 参与统一事件、预警、深挖与简报流程

详细设计与维护说明见：

- `PLAN.md`
- `docs/AGENT_HTML_MODE.md`

## 目录结构

```
auto-news-studio/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用入口、路由
│   │   ├── store.py             # 数据持久化（JSON + RLock）
│   │   ├── store_base.py        # 存储基类
│   │   ├── store_defaults.py    # 存储默认值
│   │   ├── store_llm.py         # LLM 配置存储
│   │   ├── models.py            # Pydantic v2 数据模型
│   │   ├── models_llm.py        # LLM 配置模型
│   │   ├── intel_pipeline.py    # 情报管道：聚类、评分、预警
│   │   ├── connectors.py        # 多源采集驱动
│   │   ├── llm.py               # LLM 多提供商路由
│   │   ├── pipeline.py          # 采集结果归一化与入库桥接
│   │   ├── publishers.py        # 微信公众号发布自动化
│   │   ├── deep_dive.py         # 深度分析模块
│   │   ├── briefing.py          # 简报生成模块
│   │   ├── entity_extractor.py  # 实体识别与抽取
│   │   ├── entity_aliases.py    # 实体别名
│   │   ├── entity_types.py      # 实体类型定义
│   │   ├── cc_switch_bridge.py  # CC-Switch 桥接
│   │   ├── reference_projects.py # 参考项目管理
│   │   ├── legacy_sources.py    # 旧版来源兼容
│   │   └── sources/             # 信息源注册
│   │       ├── registry.py
│   │       ├── rss/
│   │       ├── hotlists/
│   │       └── monitors/
│   └── tests/                   # 后端测试
│       ├── test_intel_pipeline.py
│       ├── test_admin_pagination.py
│       └── test_agent_upload_guard.py
├── frontend/
│   └── src/
│       ├── app.tsx              # 主应用（状态管理）
│       ├── components/          # 页面组件（含 .test.tsx 测试）
│       ├── hooks/               # 自定义 Hooks
│       │   └── useAdaptivePolling.ts
│       ├── lib/                 # 工具函数
│       ├── types.ts             # 共享类型定义
│       ├── test/                # 测试配置
│       └── styles.css           # 全局样式
├── docs/                        # 项目文档
│   ├── DISTRIBUTION.md
│   ├── BRAND_SOURCE_AUDIT.md
│   └── RELEASE_WORKFLOW.md
├── scripts/                     # 发布与运维脚本
│   ├── validate_brand_sources.py # 品牌官方 RSS / WordPress 源验证脚本
├── AGENT.md                     # 外部 AI 工具的真实操作说明
├── start.bat                    # Windows 一键启动
├── stop.bat                     # Windows 停止
├── doctor.bat                   # 环境自检
├── install.bat                  # 分发版安装
├── pyproject.toml               # Python 项目配置（ruff）
├── version.json                 # 版本号
├── .env.example                 # 环境变量模板
└── LICENSE                      # MIT License
```

## API

所有主要 API 端点位于 `/api/admin/` 下。下面只列当前常用、且真实存在的接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/dashboard` | 系统全景状态 |
| GET | `/api/admin/intel/stream` | 实时素材流 |
| GET | `/api/admin/intel/events` | 聚合热点事件 |
| GET | `/api/admin/intel/alerts` | 预警列表 |
| GET | `/api/admin/intel/deep-dives` | 正文深挖列表 |
| GET | `/api/admin/briefs?page=&page_size=&stage=&q=` | 共享文章 / 简报记录 |
| GET | `/api/admin/wechat/mapping` | 微信草稿箱映射 |
| GET | `/api/admin/logs?page=&page_size=&level=&q=` | 系统日志 |
| GET | `/api/admin/publish-tasks?page=&page_size=` | 上传/删除操作记录 |
| POST | `/api/admin/sources/sync` | 同步全部来源 |
| POST | `/api/admin/intel/events/{event_id}/deep-dive` | 对指定事件执行正文深挖 |
| POST | `/api/admin/intel/events/{event_id}/brief` | 用传统流程为事件生成简报 |
| POST | `/api/admin/agent/articles` | 外部 AI 直接写入完整文章，并可同步微信草稿箱 |
| POST | `/api/admin/briefs/{brief_id}/wechat-draft` | 将现有文章 / 简报同步进微信草稿箱（Agent 长文不要走这里） |
| POST | `/api/admin/browser/wechat/check-drafts` | 检查真实微信草稿箱 |
| POST | `/api/admin/browser/wechat/check-publish-history` | 检查真实微信发表记录 |
| PUT | `/api/admin/runtime/plan` | 配置自动化计划 |
| POST | `/api/admin/runtime/start` | 启动自动化 |
| POST | `/api/admin/runtime/stop` | 停止自动化 |

更完整的外部 AI 使用建议，见 [AGENT.md](AGENT.md)。

### 列表分页参数

- `GET /api/admin/briefs?page=&page_size=&stage=&q=`
  - `stage`: `all | prepared | synced | failed`
  - `q`: 匹配 `title / one_line / why_it_matters`
- `GET /api/admin/logs?page=&page_size=&level=&q=`
  - `level`: `all | info | warning | error`
  - `q`: 匹配 `message / detail / category / actor`
- `GET /api/admin/publish-tasks?page=&page_size=`
- 统一返回：
  - `items`
  - `total`
  - `page`
  - `page_size`
  - `has_more`

## Windows 分发版

- 分发对象：单用户、本机运行
- 安装方式：运行 `install.bat`
- 自检方式：运行 `doctor.bat`
- 备份恢复：见 [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md)
- 更新提示：项目发布新 GitHub Release 后，应用首页与设置页会提示新版本；若匿名请求遇到限流，可在 `.env` 中配置 `GITHUB_TOKEN`

## 声明

- 本项目面向**本地、自有账号、自担责任**的内容运营场景，不提供第三方托管服务，也不代替平台官方审核。
- 项目会调用真实外部服务，包括 LLM API、公开信息源与微信公众号后台。请确认你有权访问和使用这些服务，并自行遵守对应平台的条款、频率限制与内容规范。
- 微信相关能力依赖浏览器自动化与当前页面结构。若公众号后台页面改版、账号权限变化、登录状态失效，相关操作可能失败，项目不会把失败伪装成成功。
- AI 生成内容仅提供辅助，不构成事实保证、投资建议、医疗建议或法律意见。正式发布前，请自行复核事实、引文、时效性与合规性。
- 仓库默认按真实数据链路工作；当上游不可用时，系统应报告失败而不是伪造成功结果。

## 发布流程

每次发版请按固定流程走，避免“版本号已更新，但旧版看不到更新”：

1. 更新版本号与更新说明
2. `python -m compileall backend/app`
3. `cd frontend && npm run build`
4. `git push origin master`
5. 发布对应的 GitHub Release

详细步骤见 [docs/RELEASE_WORKFLOW.md](docs/RELEASE_WORKFLOW.md)。

## 注意事项

- **单用户设计**：当前无认证机制，默认仅适用于单用户本地部署
- **单库设计**：Studio 与外部 AI 共用同一份 `data/state.json`，不要再建第二套业务数据库
- **数据安全**：分发版配置保存在 `config/user-settings.json`，请勿公开分享
- **微信发布**：使用 Playwright 浏览器自动化，不会自动点击最终发布按钮，需手动确认
- **LLM 容错**：LLM 调用失败不会阻塞主管道，会降级为规则化简报

## License

[MIT](LICENSE)
