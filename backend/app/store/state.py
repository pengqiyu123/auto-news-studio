from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime
from html import escape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from ..intel.normalize import normalize_raw_items
from ..llm.store_llm import (
    DEFAULT_LLM_TASK_TEMPLATE,
    build_provider_from_profile,
    default_llm_state,
    infer_fallback_profile_id_from_tasks,
    merge_llm_profiles,
)
from .base import (
    DEFAULT_RUNTIME_INTENT,
    DEFAULT_USER_SETTINGS,
    MAX_RAW_ITEMS,
    UTC,
    _contains_synthetic_marker,
    _is_synthetic_raw_item,
    atomic_write_json,
    deepcopy_json,
    freshness_bucket,
    local_now,
    now_iso,
    parse_time,
    read_json_file,
    schedule_to_minutes,
)
from .defaults import AUTOMATION_MODE_DEFINITIONS, DEFAULT_AUTOMATION_PROFILES

# publishers imported lazily to avoid circular import
from .reference_projects import write_reference_baseline


def _default_agent_html_targets() -> list[dict[str, Any]]:
    now = now_iso()
    return [
        {
            "id": "aht-maomu-news",
            "brand": "猫目",
            "name": "猫目新闻聚合",
            "entry_url": "https://maomu.com/news",
            "target_type": "newsroom",
            "enabled": True,
            "tags": ["cn", "ai", "aggregation", "media"],
            "discover_mode": "rule_with_ai_fallback",
            "extract_mode": "best_effort_html",
            "discovery_rules": {
                "link_selector": "a[href*='tmtpost.com'], a[href*='qbitai.com'], a[href*='zhidx.com'], a[href*='ithome.com'], a[href*='36kr.com'], a[href*='techweb.com.cn']",
                "title_selector": "h3, .title",
                "time_selector": "",
                "summary_selector": ".desc",
                "link_allow_patterns": [
                    "tmtpost.com/",
                    "qbitai.com/",
                    "zhidx.com/",
                    "ithome.com/",
                    "36kr.com/",
                    "techweb.com.cn/",
                ],
                "link_deny_patterns": [
                    "maomu.com/news",
                    "/tag/",
                    "/category/",
                    "javascript:",
                ],
            },
            "last_run_at": None,
            "last_success_at": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        }
    ]

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
            "label": str(task.get("label") or current.get("label") or base.get("label") or key),
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


def _migrate_automation_mode_and_delivery(state: dict[str, Any]) -> None:
    runtime_plan = state.setdefault("runtime_plan", {})
    runtime = state.setdefault("runtime", {})
    current_mode = str(state.get("automation_mode") or "manual")
    runtime_mode = str(runtime.get("current_mode") or current_mode)

    def _apply(mode: str, delivery_mode: str) -> None:
        state["automation_mode"] = mode
        runtime["current_mode"] = mode
        runtime_plan["delivery_mode"] = delivery_mode
        runtime["delivery_mode"] = delivery_mode
        runtime_plan["admission_strategy"] = "top_scored"
        runtime["admission_strategy"] = "top_scored"

    if current_mode == "radar_only":
        _apply("manual", "collect_only")
    elif current_mode == "radar_and_draft":
        _apply("automated", "local_digest")
    elif current_mode == "full_pipeline":
        _apply("automated", "immediate")
    elif current_mode in {"manual", "automated"}:
        state["automation_mode"] = current_mode
        runtime["current_mode"] = current_mode if runtime_mode in {"radar_only", "radar_and_draft", "full_pipeline"} else runtime_mode
        if current_mode == "manual":
            runtime_plan.setdefault("delivery_mode", "collect_only")
        else:
            runtime_plan.setdefault("delivery_mode", "local_digest")
        runtime.setdefault("delivery_mode", runtime_plan.get("delivery_mode", "collect_only"))
        runtime_plan.setdefault("admission_strategy", "top_scored")
        runtime.setdefault("admission_strategy", runtime_plan.get("admission_strategy", "top_scored"))
    else:
        _apply("manual", "collect_only")


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


class StoreCoreStateMixin:
    def _bootstrap_state(self) -> dict[str, Any]:
        from ..publishers import default_browser_profile_path
        reference_projects = write_reference_baseline()
        sources = self._build_source_registry()
        state = {
            "automation_mode": "manual",
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
            "agent_workflows": [],
            "agent_html_targets": _default_agent_html_targets(),
            "agent_html_runs": [],
            "agent_html_discovery_items": [],
            "agent_html_events": [],
            "agent_html_event_snapshots": [],
            "agent_html_event_history": [],
            "agent_html_documents": [],
            "agent_html_document_revisions": [],
            "analysis_feedback": [],
            "analysis_reports": [],
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
                },
                "douyin": {
                    "browser_name": "edge",
                    "browser_profile_path": str(default_browser_profile_path("edge")).replace("wechat-", "douyin-"),
                    "publish_entry_url": "https://creator.douyin.com/",
                    "selectors_version": "douyin-creator-v1",
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
                },
                "douyin": {
                    "platform": "douyin_creator",
                    "browser_name": "edge",
                    "user_data_dir": str(default_browser_profile_path("edge")).replace("wechat-", "douyin-"),
                    "logged_in": False,
                    "last_checked_at": None,
                    "last_opened_url": None,
                    "last_error": None,
                    "selectors_version": "douyin-creator-v1",
                    "last_screenshot": None,
                    "last_selector_check": None,
                    "current_page": "https://creator.douyin.com/",
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
                },
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
                "delivery_mode": "collect_only",
                "delivery_schedule_time": None,
                "admission_strategy": "top_scored",
                "batch_limit": 5,
            },
            "runtime": {
                "scheduler_running": False,
                "control_state": "stopped",
                "launch_mode": "interval_now",
                "current_mode": "manual",
                "work_scope": "collect_events_alerts",
                "last_collect_at": None,
                "last_event_sync_at": None,
                "last_brief_at": None,
                "next_collect_at": None,
                "delivery_mode": "collect_only",
                "delivery_schedule_time": None,
                "admission_strategy": "top_scored",
                "batch_limit": 5,
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
        from ..publishers import default_browser_profile_path
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
        legacy_state = read_json_file(self._active_state_read_file(), {})
        migrated = self._extract_config_from_state(legacy_state)
        self._write_config(migrated)

    def _apply_user_settings_to_state(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        from ..publishers import ensure_channel_defaults
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
            state_file = self._active_state_read_file()
            state = json.loads(state_file.read_text(encoding="utf-8"))
            config = self._upgrade_user_settings(read_json_file(self.config_file, self._bootstrap_user_settings()))
            return self._apply_user_settings_to_state(state, config)

    def _ensure_live_state_defaults(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("automation_mode", "manual")
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
        state.setdefault("agent_workflows", [])
        state.setdefault("agent_html_targets", _default_agent_html_targets())
        state.setdefault("agent_html_runs", [])
        state.setdefault("agent_html_discovery_items", [])
        state.setdefault("agent_html_events", [])
        state.setdefault("agent_html_event_snapshots", [])
        state.setdefault("agent_html_event_history", [])
        state.setdefault("agent_html_documents", [])
        state.setdefault("agent_html_document_revisions", [])
        state.setdefault("analysis_feedback", [])
        state.setdefault("analysis_reports", [])
        state.setdefault("publish_tasks", [])
        state.setdefault("jobs", [])
        state.setdefault("logs", [])
        state.setdefault("reference_projects", [])
        state.setdefault("runtime_plan", {})
        _migrate_automation_mode_and_delivery(state)
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
        from ..publishers import ensure_channel_defaults, ensure_douyin_channel_defaults
        channels["wechat"] = ensure_channel_defaults(channels.get("wechat", {}))
        channels["douyin"] = ensure_douyin_channel_defaults(channels.get("douyin", {}))

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
        browser_wechat.setdefault("last_analytics_overview", None)

        browser_douyin = browser.setdefault("douyin", {})
        browser_douyin.setdefault("platform", "douyin_creator")
        browser_douyin["browser_name"] = channels["douyin"]["browser_name"]
        browser_douyin["user_data_dir"] = channels["douyin"]["browser_profile_path"]
        browser_douyin.setdefault("logged_in", False)
        browser_douyin.setdefault("last_checked_at", None)
        browser_douyin.setdefault("last_opened_url", None)
        browser_douyin.setdefault("last_error", None)
        browser_douyin["selectors_version"] = channels["douyin"]["selectors_version"]
        browser_douyin.setdefault("last_screenshot", None)
        browser_douyin.setdefault("last_selector_check", None)
        browser_douyin.setdefault("current_page", channels["douyin"]["publish_entry_url"])
        browser_douyin.setdefault("sidecar_health", "offline")
        browser_douyin.setdefault("manager_alive", False)
        browser_douyin.setdefault("window_state", "unknown")
        browser_douyin.setdefault("resident_page", None)
        browser_douyin.setdefault("busy", False)
        browser_douyin.setdefault("last_reset_reason", None)
        browser_douyin.setdefault("session_generation", 0)
        browser_douyin.setdefault("last_action", None)
        browser_douyin.setdefault("last_action_phase", None)
        browser_douyin.setdefault("is_session_level_error", False)

        runtime = state.setdefault("runtime", {})
        runtime.setdefault("scheduler_running", False)
        runtime.setdefault("control_state", "stopped")
        runtime.setdefault("launch_mode", "interval_now")
        runtime.setdefault("current_mode", state.get("automation_mode", "manual"))
        runtime.setdefault("work_scope", state.get("runtime_plan", {}).get("work_scope", "collect_events_alerts"))
        runtime.setdefault("last_collect_at", None)
        runtime.setdefault("last_event_sync_at", None)
        runtime.setdefault("last_brief_at", None)
        runtime.setdefault("next_collect_at", None)
        runtime.setdefault("delivery_mode", state.get("runtime_plan", {}).get("delivery_mode", "collect_only"))
        runtime.setdefault("delivery_schedule_time", None)
        runtime.setdefault("admission_strategy", state.get("runtime_plan", {}).get("admission_strategy", "top_scored"))
        runtime.setdefault("batch_limit", int(state.get("runtime_plan", {}).get("batch_limit", 5) or 5))
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

        for target in state.get("agent_html_targets", []):
            if not isinstance(target, dict):
                continue
            target.setdefault("target_type", "newsroom")
            target.setdefault("enabled", True)
            target.setdefault("tags", [])
            target.setdefault("discover_mode", "rule_with_ai_fallback")
            target.setdefault("extract_mode", "best_effort_html")
            target.setdefault("discovery_rules", {})
            target.setdefault("last_run_at", None)
            target.setdefault("last_success_at", None)
            target.setdefault("last_error", None)
            target.setdefault("created_at", now_iso())
            target.setdefault("updated_at", now_iso())

        existing_agent_html_target_ids = {
            str(target.get("id") or "").strip()
            for target in state.get("agent_html_targets", [])
            if isinstance(target, dict)
        }
        for default_target in _default_agent_html_targets():
            target_id = str(default_target.get("id") or "").strip()
            if target_id and target_id not in existing_agent_html_target_ids:
                state["agent_html_targets"].append(deepcopy(default_target))

        for run in state.get("agent_html_runs", []):
            if not isinstance(run, dict):
                continue
            run.setdefault("status", "pending")
            run.setdefault("started_at", None)
            run.setdefault("finished_at", None)
            run.setdefault("discovered_count", 0)
            run.setdefault("new_discovery_count", 0)
            run.setdefault("updated_discovery_count", 0)
            run.setdefault("fetched_count", 0)
            run.setdefault("extracted_count", 0)
            run.setdefault("failed_count", 0)
            run.setdefault("list_fetch_status", "pending")
            run.setdefault("ai_fallback_used", False)
            run.setdefault("error_summary", None)
            run.setdefault("triggered_by", "dashboard")
            run.setdefault("created_at", now_iso())
            run.setdefault("updated_at", now_iso())

        for item in state.get("agent_html_discovery_items", []):
            if not isinstance(item, dict):
                continue
            item.setdefault("content_hash", "")
            item.setdefault("item_state", "new_item")
            item.setdefault("document_id", None)
            item.setdefault("event_id", None)
            item.setdefault("metadata", {})

        for document in state.get("agent_html_documents", []):
            if not isinstance(document, dict):
                continue
            document.setdefault("title", "")
            document.setdefault("published_at", None)
            document.setdefault("latest_seen_at", None)
            document.setdefault("current_content_hash", "")
            document.setdefault("word_count", 0)
            document.setdefault("extractor", "")
            document.setdefault("revisions", [])

        for revision in state.get("agent_html_document_revisions", []):
            if not isinstance(revision, dict):
                continue
            revision.setdefault("title", "")
            revision.setdefault("content_text", "")
            revision.setdefault("excerpt", "")
            revision.setdefault("content_hash", "")
            revision.setdefault("word_count", 0)
            revision.setdefault("extractor", "")
            revision.setdefault("published_at", None)
            revision.setdefault("change_summary", "")

        for event in state.get("agent_html_events", []):
            if not isinstance(event, dict):
                continue
            event.setdefault("summary", "")
            event.setdefault("representative_document_id", None)
            event.setdefault("representative_link", "")
            event.setdefault("discovery_item_ids", [])
            event.setdefault("document_ids", [])
            event.setdefault("member_count", 0)
            event.setdefault("source_count", 0)
            event.setdefault("first_seen_at", None)
            event.setdefault("last_seen_at", None)
            event.setdefault("change_state", "new_event")
            event.setdefault("alert_state", "watch")
            event.setdefault("entity_names", [])
            event.setdefault("tags", [])

        for brief in state.get("briefs", []):
            if not isinstance(brief, dict):
                continue
            brief.setdefault("brief_level", "rule")
            brief.setdefault("stage", "prepared")
            brief.setdefault("summary", "")
            brief.setdefault("one_line", "")
            brief.setdefault("why_it_matters", "")
            brief.setdefault("facts", [])
            brief.setdefault("quotes", [])
            brief.setdefault("timeline", [])
            brief.setdefault("entity_names", [])
            brief.setdefault("source_links", [])
            brief.setdefault("risk_notes", [])
            brief.setdefault("prompt_package_markdown", "")
            brief.setdefault("douyin_prompt_package_markdown", "")
            brief.setdefault("wechat_markdown", "")
            brief.setdefault("wechat_html", "")
            brief.setdefault("douyin_title", "")
            brief.setdefault("douyin_summary", "")
            brief.setdefault("douyin_markdown", "")
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
            brief.setdefault("workflow_mode", "traditional")
            brief.setdefault("workflow_session_id", None)
            brief.setdefault("updated_at", now_iso())
            brief.pop("wechat_draft_id", None)

        for workflow in state.get("agent_workflows", []):
            if not isinstance(workflow, dict):
                continue
            workflow.setdefault("workflow_session_id", f"agentwf-{uuid4().hex[:12]}")
            workflow.setdefault("status", "running")
            workflow.setdefault("current_step", "sources_sync")
            workflow.setdefault("event_id", None)
            workflow.setdefault("material_brief_id", None)
            workflow.setdefault("article_brief_id", None)
            workflow.setdefault("target_platforms", [])
            workflow.setdefault("last_error", None)
            workflow.setdefault("started_at", now_iso())
            workflow.setdefault("updated_at", workflow.get("started_at") or now_iso())
            workflow.setdefault("finished_at", None)

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
        state_file = self._active_state_read_file()
        state = json.loads(state_file.read_text(encoding="utf-8"))
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
            self.state_read_file = self.data_file

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
        state.setdefault("automation_mode", "manual")
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
        state.setdefault("agent_workflows", [])
        state.setdefault("analysis_feedback", [])
        state.setdefault("analysis_reports", [])
        settings = state.setdefault("settings", {})
        settings["max_workers"] = int(config.get("settings", {}).get("max_workers", 8) or 8)
        settings.setdefault("entity_watchlist", [])
        settings["tavily_api_key"] = str(config.get("settings", {}).get("tavily_api_key") or "").strip()
        state.setdefault("runtime_plan", {})
        _migrate_automation_mode_and_delivery(state)
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
        raw_douyin_channel = dict(config.get("douyin", channels.setdefault("douyin", {})))
        from ..publishers import ensure_channel_defaults, ensure_douyin_channel_defaults
        wechat_channel = ensure_channel_defaults(channels.setdefault("wechat", {}))
        wechat_channel.update(ensure_channel_defaults(raw_wechat_channel))
        channels["wechat"] = wechat_channel
        douyin_channel = ensure_douyin_channel_defaults(channels.setdefault("douyin", {}))
        douyin_channel.update(ensure_douyin_channel_defaults(raw_douyin_channel))
        channels["douyin"] = douyin_channel
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
        browser_wechat.setdefault("last_analytics_overview", None)
        browser_douyin = browser.setdefault("douyin", {})
        browser_douyin.setdefault("platform", "douyin_creator")
        browser_douyin["browser_name"] = douyin_channel["browser_name"]
        browser_douyin["user_data_dir"] = douyin_channel["browser_profile_path"]
        browser_douyin.setdefault("logged_in", False)
        browser_douyin.setdefault("last_checked_at", None)
        browser_douyin.setdefault("last_opened_url", None)
        browser_douyin.setdefault("last_error", None)
        browser_douyin["selectors_version"] = douyin_channel["selectors_version"]
        browser_douyin.setdefault("last_screenshot", None)
        browser_douyin.setdefault("last_selector_check", None)
        browser_douyin.setdefault("current_page", douyin_channel["publish_entry_url"])
        browser_douyin.setdefault("sidecar_health", "offline")
        browser_douyin.setdefault("manager_alive", False)
        browser_douyin.setdefault("window_state", "unknown")
        browser_douyin.setdefault("resident_page", None)
        browser_douyin.setdefault("busy", False)
        browser_douyin.setdefault("last_reset_reason", None)
        browser_douyin.setdefault("session_generation", 0)
        browser_douyin.setdefault("last_action", None)
        browser_douyin.setdefault("last_action_phase", None)
        browser_douyin.setdefault("is_session_level_error", False)
        runtime = state.setdefault("runtime", {})
        runtime.setdefault("scheduler_running", False)
        runtime.setdefault("control_state", "stopped")
        runtime.setdefault("launch_mode", "interval_now")
        runtime.setdefault("current_mode", state.get("automation_mode", "manual"))
        runtime.setdefault("work_scope", state.get("runtime_plan", {}).get("work_scope", "collect_events_alerts"))
        runtime.setdefault("last_collect_at", None)
        runtime.setdefault("last_event_sync_at", None)
        runtime.setdefault("last_brief_at", None)
        runtime.setdefault("next_collect_at", None)
        runtime.setdefault("delivery_mode", state.get("runtime_plan", {}).get("delivery_mode", "collect_only"))
        runtime.setdefault("delivery_schedule_time", None)
        runtime.setdefault("admission_strategy", state.get("runtime_plan", {}).get("admission_strategy", "top_scored"))
        runtime.setdefault("batch_limit", int(state.get("runtime_plan", {}).get("batch_limit", 5) or 5))
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
            brief.setdefault("summary", "")
            brief.setdefault("one_line", "")
            brief.setdefault("why_it_matters", "")
            brief.setdefault("facts", [])
            brief.setdefault("quotes", [])
            brief.setdefault("timeline", [])
            brief.setdefault("entity_names", [])
            brief.setdefault("source_links", [])
            brief.setdefault("risk_notes", [])
            brief.setdefault("prompt_package_markdown", "")
            brief.setdefault("douyin_prompt_package_markdown", "")
            brief.setdefault("wechat_markdown", "")
            brief.setdefault("wechat_html", "")
            brief.setdefault("douyin_title", "")
            brief.setdefault("douyin_summary", "")
            brief.setdefault("douyin_markdown", "")
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
            brief.setdefault("workflow_mode", "traditional")
            brief.setdefault("workflow_session_id", None)
            brief.setdefault("updated_at", now_iso())
            brief.pop("wechat_draft_id", None)
        for workflow in state.get("agent_workflows", []):
            if not isinstance(workflow, dict):
                continue
            workflow.setdefault("workflow_session_id", f"agentwf-{uuid4().hex[:12]}")
            workflow.setdefault("status", "running")
            workflow.setdefault("current_step", "sources_sync")
            workflow.setdefault("event_id", None)
            workflow.setdefault("material_brief_id", None)
            workflow.setdefault("article_brief_id", None)
            workflow.setdefault("target_platforms", [])
            workflow.setdefault("last_error", None)
            workflow.setdefault("started_at", now_iso())
            workflow.setdefault("updated_at", workflow.get("started_at") or now_iso())
            workflow.setdefault("finished_at", None)
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
