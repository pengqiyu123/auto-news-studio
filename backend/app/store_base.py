"""Base constants, utilities, and state management for StudioStore."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import re
from pathlib import Path
from typing import Any


DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "state.json"
UTC = timezone.utc
LOCAL_TZ = timezone(timedelta(hours=8))
MAX_RAW_ITEMS = 480
SYNTHETIC_MARKERS = (
    "example.com/",
    "当前为回退样例",
    "已回退到样例素材",
    "可用样例素材",
    "样例数据",
)
UNSUPPORTED_SOURCE_DRIVERS = {
    "legacy_bilibili",
    "legacy_toutiao",
    "legacy_youtube",
    "newsnow_pool",
}
SOURCE_TIMEOUT_SECONDS = 12
SLOW_SOURCE_WARNING_SECONDS = 8
SOURCE_COLLECTION_STALL_SECONDS = max(SOURCE_TIMEOUT_SECONDS * 5, 60)
RUN_STALE_SECONDS = 180
DEFAULT_RUNTIME_INTENT = "normal_monitoring"
INTENT_TO_WORK_SCOPE: dict[str, str] = {
    "normal_monitoring": "collect_events_alerts",
    "collect_validation": "collect_only",
    "event_rebuild": "collect_events",
    "alert_rebuild": "collect_events_alerts",
}

MODE_STAGE_PLANS: dict[str, list[dict[str, str]]] = {
    "radar_only": [
        {"key": "collecting", "label": "采集素材"},
        {"key": "clustering", "label": "聚合热点事件"},
        {"key": "scoring", "label": "判断热度与预警"},
    ],
    "radar_and_draft": [
        {"key": "collecting", "label": "采集素材"},
        {"key": "clustering", "label": "聚合热点事件"},
        {"key": "scoring", "label": "判断热度与预警"},
        {"key": "drafting", "label": "生成稿件"},
    ],
    "full_pipeline": [
        {"key": "collecting", "label": "采集素材"},
        {"key": "clustering", "label": "聚合热点事件"},
        {"key": "scoring", "label": "判断热度与预警"},
        {"key": "drafting", "label": "生成稿件"},
        {"key": "wechat_sync", "label": "分发与同步"},
    ],
}

INTENT_STAGE_PLANS: dict[str, list[dict[str, str]]] = {
    "collect_validation": [{"key": "collecting", "label": "采集素材"}],
    "event_rebuild": [{"key": "clustering", "label": "重建热点事件"}],
    "alert_rebuild": [{"key": "scoring", "label": "重算预警"}],
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


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


def minutes_between(start: str | None, end: str | None) -> float | None:
    start_dt = parse_time(start)
    end_dt = parse_time(end)
    if not start_dt or not end_dt:
        return None
    return round(max((end_dt - start_dt).total_seconds() / 60, 0.0), 1)


def schedule_to_minutes(schedule: str | None) -> int | None:
    if not schedule:
        return None
    compact = schedule.strip()
    fixed = {
        "*/15 * * * *": 15,
        "*/20 * * * *": 20,
        "*/30 * * * *": 30,
        "*/45 * * * *": 45,
        "0 * * * *": 60,
        "0 */4 * * *": 240,
    }
    if compact in fixed:
        return fixed[compact]
    match = re.fullmatch(r"\*/(\d+)\s+\*\s+\*\s+\*\s+\*", compact)
    if match:
        return max(int(match.group(1)), 1)
    return None


def parse_clock_time(value: str | None) -> tuple[int, int] | None:
    compact = str(value or "").strip()
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", compact)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def freshness_bucket(collected_at: str | None) -> str:
    collected_dt = parse_time(collected_at)
    if not collected_dt:
        return "unknown"
    delta_minutes = (datetime.now(UTC) - collected_dt).total_seconds() / 60
    if delta_minutes <= 15:
        return "fresh"
    if delta_minutes <= 60:
        return "recent"
    if delta_minutes <= 360:
        return "aging"
    return "stale"


def _contains_synthetic_marker(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (dict, list, tuple, set)):
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    else:
        text = str(value)
    return any(marker in text for marker in SYNTHETIC_MARKERS)


def _is_synthetic_raw_item(item: dict[str, Any]) -> bool:
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
    return bool(
        metadata.get("fallback")
        or _contains_synthetic_marker(item.get("link"))
        or _contains_synthetic_marker(item.get("summary"))
        or _contains_synthetic_marker(item.get("content"))
        or _contains_synthetic_marker(metadata)
    )


def _extract_json_payload(text: str) -> Any | None:
    compact = str(text or "").strip()
    if not compact:
        return None
    if compact.startswith("```"):
        compact = re.sub(r"^```(?:json)?\s*", "", compact)
        compact = re.sub(r"\s*```$", "", compact)
    try:
        return json.loads(compact)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", compact)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
