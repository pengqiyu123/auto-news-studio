# Auto News Studio LLM 翻译与故障切换收口计划（修订定稿版）

## Summary

当前不应直接推进完整的 LLM failover 目标态，必须先修复已经实现但实际上**从未成功调用 LLM** 的事件翻译链。

已确认的现状事实：

- `IntelEvent.summary_translated` 和 `IntelAlert.summary_translated` 字段已存在，前端事件页也已接入翻译行显示
- `intel_pipeline.py` 当前通过 `_get_llm_service()` 创建 `LLMService()`，**没有传入任何 llm config**
- `LLMService.generate("summary", ...)` 因 `providers/tasks` 为空而抛出 `ValueError: Task summary is not configured`
- 异常被 `_translate_summary()` 吃掉后返回 `""`
- 结果是：**所有 `summary_translated` 实际恒为空，事件翻译功能表面存在、实际未工作**

因此固定实施顺序改为：

1. **先修翻译链致命 bug**
2. **再做翻译缓存**
3. **再做并行翻译**
4. **再做任务级主备 failover**
5. **最后再改 AI 设置页任务级主备 UI**

第一阶段目标不是“做完整 LLM 路由系统”，而是先让**事件层翻译真实可用**。

## Key Changes

### 1. 现状审计与第一优先级修复

先修复事件翻译链的前提问题，禁止在此前提未通前推进后续优化。

固定修法：

- `build_intel_state(...)` 增加 `llm_config` 入参
- `store._rebuild_intel_for_state(...)` 调用 `build_intel_state(...)` 时，把当前 `state["llm"]` 显式传入
- `intel_pipeline` 不再自行构造裸 `LLMService()`
- `_get_llm_service()` 改为基于传入的 `llm_config` 创建服务，或直接改成“按当前 llm_config 获取 service”的纯函数
- 若当前 llm 配置不可用，翻译链才允许返回空字符串；不能因为代码 wiring 错误导致恒为空

本阶段固定继续**复用 `summary` 任务配置做翻译**：

- 不新增 `translation` task key
- 不改 `DEFAULT_LLM_TASK_TEMPLATE`
- 翻译模型来源固定为：
  - 优先 `summary`
  - 若 `summary` 不可用，则视为当前无翻译能力，不做隐式乱回退

### 2. Phase A：让事件层翻译真实可用

在 bug 修复后，保留现有最小翻译策略，但把行为定义明确。

固定行为：

- 只翻译 `IntelEvent.summary`
- `IntelAlert.summary_translated` 继续从事件投影
- `DiscoveryItem` 仍不加翻译字段
- 中文占比 > 50% 时跳过翻译
- 翻译输入截断上限固定为 1500 字符
- 翻译失败时：
  - `summary_translated = ""`
  - 不阻断事件和预警生成
  - 不做高频 error 日志刷屏
  - 只记录低频 warning 或 runtime 级调用结果

本阶段不做：

- failover
- 并行翻译
- task-level UI
- translation 独立任务键

### 3. Phase B：翻译缓存

在翻译真正可用后，优先加缓存，避免同一事件/相近摘要重复请求。

固定缓存策略：

- 只做**事件摘要级缓存**
- 缓存键固定为摘要规范化后的 hash
- 缓存值固定为译文字符串
- 空字符串失败结果**不缓存为成功**
- 同一轮内重复摘要应命中缓存
- 缓存放在 `intel_pipeline` 模块级变量，**进程生命周期内有效**
- **不做持久化**，避免 `state.json` 膨胀

固定目标：

- 对 carry-forward 事件、重复事件摘要、相同英文摘要避免重复打 LLM
- 缓存只优化性能，不改变翻译语义

### 4. Phase C：并行翻译

缓存之后再加并行，避免在“翻译根本不工作”或“重复请求很多”时先把复杂度抬高。

固定范围：

- 只并发翻译事件级摘要
- 并发上限固定取一个保守值，不与来源抓取线程池混用
- 单个事件翻译失败不影响同轮其他事件翻译
- 结果写回时保持事件顺序稳定，不让翻译并发破坏排序和 UI 结果对应关系

并行前提：

- 必须建立在 bug 已修复、缓存已可用的基础上

### 5. Phase D：任务级主备 failover

在翻译链真实可用、且性能优化完成后，再做主备切换。

第一版 failover 固定范围：

- 先覆盖 `summary` 任务
- 翻译继续复用 `summary` 的任务执行链
- 每任务仅支持：
  - primary provider/model
  - 1 个 fallback provider/model

切换触发条件固定为：

- `RateLimitError`
- `APIConnectionError`
- `APITimeoutError`

固定不作为切换信号的情况：

- 输出内容不满意
- 文风不理想
- 业务语义弱

固定执行顺序：

- primary 1 次
- 失败后 fallback 1 次
- 不无限重试

日志固定记录：

- `task_key`
- primary / fallback provider/model
- primary 失败原因
- 是否发生切换
- 最终成功/失败
- 最终使用模型
- latency

### 6. Phase E：AI 设置页任务级主备 UI

最后才改 UI，因为当前前端任务级配置即使存在也会被后端覆盖，先改 UI 没有真实意义。

固定改法：

- 后端先放开 `tasks` 的持久化，不再每次保存都被 `build_tasks_from_profile()` 覆盖
- `build_tasks_from_profile()` 仅保留为：
  - 默认值派生
  - 旧配置迁移
- 设置页在后端持久化逻辑放开后，再增加任务级主备配置区

第一版 UI 只要求：

- `summary` 的主模型/备用模型
- 若后续需要，再单独拆 `translation`
- 不做“按启用档位自动尝试全部模型”的黑箱策略

## Public Interfaces / Types

### 第一阶段（bug 修复 + 可用翻译）
- `build_intel_state(...)`
  - 新增 `llm_config` 入参
- `IntelEvent`
  - 保留 `summary_translated`
- `IntelAlert`
  - 保留 `summary_translated`

### 后续阶段（failover / UI）
- `LLMTaskConfig`
  - 后续扩展为显式 primary/fallback 字段
- `GET /api/admin/llm`
  - 后续返回任务级主备配置
- `PUT /api/admin/llm`
  - 后续接受并持久化任务级主备配置
- 当前阶段不新增 `translation` task key，继续复用 `summary`

## Test Plan

### 1. 现状 bug 修复验证
- 当前有有效 llm 配置时，`summary_translated` 不再恒为空
- 可通过实际 provider/model 调用记录确认 `LLMService.generate("summary", ...)` 被真正执行
- 配置缺失时才返回空字符串，而不是因为 wiring 错误返回空字符串

### 2. 事件翻译可用性
- 英文事件摘要可生成中文译文
- 中文占比 > 50% 时跳过翻译
- 截断到 1500 字符后仍可输出译文
- 翻译失败不影响 `intel_events / intel_alerts` 主链

### 3. 缓存
- 同一摘要重复出现时不会重复请求 LLM
- 失败结果不会被当成功缓存
- carry-forward 事件重复摘要可命中缓存

### 4. 并行
- 多事件翻译时可并发执行
- 单个事件翻译失败不影响其他事件
- 并发后事件顺序和结果映射不乱

### 5. Failover
- primary 成功时不触发 fallback
- primary 限流/超时/连接失败时触发 fallback
- primary 与 fallback 都失败时，日志完整、结果为空但主链不中断

### 6. 设置页
- 后端放开任务配置持久化后，前端保存的任务路由不再被 current profile 覆盖
- `summary` 主备模型保存后刷新页面仍保持

## Assumptions

- 当前事件层翻译字段和前端显示已经存在，不需要重做字段和展示结构
- 当前最优先问题是“翻译调用链未真正接上 llm_config”，不是算法优化
- 第一阶段继续复用 `summary` 任务做翻译，不新增 `translation` task key
- failover、并行、缓存都必须建立在“翻译已真实可调用”的前提上
- 第一版 task-level failover 只覆盖 `summary`，翻译跟随其执行链
