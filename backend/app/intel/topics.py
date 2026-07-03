from __future__ import annotations

import re
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from .tokenizer import tokenize_for_analysis

try:
    from sklearn.decomposition import NMF  # type: ignore
    from sklearn.exceptions import ConvergenceWarning  # type: ignore
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - lean local env fallback
    ConvergenceWarning = Warning
    NMF = None
    TfidfVectorizer = None


@dataclass(frozen=True)
class TopicInfo:
    topic_id: str
    label: str
    keywords: list[str]
    event_count: int = 0


@dataclass(frozen=True)
class EventTopic:
    event_id: str
    topic_id: str
    weight: float


@dataclass(frozen=True)
class TopicModelResult:
    topics: list[TopicInfo] = field(default_factory=list)
    event_topics: list[EventTopic] = field(default_factory=list)


def _event_text(event: dict[str, Any]) -> str:
    return " ".join(
        part for part in [
            str(event.get("title") or ""),
            str(event.get("summary") or ""),
            " ".join(str(item) for item in event.get("anchor_tokens") or []),
            " ".join(str(item) for item in event.get("entity_names") or []),
        ]
        if part
    )


def _fallback_topic_model(events: list[dict[str, Any]], topic_count: int) -> TopicModelResult:
    buckets: dict[str, list[tuple[dict[str, Any], list[str]]]] = defaultdict(list)
    for event in events:
        tokens = tokenize_for_analysis(_event_text(event))
        if not tokens:
            continue
        entity_ids = [str(item).strip().lower() for item in event.get("entity_ids") or [] if str(item).strip()]
        key = entity_ids[0] if entity_ids else tokens[0]
        if not entity_ids:
            for token in tokens:
                if reweight_token(token) > reweight_token(key):
                    key = token
        buckets[key].append((event, tokens))
    topics: list[TopicInfo] = []
    event_topics: list[EventTopic] = []
    for index, (key, bucket) in enumerate(sorted(buckets.items(), key=lambda item: len(item[1]), reverse=True)[:topic_count]):
        counter: Counter[str] = Counter()
        for event, tokens in bucket:
            counter.update(tokens)
            event_topics.append(EventTopic(event_id=str(event.get("id")), topic_id=f"topic-{index:02d}", weight=1.0))
        keywords = [word for word, _count in counter.most_common(8)]
        topics.append(TopicInfo(topic_id=f"topic-{index:02d}", label=" / ".join(keywords[:3]) or key, keywords=keywords, event_count=len(bucket)))
    return TopicModelResult(topics=topics, event_topics=event_topics)


def reweight_token(token: str) -> int:
    if re.search(r"[\u4e00-\u9fff]", token):
        return len(token) + 2
    return len(token)


def build_topic_model(events: list[dict[str, Any]], topic_count: int = 30) -> TopicModelResult:
    valid_events = [event for event in events if str(event.get("id") or "").strip()]
    if not valid_events:
        return TopicModelResult()
    documents = [" ".join(tokenize_for_analysis(_event_text(event))) for event in valid_events]
    if TfidfVectorizer is None or NMF is None or len(valid_events) < 2 or not any(documents):
        return _fallback_topic_model(valid_events, topic_count)
    try:
        vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b", min_df=1)
        matrix = vectorizer.fit_transform(documents)
        if matrix.shape[1] < 2:
            return _fallback_topic_model(valid_events, topic_count)
        sample_limited_topics = max(1, len(valid_events) // 2)
        safe_topic_count = max(1, min(topic_count, sample_limited_topics, matrix.shape[1]))
        model = NMF(n_components=safe_topic_count, init="nndsvda", random_state=42, max_iter=800)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            weights = model.fit_transform(matrix)
        names = vectorizer.get_feature_names_out()
    except Exception:
        return _fallback_topic_model(valid_events, topic_count)

    topic_events: dict[int, list[tuple[str, float]]] = defaultdict(list)
    event_topics: list[EventTopic] = []
    for event, row in zip(valid_events, weights, strict=False):
        best_index = int(row.argmax()) if len(row) else 0
        best_weight = float(row[best_index]) if len(row) else 0.0
        normalized_weight = round(min(max(best_weight, 0.0), 1.0), 4) or 1.0
        topic_id = f"topic-{best_index:02d}"
        event_id = str(event.get("id"))
        event_topics.append(EventTopic(event_id=event_id, topic_id=topic_id, weight=normalized_weight))
        topic_events[best_index].append((event_id, normalized_weight))

    topics: list[TopicInfo] = []
    for index, component in enumerate(model.components_):
        top_indices = component.argsort()[::-1][:8]
        keywords = [str(names[token_index]) for token_index in top_indices if component[token_index] > 0]
        topics.append(
            TopicInfo(
                topic_id=f"topic-{index:02d}",
                label=" / ".join(keywords[:3]) if keywords else f"主题 {index + 1}",
                keywords=keywords,
                event_count=len(topic_events.get(index, [])),
            )
        )
    return TopicModelResult(topics=topics, event_topics=event_topics)
