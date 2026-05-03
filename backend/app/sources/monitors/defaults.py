from __future__ import annotations

from typing import Any


def _yt(
    key: str,
    name: str,
    channel_id: str,
    *,
    priority: int,
    schedule: str = "*/60 * * * *",
    tags: list[str] | None = None,
    weight: float | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "platform": "youtube",
        "kind": "monitor",
        "driver": "youtube_channel",
        "enabled": True,
        "schedule": schedule,
        "interval_minutes": 60,
        "priority": priority,
        "weight": weight if weight is not None else 0.8,
        "auth": {"channel_id": channel_id},
        "url": f"https://www.youtube.com/channel/{channel_id}",
        "tags": tags or [],
        "capabilities": ["pull", "dedupe", "score"],
        "origin_repo": "auto-news-studio",
        "origin_license": "MIT",
        "health_status": "idle",
        "health_detail": "",
        "item_count": 0,
        "last_synced_at": None,
        "last_error": None,
        "updated_at": None,
    }


def register() -> list[dict[str, Any]]:
    return [
        _yt("yt-google", "Google", "UCBR8-60-B28hp2BmDPdntcYw", priority=9, tags=["tech", "official"], weight=0.9),
        _yt("yt-openai", "OpenAI", "UCmE2kSPbvbgeFbLGeCvI_VQ", priority=9, tags=["ai", "official"], weight=0.9),
        _yt("yt-deepseek", "DeepSeek", "UCvOgS2-6EyLkXg2G7CjlrQw", priority=8, tags=["ai", "cn"], weight=0.85),
        _yt("yt-vivo", "vivo", "UCDkIRrLsdUyNUmrYmGKJzwg", priority=7, tags=["cn", "digital"], weight=0.8),
        _yt("yt-mkbhd", "MKBHD", "UCBJycsmduvYEL83R_U4JriQ", priority=8, tags=["tech", "review"], weight=0.85),
        _yt("yt-googletech", "Google Tech", "UCtq06qzQ2ATWNaLD6vP6xqA", priority=7, tags=["tech", "dev"], weight=0.8),
    ]
