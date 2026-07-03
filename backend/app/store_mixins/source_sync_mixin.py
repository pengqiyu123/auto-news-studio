from __future__ import annotations

import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from typing import Any

from ..intel.connectors import _collect_with_retry
from ..intel.normalize import normalize_raw_items
from ..intel.pipeline import build_intel_state
from ..models import SourceSyncResponse
from ..store.base import (
    MAX_RAW_ITEMS,
    SLOW_SOURCE_WARNING_SECONDS,
    SOURCE_COLLECTION_STALL_SECONDS,
    UTC,
    freshness_bucket,
    now_iso,
    parse_time,
    schedule_to_minutes,
)


class SourceSyncMixin:
    """Source synchronization: health tracking, intel rebuild, and collection orchestration."""

    def _record_source_attempt(
        self,
        source: dict[str, Any],
        *,
        started_at: datetime,
        completed_at: datetime,
        items: list[dict[str, Any]],
        warning_text: str | None = None,
    ) -> None:
        duration_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
        attempt_stamp = started_at.replace(microsecond=0).isoformat()
        completed_stamp = completed_at.replace(microsecond=0).isoformat()
        count = len(items)
        source["item_count"] = count
        source["last_item_count"] = count
        source["last_attempt_at"] = attempt_stamp
        source["last_duration_ms"] = duration_ms
        previous_avg = source.get("avg_duration_ms")
        if isinstance(previous_avg, int):
            source["avg_duration_ms"] = max(int(round((previous_avg * 0.7) + (duration_ms * 0.3))), 0)
        else:
            source["avg_duration_ms"] = duration_ms
        if warning_text:
            source["last_failure_at"] = completed_stamp
            source["consecutive_failures"] = int(source.get("consecutive_failures", 0) or 0) + 1
            if count:
                source["health_status"] = "warning"
            else:
                source["health_status"] = "error" if int(source.get("consecutive_failures", 0) or 0) >= 2 else "warning"
            source["health_detail"] = warning_text
            source["last_error"] = warning_text
        else:
            source["last_success_at"] = completed_stamp
            source["last_synced_at"] = completed_stamp
            source["consecutive_failures"] = 0
            source["last_error"] = None
            if duration_ms >= SLOW_SOURCE_WARNING_SECONDS * 1000:
                source["health_status"] = "warning"
                source["health_detail"] = f"最近一次成功但耗时较长（{round(duration_ms / 1000, 1)}s），产生 {count} 条素材。"
            else:
                source["health_status"] = "healthy"
                source["health_detail"] = f"最近一次同步产生 {count} 条素材。"

    def _finalize_source_health(self, source: dict[str, Any], now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        if not source.get("enabled"):
            source["health_status"] = "idle"
            source["health_detail"] = "已停用"
            return
        consecutive_failures = int(source.get("consecutive_failures", 0) or 0)
        last_success = parse_time(source.get("last_success_at"))
        last_duration_ms = int(source.get("last_duration_ms", 0) or 0)
        if consecutive_failures >= 2:
            source["health_status"] = "error"
            if not source.get("health_detail"):
                source["health_detail"] = "连续失败 2 次以上。"
            return
        if last_success:
            success_age_hours = max((now - last_success).total_seconds() / 3600, 0.0)
            if success_age_hours > 24:
                source["health_status"] = "error"
                source["health_detail"] = source.get("health_detail") or "最近 24 小时无成功同步。"
                return
            if success_age_hours > 6 or consecutive_failures == 1 or last_duration_ms >= SLOW_SOURCE_WARNING_SECONDS * 1000:
                source["health_status"] = "warning"
                if not source.get("health_detail"):
                    source["health_detail"] = "最近同步偏慢或存在轻微异常。"
                return
            source["health_status"] = "healthy"
            if not source.get("health_detail"):
                source["health_detail"] = f"最近一次同步产生 {int(source.get('last_item_count', 0) or 0)} 条素材。"
            return
        if source.get("last_failure_at"):
            source["health_status"] = "error" if consecutive_failures >= 2 else "warning"
            source["health_detail"] = source.get("health_detail") or "尚未出现成功同步。"

    def _project_normalized_items_from_events(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for event in state.get("intel_events", []):
            normalized.append(
                {
                    "id": f"norm-{event['id']}",
                    "raw_item_ids": list(event.get("discovery_item_ids", [])),
                    "title": event.get("title", ""),
                    "link": event.get("representative_link", ""),
                    "summary": event.get("summary", ""),
                    "published_at": event.get("published_at"),
                    "cluster_id": event.get("id"),
                    "cluster_members": list(event.get("discovery_item_ids", [])),
                    "dedupe_key": str(event.get("id")),
                    "source_names": list(event.get("source_names", [])),
                    "origin_sources": list(event.get("source_keys", [])),
                    "source_weight": round(min(float(event.get("coverage_score", 0) or 0) / 100.0, 1.0), 2),
                    "trend_score": float(event.get("velocity_score", 0) or 0),
                    "final_score": float(event.get("composite_score", 0) or 0),
                    "signals": [str(event.get("alert_reason") or "多平台聚合事件")],
                    "score_breakdown": {
                        "velocity": float(event.get("velocity_score", 0) or 0),
                        "coverage": float(event.get("coverage_score", 0) or 0),
                        "freshness": float(event.get("freshness_score", 0) or 0),
                        "audience_fit": float(event.get("audience_fit_score", 0) or 0),
                    },
                    "collected_at": event.get("latest_collected_at"),
                    "freshness_bucket": freshness_bucket(event.get("latest_collected_at")),
                }
            )
        normalized.sort(key=lambda item: item.get("final_score", 0), reverse=True)
        return normalized

    def _rebuild_intel_for_state(
        self,
        state: dict[str, Any],
        stamp: str | None = None,
        work_scope_override: str | None = None,
    ) -> None:
        work_scope = str(work_scope_override or self._work_scope(state))
        intel = build_intel_state(
            state.get("raw_items", []),
            self._sources_by_key(state),
            previous_discovery_items=state.get("discovery_items", []),
            previous_events=state.get("intel_events", []),
            previous_snapshots=state.get("event_snapshots", []),
            captured_at=stamp or now_iso(),
            entity_watchlist=state.get("settings", {}).get("entity_watchlist", []),
        )
        state["discovery_items"] = intel["discovery_items"]
        if work_scope == "collect_only":
            self._refresh_intel_histories(state, update_event_history=False, update_alert_history=False)
            state["intel_events"] = []
            state["intel_alerts"] = []
            state["event_snapshots"] = []
            state["normalized_items"] = []
            return
        state["event_snapshots"] = intel["event_snapshots"]
        state["intel_events"] = intel["intel_events"]
        if work_scope == "collect_events":
            state["intel_alerts"] = []
            self._refresh_intel_histories(state, update_event_history=True, update_alert_history=False)
        elif work_scope == "collect_events_alerts":
            state["intel_alerts"] = intel["intel_alerts"]
            self._refresh_intel_histories(state, update_event_history=True, update_alert_history=True)
        else:
            state["intel_alerts"] = []
            self._refresh_intel_histories(state, update_event_history=False, update_alert_history=False)
        state["normalized_items"] = self._project_normalized_items_from_events(state)
        runtime = self._runtime(state)
        runtime["last_event_sync_at"] = now_iso()

    def _rebuild_candidates_for_state(
        self,
        state: dict[str, Any],
        work_scope_override: str | None = None,
    ) -> list[dict[str, Any]]:
        # Compatibility shim for old call sites that still expect a rebuilt
        # candidate list after the system was unified onto intel events.
        self._rebuild_intel_for_state(state, work_scope_override=work_scope_override)
        return list(state.get("normalized_items", []))

    def _sync_due_sources(self, state: dict[str, Any], triggered_by: str, minimum_interval_minutes: int | None = None) -> SourceSyncResponse:
        now = datetime.now(UTC)
        runtime = self._runtime(state)
        stage_plan = self._stage_plan(runtime)
        stage_positions = {item["key"]: index + 1 for index, item in enumerate(stage_plan)}
        stage_total = len(stage_plan)
        collect_stage_no = stage_positions.get("collecting", 1)
        cluster_stage_no = stage_positions.get("clustering", min(collect_stage_no + 1, max(stage_total, 1)))
        scoring_stage_no = stage_positions.get("scoring", min(cluster_stage_no + 1, max(stage_total, 1)))
        due_sources: list[dict[str, Any]] = []
        for source in state["sources"]:
            if not source.get("enabled"):
                continue
            interval = schedule_to_minutes(source.get("schedule"))
            if minimum_interval_minutes:
                interval = max(interval or 0, minimum_interval_minutes)
            last_synced = parse_time(source.get("last_synced_at"))
            if not last_synced or not interval or (now - last_synced).total_seconds() >= interval * 60:
                due_sources.append(source)
        if not due_sources:
            self._set_runtime_progress(runtime, percent=100, done=0, total=0, label="本轮没有到期来源")
            runtime["next_collect_at"] = self._calculate_next_collect_at(state, now, minimum_interval_minutes)
            return SourceSyncResponse(
                raw_count=len(state["raw_items"]),
                normalized_count=len(state["normalized_items"]),
                event_count=len(state.get("intel_events", [])),
                synced_at=now_iso(),
                warnings=[],
            )

        existing = [item for item in state["raw_items"] if item["source_key"] not in {source["key"] for source in due_sources}]
        collected: list[dict[str, Any]] = []
        warnings: list[str] = []
        stamp = now_iso()
        total_sources = len(due_sources)
        max_workers = max(1, min(int(state.get("settings", {}).get("max_workers", 8)), 20))
        self._set_runtime_progress(
            runtime,
            percent=self._stage_progress_percent(runtime, "collecting", 5),
            done=0,
            total=total_sources,
            label=f"正在并发采集 {total_sources} 个来源 ({max_workers} 线程)",
        )
        self._heartbeat_runtime_run(runtime, stage="collecting", now=now)
        self._write_runtime_checkpoint(state)

        def _collect_one(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str | None, str | None, datetime, datetime]:
            started_at = datetime.now(UTC)
            try:
                items, warning = _collect_with_retry(source)
                return source, items, warning, None, started_at, datetime.now(UTC)
            except Exception:
                tb = traceback.format_exc()
                return source, [], None, f"{source['name']}: 抓取器异常:\n{tb}", started_at, datetime.now(UTC)

        source_map: dict[str, dict[str, Any]] = {src["key"]: src for src in due_sources}
        completed = 0
        last_progress_at = now
        next_wait_heartbeat_at = time.monotonic() + 5

        def _finalize_source_result(
            source: dict[str, Any],
            *,
            items: list[dict[str, Any]],
            warning: str | None,
            error: str | None,
            started_at: datetime,
            completed_at: datetime,
        ) -> None:
            nonlocal completed
            collected.extend(items)
            if warning:
                warnings.append(f"{source['name']}: {warning}")
            if error:
                warnings.append(error)
                self._append_log(state, "error", "collection", error, stream="system_runtime", actor=triggered_by)
            warning_text = warning or (error.split("\n")[0][:200] if error else None)
            self._record_source_attempt(
                source,
                started_at=started_at,
                completed_at=completed_at,
                items=items,
                warning_text=warning_text,
            )
            duration_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
            self._record_runtime_source_attempt(
                runtime,
                source=source,
                duration_ms=duration_ms,
                status="success" if not warning_text else ("warning" if items else "error"),
                item_count=len(items),
                warning_text=warning_text,
                error_text=error.split("\n")[0][:200] if error else None,
            )
            self._finalize_source_health(source, now=completed_at)
            completed += 1
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "collecting", completed / max(total_sources, 1) * 100),
                done=completed,
                total=total_sources,
                label=f"已采集 {completed}/{total_sources} 个来源",
            )
            self._heartbeat_runtime_run(runtime, stage=f"collecting:{source['key']}", error=warning_text, now=completed_at)
            self._write_runtime_checkpoint(state)

        executor = ThreadPoolExecutor(max_workers=max_workers)
        pending: dict[Any, dict[str, Any]] = {}
        try:
            for src in due_sources:
                future = executor.submit(_collect_one, src)
                pending[future] = {
                    "source_key": src["key"],
                    "submitted_at": datetime.now(UTC),
                }

            while pending:
                done, _ = wait(tuple(pending.keys()), timeout=1, return_when=FIRST_COMPLETED)
                current_time = datetime.now(UTC)
                if done:
                    for future in done:
                        meta = pending.pop(future, None)
                        if not meta:
                            continue
                        src_key = str(meta["source_key"])
                        source = source_map[src_key]
                        try:
                            _src_collected, items, warning, error, started_at, completed_at = future.result()
                        except Exception:
                            items, warning, error = [], None, f"{source['name']}: 未知异常"
                            started_at = current_time
                            completed_at = current_time
                        _finalize_source_result(
                            source,
                            items=items,
                            warning=warning,
                            error=error,
                            started_at=started_at,
                            completed_at=completed_at,
                        )
                    last_progress_at = current_time
                    continue

                if time.monotonic() >= next_wait_heartbeat_at:
                    pending_count = len(pending)
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "collecting", completed / max(total_sources, 1) * 100),
                        done=completed,
                        total=total_sources,
                        label=f"正在等待剩余 {pending_count} 个来源返回",
                    )
                    self._heartbeat_runtime_run(runtime, stage="collecting:waiting", now=current_time)
                    self._write_runtime_checkpoint(state)
                    next_wait_heartbeat_at = time.monotonic() + 5

                stalled_for = (current_time - last_progress_at).total_seconds()
                if stalled_for < SOURCE_COLLECTION_STALL_SECONDS:
                    continue

                stalled_sources = []
                for future, meta in list(pending.items()):
                    src_key = str(meta["source_key"])
                    source = source_map[src_key]
                    pending.pop(future, None)
                    future.cancel()
                    stalled_sources.append(source["name"])
                    timeout_message = (
                        f"{source['name']}: 采集超时，已跳过该来源并继续本轮（连续 {int(stalled_for)}s 无进展）"
                    )
                    _finalize_source_result(
                        source,
                        items=[],
                        warning=None,
                        error=timeout_message,
                        started_at=meta.get("submitted_at") or current_time,
                        completed_at=current_time,
                    )
                if stalled_sources:
                    self._append_log(
                        state,
                        "warning",
                        "runtime",
                        f"采集阶段长时间无进展，已跳过 {len(stalled_sources)} 个来源：{', '.join(stalled_sources)}",
                        stream="system_runtime",
                        actor=triggered_by,
                    )
                last_progress_at = current_time
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        merged = sorted(existing + collected, key=lambda item: parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        state["raw_items"] = merged[:MAX_RAW_ITEMS]
        active_work_scope = str(runtime.get("work_scope") or self._work_scope(state) or "collect_events_alerts")
        self._append_log(
            state,
            "info",
            "runtime",
            f"阶段 {collect_stage_no}/{stage_total} 完成：采集 {len(state['raw_items'])} 条素材",
            stream="system_runtime" if triggered_by == "scheduler" else "business_event",
            actor=triggered_by,
        )
        if active_work_scope == "collect_only":
            candidates = self._rebuild_candidates_for_state(
                state,
                work_scope_override=active_work_scope,
            )
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "collecting", 100),
                done=total_sources,
                total=total_sources,
                label="采集完成，即将完成",
            )
            self._heartbeat_runtime_run(runtime, stage="collecting:complete", now=datetime.now(UTC))
        else:
            self._append_log(
                state,
                "info",
                "runtime",
                f"阶段 {cluster_stage_no}/{stage_total}：开始聚合热点事件...",
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
            runtime["current_cycle"] = "clustering"
            self._progress_snapshot["cycle"] = "clustering"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "clustering", 10),
                done=0,
                total=0,
                label="采集完成，正在聚合热点事件",
            )
            self._heartbeat_runtime_run(runtime, stage="clustering", now=datetime.now(UTC))
            self._write_runtime_checkpoint(state)

            candidates = self._rebuild_candidates_for_state(
                state,
                work_scope_override=active_work_scope,
            )
            self._append_log(
                state,
                "info",
                "runtime",
                f"阶段 {cluster_stage_no}/{stage_total} 完成：形成 {len(state.get('intel_events', []))} 个热点事件",
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "clustering", 100),
                done=0,
                total=0,
                label="热点事件聚合完成",
            )

            stage_three_message = (
                f"阶段 {scoring_stage_no}/{stage_total}：开始整理热点排序..."
                if active_work_scope == "collect_events"
                else f"阶段 {scoring_stage_no}/{stage_total}：开始判断热度与预警..."
            )
            self._append_log(
                state,
                "info",
                "runtime",
                stage_three_message,
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
            runtime["current_cycle"] = "scoring"
            self._progress_snapshot["cycle"] = "scoring"
            scoring_label = "热点事件已聚合，正在整理热点排序" if active_work_scope == "collect_events" else "热点事件已聚合，正在判断热度与预警"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "scoring", 10),
                done=0,
                total=0,
                label=scoring_label,
            )
            self._heartbeat_runtime_run(runtime, stage="scoring", now=datetime.now(UTC))
            self._write_runtime_checkpoint(state)

            stage_three_done = (
                f"阶段 {scoring_stage_no}/{stage_total} 完成：更新 {len(candidates)} 条重点观察"
                if active_work_scope == "collect_events"
                else f"阶段 {scoring_stage_no}/{stage_total} 完成：生成 {len(state.get('intel_alerts', []))} 条预警，更新 {len(candidates)} 条重点观察"
            )
            self._append_log(
                state,
                "info",
                "runtime",
                stage_three_done,
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "scoring", 100),
                done=0,
                total=0,
                label="热度结果已更新，即将完成",
            )
            self._heartbeat_runtime_run(runtime, stage="scoring:complete", now=datetime.now(UTC))
            self._write_runtime_checkpoint(state)
        runtime["last_collect_at"] = stamp
        if collected:
            runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        level = "success"
        message = f"自动同步 {len(due_sources)} 个来源，新增 {len(collected)} 条素材，当前聚合出 {len(state.get('intel_events', []))} 个事件。"
        if not collected and warnings:
            level = "warning"
            message = f"自动同步执行完成，但本轮未获取到任何真实素材；涉及 {len(due_sources)} 个到期来源。"
        elif not collected:
            level = "warning"
            message = f"自动同步执行完成，但本轮没有新增素材；已检查 {len(due_sources)} 个到期来源。"
        self._append_log(
            state,
            level,
            "collection",
            message,
            stream="system_runtime" if triggered_by == "scheduler" else "business_event",
            actor=triggered_by,
        )
        for warning in warnings[:6]:
            self._append_log(state, "warning", "collection", warning, stream="system_runtime" if triggered_by == "scheduler" else "business_event", actor=triggered_by)
        return SourceSyncResponse(
            raw_count=len(state["raw_items"]),
            normalized_count=len(state["normalized_items"]),
            event_count=len(state.get("intel_events", [])),
            synced_at=stamp,
            warnings=warnings,
        )

    def _sync_sources_internal(
        self,
        state: dict[str, Any],
        triggered_by: str,
        work_scope_override: str | None = None,
    ) -> SourceSyncResponse:
        from ..intel.connectors import collect_enabled_sources

        max_workers = state.get("settings", {}).get("max_workers", 8)
        raw_items, warnings = collect_enabled_sources(state["sources"], max_workers=max_workers)
        sources_by_key = self._sources_by_key(state)
        normalized = normalize_raw_items(raw_items, sources_by_key)
        stamp = now_iso()

        for source in state["sources"]:
            warning_text = next((warning for warning in warnings if warning.startswith(f"{source['name']}:")), None)
            now = datetime.now(UTC)
            items_for_source = [item for item in raw_items if item["source_key"] == source["key"]]
            self._record_source_attempt(
                source,
                started_at=now,
                completed_at=now,
                items=items_for_source,
                warning_text=warning_text if source.get("enabled") else None,
            )
            if source.get("enabled"):
                source["last_synced_at"] = stamp
            self._finalize_source_health(source, now=now)

        state["raw_items"] = raw_items
        self._rebuild_candidates_for_state(state, work_scope_override=work_scope_override)
        runtime = self._runtime(state)
        runtime["last_collect_at"] = stamp
        if raw_items:
            runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        level = "success"
        message = f"已同步 {len(raw_items)} 条素材，形成 {len(normalized)} 条标准化素材并聚合出 {len(state.get('intel_events', []))} 个事件。"
        if not raw_items and warnings:
            level = "warning"
            message = "已执行来源同步，但本轮没有获取到任何真实素材。"
        elif not raw_items:
            level = "warning"
            message = "已执行来源同步，但本轮没有新增素材。"
        self._append_log(
            state,
            level,
            "collection",
            message,
            stream="system_runtime" if triggered_by == "scheduler" else "business_event",
            actor=triggered_by,
        )
        for warning in warnings[:6]:
            self._append_log(state, "warning", "collection", warning, stream="system_runtime" if triggered_by == "scheduler" else "business_event", actor=triggered_by)
        return SourceSyncResponse(
            raw_count=len(raw_items),
            normalized_count=len(state["normalized_items"]),
            event_count=len(state.get("intel_events", [])),
            synced_at=stamp,
            warnings=warnings,
        )
