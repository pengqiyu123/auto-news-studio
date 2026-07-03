# AGENTS.md - Auto News Studio

This file is the project-level entry point for AI agents that support `AGENTS.md`.

For the complete API map and workflow details, read `AGENT.md` next. This file is deliberately shorter: it captures the rules that must be correct before any agent starts operating the product.

## File Roles

`AGENTS.md` and `AGENT.md` are intentionally separate:

- `AGENTS.md` is the short, automatically discovered entry point for AI tools. Keep only high-priority guardrails and handoff instructions here.
- `AGENT.md` is the long operating manual: API map, workflow details, writing rules, and implementation notes.

Do not duplicate the full API reference here. If a detail is procedural or endpoint-specific, put it in `AGENT.md` or a focused doc under `docs/`.

## Required Reading Order

Before running or changing the project, read the relevant files in this order:

1. `AGENTS.md` - this project-level entry and guardrails
2. `AGENT.md` - full Agent workflow, API surface, and writing rules
3. `README.md` - product overview and user-facing behavior
4. `docs/快速上手指南.md` - operator workflow
5. `docs/常见问题.md` - known failure modes and fixes
6. `docs/AGENT_DAILY_WORKFLOW_RUNBOOK.md` - ordered Agent daily workflow and save/upload retry rules
7. `docs/WECHAT_AGENT_PUBLISH_RUNBOOK.md` - verified WeChat draft-to-QR path
8. `.trae/rules/project-agent-workflow.md`, if present - Trae-specific always-on rules

If any of these files disagree, prefer the most recently verified real workflow and update the stale document before relying on it.

## Product Truth

Auto News Studio is a real local product connected to real external publishing surfaces. Do not use demo data, guessed browser state, cached state, or synthetic results as proof of success.

Always distinguish these states precisely:

- generated
- saved locally
- synced to WeChat draft
- opened in WeChat editor
- reached WeChat verification QR code
- published

Reaching the WeChat verification QR code is not a successful publish. A human scan or a confirmed platform state is still required.

## Agent Operating Rules

- Use the project APIs and shared state. Do not create side databases, mirror state, or one-off scripts to bypass the product.
- Do not start the traditional runtime for Agent work. Stop it if needed, then use one-shot project APIs.
- Mark supported operations with `triggered_by=agent`.
- Verify one step before starting the next. Do not batch-click through fragile browser workflows.
- Report failures with the current URL, phase, key logs, and failed selector/action.
- Never expose tokens, QR links, account-sensitive URLs, credentials, or private browser state.
- Do not claim an external result succeeded unless the real API or external platform state confirms it.

## Compact Handoff Prompt

Use this prompt when another AI needs to take over Auto News Studio Agent work:

```text
You are operating Auto News Studio as an Agent. Work in:
D:\python\Auto-news2\auto-news-studio

Read the project guidance first: AGENTS.md, AGENT.md, README.md, docs/快速上手指南.md, docs/常见问题.md, docs/AGENT_DAILY_WORKFLOW_RUNBOOK.md, docs/WECHAT_AGENT_PUBLISH_RUNBOOK.md, and .trae/rules/project-agent-workflow.md if present.

Use real APIs, real browser state, and real WeChat draft data. Verify one step before the next. Never treat sample data, fallback data, guessed state, reaching a QR code, or opening a preview page as publish success.

For WeChat drafts, the verified editor path is:
草稿箱 -> 目标草稿 -> 操作区“编辑”按钮 -> action=edit 编辑页

Do not click the title, cover, first link, or /s/ preview link as the editor entry. Stop at the WeChat verification QR code and ask for human scan.

For new Agent articles, save and upload are separate steps:
1. save with POST /api/admin/agent/articles and publish_to_wechat_draft=false
2. record the returned brief_id
3. upload/retry with POST /api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent
Never delete a saved article only because WeChat upload failed.
```

## Verified WeChat Draft-To-Editor Path

Real-browser verified on 2026-06-21:

`草稿箱 -> 目标草稿 -> 操作区“编辑”按钮 -> action=edit 编辑页`

Operational details:

- `action=list_card` is the draft box, not the editor.
- A normal `/s/` article link is usually preview, not editor.
- The first link, title, or cover inside a draft card may open preview.
- To open an existing draft, locate the target draft card and click the card action area's `编辑` button.
- Success is the final URL containing `action=edit`.
- This verified step only means the editor opened; it does not mean the article was published.

## WeChat Publish Guardrails

- For existing drafts, do not save as draft as the final step when the goal is publish precheck.
- For new Agent articles, prefer `docs/AGENT_DAILY_WORKFLOW_RUNBOOK.md`: save first with `publish_to_wechat_draft=false`, record `brief_id`, then upload or retry that same article with `/api/admin/briefs/{brief_id}/wechat-draft?triggered_by=agent`.
- Complete cover and publish settings, then click through only until the WeChat verification QR code.
- Required publish-precheck settings: AI cover, original declaration, reward, collection `AI新闻`, and claim source `个人观点，仅供参考`.
- Stop at the QR code and ask the user to scan.
- If the browser has both the draft box and editor open, keep the `action=edit` editor tab and close or ignore the draft box tab before screenshots or further actions.
- For button-level details and failure triage, follow `docs/WECHAT_AGENT_PUBLISH_RUNBOOK.md`.

## Change Discipline

- Read the codebase before changing behavior.
- Preserve user changes in the working tree; do not revert unrelated files.
- Add focused tests for browser workflow fixes, especially when selector behavior changes.
- For WeChat automation, a unit test is not enough for final confidence: run the narrow real-browser path when possible and record the observed state precisely.
