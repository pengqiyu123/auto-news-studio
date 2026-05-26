# PostgreSQL Setup

## 架构结论（定版）

**PostgreSQL 是唯一主账本。**

采集主链、正文证据、AI 文章产物都进入同一 PostgreSQL 实例的不同表域。JSON 只作为兼容投影，不再作为热点分析、预警判断和历史回看的真源。

### 单库分表域原则

| 表域 | 职责 | 表 |
|------|------|-----|
| `ingest` | 采集主链 | `sources`, `raw_items`, `discovery_items_current`, `intel_events_current`, `event_snapshots`, `intel_alerts_current`, `intel_event_history`, `intel_alert_history`, `sync_runs` |
| `content` | 内容资产 | `deep_dive_records`, `deep_dive_documents`, `brief_records`, `documents` (正文证据) |
| `ops` | 运维审计 | 后续审计、任务、诊断表 |

### JSON 投影层

- `state.json` 只做兼容投影，不做主分析数据源
- 短期：前端可继续读 JSON 投影
- 长期：前端应该读 PostgreSQL API，不应该依赖 JSON

### 分析层

**热点分析、预警分析、数据分析最终都应该从 PostgreSQL 主账本做，而不是继续从 480 条 JSON 窗口做。**

- 热点分析 → 基于 `intel_events`、`intel_alerts` 聚合
- 预警分析 → 基于 `intel_alert_history`、`intel_event_history` 趋势
- 数据分析 → 物化视图、窗口函数

---

## Local Docker Compose

Use the bundled compose file:

```powershell
docker compose -f docker-compose.postgres.yml up -d
```

Default connection string:

```text
postgresql+psycopg://postgres:postgres@127.0.0.1:5432/auto_news_studio
```

## Environment

Set these variables before enabling the database-backed state flow:

```text
STATE_BACKEND=json
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/auto_news_studio
```

Phase-1 scaffolding keeps `STATE_BACKEND=json` as the default. Planned rollout:

| Phase | 配置 | 目标 |
|-------|------|------|
| **1a** | `STATE_BACKEND=dual_write` | 验证 PostgreSQL 写入稳定 |
| **1b** | 采集主链 current tables 成为 API 正式读源 | JSON 继续保留兼容投影 |
| **1c** | 热点/预警/summary 正式基于 PostgreSQL 读 | 分析逻辑迁移 |
| **2** | `content` 表域上线 | 正文证据、AI 文章产物入库 |
| **3** | 分析逻辑完全迁移 | 从 JSON 窗口迁移到 PostgreSQL 主账本 |

## Alembic

After installing backend dependencies:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
```

## Initialize Schema

```powershell
.venv\Scripts\python.exe scripts/init_postgres.py
```

## Backfill Current State

```powershell
.venv\Scripts\python.exe scripts/backfill_ingest_chain.py
.venv\Scripts\python.exe scripts/backfill_content_assets.py
```

The ingest backfill script matches the existing ingest chain only:

- `sources`
- `raw_items`
- `discovery_items`
- `intel_events`
- `event_snapshots`
- `intel_alerts`
- `intel_event_history`
- `intel_alert_history`

It does not backfill:

- `publish`
- `browser`
- `agent_html`

## Phase 2 Content Assets

Phase 2 stores long-lived content assets in the same PostgreSQL instance, but in separate table domains:

- `deep_dive_records`
- `deep_dive_documents`
- `brief_records`

The current backfill script for content assets is:

```powershell
.venv\Scripts\python.exe scripts/backfill_content_assets.py
```

This Phase 2 backfill covers:

- `deep_dive_records`
- `deep_dive_documents`
- `brief_records`
