from __future__ import annotations

import time
import traceback
from datetime import datetime
from threading import Thread
from typing import Any

from ..db import database_write_enabled, persist_ingest_chain_state
from ..models import (
    AutomationMode,
    AutomationModeDefinition,
    AutomationModeProfile,
    RuntimeCycleSummary,
    RuntimeIntent,
    RuntimePlan,
    RuntimePlanPayload,
    SchedulerStatus,
)
from ..store.base import DEFAULT_RUNTIME_INTENT, INTENT_TO_WORK_SCOPE, UTC, parse_time


class RuntimeMixin:
    def list_automation_modes(self) -> list[AutomationModeDefinition]:
        state = self._upgrade_state(self._read())
        return [AutomationModeDefinition(**mode) for mode in state["automation_mode_definitions"]]

    def get_current_automation_mode(self) -> AutomationModeDefinition:
        state = self._upgrade_state(self._read())
        return AutomationModeDefinition(**self._current_automation_mode_def(state))

    def list_automation_profiles(self) -> list[AutomationModeProfile]:
        state = self._upgrade_state(self._read())
        return [AutomationModeProfile(**item) for item in state["automation_profiles"]]

    def get_current_automation_profile(self) -> AutomationModeProfile:
        state = self._upgrade_state(self._read())
        return AutomationModeProfile(**self._current_automation_profile(state))

    def update_automation_profile(self, mode: AutomationMode, profile: AutomationModeProfile) -> AutomationModeProfile:
        state = self._upgrade_state(self._read())
        profiles = self._automation_profile_map(state)
        if mode not in profiles:
            raise ValueError(f"Unknown automation mode profile: {mode}")
        payload = profile.model_dump()
        payload["mode"] = mode
        next_profiles: list[dict[str, Any]] = []
        for item in state["automation_profiles"]:
            if item["mode"] == mode:
                next_profiles.append(payload)
            else:
                next_profiles.append(item)
        state["automation_profiles"] = next_profiles
        runtime = self._runtime(state)
        runtime["next_collect_at"] = self._calculate_next_collect_at(
            state,
            minimum_interval_minutes=self._collect_interval_for_profile(state),
        )
        label = self._automation_mode_map(state).get(mode, {}).get("label", mode)
        self._append_log(state, "success", "mode", f"已更新 {label} 的运行参数。", actor="dashboard")
        self._write(state)
        return AutomationModeProfile(**payload)

    def set_current_automation_mode(self, mode: AutomationMode) -> AutomationModeDefinition:
        state = self._upgrade_state(self._read())
        modes = self._automation_mode_map(state)
        if mode not in modes:
            raise ValueError(f"Unknown automation mode: {mode}")
        if not modes[mode].get("available"):
            raise ValueError("该模式当前不可用。")
        state["automation_mode"] = mode
        plan = self._runtime_plan(state)
        if mode == "manual":
            plan["delivery_mode"] = "collect_only"
            plan["admission_strategy"] = "top_scored"
        elif mode == "automated":
            if str(plan.get("delivery_mode") or "") == "collect_only":
                plan["delivery_mode"] = "local_digest"
            plan["admission_strategy"] = "top_scored"
        runtime = self._runtime(state)
        runtime["current_mode"] = mode
        runtime["delivery_mode"] = plan.get("delivery_mode", "collect_only")
        runtime["admission_strategy"] = plan.get("admission_strategy", "top_scored")
        runtime["next_collect_at"] = self._calculate_next_collect_at(
            state,
            minimum_interval_minutes=self._collect_interval_for_profile(state),
        )
        self._append_log(
            state,
            "info",
            "mode",
            f"切换运行模式为 {modes[mode]['label']}",
            stream="business_event",
            actor="dashboard",
        )
        self._write(state)
        return AutomationModeDefinition(**modes[mode])

    def get_runtime_plan(self) -> RuntimePlan:
        state = self._read_live()
        return self._runtime_plan_from_state(state)

    def update_runtime_plan(self, payload: RuntimePlanPayload, actor: str = "dashboard") -> RuntimePlan:
        with self._lock:
            state = self._upgrade_state(self._read())
            plan = self._runtime_plan(state)
            plan.update(payload.model_dump())
            runtime = self._runtime(state)
            runtime["launch_mode"] = plan["launch_mode"]
            runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
            runtime["delivery_mode"] = plan.get("delivery_mode", "collect_only")
            runtime["delivery_schedule_time"] = plan.get("delivery_schedule_time")
            runtime["admission_strategy"] = plan.get("admission_strategy", "top_scored")
            runtime["batch_limit"] = int(plan.get("batch_limit", 3) or 3)
            if runtime.get("control_state") != "running":
                runtime["scheduled_start_at"] = (
                    plan.get("start_at") if plan["launch_mode"] in {"once_at", "interval_at"} else None
                )
            runtime["next_collect_at"] = self._calculate_next_collect_at(state)
            self._append_log(
                state,
                "success",
                "runtime",
                "已更新自动运行计划。",
                stream="business_event",
                actor=actor,
            )
            self._write(state)
            return self._runtime_plan_from_state(state)

    def get_runtime_status(self) -> SchedulerStatus:
        with self._lock:
            state = self._read_live()
            recovered_run_id = self._recover_stale_runtime_run(state, actor="runtime_status")
            if recovered_run_id:
                self._write(state)
            return self._scheduler_status_from_state(state)

    def _scheduler_status_from_state(self, state: dict[str, Any]) -> SchedulerStatus:
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        last_cycle_issue_count, last_cycle_issue_summary = self._last_cycle_issue_snapshot(state, runtime)
        last_cycle_summary = runtime.get("last_cycle_summary") or self._build_last_cycle_summary(state, runtime)
        snapshot = self._progress_snapshot
        now_mono = time.monotonic()
        in_completion_hold = now_mono < self._completion_hold_until
        control_state = str(runtime.get("control_state") or "stopped")
        enabled_at = runtime.get("enabled_at")
        enabled_dt = parse_time(enabled_at)
        uptime_seconds = 0
        if control_state != "stopped" and enabled_dt:
            uptime_seconds = max(int((datetime.now(UTC) - enabled_dt).total_seconds()), 0)
        if in_completion_hold:
            current_cycle = "completed"
            progress_percent = 100
            progress_done = int(snapshot.get("done", 1))
            progress_total = int(snapshot.get("total", 1))
            progress_label = snapshot.get("label") or "本轮已完成"
        else:
            current_cycle = str(snapshot.get("cycle") or runtime.get("current_cycle", "idle"))
            progress_percent = int(snapshot.get("percent", runtime.get("current_cycle_progress_percent", 0)) or 0)
            progress_done = int(snapshot.get("done", runtime.get("current_cycle_progress_done", 0)) or 0)
            progress_total = int(snapshot.get("total", runtime.get("current_cycle_progress_total", 0)) or 0)
            progress_label = snapshot.get("label") or runtime.get("current_cycle_progress_label")
        current_cycle, progress_percent, progress_done, progress_total, progress_label = self._normalize_runtime_status_progress(
            runtime,
            cycle=current_cycle,
            percent=progress_percent,
            done=progress_done,
            total=progress_total,
            label=progress_label,
        )
        stage_key, stage_label, stage_index, stage_total = self._stage_status(runtime, current_cycle)
        return SchedulerStatus(
            running=control_state != "stopped",
            control_state=control_state,
            launch_mode=str(runtime.get("launch_mode") or self._runtime_plan(state).get("launch_mode") or "interval_now"),
            current_mode=state["automation_mode"],
            work_scope=str(runtime.get("work_scope") or self._runtime_plan(state).get("work_scope") or "collect_events_alerts"),
            last_collect_at=runtime.get("last_collect_at"),
            last_event_sync_at=runtime.get("last_event_sync_at"),
            last_brief_at=runtime.get("last_brief_at"),
            next_collect_at=runtime.get("next_collect_at"),
            delivery_mode=str(self._runtime_plan(state).get("delivery_mode") or "collect_only"),
            delivery_schedule_time=self._runtime_plan(state).get("delivery_schedule_time"),
            admission_strategy=str(self._runtime_plan(state).get("admission_strategy") or "top_scored"),
            batch_limit=max(int(self._runtime_plan(state).get("batch_limit", 3) or 3), 1),
            current_cycle=current_cycle,
            current_cycle_progress_percent=progress_percent,
            current_cycle_progress_done=progress_done,
            current_cycle_progress_total=progress_total,
            current_cycle_progress_label=progress_label,
            stage_key=stage_key,
            stage_label=stage_label,
            stage_index=stage_index,
            stage_total=stage_total,
            enabled_at=runtime.get("enabled_at"),
            scheduled_start_at=runtime.get("scheduled_start_at"),
            current_cycle_started_at=runtime.get("current_cycle_started_at"),
            last_cycle_started_at=runtime.get("last_cycle_started_at"),
            last_cycle_finished_at=runtime.get("last_cycle_finished_at"),
            last_cycle_duration_seconds=runtime.get("last_cycle_duration_seconds"),
            uptime_seconds=uptime_seconds,
            completed_cycles_today=int(runtime.get("completed_cycles_today", 0) or 0),
            failed_cycles_today=int(runtime.get("failed_cycles_today", 0) or 0),
            last_error=runtime.get("last_error"),
            blocked_reason=runtime.get("blocked_reason"),
            last_cycle_issue_count=last_cycle_issue_count,
            last_cycle_issue_summary=last_cycle_issue_summary,
            run_id=run.get("run_id"),
            run_status=str(run.get("status") or "idle"),
            run_stage=str(run.get("stage") or "idle"),
            run_started_at=run.get("started_at"),
            run_heartbeat_at=run.get("heartbeat_at"),
            run_finished_at=run.get("finished_at"),
            run_triggered_by=run.get("triggered_by"),
            run_error=run.get("error"),
            recovered_run_id=run.get("recovered_run_id"),
            run_stale=self._runtime_run_is_stale(run),
            run_intent=str(run.get("intent") or DEFAULT_RUNTIME_INTENT),
            last_run_outcome=run.get("last_run_outcome"),
            last_cycle_summary=RuntimeCycleSummary(**last_cycle_summary) if isinstance(last_cycle_summary, dict) else None,
        )

    def set_scheduler_running(self, running: bool) -> None:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            runtime["scheduler_running"] = running
            if not running and runtime.get("control_state") != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                self._reset_runtime_progress(runtime)
                runtime["enabled_at"] = None
                runtime["scheduled_start_at"] = None
                runtime["current_cycle_started_at"] = None
                runtime["next_collect_at"] = None
            self._write(state)

    def reset_runtime_on_boot(
        self,
        actor: str = "system",
        message: str = "服务启动后自动运行保持关闭，需要在驾驶舱手动启动。",
    ) -> SchedulerStatus:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            self._finish_runtime_run(runtime, status="idle", stage="idle", error=None, recovered_run_id=None)
            self._set_runtime_run_intent(runtime, DEFAULT_RUNTIME_INTENT)
            runtime["scheduler_running"] = False
            runtime["control_state"] = "stopped"
            runtime["current_cycle"] = "idle"
            self._reset_runtime_progress(runtime)
            runtime["enabled_at"] = None
            runtime["scheduled_start_at"] = None
            runtime["current_cycle_started_at"] = None
            runtime["next_collect_at"] = None
            runtime["launch_mode"] = self._runtime_plan(state).get("launch_mode", "interval_now")
            runtime["work_scope"] = self._runtime_plan(state).get("work_scope", "collect_events_alerts")
            runtime["active_interval_minutes"] = None
            runtime["last_error"] = None
            self._append_log(
                state,
                "info",
                "runtime",
                message,
                stream="system_runtime",
                actor=actor,
            )
            self._write(state)
            return self._scheduler_status_from_state(state)

    def start_runtime(self, actor: str = "dashboard") -> SchedulerStatus:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            now = datetime.now(UTC)
            self._recover_stale_runtime_run(state, actor=actor, now=now)
            run = self._runtime_run(runtime)
            startup_inflight = (
                str(run.get("status") or "idle") == "running"
                and str(run.get("stage") or "idle") == "starting"
                and str(runtime.get("current_cycle") or "idle") == "starting"
            )
            if (
                str(run.get("status") or "idle") == "running"
                and not self._runtime_run_is_stale(run, now)
                and not startup_inflight
            ):
                return self._scheduler_status_from_state(state)
            plan = self._runtime_plan(state)
            runtime["scheduler_running"] = True
            runtime["current_mode"] = state["automation_mode"]
            runtime["launch_mode"] = plan["launch_mode"]
            runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
            runtime["delivery_mode"] = plan.get("delivery_mode", "collect_only")
            runtime["delivery_schedule_time"] = plan.get("delivery_schedule_time")
            runtime["admission_strategy"] = plan.get("admission_strategy", "top_scored")
            runtime["batch_limit"] = int(plan.get("batch_limit", 3) or 3)
            runtime["last_error"] = None
            runtime["blocked_reason"] = None
            self._set_runtime_run_intent(runtime, DEFAULT_RUNTIME_INTENT)
            runtime["enabled_at"] = now.replace(microsecond=0).isoformat()
            runtime["scheduled_start_at"] = plan.get("start_at") if plan["launch_mode"] in {"once_at", "interval_at"} else None
            runtime["active_interval_minutes"] = plan.get("interval_minutes")
            if plan["launch_mode"] in {"once_at", "interval_at"} and runtime.get("scheduled_start_at"):
                scheduled_dt = parse_time(runtime["scheduled_start_at"])
                if scheduled_dt and scheduled_dt > now:
                    runtime["control_state"] = "armed"
                    runtime["current_cycle"] = "idle"
                    self._reset_runtime_progress(runtime)
                    runtime["next_collect_at"] = runtime["scheduled_start_at"]
                    self._append_log(
                        state,
                        "info",
                        "runtime",
                        "自动运行计划已设定，等待到点启动。",
                        stream="system_runtime",
                        actor=actor,
                    )
                    self._append_log(
                        state,
                        "info",
                        "runtime",
                        "已从前端启用自动运行计划。",
                        stream="business_event",
                        actor=actor,
                    )
                    self._write(state)
                    return self._scheduler_status_from_state(state)
            immediate_launch = plan["launch_mode"] in {"once_now", "interval_now"}
            runtime["control_state"] = "running" if immediate_launch else "waiting"
            runtime["current_cycle"] = "starting" if immediate_launch else "idle"
            if immediate_launch:
                self._set_runtime_progress(runtime, percent=2, done=0, total=0, label="正在启动工作轮次")
                self._progress_snapshot["cycle"] = "starting"
                self._finish_runtime_run(runtime, status="idle", stage="starting", error=None, recovered_run_id=None, now=now)
            else:
                self._reset_runtime_progress(runtime)
                self._finish_runtime_run(runtime, status="idle", stage="idle", error=None, recovered_run_id=None, now=now)
            runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat() if immediate_launch else None
            runtime["next_collect_at"] = (
                now.replace(microsecond=0).isoformat() if immediate_launch else self._calculate_next_collect_at(state)
            )
            self._append_log(
                state,
                "info",
                "runtime",
                "后台自动调度器已启动。",
                stream="system_runtime",
                actor=actor,
            )
            self._append_log(
                state,
                "info",
                "runtime",
                "已从前端恢复自动运行。",
                stream="business_event",
                actor=actor,
            )
            self._write(state)
            if immediate_launch:
                self._launch_runtime_cycle_async(triggered_by="runtime_start", force=True)
                return self._scheduler_status_from_state(state)
            return self._scheduler_status_from_state(self._upgrade_state(self._read()))

    def stop_runtime(self, actor: str = "dashboard") -> SchedulerStatus:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            runtime["scheduler_running"] = False
            if runtime.get("control_state") != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                self._reset_runtime_progress(runtime)
                runtime["current_cycle_started_at"] = None
                runtime["enabled_at"] = None
                self._finish_runtime_run(
                    runtime,
                    status="idle",
                    stage="idle",
                    error=None,
                    recovered_run_id=None,
                    last_run_outcome="stopped",
                )
            runtime["scheduled_start_at"] = None
            runtime["next_collect_at"] = None if runtime.get("control_state") != "running" else runtime.get("next_collect_at")
            self._append_log(
                state,
                "warning",
                "runtime",
                "后台自动调度器已暂停。",
                stream="system_runtime",
                actor=actor,
            )
            self._append_log(
                state,
                "warning",
                "runtime",
                "已从前端暂停自动运行。",
                stream="business_event",
                actor=actor,
            )
            self._write(state)
            return self._scheduler_status_from_state(state)

    def run_runtime_intent(self, intent: RuntimeIntent, actor: str = "dashboard") -> SchedulerStatus:
        work_scope = INTENT_TO_WORK_SCOPE.get(str(intent))
        if not work_scope:
            raise ValueError("未知的维护动作。")

        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            run = self._runtime_run(runtime)
            now = datetime.now(UTC)
            self._recover_stale_runtime_run(state, actor=actor, now=now)
            if str(runtime.get("control_state") or "stopped") != "stopped":
                raise ValueError("监测已启用，请先停止后再执行维护动作。")
            if str(run.get("status") or "idle") == "running" and not self._runtime_run_is_stale(run, now):
                raise ValueError("当前已有运行中的轮次，请稍后再试。")

            runtime["scheduler_running"] = False
            runtime["control_state"] = "running"
            runtime["current_mode"] = state["automation_mode"]
            runtime["launch_mode"] = "once_now"
            runtime["work_scope"] = work_scope
            runtime["delivery_mode"] = self._runtime_plan(state).get("delivery_mode", "collect_only")
            runtime["delivery_schedule_time"] = self._runtime_plan(state).get("delivery_schedule_time")
            runtime["admission_strategy"] = self._runtime_plan(state).get("admission_strategy", "top_scored")
            runtime["batch_limit"] = int(self._runtime_plan(state).get("batch_limit", 3) or 3)
            runtime["last_error"] = None
            runtime["blocked_reason"] = None
            runtime["enabled_at"] = now.replace(microsecond=0).isoformat()
            runtime["scheduled_start_at"] = None
            runtime["active_interval_minutes"] = None
            runtime["current_cycle"] = "starting"
            runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat()
            self._reset_runtime_cycle_context(runtime)
            runtime["next_collect_at"] = None
            self._set_runtime_progress(runtime, percent=2, done=0, total=0, label="正在启动维护任务")
            self._progress_snapshot["cycle"] = "starting"
            self._set_runtime_run_intent(runtime, str(intent))
            self._finish_runtime_run(runtime, status="idle", stage="starting", error=None, recovered_run_id=None, now=now)
            self._append_log(
                state,
                "info",
                "runtime",
                f"已启动维护动作：{intent}",
                stream="business_event",
                actor=actor,
            )
            self._write(state)

        if work_scope == "collect_only":
            try:
                self._run_automation_cycle_locked(state, triggered_by=actor, force=True)
            finally:
                with self._lock:
                    state = self._upgrade_state(self._read())
                    runtime = self._runtime(state)
                    plan = self._runtime_plan(state)
                    runtime["launch_mode"] = plan.get("launch_mode", "interval_now")
                    runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
                    self._write(state)
        else:
            with self._lock:
                state = self._upgrade_state(self._read())
                runtime = self._runtime(state)
                now = datetime.now(UTC)
                runtime["control_state"] = "running"
                runtime["current_cycle"] = "clustering" if work_scope == "collect_events" else "scoring"
                runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat()
                runtime["last_cycle_started_at"] = runtime["current_cycle_started_at"]
                progress_label = "正在重建热点事件" if work_scope == "collect_events" else "正在重算预警"
                progress_cycle = "clustering" if work_scope == "collect_events" else "scoring"
                self._set_runtime_progress(runtime, percent=35, done=0, total=0, label=progress_label)
                self._progress_snapshot["cycle"] = progress_cycle
                self._start_runtime_run(runtime, stage=progress_cycle, triggered_by=actor, intent=str(intent), now=now)
                self._write(state)
            start = datetime.now(UTC)
            try:
                with self._lock:
                    state = self._upgrade_state(self._read())
                    runtime = self._runtime(state)
                    candidates = self._rebuild_candidates_for_state(state, work_scope_override=work_scope)
                    finish = datetime.now(UTC)
                    duration = round((finish - start).total_seconds(), 1)
                    runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
                    runtime["last_cycle_duration_seconds"] = duration
                    runtime["current_cycle_started_at"] = None
                    runtime["completed_cycles_today"] = int(runtime.get("completed_cycles_today", 0) or 0) + 1
                    runtime["control_state"] = "stopped"
                    runtime["current_cycle"] = "idle"
                    runtime["enabled_at"] = None
                    runtime["next_collect_at"] = None
                    self._set_runtime_progress(runtime, percent=100, done=1, total=1, label="本轮已完成")
                    self._finish_runtime_run(
                        runtime,
                        status="completed",
                        stage="done",
                        error=None,
                        last_run_outcome="completed",
                        now=finish,
                    )
                    runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
                    self._append_job(
                        state,
                        "rebuild_candidates",
                        f"已完成维护动作：{intent}，当前 {len(candidates)} 个候选主题。",
                        triggered_by=actor,
                    )
                    self._reset_runtime_progress(runtime)
                    plan = self._runtime_plan(state)
                    runtime["launch_mode"] = plan.get("launch_mode", "interval_now")
                    runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
                    self._write(state)
            except Exception as exc:
                with self._lock:
                    state = self._upgrade_state(self._read())
                    runtime = self._runtime(state)
                    finish = datetime.now(UTC)
                    duration = round((finish - start).total_seconds(), 1)
                    runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
                    runtime["last_cycle_duration_seconds"] = duration
                    runtime["current_cycle_started_at"] = None
                    runtime["failed_cycles_today"] = int(runtime.get("failed_cycles_today", 0) or 0) + 1
                    runtime["last_error"] = str(exc)
                    runtime["control_state"] = "stopped"
                    runtime["current_cycle"] = "failed"
                    self._set_runtime_progress(runtime, percent=100, done=1, total=1, label=f"本轮失败：{exc}")
                    self._progress_snapshot["cycle"] = "failed"
                    self._finish_runtime_run(
                        runtime,
                        status="failed",
                        stage="failed",
                        error=str(exc),
                        last_run_outcome="failed",
                        now=finish,
                    )
                    runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
                    self._append_log(
                        state,
                        "error",
                        "runtime",
                        f"维护动作失败：{intent} - {exc}",
                        stream="system_runtime",
                        actor=actor,
                    )
                    self._append_job(
                        state,
                        "rebuild_candidates",
                        f"维护动作失败：{intent} - {exc}",
                        status="failed",
                        triggered_by=actor,
                    )
                    plan = self._runtime_plan(state)
                    runtime["launch_mode"] = plan.get("launch_mode", "interval_now")
                    runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
                    self._write(state)
                raise

        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            plan = self._runtime_plan(state)
            runtime["launch_mode"] = plan.get("launch_mode", "interval_now")
            runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
            self._write(state)
            return self._scheduler_status_from_state(state)

    def _finalize_cycle(
        self,
        state: dict[str, Any],
        runtime: dict[str, Any],
        *,
        finish: datetime,
        duration: float,
        run_outcome: str,
        error: str | None = None,
        triggered_by: str = "scheduler",
    ) -> None:
        """Shared cleanup after a cycle completes or fails."""
        plan = self._runtime_plan(state)
        runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
        runtime["last_cycle_duration_seconds"] = duration
        runtime["current_cycle_started_at"] = None
        self._finish_runtime_run(
            runtime,
            status=run_outcome,
            stage="done" if run_outcome == "completed" else "failed",
            error=error,
            last_run_outcome=run_outcome,
            now=finish,
        )
        runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
        launch_mode = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")
        if not runtime.get("scheduler_running") or launch_mode in {"once_now", "once_at"}:
            runtime["scheduler_running"] = False
            runtime["control_state"] = "stopped"
            runtime["current_cycle"] = "idle"
            self._reset_runtime_progress(runtime)
            runtime["enabled_at"] = None
            runtime["scheduled_start_at"] = None
            runtime["active_interval_minutes"] = None
            runtime["next_collect_at"] = None
        else:
            runtime["control_state"] = "waiting"
            runtime["current_cycle"] = "idle"
            self._reset_runtime_progress(runtime)
            runtime["next_collect_at"] = self._calculate_runtime_next_collect_at(state, finish)

    def _run_automation_cycle_locked(self, state: dict[str, Any], triggered_by: str, force: bool = False) -> dict[str, Any]:
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        now = datetime.now(UTC)
        recovered_run_id = self._recover_stale_runtime_run(state, actor=triggered_by, now=now)
        run = self._runtime_run(runtime)
        current_cycle = str(runtime.get("current_cycle", "idle"))
        startup_inflight = (
            force
            and str(run.get("status") or "idle") == "running"
            and str(run.get("stage") or "idle") == "starting"
            and current_cycle == "starting"
        )
        if str(run.get("status") or "idle") == "running" and not self._runtime_run_is_stale(run, now) and not startup_inflight:
            with self._lock:
                self._write(state)
            return {"status": "busy", "current_cycle": current_cycle, "run_id": run.get("run_id")}
        if not force and current_cycle not in ("idle", "failed"):
            with self._lock:
                self._write(state)
            return {"status": "busy", "current_cycle": current_cycle}
        plan = self._runtime_plan(state)
        stage_plan = self._stage_plan(runtime)
        stage_positions = {item["key"]: index + 1 for index, item in enumerate(stage_plan)}
        stage_total = len(stage_plan)
        collect_stage_no = stage_positions.get("collecting", 1)
        control_state = str(runtime.get("control_state") or "stopped")

        if not force:
            if not runtime.get("scheduler_running") and control_state != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                self._reset_runtime_progress(runtime)
                runtime["next_collect_at"] = None
                with self._lock:
                    self._write(state)
                return {"status": "stopped"}
            if control_state == "armed":
                scheduled_at = parse_time(runtime.get("scheduled_start_at"))
                if scheduled_at and now < scheduled_at:
                    runtime["next_collect_at"] = runtime.get("scheduled_start_at")
                    with self._lock:
                        self._write(state)
                    return {"status": "armed"}
                runtime["control_state"] = "waiting"
            elif control_state == "stopped":
                runtime["next_collect_at"] = None
                self._reset_runtime_progress(runtime)
                with self._lock:
                    self._write(state)
                return {"status": "stopped"}
            elif control_state == "waiting":
                next_due = parse_time(runtime.get("next_collect_at"))
                if next_due and now < next_due:
                    with self._lock:
                        self._write(state)
                    return {"status": "waiting"}

        runtime["control_state"] = "running"
        runtime["current_mode"] = state["automation_mode"]
        runtime["current_cycle"] = "collecting"
        runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat()
        runtime["last_cycle_started_at"] = runtime["current_cycle_started_at"]
        self._reset_runtime_cycle_context(runtime)
        self._set_runtime_progress(runtime, percent=5, done=0, total=0, label="正在准备采集来源")
        self._progress_snapshot["cycle"] = "collecting"
        self._start_runtime_run(
            runtime,
            stage="collecting",
            triggered_by=triggered_by,
            intent=str(run.get("intent") or DEFAULT_RUNTIME_INTENT),
            now=now,
        )
        if recovered_run_id:
            self._runtime_run(runtime)["recovered_run_id"] = recovered_run_id
        runtime["launch_mode"] = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")
        runtime["last_error"] = None
        runtime["blocked_reason"] = None
        self._sync_runtime_counters(runtime)
        self._append_log(
            state,
            "info",
            "runtime",
            f"轮次启动：launch_mode={runtime['launch_mode']}, work_scope={runtime['work_scope']}, force={force}",
            stream="system_runtime",
            actor=triggered_by,
        )
        with self._lock:
            self._write(state)

        start = datetime.now(UTC)
        try:
            self._append_log(
                state,
                "info",
                "runtime",
                f"阶段 {collect_stage_no}/{stage_total}：开始采集到期来源...",
                stream="system_runtime",
                actor=triggered_by,
            )
            self._heartbeat_runtime_run(runtime, stage="collecting", now=start)
            self._write_runtime_checkpoint(state)
            sync_response = self._sync_due_sources(
                state,
                triggered_by="scheduler",
                minimum_interval_minutes=None,
            )
            self._write_runtime_checkpoint(state)
            if str(state.get("automation_mode") or "manual") == "manual":
                self._append_log(
                    state,
                    "info",
                    "delivery",
                    "手动模式：跳过自动交付，请在对应页面手动触发深挖、生成速递或上传。",
                    stream="system_runtime",
                    actor=triggered_by,
                )
                self._write_runtime_checkpoint(state)
            else:
                self._run_delivery_pipeline(state, runtime, triggered_by=triggered_by)
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)

            finish = datetime.now(UTC)
            duration = round((finish - start).total_seconds(), 1)
            self._append_log(state, "info", "runtime", f"轮次完成，总耗时 {duration}s", stream="system_runtime", actor=triggered_by)
            self._set_runtime_progress(runtime, percent=100, done=1, total=1, label="本轮已完成")
            self._finalize_cycle(state, runtime, finish=finish, duration=duration, run_outcome="completed", triggered_by=triggered_by)
            self._completion_hold_until = time.monotonic() + 5
            runtime["completed_cycles_today"] = int(runtime.get("completed_cycles_today", 0) or 0) + 1
            self._append_job(
                state,
                "collect_news",
                (
                    f"自动轮次完成：素材 {sync_response.raw_count}，事件 {sync_response.event_count}，"
                    f"入选 {int(runtime.get('current_cycle_metrics', {}).get('selected_event_count', 0) or 0)}，"
                    f"深挖 {int(runtime.get('current_cycle_metrics', {}).get('deep_dive_count', 0) or 0)}，"
                    f"简报 {int(runtime.get('current_cycle_metrics', {}).get('brief_count', 0) or 0)}，"
                    f"上传 {int(runtime.get('current_cycle_metrics', {}).get('wechat_sync_count', 0) or 0)}，"
                    f"回查 {int(runtime.get('current_cycle_metrics', {}).get('wechat_verify_count', 0) or 0)}，耗时 {duration}s。"
                ),
                triggered_by="scheduler",
            )
            if database_write_enabled():
                persist_ingest_chain_state(
                    state,
                    source_key=None,
                    triggered_by="scheduler",
                    run_id=str(self._runtime_run(runtime).get("run_id") or ""),
                    started_at=self._runtime_run(runtime).get("started_at"),
                    finished_at=finish,
                    status="completed",
                    warnings=list(sync_response.warnings),
                )
            with self._lock:
                self._write(state)
            return {
                "raw_count": sync_response.raw_count,
                "event_count": sync_response.event_count,
                "selected_event_count": int(runtime.get("current_cycle_metrics", {}).get("selected_event_count", 0) or 0),
                "deep_dive_count": int(runtime.get("current_cycle_metrics", {}).get("deep_dive_count", 0) or 0),
                "brief_count": int(runtime.get("current_cycle_metrics", {}).get("brief_count", 0) or 0),
                "wechat_synced_count": int(runtime.get("current_cycle_metrics", {}).get("wechat_sync_count", 0) or 0),
                "wechat_verify_count": int(runtime.get("current_cycle_metrics", {}).get("wechat_verify_count", 0) or 0),
                "duration": duration,
            }
        except Exception as exc:  # pragma: no cover - scheduler guard
            tb = traceback.format_exc()
            finish = datetime.now(UTC)
            duration = round((finish - start).total_seconds(), 1)
            self._progress_snapshot["label"] = f"本轮失败：{exc}"
            self._progress_snapshot["cycle"] = "failed"
            self._completion_hold_until = 0
            runtime["failed_cycles_today"] = int(runtime.get("failed_cycles_today", 0) or 0) + 1
            runtime["last_error"] = str(exc)
            runtime["current_cycle"] = "failed"
            runtime["current_cycle_progress_label"] = f"本轮失败：{exc}"
            self._finalize_cycle(state, runtime, finish=finish, duration=duration, run_outcome="failed", error=str(exc), triggered_by=triggered_by)
            self._append_job(
                state,
                "collect_news",
                f"自动轮次失败：{exc}",
                status="failed",
                triggered_by="scheduler",
            )
            self._append_log(
                state,
                "error",
                "runtime",
                f"自动轮次失败：{exc}",
                stream="system_runtime",
                actor=triggered_by,
                detail=tb,
            )
            if database_write_enabled():
                persist_ingest_chain_state(
                    state,
                    source_key=None,
                    triggered_by="scheduler",
                    run_id=str(self._runtime_run(runtime).get("run_id") or ""),
                    started_at=self._runtime_run(runtime).get("started_at"),
                    finished_at=finish,
                    status="failed",
                    warnings=[str(exc)],
                )
            with self._lock:
                self._write(state)
            raise

    def run_automation_cycle(self) -> dict[str, Any]:
        with self._lock:
            state = self._upgrade_state(self._read())
        return self._run_automation_cycle_locked(state, triggered_by="scheduler")

    def _launch_runtime_cycle_async(self, triggered_by: str, force: bool = False) -> None:
        def runner() -> None:
            try:
                with self._lock:
                    state = self._upgrade_state(self._read())
                self._run_automation_cycle_locked(state, triggered_by=triggered_by, force=force)
            except Exception as exc:
                tb = traceback.format_exc()
                try:
                    with self._lock:
                        state = self._upgrade_state(self._read())
                        runtime = self._runtime(state)
                        run = self._runtime_run(runtime)
                        finish = datetime.now(UTC)
                        if str(run.get("status") or "idle") == "running":
                            started_at = parse_time(runtime.get("last_cycle_started_at")) or finish
                            runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
                            runtime["last_cycle_duration_seconds"] = round((finish - started_at).total_seconds(), 1)
                            runtime["current_cycle_started_at"] = None
                            runtime["current_cycle"] = "failed"
                            runtime["last_error"] = str(exc)
                            runtime["failed_cycles_today"] = int(runtime.get("failed_cycles_today", 0) or 0) + 1
                            self._finish_runtime_run(
                                runtime,
                                status="failed",
                                stage="failed",
                                error=str(exc),
                                last_run_outcome="failed",
                                now=finish,
                            )
                            runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
                            launch_mode = str(
                                runtime.get("launch_mode")
                                or self._runtime_plan(state).get("launch_mode")
                                or "interval_now"
                            )
                            runtime["scheduler_running"] = (
                                False if launch_mode in {"once_now", "once_at"} else bool(runtime.get("scheduler_running"))
                            )
                            runtime["control_state"] = "stopped" if launch_mode in {"once_now", "once_at"} else "waiting"
                            runtime["current_cycle"] = "idle"
                            self._reset_runtime_progress(runtime)
                            if launch_mode in {"once_now", "once_at"}:
                                runtime["enabled_at"] = None
                                runtime["scheduled_start_at"] = None
                                runtime["active_interval_minutes"] = None
                                runtime["next_collect_at"] = None
                            else:
                                runtime["next_collect_at"] = self._calculate_runtime_next_collect_at(state, finish)
                        self._append_job(
                            state,
                            "collect_news",
                            f"后台线程异常退出：{exc}",
                            status="failed",
                            triggered_by=triggered_by,
                        )
                        self._append_log(
                            state,
                            "error",
                            "runtime",
                            f"后台线程异常退出：{exc}",
                            stream="system_runtime",
                            actor=triggered_by,
                            detail=tb,
                        )
                        self._write(state)
                        self._progress_snapshot["label"] = f"本轮失败：{exc}"
                        self._progress_snapshot["cycle"] = "idle"
                        self._completion_hold_until = 0
                except Exception:
                    pass
                return

        Thread(
            target=runner,
            name=f"studio-{triggered_by}",
            daemon=True,
        ).start()
