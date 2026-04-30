# Auto News Studio PLAN13-R1：正文深挖与简报交付落地计划

## Summary

本轮继续保持“先不重做首页热点发现系统、先不打通现有 4 种调度模式”的边界，集中把热点发现后的后半段做成一条稳定新链：

**`IntelEvent -> 正文深挖 -> 简报 -> 微信草稿箱`**

固定目标：

- 用**确定性正文抓取**替代“长稿生成器”做主链
- 用**结构化简报**替代“公众号长文初稿”做主交付
- 正文深挖完成后**直接喂 AI 生成简报**
- 前端继续保留两栏，但重命名为：
  - `深挖池`
  - `简报`
- 自动化终点仍是**微信公众号草稿箱**
- 默认微信投递链路固定为：**浏览器链路优先**
- 旧 `CandidateTopic / DraftItem / composer.py` 先兼容保留，等新链稳定后再分阶段删除

固定范围：

- 本轮只把“正文深挖 + 简报交付”单独打通并测稳
- 不在本轮把首页已有调度模式直接接到新链
- 不再以 `CandidateTopic` 作为新链主入口
- 新链主入口固定为 `IntelEvent`

---

## Key Changes

### 1. 数据主线：保留浅证据包做输入，深挖结果成为下游权威证据

当前 `_event_evidence_pack()` 已经存在，首版不删除，但重新定义职责：

- **浅证据包 `evidence_pack`**：
  - 仍作为事件级“快速证据种子”
  - 来源于 `discovery_items`
  - 用于热点页、预警页、深挖前概览
- **深挖结果 `EventDeepDive`**：
  - 作为 `evidence_pack` 的**升级版权威替代**
  - 下游 AI 简报生成、复制来源包、微信交付都固定读取深挖结果
  - 不再以浅 `evidence_pack` 作为最终 AI 输入

固定语义：

- 深挖成功后，**下游消费层视深挖结果为主证据**
- 浅 `evidence_pack` 不做 destructive 覆盖删除，只保留为前置输入和兼容回退
- 深挖失败或部分失败时，允许回退读取浅证据包，但必须明确标注“仅摘要证据，未完成正文核验”
- 对外产品层不单独引入“结构化材料包”概念；正文深挖结果直接作为 AI 简报生成输入

### 2. 正文深挖层：新增独立存储，不把状态硬塞进 `IntelEvent`

新增独立运行态集合：

- `event_deep_dives`
- 每条记录对应一个 `event_id`

固定存储结构：

- `EventDeepDive`
  - `id`
  - `event_id`
  - `status`
  - `started_at / finished_at / updated_at`
  - `attempted_count / success_count / failed_count`
  - `resolved_evidence_pack`
  - `full_text_sources`
  - `facts`
  - `quotes`
  - `timeline`
  - `worthiness`
  - `last_error`
- `DeepDiveSourceItem`
  - `source_key / source_name`
  - `original_link / canonical_link`
  - `title / published_at`
  - `fetch_status`
  - `extract_status`
  - `word_count`
  - `cleaned_full_text`
  - `excerpt`
  - `quotes`
  - `error`

固定 `IntelEvent` 只新增轻量指针，不再膨胀一堆字段：

- `deep_dive_id?: string | null`
- `brief_id?: string | null`

如前端需要状态展示，则由接口**运行时投影**：

- `deep_dive_status`
- `brief_status`
- `deep_dive_summary`

但这些不作为 `IntelEvent` 持久化真相。

### 3. 正文提取策略：双提取器，规则优先，不用 AI 卡主链

首版正文深挖固定技术策略：

- 抓取：`httpx`
- 正文提取主力：`trafilatura`
- 正文提取兜底：`readability-lxml`

固定流程：

1. 用 `resolved_evidence_pack` 的候选链接逐条抓取 HTML
2. `trafilatura` 先提取正文
3. 失败或正文过短时切 `readability-lxml`
4. 两者都失败则记 `extract_failed`
5. 非 HTML、登录墙、重定向异常、超时分别落明确错误态

固定产物：

- 深挖层的主产物不是“摘录集合”，而是**清洗后的完整正文集合**
- `excerpt / quotes / facts / timeline` 都是基于完整正文再做的派生结果
- 后续 AI 读取时，默认优先读取 `cleaned_full_text`

固定约束：

- 本轮**不做浏览器辅助正文抓取**
- 微信文章、知乎专栏、强登录站点若抓不到，明确记为 `fetch_blocked` 或 `extract_failed`
- AI 不参与正文提取主链
- 深挖允许 `partial`，不要求全源成功

固定抓取规模：

- 单事件默认**尽量全抓**
- 但必须有两层保护：
  - 单链接超时上限
  - 单事件总时长 / 总链接数上限
- 超上限后停止追加抓取，并把结果标为 `partial`

### 4. 简报生成：分“规则简报 / 增强简报”两级，LLM 只做增强

新增独立集合：

- `briefs`

新增主类型：

- `BriefItem`
  - `id`
  - `event_id`
  - `deep_dive_id`
  - `brief_level: "rule" | "enhanced"`
  - `stage: "prepared" | "synced" | "failed"`
  - `title`
  - `one_line`
  - `why_it_matters`
  - `facts`
  - `quotes`
  - `timeline`
  - `entity_names`
  - `source_links`
  - `risk_notes`
  - `prompt_package_markdown`
  - `wechat_markdown`
  - `wechat_html`
  - `last_error`
  - `updated_at`

固定两级语义：

#### 规则简报
不依赖 LLM，必可生成：

- 事件标题
- 时间线
- 事实列表
- 正文摘录
- 关键引文
- 来源链接
- 风险说明
- 证据不足提示

#### 增强简报
正文深挖完成后，直接把深挖结果喂给 AI；LLM 可用时尝试补充：

- 一句话结论
- 为什么值得关注
- 更自然的风险提示

固定降级规则：

- LLM 成功 -> `brief_level = enhanced`
- LLM 不可用或失败 -> 自动降级为 `rule`
- 不允许因为增强失败而阻断规则简报生成

固定 AI 输入：

- 不喂原始网页 HTML
- 不只喂截断摘要
- 固定喂“正文深挖后的完整正文与派生证据”，至少包含：
  - 事件标题
  - 一句话背景
  - 多来源 `cleaned_full_text`
  - 已核验事实
  - 关键引文
  - 时间线
  - 来源链接
  - 风险与不确定性

### 5. “是否值得交付”规则：深挖后再做一次准入，不把所有热点都发走

新增事件后验判断：

- `worth_to_brief`
- `worth_reason`

固定准入逻辑：

- 上游事件仍沿用现有规则评分与 alert 状态
- 深挖完成后再补一层正文证据判断
- 自动生成简报至少要求：
  - `alert_state ∈ {rising, breakout}` 或进入人工观察池
  - 深挖成功来源数达到最小阈值
  - 有可用完整正文或可引用正文
- 证据过弱时：
  - 可手动生成简报
  - 自动链路默认跳过

### 6. 前端：不是只改名字，而是把两栏真正换成新职责

#### 深挖池
现有 `WatchlistPanel` 升级为 `DeepDivePoolPanel`，主数据源仍是：

- `watchlisted = true` 的 `IntelEvent[]`

固定展示：

- 事件标题 / 摘要
- 热度与预警状态
- 深挖状态
- 成功/失败来源数
- 最近深挖时间
- 是否已有简报

固定动作：

- `立即深挖`
- `重新深挖`
- `生成简报`
- `查看来源`

热点簇页、预警页按钮统一改为：

- `加入深挖池`
- `立即深挖`

不再以“生成稿件”为主入口文案。

#### 简报
现有 `DraftTable` 不再继续扩成“长稿中心”，而是改成 `BriefTable / BriefDetail` 心智。

固定页面能力：

- 列表筛选：
  - `全部`
  - `待同步`
  - `已进草稿箱`
  - `失败`
- 卡片/表格展示：
  - 简报标题
  - 结论
  - 事实条数
  - 来源数
  - 简报级别
  - 微信状态
  - 最近错误
- 动作：
  - `查看简报`
  - `重新生成`
  - `同步微信草稿箱`
  - `复制简报`
  - `复制来源包`

固定兼容策略：

- 旧稿件编辑器与旧 `DraftItem` 页面逻辑先保留代码壳
- 但从顶层导航移出主心智
- 不再继续给旧稿件页加新能力

### 7. 复制来源包：固定给 Codex / Claude Code 的 prompt 模板

“复制来源包”必须输出固定 Markdown 模板，首版格式固定为：

```md
## 写作任务
基于以下已核验素材，写一篇公众号文章。

## 事件标题
{title}

## 一句话结论
{one_line_or_fallback}

## 为什么值得关注
{why_it_matters_or_fallback}

## 已抓取完整正文
来源：{source_name}
正文：
{cleaned_full_text_or_truncated_full_text}

## 核心事实
- ...
- ...

## 正文摘录
来源：{source_name}
> ...

## 关键引文
> ...

## 时间线
- ...

## 风险与不确定性
- ...

## 来源链接
- ...
- ...
```

固定规则：

- 一键复制时输出完整模板
- 若没有增强简报字段，则用规则简报内容补位
- 若单篇正文过长，可按来源分段截取，但输入基础必须来自已抓取完整正文
- 该来源包直接面向“复制给 Codex / Claude Code / 其他外部 AI 写长文”

### 8. 微信交付：简报进草稿箱，默认浏览器链路优先

固定交付物：

- 微信收到的是**简报内容**
- 不是长稿成文

固定默认链路：

- 手动 / 自动同步简报到微信草稿箱时：
  - 默认走现有浏览器链路
- `wechat-sidecar` 官方 API 保留，但只作为后续增强位

固定阶段：

- `prepared`
- `synced`
- `failed`

固定约束：

- 不自动正式发布
- 同步失败保留本地简报
- 写入 `last_error`
- 允许手动重试同步

### 9. 旧框架清理：必须等新链跑通后分阶段删

#### Phase A：并存
保留：

- `CandidateTopic`
- `DraftItem`
- `/api/admin/candidates`
- `/api/admin/drafts`
- `compose_draft` 长稿链

新增：

- `event_deep_dives`
- `briefs`

#### Phase B：前端切主
顶层导航切为：

- `深挖池`
- `简报`

旧稿件逻辑降为兼容层。

#### Phase C：新链单独跑通
只验证：

- `IntelEvent -> DeepDive -> Brief -> WeChatDraft`

不先接现有首页调度。

#### Phase D：删除旧框架
新链稳定后再删：

- `CandidateTopic` 的前台主入口职责
- `/api/admin/candidates` 的 UI 主依赖
- `DraftItem` 的长稿主职责
- `composer.py` 的 outline/article/title/summary 链
- 旧“生成稿件”相关按钮文案与工作台逻辑

### 10. 中转站固定格式配置化：从“探测对象”升级为“固定协议对象”

在新链里，AI 不再承担“从零写长稿”的主链职责，但 `增强简报`、模型测试、后续外部 AI 协作仍然需要一条**稳定、可解释、可复用**的模型运行链。  
本轮调研结论明确：对于 `CC-Switch` 导入的中转站，不能一直把它当成“每次运行前都要重新猜协议的探测对象”，而应逐步升级为和官方模型一样的**固定运行配置对象**。

#### 调研结论

- `CC-Switch` 自身已经把以下字段作为一等语义：
  - `apiFormat`
  - `isFullUrl`
  - `endpointAutoSelect`
- 当前项目后端也已经保留并消费了这批元数据：
  - `cc_api_format`
  - `cc_is_full_url`
  - `cc_endpoint_auto_select`
  - `cc_endpoint_candidates`
  - `cc_last_verified_endpoint`
  - `cc_last_verified_format`
  - `cc_last_verified_model`
- 实测表明，部分中转站虽然原始导入配置里 `model_id` 为空，但经过一次真实协议验证后，可以稳定收敛到明确运行路由。

已验证样本：

- `小熊API`
  - 原始导入：
    - `cc_app_type = claude`
    - `cc_api_format = anthropic`
    - `base_url = https://api.xxdlzs.top`
    - `model_id = ""`
  - 实测可用运行路由：
    - `resolved_format = openai_responses`
    - `resolved_endpoint = https://api.xxdlzs.top/v1/responses`
    - `resolved_model = claude-sonnet-4-6`

这说明：

- “中转站声明格式”与“最终可用格式”可能不同
- 但一旦验证成功，就应该允许把该结果**固化为运行真相**
- 不应每次都隐式重新探测，更不应让 UI 只显示“测通过了”，却不说明真正跑的是哪条协议路由

#### 固定设计

新增一层“固定运行路由”心智，适用于所有 `source = cc-switch` 的 profile：

- `cc_route_mode?: "auto_probe" | "pinned"`
- `cc_pinned_endpoint?: string | null`
- `cc_pinned_format?: "openai_chat" | "openai_responses" | "anthropic" | "gemini_native" | null`
- `cc_pinned_model?: string | null`
- `cc_probe_last_success_at?: string | null`

固定语义：

- `auto_probe`
  - 保留当前探测逻辑
  - 适合刚导入、尚未验证或仍在试错的中转站
- `pinned`
  - 以固定端点 + 固定协议 + 固定模型作为运行真相
  - 适合已经验证稳定可用的中转站

固定原则：

- `probe` 是**引导与校验工具**
- `pinned route` 才是**稳定运行配置**
- 一旦用户确认固化，运行时默认优先走固定路由，不再把“重新猜测协议”当成常规路径

#### 运行时规则

当 profile 为 `source = cc-switch` 时，运行时按以下优先级解析：

1. 若 `cc_route_mode = pinned` 且 `cc_pinned_endpoint / cc_pinned_format / cc_pinned_model` 完整：
   - 直接使用 pinned route
2. 若 pinned 不完整：
   - 回退到 `cc_last_verified_*`
3. 若尚无 verified route：
   - 才进入 `auto_probe` / 候选端点探测逻辑

固定约束：

- pinned route 失败时，要返回**明确错误**，而不是静默改写配置
- 运行失败不自动覆盖用户的 pinned 配置
- 只有用户主动重新测试并确认，或显式点击“用当前验证结果覆盖固定路由”时，才更新 pinned 字段

#### 产品层语义

固定产品判断：

- 官方模型与中转站模型最终都应表现为“可运行 profile”
- 区别只在于来源不同，不在于运行时要不要被特殊化对待
- 对用户而言，最重要的不是“这是 Claude/Codex/Gemini 来源”，而是：
  - 现在到底用什么协议
  - 发到哪个端点
  - 用哪个模型
  - 它是否真的能用于生成

这意味着设置页后续应把“中转站探测成功”升级为更真实的状态表达：

- `声明格式`
- `最近验证格式`
- `固定运行格式`
- `固定运行端点`
- `固定运行模型`
- `当前模式：自动探测 / 固定路由`

#### UI / 交互优化方向

保持左侧模型卡片不动，但右侧详情区后续新增中转站专属信息块：

- `来源：CC-Switch`
- `声明协议`
- `是否完整 URL`
- `是否自动选端点`
- `最近验证结果`
- `固定运行路由`

新增动作建议：

- `测试并验证`
- `固化当前已验证路由`
- `切回自动探测`

固定交互规则：

- “测试通过”必须区分：
  - 仅连接可达
  - 可真实用于生成
- 当 profile 处于 `pinned` 模式时，测试结果应明确说明：
  - 当前测试的是固定路由
  - 还是临时探测出的其他候选路由

#### 与 PLAN13 新链的关系

这项优化不改变 `PLAN13-R1` 的产品边界，但会直接增强三条后链稳定性：

1. `增强简报`
   - 需要更稳定的模型调用路径
2. `正文深挖后直接喂 AI`
   - 需要更稳定的完整正文输入消费路径
3. `复制来源包后的人机协作`
   - 需要用户清楚知道当前可用模型链路
4. 后续“简报自动同步微信草稿箱前的 AI 增强”
   - 不能建立在不透明的探测结果之上

固定边界：

- 规则简报仍然必须不依赖 AI
- pinned route 优化只增强 AI 能力的可靠性
- 不让中转站不稳定反过来污染信息层和深挖层主链

#### 迁移策略

对已有 `CC-Switch` profile，采用加法兼容迁移：

- 保留现有：
  - `cc_last_verified_endpoint`
  - `cc_last_verified_format`
  - `cc_last_verified_model`
  - `cc_probe_status`
  - `cc_probe_message`
- 新增 pinned 字段，但首版不强制自动写入
- 对 `probe_status = verified` 的 profile，UI 可提示：
  - “检测到可用已验证路由，是否固化为固定运行路由？”

默认迁移建议：

- 已验证且用户已实际设为默认模型的 profile，可优先提示固化
- 未验证 profile 保持 `auto_probe`
- 非 CC profile 完全不受影响

#### Phase 建议

##### Phase E1：固定路由能力建模

- 扩展 `LLMProfileConfig`
- 新增 pinned route 字段
- API 读写支持这些字段
- 前端类型同步

##### Phase E2：测试链与运行时收口

- 测试链允许“将本次已验证路由固化”
- 运行时优先读取 pinned route
- 明确区分 pinned failure 与 probe failure

##### Phase E3：设置页状态说真话

- 展示声明协议 / 已验证协议 / 固定协议
- 增加“固化当前已验证路由”动作
- 增加“切回自动探测”动作

##### Phase E4：样本回归

- 用已验证中转站做回归样本：
  - `小熊API`
  - `Codex 直连中转`
  - 其他导入的 CC provider

该阶段目标不是“让所有中转站都神奇可用”，而是：

- 已验证可用的，可以稳定复用
- 不可用的，要明确报错
- UI 和运行时对外说的是同一套真相

---

## Public Interfaces / Types

### 新增接口

- `POST /api/admin/intel/events/{event_id}/deep-dive`
- `GET /api/admin/intel/deep-dives`
- `GET /api/admin/intel/deep-dives/{event_id}`
- `POST /api/admin/intel/events/{event_id}/brief`
- `GET /api/admin/briefs`
- `GET /api/admin/briefs/{brief_id}`
- `POST /api/admin/briefs/{brief_id}/wechat-draft`
- `POST /api/admin/briefs/{brief_id}/copy-package` 可只返回模板字符串，不必真做剪贴板后端

### 接口投影调整

`/api/admin/intel/events` 与 `/api/admin/intel/alerts` 可加法返回轻量投影：

- `deep_dive_id`
- `brief_id`
- `deep_dive_status?`
- `brief_status?`

但深挖与简报详情固定从独立接口读取，不再把大对象塞进事件列表响应。

### 新增依赖

后端新增：

- `httpx`
- `trafilatura`
- `readability-lxml`

### 中转站配置扩展（后续优化）

`LLMProfileConfig` 后续新增：

- `cc_route_mode?: "auto_probe" | "pinned"`
- `cc_pinned_endpoint?: string | null`
- `cc_pinned_format?: "openai_chat" | "openai_responses" | "anthropic" | "gemini_native" | null`
- `cc_pinned_model?: string | null`
- `cc_probe_last_success_at?: string | null`

`LLMTestResult` 后续补充表达：

- `declared_format`
- `verified_format`
- `pinned_format`
- `resolved_endpoint`
- `resolved_model`
- `supports_generation`

---

## Test Plan

### 1. 深挖层
- 事件可从深挖池手动触发正文深挖
- 单事件多链接可尽量全抓，但受总链接数与总时长保护
- `trafilatura` 失败后能自动切 `readability-lxml`
- 非 HTML、登录墙、超时、提取失败能明确分类
- 深挖允许 `partial`，不会因为单源失败整事件失败

### 2. 简报层
- 深挖完成后可生成规则简报
- LLM 可用时，深挖结果可直接喂给 AI 升级为增强简报
- LLM 不可用时自动降级，不阻断简报生成
- AI 输入基于完整正文，不是只基于摘录
- 简报包含事实、摘录、引文、时间线、来源链接
- 复制来源包时输出固定 prompt 模板

### 3. 前端
- 顶层两栏已改为 `深挖池 / 简报`
- 热点簇 / 预警页按钮已改为深挖语义
- 深挖池能显示状态、来源覆盖、简报状态
- 简报页能查看、复制、同步、重试、筛选失败项
- 不再把“生成稿件”作为主文案

### 4. 微信草稿箱
- 浏览器登录态正常时，简报可进入微信草稿箱
- 同步失败时简报仍保留本地
- 不自动正式发布
- 官方 API 未配置时不阻断浏览器链路

### 5. 兼容与回归
- 不影响现有 `IntelEvent / IntelAlert / 24h 历史层`
- 不影响现有热点发现与预警判定
- 旧 `CandidateTopic / DraftItem` 相关接口仍可工作至清理阶段
- 首页 4 种调度模式本轮不重写、不强接新链

### 6. 中转站固定路由优化
- `CC-Switch` 导入 profile 后，声明格式、完整 URL 标志、自动选端点标志可完整保留
- 已验证的中转站可从 `verified route` 提升为 `pinned route`
- `pinned` 模式下运行时不再每次重新探测协议
- `pinned route` 失败时返回明确错误，不静默改写配置
- `auto_probe` 与 `pinned` 两种模式切换后，测试结果与运行路径保持一致
- `小熊API` 可作为样本固化为：
  - `pinned_format = openai_responses`
  - `pinned_endpoint = https://api.xxdlzs.top/v1/responses`
  - `pinned_model = claude-sonnet-4-6`
- 非 CC profile 与官方 provider 不受影响

---

## Assumptions

- 本轮固定先做“正文深挖 + 简报交付”，不先接首页调度自动化
- 深挖结果是下游权威证据，浅 `evidence_pack` 仅做输入与兼容
- 不单独把“结构化材料包”作为产品层产物；正文深挖结果直接作为 AI 输入
- 简报分为 `rule / enhanced` 两级，规则简报必须不依赖 LLM
- 正文提取首版固定 `trafilatura + readability-lxml`
- 深挖默认“尽量全抓”，但必须有事件级保护上限
- 模型不具备联网能力，因此 AI 主输入必须包含已抓取并清洗的完整正文
- 微信草稿箱默认浏览器链路优先，官方 API 留作后续增强
- 旧稿件系统只做过渡兼容，等新链稳定后再删
- `CC-Switch` 是长期配置中心，中转站协议语义以其 `apiFormat / isFullUrl / endpointAutoSelect` 为准
- 对中转站而言，“最近验证成功”不等于“固定运行真相”；后续需要显式 pinned route 语义
