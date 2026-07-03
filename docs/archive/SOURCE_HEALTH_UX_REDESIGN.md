# 来源健康页面 UX 重新设计报告

> 评审日期：2026-05-28
> 方法：跨职能团队分析（产品经理 + 设计专家）
> 定位：从功能逻辑升级为用户级产品设计
> 前序文档：总览页 / 实时流 / 热点簇+预警台 UX 报告

---

## 一、当前问题

页面 143 行，纯功能堆砌无设计：

| 问题 | 影响 |
|---|---|
| 所有来源平铺无分组，健康/异常视觉权重相同 | 巡检需滚完全列表才能确认无问题 |
| 没有全局健康概览 | 看不到"几个正常/几个异常" |
| 搜索只有关键词，不能按状态/平台筛选 | 无法快速聚焦问题来源 |
| 展开后 9 个数据点一次性显示 | 信息过载无优先级 |
| 卡片无色条区分 | 与总览/热点簇/预警台的 severity 系统不一致 |
| 单列列表浪费横向空间 | 10+ 来源时滚动距离长 |
| 搜索框样式与过滤栏不一致 | 用 draft-toolbar 而非 intel-filter-bar |
| "补抓"术语不友好 | 用户不知道什么是"补抓" |
| 没有来源添加/删除入口 | 管理来源需跳 Settings 页 |

---

## 二、重新设计

### 页面布局

```
┌──────────────────────────────────────────────────────────┐
│ 来源健康 · 数据源状态监控              [全部重新抓取]      │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  [ 12 正常 ]  [ 2 告警 ]  [ 1 异常 ]  [ 3 停用 ]         │  ← 可点击过滤的统计卡
│                                                          │
├──────────────────────────────────────────────────────────┤
│ [全部] [正常] [告警] [异常] [停用]   [平台 ▾]   [🔍 搜索] │  ← 统一过滤栏
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─[绿色色条]─────────────────┐ ┌─[红色色条]───────────┐  │
│  │ ● 正常   RSS · 每小时      │ │ ● 异常   API · 每30分│  │
│  │ OpenAI Blog                │ │ Hacker News          │  │
│  │ 上次成功: 3分钟前 · 2 条    │ │ 连续失败 3 次         │  │
│  │ 耗时 1.2s (avg 1.5s)       │ │ 耗时 8.3s · 0 条     │  │
│  │ [重新抓取] [停用] [打开→]   │ │ [重新抓取] [停用]    │  │
│  └───────────────────────────┘ └─────────────────────┘  │
│                                                          │
│  ┌─[橙色色条]─────────────────┐ ┌─[灰色色条]───────────┐  │
│  │ ● 告警   RSS · 每小时      │ │ ● 停用   热榜        │  │
│  │ arXiv CS.AI                │ │ Weibo 热搜            │  │
│  │ 上次成功: 7h前 · 5 条      │ │ 已停用                │  │
│  │ 耗时 3.2s (avg 2.1s)       │ │ 累计 342 条           │  │
│  │ [重新抓取] [停用] [打开→]   │ │ [启用] [打开→]       │  │
│  └───────────────────────────┘ └─────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 卡片设计（收起状态，无需展开即可判断）

```
┌─4px severity bar──┐
│ ● [正常]  RSS  ·  每小时  ·  权重 8
│ 来源名称 (bold, 15px)
│ 上次成功: 3分钟前 · 累计 1,247 条
│ 耗时 1.2s (avg 1.5s) · 最近 23 条
│ [重新抓取] [停用] [打开来源→]
└───────────────────┘
```

展开后只显示额外诊断信息：
- 精确时间戳（最近成功/失败时间）
- health_detail 错误文本
- 连续失败次数（异常时高亮）

### 排序规则

error 在前（按 consecutive_failures 降序）→ warning → healthy（按最后同步时间降序）→ idle

---

## 三、设计规格

### 统计卡

复用预警台 `alert-stats-row` / `alert-stat` 模式：

```css
.source-health-stats { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.source-health-stat { display: flex; flex-direction: column; align-items: center; min-width: 64px; padding: 8px 18px; border-radius: 8px; background: #f8fafc; border: 1px solid #e5e7eb; cursor: pointer; }
.source-health-stat-active.stat-healthy { background: #f0fdf4; border-color: #bbf7d0; }
.source-health-stat-active.stat-warning { background: #fffbeb; border-color: #fde68a; }
.source-health-stat-active.stat-error { background: #fef2f2; border-color: #fecaca; }
.source-health-stat-active.stat-idle { background: #f8fafc; border-color: #e2e8f0; }
.source-health-stat-value { font-size: 20px; font-weight: 700; color: #111827; }
.source-health-stat-label { font-size: 11px; color: #64748b; margin-top: 2px; }
```

### 卡片网格

```css
.source-health-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
.source-health-card { border: 1px solid #dbe3ef; border-radius: 8px; border-left: 4px solid #e5e7eb; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }
.source-health-card.severity-healthy { border-left-color: #22c55e; }
.source-health-card.severity-warning { border-left-color: #f59e0b; background: rgba(245,158,11,0.03); }
.source-health-card.severity-error { border-left-color: #ef4444; background: rgba(239,68,68,0.03); }
.source-health-card.severity-idle { border-left-color: #94a3b8; }
@media (max-width: 768px) { .source-health-grid { grid-template-columns: 1fr; } }
```

### 过滤栏

复用 `intel-chip-filter-bar` + `filter-chip`，增加平台下拉。

### 术语修正

| 当前 | 改为 |
|---|---|
| 补抓 | 重新抓取 |
| 全部补抓一次 | 全部重新抓取 |

### 视觉一致性

与总览/热点簇/预警台统一：
- 左侧色条：`severity-*` 系统
- 状态徽章：`status-badge` + `status-success/warning/danger/neutral`
- 过滤 chip：`filter-chip` / `filter-chip-active`
- 面板容器：`section.panel` + `panel-header.compact`

---

## 四、TSX 改动要点

### 新增 state

```typescript
const [statusFilter, setStatusFilter] = useState<"all"|"healthy"|"warning"|"error"|"idle">("all");
const [platformFilter, setPlatformFilter] = useState("all");
```

### useMemo 增强

```typescript
const filteredSources = useMemo(() => {
  let result = sources;
  // 状态筛选
  if (statusFilter !== "all") result = result.filter(s => {
    if (statusFilter === "idle") return !s.enabled || s.health_status === "idle";
    return s.enabled && s.health_status === statusFilter;
  });
  // 平台筛选
  if (platformFilter !== "all") result = result.filter(s => s.platform === platformFilter);
  // 搜索
  if (searchTerm.trim()) { ... }
  // 排序：error→warning→healthy→idle
  return [...result].sort((a, b) => {
    const rank = { error: 0, warning: 1, healthy: 2, idle: 3 };
    return (rank[a.health_status] ?? 2) - (rank[b.health_status] ?? 2);
  });
}, [sources, statusFilter, platformFilter, searchTerm]);
```

### 布局结构

```tsx
<section className="panel">
  <div className="panel-header compact">...</div>
  <div className="source-health-stats">
    {/* 4 个可点击统计卡 */}
  </div>
  <div className="source-health-filter-bar">
    <div className="intel-chip-row">
      {/* 状态 filter-chip 按钮 */}
    </div>
    <div className="source-health-filter-tools">
      <select>{/* 平台 */}</select>
      <input />{/* 搜索 */}
    </div>
  </div>
  <div className="source-health-grid">
    {filteredSources.map(source => (
      <article className={`source-health-card severity-${severity}`}>
        {/* 收起内容：始终可见的关键指标 */}
        {/* 展开内容：诊断详情 */}
      </article>
    ))}
  </div>
</section>
```

---

## 五、实施优先级

| 阶段 | 内容 | 性质 |
|---|---|---|
| **Phase 1** | 统计卡 + 网格布局 + severity 色条 + 状态排序 + 术语修正 + 过滤栏 | 纯前端，约 1-2 天 |
| **Phase 2** | 平台筛选 + 搜索整合到过滤栏 + "编辑配置"跳转 Settings | 纯前端，约 1 天 |
| **Phase 3** | 排序切换 + 批量操作 + 性能对比视图 | 纯前端，约 2 天 |

不需要后端改动。

---

## 六、验证清单

### Phase 1
- [ ] 4 个统计卡数字正确（正常/告警/异常/停用）
- [ ] 统计卡可点击过滤
- [ ] 来源按 error→warning→healthy→idle 排序
- [ ] 色条颜色与预警台一致
- [ ] 网格布局宽屏 2-3 列、窄屏单列
- [ ] 异常来源卡片背景微红
- [ ] "补抓"→"重新抓取"术语修正
- [ ] `npm run build` 通过
