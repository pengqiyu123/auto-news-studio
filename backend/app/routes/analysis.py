from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..db import current_database_url, database_read_is_truth, database_write_enabled
from ..db.models import AnalysisFeedbackRecord, AnalysisReportRecord
from ..db.session import build_session_factory
from ..features.analysis.report_generator import generate_analysis_report, generate_weekly_digest
from ..intel.correlation import build_event_relations
from ..intel.periodicity import detect_topic_periodicity
from ..intel.temporal_rules import mine_temporal_association_rules
from ..intel.topics import build_topic_model
from ..intel.trends import aggregate_daily_metrics, detect_trends
from ..models import (
    AnalysisBatchRunInfo,
    AnalysisBatchStatusResponse,
    AnalysisFeedbackPayload,
    AnalysisFeedbackResponse,
    AnalysisFeedbackStatsResponse,
    AnalysisReportItem,
    AnalysisReportRequest,
    AnalysisReportResponse,
    AnalysisReportSections,
    AnalysisReportsResponse,
    AnalysisReportSummary,
    AnalysisSignalInfo,
    AnalysisSignalsResponse,
    AnalysisTopicEventInfo,
    AnalysisTopicEventsResponse,
    EventRelationInfo,
    EventRelationsResponse,
    TemporalRuleInfo,
    TemporalRulesResponse,
    TopicPeriodicityInfo,
    TopicPeriodicityResponse,
    TopicsResponse,
    TrendSignalInfo,
    TrendSignalsResponse,
)
from ..store.base import now_iso, parse_time
from .common import get_store


def _events_from_store() -> list[dict[str, Any]]:
    items, _total = get_store().list_intel_events(page=1, page_size=200, ignore_mode="visible", sort_by="latest_seen")
    return [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in items]


def _snapshots_from_store() -> list[dict[str, Any]]:
    store = get_store()
    state = store._upgrade_state(store._read())  # analysis is read-only; keep store protocol untouched.
    return [item for item in state.get("event_snapshots", []) if isinstance(item, dict)]


def _latest_event_sort_key(event: dict[str, Any]) -> float:
    latest = parse_time(event.get("last_seen_at") or event.get("latest_collected_at") or event.get("first_seen_at"))
    if not latest:
        return 0.0
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    return latest.timestamp()


def _topic_events_from_projection(topic_id: str) -> list[AnalysisTopicEventInfo]:
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select
                    events.id as event_id,
                    events.title as title,
                    events.composite_score as composite_score,
                    events.first_seen_at as first_seen_at
                from event_topics topics
                join intel_events_current events on events.id = topics.event_id
                where topics.topic_id = :topic_id and coalesce(events.ignored, false) = false
                order by topics.weight desc, events.composite_score desc
                limit 50
                """
            ),
            {"topic_id": topic_id},
        ).mappings().all()
    return [
        AnalysisTopicEventInfo(
            event_id=str(row["event_id"] or ""),
            title=str(row["title"] or ""),
            composite_score=float(row["composite_score"] or 0),
            first_seen_at=row["first_seen_at"].isoformat() if hasattr(row["first_seen_at"], "isoformat") else row["first_seen_at"],
        )
        for row in rows
    ]


def _topic_events_from_memory(topic_id: str) -> list[AnalysisTopicEventInfo]:
    events = _events_from_store()
    topics = build_topic_model(events)
    event_ids = {
        item.event_id
        for item in topics.event_topics
        if item.topic_id == topic_id
    }
    by_id = {str(event.get("id") or ""): event for event in events}
    items: list[AnalysisTopicEventInfo] = []
    for event_id in event_ids:
        event = by_id.get(event_id)
        if not event or bool(event.get("ignored")):
            continue
        items.append(
            AnalysisTopicEventInfo(
                event_id=event_id,
                title=str(event.get("title") or ""),
                composite_score=float(event.get("composite_score") or 0),
                first_seen_at=str(event.get("first_seen_at") or "") or None,
            )
        )
    return sorted(items, key=lambda item: item.composite_score, reverse=True)[:50]


def _topic_periodicity_from_memory() -> list[TopicPeriodicityInfo]:
    events = _events_from_store()
    topics = build_topic_model(events)
    return [TopicPeriodicityInfo(**item.__dict__) for item in detect_topic_periodicity(events, topics)]


def _topic_periodicity_from_db() -> list[TopicPeriodicityInfo]:
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select topic_id, label, period_days, confidence, detected_at
                from topic_periodicity
                order by confidence desc, period_days asc
                limit 50
                """
            )
        ).mappings().all()
    return [
        TopicPeriodicityInfo(
            topic_id=str(row["topic_id"] or ""),
            label=str(row["label"] or ""),
            period_days=int(row["period_days"] or 0),
            confidence=float(row["confidence"] or 0),
            detected_at=row["detected_at"].isoformat() if hasattr(row["detected_at"], "isoformat") else str(row["detected_at"] or ""),
        )
        for row in rows
    ]


def _temporal_rules_from_memory() -> list[TemporalRuleInfo]:
    events = _events_from_store()
    topics = build_topic_model(events)
    relations = build_event_relations(events, topics.event_topics)
    return [TemporalRuleInfo(**item.__dict__) for item in mine_temporal_association_rules(events, relations)[:5]]


def _temporal_rules_from_db() -> list[TemporalRuleInfo]:
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select
                    rules.id as id,
                    rules.antecedent_event_id as antecedent_event_id,
                    rules.consequent_event_id as consequent_event_id,
                    rules.lag_days as lag_days,
                    rules.support as support,
                    rules.confidence as confidence,
                    rules.lift as lift,
                    antecedent.title as antecedent_title,
                    consequent.title as consequent_title
                from temporal_association_rules rules
                left join intel_events_current antecedent on antecedent.id = rules.antecedent_event_id
                left join intel_events_current consequent on consequent.id = rules.consequent_event_id
                order by rules.confidence desc, rules.support desc, rules.lift desc
                limit 5
                """
            )
        ).mappings().all()
    return [
        TemporalRuleInfo(
            id=str(row["id"] or ""),
            antecedent_event_id=str(row["antecedent_event_id"] or ""),
            consequent_event_id=str(row["consequent_event_id"] or ""),
            antecedent_title=str(row["antecedent_title"] or ""),
            consequent_title=str(row["consequent_title"] or ""),
            lag_days=int(row["lag_days"] or 0),
            support=float(row["support"] or 0),
            confidence=float(row["confidence"] or 0),
            lift=float(row["lift"] or 0),
        )
        for row in rows
    ]


def _analysis_signals_from_events(events: list[dict[str, Any]]) -> list[AnalysisSignalInfo]:
    metrics = aggregate_daily_metrics(events, _snapshots_from_store())
    trends = detect_trends(metrics, as_of=datetime.now(UTC).date())
    visible_events = [event for event in events if not bool(event.get("ignored"))]
    signals: list[AnalysisSignalInfo] = []
    for trend in trends:
        matching_events = [
            event
            for event in visible_events
            if trend.entity_id in {str(item or "").strip() for item in (event.get("entity_ids") or [])}
        ]
        matching_events.sort(key=_latest_event_sort_key, reverse=True)
        latest_event = matching_events[0] if matching_events else {}
        signals.append(
            AnalysisSignalInfo(
                entity_id=trend.entity_id,
                entity_name=trend.entity_name,
                trend=trend.trend,
                trend_label=trend.trend_label,
                sma_7d=trend.sma_7d,
                sma_14d=trend.sma_14d,
                recent_event_count=len(matching_events),
                latest_event_title=str(latest_event.get("title") or ""),
                latest_event_id=str(latest_event.get("id") or ""),
            )
        )
    signals.sort(
        key=lambda item: (
            item.trend == "insufficient_data",
            -item.recent_event_count,
            -item.sma_7d,
            item.entity_name,
        )
    )
    return signals


def _safe_iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _topic_rows_from_db() -> list[dict[str, Any]]:
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select topic_id, label, keywords_json, event_count
                from topic_models
                order by event_count desc, updated_at desc
                limit 50
                """
            )
        ).mappings().all()
    return [
        {
            "topic_id": str(row["topic_id"] or ""),
            "label": str(row["label"] or ""),
            "keywords": list(row["keywords_json"] or []),
            "event_count": int(row["event_count"] or 0),
        }
        for row in rows
    ]


def _entity_name_lookup(events: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for event in events:
        ids = event.get("entity_ids") if isinstance(event.get("entity_ids"), list) else []
        names = event.get("entity_names") if isinstance(event.get("entity_names"), list) else []
        for index, entity_id in enumerate(ids):
            normalized_id = str(entity_id or "").strip()
            if not normalized_id:
                continue
            name = str(names[index] if index < len(names) else normalized_id).strip() or normalized_id
            lookup.setdefault(normalized_id, name)
    return lookup


def _trend_label(signal_type: str) -> str:
    labels = {
        "hot": "近7天持续上升",
        "warm": "近7天走势平稳",
        "cool": "近7天热度回落",
        "cold": "近7天暂无新事件",
        "emerging": "近3天明显升温",
        "insufficient_data": "数据不足，暂不判断趋势",
    }
    return labels.get(signal_type, signal_type or "趋势信号")


def _trend_rows_from_db(events: list[dict[str, Any]] | None = None) -> list[TrendSignalInfo]:
    events = events if events is not None else _events_from_store()
    names = _entity_name_lookup(events)
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select entity_id, signal_type, signal_value, confidence, detected_at
                from trend_signals
                order by detected_at desc, signal_value desc
                limit 80
                """
            )
        ).mappings().all()
    return [
        TrendSignalInfo(
            entity_id=str(row["entity_id"] or ""),
            entity_name=names.get(str(row["entity_id"] or ""), str(row["entity_id"] or "")),
            trend=str(row["signal_type"] or ""),
            trend_label=_trend_label(str(row["signal_type"] or "")),
            sma_7d=float(row["signal_value"] or 0),
            sma_14d=0.0,
            signals=[
                {
                    "type": str(row["signal_type"] or ""),
                    "confidence": float(row["confidence"] or 0),
                    "detected_at": _safe_iso(row["detected_at"]),
                }
            ],
        )
        for row in rows
    ]


def _analysis_signals_from_cached_trends(events: list[dict[str, Any]]) -> list[AnalysisSignalInfo]:
    trend_rows = _trend_rows_from_db(events)
    if not trend_rows:
        return []
    visible_events = [event for event in events if not bool(event.get("ignored"))]
    signals: list[AnalysisSignalInfo] = []
    for trend in trend_rows:
        matching_events = [
            event
            for event in visible_events
            if trend.entity_id in {str(item or "").strip() for item in (event.get("entity_ids") or [])}
        ]
        matching_events.sort(key=_latest_event_sort_key, reverse=True)
        latest_event = matching_events[0] if matching_events else {}
        signals.append(
            AnalysisSignalInfo(
                entity_id=trend.entity_id,
                entity_name=trend.entity_name,
                trend=trend.trend,
                trend_label=trend.trend_label,
                sma_7d=trend.sma_7d,
                sma_14d=trend.sma_14d,
                recent_event_count=len(matching_events),
                latest_event_title=str(latest_event.get("title") or ""),
                latest_event_id=str(latest_event.get("id") or ""),
            )
        )
    signals.sort(key=lambda item: (-item.recent_event_count, -item.sma_7d, item.entity_name))
    return signals


def _batch_runs_from_db(limit: int = 10) -> list[AnalysisBatchRunInfo]:
    safe_limit = max(1, min(int(limit or 10), 50))
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select id, task_name, status, started_at, finished_at, items_processed, error_message
                from analysis_batch_runs
                order by started_at desc
                limit :limit
                """
            ),
            {"limit": safe_limit},
        ).mappings().all()
    return [
        AnalysisBatchRunInfo(
            id=str(row["id"] or ""),
            task_name=str(row["task_name"] or ""),
            status=str(row["status"] or "running"),
            started_at=_safe_iso(row["started_at"]),
            finished_at=_safe_iso(row["finished_at"]) or None,
            items_processed=int(row["items_processed"] or 0),
            error_message=str(row["error_message"] or ""),
        )
        for row in rows
    ]


def _store_feedback_json(feedback_id: str, payload: AnalysisFeedbackPayload) -> None:
    store = get_store()
    state = store._upgrade_state(store._read())
    state.setdefault("analysis_feedback", []).insert(
        0,
        {
            "id": feedback_id,
            "target_type": payload.target_type,
            "target_id": payload.target_id,
            "feedback_type": payload.feedback_type,
            "correction": payload.correction or {},
            "created_at": now_iso(),
        },
    )
    store._write(state)


def _store_feedback_db(feedback_id: str, payload: AnalysisFeedbackPayload) -> None:
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        session.add(
            AnalysisFeedbackRecord(
                id=feedback_id,
                target_type=payload.target_type,
                target_id=payload.target_id,
                feedback_type=payload.feedback_type,
                correction_json=payload.correction or {},
                created_at=datetime.now(UTC),
            )
        )
        session.commit()


def _parse_report_date(value: str, field_name: str) -> date:
    text_value = str(value or "").strip()
    try:
        return date.fromisoformat(text_value[:10])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} 必须是 YYYY-MM-DD 日期") from exc


def _report_preview(markdown: str) -> str:
    compact = " ".join(str(markdown or "").replace("#", " ").split())
    return compact[:120]


def _report_from_record(record: AnalysisReportRecord) -> AnalysisReportItem:
    return AnalysisReportItem(
        report_id=record.id,
        scope=record.report_type,
        period_start=record.period_start.isoformat(),
        period_end=record.period_end.isoformat(),
        status=record.status,
        markdown=record.content_markdown,
        sections=AnalysisReportSections(**(record.sections_json or {})),
        created_at=record.created_at.isoformat() if record.created_at else "",
    )


def _report_from_state(item: dict[str, Any]) -> AnalysisReportItem:
    return AnalysisReportItem(
        report_id=str(item.get("id") or item.get("report_id") or ""),
        scope=str(item.get("report_type") or item.get("scope") or "daily"),
        period_start=str(item.get("period_start") or ""),
        period_end=str(item.get("period_end") or ""),
        status=str(item.get("status") or "ready"),
        markdown=str(item.get("content_markdown") or item.get("markdown") or ""),
        sections=AnalysisReportSections(**(item.get("sections") or item.get("sections_json") or {})),
        created_at=str(item.get("created_at") or ""),
    )


def _summary_from_report(item: AnalysisReportItem) -> AnalysisReportSummary:
    return AnalysisReportSummary(
        report_id=item.report_id,
        scope=item.scope,
        period_start=item.period_start,
        period_end=item.period_end,
        status=item.status,
        preview=_report_preview(item.markdown),
        created_at=item.created_at,
    )


def _store_report_json(report: AnalysisReportItem) -> None:
    store = get_store()
    state = store._upgrade_state(store._read())
    reports = state.setdefault("analysis_reports", [])
    reports.insert(
        0,
        {
            "id": report.report_id,
            "report_type": report.scope,
            "period_start": report.period_start,
            "period_end": report.period_end,
            "status": report.status,
            "content_markdown": report.markdown,
            "sections": report.sections.model_dump(),
            "metadata": {},
            "created_at": report.created_at or now_iso(),
        },
    )
    state["analysis_reports"] = reports[:80]
    store._write(state)


def _store_report_db(report: AnalysisReportItem) -> None:
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        session.add(
            AnalysisReportRecord(
                id=report.report_id,
                report_type=report.scope,
                period_start=_parse_report_date(report.period_start, "period_start"),
                period_end=_parse_report_date(report.period_end, "period_end"),
                status=report.status,
                content_markdown=report.markdown,
                sections_json=report.sections.model_dump(),
                metadata_json={},
                created_at=parse_time(report.created_at) or datetime.now(UTC),
            )
        )
        session.commit()


def _list_reports_db(limit: int = 20) -> list[AnalysisReportSummary]:
    safe_limit = max(1, min(int(limit or 20), 100))
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        records = (
            session.query(AnalysisReportRecord)
            .order_by(AnalysisReportRecord.created_at.desc())
            .limit(safe_limit)
            .all()
        )
    return [_summary_from_report(_report_from_record(record)) for record in records]


def _get_report_db(report_id: str) -> AnalysisReportItem | None:
    session_factory = build_session_factory(current_database_url())
    with session_factory() as session:
        record = session.get(AnalysisReportRecord, report_id)
    return _report_from_record(record) if record else None


def _list_reports_json(limit: int = 20) -> list[AnalysisReportSummary]:
    safe_limit = max(1, min(int(limit or 20), 100))
    state = get_store()._upgrade_state(get_store()._read())
    reports = [_report_from_state(item) for item in state.get("analysis_reports", []) if isinstance(item, dict)]
    reports.sort(key=lambda item: item.created_at, reverse=True)
    return [_summary_from_report(item) for item in reports[:safe_limit]]


def _get_report_json(report_id: str) -> AnalysisReportItem | None:
    state = get_store()._upgrade_state(get_store()._read())
    for item in state.get("analysis_reports", []):
        if isinstance(item, dict) and str(item.get("id") or item.get("report_id") or "") == report_id:
            return _report_from_state(item)
    return None


def _feedback_stats_json() -> AnalysisFeedbackStatsResponse:
    state = get_store()._upgrade_state(get_store()._read())
    by_type = {"confirm": 0, "correct": 0, "dismiss": 0}
    for item in state.get("analysis_feedback", []):
        if not isinstance(item, dict):
            continue
        feedback_type = str(item.get("feedback_type") or "")
        if feedback_type in by_type:
            by_type[feedback_type] += 1
    total = sum(by_type.values())
    return AnalysisFeedbackStatsResponse(
        total=total,
        accurate_pct=(by_type["confirm"] / total if total else 0.0),
        by_type=by_type,
    )


def _feedback_stats_db() -> AnalysisFeedbackStatsResponse:
    session_factory = build_session_factory(current_database_url())
    by_type = {"confirm": 0, "correct": 0, "dismiss": 0}
    with session_factory() as session:
        rows = session.execute(
            text(
                """
                select feedback_type, count(*) as count
                from analysis_feedback
                group by feedback_type
                """
            )
        ).mappings().all()
    for row in rows:
        feedback_type = str(row["feedback_type"] or "")
        if feedback_type in by_type:
            by_type[feedback_type] = int(row["count"] or 0)
    total = sum(by_type.values())
    return AnalysisFeedbackStatsResponse(
        total=total,
        accurate_pct=(by_type["confirm"] / total if total else 0.0),
        by_type=by_type,
    )


def build_analysis_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/topics", response_model=TopicsResponse)
    def list_topics():
        if database_write_enabled():
            cached_topics = _topic_rows_from_db()
            if cached_topics:
                return TopicsResponse(items=cached_topics)
        result = build_topic_model(_events_from_store())
        return TopicsResponse(items=[item.__dict__ for item in result.topics])

    @router.get("/api/admin/events/{event_id}/related", response_model=EventRelationsResponse)
    def get_related_events(event_id: str):
        events = _events_from_store()
        event_by_id = {str(item.get("id")): item for item in events}
        topics = build_topic_model(events)
        relations = build_event_relations(events, topics.event_topics)
        items: list[EventRelationInfo] = []
        for relation in relations:
            if relation.source_event_id == event_id:
                related_id = relation.target_event_id
            elif relation.target_event_id == event_id:
                related_id = relation.source_event_id
            else:
                continue
            related = event_by_id.get(related_id, {})
            items.append(
                EventRelationInfo(
                    event_id=related_id,
                    title=str(related.get("title") or ""),
                    relation_type=relation.relation_type,
                    weight=relation.weight,
                    evidence=relation.evidence,
                )
            )
        return EventRelationsResponse(items=items)

    @router.get("/api/admin/trends", response_model=TrendSignalsResponse)
    def list_trends():
        events = _events_from_store()
        if database_write_enabled():
            cached_trends = _trend_rows_from_db(events)
            if cached_trends:
                return TrendSignalsResponse(items=cached_trends)
        metrics = aggregate_daily_metrics(events, _snapshots_from_store())
        trends = detect_trends(metrics, as_of=datetime.now(UTC).date())
        return TrendSignalsResponse(items=[item.__dict__ for item in trends])

    @router.get("/api/admin/topics/{topic_id}/events", response_model=AnalysisTopicEventsResponse)
    def list_topic_events(topic_id: str):
        if database_read_is_truth():
            return AnalysisTopicEventsResponse(items=_topic_events_from_projection(topic_id))
        return AnalysisTopicEventsResponse(items=_topic_events_from_memory(topic_id))

    @router.get("/api/admin/topics/periodicity", response_model=TopicPeriodicityResponse)
    def list_topic_periodicity():
        if database_read_is_truth():
            return TopicPeriodicityResponse(items=_topic_periodicity_from_db())
        return TopicPeriodicityResponse(items=_topic_periodicity_from_memory())

    @router.get("/api/admin/analysis/temporal-rules", response_model=TemporalRulesResponse)
    def list_temporal_rules():
        if database_read_is_truth():
            return TemporalRulesResponse(items=_temporal_rules_from_db())
        return TemporalRulesResponse(items=_temporal_rules_from_memory())

    @router.get("/api/admin/analysis/signals", response_model=AnalysisSignalsResponse)
    def list_analysis_signals():
        events = _events_from_store()
        if database_write_enabled():
            cached_signals = _analysis_signals_from_cached_trends(events)
            if cached_signals:
                return AnalysisSignalsResponse(items=cached_signals)
        return AnalysisSignalsResponse(items=_analysis_signals_from_events(events))

    @router.get("/api/admin/analysis/batch-status", response_model=AnalysisBatchStatusResponse)
    def list_analysis_batch_status():
        if database_write_enabled():
            return AnalysisBatchStatusResponse(items=_batch_runs_from_db(limit=10))
        return AnalysisBatchStatusResponse(items=[])

    @router.post("/api/admin/analysis/feedback", response_model=AnalysisFeedbackResponse)
    def submit_analysis_feedback(payload: AnalysisFeedbackPayload):
        feedback_id = f"feedback-{uuid4().hex[:12]}"
        if database_write_enabled():
            _store_feedback_db(feedback_id, payload)
        else:
            _store_feedback_json(feedback_id, payload)
        return AnalysisFeedbackResponse(ok=True, feedback_id=feedback_id)

    @router.post("/api/admin/analysis/report", response_model=AnalysisReportResponse)
    def create_analysis_report(payload: AnalysisReportRequest):
        _parse_report_date(payload.date_from, "date_from")
        _parse_report_date(payload.date_to, "date_to")
        events = _events_from_store()
        topics = [item.__dict__ for item in build_topic_model(events).topics]
        signals = [item.model_dump() for item in _analysis_signals_from_events(events)]
        store = get_store()
        state = store._upgrade_state(store._read())
        llm_service = store._make_llm_service(state) if hasattr(store, "_make_llm_service") else None
        report_id = f"report-{uuid4().hex[:12]}"
        if payload.scope == "weekly":
            temporal_rules = [item.model_dump() for item in _temporal_rules_from_db()] if database_read_is_truth() else [
                item.model_dump() for item in _temporal_rules_from_memory()
            ]
            report = generate_weekly_digest(
                payload,
                events=events,
                topics=topics,
                signals=signals,
                temporal_rules=temporal_rules,
                llm_service=llm_service,
                report_id=report_id,
            )
        else:
            report = generate_analysis_report(
                payload,
                events=events,
                topics=topics,
                signals=signals,
                llm_service=llm_service,
                report_id=report_id,
            )
        if database_write_enabled():
            _store_report_db(report)
        else:
            _store_report_json(report)
        return AnalysisReportResponse(item=report)

    @router.get("/api/admin/analysis/reports", response_model=AnalysisReportsResponse)
    def list_analysis_reports(limit: int = 20):
        if database_read_is_truth():
            return AnalysisReportsResponse(items=_list_reports_db(limit))
        return AnalysisReportsResponse(items=_list_reports_json(limit))

    @router.get("/api/admin/analysis/reports/{report_id}", response_model=AnalysisReportResponse)
    def get_analysis_report(report_id: str):
        report = _get_report_db(report_id) if database_read_is_truth() else _get_report_json(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        return AnalysisReportResponse(item=report)

    @router.get("/api/admin/analysis/feedback/stats", response_model=AnalysisFeedbackStatsResponse)
    def get_analysis_feedback_stats():
        if database_read_is_truth():
            return _feedback_stats_db()
        return _feedback_stats_json()

    return router
