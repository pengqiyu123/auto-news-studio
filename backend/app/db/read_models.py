from __future__ import annotations

from collections import Counter
import json
from typing import Any

from sqlalchemy import text

from .session import build_session_factory
from .status_normalizer import normalize_fetch_status, normalize_extract_status
from ..models import (
    DiscoveryItem,
    IntelAlert,
    IntelEvent,
    IntelEventHistoryItem,
    IntelOverviewSummary,
    IntelAlertHistoryItem,
)
from ..store.base import now_iso


def _json_list(value: Any) -> list:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return value if isinstance(value, list) else []


def _json_dict(value: Any) -> dict:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _summarize_deep_dive_record(record: dict[str, Any] | None) -> str:
    if not record:
        return "尚未开始正文深挖。"
    status = str(record.get("status") or "pending")
    attempted = int(record.get("attempted_count", 0) or 0)
    success = int(record.get("success_count", 0) or 0)
    failed = int(record.get("failed_count", 0) or 0)
    resolved_sources = _json_list(record.get("resolved_evidence_pack"))
    used_tavily = any(str(item.get("source_key") or "") == "tavily" for item in resolved_sources if isinstance(item, dict))
    if status == "ready":
        if used_tavily:
            return f"Tavily 补充搜索后正文深挖已完成，成功 {success}/{attempted} 条来源。"
        return f"正文深挖已完成，成功 {success}/{attempted} 条来源。"
    if status == "partial":
        if used_tavily:
            return f"Tavily 补充搜索后部分完成，成功 {success}/{attempted} 条来源，失败 {failed} 条。"
        return f"正文深挖部分完成，成功 {success}/{attempted} 条来源，失败 {failed} 条。"
    if status == "failed":
        return str(record.get("last_error") or "正文深挖失败。")
    if status == "running":
        return "正在补充来源并抓取正文。"
    return "等待正文深挖。"


def _evaluate_worthiness_from_records(event: dict[str, Any], deep_dive: dict[str, Any] | None) -> tuple[bool, str]:
    if not deep_dive:
        return False, "尚未完成正文深挖。"
    alert_state = str(event.get("alert_state") or "")
    watchlisted = bool(event.get("watchlisted"))
    success_count = int(deep_dive.get("success_count", 0) or 0)
    facts = [item for item in _json_list(deep_dive.get("facts")) if str(item).strip()]
    quotes = [item for item in _json_list(deep_dive.get("quotes")) if str(item).strip()]
    audience_fit_score = float(event.get("audience_fit_score") or 0)
    if success_count < 1:
        return False, "正文深挖仍未拿到可用正文来源。"
    if not facts and not quotes:
        return False, "已抓取正文，但还没有足够可复用的事实或引文。"
    if alert_state in {"rising", "breakout"}:
        return True, f"事件处于 {alert_state} 阶段，且已有可引用正文证据。"
    if watchlisted and audience_fit_score >= 45:
        return True, "事件已进入深挖池，且更贴近公众号大众科技受众，可继续生成简报。"
    if watchlisted:
        return True, "事件已进入深挖池，且已有正文证据，可生成简报继续跟进。"
    return False, "当前仍未进入重点观察或上升/爆发态，建议继续观察。"


def list_discovery_items_from_db(*, database_url: str, page: int = 1, page_size: int = 50) -> tuple[list[DiscoveryItem], int]:
    session_factory = build_session_factory(database_url)
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 50), 200))
    start = (safe_page - 1) * safe_page_size
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select *
                from discovery_items_current
                order by collected_at desc, id desc
                limit :limit offset :offset
                """
            ),
            {"offset": start, "limit": safe_page_size},
        ).mappings().all()
        total = int(session.execute(text("select count(*) from discovery_items_current")).scalar_one())

    items = [
        DiscoveryItem(
            id=row["id"],
            raw_item_id=row["raw_item_id"],
            source_key=row["source_key"],
            source_name=row["source_name"],
            source_kind=row["source_kind"],
            platform=row["platform"],
            title=row["title"],
            summary=row["summary"],
            content=row["content"],
            link=row["link"],
            canonical_link=row["canonical_link"],
            dedupe_key=row["dedupe_key"],
            source_native_id=row["source_native_id"],
            title_tokens=_json_list(row["title_tokens_json"]),
            anchor_tokens=_json_list(row["anchor_tokens_json"]),
            published_at=_iso(row["published_at"]),
            collected_at=_iso(row["collected_at"]) or "",
            tags=_json_list(row["tags_json"]),
            engagement_score=float(row["engagement_score"] or 0),
            item_state=row["item_state"],
            entity_ids=_json_list(row["entity_ids_json"]),
            entity_names=_json_list(row["entity_names_json"]),
            metadata=_json_dict(row["metadata_json"]),
        )
        for row in rows
    ]
    return items, total


def list_intel_events_from_db(*, database_url: str, page: int = 1, page_size: int = 50) -> tuple[list[IntelEvent], int]:
    session_factory = build_session_factory(database_url)
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 50), 200))
    start = (safe_page - 1) * safe_page_size
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select *
                from intel_events_current
                order by composite_score desc, latest_collected_at desc nulls last, id desc
                limit :limit offset :offset
                """
            ),
            {"offset": start, "limit": safe_page_size},
        ).mappings().all()
        total = int(session.execute(text("select count(*) from intel_events_current")).scalar_one())

    event_ids = [str(row["id"] or "") for row in rows if row.get("id")]
    deep_dive_rows_by_event: dict[str, dict[str, Any]] = {}
    brief_rows_by_event: dict[str, dict[str, Any]] = {}
    if event_ids:
        placeholders = ", ".join(f":event_id_{index}" for index, _ in enumerate(event_ids))
        params = {f"event_id_{index}": event_id for index, event_id in enumerate(event_ids)}
        with session_factory() as session:
            deep_dive_rows = session.execute(
                text(
                    f"""
                    select *
                    from deep_dive_records
                    where event_id in ({placeholders})
                    order by updated_at desc, id desc
                    """
                ),
                params,
            ).mappings().all()
            brief_rows = session.execute(
                text(
                    f"""
                    select *
                    from brief_records
                    where event_id in ({placeholders})
                    order by updated_at desc, id desc
                    """
                ),
                params,
            ).mappings().all()
        for row in deep_dive_rows:
            event_id = str(row["event_id"] or "")
            if event_id and event_id not in deep_dive_rows_by_event:
                deep_dive_rows_by_event[event_id] = dict(row)
        for row in brief_rows:
            event_id = str(row["event_id"] or "")
            if event_id and event_id not in brief_rows_by_event:
                brief_rows_by_event[event_id] = dict(row)

    items = []
    for row in rows:
        event_id = str(row["id"] or "")
        deep_dive = deep_dive_rows_by_event.get(event_id)
        brief = brief_rows_by_event.get(event_id)
        deep_dive_summary = _summarize_deep_dive_record(
            {
                "status": deep_dive.get("status") if deep_dive else row["deep_dive_status"],
                "attempted_count": deep_dive.get("attempted_count") if deep_dive else 0,
                "success_count": deep_dive.get("success_count") if deep_dive else 0,
                "failed_count": deep_dive.get("failed_count") if deep_dive else 0,
                "resolved_evidence_pack": _json_list(deep_dive.get("resolved_evidence_pack_json")) if deep_dive else [],
                "facts": _json_list(deep_dive.get("facts_json")) if deep_dive else [],
                "quotes": _json_list(deep_dive.get("quotes_json")) if deep_dive else [],
                "last_error": deep_dive.get("last_error") if deep_dive else None,
            }
            if deep_dive or row["deep_dive_status"] else None
        )
        event_payload = {
            "id": row["id"],
            "alert_state": row["alert_state"],
            "watchlisted": bool(row["watchlisted"]),
            "audience_fit_score": float(row["audience_fit_score"] or 0),
        }
        worth_to_brief, worth_reason = _evaluate_worthiness_from_records(
            event_payload,
            {
                "success_count": deep_dive.get("success_count") if deep_dive else 0,
                "facts": _json_list(deep_dive.get("facts_json")) if deep_dive else [],
                "quotes": _json_list(deep_dive.get("quotes_json")) if deep_dive else [],
            }
            if deep_dive
            else None,
        )
        items.append(
            IntelEvent(
                id=row["id"],
                title=row["title"],
                summary=row["summary"],
                representative_link=row["representative_link"],
                representative_source_name=row["representative_source_name"],
                representative_discovery_item_id=row["representative_discovery_item_id"],
                discovery_item_ids=_json_list(row["discovery_item_ids_json"]),
                source_keys=_json_list(row["source_keys_json"]),
                source_names=_json_list(row["source_names_json"]),
                platforms=_json_list(row["platforms_json"]),
                platform_count=int(row["platform_count"] or 0),
                source_count=int(row["source_count"] or 0),
                member_count=int(row["member_count"] or 0),
                story_count=int(row["story_count"] or 0),
                member_delta=int(row["member_delta"] or 0),
                platform_delta=int(row["platform_delta"] or 0),
                published_at=_iso(row["published_at"]),
                latest_collected_at=_iso(row["latest_collected_at"]),
                first_seen_at=_iso(row["first_seen_at"]),
                last_seen_at=_iso(row["last_seen_at"]),
                tags=_json_list(row["tags_json"]),
                anchor_tokens=_json_list(row["anchor_tokens_json"]),
                velocity_score=float(row["velocity_score"] or 0),
                coverage_score=float(row["coverage_score"] or 0),
                freshness_score=float(row["freshness_score"] or 0),
                audience_fit_score=float(row["audience_fit_score"] or 0),
                composite_score=float(row["composite_score"] or 0),
                velocity_details=_json_dict(row["velocity_details_json"]),
                alert_state=row["alert_state"],
                change_state=row["change_state"],
                alert_reason=row["alert_reason"],
                entity_ids=_json_list(row["entity_ids_json"]),
                entity_names=_json_list(row["entity_names_json"]),
                watchlisted=bool(row["watchlisted"]),
                ignored=bool(row["ignored"]),
                deep_dive_id=(deep_dive or {}).get("id") or row["deep_dive_id"],
                brief_id=(brief or {}).get("id") or row["brief_id"],
                deep_dive_status=(deep_dive or {}).get("status") or row["deep_dive_status"],
                deep_dive_started_at=_iso((deep_dive or {}).get("started_at")) or _iso(row["deep_dive_started_at"]),
                deep_dive_finished_at=_iso((deep_dive or {}).get("finished_at")) or _iso(row["deep_dive_finished_at"]),
                deep_dive_updated_at=_iso((deep_dive or {}).get("updated_at")) or _iso(row["deep_dive_updated_at"]),
                brief_status=(brief or {}).get("stage") or row["brief_status"],
                deep_dive_summary=deep_dive_summary or row["deep_dive_summary"],
                worth_to_brief=worth_to_brief if deep_dive else bool(row["worth_to_brief"]),
                worth_reason=worth_reason if deep_dive else row["worth_reason"],
            )
        )
    return items, total


def list_intel_alerts_from_db(*, database_url: str) -> list[IntelAlert]:
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select *
                from intel_alerts_current
                order by triggered_at desc, composite_score desc, id desc
                """
            )
        ).mappings().all()
    return [
        IntelAlert(
            id=row["id"],
            event_id=row["event_id"],
            title=row["title"],
            level=row["level"],
            reason=row["reason"],
            velocity_score=float(row["velocity_score"] or 0),
            coverage_score=float(row["coverage_score"] or 0),
            freshness_score=float(row["freshness_score"] or 0),
            audience_fit_score=float(row["audience_fit_score"] or 0),
            composite_score=float(row["composite_score"] or 0),
            platform_count=int(row["platform_count"] or 0),
            source_count=int(row["source_count"] or 0),
            representative_link=row["representative_link"],
            triggered_at=_iso(row["triggered_at"]) or "",
            entity_ids=_json_list(row["entity_ids_json"]),
            entity_names=_json_list(row["entity_names_json"]),
            deep_dive_id=row["deep_dive_id"],
            brief_id=row["brief_id"],
            deep_dive_status=row["deep_dive_status"],
            brief_status=row["brief_status"],
            deep_dive_summary=row["deep_dive_summary"],
            worth_to_brief=bool(row["worth_to_brief"]),
            worth_reason=row["worth_reason"],
        )
        for row in rows
    ]


def list_intel_event_history_from_db(*, database_url: str) -> list[IntelEventHistoryItem]:
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        rows = session.execute(
            text("select * from intel_event_history order by recorded_at desc, id desc")
        ).mappings().all()
    return [
        IntelEventHistoryItem(
            history_id=row["id"],
            event_id=row["event_id"],
            title=row["title"],
            summary=row["summary"],
            representative_link=row["representative_link"],
            entity_ids=[],
            entity_names=[],
            discovered_at=_iso(row["recorded_at"]) or "",
            last_seen_at=_iso(row["recorded_at"]) or "",
            expires_at=_iso(row["recorded_at"]) or "",
            status="active",
            latest_alert_state=row["alert_state"],
            platform_count=int(row["platform_count"] or 0),
            source_count=int(row["source_count"] or 0),
            member_count=int(row["member_count"] or 0),
            member_delta=0,
            platform_delta=0,
            composite_score=float(row["composite_score"] or 0),
        )
        for row in rows
    ]


def list_intel_alert_history_from_db(*, database_url: str) -> list[IntelAlertHistoryItem]:
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        rows = session.execute(
            text("select * from intel_alert_history order by triggered_at desc, id desc")
        ).mappings().all()
    return [
        IntelAlertHistoryItem(
            history_id=row["id"],
            event_id=row["event_id"],
            title=row["title"],
            representative_link=row["representative_link"],
            entity_ids=[],
            entity_names=[],
            first_triggered_at=_iso(row["triggered_at"]) or "",
            last_triggered_at=_iso(row["triggered_at"]) or "",
            expires_at=_iso(row["triggered_at"]) or "",
            highest_level=row["highest_level"] or row["level"],
            latest_level=row["level"],
            status="active",
            reason=row["reason"],
            platform_count=0,
            source_count=0,
            velocity_score=float(row["velocity_score"] or 0),
            coverage_score=float(row["coverage_score"] or 0),
            freshness_score=float(row["freshness_score"] or 0),
            composite_score=float(row["composite_score"] or 0),
        )
        for row in rows
    ]


def get_intel_summary_from_db(*, database_url: str) -> IntelOverviewSummary:
    discovery_items, discovery_total = list_discovery_items_from_db(database_url=database_url, page=1, page_size=500)
    events, event_total = list_intel_events_from_db(database_url=database_url, page=1, page_size=500)
    alerts = list_intel_alerts_from_db(database_url=database_url)
    event_history = list_intel_event_history_from_db(database_url=database_url)
    alert_history = list_intel_alert_history_from_db(database_url=database_url)

    item_state_counts = Counter(item.item_state for item in discovery_items)
    event_state_counts = Counter(item.change_state for item in events)

    return IntelOverviewSummary(
        alert_count=len(alerts),
        breakout_count=len([item for item in alerts if item.level == "breakout"]),
        rising_count=len([item for item in alerts if item.level == "rising"]),
        watch_count=len([item for item in alerts if item.level == "watch"]),
        event_count=event_total,
        discovery_count=discovery_total,
        new_items_count=int(item_state_counts.get("new_item", 0)),
        seen_items_count=int(item_state_counts.get("seen_item", 0)),
        updated_items_count=int(item_state_counts.get("updated_item", 0)),
        new_events_count=int(event_state_counts.get("new_event", 0)),
        growing_events_count=int(event_state_counts.get("growing_event", 0)),
        stable_events_count=int(event_state_counts.get("stable_event", 0)),
        cooling_events_count=int(event_state_counts.get("cooling_event", 0)),
        warning_sources=0,
        error_sources=0,
        healthy_sources=0,
        total_sources=0,
        recent_alert_count_24h=len(alert_history),
        recent_event_count_24h=len(event_history),
        recent_breakout_count_24h=len([item for item in alert_history if item.highest_level == "breakout"]),
        recent_rising_count_24h=len([item for item in alert_history if item.highest_level == "rising"]),
        last_sync_at=now_iso(),
        next_run_at=None,
        running=False,
        work_scope="collect_events_alerts",
        top_alerts=alerts[:6],
        top_events=events[:8],
        recent_alerts_24h=alert_history,
        recent_events_24h=event_history,
        source_alerts=["数据库读对照模式下未投影来源健康摘要。"],
    )


def list_event_deep_dives_from_db(
    *, database_url: str, page: int = 1, page_size: int = 50
) -> tuple[list[dict[str, Any]], int]:
    """List deep-dives from PostgreSQL database.

    Returns raw dicts with sources joined from deep_dive_documents table.
    """
    session_factory = build_session_factory(database_url)
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 50), 200))
    start = (safe_page - 1) * safe_page_size

    with session_factory() as session:
        # Get deep_dive_records
        rows = session.execute(
            text(
                """
                select *
                from deep_dive_records
                order by updated_at desc, id desc
                limit :limit offset :offset
                """
            ),
            {"offset": start, "limit": safe_page_size},
        ).mappings().all()
        total = int(session.execute(text("select count(*) from deep_dive_records")).scalar_one())

        result = []
        for row in rows:
            deep_dive_id = row["id"]

            # Get source documents for this deep_dive
            doc_rows = session.execute(
                text(
                    """
                    select *
                    from deep_dive_documents
                    where deep_dive_id = :deep_dive_id
                    order by id
                    """
                ),
                {"deep_dive_id": deep_dive_id},
            ).mappings().all()

            sources = [
                {
                    "source_key": doc["source_key"],
                    "source_name": doc["source_name"],
                    "original_link": doc["original_link"],
                    "canonical_link": doc["canonical_link"],
                    "title": doc["title"],
                    "published_at": _iso(doc["published_at"]),
                    "fetch_status": normalize_fetch_status(doc["fetch_status"]),
                    "extract_status": normalize_extract_status(doc["extract_status"]),
                    "word_count": int(doc["word_count"] or 0),
                    "cleaned_full_text": doc["cleaned_full_text"],
                    "excerpt": doc["excerpt"],
                    "quotes": _json_list(doc["quotes_json"]),
                    "error": doc["error"],
                }
                for doc in doc_rows
            ]

            result.append(
                {
                    "id": row["id"],
                    "event_id": row["event_id"],
                    "status": row["status"],
                    "started_at": _iso(row["started_at"]),
                    "finished_at": _iso(row["finished_at"]),
                    "updated_at": _iso(row["updated_at"]) or "",
                    "attempted_count": int(row["attempted_count"] or 0),
                    "success_count": int(row["success_count"] or 0),
                    "failed_count": int(row["failed_count"] or 0),
                    "resolved_evidence_pack": _json_list(row["resolved_evidence_pack_json"]),
                    "full_text_sources": [],  # Deprecated field, kept for compatibility
                    "sources": sources,
                    "facts": _json_list(row["facts_json"]),
                    "quotes": _json_list(row["quotes_json"]),
                    "timeline": _json_list(row["timeline_json"]),
                    "worthiness": _json_dict(row["worthiness_json"]),
                    "last_error": row["last_error"],
                    "article_writing_guide": row["article_writing_guide"],
                }
            )

    return result, total


def get_deep_dive_from_db(*, database_url: str, deep_dive_id: str) -> dict[str, Any] | None:
    """Get a single deep_dive from PostgreSQL database."""
    session_factory = build_session_factory(database_url)

    with session_factory() as session:
        row = session.execute(
            text("select * from deep_dive_records where id = :deep_dive_id"),
            {"deep_dive_id": deep_dive_id},
        ).mappings().first()

        if not row:
            return None

        # Get source documents
        doc_rows = session.execute(
            text(
                """
                select *
                from deep_dive_documents
                where deep_dive_id = :deep_dive_id
                order by id
                """
            ),
            {"deep_dive_id": deep_dive_id},
        ).mappings().all()

        sources = [
            {
                "source_key": doc["source_key"],
                "source_name": doc["source_name"],
                "original_link": doc["original_link"],
                "canonical_link": doc["canonical_link"],
                "title": doc["title"],
                "published_at": _iso(doc["published_at"]),
                "fetch_status": normalize_fetch_status(doc["fetch_status"]),
                "extract_status": normalize_extract_status(doc["extract_status"]),
                "word_count": int(doc["word_count"] or 0),
                "cleaned_full_text": doc["cleaned_full_text"],
                "excerpt": doc["excerpt"],
                "quotes": _json_list(doc["quotes_json"]),
                "error": doc["error"],
            }
            for doc in doc_rows
        ]

        return {
            "id": row["id"],
            "event_id": row["event_id"],
            "status": row["status"],
            "started_at": _iso(row["started_at"]),
            "finished_at": _iso(row["finished_at"]),
            "updated_at": _iso(row["updated_at"]) or "",
            "attempted_count": int(row["attempted_count"] or 0),
            "success_count": int(row["success_count"] or 0),
            "failed_count": int(row["failed_count"] or 0),
            "resolved_evidence_pack": _json_list(row["resolved_evidence_pack_json"]),
            "full_text_sources": [],
            "sources": sources,
            "facts": _json_list(row["facts_json"]),
            "quotes": _json_list(row["quotes_json"]),
            "timeline": _json_list(row["timeline_json"]),
            "worthiness": _json_dict(row["worthiness_json"]),
            "last_error": row["last_error"],
            "article_writing_guide": row["article_writing_guide"],
        }


def get_deep_dive_by_event_id_from_db(*, database_url: str, event_id: str) -> dict[str, Any] | None:
    """Get a single deep_dive by event_id from PostgreSQL database."""
    session_factory = build_session_factory(database_url)

    with session_factory() as session:
        row = session.execute(
            text("select * from deep_dive_records where event_id = :event_id"),
            {"event_id": event_id},
        ).mappings().first()

        if not row:
            return None

        deep_dive_id = row["id"]

        # Get source documents
        doc_rows = session.execute(
            text(
                """
                select *
                from deep_dive_documents
                where deep_dive_id = :deep_dive_id
                order by id
                """
            ),
            {"deep_dive_id": deep_dive_id},
        ).mappings().all()

        sources = [
            {
                "source_key": doc["source_key"],
                "source_name": doc["source_name"],
                "original_link": doc["original_link"],
                "canonical_link": doc["canonical_link"],
                "title": doc["title"],
                "published_at": _iso(doc["published_at"]),
                "fetch_status": normalize_fetch_status(doc["fetch_status"]),
                "extract_status": normalize_extract_status(doc["extract_status"]),
                "word_count": int(doc["word_count"] or 0),
                "cleaned_full_text": doc["cleaned_full_text"],
                "excerpt": doc["excerpt"],
                "quotes": _json_list(doc["quotes_json"]),
                "error": doc["error"],
            }
            for doc in doc_rows
        ]

        return {
            "id": row["id"],
            "event_id": row["event_id"],
            "status": row["status"],
            "started_at": _iso(row["started_at"]),
            "finished_at": _iso(row["finished_at"]),
            "updated_at": _iso(row["updated_at"]) or "",
            "attempted_count": int(row["attempted_count"] or 0),
            "success_count": int(row["success_count"] or 0),
            "failed_count": int(row["failed_count"] or 0),
            "resolved_evidence_pack": _json_list(row["resolved_evidence_pack_json"]),
            "full_text_sources": [],
            "sources": sources,
            "facts": _json_list(row["facts_json"]),
            "quotes": _json_list(row["quotes_json"]),
            "timeline": _json_list(row["timeline_json"]),
            "worthiness": _json_dict(row["worthiness_json"]),
            "last_error": row["last_error"],
            "article_writing_guide": row["article_writing_guide"],
        }


def list_briefs_from_db(
    *, database_url: str, page: int = 1, page_size: int = 50
) -> tuple[list[dict[str, Any]], int]:
    """List briefs from PostgreSQL database."""
    session_factory = build_session_factory(database_url)
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 50), 200))
    start = (safe_page - 1) * safe_page_size

    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select *
                from brief_records
                order by updated_at desc, id desc
                limit :limit offset :offset
                """
            ),
            {"offset": start, "limit": safe_page_size},
        ).mappings().all()
        total = int(session.execute(text("select count(*) from brief_records")).scalar_one())

        result = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "event_id": row["event_id"],
                    "deep_dive_id": row["deep_dive_id"],
                    "brief_level": row["brief_level"],
                    "stage": row["stage"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "one_line": row["one_line"],
                    "why_it_matters": row["why_it_matters"],
                    "facts": _json_list(row["facts_json"]),
                    "quotes": _json_list(row["quotes_json"]),
                    "timeline": _json_list(row["timeline_json"]),
                    "entity_names": _json_list(row["entity_names_json"]),
                    "source_links": _json_list(row["source_links_json"]),
                    "risk_notes": _json_list(row["risk_notes_json"]),
                    "prompt_package_markdown": row["prompt_package_markdown"],
                    "douyin_prompt_package_markdown": row["douyin_prompt_package_markdown"],
                    "wechat_markdown": row["wechat_markdown"],
                    "wechat_html": row["wechat_html"],
                    "douyin_title": row["douyin_title"],
                    "douyin_summary": row["douyin_summary"],
                    "douyin_markdown": row["douyin_markdown"],
                    "wechat_target_id": row["wechat_target_id"],
                    "wechat_editor_url": row["wechat_editor_url"],
                    "wechat_remote_appmsg_id": row["wechat_remote_appmsg_id"],
                    "preview_url": row["preview_url"],
                    "delivery_status": row["delivery_status"],
                    "delivery_attempt_count": int(row["delivery_attempt_count"] or 0),
                    "last_delivery_attempt_at": _iso(row["last_delivery_attempt_at"]),
                    "last_verified_at": _iso(row["last_verified_at"]),
                    "last_delivery_error_kind": row["last_delivery_error_kind"],
                    "needs_resync": bool(row["needs_resync"]),
                    "last_synced_revision": row["last_synced_revision"],
                    "last_successful_upload_at": _iso(row["last_successful_upload_at"]),
                    "last_error": row["last_error"],
                    "updated_at": _iso(row["updated_at"]) or "",
                    "driver_label": row["driver_label"],
                    "record_status": row["record_status"],
                    "record_exception": None,
                    "draft_remote_updated_at": _iso(row["draft_remote_updated_at"]),
                    "publish_record_published_at": _iso(row["publish_record_published_at"]),
                    "workflow_mode": row["workflow_mode"],
                    "workflow_session_id": row["workflow_session_id"],
                    "read_count": int(row["read_count"] or 0),
                    "like_count": int(row["like_count"] or 0),
                    "share_count": int(row["share_count"] or 0),
                    "recommend_count": int(row["recommend_count"] or 0),
                    "comment_count": int(row["comment_count"] or 0),
                    "highlight_count": int(row["highlight_count"] or 0),
                    "tip_amount": row["tip_amount"],
                    "reprint_count": int(row["reprint_count"] or 0),
                    "metrics_fetched_at": _iso(row["metrics_fetched_at"]),
                }
            )

    return result, total


def get_brief_from_db(*, database_url: str, brief_id: str) -> dict[str, Any] | None:
    """Get a single brief from PostgreSQL database."""
    session_factory = build_session_factory(database_url)

    with session_factory() as session:
        row = session.execute(
            text("select * from brief_records where id = :brief_id"),
            {"brief_id": brief_id},
        ).mappings().first()

        if not row:
            return None

        return {
            "id": row["id"],
            "event_id": row["event_id"],
            "deep_dive_id": row["deep_dive_id"],
            "brief_level": row["brief_level"],
            "stage": row["stage"],
            "title": row["title"],
            "summary": row["summary"],
            "one_line": row["one_line"],
            "why_it_matters": row["why_it_matters"],
            "facts": _json_list(row["facts_json"]),
            "quotes": _json_list(row["quotes_json"]),
            "timeline": _json_list(row["timeline_json"]),
            "entity_names": _json_list(row["entity_names_json"]),
            "source_links": _json_list(row["source_links_json"]),
            "risk_notes": _json_list(row["risk_notes_json"]),
            "prompt_package_markdown": row["prompt_package_markdown"],
            "douyin_prompt_package_markdown": row["douyin_prompt_package_markdown"],
            "wechat_markdown": row["wechat_markdown"],
            "wechat_html": row["wechat_html"],
            "douyin_title": row["douyin_title"],
            "douyin_summary": row["douyin_summary"],
            "douyin_markdown": row["douyin_markdown"],
            "wechat_target_id": row["wechat_target_id"],
            "wechat_editor_url": row["wechat_editor_url"],
            "wechat_remote_appmsg_id": row["wechat_remote_appmsg_id"],
            "preview_url": row["preview_url"],
            "delivery_status": row["delivery_status"],
            "delivery_attempt_count": int(row["delivery_attempt_count"] or 0),
            "last_delivery_attempt_at": _iso(row["last_delivery_attempt_at"]),
            "last_verified_at": _iso(row["last_verified_at"]),
            "last_delivery_error_kind": row["last_delivery_error_kind"],
            "needs_resync": bool(row["needs_resync"]),
            "last_synced_revision": row["last_synced_revision"],
            "last_successful_upload_at": _iso(row["last_successful_upload_at"]),
            "last_error": row["last_error"],
            "updated_at": _iso(row["updated_at"]) or "",
            "driver_label": row["driver_label"],
            "record_status": row["record_status"],
            "record_exception": None,
            "draft_remote_updated_at": _iso(row["draft_remote_updated_at"]),
            "publish_record_published_at": _iso(row["publish_record_published_at"]),
            "workflow_mode": row["workflow_mode"],
            "workflow_session_id": row["workflow_session_id"],
            "read_count": int(row["read_count"] or 0),
            "like_count": int(row["like_count"] or 0),
            "share_count": int(row["share_count"] or 0),
            "recommend_count": int(row["recommend_count"] or 0),
            "comment_count": int(row["comment_count"] or 0),
            "highlight_count": int(row["highlight_count"] or 0),
            "tip_amount": row["tip_amount"],
            "reprint_count": int(row["reprint_count"] or 0),
            "metrics_fetched_at": _iso(row["metrics_fetched_at"]),
        }


# =============================================================================
# Analysis Query Functions (Phase 3)
# =============================================================================


def get_raw_items_for_analysis(
    *,
    database_url: str,
    hours: int = 24,
    source_keys: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Get raw_items for analysis within a time window.

    Unlike the fixed 480-item window in JSON, this queries by time range.

    Args:
        database_url: Database connection string
        hours: Time window in hours (default: 24)
        source_keys: Optional list of source keys to filter

    Returns:
        List of raw_item dicts
    """
    from datetime import datetime, timedelta, timezone

    session_factory = build_session_factory(database_url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    with session_factory() as session:
        if source_keys:
            rows = session.execute(
                text(
                    """
                    select *
                    from raw_items
                    where collected_at >= :cutoff
                    and source_key = any(:source_keys)
                    order by collected_at desc
                    """
                ),
                {"cutoff": cutoff, "source_keys": source_keys},
            ).mappings().all()
        else:
            rows = session.execute(
                text(
                    """
                    select *
                    from raw_items
                    where collected_at >= :cutoff
                    order by collected_at desc
                    """
                ),
                {"cutoff": cutoff},
            ).mappings().all()

        return [
            {
                "id": row["id"],
                "source_key": row["source_key"],
                "title": row["title"],
                "summary": row["summary"],
                "content": row["content"],
                "link": row["link"],
                "canonical_link": row["canonical_link"],
                "dedupe_key": row["dedupe_key"],
                "source_native_id": row["source_native_id"],
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "collected_at": row["collected_at"].isoformat(),
                "score": float(row["score"] or 0),
                "tags": _json_list(row["tags_json"]),
                "metadata": _json_dict(row["metadata_json"]),
            }
            for row in rows
        ]


def get_event_snapshots_for_analysis(
    *,
    database_url: str,
    event_ids: list[str] | None = None,
    hours: int = 48,
) -> dict[str, list[dict[str, Any]]]:
    """Get event snapshots for trend calculation.

    Returns snapshots grouped by event_id for velocity/trend analysis.

    Args:
        database_url: Database connection string
        event_ids: Optional list of event IDs to filter
        hours: Time window in hours (default: 48)

    Returns:
        Dict mapping event_id -> list of snapshot dicts
    """
    from datetime import datetime, timedelta, timezone

    session_factory = build_session_factory(database_url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    with session_factory() as session:
        if event_ids:
            rows = session.execute(
                text(
                    """
                    select *
                    from event_snapshots
                    where captured_at >= :cutoff
                    and event_id = any(:event_ids)
                    order by event_id, captured_at
                    """
                ),
                {"cutoff": cutoff, "event_ids": event_ids},
            ).mappings().all()
        else:
            rows = session.execute(
                text(
                    """
                    select *
                    from event_snapshots
                    where captured_at >= :cutoff
                    order by event_id, captured_at
                    """
                ),
                {"cutoff": cutoff},
            ).mappings().all()

        # Group by event_id
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            event_id = row["event_id"]
            if event_id not in result:
                result[event_id] = []
            result[event_id].append(
                {
                    "id": row["id"],
                    "event_id": event_id,
                    "captured_at": row["captured_at"].isoformat(),
                    "member_count": int(row["member_count"] or 0),
                    "platform_count": int(row["platform_count"] or 0),
                    "source_count": int(row["source_count"] or 0),
                    "velocity_score": float(row["velocity_score"] or 0),
                    "coverage_score": float(row["coverage_score"] or 0),
                    "freshness_score": float(row["freshness_score"] or 0),
                    "audience_fit_score": float(row["audience_fit_score"] or 0),
                    "composite_score": float(row["composite_score"] or 0),
                    "alert_state": row["alert_state"],
                }
            )

        return result


def get_discovery_items_for_clustering(
    *,
    database_url: str,
    hours: int = 24,
) -> list[dict[str, Any]]:
    """Get discovery_items for clustering analysis.

    Returns items with token fields for Jaccard similarity calculation.

    Args:
        database_url: Database connection string
        hours: Time window in hours (default: 24)

    Returns:
        List of discovery_item dicts with title_tokens and anchor_tokens
    """
    from datetime import datetime, timedelta, timezone

    session_factory = build_session_factory(database_url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select *
                from discovery_items_current
                where collected_at >= :cutoff
                order by collected_at desc
                """
            ),
            {"cutoff": cutoff},
        ).mappings().all()

        return [
            {
                "id": row["id"],
                "raw_item_id": row["raw_item_id"],
                "source_key": row["source_key"],
                "source_name": row["source_name"],
                "source_kind": row["source_kind"],
                "platform": row["platform"],
                "title": row["title"],
                "summary": row["summary"],
                "content": row["content"],
                "link": row["link"],
                "canonical_link": row["canonical_link"],
                "dedupe_key": row["dedupe_key"],
                "source_native_id": row["source_native_id"],
                "title_tokens": _json_list(row["title_tokens_json"]),
                "anchor_tokens": _json_list(row["anchor_tokens_json"]),
                "published_at": row["published_at"].isoformat() if row["published_at"] else None,
                "collected_at": row["collected_at"].isoformat(),
                "tags": _json_list(row["tags_json"]),
                "engagement_score": float(row["engagement_score"] or 0),
                "item_state": row["item_state"],
                "entity_ids": _json_list(row["entity_ids_json"]),
                "entity_names": _json_list(row["entity_names_json"]),
                "metadata": _json_dict(row["metadata_json"]),
            }
            for row in rows
        ]
