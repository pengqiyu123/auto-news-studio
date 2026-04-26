from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import re
from typing import Any


UTC = timezone.utc

CORE_KEYWORDS = [
    "ai",
    "agent",
    "大模型",
    "人工智能",
    "openai",
    "claude",
    "gemini",
    "copilot",
    "browser",
    "自动化",
    "wechat",
    "公众号",
    "github",
    "startup",
    "芯片",
    "gpu",
    "nvidia",
]

JUNK_KEYWORDS = [
    "coupon",
    "sponsored",
    "tutorial",
    "newsletter",
    "课程",
    "教程",
    "直播回放",
]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        try:
            return parsedate_to_datetime(value).astimezone(UTC)
        except Exception:
            return datetime.now(UTC)


def dedupe_key(title: str, link: str) -> str:
    compact = re.sub(r"\W+", "", (title or "").lower())
    if compact:
        return compact[:80]
    return hashlib.sha1(link.encode("utf-8")).hexdigest()[:40]


def _tokenize(text: str) -> set[str]:
    lowered = text.lower()
    ascii_tokens = {token for token in re.findall(r"[a-z0-9]{3,}", lowered)}
    zh_tokens = {token for token in re.findall(r"[\u4e00-\u9fff]{2,6}", text)}
    return ascii_tokens | zh_tokens


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    return len(left & right) / max(len(left | right), 1)


def _is_relevant(item: dict[str, Any]) -> bool:
    combined = f"{item['title']} {item.get('summary', '')}".lower()
    if any(keyword in combined for keyword in JUNK_KEYWORDS):
        return False
    if any(keyword in combined for keyword in CORE_KEYWORDS):
        return True
    return item.get("engagement", {}).get("score", 0) >= 120


def _source_weight(priority: int, source_count: int) -> float:
    base = 0.42 + priority * 0.045
    spread = min(source_count * 0.08, 0.28)
    return round(min(base + spread, 1.24), 2)


def _score_group(items: list[dict[str, Any]], priority: int) -> tuple[float, dict[str, float], list[str]]:
    latest = max(items, key=lambda item: _parse_time(item["published_at"]))
    hours_ago = max((datetime.now(UTC) - _parse_time(latest["published_at"])).total_seconds() / 3600, 0.0)
    recency = round(max(0.0, 30.0 - min(hours_ago, 30.0)), 1)
    engagement = sum(float(item.get("engagement", {}).get("score", 0)) for item in items)
    engagement_score = round(min(24.0, engagement / 22.0), 1)
    coverage = round(min(18.0, len({item['source_name'] for item in items}) * 4.5), 1)
    weight = round(_source_weight(priority, len(items)) * 20, 1)
    total = round(min(100.0, recency + engagement_score + coverage + weight), 1)
    breakdown = {
        "recency": recency,
        "engagement": engagement_score,
        "coverage": coverage,
        "weight": weight,
    }
    signals = [
        f"来源优先级 {priority}/10",
        f"{len(items)} 条素材落在同一事件簇",
        f"最近信号距今 {hours_ago:.1f} 小时",
    ]
    return total, breakdown, signals


def _cluster_items(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not items:
        return []
    parent = list(range(len(items)))
    tokens = [_tokenize(item["title"]) for item in items]

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_left] = root_right

    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            same_link = items[left]["link"] == items[right]["link"]
            same_dedupe = dedupe_key(items[left]["title"], items[left]["link"]) == dedupe_key(items[right]["title"], items[right]["link"])
            similar = _jaccard(tokens[left], tokens[right]) >= 0.32
            if same_link or same_dedupe or similar:
                union(left, right)

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(items):
        grouped[find(index)].append(item)
    return list(grouped.values())


def normalize_raw_items(
    raw_items: list[dict[str, Any]],
    sources_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    relevant = [item for item in raw_items if _is_relevant(item)]
    clustered = _cluster_items(relevant)
    normalized: list[dict[str, Any]] = []
    for cluster in clustered:
        primary = sorted(cluster, key=lambda item: _parse_time(item["published_at"]), reverse=True)[0]
        priorities = [
            int(sources_by_key.get(item["source_key"], {}).get("priority", 5))
            for item in cluster
        ]
        priority = max(priorities) if priorities else 5
        score, breakdown, signals = _score_group(cluster, priority)
        normalized.append(
            {
                "id": f"norm-{hashlib.sha1(dedupe_key(primary['title'], primary['link']).encode('utf-8')).hexdigest()[:10]}",
                "raw_item_ids": [item["id"] for item in cluster],
                "title": primary["title"],
                "link": primary["link"],
                "summary": primary["summary"],
                "published_at": primary["published_at"],
                "cluster_id": f"cluster-{hashlib.sha1(primary['title'].lower().encode('utf-8')).hexdigest()[:10]}",
                "cluster_members": [item["title"] for item in cluster],
                "dedupe_key": dedupe_key(primary["title"], primary["link"]),
                "source_names": sorted({item["source_name"] for item in cluster}),
                "origin_sources": sorted({item["source_key"] for item in cluster}),
                "source_weight": _source_weight(priority, len(cluster)),
                "trend_score": score,
                "final_score": round(min(100.0, score + min(len(cluster) * 2.2, 8.0)), 1),
                "signals": signals,
                "score_breakdown": breakdown,
            }
        )
    normalized.sort(key=lambda item: item["final_score"], reverse=True)
    return normalized


def _facts_for_item(item: dict[str, Any]) -> list[str]:
    return [
        f"核心事件：{item['title']}",
        f"传播概况：已有 {len(item['source_names'])} 个来源进入同一事件簇",
        f"判断依据：{item['signals'][0]}，综合得分 {item['final_score']}",
    ]


def _angles_for_item(item: dict[str, Any]) -> list[dict[str, str]]:
    summary = item["summary"]
    return [
        {
            "name": "快讯判断",
            "tone": "简洁",
            "focus": "先说发生了什么，再给公众号读者一个判断。",
            "why": summary or "适合当天快评。",
        },
        {
            "name": "行业观察",
            "tone": "分析",
            "focus": "从行业变化、组织动作和二阶影响切入。",
            "why": "适合做专题过渡稿。",
        },
        {
            "name": "操作指南",
            "tone": "实用",
            "focus": "把读者最关心的下一步行动说清楚。",
            "why": "适合沉淀高转发内容。",
        },
    ]


def _article_type(score: float) -> str:
    if score >= 85:
        return "深度"
    if score >= 72:
        return "专题"
    return "快讯"


def build_candidates(normalized_items: list[dict[str, Any]], current_mode: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in normalized_items[:16]:
        angles = _angles_for_item(item)
        selected = angles[0]["focus"]
        candidates.append(
            {
                "id": f"cand-{hashlib.sha1(item['id'].encode('utf-8')).hexdigest()[:10]}",
                "normalized_item_id": item["id"],
                "title": item["title"],
                "summary": item["summary"],
                "recommended_angle": selected,
                "article_type": _article_type(item["final_score"]),
                "rationale": "；".join(item["signals"]),
                "evidence_links": [item["link"]],
                "source_names": item["source_names"],
                "source_count": len(item["source_names"]),
                "score": item["final_score"],
                "status": "new",
                "recommended_mode": current_mode if item["final_score"] >= 70 else "draft_only",
                "facts": _facts_for_item(item),
                "angles": angles,
                "selected_angle": selected,
                "score_breakdown": item["score_breakdown"],
                "published_at": item.get("published_at"),
                "collected_at": item.get("collected_at"),
                "freshness_bucket": item.get("freshness_bucket", "unknown"),
                "draft_exists": False,
                "normalized_score": item.get("final_score", 0.0),
                "updated_at": now_iso(),
            }
        )
    return candidates
