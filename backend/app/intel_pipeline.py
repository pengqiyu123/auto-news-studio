from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .entity_extractor import extract_entities
from .llm import LLMService

UTC = timezone.utc
TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "from",
    "from_source",
    "feature",
    "ref",
    "ref_src",
    "source",
}

ALERT_LEVELS = {"cooling": 0, "new": 1, "watch": 2, "rising": 3, "breakout": 4}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        try:
            return parsedate_to_datetime(value).astimezone(UTC)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def canonical_link(link: str) -> str:
    compact = str(link or "").strip()
    if not compact:
        return ""
    try:
        parts = urlsplit(compact)
    except ValueError:
        return compact
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.lower() not in TRACKING_QUERY_KEYS]
    clean_path = re.sub(r"/+", "/", parts.path or "/")
    return urlunsplit((parts.scheme, parts.netloc.lower(), clean_path.rstrip("/") or "/", urlencode(query), ""))


def normalize_title(title: str) -> str:
    lowered = str(title or "").lower().strip()
    lowered = re.sub(r"[^\w\u4e00-\u9fff\s.-]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def build_dedupe_key(title: str, link: str) -> str:
    normalized = normalize_title(title)
    ascii_tokens = re.findall(r"[a-z0-9]{2,}", normalized)
    zh_bigrams: list[str] = []
    zh_chars = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    for size in range(2, 7):
        for index in range(0, max(len(zh_chars) - size + 1, 0)):
            zh_bigrams.append(zh_chars[index:index + size])
    merged = " ".join(ascii_tokens + zh_bigrams)
    if merged.strip():
        return merged[:120]
    stable = canonical_link(link) or link
    return hashlib.sha1(stable.encode("utf-8")).hexdigest()[:40]


def tokenize_title(title: str) -> set[str]:
    normalized = normalize_title(title)
    ascii_tokens = set(re.findall(r"[a-z0-9]{2,}", normalized))
    zh_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,6}", title))
    return ascii_tokens | zh_tokens


def extract_anchor_tokens(title: str, tags: list[str] | None = None) -> set[str]:
    anchors: set[str] = set()
    anchors.update(token.lower() for token in re.findall(r"\b[A-Z][A-Za-z0-9.+-]{1,}\b", title))
    anchors.update(token.lower() for token in re.findall(r"\b[a-z]+(?:-[a-z0-9]+)*\d+(?:\.\d+)*\b", title.lower()))
    anchors.update(token.lower() for token in re.findall(r"\b[a-z]{2,}\d+(?:\.\d+)*\b", title.lower()))
    anchors.update(token for token in re.findall(r"[\u4e00-\u9fff]{2,6}", title) if len(token) >= 2)
    anchors.update(str(tag).lower() for tag in (tags or []) if str(tag).strip())
    return {token for token in anchors if token and token not in {"today", "update", "news"}}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return len(left & right) / max(len(left | right), 1)


def source_weight(source: dict[str, Any] | None) -> float:
    if not source:
        return 0.7
    try:
        return float(source.get("weight", 0.7) or 0.7)
    except (TypeError, ValueError):
        return 0.7


def _primary_platform(source: dict[str, Any] | None, item: dict[str, Any]) -> str:
    if source and source.get("platform"):
        return str(source["platform"])
    kind = str(item.get("source_kind") or "")
    if kind:
        return kind
    return "unknown"


def _theme_tags(item: dict[str, Any], source: dict[str, Any] | None) -> set[str]:
    tags = {str(tag).lower() for tag in item.get("tags", []) if str(tag).strip()}
    if source:
        tags.update(str(tag).lower() for tag in source.get("tags", []) if str(tag).strip())
    return tags


def _source_native_id(raw: dict[str, Any]) -> str | None:
    metadata = raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {}
    for key in ("source_native_id", "upstream_id", "item_id", "object_id", "post_id"):
        value = metadata.get(key) or raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _discovery_identity_keys(item: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    canonical = str(item.get("canonical_link") or "").strip()
    if canonical:
        keys.append(f"canonical:{canonical}")
    source_key = str(item.get("source_key") or "").strip()
    source_native_id = str(item.get("source_native_id") or "").strip()
    if source_key and source_native_id:
        keys.append(f"native:{source_key}:{source_native_id}")
    dedupe_key = str(item.get("dedupe_key") or "").strip()
    published_at = str(item.get("published_at") or "").strip()
    if source_key and dedupe_key and published_at:
        keys.append(f"published:{source_key}:{dedupe_key}:{published_at}")
    return keys


def _discovery_fingerprint(item: dict[str, Any]) -> str:
    summary = normalize_title(str(item.get("summary") or ""))
    content = normalize_title(str(item.get("content") or ""))
    engagement = round(float(item.get("engagement_score", 0) or 0), 2)
    return "|".join(
        [
            normalize_title(str(item.get("title") or "")),
            summary[:200],
            content[:400],
            str(engagement),
        ]
    )


def _index_previous_discovery_items(previous_discovery_items: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in previous_discovery_items or []:
        for key in _discovery_identity_keys(item):
            index.setdefault(key, item)
    return index


def build_discovery_items(
    raw_items: list[dict[str, Any]],
    sources_by_key: dict[str, dict[str, Any]],
    previous_discovery_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    previous_index = _index_previous_discovery_items(previous_discovery_items)
    discovery: list[dict[str, Any]] = []
    for raw in raw_items:
        source = sources_by_key.get(raw.get("source_key"))
        canonical = canonical_link(str(raw.get("link") or ""))
        title = str(raw.get("title") or "").strip()
        published_at = raw.get("published_at") or raw.get("collected_at") or now_iso()
        collected_at = raw.get("collected_at") or now_iso()
        tags = sorted(_theme_tags(raw, source))
        discovery.append(
            {
                "id": f"disc-{raw.get('id') or hashlib.sha1((title + canonical).encode('utf-8')).hexdigest()[:12]}",
                "raw_item_id": raw.get("id"),
                "source_key": raw.get("source_key"),
                "source_name": raw.get("source_name"),
                "source_kind": raw.get("source_kind"),
                "platform": _primary_platform(source, raw),
                "title": title,
                "summary": str(raw.get("summary") or title).strip(),
                "content": str(raw.get("content") or raw.get("summary") or title).strip(),
                "link": str(raw.get("link") or "").strip(),
                "canonical_link": canonical,
                "dedupe_key": build_dedupe_key(title, canonical),
                "source_native_id": _source_native_id(raw),
                "title_tokens": sorted(tokenize_title(title)),
                "anchor_tokens": sorted(extract_anchor_tokens(title, tags)),
                "published_at": published_at,
                "collected_at": collected_at,
                "tags": tags,
                "engagement_score": float(raw.get("engagement", {}).get("score", 0) or 0),
                "item_state": "new_item",
                "metadata": raw.get("metadata", {}),
            }
        )
        current = discovery[-1]
        previous = next((previous_index[key] for key in _discovery_identity_keys(current) if key in previous_index), None)
        if previous:
            current["item_state"] = "updated_item" if _discovery_fingerprint(previous) != _discovery_fingerprint(current) else "seen_item"
    discovery.sort(key=lambda item: parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
    return discovery


def _should_merge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("canonical_link") and left.get("canonical_link") == right.get("canonical_link"):
        return True
    if left.get("dedupe_key") and left.get("dedupe_key") == right.get("dedupe_key"):
        return True
    left_tokens = set(left.get("title_tokens", []))
    right_tokens = set(right.get("title_tokens", []))
    similarity = jaccard(left_tokens, right_tokens)
    if similarity >= 0.45:
        return True
    if similarity < 0.28:
        return False
    left_anchors = set(left.get("anchor_tokens", []))
    right_anchors = set(right.get("anchor_tokens", []))
    anchor_overlap = bool(left_anchors & right_anchors)
    left_time = parse_time(left.get("published_at")) or parse_time(left.get("collected_at"))
    right_time = parse_time(right.get("published_at")) or parse_time(right.get("collected_at"))
    within_day = bool(left_time and right_time and abs((left_time - right_time).total_seconds()) <= 24 * 3600)
    left_tags = set(left.get("tags", []))
    right_tags = set(right.get("tags", []))
    same_theme = bool(left_tags & right_tags) or left.get("platform") == right.get("platform")
    return anchor_overlap and within_day and same_theme


def _day_bucket(item: dict[str, Any]) -> str:
    point = (
        parse_time(item.get("published_at"))
        or parse_time(item.get("collected_at"))
        or datetime.now(UTC)
    )
    return point.astimezone(UTC).strftime("%Y-%m-%d")


def _source_story_seed(item: dict[str, Any]) -> str:
    canonical = str(item.get("canonical_link") or "").strip()
    if canonical:
        return f"canonical:{canonical}"
    source_native_id = str(item.get("source_native_id") or "").strip()
    if source_native_id:
        return f"native:{source_native_id}"
    anchors = sorted(set(str(token).strip().lower() for token in item.get("anchor_tokens", []) if str(token).strip()))
    top_anchors = anchors[:2]
    if top_anchors:
        return f"anchors:{'|'.join(top_anchors)}:{_day_bucket(item)}"
    dedupe = str(item.get("dedupe_key") or "").strip()
    return f"dedupe:{dedupe[:80]}:{_day_bucket(item)}"


def _source_story_time(item: dict[str, Any]) -> datetime:
    return (
        parse_time(item.get("published_at"))
        or parse_time(item.get("collected_at"))
        or datetime.min.replace(tzinfo=UTC)
    )


def _should_merge_within_source(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if str(left.get("source_key") or "") != str(right.get("source_key") or ""):
        return False
    if left.get("canonical_link") and left.get("canonical_link") == right.get("canonical_link"):
        return True
    if left.get("source_native_id") and left.get("source_native_id") == right.get("source_native_id"):
        return True
    if left.get("dedupe_key") and left.get("dedupe_key") == right.get("dedupe_key"):
        return True
    left_time = _source_story_time(left)
    right_time = _source_story_time(right)
    if abs((left_time - right_time).total_seconds()) > 12 * 3600:
        return False
    similarity = jaccard(set(left.get("title_tokens", [])), set(right.get("title_tokens", [])))
    if similarity < 0.30:
        return False
    left_anchors = set(left.get("anchor_tokens", []))
    right_anchors = set(right.get("anchor_tokens", []))
    return bool(left_anchors & right_anchors)


def _compact_source_cluster(cluster: list[dict[str, Any]], sources_by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    primary = _representative_item(cluster, sources_by_key)
    compacted = dict(primary)
    compacted["title_tokens"] = list(primary.get("title_tokens", []))
    compacted["anchor_tokens"] = list(primary.get("anchor_tokens", []))
    compacted["tags"] = sorted({tag for item in cluster for tag in item.get("tags", [])})
    compacted["summary"] = primary.get("summary") or primary.get("content") or primary.get("title")
    compacted["content"] = primary.get("content") or primary.get("summary") or primary.get("title")
    compacted["engagement_score"] = max(float(item.get("engagement_score", 0) or 0) for item in cluster)
    compacted["story_discovery_item_ids"] = [str(item.get("id")) for item in cluster if item.get("id")]
    compacted["raw_member_count"] = len(cluster)
    compacted["published_at"] = primary.get("published_at")
    compacted["collected_at"] = max(
        (item.get("collected_at") for item in cluster),
        key=lambda value: parse_time(value) or datetime.min.replace(tzinfo=UTC),
    ) if cluster else primary.get("collected_at")
    return compacted


def _compact_source_stories(
    discovery_items: list[dict[str, Any]],
    sources_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not discovery_items:
        return []
    grouped_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in discovery_items:
        grouped_by_source[str(item.get("source_key") or "")].append(item)

    stories: list[dict[str, Any]] = []
    for source_key, source_items in grouped_by_source.items():
        seed_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in source_items:
            seed_buckets[_source_story_seed(item)].append(item)
        for bucket_items in seed_buckets.values():
            if len(bucket_items) == 1:
                single = dict(bucket_items[0])
                single["story_discovery_item_ids"] = [str(single.get("id"))] if single.get("id") else []
                single["raw_member_count"] = 1
                stories.append(single)
                continue
            parent = list(range(len(bucket_items)))

            def find(index: int) -> int:
                while parent[index] != index:
                    parent[index] = parent[parent[index]]
                    index = parent[index]
                return index

            def union(left: int, right: int) -> None:
                left_root = find(left)
                right_root = find(right)
                if left_root != right_root:
                    parent[left_root] = right_root

            for idx, left in enumerate(bucket_items):
                for right_idx in range(idx + 1, len(bucket_items)):
                    if _should_merge_within_source(left, bucket_items[right_idx]):
                        union(idx, right_idx)

            compacted_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for index, item in enumerate(bucket_items):
                compacted_groups[find(index)].append(item)
            for cluster in compacted_groups.values():
                stories.append(_compact_source_cluster(cluster, sources_by_key))
    stories.sort(key=lambda item: _source_story_time(item), reverse=True)
    return stories


def cluster_discovery_items(
    discovery_items: list[dict[str, Any]],
    sources_by_key: dict[str, dict[str, Any]],
    reference_time: datetime | None = None,
) -> list[list[dict[str, Any]]]:
    if not discovery_items:
        return []
    source_stories = _compact_source_stories(discovery_items, sources_by_key)
    parent = list(range(len(source_stories)))
    now = reference_time or datetime.now(UTC)

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[left_root] = right_root

    recent_cutoff = now - timedelta(hours=24)
    recent_indices = [
        i for i, item in enumerate(source_stories)
        if (parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC)) >= recent_cutoff
    ]
    for idx, left_index in enumerate(recent_indices):
        for right_index in recent_indices[idx + 1:]:
            if _should_merge(source_stories[left_index], source_stories[right_index]):
                union(left_index, right_index)

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(source_stories):
        grouped[find(index)].append(item)
    return list(grouped.values())


def _representative_item(cluster: list[dict[str, Any]], sources_by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def rank(item: dict[str, Any]) -> tuple[Any, ...]:
        published = parse_time(item.get("published_at")) or datetime.min.replace(tzinfo=UTC)
        weight = source_weight(sources_by_key.get(item.get("source_key")))
        return (
            published,
            float(item.get("engagement_score", 0) or 0),
            weight,
            parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC),
        )

    return sorted(cluster, key=rank, reverse=True)[0]


def _event_id_for_cluster(cluster: list[dict[str, Any]], primary: dict[str, Any]) -> str:
    seed = primary.get("canonical_link") or primary.get("dedupe_key") or " ".join(primary.get("anchor_tokens", [])[:4])
    if not seed:
        seed = "|".join(sorted(str(item.get("id")) for item in cluster))
    return f"evt-{hashlib.sha1(str(seed).encode('utf-8')).hexdigest()[:12]}"


def _event_time_bounds(cluster: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    points = [parse_time(item.get("published_at")) or parse_time(item.get("collected_at")) for item in cluster]
    valid = [point for point in points if point]
    if not valid:
        return None, None
    return min(valid).replace(microsecond=0).isoformat(), max(valid).replace(microsecond=0).isoformat()


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _published_recency_score(now: datetime, published_at: datetime | None) -> float:
    if not published_at:
        return 0.0
    age_hours = max((now - published_at).total_seconds() / 3600, 0.0)
    if age_hours <= 1:
        return 70.0
    if age_hours <= 6:
        return 70.0 - ((age_hours - 1) / 5.0) * 20.0
    if age_hours <= 24:
        return 50.0 - ((age_hours - 6) / 18.0) * 30.0
    if age_hours <= 72:
        return 20.0 - ((age_hours - 24) / 48.0) * 20.0
    return 0.0


def _lag_score(published_at: datetime | None, collected_at: datetime | None) -> float:
    if not published_at or not collected_at:
        return 0.0
    lag_minutes = max((collected_at - published_at).total_seconds() / 60, 0.0)
    if lag_minutes <= 10:
        return 30.0
    if lag_minutes <= 30:
        return 24.0
    if lag_minutes <= 120:
        return 14.0
    if lag_minutes <= 360:
        return 6.0
    return 0.0


def _freshness_score(event: dict[str, Any], now: datetime) -> float:
    published = parse_time(event.get("published_at"))
    collected = parse_time(event.get("latest_collected_at"))
    if published:
        return round(_published_recency_score(now, published) + _lag_score(published, collected), 1)
    if not collected:
        return 0.0
    approx = round(min(_published_recency_score(now, collected), 45.0), 1)
    return approx


def _window_baseline(
    snapshots: list[dict[str, Any]],
    event_id: str,
    window_start: datetime,
) -> dict[str, Any] | None:
    candidates = [
        item for item in snapshots
        if item.get("event_id") == event_id
        and (parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC)) >= window_start
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC))[0]


def _growth_from_last_two(snapshots: list[dict[str, Any]], event_id: str, current_member_count: int) -> bool:
    candidates = [
        item for item in snapshots
        if item.get("event_id") == event_id
    ]
    candidates.sort(key=lambda item: parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC))
    if not candidates:
        return False
    if len(candidates) == 1:
        return current_member_count > int(candidates[-1].get("member_count", 0) or 0)
    return (
        int(candidates[-1].get("member_count", 0) or 0) >= int(candidates[-2].get("member_count", 0) or 0)
        and current_member_count >= int(candidates[-1].get("member_count", 0) or 0)
    )


def _coverage_score(event: dict[str, Any], sources_by_key: dict[str, dict[str, Any]]) -> float:
    weights = [source_weight(sources_by_key.get(source_key)) for source_key in event.get("source_keys", [])]
    weighted_source_base = _avg(weights) * 45.0
    platform_count = int(event.get("platform_count", 0) or 0)
    if platform_count <= 1:
        platform_bonus = 0.0
    elif platform_count == 2:
        platform_bonus = 10.0
    elif platform_count == 3:
        platform_bonus = 18.0
    elif platform_count == 4:
        platform_bonus = 24.0
    else:
        platform_bonus = 30.0
    source_bonus = min(int(event.get("source_count", 0) or 0) * 3.0, 15.0)
    return round(min(100.0, weighted_source_base + platform_bonus + source_bonus), 1)


def _velocity_score(event: dict[str, Any], prior_snapshots: list[dict[str, Any]], now: datetime) -> tuple[float, dict[str, float]]:
    event_id = str(event.get("id"))
    member_count = int(event.get("member_count", 0) or 0)
    platform_count = int(event.get("platform_count", 0) or 0)
    first_seen = parse_time(event.get("first_seen_at")) or now
    age_hours = max((now - first_seen).total_seconds() / 3600, 0.0)

    baseline_30m = _window_baseline(prior_snapshots, event_id, now - timedelta(minutes=30))
    baseline_2h = _window_baseline(prior_snapshots, event_id, now - timedelta(hours=2))
    baseline_platform_30m = int(baseline_30m.get("platform_count", 0) or 0) if baseline_30m else 0
    delta_mentions_30m = member_count - int(baseline_30m.get("member_count", 0) or 0) if baseline_30m else member_count
    delta_mentions_2h = member_count - int(baseline_2h.get("member_count", 0) or 0) if baseline_2h else member_count
    speed_30m = delta_mentions_30m / 0.5
    speed_2h = (delta_mentions_2h / 2.0) if baseline_2h else speed_30m

    if speed_30m >= 100:
        base_velocity = 80.0
    elif speed_30m >= 30:
        base_velocity = 60.0 + min((speed_30m - 30.0) / 70.0 * 19.0, 19.0)
    elif speed_30m >= 10:
        base_velocity = 40.0 + min((speed_30m - 10.0) / 20.0 * 19.0, 19.0)
    elif speed_30m >= 3:
        base_velocity = 20.0 + min((speed_30m - 3.0) / 7.0 * 19.0, 19.0)
    else:
        base_velocity = min(speed_30m / 3.0 * 19.0, 19.0)

    if age_hours < 2.0:
        acceleration = 0.0
    else:
        acceleration = speed_30m - speed_2h

    if acceleration >= 40:
        acceleration_bonus = 20.0
    elif acceleration >= 20:
        acceleration_bonus = 12.0
    elif acceleration >= 8:
        acceleration_bonus = 6.0
    else:
        acceleration_bonus = 0.0
    fresh_bonus = 10.0 if age_hours <= 2.0 else 0.0
    score = round(min(100.0, base_velocity + acceleration_bonus + fresh_bonus), 1)
    details = {
        "delta_mentions_30m": float(delta_mentions_30m),
        "delta_mentions_2h": float(delta_mentions_2h),
        "speed_30m": round(speed_30m, 1),
        "speed_2h": round(speed_2h, 1),
        "acceleration": round(acceleration, 1),
        "baseline_platform_30m": float(baseline_platform_30m),
        "recent_growth": 1.0 if _growth_from_last_two(prior_snapshots, event_id, member_count) else 0.0,
    }
    return score, details


def _alert_state(event: dict[str, Any], details: dict[str, float], now: datetime) -> str:
    member_count = int(event.get("member_count", 0) or 0)
    platform_count = int(event.get("platform_count", 0) or 0)
    first_seen = parse_time(event.get("first_seen_at")) or now
    last_seen = parse_time(event.get("last_seen_at")) or first_seen
    age_hours = max((now - first_seen).total_seconds() / 3600, 0.0)
    last_seen_hours = max((now - last_seen).total_seconds() / 3600, 0.0)
    velocity = float(event.get("velocity_score", 0) or 0)
    delta_30m = details.get("delta_mentions_30m", 0.0)
    recent_growth = bool(details.get("recent_growth", 0.0))
    acceleration = details.get("acceleration", 0.0)
    baseline_platform_30m = details.get("baseline_platform_30m", 0.0)

    if last_seen_hours > 6 or delta_30m <= 0:
        return "cooling"
    if velocity >= 75 and platform_count >= 2 and (age_hours < 2 or acceleration >= 20) and recent_growth:
        return "breakout"
    if velocity >= 55 or (baseline_platform_30m <= 1 and platform_count >= 2) or delta_30m >= 12:
        return "rising"
    if member_count >= 3 and age_hours <= 2:
        return "watch"
    return "new"


def _rule_title(event: dict[str, Any]) -> str:
    title = str(event.get("title") or "").strip()
    if title:
        return title
    platforms = " / ".join(event.get("platforms", [])[:3])
    return f"{platforms or '多平台'}热点事件"


def _rule_reason(event: dict[str, Any], details: dict[str, float], level: str) -> str:
    parts = [
        f"{event.get('platform_count', 0)} 个平台同时出现",
        f"30 分钟新增 {int(details.get('delta_mentions_30m', 0) or 0)} 条",
    ]
    if level == "breakout" and details.get("acceleration", 0) > 0:
        parts.append(f"速度加成 {details.get('acceleration', 0):.1f}")
    elif level == "rising":
        parts.append("热度正在明显抬升")
    return "，".join(parts)


def _event_change_state(event: dict[str, Any], previous: dict[str, Any] | None) -> str:
    if str(event.get("alert_state") or "") == "cooling":
        return "cooling_event"
    if not previous:
        return "new_event"
    current_member_count = int(event.get("member_count", 0) or 0)
    previous_member_count = int(previous.get("member_count", 0) or 0)
    current_platform_count = int(event.get("platform_count", 0) or 0)
    previous_platform_count = int(previous.get("platform_count", 0) or 0)
    if current_member_count > previous_member_count or current_platform_count > previous_platform_count:
        return "growing_event"
    return "stable_event"


def _event_to_snapshot(event: dict[str, Any], captured_at: str) -> dict[str, Any]:
    snapshot_seed = f"{event['id']}|{captured_at}"
    return {
        "id": f"snap-{hashlib.sha1(snapshot_seed.encode('utf-8')).hexdigest()[:12]}",
        "event_id": event["id"],
        "captured_at": captured_at,
        "member_count": event["member_count"],
        "platform_count": event["platform_count"],
        "source_count": event["source_count"],
        "velocity_score": event["velocity_score"],
        "coverage_score": event["coverage_score"],
        "freshness_score": event["freshness_score"],
        "composite_score": event["composite_score"],
        "alert_state": event["alert_state"],
    }


def _carry_forward_stale_events(
    events: list[dict[str, Any]],
    previous_events: list[dict[str, Any]],
    active_ids: set[str],
    captured_at: datetime,
) -> list[dict[str, Any]]:
    carried: list[dict[str, Any]] = []
    for event in previous_events:
        event_id = str(event.get("id") or "")
        if not event_id or event_id in active_ids:
            continue
        last_seen = parse_time(event.get("last_seen_at"))
        if not last_seen or (captured_at - last_seen).total_seconds() > 48 * 3600:
            continue
        preserved = dict(event)
        preserved["alert_state"] = "cooling"
        preserved["velocity_score"] = 0.0
        preserved["composite_score"] = round(
            float(preserved.get("coverage_score", 0) or 0) * 0.35
            + float(preserved.get("freshness_score", 0) or 0) * 0.25,
            1,
        )
        preserved["change_state"] = "cooling_event"
        preserved["alert_reason"] = "最近没有继续增长，已进入降温观察。"
        carried.append(preserved)
    return carried


def _make_llm_service(llm_config: dict[str, Any] | None) -> LLMService | None:
    if not llm_config:
        return None
    try:
        return LLMService(llm_config)
    except Exception:
        return None


# Translation cache: key=md5[:16], value=translated text
_translation_cache: dict[str, str] = {}
_MAX_CACHE_SIZE = 200


def _translate_summary(text: str, llm_service: LLMService | None) -> str:
    """Translate summary to Chinese. Returns empty string on failure or if already Chinese."""
    if not text:
        return ""
    chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
    if len(text) > 0 and chinese_chars / len(text) > 0.5:
        return ""
    cache_key = hashlib.md5(text[:500].encode()).hexdigest()[:16]
    if cache_key in _translation_cache:
        return _translation_cache[cache_key]
    if not llm_service or not llm_service.is_available():
        return ""
    truncated = text[:1500]
    try:
        messages = [{"role": "user", "content": f"翻译成中文，只返回译文：\n{truncated}"}]
        # Use 15 second timeout for translation to avoid blocking the pipeline
        result = llm_service.generate("translation", messages, temperature=0.3, max_tokens=256, timeout=15.0)
        translated = result.get("content", "").strip()
        if translated:
            if len(_translation_cache) >= _MAX_CACHE_SIZE:
                oldest_key = next(iter(_translation_cache))
                del _translation_cache[oldest_key]
            _translation_cache[cache_key] = translated
        return translated
    except Exception:
        return ""


def build_intel_state(
    raw_items: list[dict[str, Any]],
    sources_by_key: dict[str, dict[str, Any]],
    previous_discovery_items: list[dict[str, Any]] | None = None,
    previous_events: list[dict[str, Any]] | None = None,
    previous_snapshots: list[dict[str, Any]] | None = None,
    captured_at: str | None = None,
    llm_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stamp = captured_at or now_iso()
    now = parse_time(stamp) or datetime.now(UTC)
    previous_events = previous_events or []
    previous_snapshots = previous_snapshots or []
    previous_events_by_id = {str(item.get("id")): item for item in previous_events if item.get("id")}

    discovery_items = build_discovery_items(raw_items, sources_by_key, previous_discovery_items=previous_discovery_items)
    clusters = cluster_discovery_items(discovery_items, sources_by_key, reference_time=now)
    events: list[dict[str, Any]] = []
    llm_service = _make_llm_service(llm_config)

    for cluster in clusters:
        primary = _representative_item(cluster, sources_by_key)
        event_id = _event_id_for_cluster(cluster, primary)
        previous = previous_events_by_id.get(event_id, {})
        source_keys = sorted({str(item.get("source_key") or "") for item in cluster if item.get("source_key")})
        source_names = sorted({str(item.get("source_name") or "") for item in cluster if item.get("source_name")})
        platforms = sorted({str(item.get("platform") or "") for item in cluster if item.get("platform")})
        tags = sorted({tag for item in cluster for tag in item.get("tags", [])})
        first_seen, last_seen = _event_time_bounds(cluster)
        if previous.get("first_seen_at"):
            previous_first_seen = parse_time(previous.get("first_seen_at"))
            new_first_seen = parse_time(first_seen)
            if previous_first_seen and new_first_seen and previous_first_seen < new_first_seen:
                first_seen = previous_first_seen.replace(microsecond=0).isoformat()
        discovery_item_ids = [
            item_id
            for item in cluster
            for item_id in item.get("story_discovery_item_ids", [item.get("id")])
            if item_id
        ]
        event = {
            "id": event_id,
            "title": _rule_title(primary),
            "summary": primary.get("summary") or primary.get("content") or primary.get("title"),
            "representative_link": primary.get("link"),
            "representative_source_name": primary.get("source_name"),
            "representative_discovery_item_id": primary.get("id"),
            "discovery_item_ids": discovery_item_ids,
            "source_keys": source_keys,
            "source_names": source_names,
            "platforms": platforms,
            "platform_count": len(platforms),
            "source_count": len(source_keys),
            "member_count": len(discovery_item_ids),
            "story_count": len(cluster),
            "member_delta": 0,
            "platform_delta": 0,
            "published_at": primary.get("published_at"),
            "latest_collected_at": max((item.get("collected_at") for item in cluster), key=lambda value: parse_time(value) or datetime.min.replace(tzinfo=UTC)) if cluster else stamp,
            "first_seen_at": first_seen or primary.get("published_at") or primary.get("collected_at") or stamp,
            "last_seen_at": last_seen or primary.get("collected_at") or stamp,
            "tags": tags,
            "anchor_tokens": sorted({token for item in cluster for token in item.get("anchor_tokens", [])}),
            "representative_engagement_score": float(primary.get("engagement_score", 0) or 0),
            "watchlisted": bool(previous.get("watchlisted", False)),
            "ignored": bool(previous.get("ignored", False)),
        }
        velocity_score, velocity_details = _velocity_score(event, previous_snapshots, now)
        event["velocity_score"] = velocity_score
        event["coverage_score"] = _coverage_score(event, sources_by_key)
        event["freshness_score"] = _freshness_score(event, now)
        event["composite_score"] = round(
            event["velocity_score"] * 0.4 + event["coverage_score"] * 0.35 + event["freshness_score"] * 0.25,
            1,
        )
        event["velocity_details"] = velocity_details
        event["alert_state"] = _alert_state(event, velocity_details, now)
        previous_member_count = int(previous.get("member_count", 0) or 0)
        previous_platform_count = int(previous.get("platform_count", 0) or 0)
        event["member_delta"] = int(event["member_count"]) - previous_member_count
        event["platform_delta"] = int(event["platform_count"]) - previous_platform_count
        event["change_state"] = _event_change_state(event, previous)
        event["alert_reason"] = _rule_reason(event, velocity_details, event["alert_state"])
        try:
            extracted_entities = extract_entities(
                " ".join(
                    part for part in [
                        str(event.get("title") or "").strip(),
                        str(event.get("summary") or "").strip(),
                    ]
                    if part
                )
            )
        except Exception:
            extracted_entities = []
        event["entity_ids"] = [item["entity_id"] for item in extracted_entities if item.get("entity_id")]
        event["entity_names"] = [item["entity_name"] for item in extracted_entities if item.get("entity_name")]
        event["summary_translated"] = ""
        events.append(event)

    active_ids = {item["id"] for item in events}
    events.extend(_carry_forward_stale_events(events, previous_events, active_ids, now))

    events.sort(key=lambda item: (ALERT_LEVELS.get(str(item.get("alert_state")), 0), float(item.get("composite_score", 0) or 0)), reverse=True)

    # Parallel translation for events without translation (skip carry-forward events that already have it)
    if llm_service and llm_service.is_available():
        events_needing_translation = [
            (e["id"], e.get("summary") or "") for e in events if not e.get("summary_translated")
        ]
        if events_needing_translation:
            def _translate_one(item: tuple[str, str]) -> tuple[str, str]:
                return (item[0], _translate_summary(item[1], llm_service))

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(_translate_one, item): item[0] for item in events_needing_translation}
                for future in as_completed(futures):
                    event_id, translated = future.result()
                    for event in events:
                        if event["id"] == event_id:
                            event["summary_translated"] = translated
                            break

    retained_snapshots = [
        item for item in previous_snapshots
        if (parse_time(item.get("captured_at")) or datetime.min.replace(tzinfo=UTC)) >= now - timedelta(hours=48)
    ]
    snapshots = retained_snapshots + [_event_to_snapshot(event, stamp) for event in events]

    alerts: list[dict[str, Any]] = []
    for event in events:
        level = str(event.get("alert_state") or "new")
        if level not in {"watch", "rising", "breakout"} or event.get("ignored"):
            continue
        alerts.append(
            {
                "id": f"alert-{event['id']}-{level}",
                "event_id": event["id"],
                "title": event["title"],
                "level": level,
                "reason": event["alert_reason"],
                "velocity_score": event["velocity_score"],
                "coverage_score": event["coverage_score"],
                "freshness_score": event["freshness_score"],
                "composite_score": event["composite_score"],
                "platform_count": event["platform_count"],
                "source_count": event["source_count"],
                "representative_link": event["representative_link"],
                "triggered_at": stamp,
                "entity_ids": list(event.get("entity_ids", [])),
                "entity_names": list(event.get("entity_names", [])),
                "summary_translated": event.get("summary_translated") or "",
            }
        )
    alerts.sort(key=lambda item: (ALERT_LEVELS.get(item["level"], 0), item["composite_score"]), reverse=True)

    return {
        "discovery_items": discovery_items,
        "intel_events": events,
        "event_snapshots": snapshots,
        "intel_alerts": alerts,
    }
