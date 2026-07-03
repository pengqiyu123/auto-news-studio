from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..store.base import UTC, parse_time
from .models import (
    DiscoveryItemCurrentRecord,
    EventSnapshotRecord,
    IntelAlertCurrentRecord,
    IntelAlertHistoryRecord,
    IntelEventCurrentRecord,
    IntelEventHistoryRecord,
    RawItemRecord,
    SourceConnectorRecord,
)
from .session import build_session_factory


def _dt(value: Any) -> datetime | None:
    parsed = parse_time(str(value or ""))
    if parsed:
        return parsed
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _json_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def load_state_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _replace_rows(session: Session, model: type, rows: Iterable[dict[str, Any]]) -> int:
    session.query(model).delete()
    count = 0
    for row in rows:
        session.add(model(**row))
        count += 1
    return count


def _append_rows_by_id(session: Session, model: type, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            continue
        existing = session.get(model, row_id)
        if existing is not None:
            continue
        session.add(model(**row))
        count += 1
    return count


def _upsert_history_rows(session: Session, model: type, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            continue
        existing = session.get(model, row_id)
        if existing is None:
            session.add(model(**row))
            count += 1
            continue
        for key, value in row.items():
            setattr(existing, key, value)
        count += 1
    return count


def sync_ingest_projection_from_state(state: dict[str, Any], *, database_url: str) -> dict[str, int]:
    session_factory = build_session_factory(database_url)
    counts: dict[str, int] = {}
    with session_factory() as session:
        counts["sources"] = _replace_rows(
            session,
            SourceConnectorRecord,
            (
                {
                    "source_key": str(item.get("key") or ""),
                    "name": str(item.get("name") or ""),
                    "kind": str(item.get("kind") or "rss"),
                    "driver": str(item.get("driver") or ""),
                    "platform": str(item.get("platform") or ""),
                    "enabled": bool(item.get("enabled", True)),
                    "schedule": str(item.get("schedule") or ""),
                    "interval_minutes": item.get("interval_minutes"),
                    "priority": int(item.get("priority") or 5),
                    "weight": float(item.get("weight") or 0.7),
                    "auth_json": _json_dict(item.get("auth")),
                    "url": item.get("url"),
                    "tags_json": _json_list(item.get("tags")),
                    "capabilities_json": _json_list(item.get("capabilities")),
                    "origin_repo": str(item.get("origin_repo") or ""),
                    "origin_license": str(item.get("origin_license") or ""),
                    "health_status": str(item.get("health_status") or "idle"),
                    "health_detail": str(item.get("health_detail") or ""),
                    "item_count": int(item.get("item_count") or 0),
                    "last_synced_at": _dt(item.get("last_synced_at")),
                    "last_error": item.get("last_error"),
                    "updated_at": _dt(item.get("updated_at")),
                }
                for item in state.get("sources", [])
                if isinstance(item, dict) and item.get("key")
            ),
        )

        counts["raw_items"] = _append_rows_by_id(
            session,
            RawItemRecord,
            (
                {
                    "id": str(item.get("id") or ""),
                    "source_key": str(item.get("source_key") or ""),
                    "title": str(item.get("title") or ""),
                    "summary": str(item.get("summary") or ""),
                    "content": str(item.get("content") or ""),
                    "link": str(item.get("link") or ""),
                    "canonical_link": item.get("canonical_link"),
                    "dedupe_key": item.get("dedupe_key"),
                    "source_native_id": item.get("source_native_id"),
                    "published_at": _dt(item.get("published_at")),
                    "collected_at": _dt(item.get("collected_at")) or datetime.now(UTC),
                    "score": _coerce_float(item.get("score")),
                    "tags_json": _json_list(item.get("tags")),
                    "metadata_json": _json_dict(item.get("metadata")),
                }
                for item in state.get("raw_items", [])
                if isinstance(item, dict) and item.get("id")
            ),
        )

        counts["discovery_items_current"] = _replace_rows(
            session,
            DiscoveryItemCurrentRecord,
            (
                {
                    "id": str(item.get("id") or ""),
                    "raw_item_id": str(item.get("raw_item_id") or ""),
                    "source_key": str(item.get("source_key") or ""),
                    "source_name": str(item.get("source_name") or ""),
                    "source_kind": str(item.get("source_kind") or ""),
                    "platform": str(item.get("platform") or ""),
                    "title": str(item.get("title") or ""),
                    "summary": str(item.get("summary") or ""),
                    "content": str(item.get("content") or ""),
                    "link": str(item.get("link") or ""),
                    "canonical_link": str(item.get("canonical_link") or ""),
                    "dedupe_key": str(item.get("dedupe_key") or ""),
                    "source_native_id": item.get("source_native_id"),
                    "title_tokens_json": _json_list(item.get("title_tokens")),
                    "anchor_tokens_json": _json_list(item.get("anchor_tokens")),
                    "published_at": _dt(item.get("published_at")),
                    "collected_at": _dt(item.get("collected_at")) or datetime.now(UTC),
                    "tags_json": _json_list(item.get("tags")),
                    "engagement_score": float(item.get("engagement_score") or 0),
                    "item_state": str(item.get("item_state") or "new_item"),
                    "entity_ids_json": _json_list(item.get("entity_ids")),
                    "entity_names_json": _json_list(item.get("entity_names")),
                    "metadata_json": _json_dict(item.get("metadata")),
                }
                for item in state.get("discovery_items", [])
                if isinstance(item, dict) and item.get("id")
            ),
        )

        counts["intel_events_current"] = _replace_rows(
            session,
            IntelEventCurrentRecord,
            (
                {
                    "id": str(item.get("id") or ""),
                    "title": str(item.get("title") or ""),
                    "summary": str(item.get("summary") or ""),
                    "representative_link": str(item.get("representative_link") or ""),
                    "representative_source_name": str(item.get("representative_source_name") or ""),
                    "representative_discovery_item_id": str(item.get("representative_discovery_item_id") or ""),
                    "discovery_item_ids_json": _json_list(item.get("discovery_item_ids")),
                    "source_keys_json": _json_list(item.get("source_keys")),
                    "source_names_json": _json_list(item.get("source_names")),
                    "platforms_json": _json_list(item.get("platforms")),
                    "platform_count": int(item.get("platform_count") or 0),
                    "source_count": int(item.get("source_count") or 0),
                    "member_count": int(item.get("member_count") or 0),
                    "story_count": int(item.get("story_count") or 0),
                    "member_delta": int(item.get("member_delta") or 0),
                    "platform_delta": int(item.get("platform_delta") or 0),
                    "published_at": _dt(item.get("published_at")),
                    "latest_collected_at": _dt(item.get("latest_collected_at")),
                    "first_seen_at": _dt(item.get("first_seen_at")),
                    "last_seen_at": _dt(item.get("last_seen_at")),
                    "tags_json": _json_list(item.get("tags")),
                    "anchor_tokens_json": _json_list(item.get("anchor_tokens")),
                    "velocity_score": float(item.get("velocity_score") or 0),
                    "coverage_score": float(item.get("coverage_score") or 0),
                    "freshness_score": float(item.get("freshness_score") or 0),
                    "audience_fit_score": float(item.get("audience_fit_score") or 0),
                    "composite_score": float(item.get("composite_score") or 0),
                    "velocity_details_json": _json_dict(item.get("velocity_details")),
                    "alert_state": str(item.get("alert_state") or "new"),
                    "change_state": str(item.get("change_state") or "new_event"),
                    "alert_reason": str(item.get("alert_reason") or ""),
                    "entity_ids_json": _json_list(item.get("entity_ids")),
                    "entity_names_json": _json_list(item.get("entity_names")),
                    "watchlisted": bool(item.get("watchlisted", False)),
                    "ignored": bool(item.get("ignored", False)),
                    "deep_dive_id": item.get("deep_dive_id"),
                    "brief_id": item.get("brief_id"),
                    "deep_dive_status": item.get("deep_dive_status"),
                    "deep_dive_started_at": _dt(item.get("deep_dive_started_at")),
                    "deep_dive_finished_at": _dt(item.get("deep_dive_finished_at")),
                    "deep_dive_updated_at": _dt(item.get("deep_dive_updated_at")),
                    "brief_status": item.get("brief_status"),
                    "deep_dive_summary": str(item.get("deep_dive_summary") or ""),
                    "worth_to_brief": bool(item.get("worth_to_brief", False)),
                    "worth_reason": str(item.get("worth_reason") or ""),
                }
                for item in state.get("intel_events", [])
                if isinstance(item, dict) and item.get("id")
            ),
        )

        counts["event_snapshots"] = _append_rows_by_id(
            session,
            EventSnapshotRecord,
            (
                {
                    "id": str(item.get("id") or ""),
                    "event_id": str(item.get("event_id") or ""),
                    "captured_at": _dt(item.get("captured_at")) or datetime.now(UTC),
                    "member_count": int(item.get("member_count") or 0),
                    "platform_count": int(item.get("platform_count") or 0),
                    "source_count": int(item.get("source_count") or 0),
                    "velocity_score": float(item.get("velocity_score") or 0),
                    "coverage_score": float(item.get("coverage_score") or 0),
                    "freshness_score": float(item.get("freshness_score") or 0),
                    "audience_fit_score": float(item.get("audience_fit_score") or 0),
                    "composite_score": float(item.get("composite_score") or 0),
                    "alert_state": str(item.get("alert_state") or "new"),
                }
                for item in state.get("event_snapshots", [])
                if isinstance(item, dict) and item.get("id")
            ),
        )

        counts["intel_alerts_current"] = _replace_rows(
            session,
            IntelAlertCurrentRecord,
            (
                {
                    "id": str(item.get("id") or ""),
                    "event_id": str(item.get("event_id") or ""),
                    "title": str(item.get("title") or ""),
                    "level": str(item.get("level") or "watch"),
                    "reason": str(item.get("reason") or ""),
                    "velocity_score": float(item.get("velocity_score") or 0),
                    "coverage_score": float(item.get("coverage_score") or 0),
                    "freshness_score": float(item.get("freshness_score") or 0),
                    "audience_fit_score": float(item.get("audience_fit_score") or 0),
                    "composite_score": float(item.get("composite_score") or 0),
                    "platform_count": int(item.get("platform_count") or 0),
                    "source_count": int(item.get("source_count") or 0),
                    "representative_link": str(item.get("representative_link") or ""),
                    "triggered_at": _dt(item.get("triggered_at")) or datetime.now(UTC),
                    "entity_ids_json": _json_list(item.get("entity_ids")),
                    "entity_names_json": _json_list(item.get("entity_names")),
                    "deep_dive_id": item.get("deep_dive_id"),
                    "brief_id": item.get("brief_id"),
                    "deep_dive_status": item.get("deep_dive_status"),
                    "brief_status": item.get("brief_status"),
                    "deep_dive_summary": str(item.get("deep_dive_summary") or ""),
                    "worth_to_brief": bool(item.get("worth_to_brief", False)),
                    "worth_reason": str(item.get("worth_reason") or ""),
                }
                for item in state.get("intel_alerts", [])
                if isinstance(item, dict) and item.get("id")
            ),
        )

        counts["intel_event_history"] = _upsert_history_rows(
            session,
            IntelEventHistoryRecord,
            (
                {
                    "id": str(item.get("id") or item.get("history_id") or ""),
                    "event_id": str(item.get("event_id") or ""),
                    "title": str(item.get("title") or ""),
                    "summary": str(item.get("summary") or ""),
                    "representative_link": str(item.get("representative_link") or ""),
                    "representative_source_name": str(item.get("representative_source_name") or ""),
                    "change_state": str(item.get("change_state") or item.get("latest_alert_state") or "new_event"),
                    "alert_state": str(item.get("alert_state") or item.get("latest_alert_state") or "new"),
                    "highest_level": item.get("highest_level"),
                    "member_count": int(item.get("member_count") or 0),
                    "platform_count": int(item.get("platform_count") or 0),
                    "source_count": int(item.get("source_count") or 0),
                    "velocity_score": float(item.get("velocity_score") or 0),
                    "coverage_score": float(item.get("coverage_score") or 0),
                    "freshness_score": float(item.get("freshness_score") or 0),
                    "audience_fit_score": float(item.get("audience_fit_score") or 0),
                    "composite_score": float(item.get("composite_score") or 0),
                    "recorded_at": _dt(item.get("recorded_at") or item.get("last_seen_at") or item.get("discovered_at")) or datetime.now(UTC),
                    "detail_json": _json_dict(item),
                }
                for item in state.get("intel_event_history", [])
                if isinstance(item, dict) and (item.get("id") or item.get("history_id"))
            ),
        )

        counts["intel_alert_history"] = _upsert_history_rows(
            session,
            IntelAlertHistoryRecord,
            (
                {
                    "id": str(item.get("id") or item.get("history_id") or ""),
                    "event_id": str(item.get("event_id") or ""),
                    "title": str(item.get("title") or ""),
                    "level": str(item.get("level") or item.get("latest_level") or "watch"),
                    "highest_level": item.get("highest_level"),
                    "reason": str(item.get("reason") or ""),
                    "representative_link": str(item.get("representative_link") or ""),
                    "velocity_score": float(item.get("velocity_score") or 0),
                    "coverage_score": float(item.get("coverage_score") or 0),
                    "freshness_score": float(item.get("freshness_score") or 0),
                    "audience_fit_score": float(item.get("audience_fit_score") or 0),
                    "composite_score": float(item.get("composite_score") or 0),
                    "triggered_at": _dt(item.get("triggered_at") or item.get("last_triggered_at") or item.get("first_triggered_at")) or datetime.now(UTC),
                    "detail_json": _json_dict(item),
                }
                for item in state.get("intel_alert_history", [])
                if isinstance(item, dict) and (item.get("id") or item.get("history_id"))
            ),
        )
        session.commit()
    return counts


def sync_ingest_projection_from_state_file(path: Path, *, database_url: str) -> dict[str, int]:
    state = load_state_file(path)
    return sync_ingest_projection_from_state(state, database_url=database_url)


def count_projection_rows(*, database_url: str) -> dict[str, int]:
    session_factory = build_session_factory(database_url)
    counts: dict[str, int] = {}
    tables = [
        "source_connectors",
        "raw_items",
        "discovery_items_current",
        "intel_events_current",
        "event_snapshots",
        "intel_alerts_current",
        "intel_event_history",
        "intel_alert_history",
    ]
    with session_factory() as session:
        for table in tables:
            counts[table] = int(session.execute(text(f"select count(*) from {table}")).scalar_one())
    return counts
