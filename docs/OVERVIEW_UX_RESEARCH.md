# 总览页面 UX 改进调研报告

> 调研日期：2026-05-27
> 范围：总览页（overview）控制器以下区域的设计改进
> 关联问题：P1 预警→行动路径断裂、P7 缺数据新鲜度指标、P13 页面纵向过深、P14 预警/事件视觉无区分

---

## 一、评审问题回顾

跨职能评审（产品/运营/设计）发现 18 个问题，其中 4 个🔴必须改：

| 编号 | 问题 | 核心矛盾 |
|------|------|----------|
| P1 | 预警卡片缺"查看事件"操作 | 预警→深挖路径断裂 |
| P7 | 缺全局数据新鲜度指标 | 运营无法快速判断数据是否过时 |
| P13 | 页面纵向过深（~3000px） | 扫描效率不足，3-5秒内无法完成巡检 |
| P14 | 预警与事件卡片视觉无区分 | breakout 预警与 watch 事件紧急性等价 |

---

## 二、开源项目参考

### 2.1 监控/告警类仪表盘

#### Grafana Alert List Panel
- **地址**: https://play.grafana.org/d/bdodlcyou483ke/alert-list
- **相关代码**: https://github.com/grafana/grafana

**可借鉴模式**：

| 模式 | Grafana 做法 | Auto-news2 对应 |
|------|-------------|----------------|
| 告警状态机 | 5态模型：Normal→Pending→Firing→Resolved + NoData/Error | 映射到 new→watch→rising→breakout→cooling，建议加 NoData/Error 态 |
| 告警列表面板 | 按状态分组显示（firing/pending/normal），支持标签过滤 | 预警按级别分组，支持来源/类型过滤 |
| 告警→面板关联 | Alert rule 可链接到 Dashboard Panel，通知中含截图 | 预警卡片链接到对应事件详情（P1 的解决方案） |
| Pending Period | 滞后机制防止状态抖动 | watch→rising 阈值加滞后窗口 |

**直接可用**：Alert Rule → Panel Linking 模式解决 P1（预警卡片加 event_id 链接）。

#### PagerDuty Incident Workflow
- **地址**: https://support.pagerduty.com/main/docs/dynamic-notifications

**可借鉴模式**：
- **Acknowledge 概念**：运营看到 breakout 预警后，应有"已关注"操作，标记"有人在处理"。当前只有"观察"和"忽略"，缺少中间态。
- **MTTA/MTTR 指标**：追踪从 breakout 到深挖、从深挖到发布的耗时，给运营可见性。

#### Sentry Issue Grouping
- **地址**: https://github.com/getsentry/sentry

**可借鉴模式**：
- **Issue 分组 = 我们的 Union-Find 聚类**：Sentry 用 fingerprint 合并相似错误，我们用 Jaccard ≥ 0.45 合并相似新闻
- **卡片信息密度**：Sentry Issue 卡片显示：标题 + 事件数 + 用户数 + 首次/最后出现 + 负责人 + 状态。映射到我们：事件标题 + 来源数 + 平台数 + 首次/最后采集 + 简报状态 + alert_state
- **操作流**：Alert → Issue Grouping → Issue Detail → Resolve/Ignore/Assign，映射到：RawItem → IntelEvent → EventDetail → DeepDive/DraftBrief/Publish

### 2.2 新闻/媒体情报类仪表盘

#### News-Dash（AI 驱动新闻仪表盘）
- **地址**: https://github.com/Tejeswar001/news-dash
- **技术栈**: Next.js + React 19 + Tailwind CSS + Firebase

**可借鉴模式**：
- **快速搜索按钮**：热门话题的一键过滤，映射到 breakout 预警的快速跳转
- **词云可视化**：展示趋势聚类，可用于事件卡片中展示关键词标签
- **多面过滤**：按话题/国家/日期/关键词/来源同时过滤

#### DevHub（GitHub 版 TweetDeck）
- **地址**: https://github.com/devhubapp/devhub
- **技术栈**: TypeScript + React Hooks + Redux + React Native Web

**可借鉴模式**：
- **多列布局**：每列独立配置数据源和过滤器。可用于 Stream 页，分列显示"上升预警 / 观察列表 / 最近简报"
- **Inbox Zero 模式**：每列可标记"全部已读"，解决告警疲劳
- **Save for Later**：映射到我们的 watchlist 概念

#### changedetection.io（网站变更监控，31.5k stars）
- **地址**: https://github.com/dgtlmoon/changedetection.io

**可借鉴模式**：
- **Diff 视图**：展示新闻事件如何演变（新来源加入、分数变化），字/行/字符级别的对比
- **AI 变更摘要**：LLM 生成"价格从 $89.99 降到 $67.00"，映射到"3个新来源在1小时内加入此话题"
- **自然语言告警规则**："价格低于50时通知我"，映射到"5个以上来源在2小时内覆盖同一话题时预警"

### 2.3 运维/可观测性仪表盘

#### SigNoz
- **地址**: https://github.com/SigNoz/signoz

**可借鉴模式**：
- **经典布局**：侧边导航 + 顶部状态栏（系统健康/最后同步时间）+ 主内容区
- **Controller + Status Bar + Priority Content** 布局与我们当前架构最接近

#### shadcn/ui Incident Response Block
- **地址**: https://www.shadcn.io/blocks/dashboard-incident-response

**可借鉴模式**：
- **P1-P4 严重性徽章**：彩色药丸标签，解决 P14（视觉层级区分）
- **状态进度条**：investigating → identified → monitoring → resolved，映射到我们的 alert_state 进度
- **受影响服务芯片**：事件卡片显示"受影响来源"，解决事件详情的来源展示
- **顶部 KPI 卡片**：活跃事件数 + MTTR 指标

---

## 三、设计系统与最佳实践

### 3.1 状态/严重性设计

#### PatternFly（Red Hat）— Status & Severity
- **地址**: https://www.patternfly.org/patterns/status-and-severity

**核心原则**：
1. **状态 ≠ 严重性**：状态是系统当前状况，严重性是问题有多严重。两者用不同图标集。
2. **三元组编码**：严重性必须通过颜色 + 图标 + 文字三者传达（WCAG 合规）
3. **聚合严重性 = 最高级别胜出**：如果组件有绿/黄/红状态，整体指示器用红色
4. **3-6级严重性标度**：我们的 5 态模型（new/watch/rising/breakout/cooling）刚好适用

#### IBM Carbon Design — Status Indicator
- **地址**: https://carbondesignsystem.com/patterns/status-indicator-pattern/

**核心原则**：
1. **四种指示器变体**（按空间和关注度选择）：
   - 图标指示器（最大关注度）
   - 带数字徽章（计数重要时）
   - 无数字徽章（紧凑场景，只表示"有新内容"）
   - 形状指示器（紧凑扫描大量数据）
2. **填充 > 描边**：关键状态用填充图标，次要状态用描边
3. **认知负荷限制**：超过 5-6 个指示器开始造成负担

### 3.2 信息密度与卡片设计

#### Baymard Institute — Dashboard Card Layout
- **地址**: https://baymard.com/blog/cards-dashboard-layout

**核心原则**：
1. **卡片标题是主要扫描目标**：提供"信息气味"，标题要高可见性 + 充足留白
2. **"足够无聊"原则**：REI 的卡片仪表盘测试表现最好——一致性 > 视觉多样性
3. **显示路径而非完整信息**：摘要卡片只放标题 + 严重性指示 + 来源数，详情靠 drill-down
4. **图像/图形谨慎使用**：图片会不成比例地吸引注意力，破坏扫描对称性

#### Pencil & Paper — Dashboard UX Patterns
- **地址**: https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-dashboards

**核心原则**：
1. **四种仪表盘类型**，监控型（我们的场景）优先考虑异常检测
2. **渐进式披露**：Tooltip 隐藏第二层 → Toggle 隐藏变量 → Filter 筛选 → Drawer 钻取不丢上下文
3. **密度失调问题**：数据像一堵墙的常见失败，修复方法：视觉停顿、额外留白、减少默认显示

### 3.3 进度与实时状态

#### Nielsen Norman Group — Progress Indicators
- **地址**: https://www.nngroup.com/articles/progress-indicators/

**时间阈值指导**：
| 等待时间 | 推荐指示器 | 适用场景 |
|----------|-----------|---------|
| < 1s | 无需指示器 | 按钮状态变化 |
| 1-2s | 即时视觉反馈 | 按钮加载态 |
| 2-10s | 循环动画 | Spinner |
| > 10s | 进度完成指示器 | 进度条 + 文字说明 |

> 我们的自动化周期 10-60 秒，进度条 + 文字说明（"正在采集来源 (3/12)"）是正确模式。

**进度条心理学**：开始慢、结束快。最后 5% 卡住会让用户沮丧。

### 3.4 媒体情报特定

#### DataScouting — Media Intelligence Dashboard Must-Haves
- **地址**: https://blog.datascouting.com/en/top-must-haves-in-a-robust-media-intelligence-dashboard/

**必备要素**：
1. 跨媒体统一监控（印刷/广播/在线/社交）
2. 可视化优先：将信息量转化为可扫描的交互式图表
3. 智能查询系统：关键词过滤器消除不相关内容
4. 可自定义告警：告警必须可配置

---

## 四、React 组件与模板参考

### 4.1 设计系统组件

| 组件模式 | 推荐参考 | 地址 |
|---------|---------|------|
| 严重性告警列表 | MUI Alert (severity prop) | https://mui.com/material-ui/react-alert/ |
| 告警状态机 UI | SigNoz Alert List | https://github.com/SigNoz/signoz |
| 可展开事件卡片 | Tremor Accordion | https://tremor.so/docs/ui/accordion |
| 数据新鲜度指示 | shadcn Live Data Sync | https://shadcn.io/blocks/banner-live-data-sync |
| KPI 卡片 + Sparkline | Tremor Card + SparkChart | https://tremor.so/docs/ui/card |
| 通知中心 | Novu (@novu/react) | https://github.com/novuhq/novu |
| 运维监控仪表盘 | Ant Design Pro Monitor | https://preview.pro.ant.design/dashboard/monitor/ |
| 实时仪表盘 UX | Smashing Magazine 文章 | https://www.smashingmagazine.com/2025/09/ux-strategies-real-time-dashboards/ |

### 4.2 完整仪表盘模板

| 模板 | 技术栈 | 特点 |
|------|--------|------|
| shadcn-admin | Shadcn UI + Tailwind + Radix | 通知下拉、AlertDialog、响应式侧边栏 |
| Slash Admin | React 19 + Vite + shadcn | 10+ 页面、表单处理、Tab 导航 |
| react-admin (34k stars) | Material Design | `useNotify` + `ListGuesser` + 自动生成列表/详情 |
| Tremor Demo Dashboard | Tailwind + Radix | 35+ 组件，Card decoration + Tracker + SparkChart |
| Incident-React | React + MUI | 最简事件管理：列表 → 详情 → 操作 |

### 4.3 性能优化

| 场景 | 工具 | 说明 |
|------|------|------|
| 300+ 事件列表 | react-virtualized / react-window | 虚拟滚动，只渲染可见区域 |
| 频繁更新动画 | requestAnimationFrame | 200-400ms 值过渡，< 300ms 列表重排 |
| 大数据集渲染 | 分块加载 + Web Workers | 先骨架屏，后分批渲染 |

---

## 五、技术可行性验证

> 以下基于实际代码验证，非猜测。

### 5.0 关键结论：4 个🔴问题均无需后端改动

| 问题 | 后端数据是否已有 | 前端字段是否已有 | 需要后端改动 |
|------|:---:|:---:|:---:|
| P1 预警→事件链接 | ✅ `IntelAlert.event_id` 存在 | ✅ `types.ts:465` 已定义 | **否** |
| P7 数据新鲜度 | ✅ `FreshnessSnapshot` 完整 | ✅ `types.ts:365-375` 已定义 | **否** |
| P13 页面压缩 | ✅ 后端返回 6 预警/8 事件，前端 slice 截取 | ✅ 已有 | **否** |
| P14 视觉区分 | ✅ `alert.level` + `event.alert_state` 存在 | ✅ 已定义 | **否** |

### 5.1 数据模型详情

#### IntelAlert（前后端一致）
```typescript
// types.ts:460-478 — 前端类型
interface IntelAlert {
  id: string;
  event_id: string;              // ← P1 需要的字段，已存在
  title: string;
  level: "watch"|"rising"|"breakout"|"cooling";  // ← P14 驱动字段
  reason: string;
  triggered_at: string;
  velocity_score: number;
  coverage_score: number;
  freshness_score: number;
  composite_score: number;
  representative_link: string;
  entity_ids: string[];
  entity_names: string[];
  // ... deep dive/brief fields
}
```

#### IntelAlertHistoryItem
```typescript
// types.ts:630-645
interface IntelAlertHistoryItem {
  history_id: string;
  event_id: string;              // ← P1 也需要，已存在
  status: "active"|"source_uncertain"|"resolved";
  highest_level: "watch"|"rising"|"breakout"|"cooling";
  // ...
}
```

#### IntelEvent
```typescript
// types.ts:92-137
interface IntelEvent {
  id: string;
  alert_state: "new"|"watch"|"rising"|"breakout"|"cooling";  // ← P14 驱动字段
  change_state: "new_event"|"growing_event"|"stable_event"|"cooling_event";
  member_delta: number;          // ← 变化方向指示
  platform_delta: number;
  watchlisted: boolean;
  ignored: boolean;
  // ...
}
```

#### FreshnessSnapshot（P7 的数据源）
```typescript
// types.ts:365-375
interface FreshnessSnapshot {
  latest_collected_at?: string | null;
  latest_published_at?: string | null;
  items_1h: number;              // 1小时素材数
  items_6h: number;
  items_24h: number;
  avg_collection_lag_minutes?: number | null;
  stale_source_count: number;
  has_staleness_alert: boolean;
  last_successful_sync_at?: string | null;
}
```

#### 当前 CSS 现状

| 元素 | 类名 | padding | gap | border-radius | font-size |
|------|------|---------|-----|---------------|-----------|
| 预警/事件卡片 | `.intel-alert-card` / `.intel-event-card` | 14px | — | 8px | — |
| 卡片标题 | 卡片内 `strong` | margin 4px 0 8px | — | — | 继承 |
| 分数行 | `.intel-score-row` | — | — | — | 12px |
| 状态徽章 | `.status-badge` | 4px 10px | — | 999px | 12px/600w |
| 网格容器 | `.intel-overview-grid` / `.intel-summary-grid` | — | 18px | — | — |
| 网格列数 | — | — | — | — | `repeat(2, 1fr)` |
| 响应式断点 | `@media (max-width: 1200px)` | — | — | — | `grid-template-columns: 1fr` |

**卡片当前无 `border-left` 色条，无背景色区分。**

---

## 六、具体实现规格

### 6.1 P1：预警→事件链接

**改动范围**：纯前端，1 个文件

**文件**：`frontend/src/screens/overview/page.tsx`

**当前代码**（预警卡片，约 line 443-458）：
```tsx
<div key={alert.id} className="intel-alert-card">
  {/* ... topline, title, reason, scores ... */}
  <a href={alert.representative_link}>查看原文</a>
</div>
```

**改为**：
```tsx
<div key={alert.id} className="intel-alert-card">
  {/* ... topline, title, reason, scores ... */}
  <div className="intel-inline-actions">
    <button type="button" className="ghost-button compact"
      onClick={() => onNavigate("events")}>
      查看事件
    </button>
    <a href={alert.representative_link}>查看原文</a>
  </div>
</div>
```

**说明**：
- `alert.event_id` 已在数据中（`IntelAlert.event_id`），但当前 `onNavigate` 只接受 tab 名，不能直接跳到特定事件
- 第一版：点击"查看事件"→ 切换到 events tab（用户自己找对应事件）
- 后续增强：给 `onNavigate` 增加可选 `eventId` 参数，自动滚动到目标事件

**对历史预警卡片做同样改动**（`IntelAlertHistoryItem` 也有 `event_id`）。

### 6.2 P7：数据新鲜度指示器

**改动范围**：纯前端，2 个文件

**数据来源**：Dashboard API 已返回 `freshness: FreshnessSnapshot`，但 overview 页面当前未使用。

**文件 1**：`frontend/src/screens/overview/page.tsx`

在系统状态区域的 4 张统计卡片中，替换或增加一张"数据新鲜度"卡片：

```tsx
<div className="intel-stat-card">
  <span>数据新鲜度</span>
  <strong>
    {freshness.latest_collected_at
      ? formatRelativeTime(freshness.latest_collected_at, "暂无")
      : "未采集"}
  </strong>
  <p>
    {freshness.stale_source_count > 0
      ? `${freshness.stale_source_count} 个来源过时`
      : "全部来源正常"}
  </p>
  <p className="subtle">
    1h {freshness.items_1h} / 6h {freshness.items_6h} / 24h {freshness.items_24h}
  </p>
</div>
```

**文件 2**：`frontend/src/screens/overview/state.ts` 或 `app.tsx`

- 从 `DashboardResponse` 中提取 `freshness` 字段
- 将其作为 prop 传入 `OverviewPage`

**freshness 数据获取路径**：
```
GET /api/admin/dashboard → DashboardResponse.freshness → OverviewPage props
```

Dashboard API 已返回此数据，只需要在 overview 组件中接入。

### 6.3 P13：页面纵向压缩

**改动范围**：纯 CSS，1 个文件 + 小幅 TSX 调整

**文件 1**：`frontend/src/styles/deep-dive.css`（或 `logs.css`，取决于样式实际位置）

```css
/* 当前值 → 目标值 */
.intel-alert-card,
.intel-event-card {
  padding: 14px;        →  padding: 10px 12px;
}

.intel-overview-grid,
.intel-summary-grid {
  gap: 18px;            →  gap: 12px;
}

/* 卡片标题增加层级 */
.intel-alert-card strong,
.intel-event-card strong {
  font-size: 14px;      /* 新增，当前无显式设定 */
  line-height: 1.4;
}

/* 卡片摘要限制行数 */
.intel-alert-card p,
.intel-event-card p {
  -webkit-line-clamp: 2;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 系统摘要区改为三等列 */
.intel-summary-grid {
  grid-template-columns: repeat(2, 1fr);  →  repeat(3, minmax(0, 1fr));
}
```

**文件 2**：`frontend/src/screens/overview/page.tsx`

```tsx
// 活跃预警：slice(0, 4) → slice(0, 3)
{summary.top_alerts.slice(0, 3).map(...)}

// 历史预警：改为精简行式布局
{summary.recent_alerts_24h.slice(0, 3).map((alert) => (
  <div className="intel-history-row">
    <span className={`status-badge status-${historyStatusTone(alert.status)}`}>
      {historyStatusLabel(alert.status)}
    </span>
    <strong>{alert.title}</strong>
    <span className="subtle">{formatRelativeTime(alert.last_triggered_at, "")}</span>
  </div>
))}
```

**预估纵向压缩**：
- 预警区：4→3 张卡片 + 历史改为行式 ≈ 节省 ~300px
- 间距：gap 18→12px × 6 个间隔 ≈ 节省 ~36px
- 摘要区三列布局 ≈ 节省 ~200px（第三列不再独占一行）
- **总计：~536px，页面从 ~3000px 压缩到 ~2460px**

### 6.4 P14：预警/事件视觉区分

**改动范围**：纯 CSS，1 个文件

**文件**：`frontend/src/styles/deep-dive.css`（或相关样式文件）

```css
/* 预警卡片：左侧色条 */
.intel-alert-card {
  border-left: 4px solid transparent;
}
.intel-alert-card.severity-breakout { border-left-color: #ef4444; }
.intel-alert-card.severity-rising   { border-left-color: #f59e0b; }
.intel-alert-card.severity-cooling  { border-left-color: #94a3b8; }
.intel-alert-card.severity-watch    { border-left-color: #22c55e; }

/* 事件卡片：左侧色条 */
.intel-event-card {
  border-left: 4px solid #e5e7eb;
}
.intel-event-card.state-breakout { border-left-color: #ef4444; }
.intel-event-card.state-rising   { border-left-color: #f59e0b; }
.intel-event-card.state-watch    { border-left-color: #22c55e; }
.intel-event-card.state-new      { border-left-color: #3b82f6; }
```

**TSX 配套**：`page.tsx` 卡片 div 增加动态 class：

```tsx
// 预警卡片
<div key={alert.id} className={`intel-alert-card severity-${alert.level}`}>

// 事件卡片
<div key={event.id} className={`intel-event-card state-${event.alert_state}`}>
```

**颜色来源**：与现有 `.status-badge` 系统对齐：
- `status-danger` 背景 `#fee2e2` → 边框用 `#ef4444`（同色系更深）
- `status-warning` 背景 `#fef3c7` → 边框用 `#f59e0b`
- `status-success` 背景 `#dcfce7` → 边框用 `#22c55e`
- `status-neutral` 背景 `#f1f5f9` → 边框用 `#94a3b8`

---

## 七、依赖链与风险评估

### 7.1 实施顺序（依赖链）

```
P14 视觉区分（CSS only）
  ↓ 无依赖
P13 页面压缩（CSS + TSX slice 调整）
  ↓ P13 的行式布局会影响 P14 的色条位置，先做 P14 再做 P13
P7 数据新鲜度（TSX prop 接入）
  ↓ 无依赖，但建议在 P13 之后，利用压缩出的空间放新鲜度卡片
P1 预警→事件链接（TSX 按钮添加）
  ↓ 无依赖，最后做因为需要测试 onNavigate 的行为
```

**推荐实施顺序**：P14 → P13 → P7 → P1

### 7.2 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| P13 卡片压缩后文字截断过多 | 用户看不到完整摘要 | 中 | `-webkit-line-clamp: 2` 保证至少两行，关键信息（标题+分数）不变 |
| P14 色条与响应式断点冲突 | 1200px 以下单列时色条视觉过重 | 低 | 色条宽度在小屏降至 3px |
| P13 三列布局在 1200px 以下回退为单列 | 第三列（监控实体）仍然被推到底部 | 中 | @media 下回退为双列，第三列 span 全宽 |
| P7 freshness 数据在某些状态下为 null | 显示"未采集"或空白 | 低 | 已有空值处理 `formatRelativeTime(value, "暂无")` |
| P1 onNavigate 只切 tab 不定位事件 | 用户切到事件 tab 后要自己找 | 中 | 第一版可接受；后续加 event ID 定位 |
| P13+P14 CSS 冲突 | 两个改动都涉及 `.intel-alert-card` | 中 | 先完成 P14 的色条，再调 P13 的间距，每次改完都 build 验证 |

### 7.3 验证清单

每个改进完成后必须验证：

**P14 验证**：
- [ ] 所有 alert_state/new/watch/rising/breakout/cooling 色条颜色正确
- [ ] 1200px 以下色条正常显示
- [ ] 空状态卡片不出现色条
- [ ] `npm run build` 通过

**P13 验证**：
- [ ] 预警卡片从 4→3 后布局不破碎
- [ ] 历史预警行式布局对齐正常
- [ ] 三列 grid 在宽屏和窄屏下表现正确
- [ ] 卡片内文字截断后仍有可读性
- [ ] `npm run build` 通过

**P7 验证**：
- [ ] 未运行时 freshness 显示"未采集"而非报错
- [ ] 运行中 freshness 时间实时更新
- [ ] stale_source_count > 0 时视觉突出
- [ ] `npm run build` 通过

**P1 验证**：
- [ ] 点击"查看事件"正确切换到 events tab
- [ ] 历史预警的"查看事件"按钮同样工作
- [ ] event_id 不存在时按钮不显示或禁用
- [ ] `npm run build` 通过

### 7.4 回归风险点

以下现有功能需要在每次改动后回归测试：

1. **控制器状态条**：刚修复的进度条（`progressMeta.visible` / `meterVisible`），P13/P14 的 CSS 改动不能影响 `.intel-cycle-progress` 和 `.intel-cycle-meter`
2. **执行摘要展开/收起**：P13 的间距调整不能破坏 `.intel-runtime-summary` 的 `maxHeight` 折叠行为
3. **事件卡片操作按钮**（观察/忽略）：P14 的色条不能影响按钮的点击区域
4. **仪表盘 API 响应体积**：P7 不增加新的 API 调用，只是使用已返回的数据，无性能回归

---

## 八、推荐阅读

1. [Smashing Magazine — UX Strategies for Real-Time Dashboards](https://www.smashingmagazine.com/2025/09/ux-strategies-real-time-dashboards/) — 实时仪表盘认知负荷管理
2. [PatternFly — Status & Severity](https://www.patternfly.org/patterns/status-and-severity) — 状态/严重性设计规范
3. [IBM Carbon — Status Indicator](https://carbondesignsystem.com/patterns/status-indicator-pattern/) — 无障碍状态指示
4. [Baymard — Dashboard Card Layout](https://baymard.com/blog/cards-dashboard-layout) — 卡片一致性设计
5. [5of10 — Dashboard Design Best Practices 2025](https://5of10.com/articles/dashboard-design-best-practices) — 三层颜色系统 + 5秒测试
6. [NN/g — Progress Indicators](https://www.nngroup.com/articles/progress-indicators/) — 进度条时间阈值指导
7. [Grafana Alerting Docs](https://grafana.com/docs/grafana/latest/alerting/) — 告警状态机参考实现
8. [Tremor Demo Dashboard](https://tremor.so/docs) — 开源 React 仪表盘组件库
