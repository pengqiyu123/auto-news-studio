# AGENT.md

This file is for external AI coding tools that can read the repository and drive the project directly.

The project has one business database only:

- `data/state.json`

Do not create a second Agent database, Agent console runtime, MCP sidecar, or fake mirror state.

## Product truth

- The shared information layer, deep dives, article records, WeChat draft mapping, and publish tasks all live in the same state.
- Traditional mode is the built-in script/rule-driven workflow.
- Agent mode is external-AI-driven workflow.
- The frontend overview page is only the traditional automation console. Do not treat it as the Agent work entry.
- Agent mode must strictly follow the project-defined chain:
  `sources/sync -> intel/events -> deep-dive -> brief -> agent/articles -> platform execution`
- WeChat and Douyin are downstream execution targets, not alternate content-ingest paths.
- Do not treat "open a platform editor and fill content" as a valid replacement for writing into the shared `briefs` ledger first.
- WeChat upload must stay on a single browser tab. Always return to the WeChat home dashboard first, then enter `新的创作 -> 文章` on the current tab.
- Do not solve WeChat upload failures by opening extra tabs. Retry by re-walking `home -> article -> editor`, not by reusing a stale editor tab.
- If the user says `开始今日的工作`, treat it as a shortcut for the full Agent daily workflow, not as a request to start the built-in traditional scheduler.
- For the Agent path, you should:
  1. collect and inspect shared intel
  2. decide what is worth writing
  3. deep-dive and verify
  4. create one local brief/material record for tracking and source packaging
  5. write the full article yourself
  6. save the full article into the shared article store
  7. upload to WeChat draft box

The shared article container is still the existing `briefs` collection in `state.json`. In Agent usage, the traditional brief record is a local material record, and the final long article is stored as a separate `article` record in that same shared collection.

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

The deep dive response includes an `article_writing_guide` field with detailed formatting, structure, and style instructions for WeChat public account articles — you MUST follow this guide when composing the article.

Key requirements from the guide: 1500-3000 word full article (not a bullet-point brief), 36氪/极客公园 style, specific numbers over vague adjectives, Markdown format with `#` title, `##` sections, `>` for quotes.

### Tab 7: 简报/文章 (Briefs)

| UI action | Agent API |
|---|---|
| Read all articles/briefs | `GET /api/admin/briefs?page=1&page_size=20&stage=all&q=` |
| Read single article/brief | `GET /api/admin/briefs/{brief_id}` |
| **Save AI-authored article** | `POST /api/admin/agent/articles` (see detail below) |
| Upload article to WeChat draft | Do **not** use this row for Agent longform uploads. Use `POST /api/admin/agent/articles` with `publish_to_wechat_draft: true`. |
| Get copy package (for clipboard) | `POST /api/admin/briefs/{brief_id}/copy-package` |
| **Delete article/brief** | `DELETE /api/admin/briefs/{brief_id}?triggered_by=agent` |
| Regenerate rule-based brief | `POST /api/admin/intel/events/{event_id}/brief?triggered_by=agent` |

### Tab 8: 发表记录 (Publish History)

| UI action | Agent API |
|---|---|
| Read publish tasks | `GET /api/admin/publish-tasks?page=1&page_size=20` |
| Check real WeChat publish history | `POST /api/admin/browser/wechat/check-publish-history?triggered_by=agent` |

### Tab 9: 微信草稿箱 (Draft Box)

| UI action | Agent API |
|---|---|
| Read WeChat-local mapping | `GET /api/admin/wechat/mapping` |
| Refresh mapping from remote | `POST /api/admin/wechat/mapping/refresh?triggered_by=agent` |
| Check remote draft box | `POST /api/admin/browser/wechat/check-drafts?triggered_by=agent` |
| **Delete remote WeChat draft** | `DELETE /api/admin/wechat/remote-drafts/{remote_id}` |
| Re-sync brief to draft | Reserved for the dedicated article record created by `POST /api/admin/agent/articles`. Do **not** use it on traditional brief records. |

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

### Save an AI-authored full article directly

- `POST /api/admin/agent/articles`

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
  "publish_to_wechat_draft": true,
  "publish_to_douyin_article": false,
  "triggered_by": "agent",
  "driver_label": "codex"
}
```

Behavior:

- saves the article into the shared `briefs` store
- reuses the existing event linkage and deep-dive linkage
- if `publish_to_wechat_draft=true`, automatically reuses the existing WeChat draft upload chain
- if `publish_to_douyin_article=true`, automatically opens the Douyin article page and fills title, summary, body, and AI illustration

### Collect shared intel

- `POST /api/admin/sources/sync?triggered_by=agent` — sync all sources
- `POST /api/admin/sources/{source_key}/sync?triggered_by=agent` — sync single source

These refresh the shared information layer and write results into the same `state.json` used by the normal product.

How to judge whether collection really succeeded:

1. the sync endpoint returns HTTP `200`
2. `synced_at` is fresh
3. a follow-up `GET /api/admin/intel/events` returns an `items` array you can actually parse
4. if `warnings` is non-empty, treat the run as partial success and read the warning text before claiming the pipeline is healthy

Do **not** assume a fixed event count threshold. Event volume depends on source configuration, time window, and whether this is a first run or a repeated run.

### Runtime maintenance intents

`POST /api/admin/runtime/run-intent` accepts `{ "intent": "..." }` with these values:

- `normal_monitoring` — full cycle: collect, normalize, cluster, score, alert
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
14. **Do NOT use `POST /api/admin/briefs/{id}/wechat-draft` to upload a traditional brief.** Agent-authored articles must go through `POST /api/admin/agent/articles` with `publish_to_wechat_draft: true`. The backend will reject `triggered_by=agent` if the target record is still a traditional brief.
15. **Do NOT invent side paths for Douyin or WeChat.** Platform actions are allowed only after the article already exists in the shared `briefs` ledger through the standard project flow.
16. **Do NOT skip the brief/article linkage.** Even when the final destination is Douyin, the content must still come from the shared event -> deep-dive -> brief -> article chain defined by this project.

## Basic error-handling rules

1. If an endpoint returns `4xx` or `5xx`, report the response body instead of guessing intent.
2. If collection succeeds but parsing returns zero results, first verify whether you forgot the `items` envelope.
3. If backend startup fails because of project PID or stale listener state, try `stop.bat` and then `start.bat` once before escalating.
4. If backend startup fails because `frontend/dist` is missing, build the frontend before retrying.
5. If WeChat inspection fails, report it as remote-state unavailable, not as empty remote data.
6. If a browser endpoint returns `"浏览器忙"`, wait a few seconds and retry — another operation is holding the lock.

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
6. save the article through `POST /api/admin/agent/articles`
7. only after that, execute the target platform step

If the user does not specify a target platform, default to the existing WeChat draft delivery path.

1. `POST /api/admin/runtime/stop` — stop the traditional scheduler if it is running (avoid conflicts)
2. `POST /api/admin/sources/sync?triggered_by=agent` — collect fresh intel (manual one-shot, not scheduler-driven)
3. `GET /api/admin/intel/events` — read hot events
4. choose up to 5 high-value events
5. for each chosen event:
   - `POST /api/admin/intel/events/{event_id}/deep-dive?triggered_by=agent` — deep-dive to get verified material
   - read the response, follow `article_writing_guide` for writing style
   - `POST /api/admin/intel/events/{event_id}/brief?triggered_by=agent` — generate a local brief record for material tracking only
   - do extra online verification yourself
   - write a 1500-3000 word full article following the `article_writing_guide`
   - before saving, you MUST run a separate Critique pass against the draft
   - Critique must independently check:
     - facts, numbers, dates, names, and quotations are traceable to source material or clearly marked as uncertain
     - title, summary, lead, section headings, and ending follow the writing guide
     - the draft does not rely on AI-sounding filler such as road-sign transitions, empty praise, or repetitive paragraph templates
     - paragraph rhythm is varied and the article structure is not loose or repetitive
   - if Critique fails, revise the article and critique again
   - repeat the write -> critique -> revise loop up to 2 times maximum
   - only when Critique passes may you call `POST /api/admin/agent/articles` to save into the shared ledger
   - if the draft still fails after 2 critique rounds, do not save it; report the problems first
   - only after that, execute the target platform step such as WeChat draft upload or Douyin page fill
6. after upload, optionally verify:
   - `POST /api/admin/browser/wechat/check-drafts?triggered_by=agent`
   - `POST /api/admin/browser/wechat/check-publish-history?triggered_by=agent`
7. if an article needs correction:
   - `DELETE /api/admin/wechat/remote-drafts/{remote_id}` — delete remote draft first (get `remote_id` from `GET /api/admin/wechat/mapping`)
   - `DELETE /api/admin/briefs/{brief_id}?remote=false&triggered_by=agent` — then delete local record (use `remote=false` since remote is already gone)
   - re-write and re-submit via `POST /api/admin/agent/articles`
   - `POST /api/admin/wechat/mapping/refresh?triggered_by=agent` — refresh mapping to verify consistency

**Key distinction:** The brief record from step 5 is a local material record. The article from `POST /api/admin/agent/articles` is your own full-length piece and is stored as a separate article record in the shared `briefs` collection. Never use `POST /api/admin/briefs/{id}/wechat-draft` on a traditional brief record — that is not the final Agent article. Always use `POST /api/admin/agent/articles` with `publish_to_wechat_draft: true` for the final upload, and only after Critique has approved the draft.

## Logging expectation

The project already has a shared log system.

When driving the project as an external AI:

- use `triggered_by=agent` on supported endpoints
- use `"triggered_by": "agent"` inside the article payload

That keeps Agent activity visible in the normal logs without building a second logging product.
