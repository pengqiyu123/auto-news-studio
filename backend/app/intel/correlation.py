from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from typing import Any

from ..store.base import parse_time
from .topics import EventTopic


@dataclass(frozen=True)
class EventRelationInfo:
    id: str
    source_event_id: str
    target_event_id: str
    relation_type: str
    weight: float
    evidence: dict[str, Any] = field(default_factory=dict)


def _as_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip().lower() for item in value if str(item).strip()}


def _parse(value: Any) -> datetime | None:
    parsed = parse_time(value)
    if parsed and parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _topic_map(event_topics: list[EventTopic]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for item in event_topics:
        result.setdefault(item.event_id, set()).add(item.topic_id)
    return result


def build_event_relations(events: list[dict[str, Any]], event_topics: list[EventTopic] | None = None) -> list[EventRelationInfo]:
    topic_by_event = _topic_map(event_topics or [])
    relations: list[EventRelationInfo] = []
    valid_events = [event for event in events if str(event.get("id") or "").strip()]
    for left, right in combinations(valid_events, 2):
        left_id = str(left.get("id"))
        right_id = str(right.get("id"))
        evidence: dict[str, Any] = {}
        relation_types: list[str] = []
        weight = 0.0

        shared_entities = sorted(_as_set(left.get("entity_ids")) & _as_set(right.get("entity_ids")))
        if len(shared_entities) >= 2:
            weight += 0.35
            relation_types.append("entity_shared")
            evidence["shared_entities"] = shared_entities

        shared_topics = sorted(topic_by_event.get(left_id, set()) & topic_by_event.get(right_id, set()))
        if shared_topics:
            weight += 0.25
            relation_types.append("topic_shared")
            evidence["shared_topics"] = shared_topics

        left_time = _parse(left.get("first_seen_at") or left.get("last_seen_at"))
        right_time = _parse(right.get("first_seen_at") or right.get("last_seen_at"))
        if left_time and right_time:
            hours = abs((left_time - right_time).total_seconds()) / 3600
            if hours <= 72:
                weight += 0.20
                relation_types.append("temporal_proximity")
                evidence["hours_apart"] = round(hours, 2)

        left_tokens = _as_set(left.get("anchor_tokens"))
        right_tokens = _as_set(right.get("anchor_tokens"))
        if left_tokens or right_tokens:
            jaccard = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
            if jaccard >= 0.3:
                weight += 0.20
                relation_types.append("anchor_overlap")
                evidence["anchor_overlap"] = sorted(left_tokens & right_tokens)
                evidence["anchor_jaccard"] = round(jaccard, 4)

        if weight >= 0.4:
            relation_id = hashlib.sha1(f"{left_id}:{right_id}:{','.join(relation_types)}".encode()).hexdigest()[:16]
            relations.append(
                EventRelationInfo(
                    id=f"rel-{relation_id}",
                    source_event_id=left_id,
                    target_event_id=right_id,
                    relation_type="+".join(relation_types) or "related",
                    weight=round(min(weight, 1.0), 4),
                    evidence=evidence,
                )
            )
    return sorted(relations, key=lambda item: item.weight, reverse=True)
