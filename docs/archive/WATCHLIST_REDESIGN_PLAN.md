# 深挖池（Watchlist）页面重设计 — Codex 实施方案

> 本文档由专业团队（代码探索者、产品经理、UI 设计师、前端架构师）四角色并行分析后综合产出。

## 改动范围

| 文件 | 操作 | 回归风险 |
|------|------|---------|
| `frontend/src/screens/watchlist/page.tsx` | 重写 | 中（主战场） |
| `frontend/src/styles/watchlist.css` | 新建 | 无 |
| `frontend/src/styles/index.css` | 加一行 import | 无 |
| `frontend/src/app.tsx`（第 859-868 行） | 加 `loading` prop | 无 |
| `frontend/src/screens/watchlist/page.test.tsx` | 新建 | 无 |

**不动**: `state.ts`、`useAppShellState.ts`、`types.ts`、`skeleton.css`

---

## 步骤一：新建 `watchlist.css` 并在 `index.css` 引入

在 `frontend/src/styles/` 下新建 `watchlist.css`，在 `index.css` 中加 `@import "./watchlist.css";`（放在 `logs.css` 之后）。

CSS 内容参考 `source-health.css` 的模式（stat 卡片 + filter 栏 + card grid + severity 边框），class 命名用 `watchlist-` 前缀。

---

## 步骤二：重写 `page.tsx`

### 2.1 Props 接口（必须保持向后兼容）

```typescript
interface WatchlistPageProps {
  items: IntelEvent[];
  selectedDeepDive: EventDeepDive | null;
  busyEventId?: string | null;
  loading?: boolean;                    // 新增可选，默认 false
  onDeepDive: (eventId: string, force?: boolean) => Promise<void>;
  onCreateBrief: (eventId: string) => Promise<void>;
  onOpenDeepDive: (eventId: string) => Promise<void>;
}
```

### 2.2 页面结构（从上到下）

```
┌─────────────────────────────────────────────────────────┐
│ panel-header: 深挖池 / 先拿到正文... / "N 个事件"       │
├─────────────────────────────────────────────────────────┤
│ watchlist-stats: 4 个 stat 卡片                         │
│   [待深挖 3] [已深挖 5] [往日待深挖 2] [往日已深挖 8]   │
│   点击切换 activeSection，不再有 filter-chip 行          │
├─────────────────────────────────────────────────────────┤
│ watchlist-filter-bar: 搜索框 + "一键深挖"按钮(可选)     │
├─────────────────────────────────────────────────────────┤
│ watchlist-grid: 卡片列表（或 skeleton / 空状态）         │
└─────────────────────────────────────────────────────────┘
```

### 2.3 卡片设计（收起态 vs 展开态）

**收起态**（决策扫描用，只显示必需信息）：
```
┌─ severity 色条 ──────────────────────────────────────┐
│ [status badge]  平台/来源/素材数                      │
│ 事件标题 (16px bold)                                  │
│ [值得交付✓]  [3个实体标签...]                          │
│ 深挖更新 · 3小时前                                    │
│ [查看详情▼]  [查看原文]  [重新深挖]  [生成简报]       │
└──────────────────────────────────────────────────────┘
```

**展开态**（深挖详情）：
```
┌─ 上同 ───────────────────────────────────────────────┐
│ ─── border-top 分隔 ─────────────────────            │
│ 深挖详情                    3/5 来源成功             │
│ 完整正文 2 篇 · 事实 5 条 · 引文 3 条                │
│ 核心事实: ...                                         │
│ 来源明细: ...                                         │
│ 正文预览: ...                                         │
│ [收起来源▲]                                           │
└──────────────────────────────────────────────────────┘
```

### 2.4 关键改动点

1. **移除 filter-chip 行**: stat 卡片独占分组切换功能
2. **移除 section-head**: 去掉 h3+description 重复区
3. **卡片两段式**: 收起态精简（标题+评估+状态），展开态显示摘要+详情
4. **移除 `window.confirm`**: "生成简报"改为直接调用（LLM 消耗已在操作语义中）
5. **多卡片展开**: 用 `expandedCards: Set<string>` 管理展开状态（类似 source-health 的 `expandedSources`）
6. **severity 色条**: 按深挖状态着色卡片左边框（ready=绿, partial=黄, failed=红, pending=灰）
7. **评估徽章**: `worth_to_brief` 显示为显眼的绿色/黄色小标签，嵌入卡片标题行下方
8. **加载骨架屏**: `loading && !items.length` 时显示 `skeleton-list`（复用 `skeleton.css` 全局 class）
9. **搜索过滤**: 添加 `searchTerm` state，搜索标题/摘要/实体名
10. **空状态区分**: 按分组和搜索状态显示不同提示文案

### 2.5 必须保持不变的逻辑

- `classifySection()` 四分组分类函数
- `pickActivityTime()` 时间选择逻辑
- `hasCompletedDeepDive()` 判断函数
- `SECTION_META` 常量数组（增加 `emptyHint` 字段即可）
- `statusTone()` 颜色映射函数
- 排序逻辑（按活动时间倒序）

### 2.6 必须复用的共享 CSS class

- `.panel`, `.panel-header`, `.panel-header.compact`
- `.eyebrow`, `.subtle`
- `.ghost-button`, `.ghost-button.compact`
- `.primary-button`, `.primary-button.compact`
- `.status-badge`, `.status-badge-compact`, `.status-success/warning/danger/neutral`
- `.entity-tag`, `.entity-tag-muted`
- `.empty-state`
- `.skeleton-list`, `.skeleton-card`, `.skeleton-line`, `.skeleton-short/medium/long`

---

## 步骤三：修改 `app.tsx` 传递 loading prop

在第 859-868 行的 `<WatchlistPage>` 调用中添加：

```tsx
loading={Boolean(tabLoading.watchlist)}
```

其他代码不变。

---

## 步骤四：新建测试 `page.test.tsx`

参照 `screens/source_health/page.test.tsx` 的模式，覆盖：
- 统计卡片渲染 + 分组数量
- 搜索过滤
- 空状态文案（按分组区分）
- skeleton 在 loading 时显示
- 事件卡片操作按钮

---

## 样式规范

### Severity 颜色（与 source-health 一致）

| 状态 | border-left 颜色 | 背景色 |
|------|-----------------|--------|
| ready | `#22c55e` | `#ffffff` |
| partial | `#f59e0b` | `rgba(245, 158, 11, 0.04)` |
| failed | `#ef4444` | `rgba(239, 68, 68, 0.04)` |
| pending | `#94a3b8` | `#ffffff` |

### 字号规范

| 元素 | 字号 |
|------|------|
| 卡片标题 | 16px bold |
| 卡片摘要 | 13px |
| meta（平台/来源数） | 12px |
| 评估标签 | 12px |
| 时间行 | 12px |
| stat 数值 | 20px bold |
| stat 标签 | 11px |

### 卡片内部间距分层

- 标题区（header → 标题）：6px gap
- 元数据区（标签 → 评估）：6px gap
- 操作区（时间 → 按钮）：10px gap（用 border-top 虚线分隔）

---

## 验收标准

1. `cd auto-news-studio/frontend && npm run build` 通过
2. `cd auto-news-studio/frontend && npm run test -- --run` 全部通过
3. 页面加载时显示 skeleton 骨架屏
4. stat 卡片点击切换分组
5. 搜索框过滤标题/摘要/实体名
6. 卡片按 severity 着色左边框
7. 展开详情使用 border-top 分隔，不使用 inline style marginTop
8. 空状态文案按分组区分
9. 不再使用 `window.confirm`
