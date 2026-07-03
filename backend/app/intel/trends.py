from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from ..store.base import parse_time


@dataclass(frozen=True)
class DailyEventMetric:
    metric_date: date
    entity_id: str
    entity_name: str
    event_count: int = 0
    avg_composite_score: float = 0.0
    max_velocity_score: float = 0.0
    breakout_count: int = 0


@dataclass(frozen=True)
class TrendSignalInfo:
    entity_id: str
    entity_name: str
    trend: str
    trend_label: str
    sma_7d: float = 0.0
    sma_14d: float = 0.0
    signals: list[dict[str, Any]] = field(default_factory=list)


def _event_lookup(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(event.get("id")): event for event in events if str(event.get("id") or "").strip()}


def _event_entities(event: dict[str, Any]) -> list[tuple[str, str]]:
    ids = event.get("entity_ids") if isinstance(event.get("entity_ids"), list) else []
    names = event.get("entity_names") if isinstance(event.get("entity_names"), list) else []
    result: list[tuple[str, str]] = []
    for index, entity_id in enumerate(ids):
        normalized_id = str(entity_id or "").strip()
        if not normalized_id:
            continue
        name = str(names[index] if index < len(names) else normalized_id).strip() or normalized_id
        result.append((normalized_id, name))
    return result


def aggregate_daily_metrics(events: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> list[DailyEventMetric]:
    events_by_id = _event_lookup(events)
    grouped: dict[tuple[date, str], dict[str, Any]] = defaultdict(lambda: {"count": 0, "score": 0.0, "velocity": 0.0, "breakouts": 0, "name": ""})
    for snapshot in snapshots:
        event = events_by_id.get(str(snapshot.get("event_id")))
        if not event:
            continue
        captured_at = parse_time(snapshot.get("captured_at"))
        if not captured_at:
            continue
        for entity_id, entity_name in _event_entities(event):
            key = (captured_at.date(), entity_id)
            bucket = grouped[key]
            bucket["count"] += int(snapshot.get("member_count") or 1)
            bucket["score"] += float(snapshot.get("composite_score") or 0)
            bucket["velocity"] = max(float(bucket["velocity"]), float(snapshot.get("velocity_score") or 0))
            bucket["breakouts"] += 1 if str(snapshot.get("alert_state") or "") == "breakout" else 0
            bucket["name"] = entity_name
    return sorted(
        [
            DailyEventMetric(
                metric_date=metric_date,
                entity_id=entity_id,
                entity_name=str(bucket["name"] or entity_id),
                event_count=int(bucket["count"]),
                avg_composite_score=round(float(bucket["score"]) / max(int(bucket["count"]), 1), 4),
                max_velocity_score=round(float(bucket["velocity"]), 4),
                breakout_count=int(bucket["breakouts"]),
            )
            for (metric_date, entity_id), bucket in grouped.items()
        ],
        key=lambda item: (item.entity_id, item.metric_date),
    )


def _sma(values: list[int], days: int) -> float:
    if not values:
        return 0.0
    window = values[-days:]
    return sum(window) / max(len(window), 1)


def _cusum(values: list[int]) -> list[dict[str, Any]]:
    if len(values) < 4:
        return []
    mean = sum(values) / len(values)
    positive = 0.0
    signals: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        positive = max(0.0, positive + value - mean)
        if positive > max(mean * 2, 2):
            signals.append({"type": "cusum_jump", "day_index": index, "value": round(positive, 4)})
            positive = 0.0
    return signals


def detect_trends(metrics: list[DailyEventMetric], *, as_of: date | None = None) -> list[TrendSignalInfo]:
    if not metrics:
        return []
    as_of = as_of or datetime.now().date()
    by_entity: dict[str, list[DailyEventMetric]] = defaultdict(list)
    for metric in metrics:
        by_entity[metric.entity_id].append(metric)
    results: list[TrendSignalInfo] = []
    for entity_id, items in by_entity.items():
        by_day = {item.metric_date: item for item in items}
        series_days = [as_of - timedelta(days=offset) for offset in range(29, -1, -1)]
        values = [int(by_day.get(day).event_count if by_day.get(day) else 0) for day in series_days]
        active_days = len([value for value in values if value > 0])
        name = next((item.entity_name for item in reversed(items) if item.entity_name), entity_id)
        if active_days < 7:
            results.append(
                TrendSignalInfo(
                    entity_id=entity_id,
                    entity_name=name,
                    trend="insufficient_data",
                    trend_label="数据不足，暂不判断趋势",
                    sma_7d=round(_sma(values, 7), 4),
                    sma_14d=round(_sma(values, 14), 4),
                    signals=[],
                )
            )
            continue
        sma_7d = _sma(values, 7)
        sma_14d = _sma(values, 14)
        recent_3d = sum(values[-3:])
        previous_7d = sum(values[-10:-3])
        acceleration = (sum(values[-3:]) / 3) - (sum(values[-7:-4]) / 3 if values[-7:-4] else 0)
        if recent_3d > max(previous_7d * 2, 0) and recent_3d >= 3:
            trend = "emerging"
            label = "近3天明显升温"
        elif sma_7d > sma_14d and acceleration >= 0:
            trend = "hot"
            label = "近7天持续上升"
        elif sma_7d < sma_14d:
            trend = "cool"
            label = "近7天热度回落"
        elif sum(values[-7:]) == 0:
            trend = "cold"
            label = "近7天暂无新事件"
        else:
            trend = "warm"
            label = "近7天走势平稳"
        signals = _cusum(values)
        if acceleration:
            signals.append({"type": "sma_acceleration", "value": round(acceleration, 4)})
        results.append(
            TrendSignalInfo(
                entity_id=entity_id,
                entity_name=name,
                trend=trend,
                trend_label=label,
                sma_7d=round(sma_7d, 4),
                sma_14d=round(sma_14d, 4),
                signals=signals,
            )
        )
    return sorted(results, key=lambda item: (item.trend == "insufficient_data", -item.sma_7d, item.entity_name))
