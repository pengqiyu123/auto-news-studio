from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any

from ..store.base import parse_time
from .correlation import EventRelationInfo


@dataclass(frozen=True)
class TemporalAssociationRule:
    id: str
    antecedent_event_id: str
    consequent_event_id: str
    antecedent_title: str = ""
    consequent_title: str = ""
    lag_days: int = 0
    support: float = 0.0
    confidence: float = 0.0
    lift: float = 0.0


def _event_date(event: dict[str, Any]) -> date | None:
    parsed = parse_time(event.get("first_seen_at") or event.get("latest_collected_at") or event.get("last_seen_at"))
    return parsed.date() if parsed else None


def mine_temporal_association_rules(
    events: list[dict[str, Any]],
    relations: list[EventRelationInfo],
    *,
    min_support: float = 0.1,
    min_confidence: float = 0.5,
    max_lag_days: int = 14,
) -> list[TemporalAssociationRule]:
    event_by_id = {str(event.get("id") or ""): event for event in events if str(event.get("id") or "").strip()}
    dated_event_ids = {event_id for event_id, event in event_by_id.items() if _event_date(event)}
    total_events = max(len(dated_event_ids), 1)
    outgoing_counts: dict[str, int] = {}
    incoming_counts: dict[str, int] = {}
    pairs: dict[tuple[str, str, int], int] = {}

    for relation in relations:
        left = event_by_id.get(relation.source_event_id)
        right = event_by_id.get(relation.target_event_id)
        if not left or not right:
            continue
        left_date = _event_date(left)
        right_date = _event_date(right)
        if not left_date or not right_date or left_date == right_date:
            continue
        if left_date < right_date:
            antecedent_id, consequent_id = relation.source_event_id, relation.target_event_id
            lag_days = (right_date - left_date).days
        else:
            antecedent_id, consequent_id = relation.target_event_id, relation.source_event_id
            lag_days = (left_date - right_date).days
        if lag_days <= 0 or lag_days > max_lag_days:
            continue
        outgoing_counts[antecedent_id] = outgoing_counts.get(antecedent_id, 0) + 1
        incoming_counts[consequent_id] = incoming_counts.get(consequent_id, 0) + 1
        key = (antecedent_id, consequent_id, lag_days)
        pairs[key] = pairs.get(key, 0) + 1

    rules: list[TemporalAssociationRule] = []
    for (antecedent_id, consequent_id, lag_days), count in pairs.items():
        support = count / total_events
        confidence = count / max(outgoing_counts.get(antecedent_id, 0), 1)
        consequent_base_rate = incoming_counts.get(consequent_id, 0) / total_events
        lift = confidence / consequent_base_rate if consequent_base_rate > 0 else confidence
        if support < min_support or confidence < min_confidence:
            continue
        antecedent = event_by_id.get(antecedent_id, {})
        consequent = event_by_id.get(consequent_id, {})
        rule_hash = hashlib.sha1(f"{antecedent_id}:{consequent_id}:{lag_days}".encode()).hexdigest()[:16]
        rules.append(
            TemporalAssociationRule(
                id=f"rule-{rule_hash}",
                antecedent_event_id=antecedent_id,
                consequent_event_id=consequent_id,
                antecedent_title=str(antecedent.get("title") or ""),
                consequent_title=str(consequent.get("title") or ""),
                lag_days=lag_days,
                support=round(support, 4),
                confidence=round(confidence, 4),
                lift=round(lift, 4),
            )
        )
    return sorted(rules, key=lambda item: (-item.confidence, -item.support, -item.lift, item.lag_days))[:50]
