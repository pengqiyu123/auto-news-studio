# Auto News Studio 实体标签层实施计划（PLAN5 定稿版）

## Summary

本计划在**主事实链恢复基线之后**落地实体标签层，目标是在**不改变主事实链**的前提下，为 `intel_events / intel_alerts` 增加稳定的实体标签能力，用于**筛选、监控、统计**。

固定前提门槛，全部满足后才进入阶段一实施：

1. `intel_events` 数量不再长期高于 `discovery_items`
2. `current_cycle` 完成后稳定回到 `idle`
3. 执行摘要中的本轮增量统计口径可信
4. 连续多轮内不会出现“几乎全量 `cooling_event`”
5. 预警链可稳定产出非零 `rising / breakout`，或能明确证明当前数据源确实无触发

固定原则：

- 主事实链不变：`discovery_items → intel_events → intel_alerts → drafts`
- 实体标签层是**辅助浏览层**
- 一个事件可有多个实体标签
- 实体提取发生在**事件聚合之后**
- 实体标签不参与聚类、评分或预警判定
- Phase 1 只做**事件打标签**，不做全局 EntityRegistry 持久化 CRUD

## Key Changes

### Phase 1：事件打标签（最小落地）

新增最小后端模块：

- `entity_aliases.py`
- `entity_types.py`
- `entity_extractor.py`

不新增 `entity_watchlist.py`；重点监控实体在阶段二起统一存入现有 `store/state` 结构。

固定提取链路：

1. `spacy.load("zh_core_web_lg")`
2. 降级 `spacy.load("zh_core_web_md")`
3. 再降级到纯关键词模式

固定归一规则：

- `alias(lowercase) -> canonical_name`
- `canonical_name -> entity_type`
- `entity_id = md5(canonical_name)[:12]`

固定实体来源：

- 预置 `CANONICAL_ENTITIES` 显式定义类型
- 关键词命中只接受：
  - 命中 `ALIAS_MAP`
  - 或命中 `CANONICAL_ENTITIES`
- 未知关键词不自动生成 `ORG`
- spaCy 命中的未知实体可保留，但只接受 `ORG / PERSON / PRODUCT / EVENT / GPE`

固定注入时机：

- 在 `intel_pipeline.py` 的 `build_intel_state(...)` 中
- 事件聚合、评分、状态机完成后
- `IntelEvent` 最终写入前注入实体字段
- `IntelAlert.entity_*` 直接由所属 `IntelEvent.entity_*` 投影

固定字段扩展：

- `IntelEvent`
  - `entity_ids: list[str] = []`
  - `entity_names: list[str] = []`
- `IntelAlert`
  - `entity_ids: list[str] = []`
  - `entity_names: list[str] = []`

固定失败语义：

- spaCy 不可用时只降级，不阻断轮次
- 单事件提取失败时，该事件返回空数组
- 整轮实体提取失败只写 warning，不影响事件与预警生成

固定兼容策略：

- 旧 `state.json` 中已有事件没有 `entity_*` 字段时，前后端必须按空数组兼容
- Dashboard、`/intel/events`、`/intel/alerts` 返回口径一致

### Phase 2：前端筛选与重点监控实体

固定第一入口：

- 热点簇页增加实体筛选
- 预警台页增加实体筛选
- 不新增主导航

热点簇固定新增：

- `全部实体` 下拉
- 事件卡片实体标签行
- 当前结果集内实体聚合作为筛选源
- 最多显示 3 个标签，超出用 `+N`

预警台固定新增：

- 与热点簇一致的实体筛选
- 预警卡片显示实体标签
- 筛选为空时只显示“当前筛选条件下没有匹配的预警”

重点监控实体固定设计：

- 作为附属面板，不单独成主导航
- 状态存储在现有 `store/state`
- 最小字段：
  - `entity_id`
  - `entity_name`
  - `entity_type`
  - `watchlisted`
  - `added_at`

固定能力：

- 添加监控实体
- 移除监控实体
- 查看关联事件数 / 预警数 / 最近出现时间
- 点击后跳到热点簇并自动带实体筛选

Phase 2 不做：

- 全局实体管理页
- 自动发现推荐实体
- 实体级独立搜索接口

### Phase 3：实体统计与首页摘要

阶段三只做**重点监控实体摘要**，不做全量实体榜。

固定统计来源：

- 仅基于当前 `intel_events / intel_alerts` 即时聚合
- 不新增顶层事实表

固定输出字段：

- `entity_id`
- `entity_name`
- `entity_type`
- `event_count`
- `alert_count`
- `rising_count`
- `breakout_count`
- `last_seen_at`
- `watchlisted`

固定接入位置：

- `/api/dashboard` 增加 `entity_watchlist_summary`
- 首页最多展示 5 个重点监控实体
- 排序：`breakout_count desc -> rising_count desc -> last_seen_at desc`

固定限制：

- 首页实体摘要不能替代原有事件/预警主位
- 不展示全量热门品牌榜，避免固化视角、降低新信号嗅觉

## Public Interfaces / Types

### 类型扩展
- `IntelEvent`
  - `entity_ids: string[]`
  - `entity_names: string[]`
- `IntelAlert`
  - `entity_ids: string[]`
  - `entity_names: string[]`

### Phase 1 接口变更
以下接口统一返回实体字段：

- `/api/admin/intel/events`
- `/api/admin/intel/events/{event_id}`
- `/api/admin/intel/alerts`
- `/api/admin/dashboard`
- `/api/admin/intel/summary` 中的 `top_events / top_alerts`

### Phase 2 接口变更
新增最小重点监控实体接口：

- `GET /api/admin/entities/watchlist`
- `PUT /api/admin/entities/watchlist`

`PUT` 固定采用**整表覆盖**语义。

### Phase 3 接口变更
- `/api/admin/dashboard`
  - 新增 `entity_watchlist_summary`

## Test Plan

### 1. 降级与失败语义
- 安装 `zh_core_web_lg` 时可正常提取科技公司、人物、模型名
- 缺少 `lg` 时自动降级到 `md`
- 缺少 `lg/md` 时纯关键词模式仍能产出实体
- 单事件提取失败不会阻断整轮
- 旧 state 中无 `entity_*` 字段时前后端不崩

### 2. 别名归一
- `苹果 / Apple / Apple Inc.` -> 同一 `entity_id`
- `华为 / Huawei` -> 同一 `entity_id`
- `库克 / Tim Cook` -> 同一 `entity_id`
- `GPT-5` -> `PRODUCT`
- `OpenAI` -> `ORG`

### 3. 投影一致性
- `IntelEvent.entity_*` 正常返回
- `IntelAlert.entity_*` 与其源事件一致
- Dashboard `top_events / top_alerts` 实体字段不缺失
- 旧事件对象缺字段时默认空数组

### 4. 前端筛选
- 热点簇按实体筛选可用
- 预警台按实体筛选可用
- 标签过多时布局不坏
- 筛选为空时文案正确

### 5. 重点监控实体
- 可添加与移除监控实体
- 面板中的事件数、预警数与当前结果一致
- 点击监控实体可跳转并自动筛选
- 未监控实体不会进入首页实体摘要

### 6. 阶段三统计
- 首页最多展示 5 个重点监控实体
- `rising / breakout` 计数与预警列表一致
- 不会出现 dashboard 里有实体摘要、但结果页筛不到对应事件的情况

## Assumptions

- 本计划在主事实链基线恢复后实施
- Phase 1 固定只做事件级标签注入，不做全局实体 CRUD
- 实体提取逻辑固定放在 `intel_pipeline.py`，不是 `store.py`
- 重点监控实体状态固定放在现有 `store/state` 体系中
- 未知关键词不自动生成 ORG 实体
- 实体标签只服务浏览、筛选、监控、统计，不进入聚类和预警判定

## Phase 1 实施检查清单

### 后端类型与数据结构
- [ ] 在 `IntelEvent` 中新增 `entity_ids` 和 `entity_names`，默认空数组
- [ ] 在 `IntelAlert` 中新增 `entity_ids` 和 `entity_names`，默认空数组
- [ ] 确认旧 `state.json` 缺少实体字段时，Pydantic 可按默认值加载
- [ ] 确认前端共享类型同步新增这两个字段，默认按空数组处理

### 别名与类型定义
- [ ] 新建 `entity_aliases.py`，只存 `alias(lowercase) -> canonical_name`
- [ ] 新建 `entity_types.py`，只存 `canonical_name -> entity_type`
- [ ] 预置实体至少覆盖 Apple / Huawei / OpenAI / NVIDIA / Qualcomm / GPT-5 / Claude / HarmonyOS / Tim Cook / Jensen Huang
- [ ] 明确 `"苹果" -> "Apple"`、`"华为" -> "Huawei"`、`"库克" -> "Tim Cook"` 这类中英文映射
- [ ] 不允许未知关键词直接落成 ORG

### 实体提取器
- [ ] 新建 `entity_extractor.py`
- [ ] 实现 `_get_nlp()` 的三级降级：`lg -> md -> None`
- [ ] 实现 alias 归一函数，先归一再判类型
- [ ] 实现 spaCy NER 提取，限制文本长度
- [ ] 实现关键词/正则兜底，并与 spaCy 结果去重
- [ ] 实现 `entity_id(canonical_name)` 生成规则
- [ ] 限制单事件最大实体数为 10
- [ ] 任意提取异常只返回空数组，不抛出阻断主链路

### 注入到情报管线
- [ ] 在 `build_intel_state(...)` 中，事件聚合完成后对每个事件调用提取逻辑
- [ ] 将 `entity_ids` 和 `entity_names` 注入每个 `event` 字典
- [ ] 生成 `intel_alerts` 时，把事件实体字段原样投影到 alert
- [ ] 不把实体提取逻辑放进 `store.py`
- [ ] 不让实体字段参与 `_should_merge`、评分、预警状态机

### 接口投影与兼容
- [ ] `/api/admin/intel/events` 返回实体字段
- [ ] `/api/admin/intel/events/{event_id}` 返回实体字段
- [ ] `/api/admin/intel/alerts` 返回实体字段
- [ ] `/api/admin/dashboard` 的 `top_events / top_alerts` 返回实体字段
- [ ] 确认无实体字段的旧数据不会让页面崩溃

### Phase 1 验收
- [ ] 在安装 `zh_core_web_lg` 的环境下，Apple / 华为 / GPT-5 / 黄仁勋可被识别
- [ ] 在缺少 `lg` 时，`md` 或纯关键词模式仍能输出实体
- [ ] 旧 state 直接启动时，事件页和预警页不报错
- [ ] 任意单事件提取失败不会导致整轮 `intel_events / intel_alerts` 丢失
- [ ] 事件与预警的实体字段口径完全一致
