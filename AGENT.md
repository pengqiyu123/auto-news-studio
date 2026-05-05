# AGENT.md

This file is for external AI coding tools that can read the repository and drive the project directly.

The project has one business database only:

- `data/state.json`

Do not create a second Agent database, Agent console runtime, MCP sidecar, or fake mirror state.

## Product truth

- The shared information layer, deep dives, article records, WeChat draft mapping, and publish tasks all live in the same state.
- Traditional mode is the built-in script/rule-driven workflow.
- Agent mode is external-AI-driven workflow.
- Agent mode does **not** need an extra “brief first, article second” step.
- For the Agent path, you should:
  1. collect and inspect shared intel
  2. decide what is worth writing
  3. deep-dive and verify
  4. write the full article directly
  5. save the full article into the shared article store
  6. upload to WeChat draft box

The shared article container is still the existing `briefs` collection in `state.json`, but in Agent usage it should be treated as the shared article record, not as a mandatory intermediate summary workflow.

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
- most detail endpoints return `{ "item": {...} }`
- source sync returns a flat object, not `item` or `items`

Examples:

### List responses

`GET /api/admin/intel/events`

```json
{
  "items": [],
  "history_items": []
}
```

`GET /api/admin/briefs`

```json
{
  "items": []
}
```

`GET /api/admin/logs`

```json
{
  "items": []
}
```

### Detail responses

`GET /api/admin/intel/summary`

```json
{
  "item": {}
}
```

`POST /api/admin/intel/events/{event_id}/deep-dive`

```json
{
  "item": {}
}
```

`POST /api/admin/agent/articles`

```json
{
  "item": {}
}
```

### Source sync response

`POST /api/admin/sources/sync?triggered_by=agent`

```json
{
  "raw_count": 0,
  "normalized_count": 0,
  "event_count": 0,
  "synced_at": "2026-05-04T00:00:00Z",
  "warnings": []
}
```

### Read current state

- `GET /api/admin/dashboard`
- `GET /api/admin/intel/summary`
- `GET /api/admin/intel/stream`
- `GET /api/admin/intel/events`
- `GET /api/admin/intel/alerts`
- `GET /api/admin/intel/deep-dives`
- `GET /api/admin/briefs`
- `GET /api/admin/wechat/mapping`
- `GET /api/admin/logs`

### Collect shared intel

- `POST /api/admin/sources/sync?triggered_by=agent`
- `POST /api/admin/sources/{source_key}/sync?triggered_by=agent`

These refresh the shared information layer and write results into the same `state.json` used by the normal product.

How to judge whether collection really succeeded:

1. the sync endpoint returns HTTP `200`
2. `synced_at` is fresh
3. a follow-up `GET /api/admin/intel/events` returns an `items` array you can actually parse
4. if `warnings` is non-empty, treat the run as partial success and read the warning text before claiming the pipeline is healthy

Do **not** assume a fixed event count threshold. Event volume depends on source configuration, time window, and whether this is a first run or a repeated run.

### Deep-dive a selected event

- `POST /api/admin/intel/events/{event_id}/deep-dive?triggered_by=agent`

Optional JSON body:

```json
{
  "force": false
}
```

This reuses the existing full-text extraction and evidence pipeline.

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
  "triggered_by": "agent",
  "driver_label": "codex"
}
```

Behavior:

- saves the article into the shared `briefs` store
- reuses the existing event linkage and deep-dive linkage
- if `publish_to_wechat_draft=true`, automatically reuses the existing WeChat draft upload chain

### Upload an existing shared article to WeChat draft box

- `POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`

This reuses the existing idempotent sync logic. The same revision should not be uploaded twice.

### Check real WeChat browser state

- `POST /api/admin/browser/wechat/check`
- `POST /api/admin/browser/wechat/check-drafts?triggered_by=agent`
- `POST /api/admin/browser/wechat/check-publish-history?triggered_by=agent`
- `POST /api/admin/wechat/mapping/refresh?triggered_by=agent`

Use these to inspect the real remote draft box and the real publish history.

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

## Basic error-handling rules

1. If an endpoint returns `4xx` or `5xx`, report the response body instead of guessing intent.
2. If collection succeeds but parsing returns zero results, first verify whether you forgot the `items` envelope.
3. If backend startup fails because of project PID or stale listener state, try `stop.bat` and then `start.bat` once before escalating.
4. If backend startup fails because `frontend/dist` is missing, build the frontend before retrying.
5. If WeChat inspection fails, report it as remote-state unavailable, not as empty remote data.

## Suggested Agent workflow

1. `POST /api/admin/sources/sync?triggered_by=agent`
2. `GET /api/admin/intel/events`
3. choose up to 5 high-value events
4. for each chosen event:
   - `POST /api/admin/intel/events/{event_id}/deep-dive?triggered_by=agent`
   - do extra online verification yourself
   - `POST /api/admin/agent/articles`
5. after upload, optionally:
   - `POST /api/admin/browser/wechat/check-drafts?triggered_by=agent`
   - `POST /api/admin/browser/wechat/check-publish-history?triggered_by=agent`

## Logging expectation

The project already has a shared log system.

When driving the project as an external AI:

- use `triggered_by=agent` on supported endpoints
- use `"triggered_by": "agent"` inside the article payload

That keeps Agent activity visible in the normal logs without building a second logging product.
