from __future__ import annotations

from typing import Any


def _api_source(
    key: str,
    name: str,
    driver: str,
    *,
    priority: int,
    schedule: str = "*/20 * * * *",
    tags: list[str] | None = None,
    auth: dict[str, str] | None = None,
    platform: str | None = None,
    weight: float | None = None,
) -> dict[str, Any]:
    detected_platform = platform or driver
    return {
        "key": key,
        "name": name,
        "platform": detected_platform,
        "kind": "api",
        "driver": driver,
        "enabled": True,
        "schedule": schedule,
        "interval_minutes": 20,
        "priority": priority,
        "weight": weight if weight is not None else 0.6,
        "auth": auth or {},
        "url": None,
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
        _api_source("reddit-chatgpt", "Reddit r/ChatGPT", "reddit_hot", priority=7, tags=["community", "ai"], auth={"subreddit": "ChatGPT"}, platform="reddit", weight=0.8),
        _api_source("reddit-claudeai", "Reddit r/ClaudeAI", "reddit_hot", priority=7, tags=["community", "ai"], auth={"subreddit": "ClaudeAI"}, platform="reddit", weight=0.8),
        _api_source("reddit-local-llama", "Reddit r/LocalLLaMA", "reddit_hot", priority=6, tags=["community", "oss"], auth={"subreddit": "LocalLLaMA"}, platform="reddit", weight=0.8),
        _api_source("reddit-machinelearning", "Reddit r/MachineLearning", "reddit_hot", priority=7, tags=["community", "research"], auth={"subreddit": "MachineLearning"}, platform="reddit", weight=0.8),
        _api_source("reddit-singularity", "Reddit r/singularity", "reddit_hot", priority=6, tags=["community", "future"], auth={"subreddit": "singularity"}, platform="reddit", weight=0.8),
        _api_source("hn-frontpage", "Hacker News Front Page", "hackernews_frontpage", priority=8, tags=["community", "hn"], platform="hackernews", weight=0.8),
        _api_source("github-trending", "GitHub Trending", "github_trending", priority=7, tags=["oss", "github"], platform="github", weight=0.8),
        _api_source("vvhan-hotlist", "VVhan 热榜聚合", "vvhan_hotlist", priority=7, schedule="*/15 * * * *", tags=["cn", "hot"], platform="vvhan", weight=0.6),
    ]
