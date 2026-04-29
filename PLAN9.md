# Auto News Studio 稿件层落地计划（手动先通 → 自动进微信草稿箱）

## Summary

本轮目标不是直接做“全自动发布”，而是按你确认的节奏，先把**手动稿件链路完整打通**，再在同一条稳定链路上推进到**自动生成 + 自动同步到微信公众号草稿箱**。

固定目标顺序：

1. **手动从热点/预警生成稿件可用**
2. **稿件准入规则可信**
3. **自动生成本地稿件可信**
4. **自动同步微信草稿箱可信**
5. **全链路状态表达可信**

固定决策：

- 最终自动化目标：**到微信公众号草稿箱为止**
- 本计划**不做自动正式发布**
- 信息层主判定继续保持**规则优先**
- 本轮**不重做 embedding 聚类**
- 稿件主输入改为 **`intel_events / intel_alerts`**
- 手动链路先通，再开启自动链路
- 自动链路默认只处理 **`watchlisted` 且 `alert_state ∈ {rising, breakout}`** 的事件

固定调研结论：

- 外部成熟产品更常见的是 **source-grounded drafting / 草稿优先 / 人工复核**
- 手动创作流不是“点一下直接发”，而是“事件 -> 简报 -> 初稿 -> 编辑 -> 预览 -> 草稿箱”
- 当前项目的公开 5 任务心智（`judgement / outline / article / title / summary`）视为**旧版残留**，不作为本轮最终设计
- 稿件层顶层导航首版固定只保留 2 个，不继续扩增为 3 个或更多
- 现有“重点观察”命名偏情报层，进入稿件层后固定改名为 **`选题池`**

---

## Key Changes

### 0. 现状审计：当前稿件链和模型设置存在“新旧并存”

固定审计结论：

- 后端默认 LLM 任务模板已经收口为 2 任务：
  - `judgement`
  - `article`
- 但前端模型设置页仍在构造并展示 5 个任务：
  - `judgement`
  - `outline`
  - `article`
  - `title`
  - `summary`
- 稿件生成器内部仍按多步调用 `outline / article / title / summary`

固定判断：

- 当前不是稳定的“5 任务架构”，也不是完全落地的“2 任务架构”
- 本轮需要把它收口成：
  1. `编辑模型`
  2. `当前默认模型`
  3. `少量任务路由`

固定目标：

- 不再让普通用户理解和配置写作流水线的内部子步骤
- 内部多步生成可以保留，但不继续作为公开任务暴露
- 现有前端 `WatchlistPanel` 仍以 `CandidateTopic[]` 为主数据源，属于旧稿件入口心智，本轮需要切换为事件级入口

### 1. 手动创作流：固定为“事件 -> 简报 -> 初稿 -> 编辑 -> 预览 -> 草稿箱”

本轮把手动创作流明确为产品主链，而不是“生成稿件”单动作。

固定手动流程：

1. 从热点簇页或预警页选择事件
2. 查看事件级写稿简报
3. 生成本地初稿
4. 进入编辑器修改标题、摘要、正文
5. 查看微信预览与风险提示
6. 推送到微信公众号草稿箱

固定手动入口：

- 热点簇页：每条 `IntelEvent` 提供 `生成稿件`
- 预警页：每条 `IntelAlert` 提供 `生成稿件`
- 稿件页：继续承担编辑、重生成、同步草稿箱、审核与状态查看

固定写稿前简报内容：

- 事件标题
- 事件摘要
- 中文翻译摘要（如有）
- `alert_state`
- `alert_reason`
- `entity_names`
- `representative_link`
- 来源数 / 平台数 / 成员数
- 最近出现时间
- `draft_ready / draft_score / draft_reason`

固定语义：

- 手动生成时，即使 `draft_ready = false` 也允许继续
- 但 UI 必须提示“证据较弱，建议人工复核”
- 后续自动化只是在这条手动链上替用户完成前半段，不另造第二条写稿链

### 2. 稿件导航层：固定为“选题池 / 稿件”两栏，不继续增加顶层导航

固定顶层导航：

1. `选题池`
2. `稿件`

固定命名决策：

- 现有导航 `重点观察` 固定改名为 `选题池`
- 不再继续使用“重点观察”作为稿件层主导航名称

固定职责边界：

- `选题池`
  - 表示“值得继续跟、可能要写、但尚未进入正式稿件生产”的事件池
  - 属于**决策层**
- `稿件`
  - 表示“已经生成本地稿件，进入编辑、审核、草稿箱流程”的内容池
  - 属于**执行层**

固定约束：

- 首版不新增第 3 个稿件层顶层导航
- `草稿箱`、`待审核`、`已同步微信`、`失败稿件` 都通过 `稿件` 页内部状态筛选解决
- 不把每个生产阶段都拆成独立导航

固定页面内筛选方向：

- `选题池`
  - 全部
  - 证据充分
  - 证据较弱
  - 已生成稿件
- `稿件`
  - 全部
  - 本地初稿
  - 已进草稿箱
  - 待审核
  - 失败

### 3. 稿件输入层：从 `intel_events` 直连稿件，不再以旧候选池为主入口

固定改法：

- 新稿件主入口来自 `intel_events`
- `intel_alerts` 只作为快捷入口，实际仍通过其 `event_id` 落到对应事件
- 旧 `candidates` / `normalized_items` 继续保留做兼容和旧功能支撑，但**不再作为稿件层主决策入口**
- `选题池` 页面不再以 `CandidateTopic[]` 为主数据源
- `选题池` 改为展示 `watchlisted=true` 的 `IntelEvent[]`

固定生成素材包（evidence pack）：

- 事件标题
- 事件摘要
- 中文翻译摘要（如有）
- `alert_state`
- `alert_reason`
- `entity_ids / entity_names`
- `representative_link`
- 代表来源列表
- `platform_count / source_count / member_count`
- 最近出现时间
- 24h 内同事件历史状态摘要（仅用于上下文，不改写主事实）

固定约束：

- 一个事件在同一个 24h 历史窗口内，默认只生成**一条稿件主记录**
- 后续再次生成时，优先视为：
  - 手动：`regenerate` 更新现有稿件
  - 自动：跳过已存在稿件，不重复灌草稿箱
- 不从 `cooled` 历史事件自动生成新稿件

### 4. 稿件准入层：新增“值得写”规则，不让热点直接等于写稿

新增事件级稿件准入字段：

- `draft_ready: bool`
- `draft_score: number`
- `draft_reason: string`
- `draft_exists: bool`
- `draft_id?: string`

固定规则主判定：

- `draft_ready = true` 需同时满足：
  - `alert_state ∈ {rising, breakout}`
  - 有 `representative_link`
  - 事件未被忽略
  - 且满足以下任一：
    - `platform_count >= 2`
    - `source_count >= 2`
    - `member_count >= 3`

固定 `draft_score` 规则化计算，范围 `0-100`：

- 以 `composite_score` 为基础
- `breakout` 加分高于 `rising`
- 跨平台、跨来源加分
- 单素材事件减分
- 缺少实体或代表链接降分

固定语义：

- **手动生成**：允许在 `draft_ready = false` 时仍可生成，但 UI 要提示“证据较弱，建议人工复核”
- **自动生成**：只处理 `draft_ready = true` 的事件
- 首页不新增复杂稿件推荐区，稿件推荐主要体现在热点页、预警页和稿件页

固定参考心智：

- 热点高不等于值得写
- 值得写是单独一层产品判断，用于把“信息层”顺畅过渡到“稿件层”

### 5. 手动链路 Phase A：先把“事件 → 初稿 → 编辑 → 微信草稿箱”打通

固定手动入口：

- 热点簇页：每条 `IntelEvent` 提供 `生成稿件`
- 预警台页：每条 `IntelAlert` 提供 `生成稿件`
- `选题池`：展示已观察事件，并提供 `生成稿件`
- 稿件台：继续保留现有稿件查看、编辑、重生成、同步草稿箱能力

固定行为：

- 点击 `生成稿件` 时，后端直接按 `event_id` 创建草稿
- 草稿生成优先复用现有 `compose_draft(...)`
- 新增事件到稿件的适配层，把 `IntelEvent` 转成稿件生成所需的 brief / facts / evidence 格式
- 草稿生成失败时，继续允许 Python 模板兜底，不阻断整轮

固定状态表达：

- `drafted`：已生成本地稿件
- **新增** `draft_synced`：已同步到微信草稿箱
- `preview_ready`：已准备预览链路
- `approved`：已人工通过
- `published`：已发布
- `failed`：失败

固定说明：

- `draft_synced` 必须和 `preview_ready` 分开，避免“只是进了草稿箱”却显示成“已可预览”
- 稿件卡片和稿件表格必须能明确看到：
  - 来源事件
  - 当前阶段
  - 是否已进微信草稿箱

### 6. 模型设置层：从旧版 5 任务残留收口为 3 层结构

本轮固定把模型设置页收口为：

1. `编辑模型`
2. `当前默认模型`
3. `任务路由`

#### 5.1 编辑模型

用于管理 provider / API Key / model_id / fallback。

固定要求：

- 每张模型卡保留显式 `编辑`
- 保留 `测试`
- 保留 `删除`
- 不再把写作内部步骤混进模型卡本身

#### 5.2 当前默认模型

用于选择当前主模型档位。

固定语义：

- 默认模型是系统主 LLM 基线
- 写作与翻译任务如果没有单独路由，则继承当前默认模型
- 切换当前默认模型时，继承关系必须即时变化

#### 5.3 任务路由

- 用户可配置的写作相关任务只保留：
  - `translation`
  - `article`

固定规则：

- `judgement` 不再与写作任务并列展示在普通设置主界面
- `judgement` 若继续保留，固定放入高级设置或情报层独立设置
- `outline / title / summary` 若继续保留内部多步生成，必须复用 `article` 路由
- 前端设置页不再把 `outline / title / summary` 暴露成独立任务下拉
- 稿件生成失败时回退模板，不阻断手动或自动链路
- 信息层的热点/预警判断不引入 LLM 主判定

固定目标：

- 解决当前写作链的任务路由漂移
- 保持“模型连接 -> 当前默认模型 -> 少量任务路由”的设置心智
- 翻译仍独立，写稿仍独立，其余子步骤不再单独暴露
- 不继续沿用旧版公开 5 任务设计

### 7. 自动链路 Phase B / C：先自动生成本地稿，再自动同步微信草稿箱

#### Phase B：自动生成本地稿件

固定触发时机：

- 只在 `radar_and_draft` / `full_pipeline` 模式下运行
- 在情报链完成后执行
- 自动稿件来源默认是：
  - `watchlisted = true`
  - `draft_ready = true`
  - `alert_state ∈ {rising, breakout}`

固定限流：

- 单轮最多生成 `draft_limit` 篇
- 排序固定为：
  - `draft_score desc`
  - `breakout` 优先于 `rising`
  - `last_seen_at desc`

固定去重：

- 同一 `event_id` 在同一 24h 历史窗口内已存在稿件则跳过
- 自动生成不覆盖用户已手工编辑过的稿件
- 已编辑稿件若事件再次升温，只允许生成“重生成建议”，不直接覆盖正文

#### Phase C：自动同步微信公众号草稿箱

固定前提：

- 只有已生成成功的自动稿件才进入同步
- 自动同步目标只到**微信草稿箱**
- 不触发正式发布按钮

固定同步规则：

- 当自动化配置里的 `draft_delivery = wechat_draft` 时，自动调用现有草稿箱同步链路
- 同步成功后，稿件阶段进入 `draft_synced`
- 同步失败：
  - 稿件保留在本地
  - `last_error` 写明失败原因
  - 允许稍后手动重试同步
  - 不删除已生成稿件

固定日志与摘要：

- 每轮执行摘要要新增：
  - `drafted_count`
  - `wechat_draft_sync_count`
  - `draft_failed_count`
- 首页与任务日志只展示摘要计数，不展示大段稿件列表

---

## Public Interfaces / Types

### 类型调整

新增或扩展以下字段：

- `IntelEvent`
  - `draft_ready`
  - `draft_score`
  - `draft_reason`
  - `draft_exists`
  - `draft_id`
- `IntelAlert`
  - `draft_ready`
  - `draft_score`
  - `draft_reason`
  - `draft_exists`
  - `draft_id`
  - 以上字段从所属事件投影
- `DraftItem`
  - `source_event_id`
  - `source_alert_level?`
  - `generation_mode: "manual" | "automation"`
  - `draft_window_id`
- `PipelineStage`
  - 新增 `draft_synced`

导航层固定调整为：

- `watchlist` 标签更名为 `选题池`
- `选题池` 页面数据主源由 `CandidateTopic[]` 切到 `watchlisted IntelEvent[]`
- `稿件` 页面继续承载 `DraftItem[]`

LLM 设置层固定收口为：

- 普通界面只公开：
  - `translation`
  - `article`
- `judgement` 若保留，归高级设置或情报层配置
- `outline / title / summary` 不再作为公开任务类型保留

### 接口调整

固定新增或扩展：

- `POST /api/admin/intel/events/{event_id}/draft`
  - 从热点事件直接生成稿件
- `选题池` 页面不再依赖旧 `/api/admin/candidates` 作为主数据源
- `选题池` 所需数据优先来自 `/api/admin/intel/events` 中的 `watchlisted` 事件
- 预警页不新增独立后端接口，直接复用 `event_id` 调用事件生成接口
- `/api/admin/intel/events`
  - 返回 `draft_*` 字段
- `/api/admin/intel/alerts`
  - 返回投影后的 `draft_*` 字段
- `/api/admin/drafts`
  - 返回 `source_event_id / generation_mode / draft_window_id`
- 现有 automation/runtime 摘要
  - 增加稿件与微信草稿箱同步统计字段

模型设置相关接口固定兼容以下语义：

- 前端保存时不再要求提交公开的 `outline / title / summary` 路由
- 后端如仍保留内部多步生成，内部子步骤统一映射到 `article`

---

## Test Plan

### 1. 手动生成链路
- 从热点页点击 `生成稿件` 可成功创建草稿
- 从预警页点击 `生成稿件` 可成功创建草稿
- 从 `选题池` 点击 `生成稿件` 可成功创建草稿
- 生成前可看到写稿简报与“证据较弱 / 证据充分”提示
- 同一事件重复点击时默认进入重生成/复用逻辑，不出现无穷重复稿件
- LLM 不可用时仍能模板兜底生成本地稿件

### 2. 导航与职责
- 顶层稿件相关导航固定只有 `选题池 / 稿件`
- 不新增第 3 个顶层稿件导航
- `选题池` 展示已观察的事件，不再展示旧 `CandidateTopic` 候选池
- `稿件` 展示正式稿件及其状态流转

### 3. 稿件准入规则
- `rising / breakout` 且跨源事件能得到 `draft_ready = true`
- 单来源单素材弱事件默认 `draft_ready = false`
- 手动仍可强制生成
- 自动模式只处理 `draft_ready = true`

### 4. 模型设置收口
- 设置页主界面不再显示 `outline / title / summary`
- 普通用户只看到 `translation / article`
- 当前默认模型切换后，未单独路由的任务会正确继承
- 模型卡保留编辑、测试、删除等基础操作

### 5. 自动本地成稿
- `radar_and_draft` 下可自动从合格事件生成本地稿件
- 同一 24h 事件窗口不会重复生成多条自动稿件
- 用户已编辑过的稿件不会被自动覆盖
- 每轮 `drafted_count` 统计准确

### 6. 自动同步微信草稿箱
- `draft_delivery = wechat_draft` 时自动同步成功进入 `draft_synced`
- 同步失败时稿件仍保留本地，且可手动重试
- 不会自动进入正式发布
- `wechat_draft_sync_count` 统计准确

### 7. 路由与状态
- 设置页只暴露 `translation` 与 `article` 两类写作任务
- `judgement` 不再与写稿任务并列显示
- 内部 `outline / title / summary` 子步骤如存在，统一走 `article`
- `drafted`、`draft_synced`、`preview_ready` 在 UI 上区分清楚
- 自动模式完成后，首页/任务日志能正确显示“生成了几篇稿、推送了几篇微信草稿”

### 8. 兼容与回归
- 旧 `DraftItem` 没有新字段时可按默认值兼容
- 旧 `CandidateTopic` 相关能力仅做兼容保留，不再作为稿件层主入口
- 旧稿件列表、编辑器、预览链路不崩
- 不影响现有热点、预警、24h 保留层、实体筛选、翻译展示

---

## Assumptions

- 最终目标是**全自动到微信公众号草稿箱**，不是全自动正式发布
- 推进节奏固定为：**手动先通，再自动化**
- 自动稿件首版默认只处理 `watchlisted` 且 `rising/breakout` 的事件
- 本轮不引入 embedding 聚类、向量库、LLM 热点主判定
- 稿件主输入固定从 `intel_events` 来，不再以旧 `candidates` 作为主入口
- 写作链对普通用户暴露的任务配置固定只保留 `translation` 和 `article`
- `judgement` 若保留，归高级设置或情报层配置，不与写作任务并列
- 稿件层顶层导航固定只保留 `选题池 / 稿件` 两个
