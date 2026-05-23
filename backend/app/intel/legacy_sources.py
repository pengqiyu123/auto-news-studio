from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml


LEGACY_ROOT = Path(r"D:\python\auto-news")
CONFIG_EXAMPLE = LEGACY_ROOT / "config.example.yaml"
PRESET_SOURCES = LEGACY_ROOT / "preset_sources.yaml"
SOURCE_STATUS = LEGACY_ROOT / "data" / "source_status.yaml"


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "legacy-source"


def _priority(category: str, name: str) -> int:
    cat = category.lower()
    title = name.lower()
    if any(keyword in title for keyword in ["openai", "anthropic", "deepmind", "google ai", "apple newsroom", "microsoft ai"]):
        return 9
    if cat in {"ai", "cloud", "dev", "company"}:
        return 8
    if cat in {"chip", "startup", "tech", "digital"}:
        return 7
    return 6


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _collect_from_config() -> list[dict[str, Any]]:
    payload = _load_yaml(CONFIG_EXAMPLE)
    results: list[dict[str, Any]] = []
    for source in payload.get("rss_sources", []):
        url = str(source.get("url", "")).strip()
        name = str(source.get("name", "")).strip()
        if not url or not name:
            continue
        category = str(source.get("category", "legacy")).strip() or "legacy"
        language = str(source.get("language", "en")).strip() or "en"
        results.append(
            {
                "name": name,
                "url": url,
                "category": category,
                "language": language,
                "description": "",
            }
        )
    return results


def _collect_from_presets() -> list[dict[str, Any]]:
    payload = _load_yaml(PRESET_SOURCES)
    results: list[dict[str, Any]] = []
    for category, config in payload.get("categories", {}).items():
        for source in config.get("sources", []):
            url = str(source.get("url", "")).strip()
            name = str(source.get("name", "")).strip()
            if not url or not name:
                continue
            results.append(
                {
                    "name": name,
                    "url": url,
                    "category": category,
                    "language": str(source.get("language", "en")).strip() or "en",
                    "description": str(source.get("description", "")).strip(),
                }
            )
    return results


def _load_status_map() -> dict[str, dict[str, Any]]:
    payload = _load_yaml(SOURCE_STATUS)
    return {str(key): value for key, value in payload.items()} if isinstance(payload, dict) else {}


def build_legacy_rss_sources() -> list[dict[str, Any]]:
    if not LEGACY_ROOT.exists():
        return []
    status_map = _load_status_map()
    merged_by_url: dict[str, dict[str, Any]] = {}

    for source in [*_collect_from_config(), *_collect_from_presets()]:
        status = status_map.get(source["url"], {})
        merged = {
            **source,
            "status": str(status.get("status", "unknown")),
            "success_count": int(status.get("success_count", 0) or 0),
            "avg_items": int(status.get("avg_items", 0) or 0),
            "last_items": int(status.get("last_items", 0) or 0),
        }
        previous = merged_by_url.get(source["url"])
        if not previous or merged["success_count"] > previous["success_count"]:
            merged_by_url[source["url"]] = merged

    ranked = sorted(
        merged_by_url.values(),
        key=lambda item: (
            item["status"] != "success",
            -item["success_count"],
            -item["last_items"],
            item["name"],
        ),
    )

    selected: list[dict[str, Any]] = []
    for index, source in enumerate(ranked[:28]):
        tags = sorted({source["category"], source["language"], "legacy"})
        detail = f"来自旧项目沉淀源；success_count={source['success_count']} last_items={source['last_items']}"
        if source["description"]:
            detail = f"{source['description']}；{detail}"
        selected.append(
            {
                "key": f"legacy-{_slug(source['name'])}",
                "name": source["name"],
                "kind": "rss",
                "driver": "feedparser",
                "enabled": index < 18,
                "schedule": "*/30 * * * *" if source["language"] == "en" else "*/20 * * * *",
                "priority": _priority(source["category"], source["name"]),
                "auth": {},
                "url": source["url"],
                "tags": tags,
                "capabilities": ["rss", "legacy-import"],
                "origin_repo": "local/auto-news",
                "origin_license": "local",
                "health_status": "idle",
                "health_detail": detail,
                "item_count": 0,
                "last_synced_at": None,
                "last_error": None,
                "updated_at": None,
            }
        )
    return selected
