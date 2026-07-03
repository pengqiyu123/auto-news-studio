# Agent 每日工作流 Runbook

本文件给外部 AI 使用，按“每天从采集到微信草稿”的真实 API 顺序执行。它补充 `AGENT.md`，重点说明容易被误解的接口语义。

最后校准时间：2026-06-22

## 为什么其他 AI 容易失败

当前接口有几个不够直觉的地方：

1. `POST /api/admin/agent/articles` 同时承担“保存文章”和“可选上传微信”两个职责。对新 AI 来说，如果上传失败，很容易误以为整篇文章保存失败，或者反过来把本地保存成功当成微信上传成功。
2. `AgentArticlePayload.event_id` 是必填单值，但 5 条短讯合集天然包含多个事件。当前正确做法是把它当作“主事件锚点”，不是把 5 个事件都塞进去。
3. 上传失败后不需要删除本地文章。只要拿到已保存的 `brief_id`，就可以重新调用微信草稿同步接口。
4. `sidecar_health=offline` 不是微信上传失败的唯一或直接根因。这个字段在当前实现中常常只是历史/兼容状态。判断浏览器可用性应看 `logged_in`、`manager_alive`、`last_error`、`last_reset_reason`、`current_page` 和真实打开/检查接口结果。
5. **“深挖”的责任主体是 Agent 自己，不是后端爬虫**。`POST /events/{id}/deep-dive` 只是辅助，对微信公众号、36kr、IT之家等反爬严格的源站会返回“没拿到正文”。Agent 必须用自己的 `WebSearch` / `WebFetch` 工具主动检索补全，**不要因为后端深挖失败就放弃事件**。详见“阶段6 深挖”章节。
6. 微信公众平台登录态在长时间运行后会过期。`logged_in=false` 是正常事件，**不是终止信号**——按"上传失败后的重试"章节流程，让用户扫码重登后用**同一 brief_id** 重试即可。

## 推荐总原则

- 一步一验，不要把采集、写作、保存、上传放进一个无法恢复的大动作。
- 保存文章和上传微信分开做。
- 所有真实平台动作都要带 `triggered_by=agent`。
- 任何一步失败时，先保留现场和本地记录，不要删除。

## 标准执行顺序

### 1. 启动与健康检查

```powershell
cd D:\python\Auto-news2\auto-news-studio
.\stop.bat
.\start.bat
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 10
```

成功标准：

```text
status = ok
```

### 2. 停止传统调度器

不要启动传统 runtime。Agent 模式只做一次性 API 操作。

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/admin/runtime/stop?triggered_by=agent' -TimeoutSec 30
```

如果该接口不可用或返回已停止，不影响继续。

### 3. 采集信息源

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/admin/sources/sync?triggered_by=agent' -TimeoutSec 180
```

成功标准：

```text
HTTP 200
raw_count / normalized_count / event_count 可解析
warnings 如非空，要记录为部分成功
```

### 4. 读取事件池

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/admin/intel/events?page=1&page_size=50' -TimeoutSec 60
```

响应是分页结构：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 50,
  "has_more": false
}
```

不要把空数组、解析失败、字段路径错当成“今天没有新闻”。

### 5. 选择输出形态

Agent 自己做编辑判断：

- 不写：素材弱、重复、过期、证据不足。
- 5 条短讯合集：正好 5 个事件，写成一篇连贯文章。
- 长文：单个重大事件，多来源、有分析价值。
- 混合：一个长文加一篇 5 条短讯合集。

用户明确指定时，先满足用户指定形态。

### 6. 深挖事件

⚠️ **核心原则：深挖的责任主体是 Agent，不是后端爬虫**。

后端 `POST /events/{id}/deep-dive` 仅作为辅助，它的 HTTP 抓取器对微信公众号、36kr、IT之家等反爬严格的源站会返回"没拿到正文"。

**正确的深挖流程（2026-06-22 起强制执行）**：

1. 先调用后端深挖：

   ```powershell
   Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/admin/intel/events/<event_id>/deep-dive?triggered_by=agent' -TimeoutSec 180
   ```

2. 检查后端深挖结果：
   - `facts`/`quotes`/`sources` 非空 → 接受，继续
   - 返回"没拿到正文"或素材不足 → **这是正常情况，不要放弃事件**

3. **Agent 主动用搜索补全素材（必做）**：

   - 用 `WebSearch` 搜索事件标题 + 关键词（通常搜 2-3 轮不同关键词组合）
   - 对搜索结果中的新链接用 `WebFetch` 抓取可读正文
   - 从新正文提取事实、引语、数字、时间线
   - 优先选驱动之家、手机中国、搜狐科技等静态 HTML 站，它们抓取成功率高
   - 同一事件要搜到至少 3 个不同媒体来源做交叉验证

4. 合并：后端返回的素材 + Agent 自己搜到的素材 → 形成最终素材池

5. 素材池里每条事实都要标注来源链接。

**成功标准（最终是看 Agent 素材池，不是看后端深挖接口）**：

```text
- 单条事件至少有 3 篇不同报道可交叉验证
- 时间、地点、人物、数字、影响五要素齐全
- 每条事实有来源链接
```

如果是 5 条短讯合集，5 个事件都应按上述流程完成深挖。**后端深挖失败不构成放弃事件的理由**，用搜索补全。

如果后端深挖失败且 WebSearch 也搜不到有效信源（极罕见），再考虑换其他事件。

### 7. 可选：生成本地素材 brief

这一步用于素材跟踪，不是最终上传稿。

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/admin/intel/events/<event_id>/brief?triggered_by=agent' -TimeoutSec 120
```

注意：

- 这个 brief 通常是 `brief_level=rule`。
- Agent 不应把传统 brief 当最终微信稿上传。
- 最终文章必须通过 `POST /api/admin/agent/articles` 保存。

### 8. 写作与 Critique

写作要求：

- 5 条短讯合集必须正好 5 条，不是单事件短文。
- 微信平台稿不能保留 `## 1.`、`## 来源链接`、`核心事实`、`这意味着什么` 这类后台格式。
- 必须先完成 Critique，再保存。

Critique 至少检查：

- 事实、数字、日期、人名、引文可追溯。
- 每条新闻有“发生了什么 / 为什么值得看 / 还不确定什么”。
- 标题、摘要、导语和结尾符合公众号阅读场景。
- 没有把猜测写成确定事实。
- 没有明显 AI 腔、机械列表或重复段落结构。

### 9. 保存 Agent 文章

推荐先只保存本地文章，不在这个请求里上传微信：

```json
{
  "event_id": "<主事件 event_id>",
  "title": "<文章标题>",
  "article_markdown": "<最终平台稿 Markdown>",
  "summary": "<40-60字摘要>",
  "one_line": "<一句话结论>",
  "why_it_matters": "<为什么值得关注>",
  "facts": ["事实1", "事实2"],
  "quotes": [],
  "timeline": [],
  "entity_names": [],
  "source_links": [],
  "risk_notes": [],
  "publish_to_wechat_draft": false,
  "publish_to_douyin_article": false,
  "triggered_by": "agent",
  "driver_label": "<ai-name>"
}
```

调用：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8000/api/admin/agent/articles' `
  -ContentType 'application/json' `
  -Body $body `
  -TimeoutSec 180
```

成功标准：

```text
item.id 存在
item.brief_level = article
item.workflow_mode = agent
item.stage = prepared 或 local_only 相关状态
```

保存成功后，把 `item.id` 记录为后续上传用的 `brief_id`。

## 5 条短讯合集的 event_id 规则

`POST /api/admin/agent/articles` 目前只接受一个 `event_id`。对于 5 条短讯合集：

- 使用第一条/主标题/最高优先级事件作为 `event_id`。
- 这个 `event_id` 是兼容锚点，用于关联 deep-dive、workflow 和文章记录。
- 其他 4 个事件的事实、来源和实体写入 `facts`、`source_links`、`entity_names` 和正文。
- 不要为了“获取 event_id”去创建或删除额外 brief。
- 不要把传统 `brief_level=rule` 记录当成最终 Agent 文章。

长期更理想的接口是新增 `primary_event_id` 和 `included_event_ids`，但当前版本按上述规则执行。

### 10. 上传到微信草稿箱

保存成功后，用返回的 `brief_id` 单独上传：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8000/api/admin/briefs/<brief_id>/wechat-draft?triggered_by=agent' `
  -TimeoutSec 420
```

成功标准：

```text
item.stage = synced
item.delivery_status = verified 或 uploaded_unverified
item.last_error 为空，或明确说明只差草稿箱二次验证
```

如果接口返回 HTTP 200 但 `item.stage=failed` 或 `item.last_error` 非空，不能说上传成功。

## 上传失败后的重试

不要删除本地文章。

按顺序做：

1. 记录失败响应中的 `item.id`、`item.title`、`item.last_error`、`item.delivery_status`。
2. 检查浏览器会话：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/admin/browser/wechat/session' -TimeoutSec 60
```

3. 如果浏览器刚经历 `with_session_failed`、`manager_alive=false`、导航超时或当前页异常，先打开并检查微信后台：

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/admin/browser/wechat/open-dashboard' -TimeoutSec 120
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/admin/browser/wechat/check' -TimeoutSec 120
```

4. 登录态正常后，重新调用：

```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/admin/briefs/<brief_id>/wechat-draft?triggered_by=agent' -TimeoutSec 420
```

如果忘记了 `brief_id`，用标题找回：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/admin/briefs?page=1&page_size=20&workflow_mode=agent&q=<标题关键词>' -TimeoutSec 60
```

## sidecar_health 的解释

`sidecar_health=offline` 不一定表示微信浏览器不可用。当前实现中，微信浏览器主要由项目内 `WechatBrowserManager` 维护。

更重要的字段：

- `logged_in`
- `manager_alive`
- `busy`
- `last_error`
- `last_reset_reason`
- `last_action`
- `last_action_phase`
- `current_page`
- `resident_page`

如果遇到：

```text
Page.goto: Timeout 30000ms exceeded navigating to https://mp.weixin.qq.com/
last_reset_reason = with_session_failed
```

优先处理为浏览器会话/页面导航失败：

1. `open-dashboard`
2. `check`
3. 必要时 `stop.bat` / `start.bat`
4. 重新用已有 `brief_id` 调用微信草稿同步

不要仅凭 `sidecar_health=offline` 判定根因。

## 发表前确认

文章进入微信草稿箱后，如需继续点击到二维码，按：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri 'http://127.0.0.1:8000/api/admin/briefs/<brief_id>/wechat-publish?triggered_by=agent' `
  -TimeoutSec 420
```

详细按钮路径见：

```text
docs/WECHAT_AGENT_PUBLISH_RUNBOOK.md
```

成功到二维码后只能记为：

```text
delivery_status = pending_confirmation
last_error = 已到微信验证二维码，请扫码确认。
```

这不是已发布。

## 最小成功报告模板

```text
采集：成功，event_count=<n>
深挖：后端 <a>/<b>，WebSearch 主动补全 <c> 个事件，最终可写事件 <d> 个
写作：完成，Critique 通过
保存：成功，brief_id=<brief-id>
微信草稿：成功/失败，stage=<stage>, delivery_status=<status>, last_error=<error>
发表前确认：未执行 / 已到二维码 pending_confirmation / 失败
发表后验证：delivery_status=published 且 publish_record_published_at 有值 / 未验证 / 失败
```

## 今日教训沉淀（2026-06-22）

| 教训 | 错误做法 | 正确做法 |
|------|---------|---------|
| 深挖责任 | 把后端 `/deep-dive` 当唯一深挖手段，失败即放弃事件 | 后端只是辅助；Agent 必须用 WebSearch/WebFetch 主动补全 |
| 微信登录态 | `logged_in=false` 时反复重启浏览器/服务 | 直接通知用户扫码重登，登录后用同一 brief_id 重试 |
| 5 条短讯合集 | 后端深挖失败就缩成单稿 | 用 WebSearch 救活每条事件，坚持 5 条均衡的合集形态 |
| 来源选择 | 不管源站类型一律调爬虫 | 优先静态站（驱动之家、cnmo、搜狐科技），微信原文链接默认跳过 |
