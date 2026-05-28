from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from typing import Any

from ..db import current_database_url, database_read_is_truth, database_write_enabled, persist_ingest_chain_state
from ..db.read_models import (
    get_intel_summary_from_db,
    list_discovery_items_from_db,
    list_intel_alert_history_from_db,
    list_intel_alerts_from_db,
    list_intel_event_history_from_db,
    list_intel_events_from_db,
)
from ..intel.connectors import collect_from_source
from ..intel.entity_extractor import entity_id_for_name, entity_type_for_name
from ..models import (
    AutomationModeDefinition,
    AutomationModeProfile,
    BrowserSessionState,
    DashboardResponse,
    DashboardStats,
    DiscoveryItem,
    EntityWatchlistItem,
    EntityWatchlistSummaryItem,
    IntelAlert,
    IntelEvent,
    IntelOverviewSummary,
    IntelSnapshot,
    LogItem,
    PublishBackendStatus,
    RuntimeCycleSummary,
    SourceConnector,
    SourceConnectorPayload,
    CreateSourcePayload,
    SourceSyncResponse,
)
from ..store.base import MAX_RAW_ITEMS, UTC, deepcopy_json, now_iso, parse_time


def _stream_options(items: list[DiscoveryItem]) -> tuple[list[str], list[str]]:
    platforms = sorted({item.platform for item in items if item.platform}, key=lambda value: value.lower())
    sources = sorted({item.source_name for item in items if item.source_name}, key=lambda value: value.lower())
    return platforms, sources


def _filter_stream_items(
    items: list[DiscoveryItem],
    *,
    q: str | None = None,
    time_range: str | None = None,
    platform: str | None = None,
    source: str | None = None,
    item_state: str | None = None,
    min_engagement: int | None = None,
    max_engagement: int | None = None,
) -> list[DiscoveryItem]:
    filtered = items
    query = (q or "").strip().lower()
    if query:
        filtered = [
            item
            for item in filtered
            if query in (item.title or "").lower()
            or query in (item.summary or "").lower()
            or query in (item.source_name or "").lower()
            or query in (item.platform or "").lower()
        ]

    if time_range and time_range != "all":
        hours = {"1h": 1, "6h": 6, "24h": 24, "72h": 72}.get(time_range, 0)
        if hours:
            cutoff = datetime.now(UTC) - timedelta(hours=hours)
            filtered = [item for item in filtered if (parse_time(item.collected_at) or datetime.min.replace(tzinfo=UTC)) >= cutoff]

    if platform:
        filtered = [item for item in filtered if item.platform == platform]
    if source:
        filtered = [item for item in filtered if item.source_name == source]
    if item_state:
        filtered = [item for item in filtered if item.item_state == item_state]
    if min_engagement is not None:
        filtered = [item for item in filtered if (item.engagement_score or 0) >= min_engagement]
    if max_engagement is not None:
        filtered = [item for item in filtered if (item.engagement_score or 0) <= max_engagement]
    return filtered


class IntelMixin:
    def _shadow_signature(self, payload: Any) -> str:
        return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _log_shadow_diff(self, message: str, *, detail: str) -> None:
        state = self._upgrade_state(self._read())
        self._append_log(
            state,
            "warning",
            "postgres",
            message,
            stream="system_runtime",
            actor="shadow_read",
            detail=detail,
        )
        self._write(state)

    def list_sources(self) -> list[SourceConnector]:
        state = self._upgrade_state(self._read())
        return [SourceConnector(**item) for item in state["sources"]]

    def update_source(self, source_key: str, payload: SourceConnectorPayload) -> SourceConnector:
        state = self._upgrade_state(self._read())
        source = self._find_source(state, source_key)
        source.update(payload.model_dump(exclude_none=True))
        source["updated_at"] = now_iso()
        config = self._read_config()
        overrides = config.setdefault("sources", {}).setdefault("overrides", {})
        overrides[source_key] = {
            "enabled": bool(source.get("enabled", True)),
            "schedule": str(source.get("schedule") or "").strip(),
            "priority": int(source.get("priority") or 5),
            "url": source.get("url"),
            "tags": deepcopy_json(source.get("tags", [])),
            "weight": float(source.get("weight") or 0.7),
            "auth": deepcopy_json(source.get("auth", {})),
        }
        self._append_log(state, "success", "source", f"已更新来源配置：{source['name']}")
        runtime = self._runtime(state)
        runtime["next_collect_at"] = self._calculate_next_collect_at(
            state,
            minimum_interval_minutes=self._collect_interval_for_profile(state),
        )
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return SourceConnector(**source)

    def create_source(self, payload: CreateSourcePayload) -> SourceConnector:
        state = self._upgrade_state(self._read())
        existing = [item for item in state["sources"] if item["key"] == payload.key]
        if existing:
            raise ValueError(f"来源 key 已存在: {payload.key}")
        new_source = {
            "key": payload.key,
            "name": payload.name,
            "kind": payload.kind,
            "driver": payload.driver,
            "platform": "rss" if payload.kind in ("rss", "rsshub") else "api",
            "enabled": payload.enabled,
            "schedule": payload.schedule,
            "interval_minutes": None,
            "priority": payload.priority,
            "weight": payload.weight,
            "auth": payload.auth,
            "url": payload.url,
            "tags": payload.tags,
            "capabilities": [],
            "origin_repo": "user-defined",
            "origin_license": "",
            "health_status": "idle",
            "health_detail": "",
            "item_count": 0,
            "last_synced_at": None,
            "last_error": None,
            "updated_at": now_iso(),
        }
        state["sources"].append(new_source)
        self._append_log(state, "success", "source", f"已添加来源：{payload.name}")
        self._write(state)
        return SourceConnector(**new_source)

    def delete_source(self, source_key: str) -> None:
        state = self._upgrade_state(self._read())
        self._find_source(state, source_key)
        state["sources"] = [item for item in state["sources"] if item["key"] != source_key]
        config = self._read_config()
        overrides = config.setdefault("sources", {}).setdefault("overrides", {})
        overrides.pop(source_key, None)
        self._append_log(state, "success", "source", f"已删除来源：{source_key}")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)

    def sync_sources(self, triggered_by: str = "dashboard") -> SourceSyncResponse:
        state = self._upgrade_state(self._read())
        started_at = now_iso()
        response = self._sync_sources_internal(state, triggered_by=triggered_by)
        self._append_job(
            state,
            "collect_news",
            f"已采集 {response.raw_count} 条素材并刷新事件聚合。",
            triggered_by=triggered_by,
        )
        if database_write_enabled():
            persist_ingest_chain_state(
                state,
                source_key=None,
                triggered_by=triggered_by,
                started_at=started_at,
                finished_at=response.synced_at,
                status="completed" if not response.warnings else "partial",
                warnings=list(response.warnings),
            )
        self._write(state)
        return response

    def sync_source(self, source_key: str, triggered_by: str = "dashboard") -> SourceSyncResponse:
        state = self._upgrade_state(self._read())
        source = self._find_source(state, source_key)
        started_at = now_iso()
        stamp = now_iso()
        warnings: list[str] = []
        try:
            items, warning = collect_from_source(source)
            if warning:
                warnings.append(f"{source['name']}: {warning}")
        except Exception as exc:  # pragma: no cover - defensive
            items = []
            warnings.append(f"{source['name']}: 抓取器异常，已跳过: {exc}")

        warning_text = warnings[0] if warnings else None
        source["item_count"] = len(items)
        source["last_synced_at"] = stamp
        if warning_text and items:
            source["health_status"] = "warning"
            source["health_detail"] = warning_text
        elif warning_text:
            source["health_status"] = "error"
            source["health_detail"] = warning_text
        else:
            source["health_status"] = "healthy"
            source["health_detail"] = f"最近一次同步产生 {len(items)} 条素材。"
        source["last_error"] = warning_text

        state["raw_items"] = sorted(
            [item for item in state["raw_items"] if item["source_key"] != source_key] + items,
            key=lambda item: parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )[:MAX_RAW_ITEMS]
        self._rebuild_candidates_for_state(state)
        runtime = self._runtime(state)
        runtime["last_collect_at"] = stamp
        if items:
            runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(
            state,
            minimum_interval_minutes=self._collect_interval_for_profile(state),
        )
        message = f"已重抓来源 {source['name']}，新增 {len(items)} 条素材，当前聚合出 {len(state.get('intel_events', []))} 个事件。"
        level = "success" if not warning_text else "warning"
        if not items and warning_text:
            message = f"已执行来源重抓，但 {source['name']} 本轮没有返回任何真实素材。"
        elif not items:
            level = "warning"
            message = f"已执行来源重抓，但 {source['name']} 本轮没有新增素材。"
        self._append_log(
            state,
            level,
            "collection",
            message,
            stream="business_event",
            actor=triggered_by,
        )
        for warning in warnings[:3]:
            self._append_log(state, "warning", "collection", warning, stream="business_event", actor=triggered_by)
        self._append_job(state, "collect_news", f"已重抓来源《{source['name']}》。", triggered_by=triggered_by)
        if database_write_enabled():
            persist_ingest_chain_state(
                state,
                source_key=source_key,
                triggered_by=triggered_by,
                started_at=started_at,
                finished_at=stamp,
                status="completed" if not warnings else "partial",
                warnings=list(warnings),
            )
        self._write(state)
        return SourceSyncResponse(
            raw_count=len(state["raw_items"]),
            normalized_count=len(state["normalized_items"]),
            event_count=len(state.get("intel_events", [])),
            synced_at=stamp,
            warnings=warnings,
        )

    def get_intel_snapshot(self) -> IntelSnapshot:
        state = self._upgrade_state(self._read())
        stream = self._intel_stream(state)
        clusters = self._hot_clusters(state)
        github_watch = self._github_watch(state)
        source_health = [SourceConnector(**item) for item in state["sources"]]
        return IntelSnapshot(
            stream=stream,
            clusters=clusters,
            github_watch=github_watch,
            source_health=source_health,
        )

    def _find_event(self, state: dict[str, Any], event_id: str) -> dict[str, Any]:
        for event in state.get("intel_events", []):
            if event.get("id") == event_id:
                return event
        raise ValueError(f"未找到事件：{event_id}")

    def get_intel_summary(self) -> IntelOverviewSummary:
        if database_read_is_truth():
            return get_intel_summary_from_db(database_url=current_database_url())
        with self._lock:
            state = self._read_live()
            recovered_run_id = self._recover_stale_runtime_run(state, actor="intel_summary")
            runtime = self._runtime(state)
            if recovered_run_id:
                self._write(state)

        alert_dicts = [item for item in state.get("intel_alerts", []) if isinstance(item, dict)]
        event_dicts = [item for item in state.get("intel_events", []) if isinstance(item, dict)]
        event_lookup = self._event_lookup(state)
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)
        recent_alert_dicts = self._prune_intel_alert_history(state.get("intel_alert_history", []))
        recent_event_dicts = self._prune_intel_event_history(state.get("intel_event_history", []))
        alerts = [
            IntelAlert(
                **self._project_alert_runtime_fields(
                    state,
                    item,
                    event_lookup=event_lookup,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in alert_dicts
        ]
        events = [
            IntelEvent(
                **self._project_event_runtime_fields(
                    state,
                    item,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in event_dicts
        ]
        recent_alerts = [item for item in recent_alert_dicts]
        recent_events = [item for item in recent_event_dicts]
        featured_alerts = [item for item in alerts if item.level in {"breakout", "rising"}]
        engagement_threshold = self._featured_event_engagement_threshold(event_dicts)
        featured_events = [
            IntelEvent(
                **self._project_event_runtime_fields(
                    state,
                    item,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in event_dicts
            if self._is_featured_event(item, engagement_threshold)
        ]
        discovery_items = state.get("discovery_items", [])
        enabled_sources = [item for item in state["sources"] if item.get("enabled")]
        healthy_sources = len([item for item in enabled_sources if item.get("health_status") == "healthy"])
        warning_sources = len([item for item in enabled_sources if item.get("health_status") == "warning"])
        error_sources = len([item for item in enabled_sources if item.get("health_status") == "error"])
        source_alerts = [
            f"{item['name']}：{item['health_detail']}"
            for item in enabled_sources
            if item.get("health_status") in {"warning", "error"}
        ]
        if not source_alerts:
            source_alerts = ["暂无来源异常，信息获取链路正常。"]

        item_state_counts = Counter(str(item.get("item_state") or "new_item") for item in discovery_items)
        event_state_counts = Counter(str(item.get("change_state") or "new_event") for item in state.get("intel_events", []))

        result = IntelOverviewSummary(
            alert_count=len(alerts),
            breakout_count=len([item for item in alerts if item.level == "breakout"]),
            rising_count=len([item for item in alerts if item.level == "rising"]),
            watch_count=len([item for item in alerts if item.level == "watch"]),
            event_count=len(events),
            discovery_count=len(discovery_items),
            new_items_count=int(item_state_counts.get("new_item", 0)),
            seen_items_count=int(item_state_counts.get("seen_item", 0)),
            updated_items_count=int(item_state_counts.get("updated_item", 0)),
            new_events_count=int(event_state_counts.get("new_event", 0)),
            growing_events_count=int(event_state_counts.get("growing_event", 0)),
            stable_events_count=int(event_state_counts.get("stable_event", 0)),
            cooling_events_count=int(event_state_counts.get("cooling_event", 0)),
            warning_sources=warning_sources,
            error_sources=error_sources,
            healthy_sources=healthy_sources,
            total_sources=len(enabled_sources),
            recent_alert_count_24h=len(recent_alerts),
            recent_event_count_24h=len(recent_events),
            recent_breakout_count_24h=len([item for item in recent_alerts if str(item.get("highest_level") or "") == "breakout"]),
            recent_rising_count_24h=len([item for item in recent_alerts if str(item.get("highest_level") or "") == "rising"]),
            last_sync_at=runtime.get("last_successful_sync_at") or runtime.get("last_collect_at"),
            next_run_at=self._calculate_next_collect_at(state),
            running=runtime.get("control_state") != "stopped",
            work_scope=self._work_scope(state),
            top_alerts=featured_alerts[:6],
            top_events=featured_events[:8],
            recent_alerts_24h=recent_alerts,
            recent_events_24h=recent_events,
            source_alerts=source_alerts[:6],
        )
        if database_write_enabled():
            db_result = get_intel_summary_from_db(database_url=current_database_url())
            if self._shadow_signature(result.model_dump()) != self._shadow_signature(db_result.model_dump()):
                self._log_shadow_diff(
                    "summary 数据库影子读与 JSON 投影不一致。",
                    detail="category=summary",
                )
        return result

    def list_discovery_items(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        q: str | None = None,
        time_range: str | None = None,
        platform: str | None = None,
        source: str | None = None,
        item_state: str | None = None,
        min_engagement: int | None = None,
        max_engagement: int | None = None,
    ) -> tuple[list[DiscoveryItem], int, list[str], list[str]]:
        if database_read_is_truth():
            return list_discovery_items_from_db(
                database_url=current_database_url(),
                page=page,
                page_size=page_size,
                q=q,
                time_range=time_range,
                platform=platform,
                source=source,
                item_state=item_state,
                min_engagement=min_engagement,
                max_engagement=max_engagement,
            )
        state = self._read_live()
        all_items = [DiscoveryItem(**item) for item in state.get("discovery_items", [])]
        available_platforms, available_sources = _stream_options(all_items)
        filtered_items = _filter_stream_items(
            all_items,
            q=q,
            time_range=time_range,
            platform=platform,
            source=source,
            item_state=item_state,
            min_engagement=min_engagement,
            max_engagement=max_engagement,
        )
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 50), 200))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        items = filtered_items[start:end]
        total = len(filtered_items)
        if database_write_enabled():
            db_items, db_total, db_platforms, db_sources = list_discovery_items_from_db(
                database_url=current_database_url(),
                page=page,
                page_size=page_size,
                q=q,
                time_range=time_range,
                platform=platform,
                source=source,
                item_state=item_state,
                min_engagement=min_engagement,
                max_engagement=max_engagement,
            )
            if (
                total != db_total
                or available_platforms != db_platforms
                or available_sources != db_sources
                or self._shadow_signature([item.model_dump() for item in items]) != self._shadow_signature([item.model_dump() for item in db_items])
            ):
                self._log_shadow_diff(
                    "stream 数据库影子读与 JSON 投影不一致。",
                    detail=f"json_total={total} | db_total={db_total}",
                )
        return items, total, available_platforms, available_sources

    def list_intel_events(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IntelEvent], int]:
        if database_read_is_truth():
            return list_intel_events_from_db(database_url=current_database_url(), page=page, page_size=page_size)
        state = self._read_live()
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)
        all_items = [
            IntelEvent(
                **self._project_event_runtime_fields(
                    state,
                    item,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in state.get("intel_events", [])
        ]
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 50), 200))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        items = all_items[start:end]
        total = len(all_items)
        if database_write_enabled():
            db_items, db_total = list_intel_events_from_db(database_url=current_database_url(), page=page, page_size=page_size)
            if total != db_total or self._shadow_signature([item.model_dump() for item in items]) != self._shadow_signature([item.model_dump() for item in db_items]):
                self._log_shadow_diff(
                    "events 数据库影子读与 JSON 投影不一致。",
                    detail=f"json_total={total} | db_total={db_total}",
                )
        return items, total

    def list_intel_event_history(self) -> list[dict[str, Any]]:
        if database_read_is_truth():
            return [item.model_dump() for item in list_intel_event_history_from_db(database_url=current_database_url())]
        state = self._read_live()
        return self._prune_intel_event_history(state.get("intel_event_history", []))

    def get_intel_event(self, event_id: str) -> IntelEvent:
        state = self._read_live()
        return IntelEvent(
            **self._project_event_runtime_fields(
                state,
                self._find_event(state, event_id),
                deep_dive_lookup=self._deep_dive_lookup(state),
                brief_lookup=self._brief_lookup(state),
            )
        )

    def list_intel_alerts(self) -> list[IntelAlert]:
        if database_read_is_truth():
            return list_intel_alerts_from_db(database_url=current_database_url())
        state = self._read_live()
        event_lookup = self._event_lookup(state)
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)
        items = [
            IntelAlert(
                **self._project_alert_runtime_fields(
                    state,
                    item,
                    event_lookup=event_lookup,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in state.get("intel_alerts", [])
        ]
        if database_write_enabled():
            db_items = list_intel_alerts_from_db(database_url=current_database_url())
            if self._shadow_signature([item.model_dump() for item in items]) != self._shadow_signature([item.model_dump() for item in db_items]):
                self._log_shadow_diff(
                    "alerts 数据库影子读与 JSON 投影不一致。",
                    detail=f"json_total={len(items)} | db_total={len(db_items)}",
                )
        return items

    def list_intel_alert_history(self) -> list[dict[str, Any]]:
        if database_read_is_truth():
            return [item.model_dump() for item in list_intel_alert_history_from_db(database_url=current_database_url())]
        state = self._read_live()
        return self._prune_intel_alert_history(state.get("intel_alert_history", []))

    def _normalize_entity_watchlist_item(
        self,
        item: dict[str, Any],
        existing: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        existing = existing or {}
        entity_name = str(item.get("entity_name") or "").strip()
        entity_id = str(item.get("entity_id") or "").strip()
        if not entity_name and entity_id and entity_id in existing:
            entity_name = str(existing[entity_id].get("entity_name") or "").strip()
        if not entity_name:
            return None
        if not entity_id:
            entity_id = entity_id_for_name(entity_name)
        previous = existing.get(entity_id, {})
        entity_type = str(
            item.get("entity_type")
            or previous.get("entity_type")
            or entity_type_for_name(entity_name)
            or ""
        ).strip().upper()
        if not entity_type:
            return None
        return {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "watchlisted": bool(item.get("watchlisted", previous.get("watchlisted", True))),
            "added_at": item.get("added_at") or previous.get("added_at") or now_iso(),
        }

    def _entity_watchlist(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        settings = state.setdefault("settings", {})
        items = settings.setdefault("entity_watchlist", [])
        if not isinstance(items, list):
            settings["entity_watchlist"] = []
            return settings["entity_watchlist"]
        return items

    def list_entity_watchlist(self) -> list[EntityWatchlistItem]:
        state = self._read_live()
        return [EntityWatchlistItem(**item) for item in self._entity_watchlist(state)]

    def update_entity_watchlist(self, items: list[dict[str, Any]]) -> list[EntityWatchlistItem]:
        with self._lock:
            state = self._upgrade_state(self._read())
            existing_items = {
                str(item.get("entity_id") or ""): item
                for item in self._entity_watchlist(state)
                if item.get("entity_id")
            }
            normalized: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for raw_item in items:
                if not isinstance(raw_item, dict):
                    continue
                item = self._normalize_entity_watchlist_item(raw_item, existing=existing_items)
                if not item:
                    continue
                entity_id = str(item.get("entity_id") or "")
                if not entity_id or entity_id in seen_ids:
                    continue
                seen_ids.add(entity_id)
                normalized.append(item)
            state.setdefault("settings", {})["entity_watchlist"] = normalized
            self._append_log(
                state,
                "info",
                "settings",
                f"已更新重点监控实体，共 {len(normalized)} 个。",
                actor="dashboard",
            )
            self._write(state)
            return [EntityWatchlistItem(**item) for item in normalized]

    def _build_entity_watchlist_summary(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        watchlist = [item for item in self._entity_watchlist(state) if item.get("watchlisted")]
        if not watchlist:
            return []
        events = state.get("intel_events", [])
        alerts = state.get("intel_alerts", [])
        summaries: list[dict[str, Any]] = []
        for item in watchlist:
            entity_id = str(item.get("entity_id") or "")
            entity_name = str(item.get("entity_name") or "")
            matched_events = [
                event for event in events
                if entity_id in event.get("entity_ids", []) or entity_name in event.get("entity_names", [])
            ]
            matched_alerts = [
                alert for alert in alerts
                if entity_id in alert.get("entity_ids", []) or entity_name in alert.get("entity_names", [])
            ]
            last_seen_candidates = [
                event.get("last_seen_at") or event.get("latest_collected_at") or event.get("first_seen_at")
                for event in matched_events
            ]
            last_seen = max(
                last_seen_candidates,
                key=lambda value: parse_time(value) or datetime.min.replace(tzinfo=UTC),
                default=None,
            )
            summaries.append(
                {
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "entity_type": str(item.get("entity_type") or entity_type_for_name(entity_name)),
                    "watchlisted": True,
                    "added_at": item.get("added_at"),
                    "event_count": len(matched_events),
                    "alert_count": len(matched_alerts),
                    "rising_count": len([alert for alert in matched_alerts if alert.get("level") == "rising"]),
                    "breakout_count": len([alert for alert in matched_alerts if alert.get("level") == "breakout"]),
                    "last_seen_at": last_seen,
                }
            )
        summaries.sort(
            key=lambda current: (
                int(current.get("breakout_count", 0) or 0),
                int(current.get("rising_count", 0) or 0),
                parse_time(current.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        return summaries

    def list_intel_sources(self) -> list[SourceConnector]:
        state = self._read_live()
        return [SourceConnector(**item) for item in state.get("sources", [])]

    def watchlist_event(self, event_id: str) -> IntelEvent:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            event["watchlisted"] = True
            event["ignored"] = False
            state["normalized_items"] = self._project_normalized_items_from_events(state)
            self._append_log(state, "success", "intel", f"已加入重点观察：{event['title']}", actor="dashboard")
            self._write(state)
            if database_write_enabled():
                persist_ingest_chain_state(
                    self._upgrade_state(self._read()),
                    source_key=None,
                    triggered_by="dashboard",
                    status="completed",
                )
            return IntelEvent(**event)

    def ignore_event(self, event_id: str) -> IntelEvent:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            event["ignored"] = True
            event["watchlisted"] = False
            state["intel_alerts"] = [item for item in state.get("intel_alerts", []) if item.get("event_id") != event_id]
            state["normalized_items"] = self._project_normalized_items_from_events(state)
            self._append_log(state, "warning", "intel", f"已忽略事件：{event['title']}", actor="dashboard")
            self._write(state)
            if database_write_enabled():
                persist_ingest_chain_state(
                    self._upgrade_state(self._read()),
                    source_key=None,
                    triggered_by="dashboard",
                    status="completed",
                )
            return IntelEvent(**event)

    def get_dashboard(self) -> DashboardResponse:
        with self._lock:
            state = self._read_live()
            recovered_run_id = self._recover_stale_runtime_run(state, actor="dashboard")
            if recovered_run_id:
                self._write(state)
            snapshot = deepcopy(state)

        browser = self._refresh_browser_session(snapshot)
        backends = self._publish_backends(snapshot)
        runtime = self._runtime(snapshot)
        app_version = self.get_app_version_info()
        update_info = self.get_app_update_info(force=False)
        runtime["next_collect_at"] = self._calculate_next_collect_at(snapshot)
        runtime["launch_mode"] = self._runtime_plan(snapshot).get("launch_mode", "interval_now")
        runtime_status = self._scheduler_status_from_state(snapshot)
        last_cycle_summary = runtime.get("last_cycle_summary") or self._build_last_cycle_summary(snapshot, runtime)
        recent_alerts_24h = self._prune_intel_alert_history(snapshot.get("intel_alert_history", []))
        recent_events_24h = self._prune_intel_event_history(snapshot.get("intel_event_history", []))
        freshness = self._freshness_snapshot(snapshot)
        top_bar = self._dashboard_top_bar(snapshot, freshness)
        intel_stream = self._intel_stream(snapshot)
        hot_clusters = self._hot_clusters(snapshot)
        github_watch = self._github_watch(snapshot)
        execution_chain = self._execution_chain(snapshot, browser)
        entity_watchlist_summary = self._build_entity_watchlist_summary(snapshot)
        setup_status = self._setup_status(snapshot, browser)
        doctor = self.system_doctor()
        stats = {
            "total_sources": top_bar.total_sources,
            "healthy_sources": top_bar.healthy_sources,
            "collected_today": freshness.items_24h,
            "event_count": len(snapshot["intel_events"]),
            "deep_dive_ready": len(
                [
                    item
                    for item in snapshot.get("event_deep_dives", [])
                    if str(item.get("status") or "") in {"ready", "partial"}
                ]
            ),
            "brief_total": len(snapshot.get("briefs", [])),
            "brief_prepared": len([item for item in snapshot.get("briefs", []) if str(item.get("stage") or "") == "prepared"]),
            "brief_synced": len([item for item in snapshot.get("briefs", []) if str(item.get("stage") or "") == "synced"]),
            "publish_blocked": len(
                [item for item in snapshot.get("publish_tasks", []) if item.get("status") in {"blocked", "failed"}]
            ),
        }
        snapshot["browser"]["wechat"] = browser
        return DashboardResponse(
            app_version=app_version,
            update_info=update_info,
            stats=DashboardStats(**stats),
            top_bar=top_bar,
            freshness=freshness,
            intel_stream=intel_stream,
            hot_clusters=hot_clusters,
            github_watch=github_watch,
            execution_chain=execution_chain,
            current_automation_mode=AutomationModeDefinition(**self._current_automation_mode_def(snapshot)),
            current_automation_profile=AutomationModeProfile(**self._current_automation_profile(snapshot)),
            automation_profiles=[AutomationModeProfile(**item) for item in snapshot["automation_profiles"]],
            runtime_plan=self._runtime_plan_from_state(snapshot),
            runtime_status=runtime_status,
            last_cycle_summary=RuntimeCycleSummary(**last_cycle_summary) if isinstance(last_cycle_summary, dict) else None,
            recent_alerts_24h=recent_alerts_24h,
            recent_events_24h=recent_events_24h,
            entity_watchlist_summary=[EntityWatchlistSummaryItem(**item) for item in entity_watchlist_summary],
            recent_logs=[LogItem(**item) for item in snapshot["logs"][:8]],
            briefs=[],
            deep_dives=[],
            sources=[],
            browser_session=BrowserSessionState(**browser),
            publish_backends=[PublishBackendStatus(**item) for item in backends],
            setup_status=setup_status,
            doctor_summary=doctor.model_dump(),
        )

    def get_dashboard_lite(self) -> DashboardResponse:
        """Lightweight dashboard for polling — excludes heavy data like entity watchlist."""
        with self._lock:
            state = self._read_live()
            recovered_run_id = self._recover_stale_runtime_run(state, actor="dashboard")
            if recovered_run_id:
                self._write(state)
            snapshot = deepcopy(state)

        browser = self._refresh_browser_session(snapshot)
        runtime = self._runtime(snapshot)
        app_version = self.get_app_version_info()
        runtime_status = self._scheduler_status_from_state(snapshot)
        snapshot["browser"]["wechat"] = browser

        return DashboardResponse(
            app_version=app_version,
            update_info=self.get_app_update_info(force=False),
            runtime_plan=self._runtime_plan_from_state(snapshot),
            runtime_status=runtime_status,
            entity_watchlist_summary=[],  # Exclude heavy data from lite version
            browser_session=BrowserSessionState(**browser),
            recent_logs=[LogItem(**item) for item in snapshot["logs"][:8]],
        )
