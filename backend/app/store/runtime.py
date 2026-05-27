from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
import re
from typing import Any
from uuid import uuid4

from ..models import RuntimeCycleSummary, RuntimeIssueItem, RuntimePlan, RuntimeSlowSource
from .base import (
    DEFAULT_RUNTIME_INTENT,
    INTENT_STAGE_PLANS,
    MODE_STAGE_PLANS,
    RUN_STALE_SECONDS,
    UTC,
    local_now,
    now_iso,
    parse_clock_time,
    parse_time,
    schedule_to_minutes,
)
from .defaults import DEFAULT_AUTOMATION_PROFILES


class StoreCoreRuntimeMixin:
    def _automation_mode_map(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {item["key"]: item for item in state["automation_mode_definitions"]}

    def _current_automation_mode_def(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._automation_mode_map(state)[state["automation_mode"]]

    def _automation_profile_map(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {item["mode"]: item for item in state.get("automation_profiles", [])}

    def _current_automation_profile(self, state: dict[str, Any]) -> dict[str, Any]:
        profile = self._automation_profile_map(state).get(state["automation_mode"])
        if profile:
            return profile
        return next(item for item in DEFAULT_AUTOMATION_PROFILES if item["mode"] == state["automation_mode"])

    def _default_runtime_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        profile = self._current_automation_profile(state)
        interval = profile.get("collect_interval_minutes")
        try:
            interval_minutes = max(int(interval), 5)
        except (TypeError, ValueError):
            interval_minutes = 30
        return {
            "launch_mode": "interval_now",
            "start_at": None,
            "interval_minutes": interval_minutes,
            "timezone": "Asia/Shanghai",
            "work_scope": "collect_events_alerts",
            "delivery_mode": "collect_only" if state.get("automation_mode") == "manual" else "local_digest",
            "delivery_schedule_time": None,
            "admission_strategy": "top_scored",
            "batch_limit": int(profile.get("brief_limit", 5) or 5),
            "admission_filters": {
                "require_watchlisted": False,
                "require_entity_match": False,
                "min_source_count": 0,
                "min_fulltext_count": 1,
                "breakout_only": False,
                "exclude_existing_brief": True,
                "exclude_synced_brief": True,
            },
        }

    def _runtime_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        runtime_plan = state.setdefault("runtime_plan", {})
        defaults = self._default_runtime_plan(state)
        for key, value in defaults.items():
            runtime_plan.setdefault(key, value)
        runtime_plan["timezone"] = str(runtime_plan.get("timezone") or "Asia/Shanghai")
        runtime_plan["launch_mode"] = str(runtime_plan.get("launch_mode") or "interval_now")
        valid_delivery_modes = {"collect_only", "local_digest", "immediate", "scheduled_batch"}
        delivery_mode = str(runtime_plan.get("delivery_mode") or "")
        runtime_plan["delivery_mode"] = delivery_mode if delivery_mode in valid_delivery_modes else defaults["delivery_mode"]
        valid_admission_strategies = {"top_scored", "conservative", "balanced", "aggressive"}
        admission_strategy = str(runtime_plan.get("admission_strategy") or "")
        runtime_plan["admission_strategy"] = (
            admission_strategy if admission_strategy in valid_admission_strategies else defaults["admission_strategy"]
        )
        try:
            runtime_plan["batch_limit"] = max(int(runtime_plan.get("batch_limit") or defaults["batch_limit"]), 1)
        except (TypeError, ValueError):
            runtime_plan["batch_limit"] = defaults["batch_limit"]
        filters = runtime_plan.get("admission_filters")
        if not isinstance(filters, dict):
            filters = {}
        runtime_plan["admission_filters"] = {
            **deepcopy(defaults["admission_filters"]),
            **filters,
        }
        # Normal monitoring always runs the full intel chain; intermediate scopes
        # are kept only as transient maintenance actions, not as saved user plans.
        runtime_plan["work_scope"] = "collect_events_alerts"
        launch_mode = runtime_plan["launch_mode"]
        if launch_mode in {"once_now", "interval_now"}:
            runtime_plan["start_at"] = None
        if launch_mode in {"once_now", "once_at"}:
            runtime_plan["interval_minutes"] = None
        else:
            try:
                runtime_plan["interval_minutes"] = max(int(runtime_plan.get("interval_minutes") or defaults["interval_minutes"]), 5)
            except (TypeError, ValueError):
                runtime_plan["interval_minutes"] = defaults["interval_minutes"]
        if runtime_plan["delivery_mode"] != "scheduled_batch":
            runtime_plan["delivery_schedule_time"] = None
        else:
            schedule_value = str(runtime_plan.get("delivery_schedule_time") or "").strip()
            runtime_plan["delivery_schedule_time"] = schedule_value if parse_clock_time(schedule_value) else "09:00"
        return runtime_plan

    def _runtime_plan_from_state(self, state: dict[str, Any]) -> RuntimePlan:
        plan = self._runtime_plan(state)
        return RuntimePlan(
            launch_mode=str(plan.get("launch_mode") or "interval_now"),
            start_at=plan.get("start_at"),
            interval_minutes=plan.get("interval_minutes"),
            timezone=str(plan.get("timezone") or "Asia/Shanghai"),
            effective_mode=state.get("automation_mode", "manual"),
            work_scope=str(plan.get("work_scope") or "collect_events_alerts"),
            delivery_mode=str(plan.get("delivery_mode") or "collect_only"),
            delivery_schedule_time=plan.get("delivery_schedule_time"),
            admission_strategy=str(plan.get("admission_strategy") or "top_scored"),
            batch_limit=max(int(plan.get("batch_limit", 3) or 3), 1),
            admission_filters=deepcopy(plan.get("admission_filters", {})),
        )

    def _sync_runtime_counters(self, runtime: dict[str, Any]) -> None:
        today = local_now().date().isoformat()
        if runtime.get("counters_date") != today:
            runtime["counters_date"] = today
            runtime["completed_cycles_today"] = 0
            runtime["failed_cycles_today"] = 0

    def _calculate_runtime_next_collect_at(self, state: dict[str, Any], now: datetime | None = None) -> str | None:
        now = now or datetime.now(UTC)
        runtime = self._runtime(state)
        plan = self._runtime_plan(state)
        control_state = str(runtime.get("control_state") or "stopped")
        launch_mode = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")

        if control_state == "stopped":
            return None
        if control_state == "armed":
            return runtime.get("scheduled_start_at") or plan.get("start_at")
        if launch_mode in {"once_now", "once_at"}:
            return None

        interval_minutes = runtime.get("active_interval_minutes")
        try:
            interval_minutes = max(int(interval_minutes or plan.get("interval_minutes") or 30), 5)
        except (TypeError, ValueError):
            interval_minutes = 30
        base = (
            parse_time(runtime.get("last_cycle_started_at"))
            or parse_time(runtime.get("enabled_at"))
            or now
        )
        next_at = base + timedelta(minutes=interval_minutes)
        if next_at < now and control_state != "running":
            next_at = now
        return next_at.replace(microsecond=0).isoformat()

    def _is_slot_due(self, last_run_at: str | None, slot_time: str | None, now: datetime | None = None) -> bool:
        clock = parse_clock_time(slot_time)
        if not clock:
            return False
        now = now or datetime.now(UTC)
        slot_dt = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if now < slot_dt:
            return False
        last_run = parse_time(last_run_at)
        if not last_run:
            return True
        return last_run < slot_dt

    def _collect_interval_for_profile(self, state: dict[str, Any]) -> int | None:
        profile = self._current_automation_profile(state)
        value = profile.get("collect_interval_minutes")
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            return None
        return max(minutes, 5)

    def _runtime(self, state: dict[str, Any]) -> dict[str, Any]:
        runtime = state.setdefault("runtime", {})
        self._sync_runtime_counters(runtime)
        return runtime

    def _runtime_run(self, runtime: dict[str, Any]) -> dict[str, Any]:
        return runtime.setdefault(
            "automation_run",
            {
                "run_id": None,
                "status": "idle",
                "stage": "idle",
                "started_at": None,
                "heartbeat_at": None,
                "finished_at": None,
                "triggered_by": None,
                "error": None,
                "recovered_run_id": None,
                "intent": DEFAULT_RUNTIME_INTENT,
                "last_run_outcome": None,
            },
        )

    def _runtime_run_is_stale(self, run: dict[str, Any], now: datetime | None = None) -> bool:
        if str(run.get("status") or "idle") != "running":
            return False
        now = now or datetime.now(UTC)
        heartbeat = parse_time(run.get("heartbeat_at")) or parse_time(run.get("started_at"))
        if not heartbeat:
            return False
        return (now - heartbeat).total_seconds() > RUN_STALE_SECONDS

    def _set_runtime_run_intent(self, runtime: dict[str, Any], intent: str | None) -> dict[str, Any]:
        run = self._runtime_run(runtime)
        run["intent"] = str(intent or run.get("intent") or DEFAULT_RUNTIME_INTENT)
        return run

    def _start_runtime_run(
        self,
        runtime: dict[str, Any],
        *,
        stage: str,
        triggered_by: str,
        intent: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        stamp = now.replace(microsecond=0).isoformat()
        run = self._runtime_run(runtime)
        run.update(
            {
                "run_id": f"run-{uuid4().hex[:12]}",
                "status": "running",
                "stage": stage,
                "started_at": stamp,
                "heartbeat_at": stamp,
                "finished_at": None,
                "triggered_by": triggered_by,
                "error": None,
                "recovered_run_id": None,
                "intent": str(intent or run.get("intent") or DEFAULT_RUNTIME_INTENT),
            }
        )
        return run

    def _heartbeat_runtime_run(
        self,
        runtime: dict[str, Any],
        *,
        stage: str | None = None,
        error: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        stamp = now.replace(microsecond=0).isoformat()
        run = self._runtime_run(runtime)
        if stage:
            run["stage"] = stage
        run["heartbeat_at"] = stamp
        if error is not None:
            run["error"] = error
        return run

    def _finish_runtime_run(
        self,
        runtime: dict[str, Any],
        *,
        status: str,
        stage: str,
        error: str | None = None,
        recovered_run_id: str | None = None,
        last_run_outcome: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        stamp = now.replace(microsecond=0).isoformat()
        run = self._runtime_run(runtime)
        run["status"] = status
        run["stage"] = stage
        run["heartbeat_at"] = stamp
        run["finished_at"] = stamp
        run["error"] = error
        run["recovered_run_id"] = recovered_run_id
        if last_run_outcome is not None:
            run["last_run_outcome"] = last_run_outcome
        return run

    def _recover_stale_runtime_run(self, state: dict[str, Any], actor: str, now: datetime | None = None) -> str | None:
        now = now or datetime.now(UTC)
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        if not self._runtime_run_is_stale(run, now):
            return None
        recovered_run_id = str(run.get("run_id") or "").strip() or None
        self._finish_runtime_run(
            runtime,
            status="abandoned",
            stage="abandoned",
            error=f"超过 {RUN_STALE_SECONDS}s 未更新心跳，已标记为异常轮次。",
            recovered_run_id=recovered_run_id,
            last_run_outcome="abandoned",
            now=now,
        )
        runtime["last_error"] = str(run.get("error") or f"轮次 {recovered_run_id or 'unknown'} 超时未完成，已标记异常。")
        runtime["current_cycle"] = "failed"
        runtime["current_cycle_progress_label"] = runtime["last_error"]
        runtime["scheduler_running"] = False
        runtime["control_state"] = "stopped"
        runtime["current_cycle_started_at"] = None
        runtime["enabled_at"] = None
        runtime["scheduled_start_at"] = None
        runtime["active_interval_minutes"] = None
        runtime["next_collect_at"] = None
        self._progress_snapshot["cycle"] = "failed"
        self._progress_snapshot["label"] = runtime["last_error"]
        self._append_log(
            state,
            "warning",
            "runtime",
            f"检测到异常轮次并已接管：{recovered_run_id or 'unknown'}",
            stream="system_runtime",
            actor=actor,
            detail=f"{runtime['last_error']}\n已自动停止监测，请人工确认后再重新启动。",
        )
        return recovered_run_id

    def _calculate_next_collect_at(self, state: dict[str, Any], now: datetime | None = None, minimum_interval_minutes: int | None = None) -> str | None:
        runtime = self._runtime(state)
        if runtime.get("control_state", "stopped") == "stopped":
            return None
        if runtime.get("control_state", "stopped") != "stopped":
            return self._calculate_runtime_next_collect_at(state, now)
        now = now or datetime.now(UTC)
        due_times: list[datetime] = []
        for source in state["sources"]:
            if not source.get("enabled"):
                continue
            interval = schedule_to_minutes(source.get("schedule"))
            if minimum_interval_minutes:
                interval = max(interval or 0, minimum_interval_minutes)
            if not interval:
                continue
            last_synced = parse_time(source.get("last_synced_at"))
            if not last_synced:
                due_times.append(now)
            else:
                due_times.append(last_synced + timedelta(minutes=interval))
        if not due_times:
            return None
        return min(due_times).replace(microsecond=0).isoformat()

    def _last_cycle_issue_snapshot(self, state: dict[str, Any], runtime: dict[str, Any]) -> tuple[int, str | None]:
        summary = runtime.get("last_cycle_summary")
        if isinstance(summary, dict):
            issues = summary.get("issues", [])
            if isinstance(issues, list):
                count = len(issues)
                if count == 0:
                    return 0, "本轮无异常"
                preview = "；".join(
                    str(item.get("message") or "").strip()
                    for item in issues[:2]
                    if isinstance(item, dict) and str(item.get("message") or "").strip()
                )
                if preview:
                    return count, f"本轮 {count} 条异常。{preview}"
                return count, f"本轮 {count} 条异常。"
        started_at = parse_time(runtime.get("last_cycle_started_at"))
        finished_at = parse_time(runtime.get("last_cycle_finished_at"))
        if not started_at or not finished_at or finished_at < started_at:
            return 0, None

        issues: list[dict[str, Any]] = []
        for item in state.get("logs", []):
            level = str(item.get("level") or "")
            if level not in {"warning", "error"}:
                continue
            created_at = parse_time(item.get("created_at"))
            if not created_at or created_at < started_at or created_at > finished_at:
                continue
            issues.append(item)

        count = len(issues)
        if count == 0:
            return 0, "本轮无异常"

        messages = [str(item.get("message") or "").strip() for item in issues if str(item.get("message") or "").strip()]
        unique_messages: list[str] = []
        for message in messages:
            if message not in unique_messages:
                unique_messages.append(message)

        if count == 1 and unique_messages:
            return 1, unique_messages[0]

        collection_count = len([item for item in issues if str(item.get("category") or "") == "collection"])
        runtime_count = len([item for item in issues if str(item.get("category") or "") == "runtime"])
        preview = "；".join(unique_messages[:2]) if unique_messages else "详情见日志"

        if collection_count == count:
            return count, f"本轮 {count} 条来源异常。{preview}"
        if runtime_count == count:
            return count, f"本轮 {count} 条运行异常。{preview}"
        return count, f"本轮 {count} 条异常。{preview}"

    def _reset_runtime_cycle_context(self, runtime: dict[str, Any]) -> None:
        runtime["current_cycle_sources"] = []
        runtime["current_cycle_metrics"] = {
            "selected_event_count": 0,
            "deep_dive_count": 0,
            "brief_count": 0,
            "wechat_sync_count": 0,
            "wechat_verify_count": 0,
            "publish_count": 0,
            "selected_titles": [],
            "brief_titles": [],
            "synced_titles": [],
        }
        runtime["blocked_reason"] = None

    def _record_runtime_source_attempt(
        self,
        runtime: dict[str, Any],
        *,
        source: dict[str, Any],
        duration_ms: int,
        status: str,
        item_count: int,
        warning_text: str | None = None,
        error_text: str | None = None,
    ) -> None:
        attempts = runtime.setdefault("current_cycle_sources", [])
        attempts.append(
            {
                "source_key": str(source.get("key") or ""),
                "source_name": str(source.get("name") or source.get("key") or "unknown"),
                "duration_ms": max(int(duration_ms), 0),
                "status": status,
                "item_count": max(int(item_count), 0),
                "warning_text": warning_text,
                "error_text": error_text,
            }
        )

    def _set_runtime_cycle_metric(self, runtime: dict[str, Any], key: str, value: int) -> None:
        metrics = runtime.setdefault("current_cycle_metrics", {})
        metrics[key] = max(int(value), 0)

    def _build_last_cycle_summary(self, state: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any] | None:
        started_at = runtime.get("last_cycle_started_at")
        finished_at = runtime.get("last_cycle_finished_at")
        if not started_at or not finished_at:
            return None
        attempts = [
            item for item in runtime.get("current_cycle_sources", [])
            if isinstance(item, dict)
        ]
        success_source_count = len([item for item in attempts if str(item.get("status") or "") == "success"])
        failed_source_count = len([item for item in attempts if str(item.get("status") or "") != "success"])
        slow_sources = sorted(
            attempts,
            key=lambda item: int(item.get("duration_ms", 0) or 0),
            reverse=True,
        )[:3]
        issues: list[dict[str, Any]] = []
        for item in attempts:
            status = str(item.get("status") or "success")
            if status == "success":
                continue
            issues.append(
                {
                    "source_key": item.get("source_key"),
                    "source_name": item.get("source_name"),
                    "error_kind": "warning" if status == "warning" else "collection",
                    "message": str(item.get("warning_text") or item.get("error_text") or "来源执行异常").strip(),
                }
            )
        run = self._runtime_run(runtime)
        run_error = str(run.get("error") or runtime.get("last_error") or "").strip()
        if run_error and not any(issue.get("message") == run_error for issue in issues):
            issues.append(
                {
                    "source_key": None,
                    "source_name": None,
                    "error_kind": "runtime",
                    "message": run_error,
                }
            )
        event_state_counts = Counter(str(item.get("change_state") or "new_event") for item in state.get("intel_events", []))
        item_state_counts = Counter(str(item.get("item_state") or "new_item") for item in state.get("discovery_items", []))
        metrics = runtime.get("current_cycle_metrics", {})
        duration_seconds = float(runtime.get("last_cycle_duration_seconds", 0) or 0)
        summary = RuntimeCycleSummary(
            run_id=run.get("run_id"),
            mode_key=str(runtime.get("current_mode") or state.get("automation_mode") or "manual"),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(int(round(duration_seconds * 1000)), 0),
            success_source_count=success_source_count,
            failed_source_count=failed_source_count,
            new_items_count=int(item_state_counts.get("new_item", 0)),
            new_events_count=int(event_state_counts.get("new_event", 0)),
            growing_events_count=int(event_state_counts.get("growing_event", 0)),
            slow_sources=[
                RuntimeSlowSource(
                    source_key=str(item.get("source_key") or ""),
                    source_name=str(item.get("source_name") or "unknown"),
                    duration_ms=max(int(item.get("duration_ms", 0) or 0), 0),
                    status=str(item.get("status") or "success"),
                )
                for item in slow_sources
            ],
            issues=[
                RuntimeIssueItem(
                    source_key=item.get("source_key"),
                    source_name=item.get("source_name"),
                    error_kind=str(item.get("error_kind") or "runtime"),
                    message=str(item.get("message") or "").strip(),
                )
                for item in issues
                if str(item.get("message") or "").strip()
            ],
            selected_event_count=int(metrics.get("selected_event_count", 0) or 0),
            deep_dive_count=int(metrics.get("deep_dive_count", 0) or 0),
            brief_count=int(metrics.get("brief_count", 0) or 0),
            wechat_sync_count=int(metrics.get("wechat_sync_count", 0) or 0),
            wechat_verify_count=int(metrics.get("wechat_verify_count", 0) or 0),
            publish_count=int(metrics.get("publish_count", 0) or 0),
            blocked_reason=str(runtime.get("blocked_reason") or "").strip() or None,
            recent_selected_titles=[str(item).strip() for item in metrics.get("selected_titles", []) if str(item).strip()][:5],
            recent_brief_titles=[str(item).strip() for item in metrics.get("brief_titles", []) if str(item).strip()][:5],
            recent_synced_titles=[str(item).strip() for item in metrics.get("synced_titles", []) if str(item).strip()][:5],
        )
        return summary.model_dump()

    def _project_cycle_summary_text(self, summary: dict[str, Any] | None) -> str | None:
        if not isinstance(summary, dict):
            return None
        issues = [item for item in summary.get("issues", []) if isinstance(item, dict)]
        if not issues:
            return "本轮无异常"
        preview = "；".join(
            str(item.get("message") or "").strip()
            for item in issues[:2]
            if str(item.get("message") or "").strip()
        )
        if preview:
            return f"本轮 {len(issues)} 条异常。{preview}"
        return f"本轮 {len(issues)} 条异常。"

    def _stage_plan(self, runtime: dict[str, Any]) -> list[dict[str, str]]:
        intent = str(self._runtime_run(runtime).get("intent") or DEFAULT_RUNTIME_INTENT)
        if intent != "normal_monitoring":
            return deepcopy(INTENT_STAGE_PLANS.get(intent, [{"key": "collecting", "label": "执行维护任务"}]))
        mode_key = str(runtime.get("current_mode") or "manual")
        return deepcopy(MODE_STAGE_PLANS.get(mode_key, MODE_STAGE_PLANS["manual"]))

    def _stage_display_key(self, runtime: dict[str, Any], cycle: str) -> str:
        intent = str(self._runtime_run(runtime).get("intent") or DEFAULT_RUNTIME_INTENT)
        if cycle in {"starting", "idle"}:
            plan = self._stage_plan(runtime)
            return plan[0]["key"] if plan else "idle"
        if cycle == "wechat_sync" and intent == "normal_monitoring" and str(runtime.get("delivery_mode") or "") == "local_digest":
            return "briefing"
        if cycle.startswith("collecting"):
            return "collecting"
        if cycle.startswith("clustering"):
            return "clustering"
        if cycle.startswith("scoring"):
            return "scoring"
        return cycle

    def _stage_status(self, runtime: dict[str, Any], cycle: str | None = None) -> tuple[str, str, int, int]:
        plan = self._stage_plan(runtime)
        total = len(plan)
        if not plan:
            return "idle", "空闲", 0, 0
        cycle_key = self._stage_display_key(runtime, str(cycle or runtime.get("current_cycle") or "idle"))
        if str(self._runtime_run(runtime).get("status") or "idle") == "completed":
            last = plan[-1]
            return last["key"], last["label"], total, total
        for index, item in enumerate(plan, start=1):
            if item["key"] == cycle_key:
                return item["key"], item["label"], index, total
        first = plan[0]
        return first["key"], first["label"], 1, total

    def _stage_progress_percent(self, runtime: dict[str, Any], stage_key: str, stage_progress: float) -> int:
        plan = self._stage_plan(runtime)
        if not plan:
            return max(0, min(int(round(stage_progress)), 100))
        total = max(len(plan), 1)
        stage_index = next((index for index, item in enumerate(plan, start=1) if item["key"] == stage_key), 1)
        bounded = max(0.0, min(float(stage_progress), 100.0))
        span_start = 4.0 + ((stage_index - 1) / total) * 96.0
        span_end = 4.0 + (stage_index / total) * 96.0
        percent = span_start + (span_end - span_start) * (bounded / 100.0)
        if stage_index == total and bounded >= 100.0:
            return 100
        return max(0, min(int(round(percent)), 99))

    def _normalize_runtime_status_progress(
        self,
        runtime: dict[str, Any],
        *,
        cycle: str,
        percent: int,
        done: int,
        total: int,
        label: str | None,
    ) -> tuple[str, int, int, int, str | None]:
        run = self._runtime_run(runtime)
        run_status = str(run.get("status") or "idle")
        run_stage = str(run.get("stage") or "")
        if run_status != "running":
            return cycle, percent, done, total, label

        derived_cycle = self._stage_display_key(runtime, run_stage or cycle)
        if cycle in {"", "idle", "starting"} and derived_cycle not in {"", "idle"}:
            cycle = derived_cycle

        if label:
            collected_match = re.search(r"已采集\s*(\d+)\s*/\s*(\d+)\s*个来源", label)
            if collected_match:
                done = max(done, int(collected_match.group(1)))
                total = max(total, int(collected_match.group(2)))
                if percent <= 0:
                    percent = self._stage_progress_percent(
                        runtime,
                        "collecting",
                        done / max(total, 1) * 100,
                    )
            elif percent <= 0:
                pending_match = re.search(r"正在并发采集\s*(\d+)\s*个来源", label)
                if pending_match:
                    total = max(total, int(pending_match.group(1)))
                    percent = self._stage_progress_percent(runtime, "collecting", 5)

        if percent <= 0:
            stage_baselines = {
                "collecting": 5,
                "clustering": self._stage_progress_percent(runtime, "clustering", 10),
                "scoring": self._stage_progress_percent(runtime, "scoring", 10),
                "drafting": self._stage_progress_percent(runtime, "drafting", 10),
                "wechat_sync": self._stage_progress_percent(runtime, "wechat_sync", 10),
            }
            percent = stage_baselines.get(cycle, percent)

        return cycle, percent, done, total, label

    def _work_scope(self, state: dict[str, Any]) -> str:
        return str(self._runtime_plan(state).get("work_scope") or "collect_events_alerts")

    def _set_runtime_progress(
        self,
        runtime: dict[str, Any],
        *,
        percent: int,
        done: int = 0,
        total: int = 0,
        label: str | None = None,
    ) -> None:
        runtime["current_cycle_progress_percent"] = max(0, min(int(percent), 100))
        runtime["current_cycle_progress_done"] = max(int(done), 0)
        runtime["current_cycle_progress_total"] = max(int(total), 0)
        runtime["current_cycle_progress_label"] = label
        snapshot = self._progress_snapshot
        snapshot["percent"] = runtime["current_cycle_progress_percent"]
        snapshot["done"] = runtime["current_cycle_progress_done"]
        snapshot["total"] = runtime["current_cycle_progress_total"]
        snapshot["label"] = label

    def _reset_runtime_progress(self, runtime: dict[str, Any]) -> None:
        self._set_runtime_progress(runtime, percent=0, done=0, total=0, label=None)
        self._progress_snapshot["cycle"] = "idle"

    def _write_runtime_checkpoint(self, state: dict[str, Any], timeout_seconds: float = 0.5) -> bool:
        acquired = self._lock.acquire(timeout=timeout_seconds)
        if not acquired:
            return False
        try:
            self._write(state)
            return True
        finally:
            self._lock.release()
