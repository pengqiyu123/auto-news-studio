from __future__ import annotations

from datetime import datetime
from typing import Any

from ..store.base import UTC, now_iso, parse_clock_time, parse_time


class DeliveryMixin:
    def _delivery_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._runtime_plan(state)

    def _delivery_filters(self, state: dict[str, Any]) -> dict[str, Any]:
        plan = self._delivery_plan(state)
        filters = plan.get("admission_filters", {})
        if not isinstance(filters, dict):
            filters = {}
        return {
            "require_watchlisted": bool(filters.get("require_watchlisted")),
            "require_entity_match": bool(filters.get("require_entity_match")),
            "min_source_count": max(int(filters.get("min_source_count", 0) or 0), 0),
            "min_fulltext_count": max(int(filters.get("min_fulltext_count", 1) or 1), 0),
            "breakout_only": bool(filters.get("breakout_only")),
            "exclude_existing_brief": bool(filters.get("exclude_existing_brief", True)),
            "exclude_synced_brief": bool(filters.get("exclude_synced_brief", True)),
        }

    def _delivery_mode_due(self, state: dict[str, Any], now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        plan = self._delivery_plan(state)
        mode = str(plan.get("delivery_mode") or "immediate")
        if mode != "scheduled_batch":
            return True
        clock = parse_clock_time(str(plan.get("delivery_schedule_time") or ""))
        if not clock:
            return False
        runtime = self._runtime(state)
        slot_dt = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if now < slot_dt:
            return False
        last_verified = parse_time(runtime.get("last_delivery_batch_at"))
        if not last_verified:
            return True
        return last_verified < slot_dt

    def _background_draft_check_due(self, state: dict[str, Any], now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        browser = state.get("browser", {}).get("wechat", {})
        if not isinstance(browser, dict):
            return False
        if not bool(browser.get("logged_in")):
            return False
        if bool(browser.get("busy")):
            return False
        checked_at = parse_time(browser.get("last_draft_check", {}).get("checked_at") if isinstance(browser.get("last_draft_check"), dict) else None)
        if not checked_at:
            return True
        return (now - checked_at).total_seconds() >= 120

    def _select_delivery_events_strict(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        plan = self._delivery_plan(state)
        strategy = str(plan.get("admission_strategy") or "balanced")
        filters = self._delivery_filters(state)
        limit = max(int(plan.get("batch_limit", 3) or 3), 1)
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)

        projected_events = [
            self._project_event_runtime_fields(state, item)
            for item in state.get("intel_events", [])
            if isinstance(item, dict) and not bool(item.get("ignored"))
        ]

        selected: list[dict[str, Any]] = []
        for event in projected_events:
            if filters["require_watchlisted"] and not bool(event.get("watchlisted")):
                continue
            if filters["require_entity_match"] and not list(event.get("entity_names", [])):
                continue
            if filters["breakout_only"] and str(event.get("alert_state") or "") != "breakout":
                continue
            if int(event.get("source_count", 0) or 0) < filters["min_source_count"]:
                continue
            if filters["exclude_existing_brief"] and str(event.get("brief_id") or "").strip():
                continue
            if filters["exclude_synced_brief"]:
                brief = brief_lookup.get(str(event.get("id") or ""))
                if brief and str(brief.get("stage") or "") == "synced":
                    continue

            alert_state = str(event.get("alert_state") or "")
            deep_dive = deep_dive_lookup.get(str(event.get("id") or ""))
            fulltext_count = int(deep_dive.get("success_count", 0) or 0) if deep_dive else 0

            if strategy == "conservative":
                if alert_state != "breakout":
                    continue
                if fulltext_count < max(filters["min_fulltext_count"], 2):
                    continue
                if not bool(event.get("worth_to_brief")):
                    continue
            elif strategy == "balanced":
                if alert_state not in {"rising", "breakout"}:
                    continue
                if deep_dive and fulltext_count < max(filters["min_fulltext_count"], 1):
                    continue
            else:
                if alert_state not in {"rising", "breakout"} and not bool(event.get("watchlisted")):
                    continue

            selected.append(event)

        selected.sort(key=lambda item: self._delivery_sort_key(item, deep_dive_lookup), reverse=True)
        return selected[:limit]

    def _select_delivery_events(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        plan = self._delivery_plan(state)
        filters = self._delivery_filters(state)
        selected = self._select_delivery_events_strict(state)
        if selected:
            return selected
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)

        projected_events = [
            self._project_event_runtime_fields(state, item)
            for item in state.get("intel_events", [])
            if isinstance(item, dict) and not bool(item.get("ignored"))
        ]

        limit = max(int(plan.get("batch_limit", 3) or 3), 1)
        fallback_candidates: list[dict[str, Any]] = []
        for event in projected_events:
            if not bool(event.get("worth_to_brief")):
                continue
            alert_state = str(event.get("alert_state") or "")
            if alert_state == "cooling" or alert_state == "new":
                continue
            if filters["require_watchlisted"] and not bool(event.get("watchlisted")):
                continue
            if filters["require_entity_match"] and not list(event.get("entity_names", [])):
                continue
            if int(event.get("source_count", 0) or 0) < filters["min_source_count"]:
                continue
            if filters["exclude_existing_brief"] and str(event.get("brief_id") or "").strip():
                continue
            if filters["exclude_synced_brief"]:
                brief = brief_lookup.get(str(event.get("id") or ""))
                if brief and str(brief.get("stage") or "") == "synced":
                    continue
            if str(event.get("alert_state") or "") == "cooling":
                continue
            fallback_candidates.append(event)

        fallback_candidates.sort(key=lambda item: self._delivery_sort_key(item, deep_dive_lookup), reverse=True)
        return fallback_candidates[:1]

    def _select_retry_briefs(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [
            item for item in state.get("briefs", [])
            if isinstance(item, dict) and (
                bool(item.get("needs_resync"))
                or str(item.get("stage") or "") in {"prepared", "failed"}
            )
        ]

        def retry_rank(item: dict[str, Any]) -> tuple[Any, ...]:
            needs_resync = bool(item.get("needs_resync"))
            stage = str(item.get("stage") or "")
            if needs_resync:
                priority = 0
            elif stage == "failed":
                priority = 1
            else:
                priority = 2
            event_lookup = {str(e.get("id") or ""): e for e in state.get("intel_events", []) if isinstance(e, dict) and e.get("id")}
            event = event_lookup.get(str(item.get("event_id") or "")) if str(item.get("event_id") or "").strip() else None
            updated_at = parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC)
            composite_score = float((event or {}).get("composite_score", 0) or 0)
            watchlisted = 1 if bool((event or {}).get("watchlisted")) else 0
            return (
                priority,
                -updated_at.timestamp(),
                -composite_score,
                -watchlisted,
            )

        candidates.sort(key=retry_rank)
        limit = max(int(self._delivery_plan(state).get("batch_limit", 3) or 3), 1)
        return candidates[:limit]

    def _delivery_sort_key(self, item: dict[str, Any], deep_dive_lookup: dict[str, dict[str, Any]]) -> tuple[Any, ...]:
        alert_rank = {"breakout": 3, "rising": 2, "watch": 1, "cooling": 0, "new": 0}.get(str(item.get("alert_state") or "new"), 0)
        deep_dive = deep_dive_lookup.get(str(item.get("id") or ""))
        evidence_score = int(deep_dive.get("success_count", 0) or 0) if deep_dive else 0
        return (
            alert_rank,
            float(item.get("worth_to_brief") or False),
            float(item.get("composite_score", 0) or 0),
            float(item.get("audience_fit_score", 0) or 0),
            float(item.get("velocity_score", 0) or 0),
            float(item.get("coverage_score", 0) or 0),
            float(item.get("freshness_score", 0) or 0),
            evidence_score,
            len(list(item.get("entity_names", []))),
        )

    def _run_delivery_pipeline(self, state: dict[str, Any], runtime: dict[str, Any], *, triggered_by: str) -> None:
        plan = self._delivery_plan(state)
        due_for_upload = self._select_retry_briefs(state)
        events: list[dict[str, Any]] = []
        if len(due_for_upload) < max(int(plan.get("batch_limit", 3) or 3), 1):
            events = self._select_delivery_events(state)
        selected_titles = [str(item.get("title") or "").strip() for item in events if str(item.get("title") or "").strip()]
        self._set_runtime_cycle_metric(runtime, "selected_event_count", len(events))
        runtime.setdefault("current_cycle_metrics", {})["selected_titles"] = selected_titles[:5]
        if not due_for_upload and not events:
            self._append_log(state, "info", "delivery", "本轮没有符合自动交付条件的事件，也没有待补传简报。", stream="system_runtime", actor=triggered_by)
            return
        strict_matches = self._select_delivery_events_strict(state)
        if events and not strict_matches:
            fallback_event = events[0]
            self._append_log(
                state,
                "warning",
                "delivery",
                f"严格筛选未命中，本轮改为兜底推进最高分事件：{fallback_event.get('title') or fallback_event.get('id') or 'unknown'}",
                stream="system_runtime",
                actor=triggered_by,
            )
        elif not events and not strict_matches and not due_for_upload:
            self._append_log(state, "info", "delivery", "本轮严格筛选和兜底筛选均未命中，跳过交付。", stream="system_runtime", actor=triggered_by)
            return

        stage_plan = self._stage_plan(runtime)
        stage_positions = {item["key"]: index + 1 for index, item in enumerate(stage_plan)}
        stage_total = len(stage_plan)

        deep_dives_completed = 0
        briefs_completed = 0
        synced_completed = 0
        verify_completed = 0
        brief_titles: list[str] = []
        synced_titles: list[str] = []
        if events:
            runtime["current_cycle"] = "deep_dive"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "deep_dive", 5),
                done=0,
                total=max(len(events), 1),
                label=f"阶段 {stage_positions.get('deep_dive', stage_total)}/{stage_total}：开始正文深挖",
            )
            self._progress_snapshot["cycle"] = "deep_dive"
            self._heartbeat_runtime_run(runtime, stage="deep_dive")
            self._write_runtime_checkpoint(state)

            for index, event in enumerate(events, start=1):
                event_id = str(event.get("id") or "")
                try:
                    deep_dive = self.create_event_deep_dive(event_id).model_dump()
                    state.update(self._upgrade_state(self._read()))
                    if str(deep_dive.get("status") or "") not in {"ready", "partial"}:
                        continue
                    if int(deep_dive.get("success_count", 0) or 0) < max(int(self._delivery_filters(state)["min_fulltext_count"]), 0):
                        continue
                    deep_dives_completed += 1
                    self._set_runtime_cycle_metric(runtime, "deep_dive_count", deep_dives_completed)
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "deep_dive", index / max(len(events), 1) * 100),
                        done=index,
                        total=max(len(events), 1),
                        label=f"已完成正文深挖 {index}/{max(len(events), 1)}",
                    )
                    self._heartbeat_runtime_run(runtime, stage="deep_dive")
                    self._write_runtime_checkpoint(state)
                except Exception as exc:
                    self._append_log(state, "warning", "delivery", f"正文深挖失败：{event.get('title') or event_id} - {exc}", stream="system_runtime", actor=triggered_by)

            runtime["current_cycle"] = "briefing"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "briefing", 5),
                done=0,
                total=max(len(events), 1),
                label=f"阶段 {stage_positions.get('briefing', stage_total)}/{stage_total}：开始生成简报",
            )
            self._progress_snapshot["cycle"] = "briefing"
            self._heartbeat_runtime_run(runtime, stage="briefing")
            self._write_runtime_checkpoint(state)

            for index, event in enumerate(events, start=1):
                event_id = str(event.get("id") or "")
                refreshed_state = self._upgrade_state(self._read())
                deep_dive = self._find_deep_dive_for_event(refreshed_state, event_id)
                if not deep_dive or str(deep_dive.get("status") or "") not in {"ready", "partial"}:
                    continue
                if int(deep_dive.get("success_count", 0) or 0) < max(int(self._delivery_filters(refreshed_state)["min_fulltext_count"]), 0):
                    continue
                try:
                    brief = self.create_brief_from_event(event_id).model_dump()
                    state.update(self._upgrade_state(self._read()))
                    briefs_completed += 1
                    due_for_upload.append(brief)
                    brief_title = str(brief.get("title") or "").strip()
                    if brief_title:
                        brief_titles.append(brief_title)
                    self._set_runtime_cycle_metric(runtime, "brief_count", briefs_completed)
                    runtime.setdefault("current_cycle_metrics", {})["brief_titles"] = brief_titles[:5]
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "briefing", index / max(len(events), 1) * 100),
                        done=index,
                        total=max(len(events), 1),
                        label=f"已生成简报 {briefs_completed}/{max(len(events), 1)}",
                    )
                    self._heartbeat_runtime_run(runtime, stage="briefing")
                    self._write_runtime_checkpoint(state)
                except Exception as exc:
                    self._append_log(state, "warning", "delivery", f"简报生成失败：{event.get('title') or event_id} - {exc}", stream="system_runtime", actor=triggered_by)

        delivery_due = self._delivery_mode_due(state)
        delivery_mode = str(plan.get("delivery_mode") or "immediate")
        if due_for_upload and delivery_due:
            runtime["current_cycle"] = "wechat_sync"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "wechat_sync", 5),
                done=0,
                total=max(len(due_for_upload), 1),
                label=f"阶段 {stage_positions.get('wechat_sync', stage_total)}/{stage_total}：开始上传微信草稿箱",
            )
            self._progress_snapshot["cycle"] = "wechat_sync"
            self._heartbeat_runtime_run(runtime, stage="wechat_sync")
            self._write_runtime_checkpoint(state)

            for index, brief in enumerate(due_for_upload, start=1):
                brief_id = str(brief.get("id") or "")
                try:
                    synced = self.sync_brief_wechat_draft(brief_id, triggered_by="scheduler").model_dump()
                    state.update(self._upgrade_state(self._read()))
                    if str(synced.get("stage") or "") != "synced":
                        raise RuntimeError(str(synced.get("last_error") or "上传失败"))
                    synced_completed += 1
                    synced_title = str(synced.get("title") or "").strip()
                    if synced_title:
                        synced_titles.append(synced_title)
                    self._set_runtime_cycle_metric(runtime, "wechat_sync_count", synced_completed)
                    self._set_runtime_cycle_metric(runtime, "publish_count", synced_completed)
                    runtime.setdefault("current_cycle_metrics", {})["synced_titles"] = synced_titles[:5]
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "wechat_sync", index / max(len(due_for_upload), 1) * 100),
                        done=index,
                        total=max(len(due_for_upload), 1),
                        label=f"已上传微信草稿箱 {synced_completed}/{max(len(due_for_upload), 1)}",
                    )
                    self._heartbeat_runtime_run(runtime, stage="wechat_sync")
                    self._write_runtime_checkpoint(state)
                except Exception as exc:
                    error_text = str(exc)
                    latest_state = self._upgrade_state(self._read())
                    latest_brief = self._find_brief(latest_state, brief_id)
                    if bool(latest_state.get("browser", {}).get("wechat", {}).get("is_session_level_error")):
                        runtime["blocked_reason"] = f"微信上传失败：{error_text}"
                        self._append_log(state, "error", "delivery", runtime["blocked_reason"], stream="system_runtime", actor=triggered_by)
                        raise
                    self._append_log(
                        state,
                        "warning",
                        "delivery",
                        f"简报上传失败，继续下一条：{brief.get('title') or brief_id} - {error_text}",
                        stream="system_runtime",
                        actor=triggered_by,
                    )
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "wechat_sync", index / max(len(due_for_upload), 1) * 100),
                        done=index,
                        total=max(len(due_for_upload), 1),
                        label=f"已处理微信上传 {index}/{max(len(due_for_upload), 1)}",
                    )
                    self._heartbeat_runtime_run(runtime, stage="wechat_sync")
                    self._write_runtime_checkpoint(state)

            runtime["current_cycle"] = "wechat_verify"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "wechat_verify", 15),
                done=0,
                total=max(synced_completed, 1),
                label=f"阶段 {stage_positions.get('wechat_verify', stage_total)}/{stage_total}：检查微信草稿箱",
            )
            self._progress_snapshot["cycle"] = "wechat_verify"
            self._heartbeat_runtime_run(runtime, stage="wechat_verify")
            self._write_runtime_checkpoint(state)
            verify_result = self.check_wechat_draft_box()
            verify_completed = 1 if verify_result else 0
            self._set_runtime_cycle_metric(runtime, "wechat_verify_count", verify_completed)
            runtime["last_delivery_batch_at"] = now_iso()
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "wechat_verify", 100),
                done=verify_completed,
                total=max(synced_completed, 1),
                label="微信草稿箱检查完成",
            )
            self._heartbeat_runtime_run(runtime, stage="wechat_verify")
            self._write_runtime_checkpoint(state)
        elif due_for_upload and delivery_mode == "scheduled_batch":
            self._append_log(
                state,
                "info",
                "delivery",
                f"已有 {len(due_for_upload)} 条简报待定时批量上传，等待 {plan.get('delivery_schedule_time') or '固定时间'}。",
                stream="system_runtime",
                actor=triggered_by,
            )
