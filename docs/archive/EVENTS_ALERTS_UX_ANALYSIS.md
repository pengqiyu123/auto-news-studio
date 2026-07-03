# 热点簇与预警台 UX 评审报告

> 评审日期：2026-05-28
> 方法：跨职能团队分析（产品经理 + 运营专员 + 设计专家）
> 范围：热点簇（Events）、预警台（Alerts），含与实时流（Stream）的衔接关系
> 前序文档：[OVERVIEW_UX_RESEARCH.md](./OVERVIEW_UX_RESEARCH.md)、[STREAM_UX_ANALYSIS.md](./STREAM_UX_ANALYSIS.md)

---

## 一、三界面管线定位

```
实时流 (DiscoveryItem)  →  热点簇 (IntelEvent)  →  预警台 (IntelAlert)
  "进了什么"                "什么在涨"               "要做什么"
  原始素材                   聚合事件                  行动信号
```

| 界面 | 核心问题 | 用户角色 | 关键操作 |
|---|---|---|---|
| **热点簇** | 现在有什么在发生？ | 编辑做"巡览"扫描全景 | 深挖/加入深挖池/忽略 |
| **预警台** | 我现在需要做什么？ | 编辑的"待办队列" | 确认关注/深挖/忽略 |

### 角色定位建议

- **热点簇 = 雷达全景**：覆盖广度、聚合质量、趋势方向。所有事件的全景视图 + 关联预警状态
- **预警台 = 行动队列**：紧迫程度、行动选项、决策效率。按严重性分组 + 每个预警关联事件摘要

### 当前定位问题

1. 热点簇和预警台展示的事件高度重叠，信息展示方式不同，用户需要两边都看
2. 预警台缺少行动导向——更像"另一个事件列表"而非"待办队列"
3. 热点簇缺少预警上下文——alert_state 有但看不到预警触发历史

---

## 二、问题清单

### P0 — 必须修（功能缺陷 / 数据正确性）

#### P0-1：热点簇客户端过滤 vs 后端分页矛盾

**现象**：`selectedEntityId` 过滤和 7 种排序只作用于当前页 20 条 items。页面承认"热点簇筛选和排序当前按本页数据生效"。

**与实时流同类**：需要后端 API `GET /api/admin/intel/events` 增加 `entity_id`、`sort_by` 等参数。

**涉及文件**：
- 后端：`backend/app/routes/intel.py`（events 路由）、`backend/app/store_mixins/intel_mixin.py`（`list_intel_events`）
- 前端：`frontend/src/screens/events/page.tsx`（过滤逻辑 97-111 行）

#### P0-2：跨 tab 导航完全断裂

**现象**：三个界面之间无任何交叉链接。数据关系已有（IntelAlert.event_id、IntelEvent.discovery_item_ids），但 UI 无跳转。

| 导航方向 | 是否存在 | 关键数据 |
|----------|----------|---------|
| 预警→热点簇 | 不存在 | `alert.event_id` 已有 |
| 热点簇→预警台 | 不存在 | `event.alert_state` 已有 |
| 热点簇→实时流 | 不存在 | `event.discovery_item_ids` 已有 |
| 实时流→热点簇 | 不存在 | 素材无反向关联 |

**根因**：app.tsx 的 tab 切换不支持带上下文参数（如 `setActiveTab("events", { eventId })` ）。

**修复**：建立 `navigateToTab(tab, context?)` 机制，支持传递 eventId/entityId。

#### P0-3：预警卡片展示 reason 而非 summary

**现象**：`alert.reason` 是系统级预警触发原因（如"速度得分突破阈值 3.2"），对用户无意义。用户需要的是事件摘要。但 `IntelAlert` 没有 `summary` 字段。

**修复**：后端在构建 IntelAlert 时从关联 IntelEvent 复制 `summary` 字段到 alert，前端优先展示 summary。

**涉及文件**：
- 后端：`backend/app/store_mixins/intel_mixin.py`（alert 构建逻辑）
- 前端：`frontend/src/screens/alerts/page.tsx`（卡片内容）

#### P0-4：预警台 breakout 用 inline style 而非 CSS class

**现象**：`alerts/page.tsx:132` 用 `style={{ borderLeft: "3px solid var(--color-danger)", background: "rgba(239,68,68,0.04)" }}` 。`--color-danger` CSS 变量不存在，靠 fallback 生效。其他级别无色条。

**修复**：删除 inline style，统一用 CSS class `severity-*` 系统。

#### P0-5：热点簇卡片无色条

**现象**：用 `intel-row-card` class，无 border-left 色条。总览页有完整的 `state-*` 色条系统但热点簇页没复用。

**修复**：给 `intel-row-card` 增加 `severity-${alert_state}` class + 对应 CSS 规则。

#### P0-6：预警台摘要行 inline style

**现象**：`alerts/page.tsx:126` 用 `style={{ marginBottom: "0.5rem", opacity: 0.7 }}`。

**修复**：改为 CSS class，增加视觉权重。

---

### P1 — 应该修（体验 / 效率）

#### P1-1：预警台无"查看事件"按钮

`IntelAlert.event_id` 已有但卡片没有跳转链接。修复需 P0-2 的跨 tab 导航机制。

#### P1-2：预警无分组展示

breakout/rising/watch/cooling 混在平铺列表。默认"全部"视图下 breakout 可能被埋在列表底部。

**建议**：按严重性分组 + 可折叠区域 + breakout 默认展开。

#### P1-3：预警无"确认已关注"中间态

当前只有"深挖"一个出口。运营大多数决策是"看到了，不处理"，需要 PagerDuty 式的 acknowledged 状态。

#### P1-4：热点簇双 PaginationControls

page.tsx 第 169 行和第 254 行各一个。保留底部一个即可。

#### P1-5：预警台 entityOptions 缺少 entityWatchlist 兜底

alerts/page.tsx 第 47-56 行只从当前 items 推导，热点簇额外从 entityWatchlist 补充（90-93 行）。预警台遗漏了。

#### P1-6：热点簇排序 7 个 chip 太多

总分/速度/覆盖/新鲜/成员增量/平台增量/最新出现。建议 4 主 chip + select 扩展排序。

#### P1-7：跨界面设计不一致

- 色条系统三套标准（总览页 CSS class、预警台 inline style、热点簇无色条）
- 卡片结构顺序有差异（entity-tags 位置、score-row 内容）
- 过滤栏概念混淆（热点簇 chip 是排序、预警台 chip 是过滤，视觉相同）

---

### P2 — 建议修（代码质量 / 锦上添花）

#### P2-1：24h 历史区代码重复

events/alerts 两个界面的历史区（filter chips、卡片、"加载更多"）几乎一模一样。应提取为共享 `HistorySection` 组件。

#### P2-2：热点簇展开/收起按钮不够显眼

`ghost-button compact` + `fontSize: 12` 太轻量，容易错过。

#### P2-3：操作按钮拥挤

热点簇 4 个按钮一行（查看原文+深挖池+忽略+深挖），应分主要/次要两组。

#### P2-4：热点簇无关联预警 badge

事件卡片上看不到该事件触发了什么级别的预警。`alert_state` 有但缺少预警触发次数和最近触发时间。

#### P2-5：预警升级路径不可见

一个事件从 watch→rising→breakout 的升级过程看不到。IntelAlertHistoryItem 有 highest_level/latest_level 但只用在历史区。

---

## 三、优化方向

### 方向 A：后端 API 过滤参数（解决 P0-1）

与实时流同类修复。给 `GET /api/admin/intel/events` 增加 `entity_id`、`sort_by` 参数。

**涉及文件**：
- `backend/app/routes/intel.py`（events 路由参数）
- `backend/app/store_mixins/intel_mixin.py`（`list_intel_events` 过滤逻辑）
- `frontend/src/screens/events/page.tsx`（过滤改为后端调用）
- `frontend/src/screens/events/state.ts`（state hook 传参）

### 方向 B：跨 tab 导航机制（解决 P0-2、P1-1）

在 app.tsx 中增加 `navigateToTab(tab, context?)` 函数，支持传递 `eventId`、`entityId`。

1. 预警卡片增加"查看事件"按钮 → 跳转热点簇并定位事件
2. 热点簇卡片增加"查看预警"链接 → 跳转预警台并筛选
3. 热点簇 → 实时流（按 discovery_item_ids 过滤）可后续增强

**涉及文件**：
- `frontend/src/app.tsx`（导航机制）
- `frontend/src/screens/alerts/page.tsx`（"查看事件"按钮）
- `frontend/src/screens/events/page.tsx`（"查看预警"链接）

### 方向 C：预警台 UI 重构（解决 P0-3/4/6、P1-2/3/5）

1. 后端 IntelAlert 增加 `summary` 字段
2. 删除 breakout inline style，统一用 CSS class
3. 摘要行改 CSS class + 增加视觉权重
4. 按严重性分组展示（breakout 默认展开，其余可折叠）
5. 增加统计条（可点击过滤）
6. entityOptions 补充 entityWatchlist

**预警台设计草图**：

```
┌──────────────────────────────────────────────────────┐
│ 预警台 · 上升中和爆发中的热点事件                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│  [ 3 爆发 ]  [ 5 上升 ]  [ 3 关注 ]  [ 1 冷却 ]      │  ← 可点击过滤的统计条
│                                                      │
│  ● 爆发 (3)                                       ▼  │  ← 可折叠分组头
│  ┌─[红色色条 5px]─────────────────────────────────┐   │
│  │  [breakout] 2分钟前                            │   │
│  │  事件摘要（用户可读内容）                        │   │
│  │  速度 0.8  覆盖 0.6  3 平台                    │   │
│  │  [查看事件]  [查看原文]  [立即深挖]             │   │
│  └───────────────────────────────────────────────┘   │
│                                                      │
│  ● 上升 (5)                                       ▶  │  ← 默认折叠（>3条时）
│                                                      │
│  24h 内已发现预警 ...                                 │
└──────────────────────────────────────────────────────┘
```

### 方向 D：统一色条系统（解决 P0-4/5、P1-7）

为 `intel-row-card` 增加 severity class，替代所有 inline style：

```css
.intel-row-card { border-left: 4px solid #e5e7eb; }
.intel-row-card.severity-breakout { border-left-color: #ef4444; background: rgba(239,68,68,0.03); }
.intel-row-card.severity-rising   { border-left-color: #f59e0b; }
.intel-row-card.severity-watch    { border-left-color: #22c55e; }
.intel-row-card.severity-cooling  { border-left-color: #94a3b8; }
.intel-row-card.severity-new      { border-left-color: #3b82f6; }
```

**涉及文件**：
- `frontend/src/styles/logs.css`（CSS 规则）
- `frontend/src/screens/events/page.tsx`（卡片 class）
- `frontend/src/screens/alerts/page.tsx`（删 inline style + 卡片 class）

### 方向 E：热点簇体验优化（解决 P1-4/6、P2-2/3）

1. 删除顶部重复的 PaginationControls
2. 排序 7 chip → 4 主 chip + select 扩展排序
3. 展开按钮视觉增强（颜色 + 箭头图标）
4. 操作按钮分主要/次要两组

---

## 四、实施优先级

```
方向 A（后端 API 过滤）      ← 第一步，同实时流的 P0 修复
  ↓
方向 D（统一色条系统）       ← 第二步，纯 CSS + TSX class 改动
  ↓
方向 B（跨 tab 导航）        ← 第三步，需要 app.tsx 架构改动
  ↓
方向 C（预警台 UI 重构）     ← 第四步，依赖方向 B 的导航机制
  ↓
方向 E（热点簇体验优化）     ← 第五步，独立优化
```

### 分批建议

**第一批**（阻断性问题）：A + D — 后端过滤 + 色条统一
**第二批**（核心链路打通）：B — 跨 tab 导航 + 预警→事件跳转
**第三批**（预警台工作流完善）：C — 分组/统计条/summary/确认关注
**第四批**（体验打磨）：E — 排序精简/去重分页/按钮分组/共享组件

---

## 五、验证清单

### 方向 A 验证
- [ ] 后端 API 支持 entity_id/sort_by 参数
- [ ] 前端过滤调用后端 API
- [ ] 实体筛选结果跨分页完整
- [ ] `npm run build` + `python -m compileall` 通过

### 方向 D 验证
- [ ] 热点簇和预警台卡片色条颜色正确
- [ ] 无 inline style 残留
- [ ] 1200px 以下色条正常
- [ ] `npm run build` 通过

### 方向 B 验证
- [ ] 预警卡片"查看事件"跳转到热点簇
- [ ] 跳转后目标事件可见（理想：自动展开/高亮）
- [ ] `npm run build` 通过

### 方向 C 验证
- [ ] 预警卡片展示 summary 而非 reason
- [ ] 分组展示 breakout/rising/watch/cooling
- [ ] 统计条可点击过滤
- [ ] entityOptions 包含 entityWatchlist
- [ ] `npm run build` 通过

### 回归风险点
1. 总览页色条不受影响（使用 intel-alert-card/intel-event-card，非 intel-row-card）
2. 实时流过滤/排序不受影响
3. 深挖/加入深挖池/忽略按钮功能正常
4. EntityWatchlistPanel 侧边栏正常
5. API 响应体积不因新参数显著增大
