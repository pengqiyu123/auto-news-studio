# Auto News Studio 聚类与稿件证据包增强计划

## Summary

本轮目标是先修“处理漏斗”，不扩新来源、不上 embedding、不改前端主流程，围绕两件事做最小高收益增强：

1. **让实体信号参与事件聚类**
2. **让稿件输入从事件摘要升级为成员证据包**

固定决策：

- 继续沿用现有 `spaCy + 关键词` 实体提取器
- 不把实体直接当作“同事件即必合并”的硬条件
- 不新增 API 路由
- 不做网页正文抓取；证据包首版只用 `discovery_items` 的标题、摘要、链接、时间
- 不改模型设置页与稿件页主交互；本轮先提升底层质量

## Key Changes

### 1. 实体下沉到 discovery / source-story 层

在 `build_discovery_items(...)` 阶段就对每条素材的 `title + summary` 做轻量实体提取，给每个 discovery item 增加内部字段：

- `entity_ids`
- `entity_names`

固定规则：

- 复用现有 `extract_entities(...)`
- 单条素材最多保留 6 个实体
- 提取失败返回空数组，不阻断主链
- 首版只取 `title + summary`，不读 `content`

在源内压实 `_compact_source_cluster(...)` 后保留 story 级实体集合：

- `entity_ids` 为 cluster 并集
- `entity_names` 为 cluster 并集
- 上限 12 个，按主素材优先、其余按出现顺序补齐

### 2. 用实体信号增强 `_should_merge(...)`

保留现有强信号不变：

- `canonical_link` 相同直接合并
- `dedupe_key` 相同直接合并
- `Jaccard >= 0.45` 直接合并

在弱相似区间加入实体辅助判断，固定逻辑如下：

- 若 `similarity < 0.15`：直接不合并
- 计算：
  - `entity_overlap_count`
  - `anchor_overlap`
  - `within_day`
  - `same_theme`
- 仅在 `within_day = true` 且 `same_theme = true` 时允许弱合并
- 新增两条实体辅助规则：
  - `entity_overlap_count >= 2` 且 `similarity >= 0.15` -> 合并
  - `entity_overlap_count >= 1` 且 `anchor_overlap = true` 且 `similarity >= 0.18` -> 合并
- 保留原兜底：
  - `similarity >= 0.28` 且 `anchor_overlap = true` 且 `within_day = true` 且 `same_theme = true` -> 合并

固定约束：

- 仅因单个大实体名相同不能合并
- 不让实体参与评分、预警状态机，只参与聚类判定

### 3. 事件投影补证据包，替代“只有代表链接”

在事件转 candidate 的链路中，基于 `event.discovery_item_ids` 回查当前轮 `discovery_items`，生成结构化 `evidence_pack`。

每条 evidence 固定字段：

- `discovery_item_id`
- `source_name`
- `title`
- `summary`
- `link`
- `published_at`
- `collected_at`
- `entity_names`

固定生成规则：

- 每个事件最多取 5 条 evidence
- 优先顺序：
  1. `representative_discovery_item_id`
  2. 其余按 `published_at desc -> collected_at desc -> engagement_score desc`
- 对重复链接去重
- `candidate.evidence_links` 改为最多 5 个唯一链接，不再只放 `representative_link`
- `candidate` 增加可选附加字段：
  - `evidence_pack`
  - `entity_names`
  - `summary_translated`
  - `alert_state`
  - `alert_reason`

兼容要求：

- 旧 candidate / draft 无这些字段时按空数组或空值兼容
- 不删除旧 `representative_link` 语义

### 4. 稿件 brief 与 LLM prompt 改为吃证据包

`compose_draft(...)` 仍保留现有四步链路，但输入升级为证据包驱动。

固定改法：

- `_build_intel_brief(...)` 新增：
  - `evidence_pack`
  - `entity_names`
  - `alert_state`
  - `alert_reason`
- `_pick_facts(...)` 优先从 `evidence_pack` 生成事实句；证据不足时再退回原规则
- `outline / article / summary` 的 prompt 都显式加入：
  - 事件摘要
  - 来源数
  - 证据包列表
  - 证据链接列表
- 模板兜底分支也使用 `evidence_pack`，不是只看 event summary

固定文案策略：

- 证据包只作为“已确认素材”
- 不要求模型综合网页正文
- 若证据包不足，仍明确提示“信息仍待进一步确认”

## Public Interfaces / Types

默认不新增接口路由，维持现有：

- `/api/admin/intel/stream`
- `/api/admin/intel/events`
- `/api/admin/intel/alerts`
- `/api/admin/drafts`

本轮接口变更采用**加法兼容**：

- `DraftItem.brief` 增加：
  - `evidence_pack`
  - `entity_names`
  - `alert_state`
  - `alert_reason`
- `DraftItem.composition_trace` 增加：
  - `evidence_pack`
- `CandidateTopic` 运行态可携带：
  - `evidence_pack`
  - `entity_names`
  - `summary_translated`
  - `alert_state`
  - `alert_reason`

默认不要求前端立即消费这些新增字段；前端可无感兼容。

## Test Plan

### 1. 实体辅助聚类
- `Apple 发布新机` / `苹果发布新机` / `Apple unveils ...` 在同日、同主题下可合并为同一事件
- 仅共享单一实体名但主题不同的新闻不会误合并
- 现有 `canonical_link` / `dedupe_key` / `Jaccard >= 0.45` 逻辑保持有效

### 2. 旧链路不回退
- `build_intel_state(...)` 仍能正常产出 `discovery_items / intel_events / intel_alerts`
- 实体提取失败时不影响本轮事件与预警生成
- 旧 state 中无 discovery-level 实体字段时可正常启动和重建

### 3. 证据包写稿
- 从热点事件生成稿件时，`brief.evidence_pack` 至少包含代表素材，最多 5 条
- `evidence_links` 不再只是一条代表链接，而是多条唯一链接
- `create_draft_from_event`、`create_draft_from_candidate`、`regenerate_draft` 都能走通

### 4. 稿件内容回归
- LLM 可用时，outline/article/summary prompt 中包含证据包
- LLM 不可用时，模板稿仍使用 evidence_pack 生成事实点
- 前端稿件页、预警页、热点页不因新增字段报错

### 5. 编译与构建
- `python -m compileall backend/app`
- 前端 `npm run build`
- 关键事件生成稿件接口回归：
  - `POST /api/admin/intel/events/{event_id}/draft`

## Assumptions

- 本轮不引入 embedding、向量库、MinHash、网页正文抽取
- discovery-level 实体字段首版以内部使用为主，不强制前端展示
- 证据包首版只来自当前轮 `discovery_items`，不跨 24h 历史回补
- `same_theme` 继续沿用现有 `tags overlap or same platform` 定义
- 多语言同事件识别先靠“实体 + 低阈值 Jaccard + anchor”增强，不单独引入翻译预归一层
