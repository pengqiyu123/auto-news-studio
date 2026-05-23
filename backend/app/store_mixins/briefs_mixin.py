from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..deep_dive import fetch_and_extract_link
from ..briefing import (
    build_agent_article_writing_guide,
    build_brief_summary,
    build_douyin_article_markdown,
    build_douyin_prompt_package_markdown,
    build_douyin_summary,
    build_douyin_title,
    build_prompt_package_markdown,
    build_rule_brief_payload,
    optimize_wechat_article_title,
    rewrite_markdown_title,
)
from ..models import AgentArticlePayload, AgentWorkflowItem, BriefItem, BriefRecordCounts, BriefStageCounts, DictOkResponse, DouyinArticleFillPayload, EventDeepDive
from ..publishers import (
    build_preview_url,
    build_wechat_target_id,
    create_publish_task,
    extract_wechat_appmsg_id,
    run_browser_action,
)
from ..services.wechat_reconcile import project_briefs
from ..store_base import UTC, now_iso, parse_time
from ..wechat_format import markdown_to_wechat_html


class BriefsMixin:
    def _project_briefs(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return project_briefs(state)

    def _workflow_mode_for_trigger(self, triggered_by: str) -> str:
        return "agent" if str(triggered_by or "").strip() == "agent" else "traditional"

    def _resolve_brief_summary(
        self,
        *,
        brief: dict[str, Any] | None = None,
        summary: str = "",
        one_line: str = "",
        facts: list[str] | None = None,
        event_summary: str = "",
    ) -> str:
        source = brief or {}
        return build_brief_summary(
            summary=summary or str(source.get("summary") or "").strip(),
            one_line=one_line or str(source.get("one_line") or "").strip(),
            facts=facts if facts is not None else list(source.get("facts", [])),
            event_summary=event_summary,
        )

    def _agent_workflows(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        items = state.setdefault("agent_workflows", [])
        if not isinstance(items, list):
            state["agent_workflows"] = []
            return state["agent_workflows"]
        return items

    def _find_agent_workflow(self, state: dict[str, Any], workflow_session_id: str) -> dict[str, Any]:
        target = str(workflow_session_id or "").strip()
        for item in self._agent_workflows(state):
            if isinstance(item, dict) and str(item.get("workflow_session_id") or "").strip() == target:
                return item
        raise ValueError(f"未找到 Agent 工作流：{workflow_session_id}")

    def _list_agent_workflow_items(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        items = [item for item in self._agent_workflows(state) if isinstance(item, dict)]
        items.sort(
            key=lambda item: parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return items

    def list_agent_workflows(self) -> list[AgentWorkflowItem]:
        state = self._read_live()
        return [AgentWorkflowItem(**item) for item in self._list_agent_workflow_items(state)]

    def get_agent_workflow(self, workflow_session_id: str) -> AgentWorkflowItem:
        state = self._read_live()
        return AgentWorkflowItem(**self._find_agent_workflow(state, workflow_session_id))

    def _ensure_agent_workflow(
        self,
        state: dict[str, Any],
        *,
        brief_id: str | None = None,
        event_id: str,
        current_step: str,
        target_platforms: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_event_id = str(event_id or "").strip()
        for item in self._list_agent_workflow_items(state):
            if str(item.get("event_id") or "").strip() != normalized_event_id:
                continue
            if str(item.get("status") or "running") in {"completed", "abandoned"}:
                continue
            item["status"] = "running"
            item["current_step"] = current_step
            item["updated_at"] = now_iso()
            item["finished_at"] = None
            item["last_error"] = None
            if target_platforms:
                item["target_platforms"] = list(dict.fromkeys([*list(item.get("target_platforms", [])), *target_platforms]))
            return item

        workflow = {
            "workflow_session_id": f"agentwf-{uuid4().hex[:12]}",
            "status": "running",
            "current_step": current_step,
            "event_id": normalized_event_id or None,
            "material_brief_id": None,
            "article_brief_id": None,
            "target_platforms": list(dict.fromkeys(target_platforms or [])),
            "last_error": None,
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "finished_at": None,
        }
        self._agent_workflows(state).insert(0, workflow)
        return workflow

    def _set_agent_workflow_step(
        self,
        state: dict[str, Any],
        workflow_session_id: str,
        *,
        status: str | None = None,
        current_step: str | None = None,
        material_brief_id: str | None = None,
        article_brief_id: str | None = None,
        target_platforms: list[str] | None = None,
        last_error: str | None = None,
        finished: bool = False,
    ) -> dict[str, Any]:
        workflow = self._find_agent_workflow(state, workflow_session_id)
        if status:
            workflow["status"] = status
        if current_step:
            workflow["current_step"] = current_step
        if material_brief_id is not None:
            workflow["material_brief_id"] = material_brief_id
        if article_brief_id is not None:
            workflow["article_brief_id"] = article_brief_id
        if target_platforms:
            workflow["target_platforms"] = list(dict.fromkeys([*list(workflow.get("target_platforms", [])), *target_platforms]))
        workflow["last_error"] = last_error
        workflow["updated_at"] = now_iso()
        workflow["finished_at"] = now_iso() if finished else None
        return workflow

    def create_brief_from_event(self, event_id: str, *, triggered_by: str = "dashboard") -> BriefItem:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            workflow = None
            if self._workflow_mode_for_trigger(triggered_by) == "agent":
                workflow = self._ensure_agent_workflow(state, event_id=event_id, current_step="event_selected")
            deep_dive = self._find_deep_dive_for_event(state, event_id)
            if not deep_dive or str(deep_dive.get("status") or "") not in {"ready", "partial"}:
                if workflow:
                    # Persist the newly created workflow before a nested deep-dive call
                    # reloads state from disk; otherwise the follow-up workflow lookup can
                    # miss this in-memory session and create a duplicate path.
                    self._write(state)
                deep_dive_result = self.create_event_deep_dive(event_id, triggered_by=triggered_by)
                deep_dive = deep_dive_result.model_dump()
                state = self._upgrade_state(self._read())
                if workflow:
                    workflow = self._find_agent_workflow(state, str(workflow.get("workflow_session_id") or ""))
                event = self._find_event(state, event_id)
                deep_dive = self._find_deep_dive_for_event(state, event_id) or deep_dive
            deep_dive_status = str((deep_dive or {}).get("status") or "")
            if deep_dive_status not in {"ready", "partial"}:
                reason = str((deep_dive or {}).get("last_error") or "正文深挖尚未完成，暂时无法生成简报。")
                raise ValueError(reason)
            base_payload = build_rule_brief_payload(event, deep_dive)
            llm_service = self._make_llm_service(state)
            one_line, why_it_matters, risk_notes, brief_level = self._maybe_enhance_brief(llm_service, event, deep_dive, base_payload)
            full_text_sources = self._build_full_text_sources_for_ai(deep_dive)
            source_quotes: list[dict[str, str]] = []
            for item in deep_dive.get("sources", []):
                source_name = str(item.get("source_name") or "未知来源")
                for quote in item.get("quotes", [])[:1]:
                    compact = str(quote).strip()
                    if compact:
                        source_quotes.append({"source_name": source_name, "quote": compact})
            summary = self._resolve_brief_summary(
                summary=str(base_payload.get("summary") or "").strip(),
                one_line=one_line,
                facts=list(base_payload.get("facts", [])),
                event_summary=str(event.get("summary") or "").strip(),
            )
            prompt_package_markdown = build_prompt_package_markdown(
                title=str(base_payload.get("title") or ""),
                one_line=one_line,
                why_it_matters=why_it_matters,
                facts=list(base_payload.get("facts", [])),
                full_text_sources=[
                    {
                        "source_name": str(item.get("source_name") or "未知来源"),
                        "title": str(item.get("title") or ""),
                        "full_text": str(item.get("cleaned_full_text") or ""),
                    }
                    for item in full_text_sources
                ],
                source_quotes=source_quotes[:4],
                timeline=list(base_payload.get("timeline", [])),
                risk_notes=risk_notes,
                source_links=list(base_payload.get("source_links", [])),
            )
            wechat_markdown = str(base_payload.get("wechat_markdown") or "")
            douyin_prompt_package_markdown = str(base_payload.get("douyin_prompt_package_markdown") or "")
            douyin_title = str(base_payload.get("douyin_title") or "")
            douyin_summary = str(base_payload.get("douyin_summary") or "")
            douyin_markdown = str(base_payload.get("douyin_markdown") or "")
            existing = self._find_brief_record_for_event_by_level(state, event_id, brief_level="rule")
            brief = self._build_brief_dict(
                event_id=event_id,
                deep_dive_id=str(deep_dive.get("id") or ""),
                brief_level=brief_level,
                title=str(base_payload.get("title") or event.get("title") or ""),
                summary=summary,
                one_line=one_line,
                why_it_matters=why_it_matters,
                facts=list(base_payload.get("facts", [])),
                quotes=list(base_payload.get("quotes", [])),
                timeline=list(base_payload.get("timeline", [])),
                entity_names=list(base_payload.get("entity_names", [])),
                source_links=list(base_payload.get("source_links", [])),
                risk_notes=risk_notes,
                prompt_package_markdown=prompt_package_markdown,
                douyin_prompt_package_markdown=douyin_prompt_package_markdown,
                wechat_markdown=wechat_markdown,
                douyin_title=douyin_title,
                douyin_summary=douyin_summary,
                douyin_markdown=douyin_markdown,
                workflow_mode=self._workflow_mode_for_trigger(triggered_by),
                driver_label=str(existing.get("driver_label") or "") if existing else "",
                existing=existing,
                workflow_session_id=str(workflow.get("workflow_session_id") or "") if workflow else None,
            )
            self._upsert_brief(state, brief, existing)
            event["brief_id"] = brief["id"]
            if workflow:
                self._set_agent_workflow_step(
                    state,
                    str(workflow.get("workflow_session_id") or ""),
                    current_step="material_brief_ready",
                    material_brief_id=str(brief["id"]),
                )
            self._sync_llm_usage(state, llm_service)
            self._append_log(state, "success", "brief", f"已生成简报：{brief['title']}", actor=triggered_by)
            self._write(state)
            return BriefItem(**brief)

    def create_agent_article(self, payload: AgentArticlePayload) -> BriefItem:
        raw_title = str(payload.title or "").strip()
        article_markdown = str(payload.article_markdown or "").strip()
        if not raw_title:
            raise ValueError("文章标题不能为空。")
        if not article_markdown:
            raise ValueError("文章正文不能为空。")

        def dedupe_texts(values: list[str]) -> list[str]:
            result: list[str] = []
            seen: set[str] = set()
            for value in values:
                compact = re.sub(r"\s+", " ", str(value or "")).strip()
                if not compact or compact in seen:
                    continue
                seen.add(compact)
                result.append(compact)
            return result

        if payload.publish_to_wechat_draft:
            with self._lock:
                state = self._upgrade_state(self._read())
                self._ensure_agent_upload_allowed(state, actor=payload.triggered_by)

        with self._lock:
            state = self._upgrade_state(self._read())
            workflow = None
            if self._workflow_mode_for_trigger(payload.triggered_by) == "agent":
                target_platforms: list[str] = []
                if payload.publish_to_wechat_draft:
                    target_platforms.append("wechat")
                if payload.publish_to_douyin_article:
                    target_platforms.append("douyin")
                workflow = self._ensure_agent_workflow(
                    state,
                    event_id=payload.event_id,
                    current_step="event_selected",
                    target_platforms=target_platforms,
                )
            event = self._find_event(state, payload.event_id)
            deep_dive = self._find_deep_dive_for_event(state, payload.event_id)
            if not deep_dive:
                if workflow:
                    # Persist the workflow before nested deep-dive generation reloads
                    # state from disk; this keeps the same workflow session reusable
                    # through the rest of the agent article pipeline.
                    self._write(state)
                self.create_event_deep_dive(payload.event_id, triggered_by=payload.triggered_by)
                state = self._upgrade_state(self._read())
                if workflow:
                    workflow = self._find_agent_workflow(state, str(workflow.get("workflow_session_id") or ""))
                event = self._find_event(state, payload.event_id)
                deep_dive = self._find_deep_dive_for_event(state, payload.event_id)
            if not deep_dive:
                raise ValueError("未找到可关联的正文深挖记录，无法保存 AI 成稿。")

            facts = dedupe_texts(list(payload.facts))[:8]
            quotes = dedupe_texts(list(payload.quotes))[:6]
            timeline = dedupe_texts(list(payload.timeline))[:8]
            entity_names = dedupe_texts(list(payload.entity_names) or list(event.get("entity_names", [])))[:12]
            source_links = dedupe_texts(
                list(payload.source_links)
                or [
                    str(item.get("canonical_link") or item.get("original_link") or "").strip()
                    for item in deep_dive.get("sources", [])
                    if isinstance(item, dict)
                ]
            )[:12]
            risk_notes = dedupe_texts(list(payload.risk_notes))[:6]
            one_line = str(payload.one_line or "").strip()
            why_it_matters = str(payload.why_it_matters or "").strip()
            if not one_line:
                one_line = facts[0] if facts else (str(event.get("summary") or "").strip() or raw_title)
            if not why_it_matters:
                why_it_matters = str(deep_dive.get("worthiness", {}).get("reason") or "").strip()
            if not why_it_matters:
                why_it_matters = f"该事件当前处于 {event.get('alert_state') or '观察'} 阶段，且已具备可发布价值。"
            summary = self._resolve_brief_summary(
                summary=str(payload.summary or "").strip(),
                one_line=one_line,
                facts=facts,
                event_summary=str(event.get("summary") or "").strip(),
            )

            title = optimize_wechat_article_title(
                raw_title,
                one_line=one_line,
                facts=facts,
                article_markdown=article_markdown,
            )
            article_markdown = rewrite_markdown_title(article_markdown, raw_title, title)
            llm_service = self._make_llm_service(state)
            douyin_title = build_douyin_title(title)
            douyin_summary = build_douyin_summary(summary or one_line or why_it_matters, douyin_title or title)
            douyin_markdown = build_douyin_article_markdown(
                title=douyin_title or title,
                summary=douyin_summary,
                article_markdown=article_markdown,
                one_line=one_line,
                why_it_matters=why_it_matters,
                facts=facts,
                quotes=quotes,
                timeline=timeline,
                source_links=source_links,
            )
            douyin_title, douyin_summary, douyin_markdown = self._rewrite_article_for_douyin(
                llm_service,
                event=event,
                deep_dive=deep_dive,
                brief_payload={
                    "one_line": one_line,
                    "why_it_matters": why_it_matters,
                    "facts": facts,
                    "quotes": quotes,
                    "timeline": timeline,
                    "risk_notes": risk_notes,
                },
                article_markdown=article_markdown,
                fallback_title=douyin_title,
                fallback_summary=douyin_summary,
                fallback_markdown=douyin_markdown,
            )

            full_text_sources = self._build_full_text_sources_for_ai(deep_dive, limit=4)
            source_quotes: list[dict[str, str]] = []
            for item in deep_dive.get("sources", []):
                if not isinstance(item, dict):
                    continue
                source_name = str(item.get("source_name") or "未知来源").strip() or "未知来源"
                for quote in item.get("quotes", [])[:1]:
                    compact = str(quote or "").strip()
                    if compact:
                        source_quotes.append({"source_name": source_name, "quote": compact})
            prompt_package_markdown = (
                build_prompt_package_markdown(
                    title=title,
                    one_line=one_line,
                    why_it_matters=why_it_matters,
                    facts=facts,
                    full_text_sources=[
                        {
                            "source_name": str(item.get("source_name") or "未知来源"),
                            "title": str(item.get("title") or ""),
                            "full_text": str(item.get("cleaned_full_text") or ""),
                        }
                        for item in full_text_sources
                    ],
                    source_quotes=source_quotes[:4],
                    timeline=timeline,
                    risk_notes=risk_notes,
                    source_links=source_links,
                )
                + "\n\n## AI 成稿正文\n"
                + article_markdown
            ).strip()
            douyin_prompt_package_markdown = build_douyin_prompt_package_markdown(
                title=title,
                one_line=one_line,
                why_it_matters=why_it_matters,
                facts=facts,
                full_text_sources=[
                    {
                        "source_name": str(item.get("source_name") or "未知来源"),
                        "title": str(item.get("title") or ""),
                        "full_text": str(item.get("cleaned_full_text") or ""),
                    }
                    for item in full_text_sources
                ],
                source_quotes=source_quotes[:4],
                timeline=timeline,
                risk_notes=risk_notes,
                source_links=source_links,
                article_markdown=article_markdown,
            )

            existing = self._find_brief_record_for_event_by_level(state, payload.event_id, brief_level="article")
            existing_revision = self._brief_revision(existing) if existing else None
            brief_id = str(existing.get("id") or "") if existing else f"brief-{uuid4().hex[:12]}"
            brief = self._build_brief_dict(
                brief_id=brief_id,
                event_id=payload.event_id,
                deep_dive_id=str(deep_dive.get("id") or ""),
                brief_level="article",
                title=title,
                summary=summary,
                one_line=one_line,
                why_it_matters=why_it_matters,
                facts=facts,
                quotes=quotes,
                timeline=timeline,
                entity_names=entity_names,
                source_links=source_links,
                risk_notes=risk_notes,
                prompt_package_markdown=prompt_package_markdown,
                douyin_prompt_package_markdown=douyin_prompt_package_markdown,
                wechat_markdown=article_markdown,
                douyin_title=douyin_title,
                douyin_summary=douyin_summary,
                douyin_markdown=douyin_markdown,
                workflow_mode=self._workflow_mode_for_trigger(payload.triggered_by),
                driver_label=str(payload.driver_label or "").strip(),
                existing=existing,
                workflow_session_id=str(workflow.get("workflow_session_id") or "") if workflow else None,
            )
            if not brief.get("wechat_target_id"):
                brief["wechat_target_id"] = build_wechat_target_id(brief_id)
            if not brief.get("preview_url"):
                brief["preview_url"] = build_preview_url(brief_id)
            next_revision = self._brief_revision(brief)
            revision_changed = existing_revision != next_revision
            if existing and not revision_changed:
                brief["stage"] = existing.get("stage") or "prepared"
                brief["delivery_status"] = existing.get("delivery_status") or "idle"
                brief["needs_resync"] = bool(existing.get("needs_resync"))
                brief["last_synced_revision"] = existing.get("last_synced_revision")
                brief["last_successful_upload_at"] = existing.get("last_successful_upload_at")
                brief["last_verified_at"] = existing.get("last_verified_at")
                brief["last_delivery_error_kind"] = existing.get("last_delivery_error_kind")
                brief["last_error"] = existing.get("last_error")
            elif existing:
                brief["stage"] = "prepared"
                brief["delivery_status"] = "idle"
                brief["needs_resync"] = bool(existing.get("last_synced_revision") or existing.get("wechat_editor_url"))
                brief["last_synced_revision"] = None
                brief["last_successful_upload_at"] = None
                brief["last_verified_at"] = None
                brief["last_delivery_error_kind"] = None
                brief["last_error"] = None

            self._upsert_brief(state, brief, existing)
            self._append_log(
                state,
                "success",
                "brief",
                f"已保存 AI 成稿：{title}",
                actor=payload.triggered_by,
                detail=(
                    f"driver={payload.driver_label} | "
                    f"publish_to_wechat_draft={payload.publish_to_wechat_draft} | "
                    f"publish_to_douyin_article={payload.publish_to_douyin_article}"
                ),
            )
            if workflow:
                self._set_agent_workflow_step(
                    state,
                    str(workflow.get("workflow_session_id") or ""),
                    current_step="article_saved",
                    material_brief_id=str(workflow.get("material_brief_id") or "") or None,
                    article_brief_id=brief_id,
                    target_platforms=[
                        *(["wechat"] if payload.publish_to_wechat_draft else []),
                        *(["douyin"] if payload.publish_to_douyin_article else []),
                    ],
                )
            self._write(state)

        latest_brief = BriefItem(**brief)
        if payload.publish_to_wechat_draft:
            latest_brief = self.sync_brief_wechat_draft(brief_id, triggered_by=payload.triggered_by)
        if payload.publish_to_douyin_article:
            session = self.open_douyin_article_publish()
            if session.last_error:
                raise ValueError(str(session.last_error))
            latest_brief = self.fill_douyin_article(DouyinArticleFillPayload(brief_id=brief_id))
            latest_session = self.get_douyin_browser_session()
            if latest_session.last_error:
                raise ValueError(str(latest_session.last_error))
        if workflow:
            with self._lock:
                state = self._upgrade_state(self._read())
                final_step = "article_saved"
                finished = False
                if payload.publish_to_douyin_article:
                    final_step = "douyin_uploaded"
                    finished = True
                elif payload.publish_to_wechat_draft:
                    final_step = "wechat_uploaded"
                    finished = True
                self._set_agent_workflow_step(
                    state,
                    str(workflow.get("workflow_session_id") or ""),
                    status="completed" if finished else "running",
                    current_step=final_step,
                    article_brief_id=brief_id,
                    target_platforms=[
                        *(["wechat"] if payload.publish_to_wechat_draft else []),
                        *(["douyin"] if payload.publish_to_douyin_article else []),
                    ],
                    finished=finished,
                )
                self._write(state)
        return latest_brief

    def _ensure_agent_upload_allowed(self, state: dict[str, Any], actor: str = "agent") -> None:
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        control_state = str(runtime.get("control_state") or "stopped")
        run_status = str(run.get("status") or "idle")
        current_cycle = str(runtime.get("current_cycle") or "idle")
        scheduler_running = bool(runtime.get("scheduler_running"))
        scheduler_active = scheduler_running or control_state in {"armed", "waiting", "running"} or (
            run_status == "running" and not self._runtime_run_is_stale(run)
        )
        if not scheduler_active:
            return
        message = "当前自动调度器正在运行，请先停止传统模式，再执行 Agent 上传微信草稿箱。"
        self._append_log(
            state,
            "warning",
            "wechat",
            message,
            stream="business_event",
            actor=actor,
            detail=f"control_state={control_state} | run_status={run_status} | current_cycle={current_cycle}",
        )
        self._write(state)
        raise ValueError(message)

    def create_event_deep_dive(self, event_id: str, *, force: bool = False, triggered_by: str = "dashboard") -> EventDeepDive:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            event["watchlisted"] = True
            event["ignored"] = False
            workflow = None
            if self._workflow_mode_for_trigger(triggered_by) == "agent":
                workflow = self._ensure_agent_workflow(state, event_id=event_id, current_step="event_selected")
            existing = self._find_deep_dive_for_event(state, event_id)
            if existing and not force and str(existing.get("status") or "") in {"ready", "partial"}:
                return EventDeepDive(**existing)

            resolved_evidence_pack = self._event_deep_dive_inputs(state, event)
            max_links = 12
            timeout_seconds = 12.0
            started_at = now_iso()
            sources: list[dict[str, Any]] = []
            for item in resolved_evidence_pack[:max_links]:
                sources.append(fetch_and_extract_link(item, timeout_seconds=timeout_seconds))

            success_sources = [item for item in sources if str(item.get("extract_status") or "") == "extracted"]
            failed_count = len([item for item in sources if str(item.get("extract_status") or "") != "extracted"])
            status = "ready" if success_sources and not failed_count else "partial" if success_sources else "failed"
            facts = self._generate_deep_dive_facts(event, success_sources)
            quotes: list[str] = []
            seen_quotes: set[str] = set()
            for item in success_sources:
                for quote in item.get("quotes", [])[:2]:
                    compact = str(quote).strip()
                    if not compact or compact in seen_quotes:
                        continue
                    seen_quotes.add(compact)
                    quotes.append(compact)
                    if len(quotes) >= 6:
                        break
                if len(quotes) >= 6:
                    break
            timeline = self._generate_deep_dive_timeline(event, resolved_evidence_pack)
            worth_to_brief, worth_reason = self._evaluate_worthiness(
                event,
                {"success_count": len(success_sources), "facts": facts, "quotes": quotes},
            )
            record = {
                "id": existing.get("id") if existing else f"dd-{uuid4().hex[:12]}",
                "event_id": event_id,
                "status": status,
                "started_at": started_at,
                "finished_at": now_iso(),
                "updated_at": now_iso(),
                "attempted_count": len(sources),
                "success_count": len(success_sources),
                "failed_count": failed_count,
                "resolved_evidence_pack": resolved_evidence_pack,
                "full_text_sources": success_sources,
                "sources": sources,
                "facts": facts,
                "quotes": quotes,
                "timeline": timeline,
                "worthiness": {"worth_to_brief": worth_to_brief, "reason": worth_reason},
                "last_error": None if success_sources else "没有拿到可用正文来源",
                "article_writing_guide": build_agent_article_writing_guide(),
            }
            if existing:
                index = next(
                    idx for idx, item in enumerate(state.get("event_deep_dives", []))
                    if isinstance(item, dict) and str(item.get("id") or "") == str(existing.get("id") or "")
                )
                state["event_deep_dives"][index] = record
            else:
                state.setdefault("event_deep_dives", []).insert(0, record)
            event["deep_dive_id"] = record["id"]
            self._append_log(
                state,
                "success" if success_sources else "warning",
                "deep_dive",
                f"已完成正文深挖：{event.get('title', '未命名事件')}",
                actor=triggered_by,
                detail=self._summarize_deep_dive(record),
            )
            if workflow and success_sources:
                self._set_agent_workflow_step(
                    state,
                    str(workflow.get("workflow_session_id") or ""),
                    current_step="deep_dive_ready",
                )
            elif workflow and not success_sources:
                self._set_agent_workflow_step(
                    state,
                    str(workflow.get("workflow_session_id") or ""),
                    status="failed",
                    current_step="deep_dive_ready",
                    last_error=str(record.get("last_error") or "正文深挖失败。"),
                )
            self._write(state)
            return EventDeepDive(**record)

    def list_event_deep_dives(self) -> list[EventDeepDive]:
        state = self._read_live()
        items = [item for item in state.get("event_deep_dives", []) if isinstance(item, dict)]
        items.sort(key=lambda item: parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return [EventDeepDive(**item) for item in items]

    def get_event_deep_dive(self, event_id: str) -> EventDeepDive:
        state = self._read_live()
        record = self._find_deep_dive_for_event(state, event_id)
        if not record:
            raise ValueError(f"未找到事件正文深挖：{event_id}")
        if not record.get("article_writing_guide"):
            record["article_writing_guide"] = build_agent_article_writing_guide()
        return EventDeepDive(**record)

    def list_briefs(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        stage: str = "all",
        q: str = "",
        workflow_mode: str = "all",
    ) -> tuple[list[BriefItem], int, int, int, bool, BriefStageCounts, BriefRecordCounts]:
        state = self._read_live()
        items = self._project_briefs(state)
        items.sort(key=lambda item: parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=self._utc_tz()), reverse=True)
        stage_counts = BriefStageCounts(
            all=len(items),
            prepared=sum(1 for item in items if str(item.get("stage") or "") == "prepared"),
            synced=sum(1 for item in items if str(item.get("stage") or "") == "synced"),
            failed=sum(
                1
                for item in items
                if str(item.get("stage") or "") == "failed" or bool(str(item.get("last_error") or "").strip())
            ),
        )
        record_counts = BriefRecordCounts(
            all=len(items),
            local_only=sum(1 for item in items if str(item.get("record_status") or "") == "local_only"),
            draft_synced=sum(1 for item in items if str(item.get("record_status") or "") == "draft_synced"),
            published=sum(1 for item in items if str(item.get("record_status") or "") == "published"),
            exceptions=sum(1 for item in items if item.get("record_exception")),
        )
        stage_filter = str(stage or "all").strip().lower()
        workflow_filter = str(workflow_mode or "all").strip().lower()
        keyword = str(q or "").strip().lower()

        def matches_stage(item: dict[str, Any]) -> bool:
            if stage_filter == "all":
                return True
            if stage_filter == "local_only":
                return str(item.get("record_status") or "") == "local_only"
            if stage_filter == "draft_synced":
                return str(item.get("record_status") or "") == "draft_synced"
            if stage_filter == "published":
                return str(item.get("record_status") or "") == "published"
            if stage_filter == "exceptions":
                return bool(item.get("record_exception"))
            return True

        def matches_query(item: dict[str, Any]) -> bool:
            if not keyword:
                return True
            haystack = "\n".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("one_line") or ""),
                    str(item.get("why_it_matters") or ""),
                ]
            ).lower()
            return keyword in haystack

        def matches_workflow(item: dict[str, Any]) -> bool:
            if workflow_filter == "all":
                return True
            return str(item.get("workflow_mode") or "traditional").strip().lower() == workflow_filter

        filtered = [item for item in items if matches_stage(item) and matches_workflow(item) and matches_query(item)]
        page_items, total, safe_page, safe_page_size, has_more = self._paginate_items(
            filtered,
            page=page,
            page_size=page_size,
        )
        return [BriefItem(**item) for item in page_items], total, safe_page, safe_page_size, has_more, stage_counts, record_counts

    def get_brief(self, brief_id: str) -> BriefItem:
        state = self._read_live()
        brief = self._find_brief(state, brief_id)
        projected = next((item for item in self._project_briefs(state) if str(item.get("id") or "") == brief_id), None)
        return BriefItem(**(projected or brief))

    def _brief_revision(self, brief: dict[str, Any]) -> str:
        stable_payload = {
            "title": str(brief.get("title") or "").strip(),
            "summary": str(brief.get("summary") or "").strip(),
            "one_line": str(brief.get("one_line") or "").strip(),
            "why_it_matters": str(brief.get("why_it_matters") or "").strip(),
            "facts": list(brief.get("facts", [])),
            "quotes": list(brief.get("quotes", [])),
            "timeline": list(brief.get("timeline", [])),
            "risk_notes": list(brief.get("risk_notes", [])),
            "source_links": list(brief.get("source_links", [])),
            "douyin_prompt_package_markdown": str(brief.get("douyin_prompt_package_markdown") or ""),
            "wechat_markdown": str(brief.get("wechat_markdown") or ""),
            "wechat_html": str(brief.get("wechat_html") or ""),
            "douyin_title": str(brief.get("douyin_title") or ""),
            "douyin_summary": str(brief.get("douyin_summary") or ""),
            "douyin_markdown": str(brief.get("douyin_markdown") or ""),
        }
        digest = hashlib.sha256(
            json.dumps(stable_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return f"brief:{brief.get('id') or 'unknown'}:{digest}"

    def _brief_transition(
        self,
        current_stage: str,
        current_delivery_status: str,
        *,
        upload_success: bool,
        is_session_level_error: bool,
        verify_status: str,
    ) -> dict[str, Any]:
        result = {
            "new_stage": current_stage or "prepared",
            "new_delivery_status": current_delivery_status or "idle",
            "last_delivery_error_kind": None,
            "should_set_needs_resync": False,
            "should_clear_last_synced_revision": False,
        }
        if not upload_success:
            result["new_stage"] = "failed"
            result["new_delivery_status"] = "check_failed" if is_session_level_error else "idle"
            result["last_delivery_error_kind"] = "session" if is_session_level_error else "upload"
            result["should_set_needs_resync"] = False
            result["should_clear_last_synced_revision"] = True
            return result

        result["new_stage"] = "synced"
        if verify_status == "verified":
            result["new_delivery_status"] = "verified"
            result["last_delivery_error_kind"] = None
        elif verify_status == "target_missing":
            result["new_stage"] = "prepared"
            result["new_delivery_status"] = "target_missing"
            result["last_delivery_error_kind"] = "target_missing"
            result["should_clear_last_synced_revision"] = True
        elif verify_status in {"scrape_failed", "check_failed"}:
            result["new_delivery_status"] = "check_failed"
            result["last_delivery_error_kind"] = verify_status
        else:
            result["new_delivery_status"] = "uploaded_unverified"
            result["last_delivery_error_kind"] = None
        return result

    def sync_brief_wechat_draft(self, brief_id: str, triggered_by: str = "dashboard") -> BriefItem:
        with self._lock:
            state = self._upgrade_state(self._read())
            if triggered_by == "agent":
                self._ensure_agent_upload_allowed(state, actor=triggered_by)
            brief = self._find_brief(state, brief_id)
            if triggered_by == "agent" and str(brief.get("brief_level") or "rule") != "article":
                raise ValueError("Agent 模式禁止上传传统简报，请使用 /api/admin/agent/articles 保存并上传长文。")
            current_markdown = str(brief.get("wechat_markdown") or "")
            if current_markdown:
                brief["wechat_html"] = markdown_to_wechat_html(current_markdown)
            current_revision = self._brief_revision(brief)
            already_synced_same_revision = (
                str(brief.get("stage") or "") == "synced"
                and not bool(brief.get("needs_resync"))
                and str(brief.get("last_synced_revision") or "").strip()
                and str(brief.get("last_synced_revision") or "").strip() == current_revision
            )
            if already_synced_same_revision:
                message = "该版本简报已同步到微信草稿箱，无需重复上传。"
                state["publish_tasks"].insert(
                    0,
                    create_publish_task(
                        brief_id,
                        "sync_wechat_draft",
                        "completed",
                        message,
                        triggered_by,
                        str(state["channels"]["wechat"]["selectors_version"]),
                        step_logs=["命中手动同步幂等保护，跳过重复上传。"],
                    ),
                )
                self._append_log(
                    state,
                    "info",
                    "wechat",
                    f"{message}{brief['title']}",
                    detail=current_revision,
                )
                self._write(state)
                return BriefItem(**brief)
            if not brief.get("wechat_target_id"):
                brief["wechat_target_id"] = build_wechat_target_id(str(brief["id"]))
            brief["preview_url"] = build_preview_url(str(brief["id"]))
            brief["last_delivery_attempt_at"] = now_iso()
            brief["delivery_attempt_count"] = int(brief.get("delivery_attempt_count", 0) or 0) + 1
            brief["needs_resync"] = False
            event_summary = ""
            event_id = str(brief.get("event_id") or "").strip()
            if event_id:
                try:
                    event_summary = str(self._find_event(state, event_id).get("summary") or "").strip()
                except ValueError:
                    event_summary = ""
            resolved_summary = self._resolve_brief_summary(
                brief=brief,
                event_summary=event_summary,
            )
            brief["summary"] = resolved_summary
            browser = self._refresh_browser_session(state)
            browser_payload = {
                **brief,
                "summary": resolved_summary,
                "markdown": str(brief.get("wechat_markdown") or ""),
            }
            browser, artifacts, step_logs = run_browser_action("sync_wechat_draft", browser_payload, state["channels"]["wechat"], browser)
            state["browser"]["wechat"] = browser
            verification_status = str(browser.get("verification_status") or "").strip()
            verification_message = str(browser.get("verification_message") or "").strip()
            transition = self._brief_transition(
                str(brief.get("stage") or "prepared"),
                str(brief.get("delivery_status") or "idle"),
                upload_success=not bool(browser.get("last_error")),
                is_session_level_error=bool(browser.get("is_session_level_error")),
                verify_status=verification_status,
            )
            brief["stage"] = transition["new_stage"]
            brief["delivery_status"] = transition["new_delivery_status"]
            brief["last_delivery_error_kind"] = transition["last_delivery_error_kind"]
            brief["needs_resync"] = bool(transition["should_set_needs_resync"])
            if transition["should_clear_last_synced_revision"]:
                brief["last_synced_revision"] = None
                brief["last_successful_upload_at"] = None

            if browser.get("last_error"):
                brief["last_error"] = str(browser.get("last_error"))
            else:
                existing_editor_url = str(brief.get("wechat_editor_url") or "").strip()
                existing_remote_appmsg_id = str(brief.get("wechat_remote_appmsg_id") or "").strip()
                resolved_editor_url = (
                    browser.get("last_verified_remote_url")
                    or browser.get("last_synced_editor_url")
                    or existing_editor_url
                )
                resolved_remote_appmsg_id = (
                    browser.get("last_verified_remote_appmsg_id")
                    or extract_wechat_appmsg_id(str(browser.get("last_synced_editor_url") or ""))
                    or existing_remote_appmsg_id
                )
                if resolved_editor_url:
                    brief["wechat_editor_url"] = str(resolved_editor_url)
                if resolved_remote_appmsg_id:
                    brief["wechat_remote_appmsg_id"] = str(resolved_remote_appmsg_id)
                if verification_status == "target_missing":
                    brief["stage"] = "prepared"
                    brief["delivery_status"] = "target_missing"
                    brief["last_synced_revision"] = None
                    brief["last_successful_upload_at"] = None
                    brief["last_error"] = verification_message or "已上传，但远端草稿箱未确认到目标稿件，回退为 prepared。"
                elif verification_status in {"verification_failed", "check_failed", "scrape_failed"}:
                    brief["last_error"] = verification_message or "已上传，但草稿箱确认未完成。"
                    brief["last_synced_revision"] = None
                    brief["last_successful_upload_at"] = None
                else:
                    brief["last_error"] = None
                    brief["last_synced_revision"] = self._brief_revision(brief)
                    brief["last_successful_upload_at"] = now_iso()
                if verification_status == "verified":
                    brief["last_verified_at"] = now_iso()
            brief["updated_at"] = now_iso()
            task_status = "completed" if brief["stage"] == "synced" else "failed"
            if brief["stage"] == "synced":
                if verification_status == "verified":
                    task_message = "已同步简报到微信草稿箱，并确认目标稿件存在。"
                elif verification_status == "target_missing":
                    task_message = "已同步简报到微信草稿箱，但正式草稿箱暂未确认到目标稿件。"
                elif verification_status in {"verification_failed", "check_failed", "scrape_failed"}:
                    task_message = "已同步简报到微信草稿箱，但草稿箱检查失败，当前保留已上传状态。"
                else:
                    task_message = "已同步简报到微信草稿箱。"
            else:
                task_message = "简报同步微信草稿箱失败。"
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    brief_id,
                    "sync_wechat_draft",
                    task_status,
                    task_message,
                    triggered_by,
                    str(state["channels"]["wechat"]["selectors_version"]),
                    artifacts=artifacts,
                    step_logs=step_logs,
                ),
            )
            self._append_log(
                state,
                "success" if brief["stage"] == "synced" else "warning",
                "wechat",
                f"{task_message.rstrip('。')}：{brief['title']}",
                detail=brief.get("last_error"),
            )
            if str(brief.get("workflow_mode") or "traditional") == "agent" and str(brief.get("workflow_session_id") or "").strip():
                self._set_agent_workflow_step(
                    state,
                    str(brief.get("workflow_session_id") or ""),
                    status="completed" if brief["stage"] == "synced" else "failed",
                    current_step="wechat_uploaded" if brief["stage"] == "synced" else "article_saved",
                    article_brief_id=str(brief.get("id") or ""),
                    target_platforms=["wechat"],
                    last_error=str(brief.get("last_error") or "") or None,
                    finished=brief["stage"] == "synced",
                )
            self._write(state)
            return BriefItem(**brief)

    def build_brief_copy_package(self, brief_id: str) -> str:
        state = self._upgrade_state(self._read())
        brief = self._find_brief(state, brief_id)
        return str(brief.get("prompt_package_markdown") or "")

    def delete_brief(self, brief_id: str, remote: str = "auto", triggered_by: str = "briefs") -> DictOkResponse:
        with self._lock:
            state = self._upgrade_state(self._read())
            brief = self._find_brief(state, brief_id)
            should_delete_remote = False
            if remote == "true":
                should_delete_remote = True
            elif remote == "auto":
                should_delete_remote = str(brief.get("stage") or "") == "synced"
            if should_delete_remote:
                remote_id = str(brief.get("wechat_remote_appmsg_id") or brief.get("wechat_editor_url") or "").strip()
                if not remote_id:
                    raise ValueError("该简报缺少远端草稿标识，无法删除微信草稿。")
                self.delete_wechat_remote_draft(remote_id, triggered_by=triggered_by)
                state = self._upgrade_state(self._read())
                brief = self._find_brief(state, brief_id)
                if str(brief.get("stage") or "") == "synced":
                    raise ValueError("远端草稿删除后，本地状态尚未完成回写，请稍后重试。")

            briefs = [item for item in state.get("briefs", []) if not (isinstance(item, dict) and str(item.get("id") or "") == brief_id)]
            state["briefs"] = briefs
            for event in state.get("intel_events", []):
                if isinstance(event, dict) and str(event.get("brief_id") or "") == brief_id:
                    event["brief_id"] = None
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    brief_id,
                    "delete_brief",
                    "completed",
                    "已删除本地简报。",
                    triggered_by,
                    str(state["channels"]["wechat"]["selectors_version"]),
                ),
            )
            self._append_log(state, "success", "brief", f"已删除本地简报：{brief.get('title') or brief_id}")
            self._write(state)
            return DictOkResponse(ok=True, message="已删除本地简报。")

    @staticmethod
    def _build_brief_dict(
        *,
        brief_id: str | None = None,
        event_id: str,
        deep_dive_id: str,
        brief_level: str,
        title: str,
        summary: str,
        one_line: str,
        why_it_matters: str,
        facts: list[str],
        quotes: list[str],
        timeline: list[str],
        entity_names: list[str],
        source_links: list[str],
        risk_notes: list[str],
        prompt_package_markdown: str,
        douyin_prompt_package_markdown: str,
        wechat_markdown: str,
        douyin_title: str,
        douyin_summary: str,
        douyin_markdown: str,
        workflow_mode: str,
        driver_label: str,
        existing: dict[str, Any] | None,
        workflow_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Shared brief dict constructor for both traditional and agent paths."""
        brief_id = str(brief_id or "").strip() or (str(existing.get("id") or "") if existing else f"brief-{uuid4().hex[:12]}")
        return {
            "id": brief_id,
            "event_id": event_id,
            "deep_dive_id": deep_dive_id,
            "brief_level": brief_level,
            "stage": existing.get("stage") if existing else "prepared",
            "title": title,
            "summary": summary,
            "one_line": one_line,
            "why_it_matters": why_it_matters,
            "facts": facts,
            "quotes": quotes,
            "timeline": timeline,
            "entity_names": entity_names,
            "source_links": source_links,
            "risk_notes": risk_notes,
            "prompt_package_markdown": prompt_package_markdown,
            "douyin_prompt_package_markdown": douyin_prompt_package_markdown,
            "wechat_markdown": wechat_markdown,
            "wechat_html": markdown_to_wechat_html(wechat_markdown),
            "douyin_title": douyin_title,
            "douyin_summary": douyin_summary,
            "douyin_markdown": douyin_markdown,
            "wechat_target_id": existing.get("wechat_target_id") if existing else None,
            "wechat_editor_url": existing.get("wechat_editor_url") if existing else None,
            "wechat_remote_appmsg_id": existing.get("wechat_remote_appmsg_id") if existing else None,
            "preview_url": existing.get("preview_url") if existing else None,
            "last_error": None,
            "delivery_status": existing.get("delivery_status") if existing else "idle",
            "delivery_attempt_count": int(existing.get("delivery_attempt_count", 0) or 0) if existing else 0,
            "last_delivery_attempt_at": existing.get("last_delivery_attempt_at") if existing else None,
            "last_verified_at": existing.get("last_verified_at") if existing else None,
            "last_delivery_error_kind": existing.get("last_delivery_error_kind") if existing else None,
            "needs_resync": bool(existing.get("needs_resync")) if existing else False,
            "last_synced_revision": existing.get("last_synced_revision") if existing else None,
            "last_successful_upload_at": existing.get("last_successful_upload_at") if existing else None,
            "updated_at": now_iso(),
            "driver_label": driver_label,
            "workflow_mode": workflow_mode,
            "workflow_session_id": workflow_session_id or (existing.get("workflow_session_id") if existing else None),
        }

    @staticmethod
    def _upsert_brief(state: dict[str, Any], brief: dict[str, Any], existing: dict[str, Any] | None) -> None:
        """Insert or update a brief dict in state."""
        if existing:
            index = next(
                idx for idx, item in enumerate(state.get("briefs", []))
                if isinstance(item, dict) and str(item.get("id") or "") == str(existing.get("id") or "")
            )
            state["briefs"][index] = brief
        else:
            state.setdefault("briefs", []).insert(0, brief)

    def _utc_tz(self):
        from ..store_base import UTC

        return UTC
