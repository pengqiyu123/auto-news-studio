from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from ..store.base import parse_time
from .topics import TopicModelResult


@dataclass(frozen=True)
class TopicPeriodicityInfo:
    topic_id: str
    label: str = ""
    period_days: int = 0
    confidence: float = 0.0
    detected_at: str = ""


def _event_date(event: dict[str, Any]) -> date | None:
    parsed = parse_time(event.get("first_seen_at") or event.get("latest_collected_at") or event.get("last_seen_at"))
    return parsed.date() if parsed else None


def _series_from_dates(dates: list[date]) -> list[float]:
    if not dates:
        return []
    start = min(dates)
    end = max(dates)
    days = (end - start).days + 1
    counts = [0.0] * days
    for item in dates:
        counts[(item - start).days] += 1.0
    return counts


def _acf(values: list[float], lag: int) -> float:
    if len(values) <= lag or lag <= 0:
        return 0.0
    mean = sum(values) / len(values)
    denominator = sum((value - mean) ** 2 for value in values)
    if denominator <= 0:
        return 0.0
    numerator = sum((values[index] - mean) * (values[index - lag] - mean) for index in range(lag, len(values)))
    return numerator / denominator


def detect_topic_periodicity(
    events: list[dict[str, Any]],
    topics: TopicModelResult,
    *,
    min_period_days: int = 2,
    max_period_days: int = 14,
    min_confidence: float = 0.35,
) -> list[TopicPeriodicityInfo]:
    event_by_id = {str(event.get("id") or ""): event for event in events if str(event.get("id") or "").strip()}
    topic_labels = {topic.topic_id: topic.label for topic in topics.topics}
    dates_by_topic: dict[str, list[date]] = defaultdict(list)
    for item in topics.event_topics:
        event_date = _event_date(event_by_id.get(item.event_id, {}))
        if event_date:
            dates_by_topic[item.topic_id].append(event_date)

    detected_at = datetime.now(UTC).isoformat()
    results: list[TopicPeriodicityInfo] = []
    for topic_id, dates in dates_by_topic.items():
        if len(dates) < 4:
            continue
        series = _series_from_dates(dates)
        if len(series) < min_period_days * 2:
            continue
        best_period = 0
        best_score = 0.0
        for period in range(min_period_days, min(max_period_days, max(len(series) - 1, min_period_days)) + 1):
            score = _acf(series, period)
            if score > best_score:
                best_score = score
                best_period = period
        if best_period and best_score >= min_confidence:
            results.append(
                TopicPeriodicityInfo(
                    topic_id=topic_id,
                    label=topic_labels.get(topic_id, topic_id),
                    period_days=best_period,
                    confidence=round(max(0.0, min(1.0, best_score)), 4),
                    detected_at=detected_at,
                )
            )
    return sorted(results, key=lambda item: (-item.confidence, item.period_days, item.label))
