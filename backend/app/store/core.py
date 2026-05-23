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

from .base import (
    BACKUP_DIR,
    CONFIG_FILE,
    CONFIG_DIR,
    DATA_FILE,
    derive_config_file_for_data_file,
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
    resolve_existing_state_file,
    schedule_to_minutes,
)

from ..connectors import _collect_with_retry, collect_enabled_sources, collect_from_source
from ..briefing import build_prompt_package_markdown, build_rule_brief_payload, build_agent_article_writing_guide
from ..deep_dive import canonicalize_url, fetch_and_extract_link, search_tavily
from ..entity_extractor import entity_id_for_name, entity_type_for_name
from ..intel_pipeline import build_intel_state
from ..llm import LLMService
from ..legacy_sources import build_legacy_rss_sources
from ..models import (
    AgentHtmlDiscoveryItem,
    AgentHtmlDiscoverMode,
    AgentHtmlDiscoveryRules,
    AgentHtmlDocument,
    AgentHtmlDocumentRevision,
    AgentHtmlEvent,
    AgentHtmlEventHistoryItem,
    AgentHtmlEventSnapshot,
    AgentHtmlRun,
    AgentHtmlTarget,
    AgentHtmlTargetCreatePayload,
    AgentHtmlTargetUpdatePayload,
    AgentArticlePayload,
    AppUpdateInfo,
    AppVersionInfo,
    AutomationMode,
    AutomationModeDefinition,
    AutomationModeProfile,
    BriefItem,
    DouyinArticleFillPayload,
    BrowserSessionPayload,
    BrowserSessionState,
    BriefStageCounts,
    BriefRecordCounts,
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
    DouyinChannelConfig,
    DouyinArticleStructureSnapshot,
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
from ..store_llm import (
    build_provider_from_profile,
    build_runtime_tasks,
    default_llm_state,
    infer_fallback_profile_id_from_tasks,
    merge_llm_profiles,
    DEFAULT_LLM_PROFILES,
    DEFAULT_LLM_TASK_TEMPLATE,
)
from .defaults import (
    DEFAULT_SOURCES,
    AUTOMATION_MODE_DEFINITIONS,
    DEFAULT_AUTOMATION_PROFILES,
)
from ..services.wechat_reconcile import (
    apply_publish_history_matches,
    build_wechat_mapping_snapshot,
    normalize_wechat_title as _normalize_wechat_title,
    project_briefs,
    wechat_title_matches as _wechat_title_matches,
)
from ..store_mixins import AgentHtmlMixin, BriefsMixin, DashboardMixin, DeliveryMixin, IntelMixin, LLMEnhanceMixin, RuntimeMixin, SettingsMixin, SourceSyncMixin, WeChatMixin
from ..pipeline import normalize_raw_items
from ..publishers import (
    WECHAT_BROWSER_MANAGER,
    build_remote_draft_key,
    build_preview_url,
    build_wechat_target_id,
    collect_douyin_backend_status,
    collect_backend_status,
    create_publish_task,
    delete_wechat_remote_draft,
    default_browser_profile_path,
    ensure_channel_defaults,
    ensure_douyin_channel_defaults,
    extract_wechat_appmsg_id,
    fill_douyin_article_from_brief,
    inspect_wechat_draft_box,
    inspect_douyin_session,
    inspect_douyin_article_structure,
    open_douyin_article_publish,
    inspect_wechat_publish_history,
    inspect_wechat_session,
    launch_douyin_dashboard,
    launch_wechat_dashboard,
    refresh_browser_session,
    refresh_douyin_browser_session,
    run_browser_action,
)
from .reference_projects import write_reference_baseline
from ..sources import discover_sources
from .runtime import StoreCoreRuntimeMixin
from .state import StoreCoreStateMixin


def _normalize_wechat_title(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip().lower()


def _wechat_title_matches(left: str, right: str) -> bool:
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

class StoreCore(DashboardMixin, DeliveryMixin, LLMEnhanceMixin, SourceSyncMixin, StoreCoreStateMixin, StoreCoreRuntimeMixin):
    def __init__(self, data_file: Path | None = None):
        store_module = __import__(__package__, fromlist=["DATA_FILE", "CONFIG_FILE"])
        requested_data_file = data_file or getattr(store_module, "DATA_FILE", DATA_FILE)
        self.data_file = requested_data_file
        self.state_read_file = resolve_existing_state_file(requested_data_file)
        if data_file is not None:
            self.config_file = derive_config_file_for_data_file(requested_data_file)
        else:
            self.config_file = getattr(store_module, "CONFIG_FILE", CONFIG_FILE)
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
        if not self.state_read_file.exists():
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

    def _active_state_read_file(self) -> Path:
        if self.data_file.exists():
            self.state_read_file = self.data_file
        elif not self.state_read_file.exists():
            self.state_read_file = resolve_existing_state_file(self.data_file)
        return self.state_read_file

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
        audience_fit_score = float(event.get("audience_fit_score", 0) or 0)
        if success_count < 1:
            return False, "正文深挖仍未拿到可用正文来源。"
        if not facts and not quotes:
            return False, "已抓取正文，但还没有足够可复用的事实或引文。"
        if alert_state in {"rising", "breakout"}:
            return True, f"事件处于 {alert_state} 阶段，且已有可引用正文证据。"
        if watchlisted and audience_fit_score >= 45:
            return True, "事件已进入深挖池，且更贴近公众号大众科技受众，可继续生成简报。"
        if watchlisted:
            return True, "事件已进入深挖池，且已有正文证据，可生成简报继续跟进。"
        return False, "当前仍未进入重点观察或上升/爆发态，建议继续观察。"

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

    def _refresh_douyin_browser_session(self, state: dict[str, Any]) -> dict[str, Any]:
        current = state["browser"]["douyin"]
        channel = state["channels"]["douyin"]
        next_state = refresh_douyin_browser_session(channel, current)
        state["browser"]["douyin"] = next_state
        return next_state

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

    def _publish_backends(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            *collect_backend_status(state["channels"]["wechat"], state["browser"]["wechat"]),
            *collect_douyin_backend_status(state["channels"]["douyin"], state["browser"]["douyin"]),
        ]

    def _sync_llm_usage(self, state: dict[str, Any], llm_service: LLMService | None) -> None:
        if not llm_service:
            return
        state.setdefault("llm", {}).setdefault("usage_today", {})
        state["llm"]["usage_today"] = llm_service.get_usage()

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

    def _latest_collected_at(self, raw_lookup: dict[str, dict[str, Any]], raw_ids: list[str]) -> str | None:
        times = [raw_lookup[item_id].get("collected_at") for item_id in raw_ids if item_id in raw_lookup]
        parsed = [item for item in (parse_time(value) for value in times) if item]
        if not parsed:
            return None
        return max(parsed).replace(microsecond=0).isoformat()
