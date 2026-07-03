from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from ..intel.correlation import EventRelationInfo, build_event_relations
from ..intel.periodicity import detect_topic_periodicity
from ..intel.temporal_rules import mine_temporal_association_rules
from ..intel.topics import EventTopic, TopicInfo, TopicModelResult, build_topic_model
from ..intel.trends import aggregate_daily_metrics, detect_trends
from .models import (
    DailyEventMetricRecord,
    EventRelationRecord,
    EventTopicRecord,
    TemporalAssociationRuleRecord,
    TopicModelRecord,
    TopicPeriodicityRecord,
    TrendSignalRecord,
)
from .session import build_session_factory


def _now() -> datetime:
    return datetime.now(UTC)


def _topic_records(topics: TopicModelResult, now: datetime) -> list[TopicModelRecord]:
    return [
        TopicModelRecord(
            topic_id=topic.topic_id,
            keywords_json=topic.keywords,
            label=topic.label,
            event_count=topic.event_count,
            created_at=now,
            updated_at=now,
        )
        for topic in topics.topics
    ]


def _event_topic_records(topics: TopicModelResult) -> list[EventTopicRecord]:
    return [
        EventTopicRecord(event_id=item.event_id, topic_id=item.topic_id, weight=item.weight)
        for item in topics.event_topics
    ]


def _load_event_topics(session) -> list[EventTopic]:
    records = session.query(EventTopicRecord).all()
    return [
        EventTopic(event_id=str(record.event_id), topic_id=str(record.topic_id), weight=float(record.weight or 0))
        for record in records
    ]


def _load_topic_model_result(session) -> TopicModelResult:
    topic_records = session.query(TopicModelRecord).all()
    event_topics = _load_event_topics(session)
    return TopicModelResult(
        topics=[
            TopicInfo(
                topic_id=str(record.topic_id),
                label=str(record.label or ""),
                keywords=list(record.keywords_json or []),
                event_count=int(record.event_count or 0),
            )
            for record in topic_records
        ],
        event_topics=event_topics,
    )


def _load_event_relations(session) -> list[EventRelationInfo]:
    records = session.query(EventRelationRecord).all()
    return [
        EventRelationInfo(
            id=str(record.id),
            source_event_id=str(record.source_event_id),
            target_event_id=str(record.target_event_id),
            relation_type=str(record.relation_type or ""),
            weight=float(record.weight or 0),
            evidence=dict(record.evidence_json or {}),
        )
        for record in records
    ]


def precompute_topic_model(events: list[dict[str, Any]], *, database_url: str) -> dict[str, int]:
    topics = build_topic_model(events)
    now = _now()
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        session.query(EventTopicRecord).delete()
        session.query(TopicModelRecord).delete()
        session.add_all(_topic_records(topics, now))
        session.add_all(_event_topic_records(topics))
        session.commit()
    return {"topic_models": len(topics.topics), "event_topics": len(topics.event_topics)}


def precompute_event_relations(events: list[dict[str, Any]], *, database_url: str) -> dict[str, int]:
    session_factory = build_session_factory(database_url)
    now = _now()
    with session_factory() as session:
        event_topics = _load_event_topics(session)
        if not event_topics:
            topics = build_topic_model(events)
            session.query(EventTopicRecord).delete()
            session.query(TopicModelRecord).delete()
            session.add_all(_topic_records(topics, now))
            session.add_all(_event_topic_records(topics))
            event_topics = topics.event_topics
        relations = build_event_relations(events, event_topics)
        session.query(EventRelationRecord).delete()
        session.add_all(
            EventRelationRecord(
                id=item.id,
                source_event_id=item.source_event_id,
                target_event_id=item.target_event_id,
                relation_type=item.relation_type,
                weight=item.weight,
                evidence_json=item.evidence,
                created_at=now,
            )
            for item in relations
        )
        session.commit()
    return {"event_relations": len(relations)}


def precompute_trend_detection(events: list[dict[str, Any]], snapshots: list[dict[str, Any]], *, database_url: str) -> dict[str, int]:
    metrics = aggregate_daily_metrics(events, snapshots)
    trends = detect_trends(metrics)
    now = _now()
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        session.query(TrendSignalRecord).delete()
        session.query(DailyEventMetricRecord).delete()
        session.add_all(
            DailyEventMetricRecord(
                metric_date=item.metric_date,
                entity_id=item.entity_id,
                event_count=item.event_count,
                avg_composite_score=item.avg_composite_score,
                max_velocity_score=item.max_velocity_score,
                breakout_count=item.breakout_count,
            )
            for item in metrics
        )
        trend_records: list[TrendSignalRecord] = []
        for item in trends:
            signal_id = hashlib.sha1(f"{item.entity_id}:{item.trend}:{now.isoformat()}".encode()).hexdigest()[:16]
            trend_records.append(
                TrendSignalRecord(
                    id=f"trend-{signal_id}",
                    entity_id=item.entity_id,
                    signal_type=item.trend,
                    signal_value=item.sma_7d,
                    confidence=0.8 if item.trend != "insufficient_data" else 0.2,
                    detected_at=now,
                )
            )
        session.add_all(trend_records)
        session.commit()
    return {"daily_event_metrics": len(metrics), "trend_signals": len(trends)}


def precompute_topic_periodicity(events: list[dict[str, Any]], *, database_url: str) -> dict[str, int]:
    now = _now()
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        topics = _load_topic_model_result(session)
        if not topics.topics:
            topics = build_topic_model(events)
            session.query(EventTopicRecord).delete()
            session.query(TopicModelRecord).delete()
            session.add_all(_topic_records(topics, now))
            session.add_all(_event_topic_records(topics))
        periodicity = detect_topic_periodicity(events, topics)
        session.query(TopicPeriodicityRecord).delete()
        session.add_all(
            TopicPeriodicityRecord(
                topic_id=item.topic_id,
                label=item.label,
                period_days=item.period_days,
                confidence=item.confidence,
                detected_at=now,
            )
            for item in periodicity
        )
        session.commit()
    return {"topic_periodicity": len(periodicity)}


def precompute_temporal_rules(events: list[dict[str, Any]], *, database_url: str) -> dict[str, int]:
    now = _now()
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        relations = _load_event_relations(session)
        if not relations:
            event_topics = _load_event_topics(session)
            if not event_topics:
                topics = build_topic_model(events)
                session.query(EventTopicRecord).delete()
                session.query(TopicModelRecord).delete()
                session.add_all(_topic_records(topics, now))
                session.add_all(_event_topic_records(topics))
                event_topics = topics.event_topics
            relations = build_event_relations(events, event_topics)
            session.query(EventRelationRecord).delete()
            session.add_all(
                EventRelationRecord(
                    id=item.id,
                    source_event_id=item.source_event_id,
                    target_event_id=item.target_event_id,
                    relation_type=item.relation_type,
                    weight=item.weight,
                    evidence_json=item.evidence,
                    created_at=now,
                )
                for item in relations
            )
        temporal_rules = mine_temporal_association_rules(events, relations)
        session.query(TemporalAssociationRuleRecord).delete()
        session.add_all(
            TemporalAssociationRuleRecord(
                id=item.id,
                antecedent_event_id=item.antecedent_event_id,
                consequent_event_id=item.consequent_event_id,
                lag_days=item.lag_days,
                support=item.support,
                confidence=item.confidence,
                lift=item.lift,
                detected_at=now,
            )
            for item in temporal_rules
        )
        session.commit()
    return {"temporal_rules": len(temporal_rules)}


def sync_analysis_projection_from_events(
    events: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    *,
    database_url: str,
) -> dict[str, int]:
    """Precompute Phase 1 analysis tables from the current event snapshot."""
    topics = build_topic_model(events)
    relations = build_event_relations(events, topics.event_topics)
    metrics = aggregate_daily_metrics(events, snapshots)
    trends = detect_trends(metrics)
    periodicity = detect_topic_periodicity(events, topics)
    temporal_rules = mine_temporal_association_rules(events, relations)
    now = _now()
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        session.query(EventTopicRecord).delete()
        session.query(EventRelationRecord).delete()
        session.query(TemporalAssociationRuleRecord).delete()
        session.query(TopicPeriodicityRecord).delete()
        session.query(TrendSignalRecord).delete()
        session.query(DailyEventMetricRecord).delete()
        session.query(TopicModelRecord).delete()

        session.add_all(_topic_records(topics, now))
        session.add_all(_event_topic_records(topics))
        session.add_all(
            EventRelationRecord(
                id=item.id,
                source_event_id=item.source_event_id,
                target_event_id=item.target_event_id,
                relation_type=item.relation_type,
                weight=item.weight,
                evidence_json=item.evidence,
                created_at=now,
            )
            for item in relations
        )
        session.add_all(
            DailyEventMetricRecord(
                metric_date=item.metric_date,
                entity_id=item.entity_id,
                event_count=item.event_count,
                avg_composite_score=item.avg_composite_score,
                max_velocity_score=item.max_velocity_score,
                breakout_count=item.breakout_count,
            )
            for item in metrics
        )
        session.add_all(
            TopicPeriodicityRecord(
                topic_id=item.topic_id,
                label=item.label,
                period_days=item.period_days,
                confidence=item.confidence,
                detected_at=now,
            )
            for item in periodicity
        )
        session.add_all(
            TemporalAssociationRuleRecord(
                id=item.id,
                antecedent_event_id=item.antecedent_event_id,
                consequent_event_id=item.consequent_event_id,
                lag_days=item.lag_days,
                support=item.support,
                confidence=item.confidence,
                lift=item.lift,
                detected_at=now,
            )
            for item in temporal_rules
        )
        trend_records: list[TrendSignalRecord] = []
        for item in trends:
            signal_id = hashlib.sha1(f"{item.entity_id}:{item.trend}:{now.isoformat()}".encode()).hexdigest()[:16]
            trend_records.append(
                TrendSignalRecord(
                    id=f"trend-{signal_id}",
                    entity_id=item.entity_id,
                    signal_type=item.trend,
                    signal_value=item.sma_7d,
                    confidence=0.8 if item.trend != "insufficient_data" else 0.2,
                    detected_at=now,
                )
            )
        session.add_all(trend_records)
        session.commit()
    return {
        "topic_models": len(topics.topics),
        "event_topics": len(topics.event_topics),
        "event_relations": len(relations),
        "daily_event_metrics": len(metrics),
        "trend_signals": len(trends),
        "topic_periodicity": len(periodicity),
        "temporal_rules": len(temporal_rules),
    }
