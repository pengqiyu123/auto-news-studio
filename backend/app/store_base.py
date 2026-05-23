"""Base constants, utilities, and state management for StudioStore."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
import re
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LEGACY_DATA_DIR = PROJECT_ROOT / "backend" / "data"
DATA_DIR = PROJECT_ROOT / "data"
DATA_STATE_DIR = DATA_DIR / "state"
DATA_FILE = DATA_STATE_DIR / "state.json"
LEGACY_DATA_FILE = DATA_DIR / "state.json"
LEGACY_BACKEND_DATA_FILE = LEGACY_DATA_DIR / "state.json"
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_FILE = CONFIG_DIR / "user-settings.json"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
RUNTIME_CACHE_DIR = RUNTIME_DIR / "cache"
RUNTIME_LOG_DIR = RUNTIME_DIR / "logs"
RUNTIME_TEMP_DIR = RUNTIME_DIR / "temp"
BACKUP_DIR = RUNTIME_DIR / "backups"
LOG_DIR = RUNTIME_LOG_DIR
DIST_DIR = PROJECT_ROOT / "dist"
VERSION_FILE = PROJECT_ROOT / "version.json"
UTC = timezone.utc
LOCAL_TZ = timezone(timedelta(hours=8))

MAX_RAW_ITEMS = int(os.environ.get("MAX_RAW_ITEMS", "480"))
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
SOURCE_TIMEOUT_SECONDS = int(os.environ.get("SOURCE_TIMEOUT_SECONDS", "12"))
SLOW_SOURCE_WARNING_SECONDS = int(os.environ.get("SLOW_SOURCE_WARNING_SECONDS", "8"))
SOURCE_COLLECTION_STALL_SECONDS = max(SOURCE_TIMEOUT_SECONDS * 5, int(os.environ.get("SOURCE_COLLECTION_STALL_SECONDS", "60")))
RUN_STALE_SECONDS = int(os.environ.get("RUN_STALE_SECONDS", "180"))
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
        {"key": "deep_dive", "label": "正文深挖"},
        {"key": "briefing", "label": "生成简报"},
    ],
    "full_pipeline": [
        {"key": "collecting", "label": "采集素材"},
        {"key": "clustering", "label": "聚合热点事件"},
        {"key": "scoring", "label": "判断热度与预警"},
        {"key": "deep_dive", "label": "正文深挖"},
        {"key": "briefing", "label": "生成简报"},
        {"key": "wechat_sync", "label": "上传微信草稿箱"},
        {"key": "wechat_verify", "label": "回查草稿箱"},
    ],
}

INTENT_STAGE_PLANS: dict[str, list[dict[str, str]]] = {
    "collect_validation": [{"key": "collecting", "label": "采集素材"}],
    "event_rebuild": [{"key": "clustering", "label": "重建热点事件"}],
    "alert_rebuild": [{"key": "scoring", "label": "重算预警"}],
}


DEFAULT_USER_SETTINGS: dict[str, Any] = {
    "schema_version": 1,
    "llm": {
        "current_profile_id": "",
        "fallback_profile_id": None,
        "profiles": [],
        "providers": [],
    },
    "wechat": {
        "app_id": "",
        "app_secret_masked": "",
        "author": "Auto News Studio",
        "default_cover_strategy": "auto",
        "default_digest_strategy": "balanced",
        "draft_mode": True,
        "preview_enabled": True,
        "auto_send_window": "09:00-10:00",
        "risk_keywords": [],
        "browser_name": "edge",
        "browser_profile_path": "",
        "publish_entry_url": "https://mp.weixin.qq.com/",
        "selectors_version": "wechat-mp-v1",
        "sidecar_url": "http://127.0.0.1:8091",
    },
    "sources": {"overrides": {}},
    "settings": {
        "max_workers": 8,
        "tavily_api_key": "",
    },
}

DEFAULT_APP_VERSION = "0.2.10"
DEFAULT_RELEASE_CHANNEL = "stable"
DEFAULT_RELEASE_REPO = "pengqiyu123/auto-news-studio"
DEFAULT_RELEASE_NOTES_URL = "https://github.com/pengqiyu123/auto-news-studio/releases"


def _same_path(left: Path, right: Path) -> bool:
    return str(Path(left).resolve()).lower() == str(Path(right).resolve()).lower()


def _uses_project_default_state_paths(primary: Path) -> bool:
    return any(
        _same_path(primary, candidate)
        for candidate in (DATA_FILE, LEGACY_DATA_FILE, LEGACY_BACKEND_DATA_FILE)
    )


def derive_config_file_for_data_file(data_file: Path) -> Path:
    path = Path(data_file)
    base_dir = path.parent.parent if path.parent.name.lower() == "data" else path.parent
    return base_dir / "config" / CONFIG_FILE.name


def candidate_state_files(primary: Path | None = None) -> list[Path]:
    primary_file = Path(primary or DATA_FILE)
    if not _uses_project_default_state_paths(primary_file):
        return [primary_file]
    candidates: list[Path] = []
    for path in (primary_file, LEGACY_DATA_FILE, LEGACY_BACKEND_DATA_FILE):
        if path not in candidates:
            candidates.append(path)
    return candidates


def resolve_existing_state_file(primary: Path | None = None) -> Path:
    primary_file = Path(primary or DATA_FILE)
    existing = [candidate for candidate in candidate_state_files(primary_file) if candidate.exists()]
    if existing:
        existing.sort(
            key=lambda path: (
                path.stat().st_mtime,
                1 if _same_path(path, primary_file) else 0,
            ),
            reverse=True,
        )
        return existing[0]
    return primary_file


def load_version_manifest() -> dict[str, Any]:
    payload = read_json_file(VERSION_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "version": str(payload.get("version") or DEFAULT_APP_VERSION).strip() or DEFAULT_APP_VERSION,
        "release_channel": str(payload.get("release_channel") or DEFAULT_RELEASE_CHANNEL).strip() or DEFAULT_RELEASE_CHANNEL,
        "release_repo": str(payload.get("release_repo") or DEFAULT_RELEASE_REPO).strip() or DEFAULT_RELEASE_REPO,
        "release_notes_url": str(payload.get("release_notes_url") or DEFAULT_RELEASE_NOTES_URL).strip() or DEFAULT_RELEASE_NOTES_URL,
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


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    temp_file = path.with_name(f"{path.stem}.{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.tmp")
    temp_file.write_text(content, encoding="utf-8")
    temp_file.replace(path)


def read_json_file(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return deepcopy_json(default or {})
    return json.loads(path.read_text(encoding="utf-8"))


def deepcopy_json(value: Any) -> Any:
    return deepcopy(value)


def backup_file(path: Path, backup_root: Path, prefix: str) -> Path | None:
    if not path.exists():
        return None
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_root / f"{prefix}-{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    return backup_path
