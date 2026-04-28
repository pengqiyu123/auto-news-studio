# Auto News Studio 信息获取增强方案（修订版）

## Summary

按你的反馈调整优先级，信息获取层分 4 个阶段推进，先解决“卡死”和“新旧不分”，再补可观察性，最后才考虑缓存。

固定顺序：

- **P0：任务锁 + 心跳 + 僵尸回收**
- **P1：增量判定**
- **P2：源健康状态**
- **P3：源级缓存（延后）**

本轮计划里，**P0-P2 作为必做**，**P3 作为后续增强**。  
原则固定为：

- 先保证自动轮次不会卡死
- 再保证“本轮新增”语义可信
- 再提升来源可观察性
- 缓存只在前面三项稳定后再引入

## Key Changes

### P0. 任务锁 + 心跳 + 僵尸回收

目标：任何一轮采集都必须有明确的开始、存活、结束、异常回收语义。

实现要求：

- 为自动轮次建立单独的持久化运行状态对象，至少包含：
  - `run_id`
  - `status: idle | running | completed | failed | abandoned`
  - `stage`
  - `started_at`
  - `heartbeat_at`
  - `finished_at`
  - `triggered_by`
  - `error`
- 启动前先检查运行状态：
  - 若存在新鲜 `running`，拒绝再次启动
  - 若存在超时 `running`，标记旧轮次为 `abandoned` 后再接管
- 心跳更新时机固定为：
  - 每完成一个来源
  - 每次阶段切换
  - 每次捕获异常前
- 僵尸阈值固定：
  - `source_timeout_seconds = 12`
  - `run_stale_seconds = 180`
- 任意退出路径都必须写入终态：
  - 成功 -> `completed`
  - 异常 -> `failed`
  - 超时接管 -> `abandoned`
- 首页、日志页、任务页统一读取这套运行状态，不再混用散落的瞬时字段

接口与状态变化：

- `/api/admin/runtime/status` 返回上述运行态
- dashboard 中 `runtime_status` 必须与其语义一致
- 前端显示状态固定为：
  - `运行中`
  - `等待下一轮`
  - `已停止`
  - `本轮失败`
  - `已接管异常轮次`

---

### P1. 增量判定

目标：把“抓到很多条”变成“这轮真正新增了什么”。

新增两层判定：

#### 1) 条目级增量

判定键固定按优先级使用：

1. `canonical_link`
2. `source_key + 原始来源唯一 id`
3. `source_key + dedupe_key + published_at`

条目状态固定为：

- `new_item`
- `seen_item`
- `updated_item`

规则固定：

- 本轮首次出现且历史不存在 -> `new_item`
- 历史已有同键且内容无变化 -> `seen_item`
- 历史已有同键但标题/摘要/互动数有明显变化 -> `updated_item`

#### 2) 事件级增量

聚类后为事件打标：

- `new_event`
- `growing_event`
- `stable_event`
- `cooling_event`

判定规则固定：

- `new_event`
  - 历史中不存在该事件标识
- `growing_event`
  - 历史存在，且本轮成员数增加或平台数增加
- `stable_event`
  - 历史存在，但无新增成员、无新增平台
- `cooling_event`
  - 连续两轮无成员增长，或最近一段时间只重复出现旧成员

首页与预警规则：

- 首页“本轮动态”只统计：
  - `new_event`
  - `growing_event`
- `stable_event` 不进入本轮重点提示
- `cooling_event` 只在预警台或事件详情里显示，不占首页核心位

指标新增：

- `new_items_count`
- `seen_items_count`
- `updated_items_count`
- `new_events_count`
- `growing_events_count`
- `stable_events_count`
- `cooling_events_count`

文案统一改为：

- 本轮新增素材
- 本轮新事件
- 本轮升温事件

不再只说“抓取了多少条”。

---

### P2. 源健康状态

目标：让用户知道“哪里慢、哪里坏、坏了多久”，但不把它放在稳定性之前。

保留现有来源模型，补充以下字段：

- `last_attempt_at`
- `last_success_at`
- `last_failure_at`
- `consecutive_failures`
- `last_duration_ms`
- `avg_duration_ms`
- `last_item_count`
- `health_status`
- `health_detail`

健康状态规则固定：

- `healthy`
  - 最近一次成功，且连续失败数为 0
- `warning`
  - 最近一次成功但耗时 > `8s`
  - 或连续失败数为 1
  - 或最近 6 小时未成功同步
- `error`
  - 连续失败数 >= 2
  - 或最近一次请求超时/异常且无结果
  - 或最近 24 小时无成功记录
- `idle`
  - 来源被停用

展示要求：

- 首页摘要显示：
  - 健康来源数
  - warning 数
  - error 数
  - 最慢 3 个来源
- 来源健康页显示：
  - 最近成功
  - 最近失败
  - 连续失败次数
  - 最近耗时
  - 平均耗时
  - 最近条数
  - 最近错误

注意：

- 这一层只提升可观察性
- 不改变 P0/P1 的核心运行逻辑
- 健康状态不得影响增量判定语义

---

### P3. 源级缓存（后续增强，暂不立即实施）

目标：降低慢源压力和波动，但明确不在当前阶段落地。

延后原因固定为：

- 当前瓶颈首先是卡死与状态不可信，不是缓存命中率
- 并发与超时先落地后，单个慢源不会再拖垮整轮
- 在增量判定稳定前引入缓存，会污染“本轮新增”语义

后续若实施，约束固定：

- 缓存只做性能和短时容灾
- 缓存结果必须显式标记 `used_cache = true`
- 使用缓存不得计入真实新增
- 过期缓存不得冒充成功抓取

本阶段只保留接口设计预留，不要求实现。

## Test Plan

### P0. 任务锁与僵尸回收

- 连续触发两次开始工作，只允许一轮进入 `running`
- 模拟轮次异常退出，状态写为 `failed`
- 模拟超时无心跳的旧轮次，新轮次可接管并把旧轮次标记为 `abandoned`
- 完成后状态不会瞬间回到“未运行”且丢失上下文

### P1. 增量判定

- 相同链接重复抓取，只出现一次 `new_item`
- 同事件被多个来源转载，本轮只新增一次 `new_event`
- 同事件平台数增加时转为 `growing_event`
- 无新增成员、无新增平台时保持 `stable_event`
- 首页本轮动态不再被重复旧条目占满

### P2. 源健康状态

- 单源成功会更新最近成功时间、耗时、条数
- 单次失败进入 `warning`
- 连续两次失败进入 `error`
- 慢源能被标记为 warning
- 停用来源保持 `idle`

### P3. 缓存预留

- 本阶段不验收缓存命中逻辑
- 只确认后续实现不会与增量统计冲突

## Assumptions

- 当前仍沿用现有 `store/state` 架构，不强制迁移 SQLite
- 单源超时默认值固定为 `12s`
- 自动轮次最终应切换到真正并发采集，但该改动属于实现阶段，不在本计划中展开为独立决策项
- P3 缓存明确延期，不与 P0-P2 一起落地
- 所有统计都必须坚持“真实新增优先”，禁止缓存、回退或旧数据伪装成新结果
