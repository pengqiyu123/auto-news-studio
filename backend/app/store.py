from __future__ import annotations

from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from html import escape
import json
import os
import shutil
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile
from pathlib import Path
import re
from threading import RLock, Thread
from typing import Any
from uuid import uuid4
import xml.etree.ElementTree as ET

from .store_base import (
    BACKUP_DIR,
    CONFIG_FILE,
    CONFIG_DIR,
    DATA_FILE,
    DEFAULT_RUNTIME_INTENT,
    DEFAULT_RELEASE_NOTES_URL,
    DEFAULT_RELEASE_REPO,
    DEFAULT_USER_SETTINGS,
    INTENT_STAGE_PLANS,
    INTENT_TO_WORK_SCOPE,
    LOG_DIR,
    LOCAL_TZ,
    LOCAL_TZ as LTZ,
    load_version_manifest,
    MAX_RAW_ITEMS,
    MODE_STAGE_PLANS,
    RUN_STALE_SECONDS,
    SLOW_SOURCE_WARNING_SECONDS,
    SOURCE_COLLECTION_STALL_SECONDS,
    SOURCE_TIMEOUT_SECONDS,
    SYNTHETIC_MARKERS,
    UTC,
    UNSUPPORTED_SOURCE_DRIVERS,
    atomic_write_json,
    backup_file,
    _contains_synthetic_marker,
    deepcopy_json,
    _extract_json_payload,
    _is_synthetic_raw_item,
    ensure_parent_dir,
    freshness_bucket,
    local_now,
    minutes_between,
    now_iso,
    parse_clock_time,
    parse_time,
    read_json_file,
    schedule_to_minutes,
)

from .connectors import _collect_with_retry, collect_enabled_sources, collect_from_source
from .briefing import build_prompt_package_markdown, build_rule_brief_payload, build_agent_article_writing_guide
from .deep_dive import canonicalize_url, fetch_and_extract_link, search_tavily
from .entity_extractor import entity_id_for_name, entity_type_for_name
from .intel_pipeline import build_intel_state
from .llm import LLMService
from .legacy_sources import build_legacy_rss_sources
from .models import (
    AgentArticlePayload,
    AppUpdateInfo,
    AppVersionInfo,
    AutomationMode,
    AutomationModeDefinition,
    AutomationModeProfile,
    BriefItem,
    BrowserSessionPayload,
    BrowserSessionState,
    BriefStageCounts,
    ChannelConfigPayload,
    ChainStateCard,
    DashboardResponse,
    DashboardStats,
    DashboardTopBar,
    EventDeepDive,
    DiscoveryItem,
    EntityWatchlistItem,
    EntityWatchlistSummaryItem,
    ExecutionChainSnapshot,
    FreshnessSnapshot,
    GithubSignalItem,
    ImportBackupResponse,
    IntelAlert,
    IntelAlertsResponse,
    IntelEvent,
    IntelEventResponse,
    IntelEventsResponse,
    IntelOverviewSummary,
    IntelSummaryResponse,
    HotClusterCard,
    IntelStreamItem,
    LogItem,
    RuntimeCycleSummary,
    RuntimeIssueItem,
    RuntimeSlowSource,
    SchedulerStatus,
    PublishBackendStatus,
    PublishTask,
    ReferenceProject,
    RuntimePlan,
    RuntimeIntent,
    RuntimePlanPayload,
    SourceConnector,
    SourceConnectorPayload,
    CreateSourcePayload,
    SourceSyncResponse,
    SystemDoctorResult,
    SystemCheckItem,
    WeChatDraftSyncCheckResult,
    WeChatMappingResponse,
    WeChatMappingRow,
    WeChatMappingSnapshot,
    WeChatRemoteDraftItem,
    WeChatPublishHistorySnapshot,
    WeChatPublishRecordItem,
    WeChatChannelConfig,
    DictOkResponse,
)
from .store_llm import (
    build_provider_from_profile,
    build_runtime_tasks,
    default_llm_state,
    infer_fallback_profile_id_from_tasks,
    merge_llm_profiles,
    DEFAULT_LLM_PROFILES,
    DEFAULT_LLM_TASK_TEMPLATE,
)
from .store_defaults import (
    DEFAULT_SOURCES,
    AUTOMATION_MODE_DEFINITIONS,
    DEFAULT_AUTOMATION_PROFILES,
)
from .pipeline import normalize_raw_items
from .publishers import (
    WECHAT_BROWSER_MANAGER,
    build_remote_draft_key,
    build_preview_url,
    build_wechat_target_id,
    collect_backend_status,
    create_publish_task,
    delete_wechat_remote_draft,
    default_browser_profile_path,
    ensure_channel_defaults,
    extract_wechat_appmsg_id,
    inspect_wechat_draft_box,
    inspect_wechat_publish_history,
    inspect_wechat_session,
    launch_wechat_dashboard,
    refresh_browser_session,
    run_browser_action,
)
from .reference_projects import write_reference_baseline
from .sources import discover_sources


def _migrate_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将旧任务配置折叠为 article。"""
    if not tasks:
        return tasks

    templates_by_key = {task["task_key"]: deepcopy(task) for task in DEFAULT_LLM_TASK_TEMPLATE}
    task_keys = {str(t.get("task_key") or "") for t in tasks if t.get("task_key")}
    target_keys = {"article"}
    if task_keys <= target_keys:
        return tasks

    result_by_key: dict[str, dict[str, Any]] = {}
    for task in tasks:
        key = str(task.get("task_key") or "")
        if not key:
            continue
        if key in {"outline", "title", "summary", "translation", "judgement"}:
            key = "article"
        if key not in target_keys:
            continue
        base = deepcopy(templates_by_key.get(key, {}))
        current = result_by_key.get(key, {})
        result_by_key[key] = {
            **base,
            **current,
            **task,
            "task_key": key,
            "label": str((task.get("label") or current.get("label") or base.get("label") or key)),
        }

    ordered: list[dict[str, Any]] = []
    for key in ("article",):
        task = result_by_key.get(key)
        if task:
            ordered.append(task)
    return ordered


def automation_to_publish_mode(mode: str) -> str:
    if mode == "full_pipeline":
        return "draft_preview_browser"
    return "draft_only"


JOB_LABELS = {
    "collect_news": "雷达获取",
    "rebuild_candidates": "刷新事件聚合",
    "build_digest": "批量生成简报",
    "sync_wechat_draft": "同步微信草稿",
    "open_preview": "准备网页预览",
    "publish_pipeline": "执行浏览器发布链",
    "check_browser": "检查浏览器会话",
}


def _wechat_html(markdown: str) -> str:
    blocks: list[str] = []
    list_items: list[str] = []
    quote_items: list[str] = []

    def flush_lists() -> None:
        nonlocal list_items, quote_items
        if list_items:
            blocks.append("<ul>" + "".join(f"<li>{item}</li>" for item in list_items) + "</ul>")
            list_items = []
        if quote_items:
            blocks.append("<blockquote>" + "<br/>".join(quote_items) + "</blockquote>")
            quote_items = []

    for raw in str(markdown or "").splitlines():
        text = raw.strip()
        if not text:
            flush_lists()
            continue
        if text.startswith("# "):
            flush_lists()
            blocks.append(f"<h1>{escape(text[2:].strip())}</h1>")
            continue
        if text.startswith("## "):
            flush_lists()
            blocks.append(f"<h2>{escape(text[3:].strip())}</h2>")
            continue
        if text.startswith("- "):
            list_items.append(escape(text[2:].strip()))
            continue
        if text.startswith("> "):
            quote_items.append(escape(text[2:].strip()))
            continue
        flush_lists()
        blocks.append(f"<p>{escape(text)}</p>")

    flush_lists()
    return "<section style='font-size:15px;line-height:1.8;color:#222;'>" + "".join(blocks) + "</section>"


class StudioStore:
    def __init__(self, data_file: Path | None = None):
        self.data_file = data_file or DATA_FILE
        self.config_file = CONFIG_FILE
        self._lock = RLock()
        self._progress_snapshot: dict[str, Any] = {
            "percent": 0, "done": 0, "total": 0,
            "label": None, "cycle": "idle",
            "cycle_started_at": None,
        }
        self._completion_hold_until: float = 0.0
        self.version_manifest = load_version_manifest()
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        ensure_parent_dir(self.config_file)
        if not self.data_file.exists():
            self._write_config(self._bootstrap_user_settings())
            self._write(self._bootstrap_state())
            return
        if not self.config_file.exists():
            self._migrate_legacy_config()
        state = self._upgrade_state(self._read())
        required_keys = {"sources", "channels", "browser", "reference_projects"}
        source_shape_ok = bool(state.get("sources")) and all("driver" in item for item in state.get("sources", []))
        channel_shape_ok = "sidecar_url" in state.get("channels", {}).get("wechat", {})
        has_legacy_imports = any("legacy-import" in item.get("capabilities", []) for item in state.get("sources", []))
        if (
            not required_keys.issubset(state)
            or not source_shape_ok
            or not channel_shape_ok
            or not has_legacy_imports
        ):
            self._write(self._bootstrap_state())
        else:
            self._write(state)
        self._write_config(self._upgrade_user_settings(self._read_config()))

    def _bootstrap_state(self) -> dict[str, Any]:
        reference_projects = write_reference_baseline()
        sources = self._build_source_registry()
        state = {
            "automation_mode": "radar_only",
            "automation_mode_definitions": deepcopy(AUTOMATION_MODE_DEFINITIONS),
            "automation_profiles": deepcopy(DEFAULT_AUTOMATION_PROFILES),
            "sources": sources,
            "raw_items": [],
            "discovery_items": [],
            "intel_events": [],
            "event_snapshots": [],
            "intel_alerts": [],
            "intel_event_history": [],
            "intel_alert_history": [],
            "event_deep_dives": [],
            "briefs": [],
            "normalized_items": [],
            "publish_tasks": [],
            "jobs": [],
            "logs": [],
            "notifications": {
                "webhook": {
                    "enabled": False,
                    "url": "",
                    "secret": "",
                    "events": ["breakout"],
                },
                "delivery_log": [],
            },
            "app_meta": {
                "dismissed_update_version": None,
                "last_update_check": None,
            },
            "channels": {
                "wechat": {
                    "app_id": "",
                    "app_secret_masked": "",
                    "author": "Auto News Studio",
                    "default_cover_strategy": "auto",
                    "default_digest_strategy": "balanced",
                    "draft_mode": True,
                    "preview_enabled": True,
                    "auto_send_window": "09:00-10:00",
                    "risk_keywords": ["投资建议", "医疗建议", "未经核实", "爆料"],
                    "browser_name": "edge",
                    "browser_profile_path": str(default_browser_profile_path("edge")),
                    "publish_entry_url": "https://mp.weixin.qq.com/",
                    "selectors_version": "wechat-mp-v1",
                    "sidecar_url": "http://127.0.0.1:8091",
                }
            },
            "browser": {
                "wechat": {
                    "platform": "wechat_mp",
                    "browser_name": "edge",
                    "user_data_dir": str(default_browser_profile_path("edge")),
                    "logged_in": False,
                    "last_checked_at": None,
                    "last_opened_url": None,
                    "last_error": None,
                    "selectors_version": "wechat-mp-v1",
                    "last_screenshot": None,
                    "last_selector_check": None,
                "current_page": None,
                "sidecar_health": "offline",
                "manager_alive": False,
                "window_state": "unknown",
                "resident_page": None,
                "busy": False,
                "last_reset_reason": None,
                "session_generation": 0,
                "last_action": None,
                "last_action_phase": None,
                "is_session_level_error": False,
                "last_draft_check": None,
                }
            },
            "llm": default_llm_state(),
            "settings": {
                "max_workers": 8,
                "entity_watchlist": [],
                "tavily_api_key": "",
            },
            "reference_projects": reference_projects,
            "runtime_plan": {
                "launch_mode": "interval_now",
                "start_at": None,
                "interval_minutes": 30,
                "timezone": "Asia/Shanghai",
                "work_scope": "collect_events_alerts",
            },
            "runtime": {
                "scheduler_running": False,
                "control_state": "stopped",
                "launch_mode": "interval_now",
                "current_mode": "radar_only",
                "work_scope": "collect_events_alerts",
                "last_collect_at": None,
                "last_event_sync_at": None,
                "last_brief_at": None,
                "next_collect_at": None,
                "delivery_mode": "immediate",
                "delivery_schedule_time": None,
                "admission_strategy": "balanced",
                "batch_limit": 3,
                "current_cycle": "idle",
                "current_cycle_progress_percent": 0,
                "current_cycle_progress_done": 0,
                "current_cycle_progress_total": 0,
                "current_cycle_progress_label": None,
                "enabled_at": None,
                "scheduled_start_at": None,
                "current_cycle_started_at": None,
                "last_cycle_started_at": None,
                "last_cycle_finished_at": None,
                "last_cycle_duration_seconds": None,
                "completed_cycles_today": 0,
                "failed_cycles_today": 0,
                "counters_date": local_now().date().isoformat(),
                "last_error": None,
                "blocked_reason": None,
                "last_successful_sync_at": None,
                "current_cycle_sources": [],
                "current_cycle_metrics": {
                    "selected_event_count": 0,
                    "deep_dive_count": 0,
                    "brief_count": 0,
                    "wechat_sync_count": 0,
                    "wechat_verify_count": 0,
                    "publish_count": 0,
                    "selected_titles": [],
                    "brief_titles": [],
                    "synced_titles": [],
                },
                "last_cycle_summary": None,
                "automation_run": {
                    "run_id": None,
                    "status": "idle",
                    "stage": "idle",
                    "started_at": None,
                    "heartbeat_at": None,
                    "finished_at": None,
                    "triggered_by": None,
                    "error": None,
                    "recovered_run_id": None,
                    "intent": DEFAULT_RUNTIME_INTENT,
                    "last_run_outcome": None,
                },
            },
        }
        self._append_log(
            state,
            "info",
            "system",
            "已完成 Auto News Studio 初始化，当前未自动抓取素材，也未开始自动交付。",
            stream="system_runtime",
        )
        return state

    def _bootstrap_user_settings(self) -> dict[str, Any]:
        settings = deepcopy(DEFAULT_USER_SETTINGS)
        settings["llm"] = default_llm_state()
        settings["wechat"]["risk_keywords"] = ["投资建议", "医疗建议", "未经核实", "爆料"]
        settings["wechat"]["browser_profile_path"] = str(default_browser_profile_path("edge"))
        return settings

    def _read_config(self) -> dict[str, Any]:
        with self._lock:
            return read_json_file(self.config_file, self._bootstrap_user_settings())

    def _write_config(self, payload: dict[str, Any]) -> None:
        with self._lock:
            atomic_write_json(self.config_file, payload)

    def _upgrade_user_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        next_payload = self._bootstrap_user_settings()
        next_payload.update({key: value for key, value in payload.items() if key in next_payload})
        next_payload["llm"] = payload.get("llm", next_payload["llm"])
        next_payload["wechat"] = {
            **next_payload["wechat"],
            **(payload.get("wechat", {}) if isinstance(payload.get("wechat"), dict) else {}),
        }
        next_payload["sources"] = {
            "overrides": (
                payload.get("sources", {}).get("overrides", {})
                if isinstance(payload.get("sources"), dict)
                else {}
            )
        }
        next_payload["settings"] = {
            **next_payload["settings"],
            **(payload.get("settings", {}) if isinstance(payload.get("settings"), dict) else {}),
        }
        next_payload["schema_version"] = 1
        return next_payload

    def _extract_config_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        config = self._bootstrap_user_settings()
        config["llm"] = deepcopy_json(state.get("llm", default_llm_state()))
        config["wechat"] = deepcopy_json(state.get("channels", {}).get("wechat", config["wechat"]))
        settings = state.get("settings", {})
        config["settings"] = {
            "max_workers": int(settings.get("max_workers", 8) or 8),
            "tavily_api_key": str(settings.get("tavily_api_key") or "").strip(),
        }
        overrides: dict[str, Any] = {}
        for source in state.get("sources", []):
            if not isinstance(source, dict):
                continue
            source_key = str(source.get("key") or "").strip()
            if not source_key:
                continue
            overrides[source_key] = {
                "enabled": bool(source.get("enabled", True)),
                "schedule": str(source.get("schedule") or "").strip(),
                "priority": int(source.get("priority") or 5),
                "url": source.get("url"),
                "tags": deepcopy_json(source.get("tags", [])),
                "weight": float(source.get("weight") or 0.7),
                "auth": deepcopy_json(source.get("auth", {})),
            }
        config["sources"] = {"overrides": overrides}
        return self._upgrade_user_settings(config)

    def _migrate_legacy_config(self) -> None:
        legacy_state = read_json_file(self.data_file, {})
        migrated = self._extract_config_from_state(legacy_state)
        self._write_config(migrated)

    def _apply_user_settings_to_state(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        state["llm"] = deepcopy_json(config.get("llm", default_llm_state()))
        channels = state.setdefault("channels", {})
        channels["wechat"] = ensure_channel_defaults(config.get("wechat", {}))
        settings = state.setdefault("settings", {})
        user_settings = config.get("settings", {}) if isinstance(config.get("settings"), dict) else {}
        settings["max_workers"] = int(user_settings.get("max_workers", 8) or 8)
        settings["tavily_api_key"] = str(user_settings.get("tavily_api_key") or "").strip()
        settings.setdefault("entity_watchlist", [])
        self._apply_source_overrides_to_state(
            state,
            config.get("sources", {}).get("overrides", {}) if isinstance(config.get("sources"), dict) else {},
        )
        return state

    def _apply_source_overrides_to_state(self, state: dict[str, Any], overrides: dict[str, Any]) -> None:
        if not isinstance(overrides, dict):
            return
        for source in state.get("sources", []):
            if not isinstance(source, dict):
                continue
            source_key = str(source.get("key") or "").strip()
            if not source_key:
                continue
            override = overrides.get(source_key)
            if not isinstance(override, dict):
                continue
            for field in ("enabled", "schedule", "priority", "url", "tags", "weight", "auth"):
                if field in override:
                    source[field] = deepcopy_json(override[field])
            source["interval_minutes"] = schedule_to_minutes(source.get("schedule")) or source.get("interval_minutes") or 30

    def _app_meta(self, state: dict[str, Any]) -> dict[str, Any]:
        app_meta = state.setdefault("app_meta", {})
        if not isinstance(app_meta, dict):
            app_meta = {}
            state["app_meta"] = app_meta
        app_meta.setdefault("dismissed_update_version", None)
        app_meta.setdefault("last_update_check", None)
        return app_meta

    @staticmethod
    def _normalize_version_text(value: str | None) -> str:
        compact = str(value or "").strip()
        if compact.lower().startswith("v"):
            compact = compact[1:]
        return compact

    @classmethod
    def _version_parts(cls, value: str | None) -> tuple[int, ...]:
        compact = cls._normalize_version_text(value)
        match = re.match(r"(\d+(?:\.\d+)*)", compact)
        if not match:
            return (0,)
        return tuple(int(part) for part in match.group(1).split("."))

    @classmethod
    def _is_version_newer(cls, latest: str | None, current: str | None) -> bool:
        latest_parts = cls._version_parts(latest)
        current_parts = cls._version_parts(current)
        max_len = max(len(latest_parts), len(current_parts))
        latest_padded = latest_parts + (0,) * (max_len - len(latest_parts))
        current_padded = current_parts + (0,) * (max_len - len(current_parts))
        return latest_padded > current_padded

    def get_app_version_info(self) -> AppVersionInfo:
        manifest = self.version_manifest
        return AppVersionInfo(
            version=str(manifest.get("version") or "0.2.6"),
            release_channel=str(manifest.get("release_channel") or "stable"),
            release_repo=str(manifest.get("release_repo") or DEFAULT_RELEASE_REPO),
            release_notes_url=str(manifest.get("release_notes_url") or DEFAULT_RELEASE_NOTES_URL),
        )

    def _github_request_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "Auto-News-Studio",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = str(os.getenv("GITHUB_TOKEN") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _fetch_latest_release_via_api(self, repo: str) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        request = Request(url, headers=self._github_request_headers())
        with urlopen(request, timeout=12) as response:  # noqa: S310 - controlled GitHub API URL
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "latest_version": str(payload.get("tag_name") or payload.get("name") or "").strip(),
            "release_url": str(payload.get("html_url") or "").strip() or None,
            "release_notes_url": str(payload.get("html_url") or "").strip() or None,
            "published_at": str(payload.get("published_at") or payload.get("created_at") or "").strip() or None,
            "source": "github_api",
        }

    def _fetch_latest_release_via_feed(self, repo: str) -> dict[str, Any]:
        url = f"https://github.com/{repo}/releases.atom"
        request = Request(url, headers={"User-Agent": "Auto-News-Studio", "Accept": "application/atom+xml,application/xml,text/xml"})
        with urlopen(request, timeout=12) as response:  # noqa: S310 - controlled GitHub URL
            xml_text = response.read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml_text)
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", namespace)
        if entry is None:
            raise ValueError("未找到任何公开 Release 记录")
        title = entry.findtext("atom:title", default="", namespaces=namespace).strip()
        link_node = entry.find("atom:link", namespace)
        updated_at = entry.findtext("atom:updated", default="", namespaces=namespace).strip() or None
        href = link_node.get("href") if link_node is not None else None
        version_match = re.search(r"\bv?\d+(?:\.\d+){1,}\b", title)
        latest_version = version_match.group(0) if version_match else title
        return {
            "latest_version": latest_version,
            "release_url": href,
            "release_notes_url": href or f"https://github.com/{repo}/releases",
            "published_at": updated_at,
            "source": "github_feed",
        }

    def _fetch_latest_release(self, repo: str) -> tuple[dict[str, Any] | None, str | None]:
        errors: list[str] = []
        for fetcher in (self._fetch_latest_release_via_api, self._fetch_latest_release_via_feed):
            try:
                payload = fetcher(repo)
                latest_version = str(payload.get("latest_version") or "").strip()
                if not latest_version:
                    raise ValueError("未返回版本号")
                return payload, None
            except HTTPError as exc:
                errors.append(f"{fetcher.__name__}:{exc.code}")
            except URLError as exc:
                errors.append(f"{fetcher.__name__}:{exc.reason}")
            except Exception as exc:
                errors.append(f"{fetcher.__name__}:{exc}")
        return None, "; ".join(errors) if errors else "unknown"

    def get_app_update_info(self, force: bool = False) -> AppUpdateInfo:
        current = self.get_app_version_info()
        checked_at = now_iso()
        with self._lock:
            state = self._upgrade_state(self._read())
            app_meta = self._app_meta(state)
            cached = app_meta.get("last_update_check")
            if isinstance(cached, dict) and not force:
                checked_dt = parse_time(str(cached.get("checked_at") or ""))
                if checked_dt and (datetime.now(UTC) - checked_dt).total_seconds() < 1800:
                    payload = deepcopy_json(cached)
                    payload["dismissed_version"] = app_meta.get("dismissed_update_version")
                    payload["dismissed"] = bool(
                        payload.get("latest_version")
                        and app_meta.get("dismissed_update_version")
                        and self._normalize_version_text(str(payload.get("latest_version") or ""))
                        == self._normalize_version_text(str(app_meta.get("dismissed_update_version") or ""))
                    )
                    return AppUpdateInfo(**payload)

        latest_payload, error = self._fetch_latest_release(current.release_repo)
        update_payload = {
            "current_version": current.version,
            "latest_version": latest_payload.get("latest_version") if latest_payload else None,
            "update_available": bool(latest_payload and self._is_version_newer(latest_payload.get("latest_version"), current.version)),
            "checked_at": checked_at,
            "source": latest_payload.get("source") if latest_payload else "unavailable",
            "release_url": latest_payload.get("release_url") if latest_payload else None,
            "release_notes_url": latest_payload.get("release_notes_url") if latest_payload else current.release_notes_url,
            "published_at": latest_payload.get("published_at") if latest_payload else None,
            "error": error,
        }
        with self._lock:
            state = self._upgrade_state(self._read())
            app_meta = self._app_meta(state)
            app_meta["last_update_check"] = deepcopy_json(update_payload)
            self._write(state)
            update_payload["dismissed_version"] = app_meta.get("dismissed_update_version")
            update_payload["dismissed"] = bool(
                update_payload.get("latest_version")
                and app_meta.get("dismissed_update_version")
                and self._normalize_version_text(str(update_payload.get("latest_version") or ""))
                == self._normalize_version_text(str(app_meta.get("dismissed_update_version") or ""))
            )
        return AppUpdateInfo(**update_payload)

    def dismiss_app_update(self, version: str) -> AppUpdateInfo:
        target_version = self._normalize_version_text(version)
        if not target_version:
            raise ValueError("缺少要关闭提示的版本号")
        with self._lock:
            state = self._upgrade_state(self._read())
            app_meta = self._app_meta(state)
            app_meta["dismissed_update_version"] = target_version
            self._write(state)
        return self.get_app_update_info(force=False)

    def _setup_status(self, state: dict[str, Any], browser: dict[str, Any]) -> dict[str, Any]:
        llm = state.get("llm", {})
        profiles = llm.get("profiles", []) if isinstance(llm, dict) else []
        has_llm = any(bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key") or "") for profile in profiles if isinstance(profile, dict))
        browser_ready = bool(browser.get("user_data_dir"))
        browser_logged_in = bool(browser.get("logged_in"))
        return {
            "llm_ready": has_llm,
            "wechat_browser_configured": browser_ready,
            "wechat_logged_in": browser_logged_in,
            "needs_setup": not (has_llm and browser_logged_in),
        }

    def system_doctor(self) -> SystemDoctorResult:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        llm_cfg = state.get("llm", {})
        profiles = llm_cfg.get("profiles", []) if isinstance(llm_cfg, dict) else []
        enabled_profiles = [profile for profile in profiles if isinstance(profile, dict) and bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key") or "")]
        items = [
            SystemCheckItem(
                key="backend",
                label="后端服务",
                ok=True,
                detail="后端接口可访问。",
                next_action=None,
            ),
            SystemCheckItem(
                key="frontend_dist",
                label="前端资源",
                ok=(Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html").exists(),
                detail="已检测到前端构建产物。" if (Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html").exists() else "缺少 frontend/dist，请先运行发布构建或开发构建。",
                next_action=None if (Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html").exists() else "运行 npm run build 生成前端资源。",
            ),
            SystemCheckItem(
                key="llm",
                label="AI 模型",
                ok=bool(enabled_profiles),
                detail=f"已配置 {len(enabled_profiles)} 个可用 profile。" if enabled_profiles else "尚未配置可用的 AI profile。",
                next_action=None if enabled_profiles else "前往设置 > AI 模型，填入至少一个 API Key 并测试连接。",
            ),
            SystemCheckItem(
                key="wechat_profile",
                label="微信浏览器配置",
                ok=bool(str(browser.get('user_data_dir') or '').strip()),
                detail=f"当前 profile：{browser.get('user_data_dir')}" if str(browser.get("user_data_dir") or "").strip() else "尚未配置微信浏览器 profile。",
                next_action=None if str(browser.get("user_data_dir") or "").strip() else "前往设置 > 微信浏览器，先保存浏览器与 profile 路径。",
            ),
            SystemCheckItem(
                key="wechat_login",
                label="公众号登录态",
                ok=bool(browser.get("logged_in")),
                detail="已检测到可复用的公众号登录态。" if browser.get("logged_in") else str(browser.get("last_error") or "尚未完成公众号后台登录检查。"),
                next_action=None if browser.get("logged_in") else "前往设置 > 微信浏览器，打开公众号后台并完成登录检查。",
            ),
        ]
        ok = all(item.ok for item in items)
        summary = "系统已满足分发版基本使用条件。" if ok else "系统仍有未完成项，请按建议补齐后再投入使用。"
        return SystemDoctorResult(checked_at=now_iso(), ok=ok, items=items, summary=summary)

    def export_config_bundle(self) -> Path:
        config = self._upgrade_user_settings(self._read_config())
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        export_path = BACKUP_DIR / f"config-export-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
        atomic_write_json(export_path, config)
        return export_path

    def export_backup_bundle(self) -> Path:
        state = self._upgrade_state(self._read())
        config = self._upgrade_user_settings(self._read_config())
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        export_path = BACKUP_DIR / f"studio-backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
        with zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("config/user-settings.json", json.dumps(config, ensure_ascii=False, indent=2))
            zf.writestr("data/state.json", json.dumps(state, ensure_ascii=False, indent=2))
            recent_logs = {"logs": state.get("logs", [])[:200]}
            zf.writestr("logs/recent-logs.json", json.dumps(recent_logs, ensure_ascii=False, indent=2))
        return export_path

    def import_backup_bundle(self, file_path: Path) -> ImportBackupResponse:
        if not file_path.exists():
            raise ValueError("备份文件不存在。")
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        rollback = BACKUP_DIR / f"rollback-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        rollback.mkdir(parents=True, exist_ok=True)
        backup_file(self.data_file, rollback, "state")
        backup_file(self.config_file, rollback, "config")
        with zipfile.ZipFile(file_path, "r") as zf:
            if "config/user-settings.json" in zf.namelist():
                config = json.loads(zf.read("config/user-settings.json").decode("utf-8"))
                self._write_config(self._upgrade_user_settings(config))
            if "data/state.json" in zf.namelist():
                state = json.loads(zf.read("data/state.json").decode("utf-8"))
                self._write(self._upgrade_state(state))
        return ImportBackupResponse(ok=True, message="已导入备份。若为新机器，请重新登录公众号后台。", backup_path=str(rollback))

    def _build_source_registry(self) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = deepcopy(discover_sources())
        seen_keys = {item["key"] for item in merged}
        seen_urls = {item["url"] for item in merged if item.get("url")}
        for source in build_legacy_rss_sources():
            if source["key"] in seen_keys or source.get("url") in seen_urls:
                continue
            source.setdefault("platform", source.get("kind", "rss"))
            source.setdefault("interval_minutes", schedule_to_minutes(source.get("schedule")) or 30)
            source.setdefault("weight", 0.7)
            merged.append(source)
            seen_keys.add(source["key"])
            if source.get("url"):
                seen_urls.add(source["url"])
        return merged

    def _prune_unsupported_sources(self, state: dict[str, Any]) -> None:
        state.setdefault("logs", [])
        state.setdefault("sources", [])
        sources_before = list(state.get("sources", []))
        supported_sources = [
            source
            for source in sources_before
            if str(source.get("driver") or "") not in UNSUPPORTED_SOURCE_DRIVERS
        ]
        if len(supported_sources) == len(sources_before):
            return
        removed_names = [str(source.get("name") or source.get("key") or "unknown") for source in sources_before if str(source.get("driver") or "") in UNSUPPORTED_SOURCE_DRIVERS]
        state["sources"] = supported_sources
        if removed_names:
            self._append_log(
                state,
                "warning",
                "cleanup",
                f"已移除未适配来源：{'、'.join(removed_names)}。",
                stream="system_runtime",
                actor="system",
            )

    def _purge_synthetic_state(self, state: dict[str, Any]) -> None:
        raw_items = [item for item in state.get("raw_items", []) if not _is_synthetic_raw_item(item)]
        raw_items = sorted(
            raw_items,
            key=lambda item: parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )[:MAX_RAW_ITEMS]

        removed_raw = len(state.get("raw_items", [])) - len(raw_items)
        raw_lookup = {item["id"]: item for item in raw_items}
        normalized = normalize_raw_items(raw_items, self._sources_by_key(state))
        for item in normalized:
            collected_at = self._latest_collected_at(raw_lookup, item.get("raw_item_ids", []))
            item["collected_at"] = collected_at
            item["freshness_bucket"] = freshness_bucket(collected_at)

        kept_brief_ids = {
            str(item.get("id") or "")
            for item in state.get("briefs", [])
            if isinstance(item, dict) and item.get("id")
        }
        kept_publish_owner_ids = kept_brief_ids | {"session-wechat"}
        for task in state.get("publish_tasks", []):
            if "draft_id" in task and "target_id" not in task:
                task["target_id"] = task.get("draft_id")
        publish_tasks = [task for task in state.get("publish_tasks", []) if str(task.get("target_id") or "") in kept_publish_owner_ids]
        logs = [
            log
            for log in state.get("logs", [])
            if not _contains_synthetic_marker(log.get("message")) and not _contains_synthetic_marker(log.get("detail"))
        ]
        jobs = [job for job in state.get("jobs", []) if not _contains_synthetic_marker(job.get("message"))]

        removed_logs = len(state.get("logs", [])) - len(logs)

        source_counts: dict[str, int] = {}
        for item in raw_items:
            key = str(item.get("source_key") or "")
            source_counts[key] = source_counts.get(key, 0) + 1
        for source in state.get("sources", []):
            count = source_counts.get(str(source.get("key") or ""), 0)
            source["item_count"] = count
            if _contains_synthetic_marker(source.get("health_detail")) or _contains_synthetic_marker(source.get("last_error")):
                source["last_error"] = None
                if count > 0:
                    source["health_status"] = "healthy"
                    source["health_detail"] = f"历史伪造数据已清理，当前保留 {count} 条真实素材。"
                else:
                    source["health_status"] = "idle"
                    source["health_detail"] = "历史伪造数据已清理，请重新同步验证。"

        state["raw_items"] = raw_items
        state["normalized_items"] = normalized
        state["publish_tasks"] = publish_tasks
        state["logs"] = logs
        state["jobs"] = jobs

        if removed_raw or removed_logs:
            self._append_log(
                state,
                "warning",
                "cleanup",
                f"已清理历史伪造数据：删除 {removed_raw} 条伪素材。",
                stream="system_runtime",
                actor="system",
            )

    def _read(self) -> dict[str, Any]:
        with self._lock:
            state = json.loads(self.data_file.read_text(encoding="utf-8"))
            config = self._upgrade_user_settings(read_json_file(self.config_file, self._bootstrap_user_settings()))
            return self._apply_user_settings_to_state(state, config)

    def _ensure_live_state_defaults(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("automation_mode", "radar_only")
        state.setdefault("automation_mode_definitions", deepcopy(AUTOMATION_MODE_DEFINITIONS))
        state.setdefault("automation_profiles", deepcopy(DEFAULT_AUTOMATION_PROFILES))
        state.setdefault("raw_items", [])
        state.setdefault("normalized_items", [])
        state.setdefault("discovery_items", [])
        state.setdefault("intel_events", [])
        state.setdefault("event_snapshots", [])
        state.setdefault("intel_alerts", [])
        state.setdefault("intel_event_history", [])
        state.setdefault("intel_alert_history", [])
        state.setdefault("event_deep_dives", [])
        state.setdefault("briefs", [])
        state.setdefault("publish_tasks", [])
        state.setdefault("jobs", [])
        state.setdefault("logs", [])
        state.setdefault("reference_projects", [])
        state.setdefault("runtime_plan", {})
        state.setdefault(
            "notifications",
            {
                "webhook": {
                    "enabled": False,
                    "url": "",
                    "secret": "",
                    "events": ["breakout"],
                },
                "delivery_log": [],
            },
        )
        self._app_meta(state)

        if not isinstance(state.get("sources"), list):
            state["sources"] = self._build_source_registry()
            self._apply_source_overrides_to_state(
                state,
                config.get("sources", {}).get("overrides", {}) if isinstance(config.get("sources"), dict) else {},
            )

        channels = state.setdefault("channels", {})
        channels["wechat"] = ensure_channel_defaults(channels.get("wechat", {}))

        browser = state.setdefault("browser", {})
        browser_wechat = browser.setdefault("wechat", {})
        browser_wechat.setdefault("platform", "wechat_mp")
        browser_wechat["browser_name"] = channels["wechat"]["browser_name"]
        browser_wechat["user_data_dir"] = channels["wechat"]["browser_profile_path"]
        browser_wechat.setdefault("logged_in", False)
        browser_wechat.setdefault("last_checked_at", None)
        browser_wechat.setdefault("last_opened_url", None)
        browser_wechat.setdefault("last_error", None)
        browser_wechat["selectors_version"] = channels["wechat"]["selectors_version"]
        browser_wechat.setdefault("last_screenshot", None)
        browser_wechat.setdefault("last_selector_check", None)
        browser_wechat.setdefault("current_page", channels["wechat"]["publish_entry_url"])
        browser_wechat.setdefault("sidecar_health", "offline")
        browser_wechat.setdefault("manager_alive", False)
        browser_wechat.setdefault("window_state", "unknown")
        browser_wechat.setdefault("resident_page", None)
        browser_wechat.setdefault("busy", False)
        browser_wechat.setdefault("last_reset_reason", None)
        browser_wechat.setdefault("session_generation", 0)
        browser_wechat.setdefault("last_action", None)
        browser_wechat.setdefault("last_action_phase", None)
        browser_wechat.setdefault("is_session_level_error", False)
        browser_wechat.setdefault("last_draft_check", None)

        runtime = state.setdefault("runtime", {})
        runtime.setdefault("scheduler_running", False)
        runtime.setdefault("control_state", "stopped")
        runtime.setdefault("launch_mode", "interval_now")
        runtime.setdefault("current_mode", state.get("automation_mode", "radar_only"))
        runtime.setdefault("work_scope", state.get("runtime_plan", {}).get("work_scope", "collect_events_alerts"))
        runtime.setdefault("last_collect_at", None)
        runtime.setdefault("last_event_sync_at", None)
        runtime.setdefault("last_brief_at", None)
        runtime.setdefault("next_collect_at", None)
        runtime.setdefault("delivery_mode", "immediate")
        runtime.setdefault("delivery_schedule_time", None)
        runtime.setdefault("admission_strategy", "balanced")
        runtime.setdefault("batch_limit", 3)
        runtime.setdefault("current_cycle", "idle")
        runtime.setdefault("current_cycle_progress_percent", 0)
        runtime.setdefault("current_cycle_progress_done", 0)
        runtime.setdefault("current_cycle_progress_total", 0)
        runtime.setdefault("current_cycle_progress_label", None)
        runtime.setdefault("enabled_at", None)
        runtime.setdefault("scheduled_start_at", None)
        runtime.setdefault("current_cycle_started_at", None)
        runtime.setdefault("last_cycle_started_at", None)
        runtime.setdefault("last_cycle_finished_at", None)
        runtime.setdefault("last_cycle_duration_seconds", None)
        runtime.setdefault("completed_cycles_today", 0)
        runtime.setdefault("failed_cycles_today", 0)
        runtime.setdefault("counters_date", local_now().date().isoformat())
        runtime.setdefault("last_error", None)
        runtime.setdefault("blocked_reason", None)
        runtime.setdefault("last_successful_sync_at", None)
        runtime.setdefault("current_cycle_sources", [])
        runtime.setdefault(
            "current_cycle_metrics",
            {
                "selected_event_count": 0,
                "deep_dive_count": 0,
                "brief_count": 0,
                "wechat_sync_count": 0,
                "wechat_verify_count": 0,
                "publish_count": 0,
                "selected_titles": [],
                "brief_titles": [],
                "synced_titles": [],
            },
        )
        runtime.setdefault("last_cycle_summary", None)
        automation_run = runtime.setdefault("automation_run", {})
        automation_run.setdefault("run_id", None)
        automation_run.setdefault("status", "idle")
        automation_run.setdefault("stage", "idle")
        automation_run.setdefault("started_at", None)
        automation_run.setdefault("heartbeat_at", None)
        automation_run.setdefault("finished_at", None)
        automation_run.setdefault("triggered_by", None)
        automation_run.setdefault("error", None)
        automation_run.setdefault("recovered_run_id", None)
        automation_run.setdefault("intent", DEFAULT_RUNTIME_INTENT)
        automation_run.setdefault("last_run_outcome", None)
        self._sync_runtime_counters(runtime)

        for source in state.get("sources", []):
            if not isinstance(source, dict):
                continue
            source.setdefault("last_attempt_at", None)
            source.setdefault("last_success_at", None)
            source.setdefault("last_failure_at", None)
            source.setdefault("consecutive_failures", 0)
            source.setdefault("last_duration_ms", None)
            source.setdefault("avg_duration_ms", None)
            source.setdefault("last_item_count", int(source.get("item_count", 0) or 0))

        for log in state.get("logs", []):
            if isinstance(log, dict):
                log.setdefault("stream", "business_event")
                log.setdefault("actor", "system")
                log.setdefault("detail", None)

        for deep_dive in state.get("event_deep_dives", []):
            if not isinstance(deep_dive, dict):
                continue
            deep_dive.setdefault("status", "pending")
            deep_dive.setdefault("started_at", None)
            deep_dive.setdefault("finished_at", None)
            deep_dive.setdefault("updated_at", now_iso())
            deep_dive.setdefault("attempted_count", 0)
            deep_dive.setdefault("success_count", 0)
            deep_dive.setdefault("failed_count", 0)
            deep_dive.setdefault("resolved_evidence_pack", [])
            deep_dive.setdefault("full_text_sources", [])
            deep_dive.setdefault("sources", [])
            deep_dive.setdefault("facts", [])
            deep_dive.setdefault("quotes", [])
            deep_dive.setdefault("timeline", [])
            deep_dive.setdefault("worthiness", {})
            deep_dive.setdefault("last_error", None)
            for source in deep_dive.get("sources", []):
                if isinstance(source, dict):
                    source.setdefault("cleaned_full_text", "")

        for brief in state.get("briefs", []):
            if not isinstance(brief, dict):
                continue
            brief.setdefault("brief_level", "rule")
            brief.setdefault("stage", "prepared")
            brief.setdefault("one_line", "")
            brief.setdefault("why_it_matters", "")
            brief.setdefault("facts", [])
            brief.setdefault("quotes", [])
            brief.setdefault("timeline", [])
            brief.setdefault("entity_names", [])
            brief.setdefault("source_links", [])
            brief.setdefault("risk_notes", [])
            brief.setdefault("prompt_package_markdown", "")
            brief.setdefault("wechat_markdown", "")
            brief.setdefault("wechat_html", "")
            brief.setdefault("wechat_target_id", None)
            brief.setdefault("wechat_editor_url", None)
            brief.setdefault("wechat_remote_appmsg_id", None)
            brief.setdefault("preview_url", None)
            brief.setdefault("last_error", None)
            brief.setdefault("delivery_status", "idle")
            brief.setdefault("delivery_attempt_count", 0)
            brief.setdefault("last_delivery_attempt_at", None)
            brief.setdefault("last_verified_at", None)
            brief.setdefault("last_delivery_error_kind", None)
            brief.setdefault("needs_resync", False)
            brief.setdefault("last_synced_revision", None)
            brief.setdefault("last_successful_upload_at", None)
            brief.setdefault("driver_label", "")
            brief.setdefault("updated_at", now_iso())
            brief.pop("wechat_draft_id", None)

        profiles_by_mode = {
            item["mode"]: item
            for item in state.get("automation_profiles", [])
            if isinstance(item, dict) and item.get("mode")
        }
        merged_profiles: list[dict[str, Any]] = []
        for default_profile in deepcopy(DEFAULT_AUTOMATION_PROFILES):
            profile = profiles_by_mode.get(default_profile["mode"], {})
            if "draft_trigger" in profile and "brief_trigger" not in profile:
                profile["brief_trigger"] = profile.get("draft_trigger")
            if "draft_schedule_time" in profile and "brief_schedule_time" not in profile:
                profile["brief_schedule_time"] = profile.get("draft_schedule_time")
            if "draft_delivery" in profile and "delivery_target" not in profile:
                profile["delivery_target"] = profile.get("draft_delivery")
            if "draft_selection" in profile and "selection_mode" not in profile:
                profile["selection_mode"] = profile.get("draft_selection")
            if "draft_limit" in profile and "brief_limit" not in profile:
                profile["brief_limit"] = profile.get("draft_limit")
            merged = {**default_profile, **profile}
            merged.pop("draft_trigger", None)
            merged.pop("draft_schedule_time", None)
            merged.pop("draft_delivery", None)
            merged.pop("draft_selection", None)
            merged.pop("draft_limit", None)
            merged_profiles.append(merged)
        state["automation_profiles"] = merged_profiles

        mode_defs_by_key = {
            item["key"]: item
            for item in state.get("automation_mode_definitions", [])
            if isinstance(item, dict) and item.get("key")
        }
        merged_mode_defs: list[dict[str, Any]] = []
        for default_mode in deepcopy(AUTOMATION_MODE_DEFINITIONS):
            existing_mode = mode_defs_by_key.get(default_mode["key"], {})
            if "auto_generate_candidates" in existing_mode and "auto_build_events" not in existing_mode:
                existing_mode["auto_build_events"] = existing_mode.get("auto_generate_candidates")
            if "auto_generate_drafts" in existing_mode and "auto_build_briefs" not in existing_mode:
                existing_mode["auto_build_briefs"] = existing_mode.get("auto_generate_drafts")
            merged_mode_defs.append({**existing_mode, **default_mode})
        state["automation_mode_definitions"] = merged_mode_defs
        state.pop("current_mode", None)
        state.pop("mode_definitions", None)
        return state

    def _read_live(self) -> dict[str, Any]:
        state = json.loads(self.data_file.read_text(encoding="utf-8"))
        config = self._upgrade_user_settings(read_json_file(self.config_file, self._bootstrap_user_settings()))
        state = self._apply_user_settings_to_state(state, config)
        state.setdefault("llm", deepcopy_json(config.get("llm", default_llm_state())))
        return self._ensure_live_state_defaults(state, config)

    def _write(self, payload: dict[str, Any]) -> None:
        with self._lock:
            content = json.dumps(payload, ensure_ascii=False, indent=2)
            temp_file = self.data_file.with_name(f"{self.data_file.stem}.{uuid4().hex}.tmp")
            temp_file.write_text(content, encoding="utf-8")
            last_error: Exception | None = None
            for attempt in range(8):
                try:
                    temp_file.replace(self.data_file)
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
                    if attempt >= 7:
                        break
                    time.sleep(0.05 * (attempt + 1))
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except OSError:
                pass
            if last_error:
                raise last_error

    def _upgrade_state(self, state: dict[str, Any]) -> dict[str, Any]:
        config = self._upgrade_user_settings(read_json_file(self.config_file, self._bootstrap_user_settings()))
        state = self._apply_user_settings_to_state(state, config)
        self._prune_unsupported_sources(state)
        state.setdefault("llm", deepcopy_json(config.get("llm", default_llm_state())))
        llm = state["llm"]
        existing_profiles = llm.get("profiles", [])
        if not existing_profiles:
            migrated_profiles = merge_llm_profiles([], [])
            providers = [item for item in llm.get("providers", []) if isinstance(item, dict)]
            active_provider = next((item for item in providers if item.get("enabled")), providers[0] if providers else None)
            if active_provider:
                matched = next(
                    (
                        item for item in migrated_profiles
                        if item.get("provider_key") == active_provider.get("key")
                        and item.get("model_id") == active_provider.get("model_id")
                    ),
                    None,
                )
                if matched:
                    matched["api_key"] = str(active_provider.get("api_key") or "")
                    matched["base_url"] = str(active_provider.get("base_url") or matched.get("base_url") or "")
                    matched["enabled"] = bool(str(active_provider.get("api_key") or "").strip())
                    llm["current_profile_id"] = matched["id"]
                else:
                    migrated_profiles.insert(
                        0,
                        {
                            "id": "custom-active",
                            "label": "当前自定义模型",
                            "description": "从旧版单模型配置迁移而来。",
                            "provider_key": str(active_provider.get("key") or ""),
                            "api_key": str(active_provider.get("api_key") or ""),
                            "base_url": str(active_provider.get("base_url") or ""),
                            "model_id": str(active_provider.get("model_id") or ""),
                            "enabled": bool(str(active_provider.get("api_key") or "").strip()),
                            "last_tested_at": active_provider.get("last_tested_at"),
                            "last_test_result": active_provider.get("last_test_result"),
                        },
                    )
                    llm["current_profile_id"] = "custom-active"
            llm["profiles"] = migrated_profiles
        else:
            llm["profiles"] = merge_llm_profiles([item for item in existing_profiles if isinstance(item, dict)], existing_profiles)

        current_profile_id = str(llm.get("current_profile_id") or "").strip() or (
            llm["profiles"][0]["id"] if llm.get("profiles") else ""
        )
        active_profile = next((item for item in llm.get("profiles", []) if item.get("id") == current_profile_id), None)
        if not active_profile and llm.get("profiles"):
            active_profile = llm["profiles"][0]
            current_profile_id = active_profile["id"]
        llm["current_profile_id"] = current_profile_id
        for profile in llm.get("profiles", []):
            profile["enabled"] = bool(str(profile.get("api_key") or "").strip())
        legacy_tasks = _migrate_tasks(llm.get("tasks", []))
        fallback_profile_id = str(llm.get("fallback_profile_id") or "").strip()
        if not fallback_profile_id and legacy_tasks:
            inferred_fallback_id = infer_fallback_profile_id_from_tasks(legacy_tasks, llm.get("profiles", []))
            fallback_profile_id = str(inferred_fallback_id or "").strip()
        if fallback_profile_id == current_profile_id:
            fallback_profile_id = ""
        fallback_profile = next((item for item in llm.get("profiles", []) if item.get("id") == fallback_profile_id), None)
        if fallback_profile and not bool(str(fallback_profile.get("api_key") or "").strip()):
            fallback_profile_id = ""
        llm["fallback_profile_id"] = fallback_profile_id or None
        llm["providers"] = [
            build_provider_from_profile(profile)
            for profile in llm.get("profiles", [])
            if bool(str(profile.get("api_key") or "").strip())
        ]
        llm.pop("tasks", None)
        llm.setdefault("usage_today", {})
        state.setdefault("automation_mode", "radar_only")
        state.setdefault("automation_mode_definitions", deepcopy(AUTOMATION_MODE_DEFINITIONS))
        state.setdefault("automation_profiles", deepcopy(DEFAULT_AUTOMATION_PROFILES))
        state.setdefault("discovery_items", [])
        state.setdefault("intel_events", [])
        state.setdefault("event_snapshots", [])
        state.setdefault("intel_alerts", [])
        state.setdefault("intel_event_history", [])
        state.setdefault("intel_alert_history", [])
        state.setdefault("event_deep_dives", [])
        state.setdefault("briefs", [])
        settings = state.setdefault("settings", {})
        settings["max_workers"] = int(config.get("settings", {}).get("max_workers", 8) or 8)
        settings.setdefault("entity_watchlist", [])
        settings["tavily_api_key"] = str(config.get("settings", {}).get("tavily_api_key") or "").strip()
        state.setdefault("runtime_plan", {})
        state.setdefault("notifications", {
            "webhook": {
                "enabled": False,
                "url": "",
                "secret": "",
                "events": ["breakout"],
            },
            "delivery_log": [],
        })
        channels = state.setdefault("channels", {})
        raw_wechat_channel = dict(config.get("wechat", channels.setdefault("wechat", {})))
        raw_browser_name = str(raw_wechat_channel.get("browser_name") or "").strip().lower()
        raw_profile_path = str(raw_wechat_channel.get("browser_profile_path") or "").strip()
        if raw_browser_name == "chrome" and (
            not raw_profile_path or raw_profile_path == str(default_browser_profile_path("chrome"))
        ):
            raw_wechat_channel["browser_name"] = "edge"
            raw_wechat_channel["browser_profile_path"] = str(default_browser_profile_path("edge"))
        wechat_channel = ensure_channel_defaults(channels.setdefault("wechat", {}))
        wechat_channel.update(ensure_channel_defaults(raw_wechat_channel))
        channels["wechat"] = wechat_channel
        browser = state.setdefault("browser", {})
        browser_wechat = browser.setdefault("wechat", {})
        browser_wechat.setdefault("platform", "wechat_mp")
        browser_wechat["browser_name"] = wechat_channel["browser_name"]
        browser_wechat["user_data_dir"] = wechat_channel["browser_profile_path"]
        browser_wechat.setdefault("logged_in", False)
        browser_wechat.setdefault("last_checked_at", None)
        browser_wechat.setdefault("last_opened_url", None)
        browser_wechat.setdefault("last_error", None)
        browser_wechat["selectors_version"] = wechat_channel["selectors_version"]
        browser_wechat.setdefault("last_screenshot", None)
        browser_wechat.setdefault("last_selector_check", None)
        browser_wechat.setdefault("current_page", wechat_channel["publish_entry_url"])
        browser_wechat.setdefault("sidecar_health", "offline")
        browser_wechat.setdefault("manager_alive", False)
        browser_wechat.setdefault("window_state", "unknown")
        browser_wechat.setdefault("resident_page", None)
        browser_wechat.setdefault("busy", False)
        browser_wechat.setdefault("last_reset_reason", None)
        browser_wechat.setdefault("session_generation", 0)
        browser_wechat.setdefault("last_action", None)
        browser_wechat.setdefault("last_action_phase", None)
        browser_wechat.setdefault("is_session_level_error", False)
        browser_wechat.setdefault("last_draft_check", None)
        runtime = state.setdefault("runtime", {})
        runtime.setdefault("scheduler_running", False)
        runtime.setdefault("control_state", "stopped")
        runtime.setdefault("launch_mode", "interval_now")
        runtime.setdefault("current_mode", state.get("automation_mode", "radar_only"))
        runtime.setdefault("work_scope", state.get("runtime_plan", {}).get("work_scope", "collect_events_alerts"))
        runtime.setdefault("last_collect_at", None)
        runtime.setdefault("last_event_sync_at", None)
        runtime.setdefault("last_brief_at", None)
        runtime.setdefault("next_collect_at", None)
        runtime.setdefault("delivery_mode", "immediate")
        runtime.setdefault("delivery_schedule_time", None)
        runtime.setdefault("admission_strategy", "balanced")
        runtime.setdefault("batch_limit", 3)
        runtime.setdefault("current_cycle", "idle")
        runtime.setdefault("current_cycle_progress_percent", 0)
        runtime.setdefault("current_cycle_progress_done", 0)
        runtime.setdefault("current_cycle_progress_total", 0)
        runtime.setdefault("current_cycle_progress_label", None)
        runtime.setdefault("enabled_at", None)
        runtime.setdefault("scheduled_start_at", None)
        runtime.setdefault("current_cycle_started_at", None)
        runtime.setdefault("last_cycle_started_at", None)
        runtime.setdefault("last_cycle_finished_at", None)
        runtime.setdefault("last_cycle_duration_seconds", None)
        runtime.setdefault("completed_cycles_today", 0)
        runtime.setdefault("failed_cycles_today", 0)
        runtime.setdefault("counters_date", local_now().date().isoformat())
        runtime.setdefault("last_error", None)
        runtime.setdefault("blocked_reason", None)
        runtime.setdefault("last_successful_sync_at", None)
        runtime.setdefault("current_cycle_sources", [])
        runtime.setdefault("current_cycle_metrics", {
            "selected_event_count": 0,
            "deep_dive_count": 0,
            "brief_count": 0,
            "wechat_sync_count": 0,
            "wechat_verify_count": 0,
            "publish_count": 0,
            "selected_titles": [],
            "brief_titles": [],
            "synced_titles": [],
        })
        runtime.setdefault("last_cycle_summary", None)
        automation_run = runtime.setdefault("automation_run", {})
        automation_run.setdefault("run_id", None)
        automation_run.setdefault("status", "idle")
        automation_run.setdefault("stage", "idle")
        automation_run.setdefault("started_at", None)
        automation_run.setdefault("heartbeat_at", None)
        automation_run.setdefault("finished_at", None)
        automation_run.setdefault("triggered_by", None)
        automation_run.setdefault("error", None)
        automation_run.setdefault("recovered_run_id", None)
        automation_run.setdefault("intent", DEFAULT_RUNTIME_INTENT)
        automation_run.setdefault("last_run_outcome", None)
        for event in state.get("intel_events", []):
            event.setdefault("entity_ids", [])
            event.setdefault("entity_names", [])
            event.setdefault("deep_dive_id", None)
            event.setdefault("brief_id", None)
        for alert in state.get("intel_alerts", []):
            alert.setdefault("entity_ids", [])
            alert.setdefault("entity_names", [])
            alert.setdefault("deep_dive_id", None)
            alert.setdefault("brief_id", None)
        state["intel_event_history"] = self._prune_intel_event_history(state.get("intel_event_history", []))
        state["intel_alert_history"] = self._prune_intel_alert_history(state.get("intel_alert_history", []))
        sanitized_watchlist: list[dict[str, Any]] = []
        for raw_item in settings.get("entity_watchlist", []):
            if not isinstance(raw_item, dict):
                continue
            normalized = self._normalize_entity_watchlist_item(raw_item)
            if normalized:
                sanitized_watchlist.append(normalized)
        settings["entity_watchlist"] = sanitized_watchlist
        for source in state.get("sources", []):
            source.setdefault("last_attempt_at", None)
            source.setdefault("last_success_at", None)
            source.setdefault("last_failure_at", None)
            source.setdefault("consecutive_failures", 0)
            source.setdefault("last_duration_ms", None)
            source.setdefault("avg_duration_ms", None)
            source.setdefault("last_item_count", int(source.get("item_count", 0) or 0))
        self._purge_synthetic_state(state)
        for log in state.get("logs", []):
            log.setdefault("stream", "business_event")
            log.setdefault("actor", "system")
            log.setdefault("detail", None)
        for deep_dive in state.get("event_deep_dives", []):
            deep_dive.setdefault("status", "pending")
            deep_dive.setdefault("started_at", None)
            deep_dive.setdefault("finished_at", None)
            deep_dive.setdefault("updated_at", now_iso())
            deep_dive.setdefault("attempted_count", 0)
            deep_dive.setdefault("success_count", 0)
            deep_dive.setdefault("failed_count", 0)
            deep_dive.setdefault("resolved_evidence_pack", [])
            deep_dive.setdefault("full_text_sources", [])
            deep_dive.setdefault("sources", [])
            deep_dive.setdefault("facts", [])
            deep_dive.setdefault("quotes", [])
            deep_dive.setdefault("timeline", [])
            deep_dive.setdefault("worthiness", {})
            deep_dive.setdefault("last_error", None)
            for source in deep_dive.get("sources", []):
                if isinstance(source, dict):
                    source.setdefault("cleaned_full_text", "")
        for brief in state.get("briefs", []):
            if "wechat_draft_id" in brief and "wechat_target_id" not in brief:
                brief["wechat_target_id"] = brief.get("wechat_draft_id")
            brief.setdefault("brief_level", "rule")
            brief.setdefault("stage", "prepared")
            brief.setdefault("one_line", "")
            brief.setdefault("why_it_matters", "")
            brief.setdefault("facts", [])
            brief.setdefault("quotes", [])
            brief.setdefault("timeline", [])
            brief.setdefault("entity_names", [])
            brief.setdefault("source_links", [])
            brief.setdefault("risk_notes", [])
            brief.setdefault("prompt_package_markdown", "")
            brief.setdefault("wechat_markdown", "")
            brief.setdefault("wechat_html", "")
            brief.setdefault("wechat_target_id", None)
            brief.setdefault("wechat_editor_url", None)
            brief.setdefault("wechat_remote_appmsg_id", None)
            brief.setdefault("preview_url", None)
            brief.setdefault("last_error", None)
            brief.setdefault("delivery_status", "idle")
            brief.setdefault("delivery_attempt_count", 0)
            brief.setdefault("last_delivery_attempt_at", None)
            brief.setdefault("last_verified_at", None)
            brief.setdefault("last_delivery_error_kind", None)
            brief.setdefault("needs_resync", False)
            brief.setdefault("last_synced_revision", None)
            brief.setdefault("last_successful_upload_at", None)
            brief.setdefault("driver_label", "")
            brief.setdefault("updated_at", now_iso())
            brief.pop("wechat_draft_id", None)
        profiles_by_mode = {item["mode"]: item for item in state.get("automation_profiles", []) if isinstance(item, dict)}
        merged_profiles: list[dict[str, Any]] = []
        for default_profile in deepcopy(DEFAULT_AUTOMATION_PROFILES):
            profile = profiles_by_mode.get(default_profile["mode"], {})
            if "draft_trigger" in profile and "brief_trigger" not in profile:
                profile["brief_trigger"] = profile.get("draft_trigger")
            if "draft_schedule_time" in profile and "brief_schedule_time" not in profile:
                profile["brief_schedule_time"] = profile.get("draft_schedule_time")
            if "draft_delivery" in profile and "delivery_target" not in profile:
                profile["delivery_target"] = profile.get("draft_delivery")
            if "draft_selection" in profile and "selection_mode" not in profile:
                profile["selection_mode"] = profile.get("draft_selection")
            if "draft_limit" in profile and "brief_limit" not in profile:
                profile["brief_limit"] = profile.get("draft_limit")
            merged = {**default_profile, **profile}
            merged.pop("draft_trigger", None)
            merged.pop("draft_schedule_time", None)
            merged.pop("draft_delivery", None)
            merged.pop("draft_selection", None)
            merged.pop("draft_limit", None)
            merged_profiles.append(merged)
        state["automation_profiles"] = merged_profiles
        mode_defs_by_key = {item["key"]: item for item in state.get("automation_mode_definitions", []) if isinstance(item, dict)}
        merged_mode_defs: list[dict[str, Any]] = []
        for default_mode in deepcopy(AUTOMATION_MODE_DEFINITIONS):
            existing_mode = mode_defs_by_key.get(default_mode["key"], {})
            if "auto_generate_candidates" in existing_mode and "auto_build_events" not in existing_mode:
                existing_mode["auto_build_events"] = existing_mode.get("auto_generate_candidates")
            if "auto_generate_drafts" in existing_mode and "auto_build_briefs" not in existing_mode:
                existing_mode["auto_build_briefs"] = existing_mode.get("auto_generate_drafts")
            merged_mode_defs.append({**existing_mode, **default_mode})
        state["automation_mode_definitions"] = merged_mode_defs
        state.pop("current_mode", None)
        state.pop("mode_definitions", None)
        return state

    def _automation_mode_map(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {item["key"]: item for item in state["automation_mode_definitions"]}

    def _current_automation_mode_def(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._automation_mode_map(state)[state["automation_mode"]]

    def _automation_profile_map(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {item["mode"]: item for item in state.get("automation_profiles", [])}

    def _current_automation_profile(self, state: dict[str, Any]) -> dict[str, Any]:
        profile = self._automation_profile_map(state).get(state["automation_mode"])
        if profile:
            return profile
        return next(item for item in DEFAULT_AUTOMATION_PROFILES if item["mode"] == state["automation_mode"])

    def _default_runtime_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        profile = self._current_automation_profile(state)
        interval = profile.get("collect_interval_minutes")
        try:
            interval_minutes = max(int(interval), 5)
        except (TypeError, ValueError):
            interval_minutes = 30
        return {
            "launch_mode": "interval_now",
            "start_at": None,
            "interval_minutes": interval_minutes,
            "timezone": "Asia/Shanghai",
            "work_scope": "collect_events_alerts",
            "delivery_mode": "immediate",
            "delivery_schedule_time": None,
            "admission_strategy": "balanced",
            "batch_limit": 3,
            "admission_filters": {
                "require_watchlisted": False,
                "require_entity_match": False,
                "min_source_count": 0,
                "min_fulltext_count": 1,
                "breakout_only": False,
                "exclude_existing_brief": True,
                "exclude_synced_brief": True,
            },
        }

    def _runtime_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        runtime_plan = state.setdefault("runtime_plan", {})
        defaults = self._default_runtime_plan(state)
        for key, value in defaults.items():
            runtime_plan.setdefault(key, value)
        runtime_plan["timezone"] = str(runtime_plan.get("timezone") or "Asia/Shanghai")
        runtime_plan["launch_mode"] = str(runtime_plan.get("launch_mode") or "interval_now")
        runtime_plan["delivery_mode"] = str(runtime_plan.get("delivery_mode") or "immediate")
        runtime_plan["admission_strategy"] = str(runtime_plan.get("admission_strategy") or "balanced")
        try:
            runtime_plan["batch_limit"] = max(int(runtime_plan.get("batch_limit") or defaults["batch_limit"]), 1)
        except (TypeError, ValueError):
            runtime_plan["batch_limit"] = defaults["batch_limit"]
        filters = runtime_plan.get("admission_filters")
        if not isinstance(filters, dict):
            filters = {}
        runtime_plan["admission_filters"] = {
            **deepcopy(defaults["admission_filters"]),
            **filters,
        }
        # Normal monitoring always runs the full intel chain; intermediate scopes
        # are kept only as transient maintenance actions, not as saved user plans.
        runtime_plan["work_scope"] = "collect_events_alerts"
        launch_mode = runtime_plan["launch_mode"]
        if launch_mode in {"once_now", "interval_now"}:
            runtime_plan["start_at"] = None
        if launch_mode in {"once_now", "once_at"}:
            runtime_plan["interval_minutes"] = None
        else:
            try:
                runtime_plan["interval_minutes"] = max(int(runtime_plan.get("interval_minutes") or defaults["interval_minutes"]), 5)
            except (TypeError, ValueError):
                runtime_plan["interval_minutes"] = defaults["interval_minutes"]
        if runtime_plan["delivery_mode"] != "scheduled_batch":
            runtime_plan["delivery_schedule_time"] = None
        else:
            schedule_value = str(runtime_plan.get("delivery_schedule_time") or "").strip()
            runtime_plan["delivery_schedule_time"] = schedule_value if parse_clock_time(schedule_value) else "09:00"
        return runtime_plan

    def _runtime_plan_from_state(self, state: dict[str, Any]) -> RuntimePlan:
        plan = self._runtime_plan(state)
        return RuntimePlan(
            launch_mode=str(plan.get("launch_mode") or "interval_now"),
            start_at=plan.get("start_at"),
            interval_minutes=plan.get("interval_minutes"),
            timezone=str(plan.get("timezone") or "Asia/Shanghai"),
            effective_mode=state.get("automation_mode", "radar_only"),
            work_scope=str(plan.get("work_scope") or "collect_events_alerts"),
            delivery_mode=str(plan.get("delivery_mode") or "immediate"),
            delivery_schedule_time=plan.get("delivery_schedule_time"),
            admission_strategy=str(plan.get("admission_strategy") or "balanced"),
            batch_limit=max(int(plan.get("batch_limit", 3) or 3), 1),
            admission_filters=deepcopy(plan.get("admission_filters", {})),
        )

    def _sync_runtime_counters(self, runtime: dict[str, Any]) -> None:
        today = local_now().date().isoformat()
        if runtime.get("counters_date") != today:
            runtime["counters_date"] = today
            runtime["completed_cycles_today"] = 0
            runtime["failed_cycles_today"] = 0

    def _calculate_runtime_next_collect_at(self, state: dict[str, Any], now: datetime | None = None) -> str | None:
        now = now or datetime.now(UTC)
        runtime = self._runtime(state)
        plan = self._runtime_plan(state)
        control_state = str(runtime.get("control_state") or "stopped")
        launch_mode = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")

        if control_state == "stopped":
            return None
        if control_state == "armed":
            return runtime.get("scheduled_start_at") or plan.get("start_at")
        if launch_mode in {"once_now", "once_at"}:
            return None

        interval_minutes = runtime.get("active_interval_minutes")
        try:
            interval_minutes = max(int(interval_minutes or plan.get("interval_minutes") or 30), 5)
        except (TypeError, ValueError):
            interval_minutes = 30
        base = (
            parse_time(runtime.get("last_cycle_started_at"))
            or parse_time(runtime.get("enabled_at"))
            or now
        )
        next_at = base + timedelta(minutes=interval_minutes)
        if next_at < now and control_state != "running":
            next_at = now
        return next_at.replace(microsecond=0).isoformat()

    def _is_slot_due(self, last_run_at: str | None, slot_time: str | None, now: datetime | None = None) -> bool:
        clock = parse_clock_time(slot_time)
        if not clock:
            return False
        now = now or datetime.now(UTC)
        slot_dt = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if now < slot_dt:
            return False
        last_run = parse_time(last_run_at)
        if not last_run:
            return True
        return last_run < slot_dt

    def _collect_interval_for_profile(self, state: dict[str, Any]) -> int | None:
        profile = self._current_automation_profile(state)
        value = profile.get("collect_interval_minutes")
        try:
            minutes = int(value)
        except (TypeError, ValueError):
            return None
        return max(minutes, 5)

    def _append_log(
        self,
        state: dict[str, Any],
        level: str,
        category: str,
        message: str,
        *,
        stream: str = "business_event",
        actor: str = "system",
        detail: str | None = None,
    ) -> None:
        state["logs"].insert(
            0,
            {
                "id": f"log-{uuid4().hex[:8]}",
                "level": level,
                "category": category,
                "message": message,
                "created_at": now_iso(),
                "stream": stream,
                "actor": actor,
                "detail": detail,
            },
        )
        state["logs"] = state["logs"][:180]

    def _append_job(
        self,
        state: dict[str, Any],
        action: str,
        message: str,
        status: str = "completed",
        triggered_by: str = "dashboard",
    ) -> dict[str, Any]:
        stamp = now_iso()
        item = {
            "id": f"job-{uuid4().hex[:8]}",
            "action": action,
            "label": JOB_LABELS[action],
            "status": status,
            "triggered_by": triggered_by,
            "started_at": stamp,
            "finished_at": stamp,
            "message": message,
        }
        state["jobs"].insert(0, item)
        state["jobs"] = state["jobs"][:60]
        return item

    def _sources_by_key(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {item["key"]: item for item in state["sources"]}

    def _find_source(self, state: dict[str, Any], source_key: str) -> dict[str, Any]:
        for source in state["sources"]:
            if source["key"] == source_key:
                return source
        raise ValueError(f"Source not found: {source_key}")

    def _normalized_id_for_event(self, event_id: str) -> str:
        return f"norm-{event_id}"

    def _build_normalized_item_from_event(self, event: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": self._normalized_id_for_event(str(event.get("id") or "")),
            "raw_item_ids": list(event.get("discovery_item_ids", [])),
            "title": event.get("title", ""),
            "link": event.get("representative_link", ""),
            "summary": event.get("summary", ""),
            "published_at": event.get("published_at"),
            "cluster_id": event.get("id"),
            "cluster_members": list(event.get("discovery_item_ids", [])),
            "dedupe_key": str(event.get("id") or ""),
            "source_names": list(event.get("source_names", [])),
            "origin_sources": list(event.get("source_keys", [])),
            "source_weight": round(min(float(event.get("coverage_score", 0) or 0) / 100.0, 1.0), 2),
            "trend_score": float(event.get("velocity_score", 0) or 0),
            "final_score": float(event.get("composite_score", 0) or 0),
            "signals": [str(event.get("alert_reason") or "多平台聚合事件")],
            "score_breakdown": {
                "velocity": float(event.get("velocity_score", 0) or 0),
                "coverage": float(event.get("coverage_score", 0) or 0),
                "freshness": float(event.get("freshness_score", 0) or 0),
            },
            "collected_at": event.get("latest_collected_at"),
            "freshness_bucket": freshness_bucket(event.get("latest_collected_at")),
        }

    def _event_evidence_pack(self, state: dict[str, Any], event: dict[str, Any]) -> list[dict[str, Any]]:
        seen_links: set[str] = set()
        evidence_pack: list[dict[str, Any]] = []
        candidate_items = self._rank_event_discovery_items(state, event)

        for item in candidate_items:
            link = str(item.get("link") or "").strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            evidence_pack.append(
                {
                    "discovery_item_id": str(item.get("id") or ""),
                    "source_name": str(item.get("source_name") or ""),
                    "title": str(item.get("title") or ""),
                    "summary": str(item.get("summary") or ""),
                    "link": link,
                    "published_at": item.get("published_at"),
                    "collected_at": item.get("collected_at"),
                    "entity_names": list(item.get("entity_names", [])),
                }
            )
            if len(evidence_pack) >= 5:
                break
        return evidence_pack

    def _event_deep_dive_inputs(self, state: dict[str, Any], event: dict[str, Any]) -> list[dict[str, Any]]:
        candidate_items = self._rank_event_discovery_items(state, event)
        seen_links: set[str] = set()
        resolved: list[dict[str, Any]] = []

        def append_item(item: dict[str, Any]) -> None:
            link = str(item.get("link") or "").strip()
            canonical = canonicalize_url(link)
            identity = canonical or link
            if not identity or identity in seen_links:
                return
            seen_links.add(identity)
            resolved.append(
                {
                    "discovery_item_id": str(item.get("id") or ""),
                    "source_key": str(item.get("source_key") or ""),
                    "source_name": str(item.get("source_name") or ""),
                    "title": str(item.get("title") or ""),
                    "summary": str(item.get("summary") or ""),
                    "link": link,
                    "canonical_link": canonical or link,
                    "published_at": item.get("published_at"),
                    "collected_at": item.get("collected_at"),
                    "entity_names": list(item.get("entity_names", [])),
                }
            )
        for item in candidate_items:
            append_item(item)

        tavily_api_key = str(state.get("settings", {}).get("tavily_api_key") or "").strip()
        if tavily_api_key:
            query_parts = [str(event.get("title") or "").strip()]
            query_parts.extend([name for name in event.get("entity_names", [])[:4] if str(name).strip()])
            if str(event.get("summary") or "").strip():
                query_parts.append(str(event.get("summary") or "").strip()[:180])
            tavily_query = " ".join(part for part in query_parts if part).strip()
            for item in search_tavily(api_key=tavily_api_key, query=tavily_query, max_results=5):
                append_item(item)
        return resolved

    def _discovery_lookup(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("id") or ""): item
            for item in state.get("discovery_items", [])
            if isinstance(item, dict) and item.get("id")
        }

    def _event_lookup(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(item.get("id") or ""): item
            for item in state.get("intel_events", [])
            if isinstance(item, dict) and item.get("id")
        }

    @staticmethod
    def _event_discovery_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            parse_time(item.get("published_at")) or datetime.min.replace(tzinfo=UTC),
            parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC),
            float(item.get("engagement_score", 0) or 0),
        )

    def _rank_event_discovery_items(self, state: dict[str, Any], event: dict[str, Any]) -> list[dict[str, Any]]:
        discovery_by_id = self._discovery_lookup(state)
        representative_id = str(event.get("representative_discovery_item_id") or "").strip()
        candidate_items = [
            discovery_by_id[item_id]
            for item_id in event.get("discovery_item_ids", [])
            if item_id in discovery_by_id
        ]
        candidate_items.sort(key=self._event_discovery_sort_key, reverse=True)
        if representative_id and representative_id in discovery_by_id:
            candidate_items.sort(key=lambda item: str(item.get("id") or "") != representative_id)
        return candidate_items

    def _deep_dive_lookup(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for item in state.get("event_deep_dives", []):
            if not isinstance(item, dict):
                continue
            event_id = str(item.get("event_id") or "").strip()
            if not event_id:
                continue
            current = lookup.get(event_id)
            if not current:
                lookup[event_id] = item
                continue
            current_updated = parse_time(current.get("updated_at")) or datetime.min.replace(tzinfo=UTC)
            item_updated = parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC)
            if item_updated >= current_updated:
                lookup[event_id] = item
        return lookup

    def _brief_lookup(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for item in state.get("briefs", []):
            if not isinstance(item, dict):
                continue
            event_id = str(item.get("event_id") or "").strip()
            if not event_id:
                continue
            current = lookup.get(event_id)
            if not current:
                lookup[event_id] = item
                continue
            current_updated = parse_time(current.get("updated_at")) or datetime.min.replace(tzinfo=UTC)
            item_updated = parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC)
            if item_updated >= current_updated:
                lookup[event_id] = item
        return lookup

    def _find_deep_dive_record(self, state: dict[str, Any], deep_dive_id: str) -> dict[str, Any]:
        for item in state.get("event_deep_dives", []):
            if isinstance(item, dict) and str(item.get("id") or "") == deep_dive_id:
                return item
        raise ValueError(f"未找到正文深挖记录：{deep_dive_id}")

    def _find_deep_dive_for_event(
        self,
        state: dict[str, Any],
        event_id: str,
        *,
        deep_dive_lookup: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        return (deep_dive_lookup or self._deep_dive_lookup(state)).get(event_id)

    def _find_brief(self, state: dict[str, Any], brief_id: str) -> dict[str, Any]:
        for item in state.get("briefs", []):
            if isinstance(item, dict) and str(item.get("id") or "") == brief_id:
                return item
        raise ValueError(f"未找到简报：{brief_id}")

    def _find_brief_for_event(
        self,
        state: dict[str, Any],
        event_id: str,
        *,
        brief_lookup: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        return (brief_lookup or self._brief_lookup(state)).get(event_id)

    def _find_brief_record_for_event_by_level(
        self,
        state: dict[str, Any],
        event_id: str,
        *,
        brief_level: str,
    ) -> dict[str, Any] | None:
        matched: dict[str, Any] | None = None
        matched_updated = datetime.min.replace(tzinfo=UTC)
        for item in state.get("briefs", []):
            if not isinstance(item, dict):
                continue
            if str(item.get("event_id") or "").strip() != str(event_id or "").strip():
                continue
            if str(item.get("brief_level") or "rule").strip() != brief_level:
                continue
            item_updated = parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC)
            if matched is None or item_updated >= matched_updated:
                matched = item
                matched_updated = item_updated
        return matched

    def _summarize_deep_dive(self, deep_dive: dict[str, Any] | None) -> str:
        if not deep_dive:
            return "尚未开始正文深挖。"
        status = str(deep_dive.get("status") or "pending")
        attempted = int(deep_dive.get("attempted_count", 0) or 0)
        success = int(deep_dive.get("success_count", 0) or 0)
        failed = int(deep_dive.get("failed_count", 0) or 0)
        used_tavily = any(str(item.get("source_key") or "") == "tavily" for item in deep_dive.get("resolved_evidence_pack", []))
        if status == "ready":
            if used_tavily:
                return f"Tavily 补充搜索后正文深挖已完成，成功 {success}/{attempted} 条来源。"
            return f"正文深挖已完成，成功 {success}/{attempted} 条来源。"
        if status == "partial":
            if used_tavily:
                return f"Tavily 补充搜索后部分完成，成功 {success}/{attempted} 条来源，失败 {failed} 条。"
            return f"正文深挖部分完成，成功 {success}/{attempted} 条来源，失败 {failed} 条。"
        if status == "failed":
            return str(deep_dive.get("last_error") or "正文深挖失败。")
        if status == "running":
            return "正在补充来源并抓取正文。"
        return "等待正文深挖。"

    def _evaluate_worthiness(self, event: dict[str, Any], deep_dive: dict[str, Any]) -> tuple[bool, str]:
        alert_state = str(event.get("alert_state") or "")
        watchlisted = bool(event.get("watchlisted"))
        success_count = int(deep_dive.get("success_count", 0) or 0)
        facts = [item for item in deep_dive.get("facts", []) if str(item).strip()]
        quotes = [item for item in deep_dive.get("quotes", []) if str(item).strip()]
        if success_count < 1:
            return False, "正文深挖仍未拿到可用正文来源。"
        if not facts and not quotes:
            return False, "已抓取正文，但还没有足够可复用的事实或引文。"
        if alert_state in {"rising", "breakout"}:
            return True, f"事件处于 {alert_state} 阶段，且已有可引用正文证据。"
        if watchlisted:
            return True, "事件已进入深挖池，且已有正文证据，可生成简报继续跟进。"
        return False, "当前仍未进入重点观察或上升/爆发态，建议继续观察。"

    def _delivery_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._runtime_plan(state)

    def _delivery_filters(self, state: dict[str, Any]) -> dict[str, Any]:
        plan = self._delivery_plan(state)
        filters = plan.get("admission_filters", {})
        if not isinstance(filters, dict):
            filters = {}
        return {
            "require_watchlisted": bool(filters.get("require_watchlisted")),
            "require_entity_match": bool(filters.get("require_entity_match")),
            "min_source_count": max(int(filters.get("min_source_count", 0) or 0), 0),
            "min_fulltext_count": max(int(filters.get("min_fulltext_count", 1) or 1), 0),
            "breakout_only": bool(filters.get("breakout_only")),
            "exclude_existing_brief": bool(filters.get("exclude_existing_brief", True)),
            "exclude_synced_brief": bool(filters.get("exclude_synced_brief", True)),
        }

    def _delivery_mode_due(self, state: dict[str, Any], now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        plan = self._delivery_plan(state)
        mode = str(plan.get("delivery_mode") or "immediate")
        if mode != "scheduled_batch":
            return True
        clock = parse_clock_time(str(plan.get("delivery_schedule_time") or ""))
        if not clock:
            return False
        runtime = self._runtime(state)
        slot_dt = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if now < slot_dt:
            return False
        last_verified = parse_time(runtime.get("last_delivery_batch_at"))
        if not last_verified:
            return True
        return last_verified < slot_dt

    def _background_draft_check_due(self, state: dict[str, Any], now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        browser = state.get("browser", {}).get("wechat", {})
        if not isinstance(browser, dict):
            return False
        if not bool(browser.get("logged_in")):
            return False
        if bool(browser.get("busy")):
            return False
        checked_at = parse_time(browser.get("last_draft_check", {}).get("checked_at") if isinstance(browser.get("last_draft_check"), dict) else None)
        if not checked_at:
            return True
        return (now - checked_at).total_seconds() >= 120

    def run_background_wechat_draft_check(self) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        now = datetime.now(UTC)
        if not self._background_draft_check_due(state, now):
            return {"status": "skipped", "reason": "not_due"}
        try:
            result = self.check_wechat_draft_box()
            return {
                "status": "checked",
                "checked_at": result.checked_at,
                "remote_count": result.remote_count,
                "matched_count": result.matched_count,
                "missing_count": result.missing_count,
            }
        except Exception as exc:
            latest_state = self._upgrade_state(self._read())
            self._append_log(
                latest_state,
                "warning",
                "browser",
                f"后台静默草稿箱检查失败：{exc}",
                stream="system_runtime",
                actor="wechat_poll",
            )
            with self._lock:
                self._write(latest_state)
            return {"status": "failed", "reason": str(exc)}

    def _select_delivery_events_strict(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        plan = self._delivery_plan(state)
        strategy = str(plan.get("admission_strategy") or "balanced")
        filters = self._delivery_filters(state)
        limit = max(int(plan.get("batch_limit", 3) or 3), 1)
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)

        projected_events = [
            self._project_event_runtime_fields(state, item)
            for item in state.get("intel_events", [])
            if isinstance(item, dict) and not bool(item.get("ignored"))
        ]

        selected: list[dict[str, Any]] = []
        for event in projected_events:
            if filters["require_watchlisted"] and not bool(event.get("watchlisted")):
                continue
            if filters["require_entity_match"] and not list(event.get("entity_names", [])):
                continue
            if filters["breakout_only"] and str(event.get("alert_state") or "") != "breakout":
                continue
            if int(event.get("source_count", 0) or 0) < filters["min_source_count"]:
                continue
            if filters["exclude_existing_brief"] and str(event.get("brief_id") or "").strip():
                continue
            if filters["exclude_synced_brief"]:
                brief = brief_lookup.get(str(event.get("id") or ""))
                if brief and str(brief.get("stage") or "") == "synced":
                    continue

            alert_state = str(event.get("alert_state") or "")
            deep_dive = deep_dive_lookup.get(str(event.get("id") or ""))
            fulltext_count = int(deep_dive.get("success_count", 0) or 0) if deep_dive else 0

            if strategy == "conservative":
                if alert_state != "breakout":
                    continue
                if fulltext_count < max(filters["min_fulltext_count"], 2):
                    continue
                if not bool(event.get("worth_to_brief")):
                    continue
            elif strategy == "balanced":
                if alert_state not in {"rising", "breakout"}:
                    continue
                if deep_dive and fulltext_count < max(filters["min_fulltext_count"], 1):
                    continue
            else:
                if alert_state not in {"rising", "breakout"} and not bool(event.get("watchlisted")):
                    continue

            selected.append(event)

        selected.sort(key=lambda item: self._delivery_sort_key(item, deep_dive_lookup), reverse=True)
        return selected[:limit]

    def _select_delivery_events(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        plan = self._delivery_plan(state)
        filters = self._delivery_filters(state)
        selected = self._select_delivery_events_strict(state)
        if selected:
            return selected
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)

        projected_events = [
            self._project_event_runtime_fields(state, item)
            for item in state.get("intel_events", [])
            if isinstance(item, dict) and not bool(item.get("ignored"))
        ]

        limit = max(int(plan.get("batch_limit", 3) or 3), 1)
        fallback_candidates: list[dict[str, Any]] = []
        for event in projected_events:
            if not bool(event.get("worth_to_brief")):
                continue
            alert_state = str(event.get("alert_state") or "")
            if alert_state == "cooling" or alert_state == "new":
                continue
            if filters["require_watchlisted"] and not bool(event.get("watchlisted")):
                continue
            if filters["require_entity_match"] and not list(event.get("entity_names", [])):
                continue
            if int(event.get("source_count", 0) or 0) < filters["min_source_count"]:
                continue
            if filters["exclude_existing_brief"] and str(event.get("brief_id") or "").strip():
                continue
            if filters["exclude_synced_brief"]:
                brief = brief_lookup.get(str(event.get("id") or ""))
                if brief and str(brief.get("stage") or "") == "synced":
                    continue
            if str(event.get("alert_state") or "") == "cooling":
                continue
            fallback_candidates.append(event)

        fallback_candidates.sort(key=lambda item: self._delivery_sort_key(item, deep_dive_lookup), reverse=True)
        return fallback_candidates[:1]

    def _select_retry_briefs(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        event_lookup = {str(item.get("id") or ""): item for item in state.get("intel_events", []) if isinstance(item, dict) and item.get("id")}
        candidates = [
            item for item in state.get("briefs", [])
            if isinstance(item, dict) and (
                bool(item.get("needs_resync"))
                or str(item.get("stage") or "") in {"prepared", "failed"}
            )
        ]

        def retry_rank(item: dict[str, Any]) -> tuple[Any, ...]:
            needs_resync = bool(item.get("needs_resync"))
            stage = str(item.get("stage") or "")
            if needs_resync:
                priority = 0
            elif stage == "failed":
                priority = 1
            else:
                priority = 2
            event = event_lookup.get(str(item.get("event_id") or "")) if str(item.get("event_id") or "").strip() else None
            updated_at = parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC)
            composite_score = float((event or {}).get("composite_score", 0) or 0)
            watchlisted = 1 if bool((event or {}).get("watchlisted")) else 0
            return (
                priority,
                -updated_at.timestamp(),
                -composite_score,
                -watchlisted,
            )

        candidates.sort(key=retry_rank)
        limit = max(int(self._delivery_plan(state).get("batch_limit", 3) or 3), 1)
        return candidates[:limit]

    def _delivery_sort_key(self, item: dict[str, Any], deep_dive_lookup: dict[str, dict[str, Any]]) -> tuple[Any, ...]:
        alert_rank = {"breakout": 3, "rising": 2, "watch": 1, "cooling": 0, "new": 0}.get(str(item.get("alert_state") or "new"), 0)
        deep_dive = deep_dive_lookup.get(str(item.get("id") or ""))
        evidence_score = int(deep_dive.get("success_count", 0) or 0) if deep_dive else 0
        return (
            alert_rank,
            float(item.get("worth_to_brief") or False),
            float(item.get("composite_score", 0) or 0),
            float(item.get("velocity_score", 0) or 0),
            float(item.get("coverage_score", 0) or 0),
            float(item.get("freshness_score", 0) or 0),
            evidence_score,
            len(list(item.get("entity_names", []))),
        )

    def _run_delivery_pipeline(self, state: dict[str, Any], runtime: dict[str, Any], *, triggered_by: str) -> None:
        plan = self._delivery_plan(state)
        due_for_upload = self._select_retry_briefs(state)
        events: list[dict[str, Any]] = []
        if len(due_for_upload) < max(int(plan.get("batch_limit", 3) or 3), 1):
            events = self._select_delivery_events(state)
        selected_titles = [str(item.get("title") or "").strip() for item in events if str(item.get("title") or "").strip()]
        self._set_runtime_cycle_metric(runtime, "selected_event_count", len(events))
        runtime.setdefault("current_cycle_metrics", {})["selected_titles"] = selected_titles[:5]
        if not due_for_upload and not events:
            self._append_log(state, "info", "delivery", "本轮没有符合自动交付条件的事件，也没有待补传简报。", stream="system_runtime", actor=triggered_by)
            return
        strict_matches = self._select_delivery_events_strict(state)
        if events and not strict_matches:
            fallback_event = events[0]
            self._append_log(
                state,
                "warning",
                "delivery",
                f"严格筛选未命中，本轮改为兜底推进最高分事件：{fallback_event.get('title') or fallback_event.get('id') or 'unknown'}",
                stream="system_runtime",
                actor=triggered_by,
            )
        elif not events and not strict_matches and not due_for_upload:
            self._append_log(state, "info", "delivery", "本轮严格筛选和兜底筛选均未命中，跳过交付。", stream="system_runtime", actor=triggered_by)
            return

        stage_plan = self._stage_plan(runtime)
        stage_positions = {item["key"]: index + 1 for index, item in enumerate(stage_plan)}
        stage_total = len(stage_plan)

        deep_dives_completed = 0
        briefs_completed = 0
        synced_completed = 0
        verify_completed = 0
        brief_titles: list[str] = []
        synced_titles: list[str] = []
        if events:
            runtime["current_cycle"] = "deep_dive"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "deep_dive", 5),
                done=0,
                total=max(len(events), 1),
                label=f"阶段 {stage_positions.get('deep_dive', stage_total)}/{stage_total}：开始正文深挖",
            )
            self._progress_snapshot["cycle"] = "deep_dive"
            self._heartbeat_runtime_run(runtime, stage="deep_dive")
            self._write_runtime_checkpoint(state)

            for index, event in enumerate(events, start=1):
                event_id = str(event.get("id") or "")
                try:
                    deep_dive = self.create_event_deep_dive(event_id).model_dump()
                    state.update(self._upgrade_state(self._read()))
                    if str(deep_dive.get("status") or "") not in {"ready", "partial"}:
                        continue
                    if int(deep_dive.get("success_count", 0) or 0) < max(int(self._delivery_filters(state)["min_fulltext_count"]), 0):
                        continue
                    deep_dives_completed += 1
                    self._set_runtime_cycle_metric(runtime, "deep_dive_count", deep_dives_completed)
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "deep_dive", index / max(len(events), 1) * 100),
                        done=index,
                        total=max(len(events), 1),
                        label=f"已完成正文深挖 {index}/{max(len(events), 1)}",
                    )
                    self._heartbeat_runtime_run(runtime, stage="deep_dive")
                    self._write_runtime_checkpoint(state)
                except Exception as exc:
                    self._append_log(state, "warning", "delivery", f"正文深挖失败：{event.get('title') or event_id} - {exc}", stream="system_runtime", actor=triggered_by)

            runtime["current_cycle"] = "briefing"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "briefing", 5),
                done=0,
                total=max(len(events), 1),
                label=f"阶段 {stage_positions.get('briefing', stage_total)}/{stage_total}：开始生成简报",
            )
            self._progress_snapshot["cycle"] = "briefing"
            self._heartbeat_runtime_run(runtime, stage="briefing")
            self._write_runtime_checkpoint(state)

            for index, event in enumerate(events, start=1):
                event_id = str(event.get("id") or "")
                refreshed_state = self._upgrade_state(self._read())
                deep_dive = self._find_deep_dive_for_event(refreshed_state, event_id)
                if not deep_dive or str(deep_dive.get("status") or "") not in {"ready", "partial"}:
                    continue
                if int(deep_dive.get("success_count", 0) or 0) < max(int(self._delivery_filters(refreshed_state)["min_fulltext_count"]), 0):
                    continue
                try:
                    brief = self.create_brief_from_event(event_id).model_dump()
                    state.update(self._upgrade_state(self._read()))
                    briefs_completed += 1
                    due_for_upload.append(brief)
                    brief_title = str(brief.get("title") or "").strip()
                    if brief_title:
                        brief_titles.append(brief_title)
                    self._set_runtime_cycle_metric(runtime, "brief_count", briefs_completed)
                    runtime.setdefault("current_cycle_metrics", {})["brief_titles"] = brief_titles[:5]
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "briefing", index / max(len(events), 1) * 100),
                        done=index,
                        total=max(len(events), 1),
                        label=f"已生成简报 {briefs_completed}/{max(len(events), 1)}",
                    )
                    self._heartbeat_runtime_run(runtime, stage="briefing")
                    self._write_runtime_checkpoint(state)
                except Exception as exc:
                    self._append_log(state, "warning", "delivery", f"简报生成失败：{event.get('title') or event_id} - {exc}", stream="system_runtime", actor=triggered_by)

        delivery_due = self._delivery_mode_due(state)
        delivery_mode = str(plan.get("delivery_mode") or "immediate")
        if due_for_upload and delivery_due:
            runtime["current_cycle"] = "wechat_sync"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "wechat_sync", 5),
                done=0,
                total=max(len(due_for_upload), 1),
                label=f"阶段 {stage_positions.get('wechat_sync', stage_total)}/{stage_total}：开始上传微信草稿箱",
            )
            self._progress_snapshot["cycle"] = "wechat_sync"
            self._heartbeat_runtime_run(runtime, stage="wechat_sync")
            self._write_runtime_checkpoint(state)

            for index, brief in enumerate(due_for_upload, start=1):
                brief_id = str(brief.get("id") or "")
                try:
                    synced = self.sync_brief_wechat_draft(brief_id, triggered_by="scheduler").model_dump()
                    state.update(self._upgrade_state(self._read()))
                    if str(synced.get("stage") or "") != "synced":
                        raise RuntimeError(str(synced.get("last_error") or "上传失败"))
                    synced_completed += 1
                    synced_title = str(synced.get("title") or "").strip()
                    if synced_title:
                        synced_titles.append(synced_title)
                    self._set_runtime_cycle_metric(runtime, "wechat_sync_count", synced_completed)
                    self._set_runtime_cycle_metric(runtime, "publish_count", synced_completed)
                    runtime.setdefault("current_cycle_metrics", {})["synced_titles"] = synced_titles[:5]
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "wechat_sync", index / max(len(due_for_upload), 1) * 100),
                        done=index,
                        total=max(len(due_for_upload), 1),
                        label=f"已上传微信草稿箱 {synced_completed}/{max(len(due_for_upload), 1)}",
                    )
                    self._heartbeat_runtime_run(runtime, stage="wechat_sync")
                    self._write_runtime_checkpoint(state)
                except Exception as exc:
                    error_text = str(exc)
                    latest_state = self._upgrade_state(self._read())
                    latest_brief = self._find_brief(latest_state, brief_id)
                    if bool(latest_state.get("browser", {}).get("wechat", {}).get("is_session_level_error")):
                        runtime["blocked_reason"] = f"微信上传失败：{error_text}"
                        self._append_log(state, "error", "delivery", runtime["blocked_reason"], stream="system_runtime", actor=triggered_by)
                        raise
                    self._append_log(
                        state,
                        "warning",
                        "delivery",
                        f"简报上传失败，继续下一条：{brief.get('title') or brief_id} - {error_text}",
                        stream="system_runtime",
                        actor=triggered_by,
                    )
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "wechat_sync", index / max(len(due_for_upload), 1) * 100),
                        done=index,
                        total=max(len(due_for_upload), 1),
                        label=f"已处理微信上传 {index}/{max(len(due_for_upload), 1)}",
                    )
                    self._heartbeat_runtime_run(runtime, stage="wechat_sync")
                    self._write_runtime_checkpoint(state)

            runtime["current_cycle"] = "wechat_verify"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "wechat_verify", 15),
                done=0,
                total=max(synced_completed, 1),
                label=f"阶段 {stage_positions.get('wechat_verify', stage_total)}/{stage_total}：检查微信草稿箱",
            )
            self._progress_snapshot["cycle"] = "wechat_verify"
            self._heartbeat_runtime_run(runtime, stage="wechat_verify")
            self._write_runtime_checkpoint(state)
            verify_result = self.check_wechat_draft_box()
            verify_completed = 1 if verify_result else 0
            self._set_runtime_cycle_metric(runtime, "wechat_verify_count", verify_completed)
            runtime["last_delivery_batch_at"] = now_iso()
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "wechat_verify", 100),
                done=verify_completed,
                total=max(synced_completed, 1),
                label="微信草稿箱检查完成",
            )
            self._heartbeat_runtime_run(runtime, stage="wechat_verify")
            self._write_runtime_checkpoint(state)
        elif due_for_upload and delivery_mode == "scheduled_batch":
            self._append_log(
                state,
                "info",
                "delivery",
                f"已有 {len(due_for_upload)} 条简报待定时批量上传，等待 {plan.get('delivery_schedule_time') or '固定时间'}。",
                stream="system_runtime",
                actor=triggered_by,
            )

    def _project_event_runtime_fields(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        *,
        deep_dive_lookup: dict[str, dict[str, Any]] | None = None,
        brief_lookup: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        projected = dict(event)
        event_id = str(projected.get("id") or "")
        deep_dive = self._find_deep_dive_for_event(state, event_id, deep_dive_lookup=deep_dive_lookup)
        brief = self._find_brief_for_event(state, event_id, brief_lookup=brief_lookup)
        projected["deep_dive_id"] = deep_dive.get("id") if deep_dive else projected.get("deep_dive_id")
        projected["brief_id"] = brief.get("id") if brief else projected.get("brief_id")
        projected["deep_dive_status"] = deep_dive.get("status") if deep_dive else None
        projected["deep_dive_started_at"] = deep_dive.get("started_at") if deep_dive else None
        projected["deep_dive_finished_at"] = deep_dive.get("finished_at") if deep_dive else None
        projected["deep_dive_updated_at"] = deep_dive.get("updated_at") if deep_dive else None
        projected["brief_status"] = brief.get("stage") if brief else None
        projected["deep_dive_summary"] = self._summarize_deep_dive(deep_dive)
        worth_to_brief, worth_reason = self._evaluate_worthiness(projected, deep_dive or {})
        projected["worth_to_brief"] = worth_to_brief if deep_dive else False
        projected["worth_reason"] = worth_reason if deep_dive else "尚未完成正文深挖。"
        return projected

    def _project_alert_runtime_fields(
        self,
        state: dict[str, Any],
        alert: dict[str, Any],
        *,
        event_lookup: dict[str, dict[str, Any]] | None = None,
        deep_dive_lookup: dict[str, dict[str, Any]] | None = None,
        brief_lookup: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        projected = dict(alert)
        event_id = str(projected.get("event_id") or "")
        event = (event_lookup or self._event_lookup(state)).get(event_id)
        if not event:
            return projected
        runtime_event = self._project_event_runtime_fields(
            state,
            event,
            deep_dive_lookup=deep_dive_lookup,
            brief_lookup=brief_lookup,
        )
        projected["deep_dive_id"] = runtime_event.get("deep_dive_id")
        projected["brief_id"] = runtime_event.get("brief_id")
        projected["deep_dive_status"] = runtime_event.get("deep_dive_status")
        projected["brief_status"] = runtime_event.get("brief_status")
        projected["deep_dive_summary"] = runtime_event.get("deep_dive_summary", "")
        projected["worth_to_brief"] = bool(runtime_event.get("worth_to_brief"))
        projected["worth_reason"] = str(runtime_event.get("worth_reason") or "")
        return projected

    def _generate_deep_dive_facts(self, event: dict[str, Any], sources: list[dict[str, Any]]) -> list[str]:
        facts: list[str] = []
        if event.get("alert_reason"):
            facts.append(str(event.get("alert_reason")))
        facts.append(
            f"事件覆盖 {event.get('platform_count', 0)} 个平台、{event.get('source_count', 0)} 个来源，成员数 {event.get('member_count', 0)}。"
        )
        for item in sources:
            excerpt = str(item.get("excerpt") or "").strip()
            title = str(item.get("title") or "").strip()
            if title:
                facts.append(f"{item.get('source_name') or '来源'}提到：{title}")
            if excerpt:
                facts.append(excerpt[:140])
            if len(facts) >= 6:
                break
        deduped: list[str] = []
        seen: set[str] = set()
        for fact in facts:
            compact = str(fact).strip()
            if not compact or compact in seen:
                continue
            seen.add(compact)
            deduped.append(compact)
        return deduped[:6]

    def _build_full_text_sources_for_ai(self, deep_dive: dict[str, Any], *, limit: int | None = None) -> list[dict[str, Any]]:
        ranked_sources = [
            item for item in deep_dive.get("sources", [])
            if isinstance(item, dict)
            and str(item.get("extract_status") or "") == "extracted"
            and str(item.get("cleaned_full_text") or "").strip()
        ]
        ranked_sources.sort(
            key=lambda item: (
                int(item.get("word_count", 0) or 0),
                parse_time(item.get("published_at")) or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        payloads: list[dict[str, Any]] = []
        selected_sources = ranked_sources if limit is None else ranked_sources[:limit]
        for item in selected_sources:
            payloads.append(
                {
                    "source_name": str(item.get("source_name") or "未知来源").strip(),
                    "title": str(item.get("title") or "").strip(),
                    "published_at": item.get("published_at"),
                    "link": str(item.get("canonical_link") or item.get("original_link") or "").strip(),
                    "word_count": int(item.get("word_count", 0) or 0),
                    "cleaned_full_text": str(item.get("cleaned_full_text") or "").strip(),
                }
            )
        return payloads

    def _extract_enhanced_brief_payload(self, content: str) -> dict[str, Any]:
        payload = _extract_json_payload(content)
        if isinstance(payload, dict):
            return payload
        fenced = str(content or "").strip()
        fenced = re.sub(r"^```json\s*", "", fenced, flags=re.IGNORECASE)
        fenced = re.sub(r"^```\s*", "", fenced)
        fenced = re.sub(r"\s*```$", "", fenced)

        extracted: dict[str, Any] = {}
        one_line_match = re.search(r'"one_line"\s*:\s*"(.*?)",\s*"why_it_matters"', fenced, re.S)
        if one_line_match:
            extracted["one_line"] = one_line_match.group(1).replace('\\"', '"').strip()
        why_match = re.search(r'"why_it_matters"\s*:\s*"(.*?)",\s*"risk_notes"', fenced, re.S)
        if why_match:
            extracted["why_it_matters"] = why_match.group(1).replace('\\"', '"').strip()
        risk_match = re.search(r'"risk_notes"\s*:\s*(\[[\s\S]*?\])\s*\}?', fenced, re.S)
        if risk_match:
            try:
                parsed_risks = json.loads(risk_match.group(1))
                if isinstance(parsed_risks, list):
                    extracted["risk_notes"] = [str(item).strip() for item in parsed_risks if str(item).strip()]
            except Exception:
                pass
        return extracted

    def _build_enhancement_messages(
        self,
        event: dict[str, Any],
        brief_payload: dict[str, Any],
        full_text_sources: list[dict[str, Any]],
        *,
        retry: bool = False,
    ) -> list[dict[str, str]]:
        system_text = (
            "你是新闻编辑助手。你会收到事件元数据、已核验事实，以及系统抓取并清洗后的完整正文。"
            "请只根据这些内容输出简洁 JSON，不要补充未给出的事实，不要输出 Markdown。"
            "所有字符串值中不要使用半角双引号，如需强调请改用中文引号或直接省略引号。"
        )
        task = (
            "请阅读完整正文与已核验事实，补充一句话结论、为什么值得关注、风险说明。"
            "必须严格返回 JSON，且 JSON 字符串值中不要出现未转义的半角双引号。"
        )
        if retry:
            task = (
                "上一次输出不合格。现在只返回一个 JSON 对象，不要代码块，不要解释，不要 Markdown。"
                "字段只能是 one_line、why_it_matters、risk_notes。"
                "one_line 和 why_it_matters 必须为非空字符串，risk_notes 必须为字符串数组。"
            )
        return [
            {"role": "system", "content": system_text},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "event_title": str(event.get("title") or ""),
                        "event_summary": str(event.get("summary") or ""),
                        "event_state": str(event.get("alert_state") or ""),
                        "facts": list(brief_payload.get("facts", []))[:5],
                        "quotes": list(brief_payload.get("quotes", []))[:3],
                        "timeline": list(brief_payload.get("timeline", []))[:5],
                        "risk_notes": list(brief_payload.get("risk_notes", []))[:4],
                        "full_text_sources": full_text_sources,
                        "schema": {
                            "one_line": "string",
                            "why_it_matters": "string",
                            "risk_notes": ["string"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def _validate_enhanced_brief_payload(
        self,
        payload: dict[str, Any],
    ) -> tuple[str, str, list[str]] | None:
        one_line = str(payload.get("one_line") or "").strip()
        why_it_matters = str(payload.get("why_it_matters") or "").strip()
        raw_risk_notes = payload.get("risk_notes", [])
        risk_notes = [str(item).strip() for item in raw_risk_notes if str(item).strip()] if isinstance(raw_risk_notes, list) else []
        if not one_line or not why_it_matters:
            return None
        return one_line, why_it_matters, risk_notes[:5]

    def _generate_deep_dive_timeline(self, event: dict[str, Any], resolved_evidence_pack: list[dict[str, Any]]) -> list[str]:
        timeline: list[str] = []
        if event.get("first_seen_at"):
            timeline.append(f"首次进入系统：{event.get('first_seen_at')}")
        if event.get("last_seen_at"):
            timeline.append(f"最近一次被捕获：{event.get('last_seen_at')}")
        for item in sorted(
            resolved_evidence_pack,
            key=lambda payload: parse_time(payload.get("published_at")) or datetime.max.replace(tzinfo=UTC),
        ):
            title = str(item.get("title") or "").strip()
            published_at = str(item.get("published_at") or "").strip()
            if title and published_at:
                timeline.append(f"{published_at} · {title}")
            if len(timeline) >= 6:
                break
        return timeline[:6]

    def _refresh_browser_session(self, state: dict[str, Any]) -> dict[str, Any]:
        current = state["browser"]["wechat"]
        channel = state["channels"]["wechat"]
        next_state = refresh_browser_session(channel, current)
        state["browser"]["wechat"] = next_state
        return next_state

    def _runtime(self, state: dict[str, Any]) -> dict[str, Any]:
        runtime = state.setdefault("runtime", {})
        self._sync_runtime_counters(runtime)
        return runtime

    def _runtime_run(self, runtime: dict[str, Any]) -> dict[str, Any]:
        return runtime.setdefault(
            "automation_run",
            {
                "run_id": None,
                "status": "idle",
                "stage": "idle",
                "started_at": None,
                "heartbeat_at": None,
                "finished_at": None,
                "triggered_by": None,
                "error": None,
                "recovered_run_id": None,
                "intent": DEFAULT_RUNTIME_INTENT,
                "last_run_outcome": None,
            },
        )

    def _runtime_run_is_stale(self, run: dict[str, Any], now: datetime | None = None) -> bool:
        if str(run.get("status") or "idle") != "running":
            return False
        now = now or datetime.now(UTC)
        heartbeat = parse_time(run.get("heartbeat_at")) or parse_time(run.get("started_at"))
        if not heartbeat:
            return False
        return (now - heartbeat).total_seconds() > RUN_STALE_SECONDS

    def _set_runtime_run_intent(self, runtime: dict[str, Any], intent: str | None) -> dict[str, Any]:
        run = self._runtime_run(runtime)
        run["intent"] = str(intent or run.get("intent") or DEFAULT_RUNTIME_INTENT)
        return run

    def _start_runtime_run(
        self,
        runtime: dict[str, Any],
        *,
        stage: str,
        triggered_by: str,
        intent: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        stamp = now.replace(microsecond=0).isoformat()
        run = self._runtime_run(runtime)
        run.update(
            {
                "run_id": f"run-{uuid4().hex[:12]}",
                "status": "running",
                "stage": stage,
                "started_at": stamp,
                "heartbeat_at": stamp,
                "finished_at": None,
                "triggered_by": triggered_by,
                "error": None,
                "recovered_run_id": None,
                "intent": str(intent or run.get("intent") or DEFAULT_RUNTIME_INTENT),
            }
        )
        return run

    def _heartbeat_runtime_run(
        self,
        runtime: dict[str, Any],
        *,
        stage: str | None = None,
        error: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        stamp = now.replace(microsecond=0).isoformat()
        run = self._runtime_run(runtime)
        if stage:
            run["stage"] = stage
        run["heartbeat_at"] = stamp
        if error is not None:
            run["error"] = error
        return run

    def _finish_runtime_run(
        self,
        runtime: dict[str, Any],
        *,
        status: str,
        stage: str,
        error: str | None = None,
        recovered_run_id: str | None = None,
        last_run_outcome: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        stamp = now.replace(microsecond=0).isoformat()
        run = self._runtime_run(runtime)
        run["status"] = status
        run["stage"] = stage
        run["heartbeat_at"] = stamp
        run["finished_at"] = stamp
        run["error"] = error
        run["recovered_run_id"] = recovered_run_id
        if last_run_outcome is not None:
            run["last_run_outcome"] = last_run_outcome
        return run

    def _recover_stale_runtime_run(self, state: dict[str, Any], actor: str, now: datetime | None = None) -> str | None:
        now = now or datetime.now(UTC)
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        if not self._runtime_run_is_stale(run, now):
            return None
        recovered_run_id = str(run.get("run_id") or "").strip() or None
        self._finish_runtime_run(
            runtime,
            status="abandoned",
            stage="abandoned",
            error=f"超过 {RUN_STALE_SECONDS}s 未更新心跳，已标记为异常轮次。",
            recovered_run_id=recovered_run_id,
            last_run_outcome="abandoned",
            now=now,
        )
        runtime["last_error"] = str(run.get("error") or f"轮次 {recovered_run_id or 'unknown'} 超时未完成，已标记异常。")
        runtime["current_cycle"] = "failed"
        runtime["current_cycle_progress_label"] = runtime["last_error"]
        runtime["scheduler_running"] = False
        runtime["control_state"] = "stopped"
        runtime["current_cycle_started_at"] = None
        runtime["enabled_at"] = None
        runtime["scheduled_start_at"] = None
        runtime["active_interval_minutes"] = None
        runtime["next_collect_at"] = None
        self._progress_snapshot["cycle"] = "failed"
        self._progress_snapshot["label"] = runtime["last_error"]
        self._append_log(
            state,
            "warning",
            "runtime",
            f"检测到异常轮次并已接管：{recovered_run_id or 'unknown'}",
            stream="system_runtime",
            actor=actor,
            detail=f"{runtime['last_error']}\n已自动停止监测，请人工确认后再重新启动。",
        )
        return recovered_run_id

    def _calculate_next_collect_at(self, state: dict[str, Any], now: datetime | None = None, minimum_interval_minutes: int | None = None) -> str | None:
        runtime = self._runtime(state)
        if runtime.get("control_state", "stopped") == "stopped":
            return None
        if runtime.get("control_state", "stopped") != "stopped":
            return self._calculate_runtime_next_collect_at(state, now)
        now = now or datetime.now(UTC)
        due_times: list[datetime] = []
        for source in state["sources"]:
            if not source.get("enabled"):
                continue
            interval = schedule_to_minutes(source.get("schedule"))
            if minimum_interval_minutes:
                interval = max(interval or 0, minimum_interval_minutes)
            if not interval:
                continue
            last_synced = parse_time(source.get("last_synced_at"))
            if not last_synced:
                due_times.append(now)
            else:
                due_times.append(last_synced + timedelta(minutes=interval))
        if not due_times:
            return None
        return min(due_times).replace(microsecond=0).isoformat()

    def _last_cycle_issue_snapshot(self, state: dict[str, Any], runtime: dict[str, Any]) -> tuple[int, str | None]:
        summary = runtime.get("last_cycle_summary")
        if isinstance(summary, dict):
            issues = summary.get("issues", [])
            if isinstance(issues, list):
                count = len(issues)
                if count == 0:
                    return 0, "本轮无异常"
                preview = "；".join(
                    str(item.get("message") or "").strip()
                    for item in issues[:2]
                    if isinstance(item, dict) and str(item.get("message") or "").strip()
                )
                if preview:
                    return count, f"本轮 {count} 条异常。{preview}"
                return count, f"本轮 {count} 条异常。"
        started_at = parse_time(runtime.get("last_cycle_started_at"))
        finished_at = parse_time(runtime.get("last_cycle_finished_at"))
        if not started_at or not finished_at or finished_at < started_at:
            return 0, None

        issues: list[dict[str, Any]] = []
        for item in state.get("logs", []):
            level = str(item.get("level") or "")
            if level not in {"warning", "error"}:
                continue
            created_at = parse_time(item.get("created_at"))
            if not created_at or created_at < started_at or created_at > finished_at:
                continue
            issues.append(item)

        count = len(issues)
        if count == 0:
            return 0, "本轮无异常"

        messages = [str(item.get("message") or "").strip() for item in issues if str(item.get("message") or "").strip()]
        unique_messages: list[str] = []
        for message in messages:
            if message not in unique_messages:
                unique_messages.append(message)

        if count == 1 and unique_messages:
            return 1, unique_messages[0]

        collection_count = len([item for item in issues if str(item.get("category") or "") == "collection"])
        runtime_count = len([item for item in issues if str(item.get("category") or "") == "runtime"])
        preview = "；".join(unique_messages[:2]) if unique_messages else "详情见日志"

        if collection_count == count:
            return count, f"本轮 {count} 条来源异常。{preview}"
        if runtime_count == count:
            return count, f"本轮 {count} 条运行异常。{preview}"
        return count, f"本轮 {count} 条异常。{preview}"

    def _reset_runtime_cycle_context(self, runtime: dict[str, Any]) -> None:
        runtime["current_cycle_sources"] = []
        runtime["current_cycle_metrics"] = {
            "selected_event_count": 0,
            "deep_dive_count": 0,
            "brief_count": 0,
            "wechat_sync_count": 0,
            "wechat_verify_count": 0,
            "publish_count": 0,
            "selected_titles": [],
            "brief_titles": [],
            "synced_titles": [],
        }
        runtime["blocked_reason"] = None

    def _record_runtime_source_attempt(
        self,
        runtime: dict[str, Any],
        *,
        source: dict[str, Any],
        duration_ms: int,
        status: str,
        item_count: int,
        warning_text: str | None = None,
        error_text: str | None = None,
    ) -> None:
        attempts = runtime.setdefault("current_cycle_sources", [])
        attempts.append(
            {
                "source_key": str(source.get("key") or ""),
                "source_name": str(source.get("name") or source.get("key") or "unknown"),
                "duration_ms": max(int(duration_ms), 0),
                "status": status,
                "item_count": max(int(item_count), 0),
                "warning_text": warning_text,
                "error_text": error_text,
            }
        )

    def _set_runtime_cycle_metric(self, runtime: dict[str, Any], key: str, value: int) -> None:
        metrics = runtime.setdefault("current_cycle_metrics", {})
        metrics[key] = max(int(value), 0)

    def _build_last_cycle_summary(self, state: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any] | None:
        started_at = runtime.get("last_cycle_started_at")
        finished_at = runtime.get("last_cycle_finished_at")
        if not started_at or not finished_at:
            return None
        attempts = [
            item for item in runtime.get("current_cycle_sources", [])
            if isinstance(item, dict)
        ]
        success_source_count = len([item for item in attempts if str(item.get("status") or "") == "success"])
        failed_source_count = len([item for item in attempts if str(item.get("status") or "") != "success"])
        slow_sources = sorted(
            attempts,
            key=lambda item: int(item.get("duration_ms", 0) or 0),
            reverse=True,
        )[:3]
        issues: list[dict[str, Any]] = []
        for item in attempts:
            status = str(item.get("status") or "success")
            if status == "success":
                continue
            issues.append(
                {
                    "source_key": item.get("source_key"),
                    "source_name": item.get("source_name"),
                    "error_kind": "warning" if status == "warning" else "collection",
                    "message": str(item.get("warning_text") or item.get("error_text") or "来源执行异常").strip(),
                }
            )
        run = self._runtime_run(runtime)
        run_error = str(run.get("error") or runtime.get("last_error") or "").strip()
        if run_error and not any(issue.get("message") == run_error for issue in issues):
            issues.append(
                {
                    "source_key": None,
                    "source_name": None,
                    "error_kind": "runtime",
                    "message": run_error,
                }
            )
        event_state_counts = Counter(str(item.get("change_state") or "new_event") for item in state.get("intel_events", []))
        item_state_counts = Counter(str(item.get("item_state") or "new_item") for item in state.get("discovery_items", []))
        metrics = runtime.get("current_cycle_metrics", {})
        duration_seconds = float(runtime.get("last_cycle_duration_seconds", 0) or 0)
        summary = RuntimeCycleSummary(
            run_id=run.get("run_id"),
            mode_key=str(runtime.get("current_mode") or state.get("automation_mode") or "radar_only"),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=max(int(round(duration_seconds * 1000)), 0),
            success_source_count=success_source_count,
            failed_source_count=failed_source_count,
            new_items_count=int(item_state_counts.get("new_item", 0)),
            new_events_count=int(event_state_counts.get("new_event", 0)),
            growing_events_count=int(event_state_counts.get("growing_event", 0)),
            slow_sources=[
                RuntimeSlowSource(
                    source_key=str(item.get("source_key") or ""),
                    source_name=str(item.get("source_name") or "unknown"),
                    duration_ms=max(int(item.get("duration_ms", 0) or 0), 0),
                    status=str(item.get("status") or "success"),
                )
                for item in slow_sources
            ],
            issues=[
                RuntimeIssueItem(
                    source_key=item.get("source_key"),
                    source_name=item.get("source_name"),
                    error_kind=str(item.get("error_kind") or "runtime"),
                    message=str(item.get("message") or "").strip(),
                )
                for item in issues
                if str(item.get("message") or "").strip()
            ],
            selected_event_count=int(metrics.get("selected_event_count", 0) or 0),
            deep_dive_count=int(metrics.get("deep_dive_count", 0) or 0),
            brief_count=int(metrics.get("brief_count", 0) or 0),
            wechat_sync_count=int(metrics.get("wechat_sync_count", 0) or 0),
            wechat_verify_count=int(metrics.get("wechat_verify_count", 0) or 0),
            publish_count=int(metrics.get("publish_count", 0) or 0),
            blocked_reason=str(runtime.get("blocked_reason") or "").strip() or None,
            recent_selected_titles=[str(item).strip() for item in metrics.get("selected_titles", []) if str(item).strip()][:5],
            recent_brief_titles=[str(item).strip() for item in metrics.get("brief_titles", []) if str(item).strip()][:5],
            recent_synced_titles=[str(item).strip() for item in metrics.get("synced_titles", []) if str(item).strip()][:5],
        )
        return summary.model_dump()

    def _prune_intel_event_history(
        self,
        items: list[dict[str, Any]] | None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now or datetime.now(UTC)
        kept: list[dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            expires_at = parse_time(item.get("expires_at"))
            if not expires_at or expires_at <= now:
                continue
            kept.append(item)
        kept.sort(
            key=lambda item: parse_time(item.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return kept

    def _prune_intel_alert_history(
        self,
        items: list[dict[str, Any]] | None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now or datetime.now(UTC)
        kept: list[dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            expires_at = parse_time(item.get("expires_at"))
            if not expires_at or expires_at <= now:
                continue
            kept.append(item)
        kept.sort(
            key=lambda item: parse_time(item.get("last_triggered_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return kept

    def _has_recent_source_uncertainty(self, state: dict[str, Any]) -> bool:
        runtime = self._runtime(state)
        current_attempts = runtime.get("current_cycle_sources", [])
        if any(str(item.get("status") or "success") != "success" for item in current_attempts if isinstance(item, dict)):
            return True
        summary = runtime.get("last_cycle_summary")
        if isinstance(summary, dict):
            if int(summary.get("failed_source_count", 0) or 0) > 0:
                return True
            if summary.get("issues"):
                return True
        return False

    def _event_history_status(self, event: dict[str, Any] | None, *, source_uncertain: bool) -> str:
        if event:
            if str(event.get("alert_state") or "new") == "cooling":
                return "cooled"
            return "active"
        return "source_uncertain" if source_uncertain else "cooled"

    def _alert_history_status(self, alert: dict[str, Any] | None, *, source_uncertain: bool) -> str:
        if alert:
            return "active"
        return "source_uncertain" if source_uncertain else "cooled"

    def _history_alert_level_rank(self, level: str) -> int:
        return {
            "cooling": 0,
            "watch": 1,
            "rising": 2,
            "breakout": 3,
        }.get(str(level or "watch"), 1)

    def _build_event_history_id(self, event_id: str, discovered_at: str) -> str:
        seed = f"{event_id}|{discovered_at}|event"
        return f"evh-{uuid4().hex[:8]}-{abs(hash(seed)) % 10000:04d}"

    def _build_alert_history_id(self, event_id: str, first_triggered_at: str) -> str:
        seed = f"{event_id}|{first_triggered_at}|alert"
        return f"alh-{uuid4().hex[:8]}-{abs(hash(seed)) % 10000:04d}"

    def _refresh_intel_histories(
        self,
        state: dict[str, Any],
        now: datetime | None = None,
        *,
        update_event_history: bool = True,
        update_alert_history: bool = True,
    ) -> None:
        now = now or datetime.now(UTC)
        now_stamp = now.replace(microsecond=0).isoformat()
        expires_at = (now + timedelta(hours=24)).replace(microsecond=0).isoformat()
        source_uncertain = self._has_recent_source_uncertainty(state)

        current_events = {
            str(item.get("id") or ""): item
            for item in state.get("intel_events", [])
            if isinstance(item, dict) and item.get("id")
        }
        current_alerts = {
            str(item.get("event_id") or ""): item
            for item in state.get("intel_alerts", [])
            if isinstance(item, dict) and item.get("event_id")
        }

        event_history = self._prune_intel_event_history(state.get("intel_event_history", []), now=now)
        if update_event_history:
            event_history_by_event = {
                str(item.get("event_id") or ""): item
                for item in event_history
                if item.get("event_id")
            }
            for event_id, event in current_events.items():
                existing = event_history_by_event.get(event_id)
                status = self._event_history_status(event, source_uncertain=source_uncertain)
                if existing:
                    existing.update(
                        {
                            "title": str(event.get("title") or existing.get("title") or ""),
                            "summary": str(event.get("summary") or existing.get("summary") or ""),
                            "representative_link": str(event.get("representative_link") or existing.get("representative_link") or ""),
                            "entity_ids": list(event.get("entity_ids", existing.get("entity_ids", []))),
                            "entity_names": list(event.get("entity_names", existing.get("entity_names", []))),
                            "last_seen_at": event.get("last_seen_at") or event.get("latest_collected_at") or now_stamp,
                            "status": status,
                            "latest_alert_state": str(event.get("alert_state") or existing.get("latest_alert_state") or "new"),
                            "platform_count": int(event.get("platform_count", 0) or 0),
                            "source_count": int(event.get("source_count", 0) or 0),
                            "member_count": int(event.get("member_count", 0) or 0),
                            "member_delta": int(event.get("member_delta", 0) or 0),
                            "platform_delta": int(event.get("platform_delta", 0) or 0),
                            "composite_score": float(event.get("composite_score", 0) or 0),
                        }
                    )
                    continue
                event_history.append(
                    {
                        "history_id": self._build_event_history_id(event_id, now_stamp),
                        "event_id": event_id,
                        "title": str(event.get("title") or ""),
                        "summary": str(event.get("summary") or ""),
                        "representative_link": str(event.get("representative_link") or ""),
                        "entity_ids": list(event.get("entity_ids", [])),
                        "entity_names": list(event.get("entity_names", [])),
                        "discovered_at": now_stamp,
                        "last_seen_at": event.get("last_seen_at") or event.get("latest_collected_at") or now_stamp,
                        "expires_at": expires_at,
                        "status": status,
                        "latest_alert_state": str(event.get("alert_state") or "new"),
                        "platform_count": int(event.get("platform_count", 0) or 0),
                        "source_count": int(event.get("source_count", 0) or 0),
                        "member_count": int(event.get("member_count", 0) or 0),
                        "member_delta": int(event.get("member_delta", 0) or 0),
                        "platform_delta": int(event.get("platform_delta", 0) or 0),
                        "composite_score": float(event.get("composite_score", 0) or 0),
                    }
                )

            for item in event_history:
                event_id = str(item.get("event_id") or "")
                if event_id in current_events:
                    continue
                item["status"] = self._event_history_status(None, source_uncertain=source_uncertain)

        alert_history = self._prune_intel_alert_history(state.get("intel_alert_history", []), now=now)
        if update_alert_history:
            alert_history_by_event = {
                str(item.get("event_id") or ""): item
                for item in alert_history
                if item.get("event_id")
            }
            for event_id, alert in current_alerts.items():
                if str(alert.get("level") or "") not in {"rising", "breakout"}:
                    continue
                existing = alert_history_by_event.get(event_id)
                status = self._alert_history_status(alert, source_uncertain=source_uncertain)
                highest_level = str(alert.get("level") or "watch")
                if existing:
                    previous_highest = str(existing.get("highest_level") or highest_level)
                    if self._history_alert_level_rank(previous_highest) > self._history_alert_level_rank(highest_level):
                        highest_level = previous_highest
                    existing.update(
                        {
                            "title": str(alert.get("title") or existing.get("title") or ""),
                            "representative_link": str(alert.get("representative_link") or existing.get("representative_link") or ""),
                            "entity_ids": list(alert.get("entity_ids", existing.get("entity_ids", []))),
                            "entity_names": list(alert.get("entity_names", existing.get("entity_names", []))),
                            "last_triggered_at": alert.get("triggered_at") or now_stamp,
                            "highest_level": highest_level,
                            "latest_level": str(alert.get("level") or existing.get("latest_level") or "watch"),
                            "status": status,
                            "reason": str(alert.get("reason") or existing.get("reason") or ""),
                            "platform_count": int(alert.get("platform_count", 0) or 0),
                            "source_count": int(alert.get("source_count", 0) or 0),
                            "velocity_score": float(alert.get("velocity_score", 0) or 0),
                            "coverage_score": float(alert.get("coverage_score", 0) or 0),
                            "freshness_score": float(alert.get("freshness_score", 0) or 0),
                            "composite_score": float(alert.get("composite_score", 0) or 0),
                        }
                    )
                    continue
                alert_history.append(
                    {
                        "history_id": self._build_alert_history_id(event_id, now_stamp),
                        "event_id": event_id,
                        "title": str(alert.get("title") or ""),
                        "representative_link": str(alert.get("representative_link") or ""),
                        "entity_ids": list(alert.get("entity_ids", [])),
                        "entity_names": list(alert.get("entity_names", [])),
                        "first_triggered_at": alert.get("triggered_at") or now_stamp,
                        "last_triggered_at": alert.get("triggered_at") or now_stamp,
                        "expires_at": expires_at,
                        "highest_level": str(alert.get("level") or "watch"),
                        "latest_level": str(alert.get("level") or "watch"),
                        "status": status,
                        "reason": str(alert.get("reason") or ""),
                        "platform_count": int(alert.get("platform_count", 0) or 0),
                        "source_count": int(alert.get("source_count", 0) or 0),
                        "velocity_score": float(alert.get("velocity_score", 0) or 0),
                        "coverage_score": float(alert.get("coverage_score", 0) or 0),
                        "freshness_score": float(alert.get("freshness_score", 0) or 0),
                        "composite_score": float(alert.get("composite_score", 0) or 0),
                    }
                )

            for item in alert_history:
                event_id = str(item.get("event_id") or "")
                if event_id in current_alerts:
                    continue
                item["status"] = self._alert_history_status(None, source_uncertain=source_uncertain)

        state["intel_event_history"] = self._prune_intel_event_history(event_history, now=now)
        state["intel_alert_history"] = self._prune_intel_alert_history(alert_history, now=now)

    def _project_cycle_summary_text(self, summary: dict[str, Any] | None) -> str | None:
        if not isinstance(summary, dict):
            return None
        issues = [item for item in summary.get("issues", []) if isinstance(item, dict)]
        if not issues:
            return "本轮无异常"
        preview = "；".join(
            str(item.get("message") or "").strip()
            for item in issues[:2]
            if str(item.get("message") or "").strip()
        )
        if preview:
            return f"本轮 {len(issues)} 条异常。{preview}"
        return f"本轮 {len(issues)} 条异常。"

    def _stage_plan(self, runtime: dict[str, Any]) -> list[dict[str, str]]:
        intent = str(self._runtime_run(runtime).get("intent") or DEFAULT_RUNTIME_INTENT)
        if intent != "normal_monitoring":
            return deepcopy(INTENT_STAGE_PLANS.get(intent, [{"key": "collecting", "label": "执行维护任务"}]))
        mode_key = str(runtime.get("current_mode") or "radar_only")
        return deepcopy(MODE_STAGE_PLANS.get(mode_key, MODE_STAGE_PLANS["radar_only"]))

    def _stage_display_key(self, runtime: dict[str, Any], cycle: str) -> str:
        mode_key = str(runtime.get("current_mode") or "radar_only")
        intent = str(self._runtime_run(runtime).get("intent") or DEFAULT_RUNTIME_INTENT)
        if cycle in {"starting", "idle"}:
            plan = self._stage_plan(runtime)
            return plan[0]["key"] if plan else "idle"
        if cycle == "wechat_sync" and intent == "normal_monitoring" and mode_key == "radar_and_draft":
            return "drafting"
        if cycle.startswith("collecting"):
            return "collecting"
        if cycle.startswith("clustering"):
            return "clustering"
        if cycle.startswith("scoring"):
            return "scoring"
        return cycle

    def _stage_status(self, runtime: dict[str, Any], cycle: str | None = None) -> tuple[str, str, int, int]:
        plan = self._stage_plan(runtime)
        total = len(plan)
        if not plan:
            return "idle", "空闲", 0, 0
        cycle_key = self._stage_display_key(runtime, str(cycle or runtime.get("current_cycle") or "idle"))
        if str(self._runtime_run(runtime).get("status") or "idle") == "completed":
            last = plan[-1]
            return last["key"], last["label"], total, total
        for index, item in enumerate(plan, start=1):
            if item["key"] == cycle_key:
                return item["key"], item["label"], index, total
        first = plan[0]
        return first["key"], first["label"], 1, total

    def _stage_progress_percent(self, runtime: dict[str, Any], stage_key: str, stage_progress: float) -> int:
        plan = self._stage_plan(runtime)
        if not plan:
            return max(0, min(int(round(stage_progress)), 100))
        total = max(len(plan), 1)
        stage_index = next((index for index, item in enumerate(plan, start=1) if item["key"] == stage_key), 1)
        bounded = max(0.0, min(float(stage_progress), 100.0))
        span_start = 4.0 + ((stage_index - 1) / total) * 96.0
        span_end = 4.0 + (stage_index / total) * 96.0
        percent = span_start + (span_end - span_start) * (bounded / 100.0)
        if stage_index == total and bounded >= 100.0:
            return 100
        return max(0, min(int(round(percent)), 99))

    def _normalize_runtime_status_progress(
        self,
        runtime: dict[str, Any],
        *,
        cycle: str,
        percent: int,
        done: int,
        total: int,
        label: str | None,
    ) -> tuple[str, int, int, int, str | None]:
        run = self._runtime_run(runtime)
        run_status = str(run.get("status") or "idle")
        run_stage = str(run.get("stage") or "")
        if run_status != "running":
            return cycle, percent, done, total, label

        derived_cycle = self._stage_display_key(runtime, run_stage or cycle)
        if cycle in {"", "idle", "starting"} and derived_cycle not in {"", "idle"}:
            cycle = derived_cycle

        if label:
            collected_match = re.search(r"已采集\s*(\d+)\s*/\s*(\d+)\s*个来源", label)
            if collected_match:
                done = max(done, int(collected_match.group(1)))
                total = max(total, int(collected_match.group(2)))
                if percent <= 0:
                    percent = self._stage_progress_percent(
                        runtime,
                        "collecting",
                        done / max(total, 1) * 100,
                    )
            elif percent <= 0:
                pending_match = re.search(r"正在并发采集\s*(\d+)\s*个来源", label)
                if pending_match:
                    total = max(total, int(pending_match.group(1)))
                    percent = self._stage_progress_percent(runtime, "collecting", 5)

        if percent <= 0:
            stage_baselines = {
                "collecting": 5,
                "clustering": self._stage_progress_percent(runtime, "clustering", 10),
                "scoring": self._stage_progress_percent(runtime, "scoring", 10),
                "drafting": self._stage_progress_percent(runtime, "drafting", 10),
                "wechat_sync": self._stage_progress_percent(runtime, "wechat_sync", 10),
            }
            percent = stage_baselines.get(cycle, percent)

        return cycle, percent, done, total, label

    def _featured_event_engagement_threshold(self, events: list[dict[str, Any]]) -> float:
        scores = sorted(
            float(item.get("representative_engagement_score", 0) or 0)
            for item in events
            if float(item.get("representative_engagement_score", 0) or 0) > 0
        )
        if not scores:
            return 0.0
        percentile_index = max(int(len(scores) * 0.75) - 1, 0)
        return scores[percentile_index]

    def _is_featured_event(self, event: dict[str, Any], engagement_threshold: float) -> bool:
        if int(event.get("platform_count", 0) or 0) >= 2:
            return True
        if int(event.get("source_count", 0) or 0) >= 2:
            return True
        if int(event.get("member_count", 0) or 0) >= 3:
            return True
        engagement_score = float(event.get("representative_engagement_score", 0) or 0)
        return engagement_threshold > 0 and engagement_score >= engagement_threshold

    def _work_scope(self, state: dict[str, Any]) -> str:
        return str(self._runtime_plan(state).get("work_scope") or "collect_events_alerts")

    def _set_runtime_progress(
        self,
        runtime: dict[str, Any],
        *,
        percent: int,
        done: int = 0,
        total: int = 0,
        label: str | None = None,
    ) -> None:
        runtime["current_cycle_progress_percent"] = max(0, min(int(percent), 100))
        runtime["current_cycle_progress_done"] = max(int(done), 0)
        runtime["current_cycle_progress_total"] = max(int(total), 0)
        runtime["current_cycle_progress_label"] = label
        snapshot = self._progress_snapshot
        snapshot["percent"] = runtime["current_cycle_progress_percent"]
        snapshot["done"] = runtime["current_cycle_progress_done"]
        snapshot["total"] = runtime["current_cycle_progress_total"]
        snapshot["label"] = label

    def _reset_runtime_progress(self, runtime: dict[str, Any]) -> None:
        self._set_runtime_progress(runtime, percent=0, done=0, total=0, label=None)
        self._progress_snapshot["cycle"] = "idle"

    def _write_runtime_checkpoint(self, state: dict[str, Any], timeout_seconds: float = 0.5) -> bool:
        acquired = self._lock.acquire(timeout=timeout_seconds)
        if not acquired:
            return False
        try:
            self._write(state)
            return True
        finally:
            self._lock.release()

    def _record_source_attempt(
        self,
        source: dict[str, Any],
        *,
        started_at: datetime,
        completed_at: datetime,
        items: list[dict[str, Any]],
        warning_text: str | None = None,
    ) -> None:
        duration_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
        attempt_stamp = started_at.replace(microsecond=0).isoformat()
        completed_stamp = completed_at.replace(microsecond=0).isoformat()
        count = len(items)
        source["item_count"] = count
        source["last_item_count"] = count
        source["last_attempt_at"] = attempt_stamp
        source["last_duration_ms"] = duration_ms
        previous_avg = source.get("avg_duration_ms")
        if isinstance(previous_avg, int):
            source["avg_duration_ms"] = max(int(round((previous_avg * 0.7) + (duration_ms * 0.3))), 0)
        else:
            source["avg_duration_ms"] = duration_ms
        if warning_text:
            source["last_failure_at"] = completed_stamp
            source["consecutive_failures"] = int(source.get("consecutive_failures", 0) or 0) + 1
            if count:
                source["health_status"] = "warning"
            else:
                source["health_status"] = "error" if int(source.get("consecutive_failures", 0) or 0) >= 2 else "warning"
            source["health_detail"] = warning_text
            source["last_error"] = warning_text
        else:
            source["last_success_at"] = completed_stamp
            source["last_synced_at"] = completed_stamp
            source["consecutive_failures"] = 0
            source["last_error"] = None
            if duration_ms >= SLOW_SOURCE_WARNING_SECONDS * 1000:
                source["health_status"] = "warning"
                source["health_detail"] = f"最近一次成功但耗时较长（{round(duration_ms / 1000, 1)}s），产生 {count} 条素材。"
            else:
                source["health_status"] = "healthy"
                source["health_detail"] = f"最近一次同步产生 {count} 条素材。"

    def _finalize_source_health(self, source: dict[str, Any], now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        if not source.get("enabled"):
            source["health_status"] = "idle"
            source["health_detail"] = "已停用"
            return
        consecutive_failures = int(source.get("consecutive_failures", 0) or 0)
        last_success = parse_time(source.get("last_success_at"))
        last_duration_ms = int(source.get("last_duration_ms", 0) or 0)
        if consecutive_failures >= 2:
            source["health_status"] = "error"
            if not source.get("health_detail"):
                source["health_detail"] = "连续失败 2 次以上。"
            return
        if last_success:
            success_age_hours = max((now - last_success).total_seconds() / 3600, 0.0)
            if success_age_hours > 24:
                source["health_status"] = "error"
                source["health_detail"] = source.get("health_detail") or "最近 24 小时无成功同步。"
                return
            if success_age_hours > 6 or consecutive_failures == 1 or last_duration_ms >= SLOW_SOURCE_WARNING_SECONDS * 1000:
                source["health_status"] = "warning"
                if not source.get("health_detail"):
                    source["health_detail"] = "最近同步偏慢或存在轻微异常。"
                return
            source["health_status"] = "healthy"
            if not source.get("health_detail"):
                source["health_detail"] = f"最近一次同步产生 {int(source.get('last_item_count', 0) or 0)} 条素材。"
            return
        if source.get("last_failure_at"):
            source["health_status"] = "error" if consecutive_failures >= 2 else "warning"
            source["health_detail"] = source.get("health_detail") or "尚未出现成功同步。"

    def _project_normalized_items_from_events(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for event in state.get("intel_events", []):
            normalized.append(
                {
                    "id": f"norm-{event['id']}",
                    "raw_item_ids": list(event.get("discovery_item_ids", [])),
                    "title": event.get("title", ""),
                    "link": event.get("representative_link", ""),
                    "summary": event.get("summary", ""),
                    "published_at": event.get("published_at"),
                    "cluster_id": event.get("id"),
                    "cluster_members": list(event.get("discovery_item_ids", [])),
                    "dedupe_key": str(event.get("id")),
                    "source_names": list(event.get("source_names", [])),
                    "origin_sources": list(event.get("source_keys", [])),
                    "source_weight": round(min(float(event.get("coverage_score", 0) or 0) / 100.0, 1.0), 2),
                    "trend_score": float(event.get("velocity_score", 0) or 0),
                    "final_score": float(event.get("composite_score", 0) or 0),
                    "signals": [str(event.get("alert_reason") or "多平台聚合事件")],
                    "score_breakdown": {
                        "velocity": float(event.get("velocity_score", 0) or 0),
                        "coverage": float(event.get("coverage_score", 0) or 0),
                        "freshness": float(event.get("freshness_score", 0) or 0),
                    },
                    "collected_at": event.get("latest_collected_at"),
                    "freshness_bucket": freshness_bucket(event.get("latest_collected_at")),
                }
            )
        normalized.sort(key=lambda item: item.get("final_score", 0), reverse=True)
        return normalized

    def _rebuild_intel_for_state(
        self,
        state: dict[str, Any],
        stamp: str | None = None,
        work_scope_override: str | None = None,
    ) -> None:
        work_scope = str(work_scope_override or self._work_scope(state))
        intel = build_intel_state(
            state.get("raw_items", []),
            self._sources_by_key(state),
            previous_discovery_items=state.get("discovery_items", []),
            previous_events=state.get("intel_events", []),
            previous_snapshots=state.get("event_snapshots", []),
            captured_at=stamp or now_iso(),
        )
        state["discovery_items"] = intel["discovery_items"]
        if work_scope == "collect_only":
            self._refresh_intel_histories(state, update_event_history=False, update_alert_history=False)
            state["intel_events"] = []
            state["intel_alerts"] = []
            state["event_snapshots"] = []
            state["normalized_items"] = []
            return
        state["event_snapshots"] = intel["event_snapshots"]
        state["intel_events"] = intel["intel_events"]
        if work_scope == "collect_events":
            state["intel_alerts"] = []
            self._refresh_intel_histories(state, update_event_history=True, update_alert_history=False)
        elif work_scope == "collect_events_alerts":
            state["intel_alerts"] = intel["intel_alerts"]
            self._refresh_intel_histories(state, update_event_history=True, update_alert_history=True)
        else:
            state["intel_alerts"] = []
            self._refresh_intel_histories(state, update_event_history=False, update_alert_history=False)
        state["normalized_items"] = self._project_normalized_items_from_events(state)
        runtime = self._runtime(state)
        runtime["last_event_sync_at"] = now_iso()

    def _rebuild_candidates_for_state(
        self,
        state: dict[str, Any],
        work_scope_override: str | None = None,
    ) -> list[dict[str, Any]]:
        # Compatibility shim for old call sites that still expect a rebuilt
        # candidate list after the system was unified onto intel events.
        self._rebuild_intel_for_state(state, work_scope_override=work_scope_override)
        return list(state.get("normalized_items", []))

    def _sync_due_sources(self, state: dict[str, Any], triggered_by: str, minimum_interval_minutes: int | None = None) -> SourceSyncResponse:
        now = datetime.now(UTC)
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        stage_plan = self._stage_plan(runtime)
        stage_positions = {item["key"]: index + 1 for index, item in enumerate(stage_plan)}
        stage_total = len(stage_plan)
        collect_stage_no = stage_positions.get("collecting", 1)
        cluster_stage_no = stage_positions.get("clustering", min(collect_stage_no + 1, max(stage_total, 1)))
        scoring_stage_no = stage_positions.get("scoring", min(cluster_stage_no + 1, max(stage_total, 1)))
        due_sources: list[dict[str, Any]] = []
        for source in state["sources"]:
            if not source.get("enabled"):
                continue
            interval = schedule_to_minutes(source.get("schedule"))
            if minimum_interval_minutes:
                interval = max(interval or 0, minimum_interval_minutes)
            last_synced = parse_time(source.get("last_synced_at"))
            if not last_synced or not interval or (now - last_synced).total_seconds() >= interval * 60:
                due_sources.append(source)
        if not due_sources:
            self._set_runtime_progress(runtime, percent=100, done=0, total=0, label="本轮没有到期来源")
            runtime["next_collect_at"] = self._calculate_next_collect_at(state, now, minimum_interval_minutes)
            return SourceSyncResponse(
                raw_count=len(state["raw_items"]),
                normalized_count=len(state["normalized_items"]),
                event_count=len(state.get("intel_events", [])),
                synced_at=now_iso(),
                warnings=[],
            )

        existing = [item for item in state["raw_items"] if item["source_key"] not in {source["key"] for source in due_sources}]
        collected: list[dict[str, Any]] = []
        warnings: list[str] = []
        stamp = now_iso()
        total_sources = len(due_sources)
        max_workers = max(1, min(int(state.get("settings", {}).get("max_workers", 8)), 20))
        self._set_runtime_progress(
            runtime,
            percent=self._stage_progress_percent(runtime, "collecting", 5),
            done=0,
            total=total_sources,
            label=f"正在并发采集 {total_sources} 个来源 ({max_workers} 线程)",
        )
        self._heartbeat_runtime_run(runtime, stage="collecting", now=now)
        self._write_runtime_checkpoint(state)

        def _collect_one(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str | None, str | None, datetime, datetime]:
            started_at = datetime.now(UTC)
            try:
                items, warning = _collect_with_retry(source)
                return source, items, warning, None, started_at, datetime.now(UTC)
            except Exception as exc:
                tb = traceback.format_exc()
                return source, [], None, f"{source['name']}: 抓取器异常:\n{tb}", started_at, datetime.now(UTC)

        source_map: dict[str, dict[str, Any]] = {src["key"]: src for src in due_sources}
        completed = 0
        last_progress_at = now
        next_wait_heartbeat_at = time.monotonic() + 5

        def _finalize_source_result(
            source: dict[str, Any],
            *,
            items: list[dict[str, Any]],
            warning: str | None,
            error: str | None,
            started_at: datetime,
            completed_at: datetime,
        ) -> None:
            nonlocal completed
            collected.extend(items)
            if warning:
                warnings.append(f"{source['name']}: {warning}")
            if error:
                warnings.append(error)
                self._append_log(state, "error", "collection", error, stream="system_runtime", actor=triggered_by)
            warning_text = warning or (error.split("\n")[0][:200] if error else None)
            self._record_source_attempt(
                source,
                started_at=started_at,
                completed_at=completed_at,
                items=items,
                warning_text=warning_text,
            )
            duration_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
            self._record_runtime_source_attempt(
                runtime,
                source=source,
                duration_ms=duration_ms,
                status="success" if not warning_text else ("warning" if items else "error"),
                item_count=len(items),
                warning_text=warning_text,
                error_text=error.split("\n")[0][:200] if error else None,
            )
            self._finalize_source_health(source, now=completed_at)
            completed += 1
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "collecting", completed / max(total_sources, 1) * 100),
                done=completed,
                total=total_sources,
                label=f"已采集 {completed}/{total_sources} 个来源",
            )
            self._heartbeat_runtime_run(runtime, stage=f"collecting:{source['key']}", error=warning_text, now=completed_at)
            self._write_runtime_checkpoint(state)

        executor = ThreadPoolExecutor(max_workers=max_workers)
        pending: dict[Any, dict[str, Any]] = {}
        try:
            for src in due_sources:
                future = executor.submit(_collect_one, src)
                pending[future] = {
                    "source_key": src["key"],
                    "submitted_at": datetime.now(UTC),
                }

            while pending:
                done, _ = wait(tuple(pending.keys()), timeout=1, return_when=FIRST_COMPLETED)
                current_time = datetime.now(UTC)
                if done:
                    for future in done:
                        meta = pending.pop(future, None)
                        if not meta:
                            continue
                        src_key = str(meta["source_key"])
                        source = source_map[src_key]
                        try:
                            _src_collected, items, warning, error, started_at, completed_at = future.result()
                        except Exception:
                            items, warning, error = [], None, f"{source['name']}: 未知异常"
                            started_at = current_time
                            completed_at = current_time
                        _finalize_source_result(
                            source,
                            items=items,
                            warning=warning,
                            error=error,
                            started_at=started_at,
                            completed_at=completed_at,
                        )
                    last_progress_at = current_time
                    continue

                if time.monotonic() >= next_wait_heartbeat_at:
                    pending_count = len(pending)
                    self._set_runtime_progress(
                        runtime,
                        percent=self._stage_progress_percent(runtime, "collecting", completed / max(total_sources, 1) * 100),
                        done=completed,
                        total=total_sources,
                        label=f"正在等待剩余 {pending_count} 个来源返回",
                    )
                    self._heartbeat_runtime_run(runtime, stage="collecting:waiting", now=current_time)
                    self._write_runtime_checkpoint(state)
                    next_wait_heartbeat_at = time.monotonic() + 5

                stalled_for = (current_time - last_progress_at).total_seconds()
                if stalled_for < SOURCE_COLLECTION_STALL_SECONDS:
                    continue

                stalled_sources = []
                for future, meta in list(pending.items()):
                    src_key = str(meta["source_key"])
                    source = source_map[src_key]
                    pending.pop(future, None)
                    future.cancel()
                    stalled_sources.append(source["name"])
                    timeout_message = (
                        f"{source['name']}: 采集超时，已跳过该来源并继续本轮（连续 {int(stalled_for)}s 无进展）"
                    )
                    _finalize_source_result(
                        source,
                        items=[],
                        warning=None,
                        error=timeout_message,
                        started_at=meta.get("submitted_at") or current_time,
                        completed_at=current_time,
                    )
                if stalled_sources:
                    self._append_log(
                        state,
                        "warning",
                        "runtime",
                        f"采集阶段长时间无进展，已跳过 {len(stalled_sources)} 个来源：{', '.join(stalled_sources)}",
                        stream="system_runtime",
                        actor=triggered_by,
                    )
                last_progress_at = current_time
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        merged = sorted(existing + collected, key=lambda item: parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        state["raw_items"] = merged[:MAX_RAW_ITEMS]
        active_work_scope = str(runtime.get("work_scope") or self._work_scope(state) or "collect_events_alerts")
        self._append_log(
            state,
            "info",
            "runtime",
            f"阶段 {collect_stage_no}/{stage_total} 完成：采集 {len(state['raw_items'])} 条素材",
            stream="system_runtime" if triggered_by == "scheduler" else "business_event",
            actor=triggered_by,
        )
        if active_work_scope == "collect_only":
            candidates = self._rebuild_candidates_for_state(
                state,
                work_scope_override=active_work_scope,
            )
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "collecting", 100),
                done=total_sources,
                total=total_sources,
                label="采集完成，即将完成",
            )
            self._heartbeat_runtime_run(runtime, stage="collecting:complete", now=datetime.now(UTC))
        else:
            self._append_log(
                state,
                "info",
                "runtime",
                f"阶段 {cluster_stage_no}/{stage_total}：开始聚合热点事件...",
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
            runtime["current_cycle"] = "clustering"
            self._progress_snapshot["cycle"] = "clustering"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "clustering", 10),
                done=0,
                total=0,
                label="采集完成，正在聚合热点事件",
            )
            self._heartbeat_runtime_run(runtime, stage="clustering", now=datetime.now(UTC))
            self._write_runtime_checkpoint(state)

            candidates = self._rebuild_candidates_for_state(
                state,
                work_scope_override=active_work_scope,
            )
            self._append_log(
                state,
                "info",
                "runtime",
                f"阶段 {cluster_stage_no}/{stage_total} 完成：形成 {len(state.get('intel_events', []))} 个热点事件",
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "clustering", 100),
                done=0,
                total=0,
                label="热点事件聚合完成",
            )

            stage_three_message = (
                f"阶段 {scoring_stage_no}/{stage_total}：开始整理热点排序..."
                if active_work_scope == "collect_events"
                else f"阶段 {scoring_stage_no}/{stage_total}：开始判断热度与预警..."
            )
            self._append_log(
                state,
                "info",
                "runtime",
                stage_three_message,
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
            runtime["current_cycle"] = "scoring"
            self._progress_snapshot["cycle"] = "scoring"
            scoring_label = "热点事件已聚合，正在整理热点排序" if active_work_scope == "collect_events" else "热点事件已聚合，正在判断热度与预警"
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "scoring", 10),
                done=0,
                total=0,
                label=scoring_label,
            )
            self._heartbeat_runtime_run(runtime, stage="scoring", now=datetime.now(UTC))
            self._write_runtime_checkpoint(state)

            stage_three_done = (
                f"阶段 {scoring_stage_no}/{stage_total} 完成：更新 {len(candidates)} 条重点观察"
                if active_work_scope == "collect_events"
                else f"阶段 {scoring_stage_no}/{stage_total} 完成：生成 {len(state.get('intel_alerts', []))} 条预警，更新 {len(candidates)} 条重点观察"
            )
            self._append_log(
                state,
                "info",
                "runtime",
                stage_three_done,
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
            self._set_runtime_progress(
                runtime,
                percent=self._stage_progress_percent(runtime, "scoring", 100),
                done=0,
                total=0,
                label="热度结果已更新，即将完成",
            )
            self._heartbeat_runtime_run(runtime, stage="scoring:complete", now=datetime.now(UTC))
            self._write_runtime_checkpoint(state)
        runtime["last_collect_at"] = stamp
        if collected:
            runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        level = "success"
        message = f"自动同步 {len(due_sources)} 个来源，新增 {len(collected)} 条素材，当前聚合出 {len(state.get('intel_events', []))} 个事件。"
        if not collected and warnings:
            level = "warning"
            message = f"自动同步执行完成，但本轮未获取到任何真实素材；涉及 {len(due_sources)} 个到期来源。"
        elif not collected:
            level = "warning"
            message = f"自动同步执行完成，但本轮没有新增素材；已检查 {len(due_sources)} 个到期来源。"
        self._append_log(
            state,
            level,
            "collection",
            message,
            stream="system_runtime" if triggered_by == "scheduler" else "business_event",
            actor=triggered_by,
        )
        for warning in warnings[:6]:
            self._append_log(state, "warning", "collection", warning, stream="system_runtime" if triggered_by == "scheduler" else "business_event", actor=triggered_by)
        return SourceSyncResponse(
            raw_count=len(state["raw_items"]),
            normalized_count=len(state["normalized_items"]),
            event_count=len(state.get("intel_events", [])),
            synced_at=stamp,
            warnings=warnings,
        )

    def _sync_sources_internal(
        self,
        state: dict[str, Any],
        triggered_by: str,
        work_scope_override: str | None = None,
    ) -> SourceSyncResponse:
        max_workers = state.get("settings", {}).get("max_workers", 8)
        raw_items, warnings = collect_enabled_sources(state["sources"], max_workers=max_workers)
        sources_by_key = self._sources_by_key(state)
        normalized = normalize_raw_items(raw_items, sources_by_key)
        stamp = now_iso()

        for source in state["sources"]:
            count = sum(1 for item in raw_items if item["source_key"] == source["key"])
            warning_text = next((warning for warning in warnings if warning.startswith(f"{source['name']}:")), None)
            now = datetime.now(UTC)
            items_for_source = [item for item in raw_items if item["source_key"] == source["key"]]
            self._record_source_attempt(
                source,
                started_at=now,
                completed_at=now,
                items=items_for_source,
                warning_text=warning_text if source.get("enabled") else None,
            )
            if source.get("enabled"):
                source["last_synced_at"] = stamp
            self._finalize_source_health(source, now=now)

        state["raw_items"] = raw_items
        candidates = self._rebuild_candidates_for_state(state, work_scope_override=work_scope_override)
        runtime = self._runtime(state)
        runtime["last_collect_at"] = stamp
        if raw_items:
            runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        level = "success"
        message = f"已同步 {len(raw_items)} 条素材，形成 {len(normalized)} 条标准化素材并聚合出 {len(state.get('intel_events', []))} 个事件。"
        if not raw_items and warnings:
            level = "warning"
            message = "已执行来源同步，但本轮没有获取到任何真实素材。"
        elif not raw_items:
            level = "warning"
            message = "已执行来源同步，但本轮没有新增素材。"
        self._append_log(
            state,
            level,
            "collection",
            message,
            stream="system_runtime" if triggered_by == "scheduler" else "business_event",
            actor=triggered_by,
        )
        for warning in warnings[:6]:
            self._append_log(state, "warning", "collection", warning, stream="system_runtime" if triggered_by == "scheduler" else "business_event", actor=triggered_by)
        return SourceSyncResponse(
            raw_count=len(raw_items),
            normalized_count=len(state["normalized_items"]),
            event_count=len(state.get("intel_events", [])),
            synced_at=stamp,
            warnings=warnings,
        )

    def _publish_backends(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return collect_backend_status(state["channels"]["wechat"], state["browser"]["wechat"])

    def list_automation_modes(self) -> list[AutomationModeDefinition]:
        state = self._upgrade_state(self._read())
        return [AutomationModeDefinition(**mode) for mode in state["automation_mode_definitions"]]

    def get_current_automation_mode(self) -> AutomationModeDefinition:
        state = self._upgrade_state(self._read())
        return AutomationModeDefinition(**self._current_automation_mode_def(state))

    def list_automation_profiles(self) -> list[AutomationModeProfile]:
        state = self._upgrade_state(self._read())
        return [AutomationModeProfile(**item) for item in state["automation_profiles"]]

    def get_current_automation_profile(self) -> AutomationModeProfile:
        state = self._upgrade_state(self._read())
        return AutomationModeProfile(**self._current_automation_profile(state))

    def update_automation_profile(self, mode: AutomationMode, profile: AutomationModeProfile) -> AutomationModeProfile:
        state = self._upgrade_state(self._read())
        profiles = self._automation_profile_map(state)
        if mode not in profiles:
            raise ValueError(f"Unknown automation mode profile: {mode}")
        payload = profile.model_dump()
        payload["mode"] = mode
        next_profiles: list[dict[str, Any]] = []
        for item in state["automation_profiles"]:
            if item["mode"] == mode:
                next_profiles.append(payload)
            else:
                next_profiles.append(item)
        state["automation_profiles"] = next_profiles
        runtime = self._runtime(state)
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        label = self._automation_mode_map(state).get(mode, {}).get("label", mode)
        self._append_log(state, "success", "mode", f"已更新 {label} 的运行参数。", actor="dashboard")
        self._write(state)
        return AutomationModeProfile(**payload)

    def set_current_automation_mode(self, mode: AutomationMode) -> AutomationModeDefinition:
        state = self._upgrade_state(self._read())
        modes = self._automation_mode_map(state)
        if mode not in modes:
            raise ValueError(f"Unknown automation mode: {mode}")
        if not modes[mode].get("available"):
            raise ValueError("该模式当前不可用。")
        state["automation_mode"] = mode
        runtime = self._runtime(state)
        runtime["current_mode"] = mode
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        self._append_log(state, "info", "mode", f"切换运行模式为 {modes[mode]['label']}", stream="business_event", actor="dashboard")
        self._write(state)
        return AutomationModeDefinition(**modes[mode])

    def get_runtime_plan(self) -> RuntimePlan:
        state = self._read_live()
        return self._runtime_plan_from_state(state)

    def update_runtime_plan(self, payload: RuntimePlanPayload, actor: str = "dashboard") -> RuntimePlan:
        with self._lock:
            state = self._upgrade_state(self._read())
            plan = self._runtime_plan(state)
            plan.update(payload.model_dump())
            runtime = self._runtime(state)
            runtime["launch_mode"] = plan["launch_mode"]
            runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
            runtime["delivery_mode"] = plan.get("delivery_mode", "immediate")
            runtime["delivery_schedule_time"] = plan.get("delivery_schedule_time")
            runtime["admission_strategy"] = plan.get("admission_strategy", "balanced")
            runtime["batch_limit"] = int(plan.get("batch_limit", 3) or 3)
            if runtime.get("control_state") != "running":
                runtime["scheduled_start_at"] = plan.get("start_at") if plan["launch_mode"] in {"once_at", "interval_at"} else None
            runtime["next_collect_at"] = self._calculate_next_collect_at(state)
            self._append_log(state, "success", "runtime", "已更新自动运行计划。", stream="business_event", actor=actor)
            self._write(state)
            return self._runtime_plan_from_state(state)

    def get_runtime_status(self) -> SchedulerStatus:
        with self._lock:
            state = self._read_live()
            recovered_run_id = self._recover_stale_runtime_run(state, actor="runtime_status")
            if recovered_run_id:
                self._write(state)
            return self._scheduler_status_from_state(state)

    def _scheduler_status_from_state(self, state: dict[str, Any]) -> SchedulerStatus:
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        last_cycle_issue_count, last_cycle_issue_summary = self._last_cycle_issue_snapshot(state, runtime)
        last_cycle_summary = runtime.get("last_cycle_summary") or self._build_last_cycle_summary(state, runtime)
        snapshot = self._progress_snapshot
        now_mono = time.monotonic()
        in_completion_hold = now_mono < self._completion_hold_until
        control_state = str(runtime.get("control_state") or "stopped")
        enabled_at = runtime.get("enabled_at")
        enabled_dt = parse_time(enabled_at)
        uptime_seconds = 0
        if control_state != "stopped" and enabled_dt:
            uptime_seconds = max(int((datetime.now(UTC) - enabled_dt).total_seconds()), 0)
        if in_completion_hold:
            current_cycle = "completed"
            progress_percent = 100
            progress_done = int(snapshot.get("done", 1))
            progress_total = int(snapshot.get("total", 1))
            progress_label = snapshot.get("label") or "本轮已完成"
        else:
            current_cycle = str(snapshot.get("cycle") or runtime.get("current_cycle", "idle"))
            progress_percent = int(snapshot.get("percent", runtime.get("current_cycle_progress_percent", 0)) or 0)
            progress_done = int(snapshot.get("done", runtime.get("current_cycle_progress_done", 0)) or 0)
            progress_total = int(snapshot.get("total", runtime.get("current_cycle_progress_total", 0)) or 0)
            progress_label = snapshot.get("label") or runtime.get("current_cycle_progress_label")
        current_cycle, progress_percent, progress_done, progress_total, progress_label = self._normalize_runtime_status_progress(
            runtime,
            cycle=current_cycle,
            percent=progress_percent,
            done=progress_done,
            total=progress_total,
            label=progress_label,
        )
        stage_key, stage_label, stage_index, stage_total = self._stage_status(runtime, current_cycle)
        return SchedulerStatus(
            running=control_state != "stopped",
            control_state=control_state,
            launch_mode=str(runtime.get("launch_mode") or self._runtime_plan(state).get("launch_mode") or "interval_now"),
            current_mode=state["automation_mode"],
            work_scope=str(runtime.get("work_scope") or self._runtime_plan(state).get("work_scope") or "collect_events_alerts"),
            last_collect_at=runtime.get("last_collect_at"),
            last_event_sync_at=runtime.get("last_event_sync_at"),
            last_brief_at=runtime.get("last_brief_at"),
            next_collect_at=runtime.get("next_collect_at"),
            delivery_mode=str(self._runtime_plan(state).get("delivery_mode") or "immediate"),
            delivery_schedule_time=self._runtime_plan(state).get("delivery_schedule_time"),
            admission_strategy=str(self._runtime_plan(state).get("admission_strategy") or "balanced"),
            batch_limit=max(int(self._runtime_plan(state).get("batch_limit", 3) or 3), 1),
            current_cycle=current_cycle,
            current_cycle_progress_percent=progress_percent,
            current_cycle_progress_done=progress_done,
            current_cycle_progress_total=progress_total,
            current_cycle_progress_label=progress_label,
            stage_key=stage_key,
            stage_label=stage_label,
            stage_index=stage_index,
            stage_total=stage_total,
            enabled_at=runtime.get("enabled_at"),
            scheduled_start_at=runtime.get("scheduled_start_at"),
            current_cycle_started_at=runtime.get("current_cycle_started_at"),
            last_cycle_started_at=runtime.get("last_cycle_started_at"),
            last_cycle_finished_at=runtime.get("last_cycle_finished_at"),
            last_cycle_duration_seconds=runtime.get("last_cycle_duration_seconds"),
            uptime_seconds=uptime_seconds,
            completed_cycles_today=int(runtime.get("completed_cycles_today", 0) or 0),
            failed_cycles_today=int(runtime.get("failed_cycles_today", 0) or 0),
            last_error=runtime.get("last_error"),
            blocked_reason=runtime.get("blocked_reason"),
            last_cycle_issue_count=last_cycle_issue_count,
            last_cycle_issue_summary=last_cycle_issue_summary,
            run_id=run.get("run_id"),
            run_status=str(run.get("status") or "idle"),
            run_stage=str(run.get("stage") or "idle"),
            run_started_at=run.get("started_at"),
            run_heartbeat_at=run.get("heartbeat_at"),
            run_finished_at=run.get("finished_at"),
            run_triggered_by=run.get("triggered_by"),
            run_error=run.get("error"),
            recovered_run_id=run.get("recovered_run_id"),
            run_stale=self._runtime_run_is_stale(run),
            run_intent=str(run.get("intent") or DEFAULT_RUNTIME_INTENT),
            last_run_outcome=run.get("last_run_outcome"),
            last_cycle_summary=RuntimeCycleSummary(**last_cycle_summary) if isinstance(last_cycle_summary, dict) else None,
        )

    def set_scheduler_running(self, running: bool) -> None:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            runtime["scheduler_running"] = running
            if not running and runtime.get("control_state") != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                self._reset_runtime_progress(runtime)
                runtime["enabled_at"] = None
                runtime["scheduled_start_at"] = None
                runtime["current_cycle_started_at"] = None
                runtime["next_collect_at"] = None
            self._write(state)

    def reset_runtime_on_boot(
        self,
        actor: str = "system",
        message: str = "服务启动后自动运行保持关闭，需要在驾驶舱手动启动。",
    ) -> SchedulerStatus:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            self._finish_runtime_run(runtime, status="idle", stage="idle", error=None, recovered_run_id=None)
            self._set_runtime_run_intent(runtime, DEFAULT_RUNTIME_INTENT)
            runtime["scheduler_running"] = False
            runtime["control_state"] = "stopped"
            runtime["current_cycle"] = "idle"
            self._reset_runtime_progress(runtime)
            runtime["enabled_at"] = None
            runtime["scheduled_start_at"] = None
            runtime["current_cycle_started_at"] = None
            runtime["next_collect_at"] = None
            runtime["launch_mode"] = self._runtime_plan(state).get("launch_mode", "interval_now")
            runtime["work_scope"] = self._runtime_plan(state).get("work_scope", "collect_events_alerts")
            runtime["active_interval_minutes"] = None
            runtime["last_error"] = None
            self._append_log(
                state,
                "info",
                "runtime",
                message,
                stream="system_runtime",
                actor=actor,
            )
            self._write(state)
            return self._scheduler_status_from_state(state)

    def start_runtime(self, actor: str = "dashboard") -> SchedulerStatus:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            now = datetime.now(UTC)
            self._recover_stale_runtime_run(state, actor=actor, now=now)
            run = self._runtime_run(runtime)
            startup_inflight = (
                str(run.get("status") or "idle") == "running"
                and str(run.get("stage") or "idle") == "starting"
                and str(runtime.get("current_cycle") or "idle") == "starting"
            )
            if str(run.get("status") or "idle") == "running" and not self._runtime_run_is_stale(run, now) and not startup_inflight:
                return self._scheduler_status_from_state(state)
            plan = self._runtime_plan(state)
            runtime["scheduler_running"] = True
            runtime["current_mode"] = state["automation_mode"]
            runtime["launch_mode"] = plan["launch_mode"]
            runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
            runtime["delivery_mode"] = plan.get("delivery_mode", "immediate")
            runtime["delivery_schedule_time"] = plan.get("delivery_schedule_time")
            runtime["admission_strategy"] = plan.get("admission_strategy", "balanced")
            runtime["batch_limit"] = int(plan.get("batch_limit", 3) or 3)
            runtime["last_error"] = None
            runtime["blocked_reason"] = None
            self._set_runtime_run_intent(runtime, DEFAULT_RUNTIME_INTENT)
            runtime["enabled_at"] = now.replace(microsecond=0).isoformat()
            runtime["scheduled_start_at"] = plan.get("start_at") if plan["launch_mode"] in {"once_at", "interval_at"} else None
            runtime["active_interval_minutes"] = plan.get("interval_minutes")
            if plan["launch_mode"] in {"once_at", "interval_at"} and runtime.get("scheduled_start_at"):
                scheduled_dt = parse_time(runtime["scheduled_start_at"])
                if scheduled_dt and scheduled_dt > now:
                    runtime["control_state"] = "armed"
                    runtime["current_cycle"] = "idle"
                    self._reset_runtime_progress(runtime)
                    runtime["next_collect_at"] = runtime["scheduled_start_at"]
                    self._append_log(state, "info", "runtime", "自动运行计划已设定，等待到点启动。", stream="system_runtime", actor=actor)
                    self._append_log(state, "info", "runtime", "已从前端启用自动运行计划。", stream="business_event", actor=actor)
                    self._write(state)
                    return self._scheduler_status_from_state(state)
            immediate_launch = plan["launch_mode"] in {"once_now", "interval_now"}
            runtime["control_state"] = "running" if immediate_launch else "waiting"
            runtime["current_cycle"] = "starting" if immediate_launch else "idle"
            if immediate_launch:
                self._set_runtime_progress(runtime, percent=2, done=0, total=0, label="正在启动工作轮次")
                self._progress_snapshot["cycle"] = "starting"
                self._finish_runtime_run(runtime, status="idle", stage="starting", error=None, recovered_run_id=None, now=now)
            else:
                self._reset_runtime_progress(runtime)
                self._finish_runtime_run(runtime, status="idle", stage="idle", error=None, recovered_run_id=None, now=now)
            runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat() if immediate_launch else None
            runtime["next_collect_at"] = now.replace(microsecond=0).isoformat() if immediate_launch else self._calculate_next_collect_at(state)
            self._append_log(state, "info", "runtime", "后台自动调度器已启动。", stream="system_runtime", actor=actor)
            self._append_log(state, "info", "runtime", "已从前端恢复自动运行。", stream="business_event", actor=actor)
            self._write(state)
            if immediate_launch:
                self._launch_runtime_cycle_async(triggered_by="runtime_start", force=True)
                return self._scheduler_status_from_state(state)
            return self._scheduler_status_from_state(self._upgrade_state(self._read()))

    def stop_runtime(self, actor: str = "dashboard") -> SchedulerStatus:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            runtime["scheduler_running"] = False
            if runtime.get("control_state") != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                self._reset_runtime_progress(runtime)
                runtime["current_cycle_started_at"] = None
                runtime["enabled_at"] = None
                self._finish_runtime_run(runtime, status="idle", stage="idle", error=None, recovered_run_id=None, last_run_outcome="stopped")
            runtime["scheduled_start_at"] = None
            runtime["next_collect_at"] = None if runtime.get("control_state") != "running" else runtime.get("next_collect_at")
            self._append_log(state, "warning", "runtime", "后台自动调度器已暂停。", stream="system_runtime", actor=actor)
            self._append_log(state, "warning", "runtime", "已从前端暂停自动运行。", stream="business_event", actor=actor)
            self._write(state)
            return self._scheduler_status_from_state(state)

    def run_runtime_intent(self, intent: RuntimeIntent, actor: str = "dashboard") -> SchedulerStatus:
        work_scope = INTENT_TO_WORK_SCOPE.get(str(intent))
        if not work_scope:
            raise ValueError("未知的维护动作。")

        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            run = self._runtime_run(runtime)
            now = datetime.now(UTC)
            self._recover_stale_runtime_run(state, actor=actor, now=now)
            if str(runtime.get("control_state") or "stopped") != "stopped":
                raise ValueError("监测已启用，请先停止后再执行维护动作。")
            if str(run.get("status") or "idle") == "running" and not self._runtime_run_is_stale(run, now):
                raise ValueError("当前已有运行中的轮次，请稍后再试。")

            runtime["scheduler_running"] = False
            runtime["control_state"] = "running"
            runtime["current_mode"] = state["automation_mode"]
            runtime["launch_mode"] = "once_now"
            runtime["work_scope"] = work_scope
            runtime["delivery_mode"] = self._runtime_plan(state).get("delivery_mode", "immediate")
            runtime["delivery_schedule_time"] = self._runtime_plan(state).get("delivery_schedule_time")
            runtime["admission_strategy"] = self._runtime_plan(state).get("admission_strategy", "balanced")
            runtime["batch_limit"] = int(self._runtime_plan(state).get("batch_limit", 3) or 3)
            runtime["last_error"] = None
            runtime["blocked_reason"] = None
            runtime["enabled_at"] = now.replace(microsecond=0).isoformat()
            runtime["scheduled_start_at"] = None
            runtime["active_interval_minutes"] = None
            runtime["current_cycle"] = "starting"
            runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat()
            self._reset_runtime_cycle_context(runtime)
            runtime["next_collect_at"] = None
            self._set_runtime_progress(runtime, percent=2, done=0, total=0, label="正在启动维护任务")
            self._progress_snapshot["cycle"] = "starting"
            self._set_runtime_run_intent(runtime, str(intent))
            self._finish_runtime_run(runtime, status="idle", stage="starting", error=None, recovered_run_id=None, now=now)
            self._append_log(state, "info", "runtime", f"已启动维护动作：{intent}", stream="business_event", actor=actor)
            self._write(state)

        if work_scope == "collect_only":
            try:
                self._run_automation_cycle_locked(state, triggered_by=actor, force=True)
            finally:
                with self._lock:
                    state = self._upgrade_state(self._read())
                    runtime = self._runtime(state)
                    plan = self._runtime_plan(state)
                    runtime["launch_mode"] = plan.get("launch_mode", "interval_now")
                    runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
                    self._write(state)
        else:
            with self._lock:
                state = self._upgrade_state(self._read())
                runtime = self._runtime(state)
                now = datetime.now(UTC)
                runtime["control_state"] = "running"
                runtime["current_cycle"] = "clustering" if work_scope == "collect_events" else "scoring"
                runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat()
                runtime["last_cycle_started_at"] = runtime["current_cycle_started_at"]
                progress_label = "正在重建热点事件" if work_scope == "collect_events" else "正在重算预警"
                progress_cycle = "clustering" if work_scope == "collect_events" else "scoring"
                self._set_runtime_progress(runtime, percent=35, done=0, total=0, label=progress_label)
                self._progress_snapshot["cycle"] = progress_cycle
                self._start_runtime_run(runtime, stage=progress_cycle, triggered_by=actor, intent=str(intent), now=now)
                self._write(state)
            start = datetime.now(UTC)
            try:
                with self._lock:
                    state = self._upgrade_state(self._read())
                    runtime = self._runtime(state)
                    candidates = self._rebuild_candidates_for_state(state, work_scope_override=work_scope)
                    finish = datetime.now(UTC)
                    duration = round((finish - start).total_seconds(), 1)
                    runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
                    runtime["last_cycle_duration_seconds"] = duration
                    runtime["current_cycle_started_at"] = None
                    runtime["completed_cycles_today"] = int(runtime.get("completed_cycles_today", 0) or 0) + 1
                    runtime["control_state"] = "stopped"
                    runtime["current_cycle"] = "idle"
                    runtime["enabled_at"] = None
                    runtime["next_collect_at"] = None
                    self._set_runtime_progress(runtime, percent=100, done=1, total=1, label="本轮已完成")
                    self._finish_runtime_run(
                        runtime,
                        status="completed",
                        stage="done",
                        error=None,
                        last_run_outcome="completed",
                        now=finish,
                    )
                    runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
                    self._append_job(
                        state,
                        "rebuild_candidates",
                        f"已完成维护动作：{intent}，当前 {len(candidates)} 个候选主题。",
                        triggered_by=actor,
                    )
                    self._reset_runtime_progress(runtime)
                    plan = self._runtime_plan(state)
                    runtime["launch_mode"] = plan.get("launch_mode", "interval_now")
                    runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
                    self._write(state)
            except Exception as exc:
                with self._lock:
                    state = self._upgrade_state(self._read())
                    runtime = self._runtime(state)
                    finish = datetime.now(UTC)
                    duration = round((finish - start).total_seconds(), 1)
                    runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
                    runtime["last_cycle_duration_seconds"] = duration
                    runtime["current_cycle_started_at"] = None
                    runtime["failed_cycles_today"] = int(runtime.get("failed_cycles_today", 0) or 0) + 1
                    runtime["last_error"] = str(exc)
                    runtime["control_state"] = "stopped"
                    runtime["current_cycle"] = "failed"
                    self._set_runtime_progress(runtime, percent=100, done=1, total=1, label=f"本轮失败：{exc}")
                    self._progress_snapshot["cycle"] = "failed"
                    self._finish_runtime_run(
                        runtime,
                        status="failed",
                        stage="failed",
                        error=str(exc),
                        last_run_outcome="failed",
                        now=finish,
                    )
                    runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
                    self._append_log(
                        state,
                        "error",
                        "runtime",
                        f"维护动作失败：{intent} - {exc}",
                        stream="system_runtime",
                        actor=actor,
                    )
                    self._append_job(
                        state,
                        "rebuild_candidates",
                        f"维护动作失败：{intent} - {exc}",
                        status="failed",
                        triggered_by=actor,
                    )
                    plan = self._runtime_plan(state)
                    runtime["launch_mode"] = plan.get("launch_mode", "interval_now")
                    runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
                    self._write(state)
                raise

        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            plan = self._runtime_plan(state)
            runtime["launch_mode"] = plan.get("launch_mode", "interval_now")
            runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
            self._write(state)
            return self._scheduler_status_from_state(state)

    def _run_automation_cycle_locked(self, state: dict[str, Any], triggered_by: str, force: bool = False) -> dict[str, Any]:
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        now = datetime.now(UTC)
        recovered_run_id = self._recover_stale_runtime_run(state, actor=triggered_by, now=now)
        run = self._runtime_run(runtime)
        current_cycle = str(runtime.get("current_cycle", "idle"))
        startup_inflight = (
            force
            and str(run.get("status") or "idle") == "running"
            and str(run.get("stage") or "idle") == "starting"
            and current_cycle == "starting"
        )
        if str(run.get("status") or "idle") == "running" and not self._runtime_run_is_stale(run, now) and not startup_inflight:
            with self._lock:
                self._write(state)
            return {"status": "busy", "current_cycle": current_cycle, "run_id": run.get("run_id")}
        if not force and current_cycle not in ("idle", "failed"):
            with self._lock:
                self._write(state)
            return {"status": "busy", "current_cycle": current_cycle}
        plan = self._runtime_plan(state)
        stage_plan = self._stage_plan(runtime)
        stage_positions = {item["key"]: index + 1 for index, item in enumerate(stage_plan)}
        stage_total = len(stage_plan)
        collect_stage_no = stage_positions.get("collecting", 1)
        control_state = str(runtime.get("control_state") or "stopped")

        if not force:
            if not runtime.get("scheduler_running") and control_state != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                self._reset_runtime_progress(runtime)
                runtime["next_collect_at"] = None
                with self._lock:
                    self._write(state)
                return {"status": "stopped"}
            if control_state == "armed":
                scheduled_at = parse_time(runtime.get("scheduled_start_at"))
                if scheduled_at and now < scheduled_at:
                    runtime["next_collect_at"] = runtime.get("scheduled_start_at")
                    with self._lock:
                        self._write(state)
                    return {"status": "armed"}
                runtime["control_state"] = "waiting"
            elif control_state == "stopped":
                runtime["next_collect_at"] = None
                self._reset_runtime_progress(runtime)
                with self._lock:
                    self._write(state)
                return {"status": "stopped"}
            elif control_state == "waiting":
                next_due = parse_time(runtime.get("next_collect_at"))
                if next_due and now < next_due:
                    with self._lock:
                        self._write(state)
                    return {"status": "waiting"}

        runtime["control_state"] = "running"
        runtime["current_mode"] = state["automation_mode"]
        runtime["current_cycle"] = "collecting"
        runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat()
        runtime["last_cycle_started_at"] = runtime["current_cycle_started_at"]
        self._reset_runtime_cycle_context(runtime)
        self._set_runtime_progress(runtime, percent=5, done=0, total=0, label="正在准备采集来源")
        self._progress_snapshot["cycle"] = "collecting"
        self._start_runtime_run(
            runtime,
            stage="collecting",
            triggered_by=triggered_by,
            intent=str(run.get("intent") or DEFAULT_RUNTIME_INTENT),
            now=now,
        )
        if recovered_run_id:
            self._runtime_run(runtime)["recovered_run_id"] = recovered_run_id
        runtime["launch_mode"] = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")
        runtime["last_error"] = None
        runtime["blocked_reason"] = None
        self._sync_runtime_counters(runtime)
        self._append_log(state, "info", "runtime", f"轮次启动：launch_mode={runtime['launch_mode']}, work_scope={runtime['work_scope']}, force={force}", stream="system_runtime", actor=triggered_by)
        with self._lock:
            self._write(state)

        start = datetime.now(UTC)
        try:
            self._append_log(
                state,
                "info",
                "runtime",
                f"阶段 {collect_stage_no}/{stage_total}：开始采集到期来源...",
                stream="system_runtime",
                actor=triggered_by,
            )
            self._heartbeat_runtime_run(runtime, stage="collecting", now=start)
            self._write_runtime_checkpoint(state)
            sync_response = self._sync_due_sources(
                state,
                triggered_by="scheduler",
                minimum_interval_minutes=None,
            )
            self._write_runtime_checkpoint(state)
            self._run_delivery_pipeline(state, runtime, triggered_by=triggered_by)
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)

            finish = datetime.now(UTC)
            duration = round((finish - start).total_seconds(), 1)
            self._append_log(state, "info", "runtime", f"轮次完成，总耗时 {duration}s", stream="system_runtime", actor=triggered_by)
            runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
            runtime["last_cycle_duration_seconds"] = duration
            runtime["current_cycle_started_at"] = None
            self._set_runtime_progress(runtime, percent=100, done=1, total=1, label="本轮已完成")
            self._finish_runtime_run(
                runtime,
                status="completed",
                stage="done",
                error=None,
                last_run_outcome="completed",
                now=finish,
            )
            runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
            self._completion_hold_until = time.monotonic() + 5
            runtime["completed_cycles_today"] = int(runtime.get("completed_cycles_today", 0) or 0) + 1
            launch_mode = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")
            if not runtime.get("scheduler_running") or launch_mode in {"once_now", "once_at"}:
                runtime["scheduler_running"] = False
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                self._reset_runtime_progress(runtime)
                runtime["enabled_at"] = None
                runtime["scheduled_start_at"] = None
                runtime["active_interval_minutes"] = None
                runtime["next_collect_at"] = None
            else:
                runtime["control_state"] = "waiting"
                runtime["current_cycle"] = "idle"
                self._reset_runtime_progress(runtime)
                runtime["next_collect_at"] = self._calculate_runtime_next_collect_at(state, finish)
            self._append_job(
                state,
                "collect_news",
                (
                    f"自动轮次完成：素材 {sync_response.raw_count}，事件 {sync_response.event_count}，"
                    f"入选 {int(runtime.get('current_cycle_metrics', {}).get('selected_event_count', 0) or 0)}，"
                    f"深挖 {int(runtime.get('current_cycle_metrics', {}).get('deep_dive_count', 0) or 0)}，"
                    f"简报 {int(runtime.get('current_cycle_metrics', {}).get('brief_count', 0) or 0)}，"
                    f"上传 {int(runtime.get('current_cycle_metrics', {}).get('wechat_sync_count', 0) or 0)}，"
                    f"回查 {int(runtime.get('current_cycle_metrics', {}).get('wechat_verify_count', 0) or 0)}，耗时 {duration}s。"
                ),
                triggered_by="scheduler",
            )
            with self._lock:
                self._write(state)
            return {
                "raw_count": sync_response.raw_count,
                "event_count": sync_response.event_count,
                "selected_event_count": int(runtime.get("current_cycle_metrics", {}).get("selected_event_count", 0) or 0),
                "deep_dive_count": int(runtime.get("current_cycle_metrics", {}).get("deep_dive_count", 0) or 0),
                "brief_count": int(runtime.get("current_cycle_metrics", {}).get("brief_count", 0) or 0),
                "wechat_synced_count": int(runtime.get("current_cycle_metrics", {}).get("wechat_sync_count", 0) or 0),
                "wechat_verify_count": int(runtime.get("current_cycle_metrics", {}).get("wechat_verify_count", 0) or 0),
                "duration": duration,
            }
        except Exception as exc:  # pragma: no cover - scheduler guard
            tb = traceback.format_exc()
            finish = datetime.now(UTC)
            duration = round((finish - start).total_seconds(), 1)
            runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
            runtime["last_cycle_duration_seconds"] = duration
            runtime["current_cycle_started_at"] = None
            runtime["current_cycle_progress_label"] = f"本轮失败：{exc}"
            self._progress_snapshot["label"] = f"本轮失败：{exc}"
            self._progress_snapshot["cycle"] = "failed"
            self._completion_hold_until = 0
            runtime["failed_cycles_today"] = int(runtime.get("failed_cycles_today", 0) or 0) + 1
            runtime["last_error"] = str(exc)
            runtime["current_cycle"] = "failed"
            self._finish_runtime_run(
                runtime,
                status="failed",
                stage="failed",
                error=str(exc),
                last_run_outcome="failed",
                now=finish,
            )
            runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
            if not runtime.get("scheduler_running") or str(runtime.get("launch_mode") or plan.get("launch_mode")) in {"once_now", "once_at"}:
                runtime["scheduler_running"] = False
                runtime["control_state"] = "stopped"
                runtime["enabled_at"] = None
                runtime["scheduled_start_at"] = None
                runtime["next_collect_at"] = None
            else:
                runtime["control_state"] = "waiting"
                runtime["next_collect_at"] = self._calculate_runtime_next_collect_at(state, finish)
            self._append_job(
                state,
                "collect_news",
                f"自动轮次失败：{exc}",
                status="failed",
                triggered_by="scheduler",
            )
            self._append_log(
                state,
                "error",
                "runtime",
                f"自动轮次失败：{exc}",
                stream="system_runtime",
                actor=triggered_by,
                detail=tb,
            )
            with self._lock:
                self._write(state)
            raise

    def run_automation_cycle(self) -> dict[str, Any]:
        with self._lock:
            state = self._upgrade_state(self._read())
        return self._run_automation_cycle_locked(state, triggered_by="scheduler")

    def _launch_runtime_cycle_async(self, triggered_by: str, force: bool = False) -> None:
        def runner() -> None:
            try:
                # Acquire lock only to read initial state, then release
                with self._lock:
                    state = self._upgrade_state(self._read())
                # Run the cycle without holding the lock during I/O
                self._run_automation_cycle_locked(state, triggered_by=triggered_by, force=force)
            except Exception as exc:
                tb = traceback.format_exc()
                try:
                    with self._lock:
                        state = self._upgrade_state(self._read())
                        runtime = self._runtime(state)
                        run = self._runtime_run(runtime)
                        finish = datetime.now(UTC)
                        if str(run.get("status") or "idle") == "running":
                            started_at = parse_time(runtime.get("last_cycle_started_at")) or finish
                            runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
                            runtime["last_cycle_duration_seconds"] = round((finish - started_at).total_seconds(), 1)
                            runtime["current_cycle_started_at"] = None
                            runtime["current_cycle"] = "failed"
                            runtime["last_error"] = str(exc)
                            runtime["failed_cycles_today"] = int(runtime.get("failed_cycles_today", 0) or 0) + 1
                            self._finish_runtime_run(
                                runtime,
                                status="failed",
                                stage="failed",
                                error=str(exc),
                                last_run_outcome="failed",
                                now=finish,
                            )
                            runtime["last_cycle_summary"] = self._build_last_cycle_summary(state, runtime)
                            launch_mode = str(runtime.get("launch_mode") or self._runtime_plan(state).get("launch_mode") or "interval_now")
                            runtime["scheduler_running"] = False if launch_mode in {"once_now", "once_at"} else bool(runtime.get("scheduler_running"))
                            runtime["control_state"] = "stopped" if launch_mode in {"once_now", "once_at"} else "waiting"
                            runtime["current_cycle"] = "idle"
                            self._reset_runtime_progress(runtime)
                            if launch_mode in {"once_now", "once_at"}:
                                runtime["enabled_at"] = None
                                runtime["scheduled_start_at"] = None
                                runtime["active_interval_minutes"] = None
                                runtime["next_collect_at"] = None
                            else:
                                runtime["next_collect_at"] = self._calculate_runtime_next_collect_at(state, finish)
                        self._append_job(
                            state,
                            "collect_news",
                            f"后台线程异常退出：{exc}",
                            status="failed",
                            triggered_by=triggered_by,
                        )
                        self._append_log(
                            state,
                            "error",
                            "runtime",
                            f"后台线程异常退出：{exc}",
                            stream="system_runtime",
                            actor=triggered_by,
                            detail=tb,
                        )
                        self._write(state)
                        self._progress_snapshot["label"] = f"本轮失败：{exc}"
                        self._progress_snapshot["cycle"] = "idle"
                        self._completion_hold_until = 0
                except Exception:
                    pass
                return

        Thread(
            target=runner,
            name=f"studio-{triggered_by}",
            daemon=True,
        ).start()

    def list_sources(self) -> list[SourceConnector]:
        state = self._upgrade_state(self._read())
        return [SourceConnector(**item) for item in state["sources"]]

    def update_source(self, source_key: str, payload: SourceConnectorPayload) -> SourceConnector:
        state = self._upgrade_state(self._read())
        source = self._find_source(state, source_key)
        source.update(payload.model_dump(exclude_none=True))
        source["updated_at"] = now_iso()
        config = self._read_config()
        overrides = config.setdefault("sources", {}).setdefault("overrides", {})
        overrides[source_key] = {
            "enabled": bool(source.get("enabled", True)),
            "schedule": str(source.get("schedule") or "").strip(),
            "priority": int(source.get("priority") or 5),
            "url": source.get("url"),
            "tags": deepcopy_json(source.get("tags", [])),
            "weight": float(source.get("weight") or 0.7),
            "auth": deepcopy_json(source.get("auth", {})),
        }
        self._append_log(state, "success", "source", f"已更新来源配置：{source['name']}")
        runtime = self._runtime(state)
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return SourceConnector(**source)

    def create_source(self, payload: CreateSourcePayload) -> SourceConnector:
        state = self._upgrade_state(self._read())
        existing = [s for s in state["sources"] if s["key"] == payload.key]
        if existing:
            raise ValueError(f"来源 key 已存在: {payload.key}")
        new_source = {
            "key": payload.key,
            "name": payload.name,
            "kind": payload.kind,
            "driver": payload.driver,
            "platform": "rss" if payload.kind in ("rss", "rsshub") else "api",
            "enabled": payload.enabled,
            "schedule": payload.schedule,
            "interval_minutes": None,
            "priority": payload.priority,
            "weight": payload.weight,
            "auth": payload.auth,
            "url": payload.url,
            "tags": payload.tags,
            "capabilities": [],
            "origin_repo": "user-defined",
            "origin_license": "",
            "health_status": "idle",
            "health_detail": "",
            "item_count": 0,
            "last_synced_at": None,
            "last_error": None,
            "updated_at": now_iso(),
        }
        state["sources"].append(new_source)
        self._append_log(state, "success", "source", f"已添加来源：{payload.name}")
        self._write(state)
        return SourceConnector(**new_source)

    def delete_source(self, source_key: str) -> None:
        state = self._upgrade_state(self._read())
        self._find_source(state, source_key)
        state["sources"] = [s for s in state["sources"] if s["key"] != source_key]
        config = self._read_config()
        overrides = config.setdefault("sources", {}).setdefault("overrides", {})
        overrides.pop(source_key, None)
        self._append_log(state, "success", "source", f"已删除来源：{source_key}")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)

    def sync_sources(self, triggered_by: str = "dashboard") -> SourceSyncResponse:
        state = self._upgrade_state(self._read())
        response = self._sync_sources_internal(state, triggered_by=triggered_by)
        self._append_job(
            state,
            "collect_news",
            f"已采集 {response.raw_count} 条素材并刷新事件聚合。",
            triggered_by=triggered_by,
        )
        self._write(state)
        return response

    def sync_source(self, source_key: str, triggered_by: str = "dashboard") -> SourceSyncResponse:
        state = self._upgrade_state(self._read())
        source = self._find_source(state, source_key)
        stamp = now_iso()
        warnings: list[str] = []
        try:
            items, warning = collect_from_source(source)
            if warning:
                warnings.append(f"{source['name']}: {warning}")
        except Exception as exc:  # pragma: no cover - defensive
            items = []
            warnings.append(f"{source['name']}: 抓取器异常，已跳过: {exc}")

        warning_text = warnings[0] if warnings else None
        source["item_count"] = len(items)
        source["last_synced_at"] = stamp
        if warning_text and items:
            source["health_status"] = "warning"
            source["health_detail"] = warning_text
        elif warning_text:
            source["health_status"] = "error"
            source["health_detail"] = warning_text
        else:
            source["health_status"] = "healthy"
            source["health_detail"] = f"最近一次同步产生 {len(items)} 条素材。"
        source["last_error"] = warning_text

        state["raw_items"] = sorted(
            [item for item in state["raw_items"] if item["source_key"] != source_key] + items,
            key=lambda item: parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )[:MAX_RAW_ITEMS]
        candidates = self._rebuild_candidates_for_state(state)
        runtime = self._runtime(state)
        runtime["last_collect_at"] = stamp
        if items:
            runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        message = f"已重抓来源 {source['name']}，新增 {len(items)} 条素材，当前聚合出 {len(state.get('intel_events', []))} 个事件。"
        level = "success" if not warning_text else "warning"
        if not items and warning_text:
            message = f"已执行来源重抓，但 {source['name']} 本轮没有返回任何真实素材。"
        elif not items:
            level = "warning"
            message = f"已执行来源重抓，但 {source['name']} 本轮没有新增素材。"
        self._append_log(
            state,
            level,
            "collection",
            message,
            stream="business_event",
            actor=triggered_by,
        )
        for warning in warnings[:3]:
            self._append_log(state, "warning", "collection", warning, stream="business_event", actor=triggered_by)
        self._append_job(state, "collect_news", f"已重抓来源《{source['name']}》。", triggered_by=triggered_by)
        self._write(state)
        return SourceSyncResponse(
            raw_count=len(state["raw_items"]),
            normalized_count=len(state["normalized_items"]),
            event_count=len(state.get("intel_events", [])),
            synced_at=stamp,
            warnings=warnings,
        )

    def get_settings(self) -> dict[str, Any]:
        config = self._upgrade_user_settings(self._read_config())
        return deepcopy_json(config.get("settings", {}))

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        settings = state.setdefault("settings", {})
        config = self._read_config()
        config_settings = config.setdefault("settings", {})
        if "max_workers" in updates:
            value = int(updates["max_workers"])
            if not 1 <= value <= 20:
                raise ValueError("max_workers 必须在 1-20 之间")
            settings["max_workers"] = value
            config_settings["max_workers"] = value
        if "tavily_api_key" in updates:
            compact = str(updates.get("tavily_api_key") or "").strip()
            settings["tavily_api_key"] = compact
            config_settings["tavily_api_key"] = compact
        self._append_log(state, "success", "settings", f"已更新设置: {list(updates.keys())}")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return settings

    def _make_llm_service(self, state: dict[str, Any]) -> LLMService | None:
        llm_config = state.get("llm", {})
        if not llm_config or not llm_config.get("profiles"):
            return None
        profiles = [item for item in llm_config.get("profiles", []) if isinstance(item, dict)]
        current_profile_id = str(llm_config.get("current_profile_id") or "").strip()
        fallback_profile_id = str(llm_config.get("fallback_profile_id") or "").strip()
        active_profile = next((item for item in profiles if str(item.get("id") or "") == current_profile_id), None)
        fallback_profile = next((item for item in profiles if str(item.get("id") or "") == fallback_profile_id), None)
        runtime_tasks = build_runtime_tasks(active_profile, fallback_profile)
        if not runtime_tasks or not runtime_tasks[0].get("provider_key"):
            return None
        providers = [
            build_provider_from_profile(profile)
            for profile in profiles
            if bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key", ""))
        ]
        if not providers:
            return None
        config = deepcopy(llm_config)
        config["providers"] = providers
        config["tasks"] = runtime_tasks
        return LLMService(config)

    def _sync_llm_usage(self, state: dict[str, Any], llm_service: LLMService | None) -> None:
        if not llm_service:
            return
        state.setdefault("llm", {}).setdefault("usage_today", {})
        state["llm"]["usage_today"] = llm_service.get_usage()

    def _maybe_enhance_brief(
        self,
        llm_service: LLMService | None,
        event: dict[str, Any],
        deep_dive: dict[str, Any],
        brief_payload: dict[str, Any],
    ) -> tuple[str, str, list[str], str]:
        if not llm_service:
            return (
                str(brief_payload.get("one_line") or ""),
                str(brief_payload.get("why_it_matters") or ""),
                list(brief_payload.get("risk_notes", [])),
                "rule",
            )
        full_text_sources = self._build_full_text_sources_for_ai(deep_dive)
        if not full_text_sources:
            return (
                str(brief_payload.get("one_line") or ""),
                str(brief_payload.get("why_it_matters") or ""),
                list(brief_payload.get("risk_notes", [])),
                "rule",
            )
        for retry in (False, True):
            try:
                messages = self._build_enhancement_messages(
                    event,
                    brief_payload,
                    full_text_sources,
                    retry=retry,
                )
                result = llm_service.generate("article", messages, temperature=0.2, max_tokens=700, timeout=90.0)
                payload = self._extract_enhanced_brief_payload(str(result.get("content") or ""))
                validated = self._validate_enhanced_brief_payload(payload)
                if not validated:
                    continue
                one_line, why_it_matters, risk_notes = validated
                if not risk_notes:
                    risk_notes = list(brief_payload.get("risk_notes", []))
                return one_line, why_it_matters, risk_notes[:5], "enhanced"
            except Exception:
                continue
        return (
            str(brief_payload.get("one_line") or ""),
            str(brief_payload.get("why_it_matters") or ""),
            list(brief_payload.get("risk_notes", [])),
            "rule",
        )

    def create_event_deep_dive(self, event_id: str, *, force: bool = False, triggered_by: str = "dashboard") -> EventDeepDive:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            event["watchlisted"] = True
            event["ignored"] = False
            existing = self._find_deep_dive_for_event(state, event_id)
            if existing and not force and str(existing.get("status") or "") in {"ready", "partial"}:
                return EventDeepDive(**existing)

            resolved_evidence_pack = self._event_deep_dive_inputs(state, event)
            max_links = 12
            timeout_seconds = 12.0
            started_at = now_iso()
            sources: list[dict[str, Any]] = []
            for item in resolved_evidence_pack[:max_links]:
                sources.append(fetch_and_extract_link(item, timeout_seconds=timeout_seconds))

            success_sources = [item for item in sources if str(item.get("extract_status") or "") == "extracted"]
            failed_count = len([item for item in sources if str(item.get("extract_status") or "") != "extracted"])
            status = "ready" if success_sources and not failed_count else "partial" if success_sources else "failed"
            facts = self._generate_deep_dive_facts(event, success_sources)
            quotes: list[str] = []
            seen_quotes: set[str] = set()
            for item in success_sources:
                for quote in item.get("quotes", [])[:2]:
                    compact = str(quote).strip()
                    if not compact or compact in seen_quotes:
                        continue
                    seen_quotes.add(compact)
                    quotes.append(compact)
                    if len(quotes) >= 6:
                        break
                if len(quotes) >= 6:
                    break
            timeline = self._generate_deep_dive_timeline(event, resolved_evidence_pack)
            worth_to_brief, worth_reason = self._evaluate_worthiness(
                event,
                {"success_count": len(success_sources), "facts": facts, "quotes": quotes},
            )
            record = {
                "id": existing.get("id") if existing else f"dd-{uuid4().hex[:12]}",
                "event_id": event_id,
                "status": status,
                "started_at": started_at,
                "finished_at": now_iso(),
                "updated_at": now_iso(),
                "attempted_count": len(sources),
                "success_count": len(success_sources),
                "failed_count": failed_count,
                "resolved_evidence_pack": resolved_evidence_pack,
                "full_text_sources": success_sources,
                "sources": sources,
                "facts": facts,
                "quotes": quotes,
                "timeline": timeline,
                "worthiness": {"worth_to_brief": worth_to_brief, "reason": worth_reason},
                "last_error": None if success_sources else "没有拿到可用正文来源",
                "article_writing_guide": build_agent_article_writing_guide(),
            }
            if existing:
                index = next(
                    idx for idx, item in enumerate(state.get("event_deep_dives", []))
                    if isinstance(item, dict) and str(item.get("id") or "") == str(existing.get("id") or "")
                )
                state["event_deep_dives"][index] = record
            else:
                state.setdefault("event_deep_dives", []).insert(0, record)
            event["deep_dive_id"] = record["id"]
            self._append_log(
                state,
                "success" if success_sources else "warning",
                "deep_dive",
                f"已完成正文深挖：{event.get('title', '未命名事件')}",
                actor=triggered_by,
                detail=self._summarize_deep_dive(record),
            )
            self._write(state)
            return EventDeepDive(**record)

    def list_event_deep_dives(self) -> list[EventDeepDive]:
        state = self._read_live()
        items = [item for item in state.get("event_deep_dives", []) if isinstance(item, dict)]
        items.sort(key=lambda item: parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return [EventDeepDive(**item) for item in items]

    def get_event_deep_dive(self, event_id: str) -> EventDeepDive:
        state = self._read_live()
        record = self._find_deep_dive_for_event(state, event_id)
        if not record:
            raise ValueError(f"未找到事件正文深挖：{event_id}")
        if not record.get("article_writing_guide"):
            record["article_writing_guide"] = build_agent_article_writing_guide()
        return EventDeepDive(**record)

    def create_brief_from_event(self, event_id: str, *, triggered_by: str = "dashboard") -> BriefItem:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            deep_dive = self._find_deep_dive_for_event(state, event_id)
            if not deep_dive or str(deep_dive.get("status") or "") not in {"ready", "partial"}:
                deep_dive_result = self.create_event_deep_dive(event_id, triggered_by=triggered_by)
                deep_dive = deep_dive_result.model_dump()
                state = self._upgrade_state(self._read())
                event = self._find_event(state, event_id)
                deep_dive = self._find_deep_dive_for_event(state, event_id) or deep_dive
            deep_dive_status = str((deep_dive or {}).get("status") or "")
            if deep_dive_status not in {"ready", "partial"}:
                reason = str((deep_dive or {}).get("last_error") or "正文深挖尚未完成，暂时无法生成简报。")
                raise ValueError(reason)
            base_payload = build_rule_brief_payload(event, deep_dive)
            llm_service = self._make_llm_service(state)
            one_line, why_it_matters, risk_notes, brief_level = self._maybe_enhance_brief(llm_service, event, deep_dive, base_payload)
            full_text_sources = self._build_full_text_sources_for_ai(deep_dive)
            source_quotes: list[dict[str, str]] = []
            for item in deep_dive.get("sources", []):
                source_name = str(item.get("source_name") or "未知来源")
                for quote in item.get("quotes", [])[:1]:
                    compact = str(quote).strip()
                    if compact:
                        source_quotes.append({"source_name": source_name, "quote": compact})
            prompt_package_markdown = build_prompt_package_markdown(
                title=str(base_payload.get("title") or ""),
                one_line=one_line,
                why_it_matters=why_it_matters,
                facts=list(base_payload.get("facts", [])),
                full_text_sources=[
                    {
                        "source_name": str(item.get("source_name") or "未知来源"),
                        "title": str(item.get("title") or ""),
                        "full_text": str(item.get("cleaned_full_text") or ""),
                    }
                    for item in full_text_sources
                ],
                source_quotes=source_quotes[:4],
                timeline=list(base_payload.get("timeline", [])),
                risk_notes=risk_notes,
                source_links=list(base_payload.get("source_links", [])),
            )
            wechat_markdown = str(base_payload.get("wechat_markdown") or "")
            existing = self._find_brief_for_event(state, event_id)
            brief = {
                "id": existing.get("id") if existing else f"brief-{uuid4().hex[:12]}",
                "event_id": event_id,
                "deep_dive_id": str(deep_dive.get("id") or ""),
                "brief_level": brief_level,
                "stage": existing.get("stage") if existing else "prepared",
                "title": str(base_payload.get("title") or event.get("title") or ""),
                "one_line": one_line,
                "why_it_matters": why_it_matters,
                "facts": list(base_payload.get("facts", [])),
                "quotes": list(base_payload.get("quotes", [])),
                "timeline": list(base_payload.get("timeline", [])),
                "entity_names": list(base_payload.get("entity_names", [])),
                "source_links": list(base_payload.get("source_links", [])),
                "risk_notes": risk_notes,
                "prompt_package_markdown": prompt_package_markdown,
                "wechat_markdown": wechat_markdown,
                "wechat_html": _wechat_html(wechat_markdown),
                "wechat_target_id": existing.get("wechat_target_id") if existing else None,
                "wechat_editor_url": existing.get("wechat_editor_url") if existing else None,
                "wechat_remote_appmsg_id": existing.get("wechat_remote_appmsg_id") if existing else None,
                "preview_url": existing.get("preview_url") if existing else None,
                "last_error": None,
                "delivery_status": existing.get("delivery_status") if existing else "idle",
                "delivery_attempt_count": int(existing.get("delivery_attempt_count", 0) or 0) if existing else 0,
                "last_delivery_attempt_at": existing.get("last_delivery_attempt_at") if existing else None,
                "last_verified_at": existing.get("last_verified_at") if existing else None,
                "last_delivery_error_kind": existing.get("last_delivery_error_kind") if existing else None,
                "needs_resync": bool(existing.get("needs_resync")) if existing else False,
                "last_synced_revision": existing.get("last_synced_revision") if existing else None,
                "last_successful_upload_at": existing.get("last_successful_upload_at") if existing else None,
                "updated_at": now_iso(),
                "driver_label": str(existing.get("driver_label") or ""),
            }
            if existing:
                index = next(
                    idx for idx, item in enumerate(state.get("briefs", []))
                    if isinstance(item, dict) and str(item.get("id") or "") == str(existing.get("id") or "")
                )
                state["briefs"][index] = brief
            else:
                state.setdefault("briefs", []).insert(0, brief)
            event["brief_id"] = brief["id"]
            self._sync_llm_usage(state, llm_service)
            self._append_log(state, "success", "brief", f"已生成简报：{brief['title']}", actor=triggered_by)
            self._write(state)
            return BriefItem(**brief)

    def create_agent_article(self, payload: AgentArticlePayload) -> BriefItem:
        title = str(payload.title or "").strip()
        article_markdown = str(payload.article_markdown or "").strip()
        if not title:
            raise ValueError("文章标题不能为空。")
        if not article_markdown:
            raise ValueError("文章正文不能为空。")

        def dedupe_texts(values: list[str]) -> list[str]:
            result: list[str] = []
            seen: set[str] = set()
            for value in values:
                compact = re.sub(r"\s+", " ", str(value or "")).strip()
                if not compact or compact in seen:
                    continue
                seen.add(compact)
                result.append(compact)
            return result

        if payload.publish_to_wechat_draft:
            with self._lock:
                state = self._upgrade_state(self._read())
                self._ensure_agent_upload_allowed(state, actor=payload.triggered_by)

        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, payload.event_id)
            deep_dive = self._find_deep_dive_for_event(state, payload.event_id)
            if not deep_dive:
                self.create_event_deep_dive(payload.event_id, triggered_by=payload.triggered_by)
                state = self._upgrade_state(self._read())
                event = self._find_event(state, payload.event_id)
                deep_dive = self._find_deep_dive_for_event(state, payload.event_id)
            if not deep_dive:
                raise ValueError("未找到可关联的正文深挖记录，无法保存 AI 成稿。")

            facts = dedupe_texts(list(payload.facts))[:8]
            quotes = dedupe_texts(list(payload.quotes))[:6]
            timeline = dedupe_texts(list(payload.timeline))[:8]
            entity_names = dedupe_texts(list(payload.entity_names) or list(event.get("entity_names", [])))[:12]
            source_links = dedupe_texts(
                list(payload.source_links)
                or [
                    str(item.get("canonical_link") or item.get("original_link") or "").strip()
                    for item in deep_dive.get("sources", [])
                    if isinstance(item, dict)
                ]
            )[:12]
            risk_notes = dedupe_texts(list(payload.risk_notes))[:6]
            one_line = str(payload.one_line or "").strip()
            why_it_matters = str(payload.why_it_matters or "").strip()
            if not one_line:
                one_line = facts[0] if facts else (str(event.get("summary") or "").strip() or title)
            if not why_it_matters:
                why_it_matters = str(deep_dive.get("worthiness", {}).get("reason") or "").strip()
            if not why_it_matters:
                why_it_matters = f"该事件当前处于 {event.get('alert_state') or '观察'} 阶段，且已具备可发布价值。"

            full_text_sources = self._build_full_text_sources_for_ai(deep_dive, limit=4)
            source_quotes: list[dict[str, str]] = []
            for item in deep_dive.get("sources", []):
                if not isinstance(item, dict):
                    continue
                source_name = str(item.get("source_name") or "未知来源").strip() or "未知来源"
                for quote in item.get("quotes", [])[:1]:
                    compact = str(quote or "").strip()
                    if compact:
                        source_quotes.append({"source_name": source_name, "quote": compact})
            prompt_package_markdown = (
                build_prompt_package_markdown(
                    title=title,
                    one_line=one_line,
                    why_it_matters=why_it_matters,
                    facts=facts,
                    full_text_sources=[
                        {
                            "source_name": str(item.get("source_name") or "未知来源"),
                            "title": str(item.get("title") or ""),
                            "full_text": str(item.get("cleaned_full_text") or ""),
                        }
                        for item in full_text_sources
                    ],
                    source_quotes=source_quotes[:4],
                    timeline=timeline,
                    risk_notes=risk_notes,
                    source_links=source_links,
                )
                + "\n\n## AI 成稿正文\n"
                + article_markdown
            ).strip()

            existing = self._find_brief_record_for_event_by_level(state, payload.event_id, brief_level="article")
            existing_revision = self._brief_revision(existing) if existing else None
            brief_id = str(existing.get("id") or "") if existing else f"brief-{uuid4().hex[:12]}"
            brief = {
                "id": brief_id,
                "event_id": payload.event_id,
                "deep_dive_id": str(deep_dive.get("id") or ""),
                "brief_level": "article",
                "stage": existing.get("stage") if existing else "prepared",
                "title": title,
                "one_line": one_line,
                "why_it_matters": why_it_matters,
                "facts": facts,
                "quotes": quotes,
                "timeline": timeline,
                "entity_names": entity_names,
                "source_links": source_links,
                "risk_notes": risk_notes,
                "prompt_package_markdown": prompt_package_markdown,
                "wechat_markdown": article_markdown,
                "wechat_html": _wechat_html(article_markdown),
                "wechat_target_id": existing.get("wechat_target_id") if existing else build_wechat_target_id(brief_id),
                "wechat_editor_url": existing.get("wechat_editor_url") if existing else None,
                "wechat_remote_appmsg_id": existing.get("wechat_remote_appmsg_id") if existing else None,
                "preview_url": existing.get("preview_url") if existing else build_preview_url(brief_id),
                "last_error": None,
                "delivery_status": existing.get("delivery_status") if existing else "idle",
                "delivery_attempt_count": int(existing.get("delivery_attempt_count", 0) or 0) if existing else 0,
                "last_delivery_attempt_at": existing.get("last_delivery_attempt_at") if existing else None,
                "last_verified_at": existing.get("last_verified_at") if existing else None,
                "last_delivery_error_kind": existing.get("last_delivery_error_kind") if existing else None,
                "needs_resync": bool(existing.get("needs_resync")) if existing else False,
                "last_synced_revision": existing.get("last_synced_revision") if existing else None,
                "last_successful_upload_at": existing.get("last_successful_upload_at") if existing else None,
                "updated_at": now_iso(),
                "driver_label": str(payload.driver_label or "").strip(),
            }
            if not brief.get("wechat_target_id"):
                brief["wechat_target_id"] = build_wechat_target_id(brief_id)
            if not brief.get("preview_url"):
                brief["preview_url"] = build_preview_url(brief_id)
            next_revision = self._brief_revision(brief)
            revision_changed = existing_revision != next_revision
            if existing and not revision_changed:
                brief["stage"] = existing.get("stage") or "prepared"
                brief["delivery_status"] = existing.get("delivery_status") or "idle"
                brief["needs_resync"] = bool(existing.get("needs_resync"))
                brief["last_synced_revision"] = existing.get("last_synced_revision")
                brief["last_successful_upload_at"] = existing.get("last_successful_upload_at")
                brief["last_verified_at"] = existing.get("last_verified_at")
                brief["last_delivery_error_kind"] = existing.get("last_delivery_error_kind")
                brief["last_error"] = existing.get("last_error")
            elif existing:
                brief["stage"] = "prepared"
                brief["delivery_status"] = "idle"
                brief["needs_resync"] = bool(existing.get("last_synced_revision") or existing.get("wechat_editor_url"))
                brief["last_synced_revision"] = None
                brief["last_successful_upload_at"] = None
                brief["last_verified_at"] = None
                brief["last_delivery_error_kind"] = None
                brief["last_error"] = None

            if existing:
                index = next(
                    idx for idx, item in enumerate(state.get("briefs", []))
                    if isinstance(item, dict) and str(item.get("id") or "") == str(existing.get("id") or "")
                )
                state["briefs"][index] = brief
            else:
                state.setdefault("briefs", []).insert(0, brief)
            self._append_log(
                state,
                "success",
                "brief",
                f"已保存 AI 成稿：{title}",
                actor=payload.triggered_by,
                detail=f"driver={payload.driver_label} | publish_to_wechat_draft={payload.publish_to_wechat_draft}",
            )
            self._write(state)

        if payload.publish_to_wechat_draft:
            return self.sync_brief_wechat_draft(brief_id, triggered_by=payload.triggered_by)
        return BriefItem(**brief)

    def _ensure_agent_upload_allowed(self, state: dict[str, Any], actor: str = "agent") -> None:
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
        control_state = str(runtime.get("control_state") or "stopped")
        run_status = str(run.get("status") or "idle")
        current_cycle = str(runtime.get("current_cycle") or "idle")
        scheduler_running = bool(runtime.get("scheduler_running"))
        scheduler_active = scheduler_running or control_state in {"armed", "waiting", "running"} or (
            run_status == "running" and not self._runtime_run_is_stale(run)
        )
        if not scheduler_active:
            return
        message = "当前自动调度器正在运行，请先停止传统模式，再执行 Agent 上传微信草稿箱。"
        self._append_log(
            state,
            "warning",
            "wechat",
            message,
            stream="business_event",
            actor=actor,
            detail=f"control_state={control_state} | run_status={run_status} | current_cycle={current_cycle}",
        )
        self._write(state)
        raise ValueError(message)

    def _paginate_items(
        self,
        items: list[Any],
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Any], int, int, int, bool]:
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 50), 200))
        total = len(items)
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return items[start:end], total, safe_page, safe_page_size, end < total

    def list_briefs(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        stage: str = "all",
        q: str = "",
    ) -> tuple[list[BriefItem], int, int, int, bool, BriefStageCounts]:
        state = self._read_live()
        items = [item for item in state.get("briefs", []) if isinstance(item, dict)]
        items.sort(key=lambda item: parse_time(item.get("updated_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        stage_counts = BriefStageCounts(
            all=len(items),
            prepared=sum(1 for item in items if str(item.get("stage") or "") == "prepared"),
            synced=sum(1 for item in items if str(item.get("stage") or "") == "synced"),
            failed=sum(
                1
                for item in items
                if str(item.get("stage") or "") == "failed" or bool(str(item.get("last_error") or "").strip())
            ),
        )
        stage_filter = str(stage or "all").strip().lower()
        keyword = str(q or "").strip().lower()

        def matches_stage(item: dict[str, Any]) -> bool:
            if stage_filter == "all":
                return True
            if stage_filter == "prepared":
                return str(item.get("stage") or "") == "prepared"
            if stage_filter == "synced":
                return str(item.get("stage") or "") == "synced"
            if stage_filter == "failed":
                return str(item.get("stage") or "") == "failed" or bool(str(item.get("last_error") or "").strip())
            return True

        def matches_query(item: dict[str, Any]) -> bool:
            if not keyword:
                return True
            haystack = "\n".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("one_line") or ""),
                    str(item.get("why_it_matters") or ""),
                ]
            ).lower()
            return keyword in haystack

        filtered = [item for item in items if matches_stage(item) and matches_query(item)]
        page_items, total, safe_page, safe_page_size, has_more = self._paginate_items(
            filtered,
            page=page,
            page_size=page_size,
        )
        return [BriefItem(**item) for item in page_items], total, safe_page, safe_page_size, has_more, stage_counts

    def get_brief(self, brief_id: str) -> BriefItem:
        state = self._read_live()
        return BriefItem(**self._find_brief(state, brief_id))

    def _brief_revision(self, brief: dict[str, Any]) -> str:
        stable_payload = {
            "title": str(brief.get("title") or "").strip(),
            "one_line": str(brief.get("one_line") or "").strip(),
            "why_it_matters": str(brief.get("why_it_matters") or "").strip(),
            "facts": list(brief.get("facts", [])),
            "quotes": list(brief.get("quotes", [])),
            "timeline": list(brief.get("timeline", [])),
            "risk_notes": list(brief.get("risk_notes", [])),
            "source_links": list(brief.get("source_links", [])),
            "wechat_markdown": str(brief.get("wechat_markdown") or ""),
            "wechat_html": str(brief.get("wechat_html") or ""),
        }
        digest = hashlib.sha256(
            json.dumps(stable_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return f"brief:{brief.get('id') or 'unknown'}:{digest}"

    def _brief_transition(
        self,
        current_stage: str,
        current_delivery_status: str,
        *,
        upload_success: bool,
        is_session_level_error: bool,
        verify_status: str,
    ) -> dict[str, Any]:
        result = {
            "new_stage": current_stage or "prepared",
            "new_delivery_status": current_delivery_status or "idle",
            "last_delivery_error_kind": None,
            "should_set_needs_resync": False,
            "should_clear_last_synced_revision": False,
        }
        if not upload_success:
            result["new_stage"] = "failed"
            result["new_delivery_status"] = "check_failed" if is_session_level_error else "idle"
            result["last_delivery_error_kind"] = "session" if is_session_level_error else "upload"
            result["should_set_needs_resync"] = False
            result["should_clear_last_synced_revision"] = True
            return result

        result["new_stage"] = "synced"
        if verify_status == "verified":
            result["new_delivery_status"] = "verified"
            result["last_delivery_error_kind"] = None
        elif verify_status == "target_missing":
            result["new_stage"] = "prepared"
            result["new_delivery_status"] = "target_missing"
            result["last_delivery_error_kind"] = "target_missing"
            result["should_clear_last_synced_revision"] = True
        elif verify_status == "scrape_failed":
            result["new_delivery_status"] = "check_failed"
            result["last_delivery_error_kind"] = "scrape_failed"
        elif verify_status == "check_failed":
            result["new_delivery_status"] = "check_failed"
            result["last_delivery_error_kind"] = "check_failed"
        else:
            result["new_delivery_status"] = "uploaded_unverified"
            result["last_delivery_error_kind"] = None
        return result

    def sync_brief_wechat_draft(self, brief_id: str, triggered_by: str = "dashboard") -> BriefItem:
        with self._lock:
            state = self._upgrade_state(self._read())
            if triggered_by == "agent":
                self._ensure_agent_upload_allowed(state, actor=triggered_by)
            brief = self._find_brief(state, brief_id)
            if triggered_by == "agent" and str(brief.get("brief_level") or "rule") != "article":
                raise ValueError("Agent 模式禁止上传传统简报，请使用 /api/admin/agent/articles 保存并上传长文。")
            current_revision = self._brief_revision(brief)
            already_synced_same_revision = (
                str(brief.get("stage") or "") == "synced"
                and not bool(brief.get("needs_resync"))
                and str(brief.get("last_synced_revision") or "").strip()
                and str(brief.get("last_synced_revision") or "").strip() == current_revision
            )
            if already_synced_same_revision:
                message = "该版本简报已同步到微信草稿箱，无需重复上传。"
                state["publish_tasks"].insert(
                    0,
                    create_publish_task(
                        brief_id,
                        "sync_wechat_draft",
                        "completed",
                        message,
                        triggered_by,
                        str(state["channels"]["wechat"]["selectors_version"]),
                        step_logs=["命中手动同步幂等保护，跳过重复上传。"],
                    ),
                )
                self._append_log(
                    state,
                    "info",
                    "wechat",
                    f"{message}{brief['title']}",
                    detail=current_revision,
                )
                self._write(state)
                return BriefItem(**brief)
            if not brief.get("wechat_target_id"):
                brief["wechat_target_id"] = build_wechat_target_id(str(brief["id"]))
            brief["preview_url"] = build_preview_url(str(brief["id"]))
            brief["last_delivery_attempt_at"] = now_iso()
            brief["delivery_attempt_count"] = int(brief.get("delivery_attempt_count", 0) or 0) + 1
            brief["needs_resync"] = False
            browser = self._refresh_browser_session(state)
            browser_payload = {
                **brief,
                "summary": str(brief.get("one_line") or ""),
                "markdown": str(brief.get("wechat_markdown") or ""),
            }
            browser, artifacts, step_logs = run_browser_action("sync_wechat_draft", browser_payload, state["channels"]["wechat"], browser)
            state["browser"]["wechat"] = browser
            verification_status = str(browser.get("verification_status") or "").strip()
            verification_message = str(browser.get("verification_message") or "").strip()
            transition = self._brief_transition(
                str(brief.get("stage") or "prepared"),
                str(brief.get("delivery_status") or "idle"),
                upload_success=not bool(browser.get("last_error")),
                is_session_level_error=bool(browser.get("is_session_level_error")),
                verify_status=verification_status,
            )
            brief["stage"] = transition["new_stage"]
            brief["delivery_status"] = transition["new_delivery_status"]
            brief["last_delivery_error_kind"] = transition["last_delivery_error_kind"]
            brief["needs_resync"] = bool(transition["should_set_needs_resync"])
            if transition["should_clear_last_synced_revision"]:
                brief["last_synced_revision"] = None
                brief["last_successful_upload_at"] = None

            if browser.get("last_error"):
                brief["last_error"] = str(browser.get("last_error"))
            else:
                existing_editor_url = str(brief.get("wechat_editor_url") or "").strip()
                existing_remote_appmsg_id = str(brief.get("wechat_remote_appmsg_id") or "").strip()
                resolved_editor_url = (
                    browser.get("last_verified_remote_url")
                    or browser.get("last_synced_editor_url")
                    or existing_editor_url
                )
                resolved_remote_appmsg_id = (
                    browser.get("last_verified_remote_appmsg_id")
                    or extract_wechat_appmsg_id(str(browser.get("last_synced_editor_url") or ""))
                    or existing_remote_appmsg_id
                )
                if resolved_editor_url:
                    brief["wechat_editor_url"] = str(resolved_editor_url)
                if resolved_remote_appmsg_id:
                    brief["wechat_remote_appmsg_id"] = str(resolved_remote_appmsg_id)
                if verification_status == "target_missing":
                    brief["stage"] = "prepared"
                    brief["delivery_status"] = "target_missing"
                    brief["wechat_editor_url"] = None
                    brief["wechat_remote_appmsg_id"] = None
                    brief["last_synced_revision"] = None
                    brief["last_successful_upload_at"] = None
                    brief["last_error"] = verification_message or "已上传，但远端草稿箱未确认到目标稿件，回退为 prepared。"
                elif verification_status in {"verification_failed", "check_failed", "scrape_failed"}:
                    brief["last_error"] = verification_message or "已上传，但草稿箱确认未完成。"
                    brief["last_synced_revision"] = None
                    brief["last_successful_upload_at"] = None
                else:
                    brief["last_error"] = None
                    brief["last_synced_revision"] = self._brief_revision(brief)
                    brief["last_successful_upload_at"] = now_iso()
                if verification_status == "verified":
                    brief["last_verified_at"] = now_iso()
            brief["updated_at"] = now_iso()
            task_status = "completed" if brief["stage"] == "synced" else "failed"
            if brief["stage"] == "synced":
                if verification_status == "verified":
                    task_message = "已同步简报到微信草稿箱，并确认目标稿件存在。"
                elif verification_status == "target_missing":
                    task_message = "已同步简报到微信草稿箱，但正式草稿箱暂未确认到目标稿件。"
                elif verification_status in {"verification_failed", "check_failed", "scrape_failed"}:
                    task_message = "已同步简报到微信草稿箱，但草稿箱检查失败，当前保留已上传状态。"
                else:
                    task_message = "已同步简报到微信草稿箱。"
            else:
                task_message = "简报同步微信草稿箱失败。"
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    brief_id,
                    "sync_wechat_draft",
                    task_status,
                    task_message,
                    triggered_by,
                    str(state["channels"]["wechat"]["selectors_version"]),
                    artifacts=artifacts,
                    step_logs=step_logs,
                ),
            )
            self._append_log(
                state,
                "success" if brief["stage"] == "synced" else "warning",
                "wechat",
                f"{task_message.rstrip('。')}：{brief['title']}",
                detail=brief.get("last_error"),
            )
            self._write(state)
            return BriefItem(**brief)

    def build_brief_copy_package(self, brief_id: str) -> str:
        state = self._upgrade_state(self._read())
        brief = self._find_brief(state, brief_id)
        return str(brief.get("prompt_package_markdown") or "")

    def list_publish_tasks(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PublishTask], int, int, int, bool]:
        state = self._read_live()
        visible_actions = {"sync_wechat_draft", "delete_wechat_draft", "delete_brief"}
        items = [
            item for item in state["publish_tasks"]
            if isinstance(item, dict) and str(item.get("action") or "") in visible_actions
        ]
        page_items, total, safe_page, safe_page_size, has_more = self._paginate_items(
            items,
            page=page,
            page_size=page_size,
        )
        return [PublishTask(**item) for item in page_items], total, safe_page, safe_page_size, has_more

    def _build_wechat_mapping_snapshot(self, state: dict[str, Any]) -> WeChatMappingSnapshot:
        browser = state.get("browser", {}).get("wechat", {})
        last_check = browser.get("last_draft_check") if isinstance(browser, dict) and isinstance(browser.get("last_draft_check"), dict) else {}
        remote_items = last_check.get("items", [])
        if not isinstance(remote_items, list):
            remote_items = []

        def normalize_title(value: Any) -> str:
            return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip().lower()

        def title_matches(left: str, right: str) -> bool:
            if not left or not right:
                return False
            if left == right:
                return True
            shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
            if len(shorter) >= 18 and longer.startswith(shorter):
                return True
            if len(shorter) >= 18 and shorter in longer:
                return True
            return False

        mapping_rows: list[WeChatMappingRow] = []
        matched_brief_ids: set[str] = set()
        remote_index: dict[str, dict[str, Any]] = {}
        remote_key_index: dict[str, dict[str, Any]] = {}
        for item in remote_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            remote_key = str(item.get("remote_key") or "").strip() or build_remote_draft_key(
                title,
                str(item.get("url") or "").strip(),
                str(item.get("appmsg_id") or "").strip() or None,
                str(item.get("updated_at") or "").strip() or None,
                len(remote_key_index),
            )
            appmsg_id = str(item.get("appmsg_id") or "").strip() or None
            url = str(item.get("url") or "").strip()
            remote_index[f"title:{normalize_title(title)}"] = item
            remote_key_index[remote_key] = item
            if appmsg_id:
                remote_index[f"appmsg:{appmsg_id}"] = item
            if url:
                remote_index[f"url:{url}"] = item

        for item in remote_items:
            if not isinstance(item, dict):
                continue
            remote_title = str(item.get("title") or "").strip()
            remote_key = str(item.get("remote_key") or "").strip() or build_remote_draft_key(
                remote_title,
                str(item.get("url") or "").strip(),
                str(item.get("appmsg_id") or "").strip() or None,
                str(item.get("updated_at") or "").strip() or None,
                len(mapping_rows),
            )
            remote_appmsg_id = str(item.get("appmsg_id") or "").strip() or None
            remote_url = str(item.get("url") or "").strip()
            remote_updated_at = str(item.get("updated_at") or "").strip() or None
            matched_brief: dict[str, Any] | None = None
            for brief in state.get("briefs", []):
                if not isinstance(brief, dict):
                    continue
                brief_id = str(brief.get("id") or "")
                if brief_id in matched_brief_ids:
                    continue
                brief_remote_id = str(brief.get("wechat_remote_appmsg_id") or "").strip()
                brief_remote_url = str(brief.get("wechat_editor_url") or "").strip()
                brief_title = normalize_title(brief.get("title"))
                if remote_appmsg_id and brief_remote_id == remote_appmsg_id:
                    matched_brief = brief
                    break
                if remote_url and brief_remote_url == remote_url:
                    matched_brief = brief
                    break
                if remote_title and brief_title and title_matches(brief_title, normalize_title(remote_title)):
                    matched_brief = brief
                    break
            if matched_brief:
                matched_brief_ids.add(str(matched_brief.get("id") or ""))
                mapping_rows.append(
                    WeChatMappingRow(
                        remote_title=remote_title,
                        remote_key=remote_key,
                        remote_appmsg_id=remote_appmsg_id,
                        remote_url=remote_url,
                        remote_updated_at=remote_updated_at,
                        local_brief_id=str(matched_brief.get("id") or "") or None,
                        local_brief_title=str(matched_brief.get("title") or "") or None,
                        local_stage=str(matched_brief.get("stage") or "") or None,
                        mapping_status="matched",
                    )
                )
            else:
                mapping_rows.append(
                    WeChatMappingRow(
                        remote_title=remote_title,
                        remote_key=remote_key,
                        remote_appmsg_id=remote_appmsg_id,
                        remote_url=remote_url,
                        remote_updated_at=remote_updated_at,
                        mapping_status="remote_only",
                    )
                )

        for brief in state.get("briefs", []):
            if not isinstance(brief, dict):
                continue
            brief_id = str(brief.get("id") or "")
            if brief_id in matched_brief_ids:
                continue
            if str(brief.get("stage") or "") == "synced":
                mapping_rows.append(
                    WeChatMappingRow(
                        remote_title=str(brief.get("title") or ""),
                        remote_key=build_remote_draft_key(
                            str(brief.get("title") or ""),
                            str(brief.get("wechat_editor_url") or ""),
                            str(brief.get("wechat_remote_appmsg_id") or "") or None,
                            None,
                        ),
                        remote_appmsg_id=str(brief.get("wechat_remote_appmsg_id") or "") or None,
                        remote_url=str(brief.get("wechat_editor_url") or ""),
                        local_brief_id=brief_id,
                        local_brief_title=str(brief.get("title") or "") or None,
                        local_stage=str(brief.get("stage") or "") or None,
                        mapping_status="local_only",
                    )
                )

        matched_count = len([row for row in mapping_rows if row.mapping_status == "matched"])
        missing_count = len([row for row in mapping_rows if row.mapping_status == "local_only"])
        return WeChatMappingSnapshot(
            checked_at=last_check.get("checked_at"),
            remote_count=int(last_check.get("remote_count", len(remote_items)) or 0),
            matched_count=matched_count,
            missing_count=missing_count,
            message=str(last_check.get("message") or ""),
            items=[WeChatRemoteDraftItem(**item) for item in remote_items if isinstance(item, dict)],
            mapping_rows=mapping_rows,
        )

    def get_wechat_mapping(self) -> WeChatMappingSnapshot:
        state = self._read_live()
        return self._build_wechat_mapping_snapshot(state)

    def refresh_wechat_mapping(self, triggered_by: str = "dashboard") -> WeChatMappingSnapshot:
        self.check_wechat_draft_box(triggered_by=triggered_by)
        latest_state = self._upgrade_state(self._read())
        return self._build_wechat_mapping_snapshot(latest_state)

    def delete_wechat_remote_draft(self, remote_id: str, triggered_by: str = "mapping") -> DictOkResponse:
        state = self._upgrade_state(self._read())
        mapping = self._build_wechat_mapping_snapshot(state)
        remote_key = str(remote_id or "").strip()
        target_row = next(
            (
                row for row in mapping.mapping_rows
                if str(row.remote_key or "") == remote_key
                or str(row.remote_appmsg_id or "") == remote_key
                or str(row.remote_url or "") == remote_key
            ),
            None,
        )
        if not target_row:
            for row in mapping.mapping_rows:
                if not row.local_brief_id:
                    continue
                try:
                    brief = self._find_brief(state, str(row.local_brief_id))
                except ValueError:
                    continue
                brief_remote_id = str(brief.get("wechat_remote_appmsg_id") or "").strip()
                brief_remote_url = str(brief.get("wechat_editor_url") or "").strip()
                if brief_remote_id == remote_key or brief_remote_url == remote_key:
                    target_row = row
                    break
        if not target_row:
            raise ValueError("未找到对应的远端草稿映射。")

        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = delete_wechat_remote_draft(
            {
                "appmsg_id": target_row.remote_appmsg_id,
                "url": target_row.remote_url,
                "title": target_row.remote_title,
            },
            state["channels"]["wechat"],
            browser,
        )
        state["browser"]["wechat"] = browser
        status = "completed" if not browser.get("last_error") else "failed"
        message = "已删除微信草稿箱远端草稿。" if status == "completed" else "删除微信草稿箱远端草稿失败。"
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                str(target_row.local_brief_id or remote_id),
                "delete_wechat_draft",
                status,
                message,
                triggered_by,
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._append_log(
            state,
            "success" if status == "completed" else "warning",
            "wechat",
            f"{message}{target_row.remote_title}",
            detail=str(browser.get("last_error") or ""),
        )
        self._write(state)
        if status == "completed":
            self.check_wechat_draft_box()
            return DictOkResponse(ok=True, message="已删除远端草稿并刷新映射。")
        raise ValueError(str(browser.get("last_error") or "远端草稿删除失败。"))

    def delete_brief(self, brief_id: str, remote: str = "auto", triggered_by: str = "briefs") -> DictOkResponse:
        state = self._upgrade_state(self._read())
        brief = self._find_brief(state, brief_id)
        should_delete_remote = False
        if remote == "true":
            should_delete_remote = True
        elif remote == "auto":
            should_delete_remote = str(brief.get("stage") or "") == "synced"
        if should_delete_remote:
            remote_id = str(brief.get("wechat_remote_appmsg_id") or brief.get("wechat_editor_url") or "").strip()
            if not remote_id:
                raise ValueError("该简报缺少远端草稿标识，无法删除微信草稿。")
            self.delete_wechat_remote_draft(remote_id, triggered_by=triggered_by)
            state = self._upgrade_state(self._read())
            brief = self._find_brief(state, brief_id)
            if str(brief.get("stage") or "") == "synced":
                raise ValueError("远端草稿删除后，本地状态尚未完成回写，请稍后重试。")

        briefs = [item for item in state.get("briefs", []) if not (isinstance(item, dict) and str(item.get("id") or "") == brief_id)]
        state["briefs"] = briefs
        for event in state.get("intel_events", []):
            if isinstance(event, dict) and str(event.get("brief_id") or "") == brief_id:
                event["brief_id"] = None
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                brief_id,
                "delete_brief",
                "completed",
                "已删除本地简报。",
                triggered_by,
                str(state["channels"]["wechat"]["selectors_version"]),
            ),
        )
        self._append_log(state, "success", "brief", f"已删除本地简报：{brief.get('title') or brief_id}")
        self._write(state)
        return DictOkResponse(ok=True, message="已删除本地简报。")

    def get_wechat_config(self) -> WeChatChannelConfig:
        config = self._upgrade_user_settings(self._read_config())
        return WeChatChannelConfig(**ensure_channel_defaults(config.get("wechat", {})))

    def update_wechat_config(self, payload: ChannelConfigPayload) -> WeChatChannelConfig:
        state = self._upgrade_state(self._read())
        state["channels"]["wechat"].update(payload.model_dump())
        state["channels"]["wechat"] = ensure_channel_defaults(state["channels"]["wechat"])
        config = self._read_config()
        config["wechat"] = deepcopy_json(state["channels"]["wechat"])
        WECHAT_BROWSER_MANAGER.reset("wechat_config_updated")
        self._refresh_browser_session(state)
        self._append_log(state, "success", "channel", "已更新微信公众号配置。")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return WeChatChannelConfig(**state["channels"]["wechat"])

    def get_browser_session(self) -> BrowserSessionState:
        state = self._read_live()
        browser = self._refresh_browser_session(state)
        self._write(state)
        return BrowserSessionState(**browser)

    def update_browser_session(self, payload: BrowserSessionPayload) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        state["channels"]["wechat"]["browser_name"] = payload.browser_name
        state["channels"]["wechat"]["browser_profile_path"] = payload.user_data_dir
        state["channels"]["wechat"] = ensure_channel_defaults(state["channels"]["wechat"])
        config = self._read_config()
        config.setdefault("wechat", {})
        config["wechat"]["browser_name"] = state["channels"]["wechat"]["browser_name"]
        config["wechat"]["browser_profile_path"] = state["channels"]["wechat"]["browser_profile_path"]
        WECHAT_BROWSER_MANAGER.reset("browser_session_updated")
        browser = self._refresh_browser_session(state)
        self._append_log(state, "info", "browser", "已刷新浏览器会话配置。")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return BrowserSessionState(**browser)

    def open_browser_dashboard(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = launch_wechat_dashboard(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "info",
            "browser",
            "已打开公众号后台登录窗口。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[:3]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "open_dashboard",
                "completed" if not browser.get("last_error") else "failed",
                "已打开公众号后台登录窗口。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def check_browser_session(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = inspect_wechat_session(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "success" if browser.get("logged_in") else "warning",
            "browser",
            "已完成公众号浏览器会话检查。" if browser.get("logged_in") else "公众号浏览器会话未通过检查。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-2:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "check_browser",
                "completed" if browser.get("logged_in") else "blocked",
                "已完成浏览器会话检查。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def check_wechat_draft_box(self, triggered_by: str = "dashboard") -> WeChatDraftSyncCheckResult:
        with self._lock:
            state = self._upgrade_state(self._read())
            browser = self._refresh_browser_session(state)
            previous_check = browser.get("last_draft_check") if isinstance(browser.get("last_draft_check"), dict) else {}
            browser, artifacts, step_logs, remote_items = inspect_wechat_draft_box(state["channels"]["wechat"], browser)
            state["browser"]["wechat"] = browser

            matched_count = 0
            missing_count = 0
            diff_logs: list[str] = []
            last_check = previous_check
            empty_confirmations = int(last_check.get("empty_confirmations", 0) or 0)
            empty_confirmed = False
            if not browser.get("last_error"):
                def normalize_title(value: Any) -> str:
                    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip().lower()

                def title_matches(left: str, right: str) -> bool:
                    if not left or not right:
                        return False
                    if left == right:
                        return True
                    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
                    if len(shorter) >= 18 and longer.startswith(shorter):
                        return True
                    if len(shorter) >= 18 and shorter in longer:
                        return True
                    return False

                remote_index: dict[str, dict[str, str | None]] = {}
                remote_titles: list[tuple[str, dict[str, str | None]]] = []
                matched_remote_titles: set[str] = set()
                for item in remote_items:
                    url = str(item.get("url") or "").strip()
                    appmsg_id = str(item.get("appmsg_id") or "").strip()
                    title = normalize_title(item.get("title"))
                    if url:
                        remote_index[url] = item
                    if appmsg_id:
                        remote_index[f"appmsg:{appmsg_id}"] = item
                    if title:
                        remote_titles.append((title, item))

                if remote_items:
                    empty_confirmations = 0
                else:
                    empty_confirmations += 1
                    empty_confirmed = empty_confirmations >= 3
                    step_logs.append(f"远端草稿箱为空候选，第 {empty_confirmations}/3 次。")

                for brief in state.get("briefs", []):
                    if not isinstance(brief, dict):
                        continue
                    previous_synced = str(brief.get("stage") or "") == "synced"
                    remote_match = None
                    remote_appmsg_id = str(brief.get("wechat_remote_appmsg_id") or "").strip()
                    remote_url = str(brief.get("wechat_editor_url") or "").strip()
                    brief_title = normalize_title(brief.get("title"))
                    if remote_appmsg_id:
                        remote_match = remote_index.get(f"appmsg:{remote_appmsg_id}")
                    if not remote_match and remote_url:
                        remote_match = remote_index.get(remote_url)
                    if not remote_match and brief_title:
                        for candidate_title, candidate_item in remote_titles:
                            if title_matches(candidate_title, brief_title):
                                remote_match = candidate_item
                                break

                    if remote_match:
                        matched_count += 1
                        brief["stage"] = "synced"
                        brief["delivery_status"] = "verified"
                        matched_title = normalize_title(remote_match.get("title"))
                        if matched_title:
                            matched_remote_titles.add(matched_title)
                        remote_match_url = str(remote_match.get("url") or "").strip()
                        remote_match_appmsg_id = str(remote_match.get("appmsg_id") or "").strip()
                        if remote_match_url:
                            brief["wechat_editor_url"] = remote_match_url
                        if remote_match_appmsg_id:
                            brief["wechat_remote_appmsg_id"] = remote_match_appmsg_id
                        brief["last_error"] = None
                        brief["last_delivery_error_kind"] = None
                        brief["last_verified_at"] = now_iso()
                        brief["updated_at"] = now_iso()
                        diff_logs.append(f"=远端草稿 \"{brief.get('title') or '未命名简报'}\" 状态无变化")
                        continue

                    entered_formal_draft_box = any("已进入草稿箱页面" in log for log in step_logs)
                    scraped_formal_draft_box = any("共读取到" in log for log in step_logs)
                    if previous_synced and entered_formal_draft_box and scraped_formal_draft_box and (remote_items or empty_confirmed):
                        missing_count += 1
                        brief["stage"] = "prepared"
                        brief["delivery_status"] = "target_missing"
                        brief["wechat_editor_url"] = None
                        brief["wechat_remote_appmsg_id"] = None
                        brief["preview_url"] = None
                        brief["last_error"] = "微信草稿箱中未找到对应草稿，可能已被删除。"
                        brief["last_delivery_error_kind"] = "target_missing"
                        brief["last_synced_revision"] = None
                        brief["last_successful_upload_at"] = None
                        brief["updated_at"] = now_iso()
                        diff_logs.append(f"-远端草稿 \"{brief.get('title') or '未命名简报'}\" 已消失，本地 {brief.get('id') or 'brief'} 回退为 prepared")

                local_titles = {
                    normalize_title(brief.get("title"))
                    for brief in state.get("briefs", [])
                    if isinstance(brief, dict) and normalize_title(brief.get("title"))
                }
                for candidate_title, _candidate_item in remote_titles:
                    if candidate_title in matched_remote_titles:
                        continue
                    if candidate_title not in local_titles:
                        diff_logs.append(f"+新增远端草稿 \"{candidate_title}\"（未匹配本地简报）")

            if remote_items:
                message = (
                    f"已检查微信草稿箱，共读取 {len(remote_items)} 条远端草稿；"
                    f"匹配本地简报 {matched_count} 条，发现缺失 {missing_count} 条。"
                )
            else:
                if empty_confirmed:
                    message = (
                        "已检查微信草稿箱，当前远端草稿为 0 条；"
                        f"匹配本地简报 {matched_count} 条，发现缺失 {missing_count} 条。"
                    )
                else:
                    message = (
                        f"已检查微信草稿箱，本次读取到 0 条远端草稿，正在做空列表确认（{empty_confirmations}/3）；"
                        f"当前先保留本地已同步状态。"
                    )
            if browser.get("last_error"):
                previous_items = previous_check.get("items", []) if isinstance(previous_check.get("items"), list) else []
                preserved_remote_count = int(previous_check.get("remote_count", len(previous_items)) or 0)
                preserved_matched = int(previous_check.get("matched_count", 0) or 0)
                preserved_missing = int(previous_check.get("missing_count", 0) or 0)
                fallback_message = (
                    f"本次检查失败，当前展示最近一次成功读取结果：远端 {preserved_remote_count} 条，"
                    f"已匹配 {preserved_matched} 条，待核对 {preserved_missing} 条。"
                )
                result_payload = {
                    "checked_at": now_iso(),
                    "remote_count": preserved_remote_count,
                    "matched_count": preserved_matched,
                    "missing_count": preserved_missing,
                    "items": previous_items[:30],
                    "message": fallback_message if previous_items else str(browser.get("last_error") or "微信草稿箱检查失败。"),
                    "empty_confirmations": int(previous_check.get("empty_confirmations", 0) or 0),
                }
                for brief in state.get("briefs", []):
                    if not isinstance(brief, dict):
                        continue
                    if str(brief.get("stage") or "") == "synced":
                        brief["delivery_status"] = "check_failed"
                        brief["last_delivery_error_kind"] = "check_failed"
            else:
                result_payload = {
                    "checked_at": now_iso(),
                    "remote_count": len(remote_items),
                    "matched_count": matched_count,
                    "missing_count": missing_count,
                    "items": remote_items[:30],
                    "message": message,
                    "empty_confirmations": empty_confirmations,
                }
            state["browser"]["wechat"]["last_draft_check"] = result_payload
            self._append_log(
                state,
                "success" if not browser.get("last_error") else "warning",
                "browser",
                str(result_payload["message"]),
                stream="business_event",
                actor=triggered_by,
                detail=" | ".join(step_logs[-3:]),
            )
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    "session-wechat",
                    "check_wechat_drafts",
                    "blocked" if browser.get("last_error") else "completed",
                    str(result_payload["message"]),
                    triggered_by,
                    str(state["channels"]["wechat"]["selectors_version"]),
                    artifacts=artifacts,
                    step_logs=step_logs + diff_logs[:8],
                ),
            )
            state["publish_tasks"] = state["publish_tasks"][:80]
            self._write(state)
            return WeChatDraftSyncCheckResult(
                checked_at=str(result_payload["checked_at"]),
                remote_count=int(result_payload["remote_count"]),
                matched_count=int(result_payload["matched_count"]),
                missing_count=int(result_payload["missing_count"]),
                items=[WeChatRemoteDraftItem(**item) for item in result_payload["items"]],
                message=str(result_payload["message"]),
            )

    def check_wechat_publish_history(self, triggered_by: str = "dashboard") -> WeChatPublishHistorySnapshot:
        with self._lock:
            state = self._upgrade_state(self._read())
            browser = self._refresh_browser_session(state)
            previous_check = (
                browser.get("last_publish_history_check")
                if isinstance(browser.get("last_publish_history_check"), dict)
                else {}
            )
            browser, artifacts, step_logs, remote_items = inspect_wechat_publish_history(state["channels"]["wechat"], browser)
            state["browser"]["wechat"] = browser

            if browser.get("last_error"):
                previous_items = previous_check.get("items", []) if isinstance(previous_check.get("items"), list) else []
                result_payload = {
                    "checked_at": now_iso(),
                    "record_count": int(previous_check.get("record_count", len(previous_items)) or 0),
                    "items": previous_items[:50],
                    "message": (
                        f"本次发表记录检查失败，当前展示最近一次成功读取结果：{int(previous_check.get('record_count', len(previous_items)) or 0)} 条。"
                        if previous_items
                        else str(browser.get("last_error") or "微信发表记录检查失败。")
                    ),
                }
            else:
                result_payload = {
                    "checked_at": now_iso(),
                    "record_count": len(remote_items),
                    "items": remote_items[:50],
                    "message": f"已检查微信发表记录，共读取 {len(remote_items)} 条远端记录。",
                }

            state["browser"]["wechat"]["last_publish_history_check"] = result_payload
            self._append_log(
                state,
                "success" if not browser.get("last_error") else "warning",
                "browser",
                str(result_payload["message"]),
                stream="business_event",
                actor=triggered_by,
                detail=" | ".join(step_logs[-3:]),
            )
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    "session-wechat",
                    "check_wechat_publish_history",
                    "blocked" if browser.get("last_error") else "completed",
                    str(result_payload["message"]),
                    triggered_by,
                    str(state["channels"]["wechat"]["selectors_version"]),
                    artifacts=artifacts,
                    step_logs=step_logs,
                ),
            )
            state["publish_tasks"] = state["publish_tasks"][:80]
            self._write(state)
            return WeChatPublishHistorySnapshot(
                checked_at=str(result_payload["checked_at"]),
                record_count=int(result_payload["record_count"]),
                items=[WeChatPublishRecordItem(**item) for item in result_payload["items"]],
                message=str(result_payload["message"]),
            )

    def get_publish_backends(self) -> list[PublishBackendStatus]:
        state = self._read_live()
        browser = self._refresh_browser_session(state)
        state["browser"]["wechat"] = browser
        backends = self._publish_backends(state)
        self._write(state)
        return [PublishBackendStatus(**item) for item in backends]

    def list_reference_projects(self) -> list[ReferenceProject]:
        state = self._upgrade_state(self._read())
        state["reference_projects"] = write_reference_baseline()
        self._write(state)
        return [ReferenceProject(**item) for item in state["reference_projects"]]

    def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        level: str = "all",
        q: str = "",
    ) -> tuple[list[LogItem], int, int, int, bool]:
        state = self._read_live()
        items = [item for item in state["logs"] if isinstance(item, dict)]
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        level_filter = str(level or "all").strip().lower()
        keyword = str(q or "").strip().lower()

        def matches_level(item: dict[str, Any]) -> bool:
            if level_filter == "all":
                return True
            return str(item.get("level") or "").lower() == level_filter

        def matches_query(item: dict[str, Any]) -> bool:
            if not keyword:
                return True
            haystack = "\n".join(
                [
                    str(item.get("message") or ""),
                    str(item.get("detail") or ""),
                    str(item.get("category") or ""),
                    str(item.get("actor") or ""),
                ]
            ).lower()
            return keyword in haystack

        filtered = [item for item in items if matches_level(item) and matches_query(item)]
        page_items, total, safe_page, safe_page_size, has_more = self._paginate_items(
            filtered,
            page=page,
            page_size=page_size,
        )
        return [LogItem(**item) for item in page_items], total, safe_page, safe_page_size, has_more

    def _latest_collected_at(self, raw_lookup: dict[str, dict[str, Any]], raw_ids: list[str]) -> str | None:
        times = [raw_lookup[item_id].get("collected_at") for item_id in raw_ids if item_id in raw_lookup]
        parsed = [item for item in (parse_time(value) for value in times) if item]
        if not parsed:
            return None
        return max(parsed).replace(microsecond=0).isoformat()

    def _freshness_snapshot(self, state: dict[str, Any]) -> FreshnessSnapshot:
        now = datetime.now(UTC)
        raw_items = state["raw_items"]
        collected_times = [parse_time(item.get("collected_at")) for item in raw_items]
        collected_times = [item for item in collected_times if item]
        published_times = [parse_time(item.get("published_at")) for item in raw_items]
        published_times = [item for item in published_times if item]

        def count_within(hours: int) -> int:
            return sum(1 for item in collected_times if (now - item).total_seconds() <= hours * 3600)

        lags = [
            minutes_between(item.get("published_at"), item.get("collected_at"))
            for item in raw_items
        ]
        lag_values = [item for item in lags if item is not None]
        enabled_sources = [item for item in state["sources"] if item.get("enabled")]
        stale_source_count = 0
        for source in enabled_sources:
            synced_at = parse_time(source.get("last_synced_at"))
            if not synced_at or (now - synced_at).total_seconds() > 6 * 3600:
                stale_source_count += 1

        latest_collected = max(collected_times).replace(microsecond=0).isoformat() if collected_times else None
        latest_published = max(published_times).replace(microsecond=0).isoformat() if published_times else None
        latest_collected_dt = parse_time(latest_collected)
        has_staleness_alert = stale_source_count > 0
        if latest_collected_dt and (now - latest_collected_dt).total_seconds() > 6 * 3600:
            has_staleness_alert = True

        return FreshnessSnapshot(
            latest_published_at=latest_published,
            latest_collected_at=latest_collected,
            items_1h=count_within(1),
            items_6h=count_within(6),
            items_24h=count_within(24),
            avg_collection_lag_minutes=round(sum(lag_values) / len(lag_values), 1) if lag_values else None,
            stale_source_count=stale_source_count,
            has_staleness_alert=has_staleness_alert,
            last_successful_sync_at=self._runtime(state).get("last_successful_sync_at"),
        )

    def _dashboard_top_bar(self, state: dict[str, Any], freshness: FreshnessSnapshot) -> DashboardTopBar:
        blocked_publish_ids = {
            str(item.get("id") or "")
            for item in state.get("briefs", [])
            if str(item.get("stage") or "") == "failed" or str(item.get("last_error") or "").strip()
        }
        blocked_publish_ids.update(
            str(item.get("target_id") or "")
            for item in state.get("publish_tasks", [])
            if item.get("status") in {"blocked", "failed"}
        )
        return DashboardTopBar(
            current_mode_label=self._current_automation_mode_def(state)["label"],
            healthy_sources=len([item for item in state["sources"] if item["health_status"] == "healthy"]),
            total_sources=len(state["sources"]),
            latest_collected_at=freshness.latest_collected_at,
            latest_published_at=freshness.latest_published_at,
            pending_briefs=len([item for item in state.get("briefs", []) if str(item.get("stage") or "") == "prepared"]),
            blocked_publish_count=len([item for item in blocked_publish_ids if item]),
        )

    def _intel_stream(self, state: dict[str, Any]) -> list[IntelStreamItem]:
        raw_lookup = {item["id"]: item for item in state["raw_items"]}
        stream: list[IntelStreamItem] = []

        for normalized in state["normalized_items"]:
            collected_at = self._latest_collected_at(raw_lookup, normalized.get("raw_item_ids", []))
            stream.append(
                IntelStreamItem(
                    id=normalized["id"],
                    title=normalized["title"],
                    summary=normalized.get("summary", ""),
                    link=normalized["link"],
                    score=float(normalized.get("final_score", 0)),
                    source_names=list(normalized.get("source_names", [])),
                    source_count=len(normalized.get("source_names", [])),
                    published_at=normalized.get("published_at"),
                    collected_at=collected_at,
                    time_lag_minutes=minutes_between(normalized.get("published_at"), collected_at),
                )
            )

        stream.sort(key=lambda item: parse_time(item.collected_at) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return stream[:12]

    def _hot_clusters(self, state: dict[str, Any]) -> list[HotClusterCard]:
        raw_lookup = {item["id"]: item for item in state["raw_items"]}
        cards = [
            HotClusterCard(
                cluster_id=item["cluster_id"],
                title=item["title"],
                final_score=float(item.get("final_score", 0)),
                member_count=len(item.get("cluster_members", [])),
                source_names=list(item.get("source_names", [])),
                published_at=item.get("published_at"),
                latest_collected_at=self._latest_collected_at(raw_lookup, item.get("raw_item_ids", [])),
                signals=list(item.get("signals", [])),
            )
            for item in sorted(state["normalized_items"], key=lambda value: value.get("final_score", 0), reverse=True)[:8]
        ]
        return cards

    def _is_github_signal(self, raw_item: dict[str, Any], source: dict[str, Any] | None) -> bool:
        if raw_item.get("source_kind") == "github":
            return True
        if "github.com/" in (raw_item.get("link") or ""):
            return True
        tags = source.get("tags", []) if source else []
        return "github" in tags or raw_item.get("source_key") == "rsshub-github-ai"

    def _extract_repo_name(self, raw_item: dict[str, Any]) -> str:
        link = raw_item.get("link") or ""
        match = re.search(r"github\.com/([^/]+/[^/?#]+)", link)
        if match:
            return match.group(1)
        return raw_item.get("title", "GitHub Repo")

    def _github_watch(self, state: dict[str, Any]) -> list[GithubSignalItem]:
        sources_by_key = self._sources_by_key(state)
        github_items: list[GithubSignalItem] = []

        for raw_item in state["raw_items"]:
            source = sources_by_key.get(raw_item["source_key"])
            if not self._is_github_signal(raw_item, source):
                continue
            github_items.append(
                GithubSignalItem(
                    id=raw_item["id"],
                    repo_name=self._extract_repo_name(raw_item),
                    summary=raw_item.get("summary", ""),
                    link=raw_item.get("link", ""),
                    stars_signal=int(raw_item.get("engagement", {}).get("score", 0) or 0),
                    source_name=raw_item.get("source_name", ""),
                    published_at=raw_item.get("published_at"),
                    collected_at=raw_item.get("collected_at"),
                )
            )

        github_items.sort(key=lambda item: parse_time(item.collected_at) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return github_items[:8]

    def _execution_chain(self, state: dict[str, Any], browser: dict[str, Any]) -> ExecutionChainSnapshot:
        source_errors = [item for item in state["sources"] if item.get("enabled") and item["health_status"] == "error"]
        source_warnings = [item for item in state["sources"] if item.get("enabled") and item["health_status"] == "warning"]
        running_jobs = [item for item in state["jobs"] if item["status"] == "running"]
        running_tasks = [item for item in state["publish_tasks"] if item["status"] == "running"]
        blocked_tasks = [item for item in state["publish_tasks"] if item["status"] in {"blocked", "failed"}]
        deep_dive_errors = [item for item in state.get("event_deep_dives", []) if str(item.get("status") or "") == "failed"]
        brief_errors = [item for item in state.get("briefs", []) if item.get("last_error") or str(item.get("stage") or "") == "failed"]
        pending_briefs = [item for item in state.get("briefs", []) if str(item.get("stage") or "") == "prepared"]
        runtime = self._runtime(state)

        if any(item["action"] == "collect_news" for item in running_jobs):
            collect_status = "running"
        elif source_errors:
            collect_status = "blocked"
        elif source_warnings:
            collect_status = "warning"
        elif state["raw_items"]:
            collect_status = "healthy"
        else:
            collect_status = "idle"

        if str(runtime.get("current_cycle") or "") == "deep_dive":
            admission_status = "running"
        elif state.get("intel_events"):
            admission_status = "healthy"
        elif state["raw_items"]:
            admission_status = "warning"
        else:
            admission_status = "idle"

        if str(runtime.get("current_cycle") or "") in {"deep_dive", "briefing"}:
            briefing_status = "running"
        elif deep_dive_errors or brief_errors:
            briefing_status = "warning"
        elif state.get("event_deep_dives") or state.get("briefs"):
            briefing_status = "healthy"
        else:
            briefing_status = "idle"

        if pending_briefs:
            review_status = "warning"
        elif state.get("briefs"):
            review_status = "healthy"
        else:
            review_status = "idle"

        if browser.get("logged_in"):
            wechat_status = "healthy"
        elif browser.get("last_error"):
            wechat_status = "blocked"
        elif state["channels"]["wechat"].get("browser_profile_path"):
            wechat_status = "warning"
        else:
            wechat_status = "blocked"

        if running_tasks or any(item["action"] == "publish_pipeline" for item in running_jobs):
            publish_status = "running"
        elif blocked_tasks:
            publish_status = "blocked"
        elif any(str(item.get("stage") or "") == "synced" for item in state.get("briefs", [])):
            publish_status = "healthy"
        else:
            publish_status = "idle"

        blockers: list[str] = []
        blockers.extend([f"来源异常：{item['name']}" for item in source_errors[:2]])
        blockers.extend(str(item.get("last_error") or "").strip() for item in brief_errors[:2] if str(item.get("last_error") or "").strip())
        if not browser.get("logged_in"):
            blockers.append("微信公众号浏览器登录态不可用。")
        browser_error = browser.get("last_error")
        if browser_error:
            blockers.append(browser_error.replace("None ", "").strip())
        if blocked_tasks:
            blockers.append(blocked_tasks[0]["message"])
        if runtime.get("blocked_reason"):
            blockers.append(str(runtime.get("blocked_reason")))
        seen: list[str] = []
        for blocker in blockers:
            if blocker and blocker not in seen:
                seen.append(blocker)
        blockers = seen[:6]

        latest_failure = next(
            (
                item for item in state["publish_tasks"]
                if item["status"] in {"blocked", "failed"}
            ),
            None,
        )
        if not latest_failure:
            latest_failure = next((item for item in state["jobs"] if item["status"] == "failed"), None)

        if latest_failure:
            latest_failure_label = latest_failure.get("label") or JOB_LABELS.get(latest_failure.get("action", ""), latest_failure.get("action", ""))
            latest_failure_at = latest_failure.get("created_at") or latest_failure.get("finished_at")
        else:
            latest_failure_label = None
            latest_failure_at = None

        stages = [
            ChainStateCard(key="collect", label="采集", status=collect_status, detail=f"健康 {len([item for item in state['sources'] if item['health_status'] == 'healthy'])}/{len(state['sources'])}"),
            ChainStateCard(key="admission", label="准入", status=admission_status, detail=f"{len(state.get('intel_events', []))} 个事件"),
            ChainStateCard(key="briefing", label="深挖/简报", status=briefing_status, detail=f"{len(state.get('event_deep_dives', []))} 次深挖 / {len(state.get('briefs', []))} 条简报"),
            ChainStateCard(key="review", label="待交付", status=review_status, detail=f"{len(pending_briefs)} 条待上传简报"),
            ChainStateCard(key="wechat", label="微信会话", status=wechat_status, detail="已登录" if browser.get("logged_in") else "未登录"),
            ChainStateCard(key="publish", label="发布", status=publish_status, detail=f"{len(blocked_tasks)} 条阻断记录"),
        ]

        source_alerts = [
            f"{item['name']}：{item['health_detail']}"
            for item in state["sources"]
            if item.get("enabled") and item.get("health_status") in {"warning", "error"}
        ]
        if not source_alerts:
            source_alerts = ["暂无来源异常，信息层运行平稳。"]

        return ExecutionChainSnapshot(
            collect_status=collect_status,
            admission_status=admission_status,
            briefing_status=briefing_status,
            review_status=review_status,
            wechat_status=wechat_status,
            publish_status=publish_status,
            blockers=blockers,
            stages=stages,
            selectors_version=str(browser.get("selectors_version", "")),
            browser_logged_in=bool(browser.get("logged_in")),
            last_screenshot=browser.get("last_screenshot"),
            last_failed_task_label=latest_failure_label,
            last_failed_task_at=latest_failure_at,
            source_alerts=source_alerts[:6],
        )

    def get_intel_snapshot(self) -> IntelSnapshot:
        state = self._upgrade_state(self._read())
        stream = self._intel_stream(state)
        clusters = self._hot_clusters(state)
        github_watch = self._github_watch(state)
        source_health = [SourceConnector(**item) for item in state["sources"]]
        return IntelSnapshot(
            stream=stream,
            clusters=clusters,
            github_watch=github_watch,
            source_health=source_health,
        )

    def _find_event(self, state: dict[str, Any], event_id: str) -> dict[str, Any]:
        for event in state.get("intel_events", []):
            if event.get("id") == event_id:
                return event
        raise ValueError(f"未找到事件：{event_id}")

    def get_intel_summary(self) -> IntelOverviewSummary:
        with self._lock:
            state = self._read_live()
            recovered_run_id = self._recover_stale_runtime_run(state, actor="intel_summary")
            runtime = self._runtime(state)
            if recovered_run_id:
                self._write(state)

        alert_dicts = [item for item in state.get("intel_alerts", []) if isinstance(item, dict)]
        event_dicts = [item for item in state.get("intel_events", []) if isinstance(item, dict)]
        event_lookup = self._event_lookup(state)
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)
        recent_alert_dicts = self._prune_intel_alert_history(state.get("intel_alert_history", []))
        recent_event_dicts = self._prune_intel_event_history(state.get("intel_event_history", []))
        alerts = [
            IntelAlert(
                **self._project_alert_runtime_fields(
                    state,
                    item,
                    event_lookup=event_lookup,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in alert_dicts
        ]
        events = [
            IntelEvent(
                **self._project_event_runtime_fields(
                    state,
                    item,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in event_dicts
        ]
        recent_alerts = [item for item in recent_alert_dicts]
        recent_events = [item for item in recent_event_dicts]
        featured_alerts = [item for item in alerts if item.level in {"breakout", "rising"}]
        engagement_threshold = self._featured_event_engagement_threshold(event_dicts)
        featured_events = [
            IntelEvent(
                **self._project_event_runtime_fields(
                    state,
                    item,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in event_dicts
            if self._is_featured_event(item, engagement_threshold)
        ]
        discovery_items = state.get("discovery_items", [])
        enabled_sources = [item for item in state["sources"] if item.get("enabled")]
        healthy_sources = len([item for item in enabled_sources if item.get("health_status") == "healthy"])
        warning_sources = len([item for item in enabled_sources if item.get("health_status") == "warning"])
        error_sources = len([item for item in enabled_sources if item.get("health_status") == "error"])
        source_alerts = [
            f"{item['name']}：{item['health_detail']}"
            for item in enabled_sources
            if item.get("health_status") in {"warning", "error"}
        ]
        if not source_alerts:
            source_alerts = ["暂无来源异常，信息获取链路正常。"]

        item_state_counts = Counter(str(item.get("item_state") or "new_item") for item in discovery_items)
        event_state_counts = Counter(str(item.get("change_state") or "new_event") for item in state.get("intel_events", []))

        return IntelOverviewSummary(
            alert_count=len(alerts),
            breakout_count=len([item for item in alerts if item.level == "breakout"]),
            rising_count=len([item for item in alerts if item.level == "rising"]),
            watch_count=len([item for item in alerts if item.level == "watch"]),
            event_count=len(events),
            discovery_count=len(discovery_items),
            new_items_count=int(item_state_counts.get("new_item", 0)),
            seen_items_count=int(item_state_counts.get("seen_item", 0)),
            updated_items_count=int(item_state_counts.get("updated_item", 0)),
            new_events_count=int(event_state_counts.get("new_event", 0)),
            growing_events_count=int(event_state_counts.get("growing_event", 0)),
            stable_events_count=int(event_state_counts.get("stable_event", 0)),
            cooling_events_count=int(event_state_counts.get("cooling_event", 0)),
            warning_sources=warning_sources,
            error_sources=error_sources,
            healthy_sources=healthy_sources,
            total_sources=len(enabled_sources),
            recent_alert_count_24h=len(recent_alerts),
            recent_event_count_24h=len(recent_events),
            recent_breakout_count_24h=len([item for item in recent_alerts if str(item.get("highest_level") or "") == "breakout"]),
            recent_rising_count_24h=len([item for item in recent_alerts if str(item.get("highest_level") or "") == "rising"]),
            last_sync_at=runtime.get("last_successful_sync_at") or runtime.get("last_collect_at"),
            next_run_at=self._calculate_next_collect_at(state),
            running=runtime.get("control_state") != "stopped",
            work_scope=self._work_scope(state),
            top_alerts=featured_alerts[:6],
            top_events=featured_events[:8],
            recent_alerts_24h=recent_alerts,
            recent_events_24h=recent_events,
            source_alerts=source_alerts[:6],
        )

    def list_discovery_items(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[DiscoveryItem], int]:
        state = self._read_live()
        all_items = [DiscoveryItem(**item) for item in state.get("discovery_items", [])]
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 50), 200))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return all_items[start:end], len(all_items)

    def list_intel_events(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IntelEvent], int]:
        state = self._read_live()
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)
        all_items = [
            IntelEvent(
                **self._project_event_runtime_fields(
                    state,
                    item,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in state.get("intel_events", [])
        ]
        safe_page = max(1, int(page or 1))
        safe_page_size = max(1, min(int(page_size or 50), 200))
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return all_items[start:end], len(all_items)

    def list_intel_event_history(self) -> list[dict[str, Any]]:
        state = self._read_live()
        return self._prune_intel_event_history(state.get("intel_event_history", []))

    def get_intel_event(self, event_id: str) -> IntelEvent:
        state = self._read_live()
        return IntelEvent(
            **self._project_event_runtime_fields(
                state,
                self._find_event(state, event_id),
                deep_dive_lookup=self._deep_dive_lookup(state),
                brief_lookup=self._brief_lookup(state),
            )
        )

    def list_intel_alerts(self) -> list[IntelAlert]:
        state = self._read_live()
        event_lookup = self._event_lookup(state)
        deep_dive_lookup = self._deep_dive_lookup(state)
        brief_lookup = self._brief_lookup(state)
        return [
            IntelAlert(
                **self._project_alert_runtime_fields(
                    state,
                    item,
                    event_lookup=event_lookup,
                    deep_dive_lookup=deep_dive_lookup,
                    brief_lookup=brief_lookup,
                )
            )
            for item in state.get("intel_alerts", [])
        ]

    def list_intel_alert_history(self) -> list[dict[str, Any]]:
        state = self._read_live()
        return self._prune_intel_alert_history(state.get("intel_alert_history", []))

    def _normalize_entity_watchlist_item(
        self,
        item: dict[str, Any],
        existing: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        existing = existing or {}
        entity_name = str(item.get("entity_name") or "").strip()
        entity_id = str(item.get("entity_id") or "").strip()
        if not entity_name and entity_id and entity_id in existing:
            entity_name = str(existing[entity_id].get("entity_name") or "").strip()
        if not entity_name:
            return None
        if not entity_id:
            entity_id = entity_id_for_name(entity_name)
        previous = existing.get(entity_id, {})
        entity_type = str(item.get("entity_type") or previous.get("entity_type") or entity_type_for_name(entity_name) or "").strip().upper()
        if not entity_type:
            return None
        return {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "watchlisted": bool(item.get("watchlisted", previous.get("watchlisted", True))),
            "added_at": item.get("added_at") or previous.get("added_at") or now_iso(),
        }

    def _entity_watchlist(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        settings = state.setdefault("settings", {})
        items = settings.setdefault("entity_watchlist", [])
        if not isinstance(items, list):
            settings["entity_watchlist"] = []
            return settings["entity_watchlist"]
        return items

    def list_entity_watchlist(self) -> list[EntityWatchlistItem]:
        state = self._read_live()
        return [EntityWatchlistItem(**item) for item in self._entity_watchlist(state)]

    def update_entity_watchlist(self, items: list[dict[str, Any]]) -> list[EntityWatchlistItem]:
        with self._lock:
            state = self._upgrade_state(self._read())
            existing_items = {str(item.get("entity_id") or ""): item for item in self._entity_watchlist(state) if item.get("entity_id")}
            normalized: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for raw_item in items:
                if not isinstance(raw_item, dict):
                    continue
                item = self._normalize_entity_watchlist_item(raw_item, existing=existing_items)
                if not item:
                    continue
                entity_id = str(item.get("entity_id") or "")
                if not entity_id or entity_id in seen_ids:
                    continue
                seen_ids.add(entity_id)
                normalized.append(item)
            state.setdefault("settings", {})["entity_watchlist"] = normalized
            self._append_log(state, "info", "settings", f"已更新重点监控实体，共 {len(normalized)} 个。", actor="dashboard")
            self._write(state)
            return [EntityWatchlistItem(**item) for item in normalized]

    def _build_entity_watchlist_summary(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        watchlist = [item for item in self._entity_watchlist(state) if item.get("watchlisted")]
        if not watchlist:
            return []
        events = state.get("intel_events", [])
        alerts = state.get("intel_alerts", [])
        summaries: list[dict[str, Any]] = []
        for item in watchlist:
            entity_id = str(item.get("entity_id") or "")
            entity_name = str(item.get("entity_name") or "")
            matched_events = [
                event for event in events
                if entity_id in event.get("entity_ids", []) or entity_name in event.get("entity_names", [])
            ]
            matched_alerts = [
                alert for alert in alerts
                if entity_id in alert.get("entity_ids", []) or entity_name in alert.get("entity_names", [])
            ]
            last_seen_candidates = [
                event.get("last_seen_at") or event.get("latest_collected_at") or event.get("first_seen_at")
                for event in matched_events
            ]
            last_seen = max(
                last_seen_candidates,
                key=lambda value: parse_time(value) or datetime.min.replace(tzinfo=UTC),
                default=None,
            )
            summaries.append(
                {
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "entity_type": str(item.get("entity_type") or entity_type_for_name(entity_name)),
                    "watchlisted": True,
                    "added_at": item.get("added_at"),
                    "event_count": len(matched_events),
                    "alert_count": len(matched_alerts),
                    "rising_count": len([alert for alert in matched_alerts if alert.get("level") == "rising"]),
                    "breakout_count": len([alert for alert in matched_alerts if alert.get("level") == "breakout"]),
                    "last_seen_at": last_seen,
                }
            )
        summaries.sort(
            key=lambda current: (
                int(current.get("breakout_count", 0) or 0),
                int(current.get("rising_count", 0) or 0),
                parse_time(current.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC),
            ),
            reverse=True,
        )
        return summaries

    def list_intel_sources(self) -> list[SourceConnector]:
        state = self._read_live()
        return [SourceConnector(**item) for item in state.get("sources", [])]

    def watchlist_event(self, event_id: str) -> IntelEvent:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            event["watchlisted"] = True
            event["ignored"] = False
            state["normalized_items"] = self._project_normalized_items_from_events(state)
            self._append_log(state, "success", "intel", f"已加入重点观察：{event['title']}", actor="dashboard")
            self._write(state)
            return IntelEvent(**event)

    def ignore_event(self, event_id: str) -> IntelEvent:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            event["ignored"] = True
            event["watchlisted"] = False
            state["intel_alerts"] = [item for item in state.get("intel_alerts", []) if item.get("event_id") != event_id]
            state["normalized_items"] = self._project_normalized_items_from_events(state)
            self._append_log(state, "warning", "intel", f"已忽略事件：{event['title']}", actor="dashboard")
            self._write(state)
            return IntelEvent(**event)

    # ── LLM config ────────────────────────────────────────────────

    def get_llm_config(self) -> dict[str, Any]:
        config = self._upgrade_user_settings(self._read_config())
        cfg = deepcopy(config.get("llm", {}))
        cfg.pop("tasks", None)
        for profile in cfg.get("profiles", []):
            key = str(profile.get("api_key", ""))
            if key and profile.get("id", "").startswith("cc-"):
                profile["api_key"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        for provider in cfg.get("providers", []):
            key = str(provider.get("api_key", ""))
            if key:
                provider["api_key"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        return cfg

    def update_llm_config(self, config: dict[str, Any]) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        existing = state.get("llm", {})
        profiles = merge_llm_profiles(
            [item for item in config.get("profiles", []) if isinstance(item, dict)],
            [item for item in existing.get("profiles", []) if isinstance(item, dict)],
        )
        current_profile_id = str(config.get("current_profile_id") or existing.get("current_profile_id") or "").strip()
        active_profile = next((item for item in profiles if item.get("id") == current_profile_id), None)
        if not active_profile and profiles:
            active_profile = profiles[0]
            current_profile_id = str(active_profile.get("id") or "")
        for profile in profiles:
            profile["enabled"] = bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key", ""))

        fallback_profile_id = str(config.get("fallback_profile_id") or existing.get("fallback_profile_id") or "").strip()
        if fallback_profile_id == current_profile_id:
            fallback_profile_id = ""
        fallback_profile = next((item for item in profiles if item.get("id") == fallback_profile_id), None)
        if not fallback_profile:
            fallback_profile_id = ""
        elif not bool(str(fallback_profile.get("api_key") or "").strip()):
            fallback_profile_id = ""

        providers_map: dict[str, dict[str, Any]] = {}
        if active_profile:
            active_provider = build_provider_from_profile(active_profile)
            if active_provider.get("key"):
                providers_map[active_provider["key"]] = active_provider
        if fallback_profile and fallback_profile_id:
            fallback_provider = build_provider_from_profile(fallback_profile)
            if fallback_provider.get("key"):
                providers_map.setdefault(fallback_provider["key"], fallback_provider)
        for profile in profiles:
            provider_key = str(profile.get("provider_key") or "")
            api_key = str(profile.get("api_key") or "").strip()
            if provider_key and api_key and "****" not in api_key and provider_key not in providers_map:
                providers_map[provider_key] = build_provider_from_profile(profile)

        next_llm = {
            "current_profile_id": current_profile_id,
            "fallback_profile_id": fallback_profile_id or None,
            "profiles": profiles,
            "providers": list(providers_map.values()),
            "usage_today": existing.get("usage_today", {}),
        }
        state["llm"] = next_llm
        settings_config = self._read_config()
        settings_config["llm"] = deepcopy_json(next_llm)
        self._write_config(self._upgrade_user_settings(settings_config))
        self._write(state)
        self._append_log(state, "info", "config", "已更新 AI 模型配置")
        return state["llm"]

    def test_llm_provider(self, provider_key: str) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        profiles = state.get("llm", {}).get("profiles", [])
        providers = state.get("llm", {}).get("providers", [])

        profile = next((item for item in profiles if item.get("provider_key") == provider_key or item.get("id") == provider_key), None)
        provider: dict[str, Any] | None = None
        tested_profile_id = ""
        if profile:
            tested_profile_id = str(profile.get("id") or "")
            provider = build_provider_from_profile(profile)
            provider["enabled"] = True
        if not provider:
            provider = next((item for item in providers if item.get("key") == provider_key), None)
            if provider:
                provider = deepcopy(provider)
        if not provider:
            raise ValueError(f"未找到服务商配置：{provider_key}")

        api_key = str(provider.get("api_key", "")).strip()
        if not api_key or "****" in api_key:
            raise ValueError(f"Provider {provider_key} has no API key configured")

        provider["enabled"] = True
        llm_config = deepcopy(state.get("llm", {}))
        llm_config["providers"] = [provider]
        llm_service = LLMService(llm_config)
        result = llm_service.test_connection(str(provider.get("key") or provider_key))
        tested_at = now_iso()
        for profile in profiles:
            if str(profile.get("id") or "") == tested_profile_id:
                profile["last_tested_at"] = tested_at
                profile["last_test_result"] = "ok" if result.get("ok") else result.get("error", "failed")
                profile["cc_probe_status"] = result.get("probe_status") or ("verified" if result.get("ok") else "request_failed")
                profile["cc_probe_message"] = result.get("probe_message") or result.get("error") or ""
                if result.get("ok"):
                    profile["cc_last_verified_endpoint"] = result.get("resolved_endpoint") or profile.get("cc_last_verified_endpoint")
                    profile["cc_last_verified_format"] = result.get("resolved_format") or profile.get("cc_last_verified_format")
                    profile["cc_last_verified_model"] = result.get("resolved_model") or result.get("model") or profile.get("cc_last_verified_model")
                break
        for p in providers:
            if p["key"] == str(provider.get("key") or provider_key):
                p["last_tested_at"] = tested_at
                p["last_test_result"] = "ok" if result.get("ok") else result.get("error", "failed")
        self._write(state)
        return result

    def get_llm_usage(self) -> dict[str, dict[str, int]]:
        state = self._read_live()
        return state.get("llm", {}).get("usage_today", {})

    def import_cc_switch_profiles(self, cc_profiles: list[dict[str, Any]]) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        llm = state.setdefault("llm", default_llm_state())
        existing_profiles = llm.get("profiles", [])
        existing_by_id = {str(p.get("id", "")): deepcopy(p) for p in existing_profiles if isinstance(p, dict) and p.get("id")}

        for cc in cc_profiles:
            pid = str(cc.get("id", ""))
            if not pid:
                continue
            incoming_key = str(cc.get("api_key", ""))
            if pid in existing_by_id:
                existing_key = str(existing_by_id[pid].get("api_key", ""))
                if "****" in incoming_key and existing_key and "****" not in existing_key:
                    cc["api_key"] = existing_key
                existing_by_id[pid] = {**existing_by_id[pid], **cc}
            else:
                existing_by_id[pid] = deepcopy(cc)

        profiles = merge_llm_profiles(list(existing_by_id.values()), existing_profiles)
        for profile in profiles:
            profile["enabled"] = bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key", ""))

        current_profile_id = str(llm.get("current_profile_id") or "").strip()
        if not any(str(profile.get("id") or "") == current_profile_id for profile in profiles):
            current_profile_id = str(profiles[0].get("id") or "") if profiles else ""

        fallback_profile_id = str(llm.get("fallback_profile_id") or "").strip()
        if fallback_profile_id == current_profile_id:
            fallback_profile_id = ""
        fallback_profile = next((profile for profile in profiles if str(profile.get("id") or "") == fallback_profile_id), None)
        if not fallback_profile or not bool(str(fallback_profile.get("api_key") or "").strip()):
            fallback_profile_id = ""

        llm["current_profile_id"] = current_profile_id
        llm["fallback_profile_id"] = fallback_profile_id or None
        llm["profiles"] = profiles
        llm["providers"] = [
            build_provider_from_profile(profile)
            for profile in profiles
            if bool(str(profile.get("api_key") or "").strip()) and "****" not in str(profile.get("api_key", ""))
        ]
        self._write(state)
        self._append_log(state, "info", "config", f"已从 CC-Switch 导入 {len(cc_profiles)} 个服务商配置")
        return llm

    # ── Dashboard ────────────────────────────────────────────────

    def get_dashboard(self) -> DashboardResponse:
        with self._lock:
            state = self._read_live()
            recovered_run_id = self._recover_stale_runtime_run(state, actor="dashboard")
            if recovered_run_id:
                self._write(state)
            snapshot = deepcopy(state)

        previous_browser = deepcopy(snapshot.get("browser", {}).get("wechat", {}))
        browser = self._refresh_browser_session(snapshot)
        backends = self._publish_backends(snapshot)
        runtime = self._runtime(snapshot)
        app_version = self.get_app_version_info()
        update_info = self.get_app_update_info(force=False)
        runtime["next_collect_at"] = self._calculate_next_collect_at(snapshot)
        runtime["launch_mode"] = self._runtime_plan(snapshot).get("launch_mode", "interval_now")
        runtime_status = self._scheduler_status_from_state(snapshot)
        last_cycle_summary = runtime.get("last_cycle_summary") or self._build_last_cycle_summary(snapshot, runtime)
        recent_alerts_24h = self._prune_intel_alert_history(snapshot.get("intel_alert_history", []))
        recent_events_24h = self._prune_intel_event_history(snapshot.get("intel_event_history", []))
        freshness = self._freshness_snapshot(snapshot)
        top_bar = self._dashboard_top_bar(snapshot, freshness)
        intel_stream = self._intel_stream(snapshot)
        hot_clusters = self._hot_clusters(snapshot)
        github_watch = self._github_watch(snapshot)
        execution_chain = self._execution_chain(snapshot, browser)
        entity_watchlist_summary = self._build_entity_watchlist_summary(snapshot)
        setup_status = self._setup_status(snapshot, browser)
        doctor = self.system_doctor()
        stats = {
            "total_sources": top_bar.total_sources,
            "healthy_sources": top_bar.healthy_sources,
            "collected_today": freshness.items_24h,
            "event_count": len(snapshot["intel_events"]),
            "deep_dive_ready": len([item for item in snapshot.get("event_deep_dives", []) if str(item.get("status") or "") in {"ready", "partial"}]),
            "brief_total": len(snapshot.get("briefs", [])),
            "brief_prepared": len([item for item in snapshot.get("briefs", []) if str(item.get("stage") or "") == "prepared"]),
            "brief_synced": len([item for item in snapshot.get("briefs", []) if str(item.get("stage") or "") == "synced"]),
            "publish_blocked": len([item for item in snapshot.get("publish_tasks", []) if item.get("status") in {"blocked", "failed"}]),
        }
        snapshot["browser"]["wechat"] = browser
        return DashboardResponse(
            app_version=app_version,
            update_info=update_info,
            stats=DashboardStats(**stats),
            top_bar=top_bar,
            freshness=freshness,
            intel_stream=intel_stream,
            hot_clusters=hot_clusters,
            github_watch=github_watch,
            execution_chain=execution_chain,
            current_automation_mode=AutomationModeDefinition(**self._current_automation_mode_def(snapshot)),
            current_automation_profile=AutomationModeProfile(**self._current_automation_profile(snapshot)),
            automation_profiles=[AutomationModeProfile(**item) for item in snapshot["automation_profiles"]],
            runtime_plan=self._runtime_plan_from_state(snapshot),
            runtime_status=runtime_status,
            last_cycle_summary=RuntimeCycleSummary(**last_cycle_summary) if isinstance(last_cycle_summary, dict) else None,
            recent_alerts_24h=recent_alerts_24h,
            recent_events_24h=recent_events_24h,
            entity_watchlist_summary=[EntityWatchlistSummaryItem(**item) for item in entity_watchlist_summary],
            recent_logs=[LogItem(**item) for item in snapshot["logs"][:8]],
            briefs=[],
            deep_dives=[],
            sources=[],
            browser_session=BrowserSessionState(**browser),
            publish_backends=[PublishBackendStatus(**item) for item in backends],
            setup_status=setup_status,
            doctor_summary=doctor.model_dump(),
        )
