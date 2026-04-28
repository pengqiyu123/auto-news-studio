# Auto News Studio 信息获取阶段收口计划（最终定稿）

## Summary

本轮计划以“**可信情报层**”为唯一目标，不扩大量新来源，不进入写稿质量优化，不引入向量库、MinHash 或 LLM 主判定。

固定目标顺序：

1. **素材增量可信**
2. **事件聚合可信**
3. **预警结果可信**
4. **模式感知运行态可信**
5. **单轮执行摘要可信**

本轮继续使用现有唯一事实链：

- `discovery_items`
- `intel_events`
- `event_snapshots`
- `intel_alerts`

三种产品模式都纳入设计：

- `radar_only`
- `radar_and_draft`
- `full_pipeline`

---

## Key Changes

### 1. 素材层：保持 `source_native_id` 作为上游稳定主键

条目增量判定优先级固定为：

1. `canonical_link`
2. `source_key + source_native_id`
3. `source_key + dedupe_key + published_at`

这里明确不改成 `source_item_id`。当前实现里 `source_native_id` 已实际承载 RSS GUID、Reddit ID、HN objectID、GitHub repo full_name 等上游稳定标识，应继续作为第二优先级身份键。

结果层固定只使用 `item_state`：

- `new_item`
- `seen_item`
- `updated_item`

首页与实时流固定展示：

- 本轮新增素材
- 本轮更新素材
- 本轮重复素材

实时流固定支持筛选：

- 时间范围
- 来源
- 平台
- 状态
- 热度区间

固定约束：

- 历史重复条目不得重新计为新增
- 缓存命中、旧数据、回退数据不得伪装成新增
- 首页计数与实时流筛选结果必须一致

### 2. 事件层：用“两段聚类 + 展示护栏”解决单源事件裂变

#### 2.1 段一：源内压实

在跨源聚类前，先做同一来源内的短时高密相似条目压实，目标是先消灭“同源裂变”。

固定规则：

- 只在相同 `source_key` 内处理
- 时间窗固定 `12h`
- 分桶种子按优先级使用：
  1. `canonical_link`
  2. `source_native_id`
  3. `top_2_anchor_tokens + day_bucket`
- `day_bucket` 固定按 **UTC 日期边界** 生成，不使用本地时区日界线

同桶内先合并为“源内临时故事”的条件固定为任一满足即可：

- `canonical_link` 相同
- `source_native_id` 相同
- `dedupe_key` 相同
- `Jaccard >= 0.30` 且 `anchor_tokens` 有交集

目的固定为：

- 同一 RSS / GitHub / 热榜来源对同一件事的轻微改写、重复转存、短时连发，先在源内压成一个故事
- 优先解决“一个来源自己刷满热点簇”的根因

#### 2.2 段二：跨源事件聚类

源内压实后的故事再进入跨源事件聚类。

固定跨源合并规则：

- 直接合并：
  - `canonical_link` 相同
  - `dedupe_key` 相同
- 强相似合并：
  - `Jaccard >= 0.45`
  - 且 `anchor_tokens` 有交集
- 弱相似合并：
  - `0.28 <= Jaccard < 0.45`
  - 且必须同时满足：
    - 至少 1 个 `anchor_token` 重合
    - 发布时间差不超过 24 小时
    - 标签有交集，或平台/来源类别高度接近

固定不全局下调主阈值到 `0.32`。原因是当前问题优先来自同源裂变，不来自跨源合并过弱；直接放低全局阈值更容易误并。

#### 2.3 段三：首页与热点簇展示护栏

单源、低扩散事件即便保留，也不应该轻易占首页主位。

固定首页“重点事件”主位准入条件，至少满足一项：

- `platform_count >= 2`
- `source_count >= 2`
- `member_count >= 3`
- `engagement_score` 达到来源内高位

不满足者：

- 保留在 `热点簇`
- 不删除
- 只做展示降权，不进首页主位

热点簇排序固定为：

- 默认：`CompositeScore`
- 切换：`member_delta`
- 切换：`platform_delta`
- 切换：最新出现时间

事件层必须稳定产出并被前端消费的字段固定为：

- `member_count`
- `platform_count`
- `source_count`
- `first_seen_at`
- `last_seen_at`
- `member_delta`
- `platform_delta`
- `change_state`
- `composite_score`
- `alert_reason`

### 3. 预警层：字段名收口为 `alert_reason -> reason` 投影，不再发明第三套名称

当前实现中：

- `IntelEvent` 使用 `alert_reason`
- `IntelAlert` 使用 `reason`

本轮固定保持这个语义，不引入 `trigger_reason` 第三套字段名。

规则固定为：

- 事件内部解释字段：`alert_reason`
- 对外预警对象字段：`reason`
- `reason` 由 `event.alert_reason` 投影生成

预警状态机继续使用：

- `watch`
- `rising`
- `breakout`
- `cooling`

继续固定为规则主判定，LLM 不参与主决策。

快照规则固定：

- 每轮写入 `event_snapshots`
- 仅保留最近 48 小时
- 支持计算：
  - `delta_mentions_30m`
  - `delta_mentions_2h`
  - `speed_30m`
  - `speed_2h`
  - `acceleration`

每条预警固定输出：

- `level`
- `reason`
- `VelocityScore`
- `CoverageScore`
- `FreshnessScore`
- 成员变化
- 平台变化
- 代表链接

首页固定只突出：

- `breakout`
- `rising`

### 4. 运行态：模式感知分段由后端显式提供

不再让前端自行猜总阶段数。

后端运行态固定显式返回：

- `mode_key`
- `stage_key`
- `stage_label`
- `stage_index`
- `stage_total`

阶段模型固定为：

- `radar_only`
  1. 采集素材
  2. 聚合热点事件
  3. 判断热度与预警

- `radar_and_draft`
  1. 采集素材
  2. 聚合热点事件
  3. 判断热度与预警
  4. 生成稿件

- `full_pipeline`
  1. 采集素材
  2. 聚合热点事件
  3. 判断热度与预警
  4. 生成稿件
  5. 分发与同步

固定约束：

- `radar_only` 不显示稿件/分发阶段
- `full_pipeline` 不允许在实际进入稿件/分发后仍显示“判断热度与预警”
- 进度条不得回退、串段、错段

### 5. 执行摘要：在 store/runtime 层新增结构化摘要，再向旧字符串投影

当前执行摘要已在 **store 层** 计算 `last_cycle_issue_snapshot` 并投给 `dashboard/runtime`。  
因此本轮结构化执行摘要固定落在 **store/runtime 主状态**，不放在前端，不放在临时 dashboard 拼装层。

固定新增结构化单轮摘要对象，挂在 runtime 下，最小字段为：

- `run_id`
- `mode_key`
- `started_at`
- `finished_at`
- `duration_ms`
- `success_source_count`
- `failed_source_count`
- `new_items_count`
- `new_events_count`
- `growing_events_count`
- `slow_sources`：最多 3 条，含 `source_key / source_name / duration_ms / status`
- `issues`：本轮异常列表，含 `source_key / source_name / error_kind / message`
- 如模式含后续阶段，再附：
  - `draft_count`
  - `wechat_sync_count`
  - `publish_count`

兼容策略固定：

- 旧字段 `last_cycle_issue_summary` 继续保留
- 但不再单独手工拼接
- 由结构化摘要对象投影生成
- 首页、任务页、日志页优先消费结构化摘要；旧字符串仅做兼容展示

### 6. 性能边界：以“源内压实减少跨源输入量”为主，实施时必须做一次基准验证

本轮不预设复杂性能优化，但固定要求实施时做一次基准校验。

基准场景固定：

- 59 个来源
- 单轮约 500 条素材
- 开启源内压实 + 跨源聚类 + 48h 快照保留

验收口径固定：

- 聚类阶段整体耗时不能明显压垮当前单轮体验
- 与未做源内压实时对比，跨源输入量应下降
- 若聚类耗时显著增加，再局部优化分桶或比较范围，但不改变本轮主方案

---

## Public Interfaces / Types

本轮固定调整以下接口/类型：

1. `/api/admin/runtime/status`
   - 新增：
     - `mode_key`
     - `stage_key`
     - `stage_label`
     - `stage_index`
     - `stage_total`
     - `last_cycle_summary`

2. `/api/dashboard`
   - 新增结构化 `last_cycle_summary`
   - 首页执行摘要与本轮动态从这里读取

3. `IntelEvent`
   - 保留 `alert_reason`
   - 保留 `change_state`
   - 保留 `member_delta / platform_delta / source_count / platform_count / composite_score`

4. `IntelAlert`
   - 保留 `reason`
   - 明确其来源是 `event.alert_reason` 投影

本轮不新增新的顶层事实表，也不新增第三套解释型状态字段。

---

## Test Plan

### 1. 素材增量
- 同一链接重复抓取 3 次，只第一次计为 `new_item`
- 标题/摘要/互动数变化时记为 `updated_item`
- 首页新增素材数与实时流筛选结果一致

### 2. 单源裂变修复
- 同一 RSS 来源短时相似条目不会稳定裂成多个弱事件
- GitHub 同 repo 重复记录不会形成多个热点事件
- 热榜类来源轻微改写不会在热点簇首屏连刷
- `day_bucket` 跨天时按 UTC 边界行为稳定

### 3. 跨源聚类
- 跨平台同事件可正确合并
- 不同事件不会因弱相似被大面积误并
- `intel_events` 数量不再长期高于 `discovery_items`

### 4. 预警可信度
- 连续多轮后能稳定出现 `rising / breakout`
- `<2h` 新事件不因缺少 2h 基线报错
- 老热点进入 `cooling`
- 每条预警都能展示 `reason`

### 5. 模式感知运行态
- `radar_only` 第 3 段后完成
- `radar_and_draft` 第 3 段后进入成稿
- `full_pipeline` 第 3 段后进入成稿与分发
- 进度条不回退、不串段、不误标阶段

### 6. 结构化执行摘要
- 摘要展示整轮异常，而不是最后一条异常
- 能展示最慢来源 Top 3
- `last_cycle_issue_summary` 能从结构化摘要正确投影
- 首页、runtime、日志页摘要语义一致

### 7. 性能基准
- 500 条素材规模下，源内压实 + 跨源聚类可在可接受时延内完成
- 源内压实后，进入跨源比较的输入量下降
- 无明显 UI 卡顿或运行阶段长时间停滞

---

## Assumptions

- 本轮不扩大量新来源，优先修现有来源的聚类与表达质量
- 本轮不引入向量库、MinHash、复杂缓存回退、LLM 主判定
- `source_native_id` 继续作为第二优先级素材身份键
- `day_bucket` 统一使用 UTC 日期边界
- 结构化执行摘要在 `store/runtime` 层生成，再投影到 `dashboard` 与旧字符串字段
- 情报链仍是所有模式的共同前置主链

## Research Basis

- 本地参考：
  - `TrendRadar`：增量监控、模式语义、单组展示上限
  - `newsnow`：来源 `interval` / `cache` 语义
- 线上参考：
  - Feedly Clustering: https://docs.feedly.com/article/552-what-is-clustering
  - Google News Personalization paper: https://compjournalism.com/files/papers/paper570.pdf
  - Google News clustering patent: https://patents.google.com/patent/US9361369B1/en
