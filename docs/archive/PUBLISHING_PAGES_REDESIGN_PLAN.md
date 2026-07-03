# 简报/发表记录/微信草稿箱 三页重设计 — Codex 实施方案

> 本文档由专业团队（代码探索者、产品经理、UI 设计师、前端架构师）四角色并行分析后综合产出。
> 分三个 Phase 实施，每个 Phase 独立可验收。

---

## Phase 1: 基础体验修复（骨架屏 + loading + 色值统一 + 响应式）

### 改动范围

| 文件 | 操作 | 回归风险 |
|------|------|---------|
| `frontend/src/screens/briefs/page.tsx` | 修改 | 低 — 加骨架屏 + 色值 |
| `frontend/src/screens/publish_history/page.tsx` | 修改 | 低 — 加 loading prop + 色值统一 |
| `frontend/src/screens/draft_box/page.tsx` | 修改 | 低 — 加 loading prop |
| `frontend/src/app.tsx` | 修改 | 低 — 传 loading prop |
| `frontend/src/styles/skeleton.css` | 修改 | 低 — 发表记录色值替换 |

### 步骤 1.1: 统一发表记录页的 CSS 变量为硬编码色值

在 `skeleton.css` 第 396-495 行的 `.wechat-publish-*` 样式中：

替换映射：
- `var(--text-primary, #333)` → `#111827`
- `var(--text-secondary, #999)` → `#64748b`
- `var(--text-muted, #bbb)` → `#94a3b8`
- `var(--link-color, #576b95)` → `#0f766e`
- `var(--border-color, #e8e8e8)` → `#e5e7eb`

### 步骤 1.2: 简报页添加骨架屏

在 `briefs/page.tsx` 中：
- 当 `loading && filtered.length === 0` 时渲染 skeleton（复用全局 `skeleton-list`/`skeleton-card` class）
- 参照 `watchlist/page.tsx` 的 `renderSkeleton()` 模式

### 步骤 1.3: 发表记录和草稿箱添加 loading prop

**publish_history/page.tsx**:
- Props 接口新增 `loading?: boolean`
- 当 `loading && !history` 时渲染骨架屏

**draft_box/page.tsx**:
- Props 接口新增 `loading?: boolean`
- 当 `loading && !mapping` 时渲染骨架屏

**app.tsx**:
- PublishHistoryPage 调用（约第 922-928 行）添加 `loading={Boolean(tabLoading["publish-history"])}`
- DraftBoxPage 调用（约第 930-967 行）添加 `loading={Boolean(tabLoading["draft-box"])}`

### 步骤 1.4: 响应式断点

在 `draft-box.css` 末尾添加 `@media (max-width: 768px)` 断点：
- `.draft-toolbar` 改为单列
- `.mapping-summary-grid` 改为 2 列
- `.wechat-publish-card__body` 改为纵向排列

### 验收标准
1. `npm run build` 通过
2. `npm run test -- --run` 全部通过
3. 简报页 loading 时显示骨架屏
4. 发表记录和草稿箱 loading 时显示骨架屏
5. 发表记录页无 CSS 变量残留
6. 768px 以下三个页面不溢出

---

## Phase 2: 简报页重设计

### 改动范围

| 文件 | 操作 | 回归风险 |
|------|------|---------|
| `frontend/src/screens/briefs/page.tsx` | 重写 | 中 |
| `frontend/src/styles/briefs.css` | 新建 | 无 |
| `frontend/src/styles/index.css` | 加一行 import | 无 |
| `frontend/src/screens/briefs/page.test.tsx` | 新建 | 无 |

### 步骤 2.1: 新建 `briefs.css`

从 `draft-box.css` 中将简报页专用的 class 迁出（`draft-workbench-tabs`、`draft-toolbar`、`draft-search` 等保留在 `draft-box.css` 因为被共享）。

新建的 `briefs.css` 包含：
- 卡片样式（`briefs-card`），带 `border-left: 4px` 状态色条
- 卡片内部视觉分组（标题区 / 摘要区 / 指标区 / 操作区，用 `border-top` 分隔）
- 操作按钮行用虚线 `border-top: 1px dashed #e5e7eb` 分隔

### 步骤 2.2: 重写 `page.tsx`

#### Props 接口（保持不变，28 个 prop）

#### 页面结构

```
┌─────────────────────────────────────────────────────────┐
│ panel-header: 简报/文章 / "N 篇文章"                      │
├─────────────────────────────────────────────────────────┤
│ 筛选栏: [来源: 全部|传统|Agent] + [状态: 全部|仅本地|      │
│         已同步|已发表|异常] + 搜索框 + 分页                 │
├─────────────────────────────────────────────────────────┤
│ 卡片列表 / 骨架屏 / 空状态                                │
└─────────────────────────────────────────────────────────┘
```

#### 卡片设计（统一结构）

```
┌─ 状态色条 ─────────────────────────────────────────────┐
│ [状态badge] [来源badge] [更新时间]                       │
│ 文章标题 (16px bold)                                     │
│ 一句话结论 (13px, 2行截断)                               │
│ 来源N · 事实N · 引文N · entity_tags                      │
│ ── border-top dashed ──                                 │
│ [查看详情▼] [查看原文] [同步微信] [复制] [删除]           │
│                                                         │
│ (展开区) ── border-top solid ──                         │
│ 深挖详情 / 文章正文 / 阅读数据                            │
└─────────────────────────────────────────────────────────┘
```

#### 关键改动

1. **两组 segmented control 合并为一行筛选栏**: `[来源] + [状态] + 搜索框` 在同一行
2. **卡片状态色条**: `record_status` 映射到颜色（local_only=灰, draft_synced=绿, published=蓝绿, failed=红）
3. **卡片信息分层**: 收起态只显示 标题+结论+指标+操作，详情在展开区
4. **删除操作加 `window.confirm`**: 文案 "确认删除《{title}》？此操作不可撤销。"
5. **阅读数据独立区域**: 有数据时在展开区用浅色背景区块展示
6. **骨架屏**: 复用全局 skeleton class
7. **多卡片展开**: 用 `expandedCards: Set<string>` 管理

#### 必须保持不变的逻辑

- 双维度筛选（workflowView + view）的过滤逻辑
- 分页逻辑（page/pageSize/total）
- 所有操作回调的签名和调用方式
- `onLoadBriefDetail` 的异步加载
- `creatingDailyDigest` 和 `abandoningWorkflowId` 的状态控制

### 验收标准
1. `npm run build` 通过
2. `npm run test -- --run` 全部通过（含新增测试文件）
3. 卡片有状态色条
4. 删除操作有确认弹窗
5. 骨架屏在 loading 时显示
6. 筛选栏合并为一行
7. 展开区用 border-top 分隔

---

## Phase 3: 发表记录 + 微信草稿箱重设计

### 改动范围

| 文件 | 操作 | 回归风险 |
|------|------|---------|
| `frontend/src/screens/publish_history/page.tsx` | 重写 | 低 |
| `frontend/src/screens/draft_box/page.tsx` | 重写 | 中 |
| `frontend/src/styles/publish-history.css` | 新建 | 无 |
| `frontend/src/styles/draft-box.css` | 修改 | 高（多页面共享） |
| `frontend/src/styles/index.css` | 加 import | 无 |
| `frontend/src/screens/publish_history/page.test.tsx` | 新建 | 无 |
| `frontend/src/screens/draft_box/page.test.tsx` | 新建 | 无 |

### 步骤 3.1: 新建 `publish-history.css`

从 `skeleton.css` 中将 `.wechat-publish-*` 样式迁出到独立文件。同时：
- 列表改为独立卡片 + gap（去掉 border-bottom 分隔）
- 卡片加 `border-radius: 8px`
- 统计网格从 6 格精简为 4 格（最近检查、发表条数、总阅读、最佳文章）

### 步骤 3.2: 重写发表记录 `page.tsx`

#### Props 接口
```typescript
interface PublishHistoryPageProps {
  history: WeChatPublishHistorySnapshot | null;
  refreshing: boolean;
  loading?: boolean;   // Phase 1 新增
  onRefresh: () => Promise<void>;
}
```

#### 页面结构
```
┌─────────────────────────────────────────────────────────┐
│ panel-header: 发表记录 / [刷新按钮]                       │
├─────────────────────────────────────────────────────────┤
│ 统计区: 最近检查 · 发表N条 · 总阅读 · 最佳文章             │
├─────────────────────────────────────────────────────────┤
│ 卡片列表 / 骨架屏 / 空状态                                │
└─────────────────────────────────────────────────────────┘
```

#### 卡片结构（仿微信后台但统一设计系统）
```
┌─ 独立卡片 border-radius: 8px ──────────────────────────┐
│ [缩略图 64x64]  标题                                     │
│                 阅读 1.2k · 赞 45 · 分享 12 · 留言 3      │
│                 发表于 2026-05-28                         │
└─────────────────────────────────────────────────────────┘
```

### 步骤 3.3: 重写草稿箱 `page.tsx`

#### Props 接口（保持不变，新增 loading）

#### 页面结构
```
┌─────────────────────────────────────────────────────────┐
│ panel-header: 微信草稿箱 / [刷新]                        │
├─────────────────────────────────────────────────────────┤
│ 浏览器状态栏 + 映射摘要行                                 │
│ "已匹配 12 · 仅微信 3 · 仅本地 5"                         │
├─────────────────────────────────────────────────────────┤
│ 三视图 tab: 微信端 / 本地记录 / 待确认                    │
├─────────────────────────────────────────────────────────┤
│ 卡片列表 / 骨架屏 / 空状态                                │
├─────────────────────────────────────────────────────────┤
│ 操作记录（折叠区，带背景色区分）                           │
└─────────────────────────────────────────────────────────┘
```

#### 关键改动

1. **映射摘要行**: 用 `mapping_rows` 数据显示 "已匹配 N · 仅微信 N · 仅本地 N"
2. **嵌套子面板用背景色区分**: 操作记录区用 `background: #f8fafc`
3. **三视图卡片统一结构**: 都用 topline + 标题 + 摘要 + 操作行
4. **删除远端草稿加确认**: `window.confirm("确认删除微信远端草稿《{title}》？")`
5. **待确认视图分两区**: "本地待同步" 和 "仅微信端" 分开展示

#### 必须保持不变
- `useWechatState` 的返回值签名
- 三视图切换逻辑
- 操作记录的分页
- 所有操作回调

### 验收标准
1. `npm run build` 通过
2. `npm run test -- --run` 全部通过
3. 发表记录卡片为独立圆角卡片
4. 草稿箱操作记录区有背景色区分
5. 删除远端草稿有确认弹窗
6. 两个页面都有骨架屏

---

## 全局设计规范（三个 Phase 共用）

### 状态色条颜色

| record_status | border-left 颜色 | 语义 |
|---------------|-----------------|------|
| local_only / prepared | `#94a3b8` (灰) | 仅本地 |
| draft_synced / synced | `#22c55e` (绿) | 已同步草稿箱 |
| published | `#0f766e` (蓝绿) | 已发表 |
| failed / 有 exception | `#ef4444` (红) | 异常 |

### 统一色值

| 用途 | 色值 |
|------|------|
| 主文字 | `#111827` |
| 次文字 | `#475569` |
| 辅助文字 | `#64748b` |
| 弱文字 | `#94a3b8` |
| 链接 | `#0f766e` |

### 共享 CSS class 必须保留

- `.draft-workbench-tabs`、`.draft-toolbar`、`.draft-search`、`.draft-list-block`
- `.panel`、`.panel-header`、`.status-badge`、`.ghost-button`、`.primary-button`
- `.entity-tag`、`.empty-state`、`.skeleton-list`、`.skeleton-card`

### 建议实施顺序

Phase 1 → 验收 → Phase 2 → 验收 → Phase 3 → 验收
