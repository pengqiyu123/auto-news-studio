# 分析中心 Tab 设计方案

> 四角色团队（探索者、产品经理、设计师、架构师）并行分析后综合产出。
> 目标：智能化数据分析与研判与闭环。独立第 11 个 Tab。

---

## 团队共识

| 共识点 | 说明 |
|--------|------|
| **独立 Tab** | 在现有 10 Tab 旁新增"分析中心"，不塞进总览页 |
| **分区面板布局** | 上下分区 + 左右分栏，与现有 intel-overview-grid 模式一致 |
| **不用图表库** | 主题趋势用 CSS 条形图，事件关联用简化 SVG，零新依赖 |
| **反馈嵌入报告** | 不单独设反馈区，嵌入研判报告卡片底部（3 个按钮 + 可展开输入框） |
| **自管理 state** | `screens/analysis/state.ts` 模式，与 overview/events 一致 |
| **analysis- CSS 前缀** | 新 class 统一前缀，与 intel-/watchlist-/briefs- 平行 |

---

## 页面布局（方案 A：分区面板）

```
+====================================================================+
|  [主控条]  分析中心                    时间范围: [7d] [30d] [全部]  |
|  最新报告: 2026-05-29 周报 | 覆盖 12 主题 · 43 实体 | [生成报告]   |
+====================================================================+
|  +-- 研判报告 (40%) ------------+ +-- 主题趋势 (60%) -----------+ |
|  | [结构化摘要]                  | | [水平条形图 + 趋势箭头]       | |
|  | 主结论/关键发现/风险提示      | | ████████ OpenAI    ↑ 升温    | |
|  | [✓准确] [✎纠正] [✗不准确]     | | ██████   芯片制裁   ↑ 升温    | |
|  +-------------------------------+ +------------------------------+ |
|  +-- 实体热度 (60%) ------------+ +-- 事件关联 (40%) -----------+ |
|  | [排行表: 名/实体/热度/趋势]   | | [SVG 关系网络 + 关联对列表]   | |
|  | 1. OpenAI  86 ↑  8事件       | | (A)──主题──(B)               | |
|  | 2. 华为    78 ↑  12事件      | | Top 3 关联对列表              | |
|  +-------------------------------+ +------------------------------+ |
|  +-- 历史报告 (100%) -------------------------------------------+ |
|  | [时间线列表] ○ 05-29 周报  ○ 05-22 周报  ● 05-15 月报      | |
|  +-------------------------------------------------------------+ |
+====================================================================+
```

---

## 功能分 3 批交付

### P0 — 核心骨架（首批）

| # | 功能 | 数据来源 | 已有API | 需要新API | LLM |
|---|------|---------|---------|----------|-----|
| F1 | 主题趋势条形图 | topic_models | `GET /topics` | 否 | 否 |
| F2 | 实体热度排行表 | trend_signals | `GET /trends` | 否 | 否 |
| F3 | 事件关联缩略图 | event_relations | `GET /events/{id}/related` | 否 | 否 |
| F4 | 主控条（时间范围切换 + 统计摘要） | 聚合计算 | 否 | 是：`GET /analysis/signals` | 否 |

### P1 — 分析深度（第二批）

| # | 功能 | 数据来源 | 已有API | 需要新API | LLM |
|---|------|---------|---------|----------|-----|
| F5 | 反馈标记（准确/不准确） | 新表 analysis_feedback | 否 | 是：`POST /analysis/feedback` | 否 |
| F6 | 主题下钻（点击主题→关联事件列表） | event_topics | 否 | 是：`GET /topics/{id}/events` | 否 |
| F7 | 实体下钻（点击实体→跳转热点簇） | 跨 Tab 导航 | 已有 | 否 | 否 |

### P2 — 智能研判（第三批，依赖 LLM）

| # | 功能 | 数据来源 | 已有API | 需要新API | LLM |
|---|------|---------|---------|----------|-----|
| F8 | 研判报告生成 | 所有分析数据 + LLM | 否 | 是：`POST /analysis/report` | 是 |
| F9 | 周报/月报自动生成 | 所有分析数据 + LLM | 否 | 是：`POST /analysis/reports/weekly` | 是 |
| F10 | 历史报告查看 | analysis_reports | 否 | 是：`GET /analysis/reports` | 否 |
| F11 | 反馈统计仪表盘 | analysis_feedback | 否 | 是：`GET /analysis/feedback/stats` | 否 |

---

## 前端集成清单

### 新建文件

| 文件 | 用途 |
|------|------|
| `frontend/src/screens/analysis/page.tsx` | 主页面组件 |
| `frontend/src/screens/analysis/state.ts` | useAnalysisState hook |
| `frontend/src/styles/analysis.css` | 新样式（analysis- 前缀） |

### 修改文件（精确改动）

| 文件 | 改动 | 回归风险 |
|------|------|---------|
| `navigation/tabs.ts` | TabKey 新增 `"analysis"` + intelTabs 新增一项 + pageMeta 新增一条 | 中 |
| `hooks/shell/useAppShellState.ts` | loadedTabs 初始值新增 `analysis: false` | 低 |
| `app.tsx` | 新增 import + hook 调用 + loadTabData switch case + JSX 渲染块 | 中高 |
| `lib/api.ts` | api 对象末尾新增方法 | 低 |
| `types.ts` | 文件末尾新增类型 | 低 |

### 代码风格约束

1. Props 用 `interface AnalysisPageProps` 定义，不用 `React.FC`
2. State hook 签名：`export function useAnalysisState({ onToast, onError, ... }: UseAnalysisStateParams)`
3. API 调用全通过 `api` 对象，不直接 fetch
4. 条件渲染：`{activeTab === "analysis" ? <AnalysisPage ... /> : null}`
5. 错误处理：`try/catch` + `onError(err instanceof Error ? err.message : "分析数据加载失败")`
6. 样式：复用现有 `panel`、`panel-header`、`ghost-button`、`entity-tag`、`trend-*` 等 class
7. lucide-react 图标：从 lucide-react 导入（推荐 `BarChart3` 或 `Brain` 作为 Tab 图标）

---

## 后端 API 缺口

### P0 需要新增

```
GET /api/admin/analysis/signals
  → { "items": [{ entity_id, entity_name, trend, trend_label, sma_7d, sma_14d, recent_event_count, latest_event_title }] }
  聚合趋势信号 + 最新事件摘要
```

### P1 需要新增

```
GET /api/admin/topics/{topic_id}/events
  → { "items": [{ event_id, title, composite_score, first_seen_at }] }

POST /api/admin/analysis/feedback
  body: { target_type, target_id, feedback_type: "confirm"|"correct"|"dismiss", correction?: { note } }
  → { "ok": true, "feedback_id": "..." }
```

### P2 需要新增

```
POST /api/admin/analysis/report
  body: { scope: "daily"|"weekly"|"monthly", date_from, date_to }
  → { "item": { report_id, status, markdown, sections: { ... } } }

GET /api/admin/analysis/reports?limit=10
  → { "items": [{ report_id, scope, period_start, period_end, status, preview }] }

GET /api/admin/analysis/feedback/stats
  → { "total": N, "accurate_pct": 0.85, "by_type": { ... } }
```

### 数据库新增表

```sql
CREATE TABLE analysis_feedback (
    id              VARCHAR(64) PRIMARY KEY,
    target_type     VARCHAR(32) NOT NULL,
    target_id       VARCHAR(64) NOT NULL,
    feedback_type   VARCHAR(16) NOT NULL,
    correction_note TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE analysis_reports (
    id              VARCHAR(64) PRIMARY KEY,
    report_type     VARCHAR(16) NOT NULL,
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    content_markdown TEXT NOT NULL DEFAULT '',
    metadata_json   JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## CSS 设计规范

### 命名：`analysis-` 前缀

```css
/* 布局 */
.analysis-hero              /* 主控条 */
.analysis-grid-row          /* 双列容器 */
.analysis-grid-row-wide     /* 全宽容器 */

/* 主题趋势 */
.analysis-topics-panel      /* 主题面板 */
.analysis-topic-row         /* 单个主题行 */
.analysis-topic-bar         /* 条形容器 */
.analysis-topic-bar-fill    /* 条形填充 */

/* 实体热度 */
.analysis-entity-panel      /* 实体面板 */
.analysis-entity-table      /* 实体表格 */
.analysis-entity-row        /* 表格行 */

/* 研判报告 */
.analysis-report-panel      /* 报告面板 */
.analysis-report-summary    /* 主结论引用块 */
.analysis-feedback-row      /* 反馈按钮行 */

/* 事件关联 */
.analysis-relation-panel    /* 关联面板 */
.analysis-relation-graph    /* SVG 图容器 */
.analysis-relation-pairs    /* 关联对列表 */

/* 历史报告 */
.analysis-history-panel     /* 历史面板 */
.analysis-timeline          /* 时间线容器 */
.analysis-timeline-item     /* 时间线条目 */
```

### 可复用现有 class

`.panel` `.panel-header.compact` `.eyebrow` `.subtle` `.ghost-button` `.entity-tag` `.entity-trend-indicator` `.trend-hot/.trend-warm/.trend-cool/.trend-emerging` `.status-badge` `.empty-state` `.intel-score-row` `.intel-inline-actions`

### 趋势颜色

| 趋势 | 背景 | 文字 | 符号 |
|------|------|------|------|
| hot 升温 | #fef2f2 | #dc2626 | ↑ |
| emerging 新升 | #f0fdf4 | #16a34a | ✦ |
| warm 平稳 | #f8fafc | #64748b | → |
| cool 回落 | #eff6ff | #2563eb | ↓ |
| cold 冷却 | #f8fafc | #64748b | ↓ |

### 响应式

| 断点 | 行为 |
|------|------|
| > 1200px | 双列分栏 |
| 960-1200px | 单列堆叠 |
| < 960px | 单列，实体表格横向滚动，关联图变列表 |

---

## 验收标准（P0）

1. `cd auto-news-studio/frontend && npm run build` 通过
2. `cd auto-news-studio/frontend && npm run test -- --run` 通过
3. Tab 栏出现"分析中心"Tab，图标正确
4. 点击进入后显示主控条 + 4 个区域面板
5. 主题趋势区显示条形图 + 趋势箭头
6. 实体热度区显示排行表 + EntityTrendIndicator
7. 事件关联区显示 Top 关联对
8. 无数据时各面板显示 empty-state
9. 所有现有 Tab 功能不受影响
