# 设置页 + 日志页重设计 — Codex 实施方案 v2

> 由4角色团队（探索者、产品经理、设计师、架构师）并行分析后综合产出。
> 外科手术式修复：响应式 + 骨架屏 + 样式语义修正。不重写、不改 props 接口、不碰子组件深层逻辑。

---

## 团队关键发现

| 角色 | 核心发现 |
|------|---------|
| 探索者 | 设置页 356 行 + 5 子组件（73 props）；日志页 280 行（11 props）。日志样式在 `sources.css:88-267`，不在 `logs.css` |
| 产品经理 | P0：LLM 测试结果脱离被测卡片、日志搜索无防抖。P1：6 宫格 tab 窄屏溢出、级别筛选无数量 |
| 设计师 | 两页均 2.8/5 分。搜索栏借用 `.draft-toolbar` 语义错误；`runtime_plan_panel` 用了 3 个不存在的 CSS class |
| 架构师 | 73 props 接口不可变；设置 loading 未传；日志 loading 已传但未消费为 skeleton；tab 用 inline style 覆盖 CSS |

---

## 改动范围

| 文件 | 操作 | 回归风险 |
|------|------|---------|
| `frontend/src/styles/settings.css` | 修改 | 低 — 加响应式断点 + 补缺失 class |
| `frontend/src/styles/sources.css` (行88-267) | 修改 | 低 — 加日志行响应式断点 |
| `frontend/src/screens/settings/page.tsx` | 修改 | 低 — 移除 inline style + 加 skeleton |
| `frontend/src/screens/settings/runtime_plan_panel.tsx` | 修改 | 低 — 替换不存在的 CSS class |
| `frontend/src/screens/logs/page.tsx` | 修改 | 低 — 加 skeleton + 搜索栏改 class |
| `frontend/src/app.tsx` | 修改 | 低 — 给 SettingsPage 传 loading prop |
| `frontend/src/screens/settings/page.test.tsx` | 新建 | 无 |
| `frontend/src/screens/logs/page.test.tsx` | 扩展 | 无 |

**不动**: `llm_panel.tsx`、`sources_panel.tsx`、`browser_section.tsx`、`reference_panel.tsx`、所有 `state.ts`

---

## 步骤 1：设置页响应式

### 1a. 移除 page.tsx 中 segmented-control 的 inline style

文件：`frontend/src/screens/settings/page.tsx`

找到 segmented-control 的 inline style：
```tsx
style={{ gridTemplateColumns: "repeat(6, minmax(0, 1fr))" }}
```
删除此 inline style，改用 CSS class `.settings-sections` 控制。

### 1b. 在 settings.css 末尾添加响应式断点

```css
/* Settings responsive */
.settings-sections {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

@media (max-width: 900px) {
  .settings-sections {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .llm-workbench {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 540px) {
  .settings-sections {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
```

---

## 步骤 2：日志页响应式

文件：`frontend/src/styles/sources.css`（日志样式在行 88-267，不是 logs.css）

在 sources.css 中找到 `.log-plain-row` 的 grid 定义，在其后添加响应式断点：

```css
@media (max-width: 768px) {
  .log-plain-row {
    grid-template-columns: 1fr;
    gap: 2px 0;
  }
  .log-plain-time,
  .log-plain-level,
  .log-plain-cat {
    display: inline;
    font-size: 11px;
    margin-right: 8px;
  }
  .runtime-card-grid {
    grid-template-columns: 1fr;
  }
}
```

---

## 步骤 3：设置页 loading skeleton

### 3a. page.tsx 添加 loading prop 和 skeleton

文件：`frontend/src/screens/settings/page.tsx`

1. 在 `SettingsPageProps` 接口中添加可选 prop：
   ```typescript
   loading?: boolean;
   ```
   注意：添加到接口末尾，不修改现有 props。

2. 在组件函数参数中解构：`loading = false`

3. 在 segmented-control 和内容区域之间，当 `loading` 为 true 时渲染 skeleton：
   ```tsx
   {loading && (
     <div className="skeleton-list">
       <div className="skeleton-card" style={{ height: 120 }} />
       <div className="skeleton-card" style={{ height: 80 }} />
       <div className="skeleton-card" style={{ height: 160 }} />
     </div>
   )}
   {!loading && (
     // 现有的 section 内容渲染
   )}
   ```

### 3b. app.tsx 传递 loading prop

文件：`frontend/src/app.tsx`

在 SettingsPage 组件调用处（约行 971-1009），添加：
```tsx
loading={Boolean(tabLoading.settings)}
```

---

## 步骤 4：日志页 loading skeleton

文件：`frontend/src/screens/logs/page.tsx`

`loading` prop 已存在（默认 `false`），但目前只透传给 `PaginationControls`。

在日志列表区域，当 `loading && filteredLogs.length === 0` 时渲染 skeleton：
```tsx
{loading && filteredLogs.length === 0 && (
  <div className="skeleton-list">
    <div className="skeleton-card" style={{ height: 40 }} />
    <div className="skeleton-card" style={{ height: 40 }} />
    <div className="skeleton-card" style={{ height: 40 }} />
    <div className="skeleton-card" style={{ height: 40 }} />
    <div className="skeleton-card" style={{ height: 40 }} />
  </div>
)}
```

注意：放在日志列表区域（系统日志和信息源日志的空判断处），不要放在整个页面外层。

---

## 步骤 5：日志页搜索栏改用独立样式

### 5a. logs/page.tsx 修改搜索栏 class

文件：`frontend/src/screens/logs/page.tsx`

找到搜索栏区域的 `.draft-toolbar` 和 `.draft-search` class，替换为：
- `.draft-toolbar` → `.logs-search-bar`
- `.draft-search` → `.logs-search`

### 5b. sources.css 添加搜索栏样式

在 sources.css 中（日志样式区域附近）添加：

```css
.logs-search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.logs-search-bar input {
  flex: 1;
  min-width: 200px;
  min-height: 32px;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #ffffff;
  color: #111827;
  font-size: 13px;
}

.logs-search-bar input:focus {
  outline: none;
  border-color: #6366f1;
}
```

---

## 步骤 6：runtime_plan_panel 修复不存在的 CSS class

文件：`frontend/src/screens/settings/runtime_plan_panel.tsx`

替换 3 个不存在的 CSS class：
- `settings-form-grid` → `intel-plan-grid`
- `settings-form-actions` → `intel-plan-footer`
- `settings-runtime-status` → `intel-runtime-section`

这些 class 已在 `intel.css` 中定义，替换后视觉一致且样式生效。

---

## 步骤 7：新增测试

### 7a. settings/page.test.tsx（新建）

```typescript
// 测试内容：
// 1. 默认渲染 AI 模型 section
// 2. 6 个 tab 切换渲染
// 3. loading skeleton 显示/隐藏
// 4. 各子面板在对应 section 下渲染
```

mock 必需的 73 个 props（使用工厂函数生成默认值），重点验证：
- 初始渲染不报错
- tab 切换内容区变化
- loading=true 时显示 skeleton，loading=false 时显示内容

### 7b. 扩展 logs/page.test.tsx（在 LogsPanel.test.tsx 中）

在现有 4 个回调测试基础上增加：
- loading skeleton 显示/隐藏
- level filter chip 切换
- 搜索框输入触发 onSearchChange

---

## 验收标准

1. `cd auto-news-studio/frontend && npm run build` 通过
2. `cd auto-news-studio/frontend && npm run test -- --run` 全部通过
3. 设置页 6 列 tab 在 900px 以下变为 3 列，540px 以下变为 2 列
4. 设置页 LLM 双栏在 900px 以下变为单栏
5. 日志页日志行在 768px 以下变为单列堆叠
6. 设置页有 loading skeleton
7. 日志页有 loading skeleton
8. 日志搜索栏使用 `.logs-search-bar` 而非 `.draft-toolbar`
9. runtime_plan_panel 不再有未定义的 CSS class
10. 所有 props 接口不变（SettingsPage 仅有新增可选 `loading?`，LogsPage 不变）

---

## Codex 实施约束

1. **Props 接口**：SettingsPage 只能在末尾新增 `loading?: boolean`；LogsPage 不做任何修改
2. **不碰 state.ts**：`useSettingsState` 和 `useLogsState` 返回接口不可改
3. **不碰子组件**：llm_panel、sources_panel、browser_section、reference_panel 不改
4. **CSS 文件位置**：日志样式在 `sources.css:88-267`，不是 `logs.css`
5. **skeleton class**：复用全局 `skeleton-list` 和 `skeleton-card`
6. **Re-export 保持**：`components/LogsPanel.tsx` 的 re-export 不动
7. **app.tsx 闭包**：logs 的 `onPageChange` 内联闭包管理 `setTabLoading`，不要改其签名
