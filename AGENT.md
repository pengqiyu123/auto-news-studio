# AGENT.md

This file is for external AI coding tools that can read the repository and drive the project directly.

`AGENTS.md` is the short entry and guardrail file. This file is the long operating manual. Keep detailed API maps, workflow procedures, and writing rules here; keep only high-priority rules in `AGENTS.md`.

For daily Agent execution, read `docs/AGENT_DAILY_WORKFLOW_RUNBOOK.md` after this file. It is the ordered runbook for collection, deep dive, writing, saving, WeChat draft upload, and retry recovery.

The project has two data stores:

- **PostgreSQL** — primary ledger (when `STATE_BACKEND=postgres` or `dual_write`)
- **`data/state.json`** — compatibility projection, always available

Do not create a second Agent database, Agent console runtime, MCP sidecar, or fake mirror state.

## Product truth

- The shared information layer, deep dives, article records, WeChat draft mapping, and publish tasks all live in the same state.
- **Recommended path: Agent mode.** External AI should normally use Agent mode because it can make editorial decisions: skip weak topics, write a 5-item short-news digest, write a long article, or build a mixed package.
- **Traditional mode** is the built-in script/rule-driven workflow for users who do not have a model available or only want lightweight automation. It now has two product modes:
  - `manual`: collection, deep dive, digest generation, and upload are all triggered by the user.
  - `automated`: the scheduler runs the pipeline; `delivery_mode` controls how far it goes.
- **Automated delivery modes**:
  - `collect_only`: collect -> cluster -> score; no deep dive, no brief, no upload.
  - `local_digest`: collect -> cluster -> score -> deep dive -> one daily digest; no WeChat upload.
  - `immediate`: collect -> cluster -> score -> deep dive -> one daily digest -> upload -> verify.
  - `scheduled_batch`: collect -> cluster -> score -> deep dive -> one daily digest, then upload and verify only when the schedule is due.
- Traditional daily digest briefs must merge exactly 5 events into one complete short-news digest. They are a fallback/productivity tool, not the preferred writing path when Agent mode is available.
- **Agent mode** is external-AI-driven workflow. You decide what to write and in what form: 5-item short-news digest, long article, mixed package, or skip. You are the editor-in-chief.
- A user-specified output form is a required deliverable, not a hard one-article cap. If the user asks for a short-news digest, deliver one complete 5-item digest first, then still scan for major events that deserve a separate long article in the same run. If a strong long-form candidate exists, create a second article as part of the same task unless the user explicitly says "only one", "只要短讯", or "不要其他文章".
- Local material drafts and platform-ready drafts are different deliverables. A structured digest with `## 1.`, `## 来源链接`, or backend labels like “核心事实 / 这意味着什么 / 还不确定什么” is acceptable for local storage, but it must not be uploaded to WeChat, Douyin, or any external platform. Before platform execution, rewrite it into a polished, conversational article.
- Platform short-news copy must read like one connected 5-item roundup: opening hook, then “首先 / 然后 / 接下来 / 再说 / 最后” style transitions, with each item naturally covering what happened, why it matters, and what remains uncertain. Do not send a mechanical numbered outline.
- When converting a local digest into platform copy, use the reusable polishing prompt in the “Short digest polishing prompt” section below. Do not rely on memory or improvise a new structure each time.
- The two modes share the same data source but produce independent outputs. Traditional digest briefs have `brief_level="rule"`. Agent articles have `brief_level="article"`.
- The frontend overview page is only the traditional manual/automated console. Do not treat it as the Agent work entry.
- Agent mode must strictly follow the project-defined chain:
  `sources/sync -> intel/events -> deep-dive -> brief -> agent/articles -> platform execution`
- For WeChat, treat article save and draft upload as two separate operational steps: save with `publish_to_wechat_draft=false`, record the returned `brief_id`, then upload or retry with `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`.
- WeChat and Douyin are downstream execution targets, not alternate content-ingest paths.
- Do not treat "open a platform editor and fill content" as a valid replacement for writing into the shared `briefs` ledger first.
- WeChat upload must stay on a single browser tab. Always return to the WeChat home dashboard first, then enter `新的创作 -> 文章` on the current tab.
- Do not solve WeChat upload failures by opening extra tabs. Retry by re-walking `home -> article -> editor`, not by reusing a stale editor tab.
- If the user says `开始今日的工作`, treat it as a shortcut for the full Agent daily workflow, not as a request to start the built-in traditional scheduler.
- For the Agent path, you should:
  1. collect and inspect shared intel
  2. decide what is worth writing, and choose the right content form: do not write / 5-item short-news digest / long article / mixed package / multiple separate articles
  3. deep-dive and verify
  4. create one local brief/material record for tracking and source packaging
  5. write the final content yourself
  6. save each final piece into the shared article store
  7. upload each selected piece to the target platform draft box

The shared article container is still the existing `briefs` collection in `state.json`. In Agent usage, the traditional brief record is a local material record, and the final long article is stored as a separate `article` record in that same shared collection.

## Current repository layout

The project structure has been reorganized. When exploring or implementing, use the current modules rather than assuming the older flat layout.

- Backend entry: `backend/app/main.py`
- Backend route layer: `backend/app/routes/`
- Backend feature pages/actions: `backend/app/features/`
- Browser automation: `backend/app/publishers/`
- Shared state logic: `backend/app/store/` and `backend/app/store_mixins/`
- Services/utilities: `backend/app/services/`
- Frontend app: `frontend/src/`
- Frontend development server: Vite on `http://127.0.0.1:4173`

Do not assume legacy paths like a single monolithic `publishers.py` or direct route/store wiring if the repo has already been split into packages.

## Real API surface

Base URL in local development:

- `http://127.0.0.1:8000`

Before calling business APIs, verify the backend is reachable:

- `GET /api/health`

Expected response:

```json
{
  "status": "ok"
}
```

If the backend is not reachable:

- run `start.bat`
- if `start.bat` reports an existing project backend or stale PID/port state, run `stop.bat` first, then retry `start.bat`
- if port `8000` is occupied by a non-project process, free that port before retrying
- if `start.bat` reports `frontend/dist` missing, run `cd frontend && npm run build` first

## Frontend development notes

- Production-style local app is still served by backend on `http://127.0.0.1:8000`
- Frontend dev server is `http://127.0.0.1:4173`
- In development, the Vite server must proxy `/api` and `/assets` to `8000`; if API calls look stale or empty, verify the dev server is using current proxy config
- If checking a frontend-only change, prefer `4173`; if checking backend-served built assets, rebuild frontend and verify through `8000`

## Response envelope rules

Do not guess response shapes. This project does **not** use one universal envelope.

- most list endpoints return `{ "items": [...] }`
- paginated list endpoints return `{ "items": [...], "total": 0, "page": 1, "page_size": 50, "has_more": false }`
- most detail endpoints return `{ "item": {...} }`
- source sync returns a flat object, not `item` or `items`

### List responses

```json
{ "items": [] }
```

### Paginated list responses

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 50,
  "has_more": false
}
```

### Detail responses

```json
{ "item": {} }
```

### Source sync response

```json
{
  "raw_count": 0,
  "normalized_count": 0,
  "event_count": 0,
  "synced_at": "2026-05-04T00:00:00Z",
  "warnings": []
}
```

---

## Complete API reference (mapped to traditional mode tabs)

The table below maps every traditional mode UI tab to its Agent-accessible API endpoints.

### Tab 1: 总览 (Overview)

| UI action | Agent API |
|---|---|
| Read dashboard | `GET /api/admin/dashboard` |
| Read intel summary | `GET /api/admin/intel/summary` |
| Start monitoring | `POST /api/admin/runtime/start` |
| Stop monitoring | `POST /api/admin/runtime/stop` |
| Run maintenance (collect/cluster/alert) | `POST /api/admin/runtime/run-intent` with body `{ "intent": "normal_monitoring" }` |
| Read runtime status | `GET /api/admin/runtime/status` |
| Read runtime plan | `GET /api/admin/runtime/plan` |

### Tab 2: 实时流 (Stream)

| UI action | Agent API |
|---|---|
| Read raw discovery items | `GET /api/admin/intel/stream?page=1&page_size=50` |

### Tab 3: 热点簇 (Events)

| UI action | Agent API |
|---|---|
| Read all events | `GET /api/admin/intel/events?page=1&page_size=50` |
| Read single event detail | `GET /api/admin/intel/events/{event_id}` |
| Add event to watchlist (深挖池) | `POST /api/admin/intel/watchlist/{event_id}` |
| Ignore event | `POST /api/admin/intel/ignore/{event_id}` |

### Tab 4: 预警台 (Alerts)

| UI action | Agent API |
|---|---|
| Read alerts + history | `GET /api/admin/intel/alerts` |

### Tab 5: 来源健康 (Source Health)

| UI action | Agent API |
|---|---|
| Read source health | `GET /api/admin/intel/sources` |
| Read all sources (config) | `GET /api/admin/sources` |
| Sync all sources | `POST /api/admin/sources/sync?triggered_by=agent` |
| Sync single source | `POST /api/admin/sources/{source_key}/sync?triggered_by=agent` |
| Update source config | `PUT /api/admin/sources/{source_key}` |
| Create source | `POST /api/admin/sources` |
| Delete source | `DELETE /api/admin/sources/{source_key}` |

### Tab 6: 深挖池 (Deep Dive Pool)

| UI action | Agent API |
|---|---|
| Read all deep dives | `GET /api/admin/intel/deep-dives` |
| Read single deep dive | `GET /api/admin/intel/deep-dives/{event_id}` |
| Trigger deep dive (new) | `POST /api/admin/intel/events/{event_id}/deep-dive?triggered_by=agent` |
| Force re-dive (re-run) | `POST /api/admin/intel/events/{event_id}/deep-dive?triggered_by=agent` with body `{ "force": true }` |
| Generate rule-based brief (traditional) | `POST /api/admin/intel/events/{event_id}/brief?triggered_by=agent` |

The deep dive response includes an `article_writing_guide` field with detailed formatting, structure, and style instructions for WeChat public account content — you MUST follow this guide when composing the final content.

Key requirements from the guide: Agent decides the content form. A WeChat short-news digest is not a single-event short article; it must be one complete article composed of exactly 5 connected tech-news items. Use an 800-1000 word article for major events, and a mixed package when the day has one major event plus a 5-item digest. For Douyin, the publish flag means “整理今日最值得关注的 5 条科技要闻组成短讯合集”. Use specific numbers over vague adjectives, Markdown format with `#` title, `##` sections, and `>` only for real quotes.

### Short digest polishing prompt

Use this exact prompt whenever a local 5-item digest needs to become WeChat/Douyin-ready platform copy:

```text
你会收到一份“本地短讯素材稿”，里面有 5 条科技新闻、事实、不确定项和来源。请把它改写成适合平台发布的一篇完整短讯合集。

目标风格：
- 像编辑在直接讲给读者听，口语自然，但不要夸张。
- 不要写成长文分析，也不要写成机械列表。
- 一篇文章必须正好包含 5 条信息，不能少于 5 条，也不能把单条新闻写成短讯。

结构要求：
1. 开头用 1 句话说明“今天直接盘 5 条科技小新闻/科技要闻”。
2. 正文用“首先 / 然后 / 接下来 / 再说 / 最后”自然串联 5 条。
3. 每条用 2-4 句说清：发生了什么、为什么值得看、还不确定什么。
4. 结尾用 1 段收束 5 条新闻共同指向的趋势。

禁止事项：
- 不要保留 `## 1.`、`## 来源链接`、裸 URL、素材包字段名。
- 不要出现“核心事实”“这意味着什么”“还不确定什么”这种后台栏目名。
- 不要新增素材里没有的数字、日期、价格、人名、产品能力。
- 不要把“可能”“预计”“测试中”写成已经确定发生。

输入：
{本地短讯素材稿}

输出：
只输出平台发布稿 Markdown。标题用 `#`，正文只保留自然段，不要附来源链接列表。
```

### Tab 7: 简报/文章 (Briefs)

| UI action | Agent API |
|---|---|
| Read all articles/briefs | `GET /api/admin/briefs?page=1&page_size=20&stage=all&q=` |
| Read single article/brief | `GET /api/admin/briefs/{brief_id}` |
| Read Agent sessions | `GET /api/admin/agent/workflows` |
| Abandon unfinished Agent session | `POST /api/admin/agent/workflows/{workflow_session_id}/abandon?triggered_by=agent` |
| **Save AI-authored article** | `POST /api/admin/agent/articles` (see detail below) |
| Upload Agent article to WeChat draft | `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent` after the article was created by `POST /api/admin/agent/articles`. Do not use this on traditional `brief_level=rule` briefs. |
| Get copy package (for clipboard) | `POST /api/admin/briefs/{brief_id}/copy-package` |
| **Delete article/brief** | `DELETE /api/admin/briefs/{brief_id}?triggered_by=agent` |
| Regenerate rule-based brief | `POST /api/admin/intel/events/{event_id}/brief?triggered_by=agent` |

### Tab 8: 发表记录 (Publish History)

| UI action | Agent API |
|---|---|
| Read publish tasks | `GET /api/admin/publish-tasks?page=1&page_size=20` |
| Check real WeChat publish history | `POST /api/admin/browser/wechat/check-publish-history?triggered_by=agent` |

Notes:

- The publish history check now fetches article engagement metrics (reads, likes, shares, comments, etc.) from WeChat and writes them back to the corresponding brief records. After calling this endpoint, the brief items will have `read_count`, `like_count`, `share_count`, etc. populated.
- The current product intent is: one manual refresh should gather both publish-history article metrics and the related WeChat analytics overview when available.
- Article-level data must come from `内容管理 -> 发表记录`.
- Do not treat the top-level `数据分析` menu click as the final target page. Analytics scraping must go into a real subpage such as `内容分析` when that workflow is being implemented or debugged.

### Tab 9: 微信草稿箱 (Draft Box)

| UI action | Agent API |
|---|---|
| Read WeChat-local mapping | `GET /api/admin/wechat/mapping` |
| Refresh mapping from remote | `POST /api/admin/wechat/mapping/refresh?triggered_by=agent` |
| Check remote draft box | `POST /api/admin/browser/wechat/check-drafts?triggered_by=agent` |
| **Delete remote WeChat draft** | `DELETE /api/admin/wechat/remote-drafts/{remote_id}` |
| Re-sync Agent article to draft | `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`; reserved for the dedicated article record created by `POST /api/admin/agent/articles`. Do **not** use it on traditional brief records. |

### WeChat browser path rules

For existing-draft publish precheck, read `docs/WECHAT_AGENT_PUBLISH_RUNBOOK.md` before touching the browser. It records the verified draft-card edit button path, publish settings, second-confirm publish button, QR-code stop condition, and failure evidence checklist.

- For article upload:
  `公众号首页 -> 新的创作 -> 文章 -> 编辑页 -> 保存草稿`
- For publish-history metrics:
  `内容管理 -> 发表记录`
- For analytics debugging:
  `数据分析 -> 内容分析` (or other explicit subpages), not just the top-level menu shell

If the user provides concrete menu HTML, prefer that concrete path over old assumptions.

### Tab 10: 设置 (Settings)

| UI action | Agent API |
|---|---|
| Read settings | `GET /api/admin/settings` |
| Read LLM config | `GET /api/admin/llm/config` |
| Read LLM usage stats | `GET /api/admin/llm/usage` |
| Update settings | `PUT /api/admin/settings` |
| Update LLM config | `PUT /api/admin/llm/config` |
| Test LLM provider | `POST /api/admin/llm/test/{provider_key}` |
| Read WeChat channel config | `GET /api/admin/channels/wechat` |
| Update WeChat channel config | `PUT /api/admin/channels/wechat` |
| Read browser session | `GET /api/admin/browser/wechat/session` |
| Open WeChat dashboard in browser | `POST /api/admin/browser/wechat/open-dashboard` |
| Check browser session | `POST /api/admin/browser/wechat/check` |
| System health check | `GET /api/admin/system/doctor` |
| Read logs | `GET /api/admin/logs?page=1&page_size=50&level=all&q=` |

### Standalone APIs (no direct tab)

| Purpose | Agent API |
|---|---|
| Entity watchlist | `GET /api/admin/entities/watchlist` / `PUT /api/admin/entities/watchlist` |
| Read reference projects | `GET /api/admin/reference-projects` |
| Check app updates | `GET /api/admin/system/update?force=false` |
| Export system config | `POST /api/admin/system/export-config` |
| Export backup | `POST /api/admin/system/export-backup` |
| Import backup | `POST /api/admin/system/import-backup` (multipart file) |
| Upload image | `POST /api/admin/images/upload` (multipart, max 5MB) |
| Serve image | `GET /api/admin/images/{filename}` |
| Read publish backends status | `GET /api/admin/publish/backends` |

---

## Key API details

### Save AI-authored content directly

- `POST /api/admin/agent/articles`

Recommended Agent behavior:

- Save first with `"publish_to_wechat_draft": false`.
- Record the returned article id as `brief_id`.
- Upload or retry WeChat draft separately with `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`.
- Do not delete a saved article just because WeChat upload failed.

JSON body:

```json
{
  "event_id": "evt-xxxx",
  "title": "文章标题",
  "article_markdown": "# 标题\n\n正文内容",
  "one_line": "一句话结论",
  "why_it_matters": "为什么值得关注",
  "facts": ["事实1", "事实2"],
  "quotes": ["引文1"],
  "timeline": ["时间点1"],
  "entity_names": ["OpenAI", "ChatGPT"],
  "source_links": ["https://example.com/a"],
  "risk_notes": ["仍需注意的不确定性"],
  "publish_to_wechat_draft": false,
  "publish_to_douyin_article": false,
  "triggered_by": "agent",
  "driver_label": "codex"
}
```

Behavior:

- saves the Agent-authored content into the shared `briefs` store
- reuses the existing event linkage and deep-dive linkage
- if `publish_to_wechat_draft=true`, the backend still attempts WeChat draft upload in the same request, but external AI should avoid that for daily work because it makes failure recovery ambiguous
- if `publish_to_douyin_article=true`, the backend first builds/reuses a daily tech-news digest from up to 5 verified events, then opens the Douyin article page and fills that short-news roundup instead of the single Agent article

For a 5-item digest, `event_id` is the primary/lead event only. Put the other four events into the article content and metadata (`facts`, `entity_names`, `source_links`, `risk_notes`). Do not create or delete extra briefs just to satisfy `event_id`.

### Upload or retry WeChat draft

- `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`

Use this only after `POST /api/admin/agent/articles` returned a dedicated Agent article record (`brief_level=article`). Do not call it on traditional material briefs (`brief_level=rule`).

If upload fails after the article was saved, keep the saved `brief_id`, recover the browser session if needed, and call this endpoint again. The detailed ordered recovery flow is in `docs/AGENT_DAILY_WORKFLOW_RUNBOOK.md`.

### Collect shared intel

- `POST /api/admin/sources/sync?triggered_by=agent` — sync all sources
- `POST /api/admin/sources/{source_key}/sync?triggered_by=agent` — sync single source

These refresh the shared information layer and write results into the same `state.json` used by the normal product.

### Check text quality (for Critique step)

- `POST /api/admin/agent/text-quality`

JSON body:

```json
{
  "text": "文章正文",
  "max_banned": 3,
  "min_burstiness": 0.4
}
```

Returns a quality report with:
- `burstiness_score` — sentence length variance / mean (higher = more varied rhythm)
- `avg_sentence_length` — average characters per sentence
- `banned_phrase_hits` — list of AI-style phrases detected
- `banned_phrase_count` — number of banned phrases found
- `passed` — `true` if burstiness >= min_burstiness AND banned count <= max_banned

Use this during Critique to detect AI-sounding writing patterns.

### Title optimization feedback loop

- `POST /api/admin/agent/analytics/title-optimization`

Generates a Markdown report analyzing high-performing articles from publish history. Use before writing to learn from past success.

Response includes:
- `report` — Markdown analysis with top 10 performers, title patterns, and AI writing suggestions
- `high_performers` — List of best articles with metrics (read, like, share, recommend, comment)
- `stats` — Summary statistics

Workflow:
1. Call `POST /api/admin/browser/wechat/check-publish-history?triggered_by=agent` to fetch latest metrics
2. Call `POST /api/admin/agent/analytics/title-optimization` to get the report
3. Read `report` field for title patterns and writing suggestions
4. Apply patterns when generating new article titles

How to judge whether collection really succeeded:

1. the sync endpoint returns HTTP `200`
2. `synced_at` is fresh
3. a follow-up `GET /api/admin/intel/events` returns an `items` array you can actually parse
4. if `warnings` is non-empty, treat the run as partial success and read the warning text before claiming the pipeline is healthy

Do **not** assume a fixed event count threshold. Event volume depends on source configuration, time window, and whether this is a first run or a repeated run.

### Runtime maintenance intents

`POST /api/admin/runtime/run-intent` accepts `{ "intent": "..." }` with these values:

- `normal_monitoring` — one scheduler cycle. In `manual`, delivery is skipped; in `automated`, `delivery_mode` decides whether it stops at collect/score, local digest, immediate upload, or scheduled upload.
- `collect_only` — source sync only
- `rebuild_events` — re-cluster without re-collecting
- `rebuild_alerts` — re-score and re-alert without re-collecting

### Delete operations

All delete endpoints require confirmation context. Use `triggered_by=agent` query param when available:

- Delete article/brief (local only): `DELETE /api/admin/briefs/{brief_id}?remote=false&triggered_by=agent`
- Delete article/brief (local + remote): `DELETE /api/admin/briefs/{brief_id}?remote=true&triggered_by=agent`
- Delete article/brief (auto-detect): `DELETE /api/admin/briefs/{brief_id}?remote=auto&triggered_by=agent` — if `stage=synced`, deletes remote draft first, then local record; if `stage=prepared`, only deletes local record
- Delete remote WeChat draft (by mapping key): `DELETE /api/admin/wechat/remote-drafts/{remote_id}` — `remote_id` is the `remote_key` from the mapping, e.g. `card:some-title|updated:12:30|0` (URL-encode the `|` and Chinese characters)
- Delete source: `DELETE /api/admin/sources/{source_key}`

### Browser operation constraints

WeChat browser operations (check-drafts, check-publish-history, delete remote draft, sync to draft) share a **single mutual-exclusion lock**. Only one browser action can run at a time. If you call two browser endpoints concurrently, the second one returns `"浏览器忙"`.

- Do **not** call `check-drafts` and `check-publish-history` in parallel — call them sequentially.
- Each browser operation follows a full cycle: go home → navigate → action → return home. The next operation starts from home.

---

## Working rules for external AI

1. Read current state first.
2. Prefer shared event data from `/api/admin/intel/events` as the topic pool.
3. Before writing, run deep-dive for the chosen event if it has no usable deep-dive result yet.
4. Use your own web research ability for extra verification and enrichment.
5. Save the final article through `/api/admin/agent/articles`.
6. Do not create a second storage layer.
7. Do not invent APIs that do not exist in this file.
8. Do not claim success unless the real API returned success.
9. If checking WeChat state fails, report the failure instead of fabricating remote truth.
10. Respect the current duplicate-upload guard. If the same revision is already synced, do not try to bypass it.
11. **Do not directly edit `data/state.json`.** All state mutations must go through the API endpoints listed above. The backend handles thread safety (RLock) and atomic writes — direct file edits bypass these guarantees and corrupt data. Read `state.json` for investigation only.
12. **Before deleting a remote draft**, always call `GET /api/admin/wechat/mapping` first to get the correct `remote_key` for the target brief. The `remote_id` in `DELETE /api/admin/wechat/remote-drafts/{remote_id}` must exactly match the `remote_key` from the mapping (URL-encode `|`, Chinese characters, etc.).
13. **Do NOT start the traditional runtime.** `POST /api/admin/runtime/start` launches a 60-second scheduler that autonomously generates briefs and uploads them to WeChat draft — this conflicts with Agent-authored articles. Use `POST /api/admin/sources/sync` for manual one-shot collection instead. If the runtime is already running, stop it with `POST /api/admin/runtime/stop` before writing articles.
14. **Do NOT use `POST /api/admin/briefs/{id}/wechat-draft` to upload a traditional brief.** For Agent-authored articles, first create the dedicated article record with `POST /api/admin/agent/articles` and `publish_to_wechat_draft=false`, then upload that returned `brief_id` through `POST /api/admin/briefs/{id}/wechat-draft?triggered_by=agent`. The backend will reject `triggered_by=agent` if the target record is still a traditional brief.
15. **Do NOT invent side paths for Douyin or WeChat.** Platform actions are allowed only after the article already exists in the shared `briefs` ledger through the standard project flow.
16. **Do NOT skip the brief/article linkage.** Even when the final destination is Douyin, the content must still come from the shared event -> deep-dive -> brief -> article chain defined by this project.
17. **写完文章后必须经过 Critique 审稿才能保存。** Critique 是独立于写作的检查步骤，不是可选优化。未通过 Critique 的文章不得调用 `POST /api/admin/agent/articles`。

## Basic error-handling rules

1. If an endpoint returns `4xx` or `5xx`, report the response body instead of guessing intent.
2. If collection succeeds but parsing returns zero results, first verify whether you forgot the `items` envelope.
3. If backend startup fails because of project PID or stale listener state, try `stop.bat` and then `start.bat` once before escalating.
4. If backend startup fails because `frontend/dist` is missing, build the frontend before retrying.
5. If WeChat inspection fails, report it as remote-state unavailable, not as empty remote data.
6. If a browser endpoint returns `"浏览器忙"`, wait a few seconds and retry — another operation is holding the lock.
7. If a WeChat browser endpoint returns old cached check data, do not claim fresh remote verification until a new timestamp or the new target title is visible in the returned items.

## Suggested Agent workflow

**Do NOT start the traditional runtime (`POST /api/admin/runtime/start`).** The traditional scheduler runs every 60 seconds and will autonomously generate briefs and upload them to WeChat draft, overwriting or conflicting with your Agent-authored articles. If the runtime is already running, stop it first with `POST /api/admin/runtime/stop`.

### Shortcut phrase

If the user says `开始今日的工作`, interpret it as a request to run the end-to-end Agent workflow for the current day unless the user narrows the scope.

This shortcut means:

1. stop the traditional scheduler if it is running
2. sync fresh shared intel
3. inspect today's event pool
4. choose worthwhile topics
5. deep-dive, create local brief/material records, and write the full article
6. save the article through `POST /api/admin/agent/articles` with `publish_to_wechat_draft=false`
7. record the returned `brief_id`
8. only after that, execute the target platform step, such as `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`

If the user does not specify a target platform, default to the existing WeChat draft delivery path.

1. `POST /api/admin/runtime/stop` — stop the traditional scheduler if it is running (avoid conflicts)
2. `POST /api/admin/sources/sync?triggered_by=agent` — collect fresh intel (manual one-shot, not scheduler-driven)
3. `GET /api/admin/intel/events` — read hot events
4. decide the output mix for the day:
   - no write: weak, stale, duplicated, or evidence-poor events
   - short-news digest: exactly 5 clear news points connected into one complete daily roundup
   - single-event flash: one clear news point that may be kept as material or upgraded to a long article, but must not be uploaded as "短讯"
   - long article: one major event with multiple sources, enough facts, clear reader value, and room for analysis
   - mixed package: one long article plus one 5-item short-news digest when the day has one dominant story and multiple smaller updates
   - multiple separate articles: when the user requested one form, but another high-value event clearly deserves a different form in the same run
   - user constraints are minimum/target deliverables, not a maximum, unless the user explicitly limits output count or says not to create additional articles
5. for each chosen event:
   - `POST /api/admin/intel/events/{event_id}/deep-dive?triggered_by=agent` — deep-dive to get verified material
   - read the response, follow `article_writing_guide` for writing style
   - `POST /api/admin/intel/events/{event_id}/brief?triggered_by=agent` — generate a local brief record for material tracking only
   - do extra online verification yourself
   - write the chosen content form following the `article_writing_guide`
     - short-news digest for local review: exactly 5 numbered items in one article; each item uses 2-3 sentences to answer “what happened / why it matters / what is still uncertain”
     - short-news digest for WeChat/Douyin upload: rewrite the local review draft into one polished conversational article, not a visible numbered outline; use natural transitions and remove source-link sections from the body
     - long article: 800-1000 words, use the full article structure from the guide
     - Douyin article: fixed 5-item short-news digest, follow the Douyin writing guide in the deep-dive response
   - before saving, you MUST run a separate Critique pass against the draft
   - Critique must independently check:
     - facts, numbers, dates, names, and quotations are traceable to source material or clearly marked as uncertain
     - title, summary, lead, section headings, and ending follow the writing guide
     - platform short-news copy is polished for readers and does not still look like a local material note or prompt package
     - the draft does not rely on AI-sounding filler such as road-sign transitions, empty praise, or repetitive paragraph templates
     - paragraph rhythm is varied and the article structure is not loose or repetitive
   - if Critique fails, revise the article and critique again
   - repeat the write -> critique -> revise loop up to 2 times maximum
   - only when Critique passes may you call `POST /api/admin/agent/articles` with `publish_to_wechat_draft=false` to save into the shared ledger
   - if the draft still fails after 2 critique rounds, do not save it; report the problems first
   - record the returned `brief_id`
   - only after that, execute the target platform step such as WeChat draft upload or Douyin page fill
6. for WeChat draft upload:
   - `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`
   - if upload fails after save, keep the saved article and retry the same `brief_id` after browser recovery
   - do not delete and recreate the article only because the browser upload timed out
7. after upload, optionally verify:
   - `POST /api/admin/browser/wechat/check-drafts?triggered_by=agent`
   - `POST /api/admin/browser/wechat/check-publish-history?triggered_by=agent`
8. for Douyin articles, after saving via `POST /api/admin/agent/articles` with `publish_to_douyin_article: true`:
   - the backend automatically builds/reuses “今日5条科技要闻” from verified events, then opens the Douyin creator center and fills that roundup
   - target form: exactly 5 short news items, each covering what happened, why it matters, and what remains uncertain
   - style: direct, conversational, mobile-first
   - do NOT include source links, "参考资料", or WeChat-style formatting
9. if an article needs correction:
   - `DELETE /api/admin/wechat/remote-drafts/{remote_id}` — delete remote draft first (get `remote_id` from `GET /api/admin/wechat/mapping`)
   - `DELETE /api/admin/briefs/{brief_id}?remote=false&triggered_by=agent` — then delete local record (use `remote=false` since remote is already gone)
   - re-write and re-submit via `POST /api/admin/agent/articles`
   - `POST /api/admin/wechat/mapping/refresh?triggered_by=agent` — refresh mapping to verify consistency

**Key distinction:** The brief record from step 5 is a local material record. The content from `POST /api/admin/agent/articles` is your own final Agent-authored piece, whether it is a 5-item short-news digest or long article, and is stored as a separate article record in the shared `briefs` collection. Never use `POST /api/admin/briefs/{id}/wechat-draft` on a traditional brief record — that is not the final Agent article. For WeChat, save the final Agent article first with `publish_to_wechat_draft=false`, then upload or retry the returned `brief_id` with `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`.

### Date discipline for daily work

- When running a “today” workflow, validate that the chosen event is actually from the current date in local timezone.
- Prefer checking `published_at`, `first_seen_at`, and `last_seen_at` together.
- Do not reuse yesterday’s topic just because it still has a high score.
- In status updates and final reporting, include the actual date when clarifying “today”, “yesterday”, or “this round”.

## Logging expectation

The project already has a shared log system.

When driving the project as an external AI:

- use `triggered_by=agent` on supported endpoints
- use `"triggered_by": "agent"` inside the article payload

That keeps Agent activity visible in the normal logs without building a second logging product.
