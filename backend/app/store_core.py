from __future__ import annotations

from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
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
from urllib.parse import urljoin, urlsplit
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
from .services.wechat_reconcile import (
    apply_publish_history_matches,
    build_wechat_mapping_snapshot,
    normalize_wechat_title as _normalize_wechat_title,
    project_briefs,
    wechat_title_matches as _wechat_title_matches,
)
from .store_mixins import AgentHtmlMixin, BriefsMixin, IntelMixin, RuntimeMixin, SettingsMixin, WeChatMixin
from .pipeline import normalize_raw_items
from .publishers import (
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
from .sources import discover_sources
from .store_core_runtime import StoreCoreRuntimeMixin
from .store_core_state import StoreCoreStateMixin


AGENT_HTML_CACHE_DIR = Path(__file__).resolve().parents[2] / "runtime" / "agent_html_cache"
AGENT_HTML_LIST_CACHE_DIR = AGENT_HTML_CACHE_DIR / "list_pages"
AGENT_HTML_DETAIL_CACHE_DIR = AGENT_HTML_CACHE_DIR / "detail_pages"


class _AgentHtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = str(data or "").strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return " ".join(self._parts)


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

class StoreCore(StoreCoreStateMixin, StoreCoreRuntimeMixin):
    def __init__(self, data_file: Path | None = None):
        store_module = __import__(__package__ + ".store", fromlist=["DATA_FILE", "CONFIG_FILE"])
        self.data_file = data_file or getattr(store_module, "DATA_FILE", DATA_FILE)
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
            float(item.get("audience_fit_score", 0) or 0),
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
                        "audience_fit": float(event.get("audience_fit_score", 0) or 0),
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
        return [
            *collect_backend_status(state["channels"]["wechat"], state["browser"]["wechat"]),
            *collect_douyin_backend_status(state["channels"]["douyin"], state["browser"]["douyin"]),
        ]

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

    @staticmethod
    def _agent_html_history_expires_at(now: datetime | None = None) -> str:
        baseline = now or datetime.now(UTC)
        return (baseline + timedelta(days=7)).replace(microsecond=0).isoformat()

    def _prune_agent_html_event_history(
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
        kept.sort(key=lambda item: parse_time(item.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return kept

    @staticmethod
    def _agent_html_extract_attr(tag_html: str, attr: str) -> str:
        match = re.search(rf'{re.escape(attr)}=["\']([^"\']+)["\']', tag_html, flags=re.I)
        return str(match.group(1)).strip() if match else ""

    @staticmethod
    def _agent_html_strip_tags(html: str) -> str:
        parser = _AgentHtmlTextExtractor()
        parser.feed(str(html or ""))
        return re.sub(r"\s+", " ", parser.text()).strip()

    def _agent_html_build_ai_discovery_messages(self, target: dict[str, Any], html: str) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "你是网页列表抽取器。请从品牌新闻/博客列表页中抽取文章候选项，并严格返回 JSON 数组。"
                    "每项字段仅允许：title, link, published_at, summary。不要输出解释。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "brand": target.get("brand"),
                        "name": target.get("name"),
                        "entry_url": target.get("entry_url"),
                        "html": str(html or "")[:18000],
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def _agent_html_parse_candidates_with_ai(
        self,
        state: dict[str, Any],
        target: dict[str, Any],
        html: str,
    ) -> list[dict[str, Any]]:
        llm_service = self._make_llm_service(state)
        if not llm_service:
            return []
        try:
            result = llm_service.generate("article", self._agent_html_build_ai_discovery_messages(target, html), temperature=0.1, max_tokens=1200, timeout=60.0)
            payload = _extract_json_payload(str(result.get("content") or ""))
        except Exception:
            return []
        if not isinstance(payload, list):
            return []
        discovered: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            link = urljoin(str(target.get("entry_url") or ""), str(item.get("link") or "").strip())
            if not link:
                continue
            title = self._agent_html_clean_text(item.get("title") or "")
            if not title:
                continue
            discovered.append(
                {
                    "title": title,
                    "link": link,
                    "published_at": str(item.get("published_at") or "").strip() or None,
                    "summary": self._agent_html_clean_text(item.get("summary") or ""),
                }
            )
        return discovered

    def _agent_html_parse_candidates_with_rules(
        self,
        entry_url: str,
        html: str,
        rules: dict[str, Any],
    ) -> list[dict[str, Any]]:
        html_text = str(html or "")
        link_selector = str(rules.get("link_selector") or "").strip()
        allow_patterns = [str(item).strip() for item in rules.get("link_allow_patterns", []) if str(item).strip()]
        deny_patterns = [str(item).strip() for item in rules.get("link_deny_patterns", []) if str(item).strip()]
        tags = re.findall(r"<a\b[^>]*href=[\"'][^\"']+[\"'][^>]*>[\s\S]*?</a>", html_text, flags=re.I)
        discovered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tag in tags:
            classes = self._agent_html_extract_attr(tag, "class")
            if link_selector and link_selector.startswith("."):
                required_class = link_selector[1:]
                if required_class not in classes.split():
                    continue
            href = urljoin(entry_url, self._agent_html_extract_attr(tag, "href"))
            canonical = canonicalize_url(href)
            identity = canonical or href
            if not href or identity in seen:
                continue
            if allow_patterns and not any(re.search(pattern, href, flags=re.I) for pattern in allow_patterns):
                continue
            if deny_patterns and any(re.search(pattern, href, flags=re.I) for pattern in deny_patterns):
                continue
            title = self._agent_html_strip_tags(tag)
            if len(title) < 8:
                continue
            seen.add(identity)
            discovered.append(
                {
                    "title": title,
                    "link": href,
                    "published_at": None,
                    "summary": "",
                }
            )
        return discovered[:30]

    def _agent_html_fetch_page(self, url: str, *, timeout_seconds: float = 15.0) -> tuple[dict[str, Any], str]:
        result = fetch_and_extract_link({"link": url, "title": "", "source_key": "agent_html", "source_name": "Agent HTML"}, timeout_seconds=timeout_seconds)
        html_result = {
            "url": url,
            "canonical_url": str(result.get("canonical_link") or url),
            "fetch_status": str(result.get("fetch_status") or "fetch_failed"),
            "error": result.get("error"),
            "title": str(result.get("title") or ""),
            "published_at": result.get("published_at"),
        }
        return html_result, str(result.get("cleaned_full_text") or "")

    def _agent_html_raw_html_fetch(self, url: str, *, timeout_seconds: float = 15.0) -> tuple[dict[str, Any], str]:
        import httpx

        meta = {"url": url, "fetch_status": "fetch_failed", "status_code": None, "content_type": None, "error": None, "final_url": url}
        try:
            with httpx.Client(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                },
                follow_redirects=True,
                timeout=timeout_seconds,
            ) as client:
                response = client.get(url)
            meta["status_code"] = response.status_code
            meta["content_type"] = str(response.headers.get("content-type") or "")
            meta["final_url"] = str(response.url)
            if response.status_code >= 400:
                meta["error"] = f"HTTP {response.status_code}"
                return meta, ""
            meta["fetch_status"] = "fetched"
            return meta, response.text
        except Exception as exc:  # noqa: BLE001
            meta["error"] = str(exc)
            return meta, ""

    def _agent_html_collect_candidates(
        self,
        state: dict[str, Any],
        target: dict[str, Any],
        html: str,
    ) -> tuple[list[dict[str, Any]], bool]:
        rules = target.get("discovery_rules", {}) if isinstance(target.get("discovery_rules"), dict) else {}
        discovered = self._agent_html_parse_candidates_with_rules(str(target.get("entry_url") or ""), html, rules)
        ai_used = False
        mode = str(target.get("discover_mode") or "rule_with_ai_fallback")
        if mode == "ai_only":
            discovered = []
        if mode in {"rule_with_ai_fallback", "ai_only"} and len(discovered) < 2:
            ai_candidates = self._agent_html_parse_candidates_with_ai(state, target, html)
            if ai_candidates:
                ai_used = True
                discovered = ai_candidates
        return discovered, ai_used

    @staticmethod
    def _agent_html_is_article_candidate(candidate: dict[str, Any], target: dict[str, Any]) -> bool:
        link = str(candidate.get("link") or "").strip().lower()
        title = str(candidate.get("title") or "").strip().lower()
        if not link:
            return False
        deny_patterns = [
            r"/category/",
            r"/categories/",
            r"/tag/",
            r"/tags/",
            r"/author/",
            r"/authors/",
            r"/search",
            r"/sp\?",
            r"/video",
            r"/videos",
            r"/podcast",
            r"/fast-facts",
            r"/select-newsroom",
            r"/media-library",
            r"/medialibrary/",
            r"/shop",
            r"/store",
        ]
        if any(re.search(pattern, link, flags=re.I) for pattern in deny_patterns):
            return False
        if title and re.search(r"search|category|tag|video|podcast|fast-facts|select newsroom|media library|shop|store", title, flags=re.I):
            return False
        target_type = str(target.get("target_type") or "")
        if target_type in {"newsroom", "blog", "press"}:
            positive = [
                r"/news/",
                r"/blog/",
                r"/post/",
                r"/posts/",
                r"/article",
                r"/articles/",
                r"/story/",
                r"/stories/",
                r"\.html?$",
                r"/\d{4}/",
            ]
            return any(re.search(pattern, link, flags=re.I) for pattern in positive)
        return True

    def _agent_html_map_document_to_raw_item(
        self,
        target: dict[str, Any],
        document: dict[str, Any],
        revision: dict[str, Any],
    ) -> dict[str, Any]:
        source_key = f"html-{str(target.get('id') or '').strip()}"
        title = str(document.get("title") or revision.get("title") or "").strip()
        canonical_link = str(document.get("canonical_url") or revision.get("source_url") or "").strip()
        content = str(revision.get("content_text") or "").strip()
        summary = str(revision.get("excerpt") or "").strip()[:320]
        published_at = str(revision.get("published_at") or document.get("published_at") or revision.get("fetched_at") or now_iso())
        collected_at = str(revision.get("fetched_at") or now_iso())
        return {
            "id": f"raw-html-{document.get('id')}-{revision.get('id')}",
            "source_key": source_key,
            "source_name": str(target.get("name") or target.get("brand") or "Agent HTML"),
            "source_kind": "page",
            "title": title,
            "link": canonical_link,
            "published_at": published_at,
            "collected_at": collected_at,
            "summary": summary,
            "content": content[:8000],
            "author": "",
            "tags": [item for item in [str(target.get("brand") or "").strip(), "agent-html"] if item],
            "engagement": {"score": 180},
            "metadata": {
                "collector": "agent_html",
                "original_link": str(revision.get("source_url") or canonical_link),
                "canonical_link": canonical_link,
                "extract_status": str(document.get("extractor") or revision.get("extractor") or ""),
                "fetch_status": "fetched",
                "word_count": int(revision.get("word_count", 0) or 0),
                "content_hash": str(revision.get("content_hash") or ""),
                "document_revision_id": str(revision.get("id") or ""),
                "html_target_id": str(target.get("id") or ""),
                "html_document_id": str(document.get("id") or ""),
            },
        }

    def _agent_html_build_discovery_item(
        self,
        target: dict[str, Any],
        run_id: str,
        candidate: dict[str, Any],
        *,
        content_hash: str = "",
        item_state: str = "new_item",
        document_id: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        link = str(candidate.get("link") or "").strip()
        canonical = canonicalize_url(link) or link
        dedupe_key = canonical or link
        return {
            "id": f"ahd-{uuid4().hex[:12]}",
            "target_id": str(target.get("id") or ""),
            "run_id": run_id,
            "source_name": str(target.get("name") or target.get("brand") or "Agent HTML"),
            "title": self._agent_html_clean_text(candidate.get("title") or ""),
            "summary": self._agent_html_clean_text(candidate.get("summary") or ""),
            "link": link,
            "canonical_link": canonical,
            "published_at": candidate.get("published_at"),
            "collected_at": now_iso(),
            "dedupe_key": dedupe_key,
            "content_hash": content_hash,
            "item_state": item_state,
            "document_id": document_id,
            "event_id": event_id,
            "metadata": {
                "target_brand": str(target.get("brand") or ""),
                "target_type": str(target.get("target_type") or ""),
            },
        }

    def _agent_html_similarity_tokens(self, text: str) -> set[str]:
        tokens = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", str(text or "").lower())
        return {token for token in tokens if len(token) >= 2}

    def _agent_html_group_event(self, state: dict[str, Any], target: dict[str, Any], discovery_item: dict[str, Any]) -> dict[str, Any]:
        brand = str(target.get("brand") or "").strip().lower()
        target_domain = self._agent_html_domain(str(target.get("entry_url") or ""))
        published_at = parse_time(discovery_item.get("published_at")) or parse_time(discovery_item.get("collected_at")) or datetime.now(UTC)
        title_tokens = self._agent_html_similarity_tokens(discovery_item.get("title") or "")
        event_candidates: list[dict[str, Any]] = []
        for event in state.get("agent_html_events", []):
            if not isinstance(event, dict):
                continue
            event_brand = str(event.get("tags", [""])[0] if event.get("tags") else "").lower()
            if brand and event_brand and event_brand != brand:
                continue
            if target_domain and self._agent_html_domain(str(event.get("representative_link") or "")) not in {"", target_domain}:
                continue
            event_last_seen = parse_time(event.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC)
            if abs((published_at - event_last_seen).total_seconds()) > 7 * 24 * 3600:
                continue
            event_tokens = self._agent_html_similarity_tokens(event.get("title") or "")
            overlap = len(title_tokens & event_tokens)
            if overlap >= 2:
                event_candidates.append(event)
        if event_candidates:
            event_candidates.sort(key=lambda item: parse_time(item.get("last_seen_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
            return event_candidates[0]
        return {
            "id": f"ahe-{uuid4().hex[:12]}",
            "title": str(discovery_item.get("title") or "未命名事件"),
            "summary": str(discovery_item.get("summary") or ""),
            "representative_document_id": discovery_item.get("document_id"),
            "representative_link": str(discovery_item.get("canonical_link") or discovery_item.get("link") or ""),
            "discovery_item_ids": [],
            "document_ids": [],
            "member_count": 0,
            "source_count": 0,
            "first_seen_at": discovery_item.get("collected_at"),
            "last_seen_at": discovery_item.get("collected_at"),
            "change_state": "new_event",
            "alert_state": "watch",
            "entity_names": [str(target.get("brand") or "")] if str(target.get("brand") or "").strip() else [],
            "tags": [str(target.get("brand") or "").strip()] if str(target.get("brand") or "").strip() else [],
        }

    def _refresh_agent_html_event_history(self, state: dict[str, Any], now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        now_stamp = now.replace(microsecond=0).isoformat()
        expires_at = self._agent_html_history_expires_at(now)
        history = self._prune_agent_html_event_history(state.get("agent_html_event_history", []), now=now)
        by_event = {str(item.get("event_id") or ""): item for item in history if isinstance(item, dict) and item.get("event_id")}
        current_events = {str(item.get("id") or ""): item for item in state.get("agent_html_events", []) if isinstance(item, dict) and item.get("id")}
        for event_id, event in current_events.items():
            existing = by_event.get(event_id)
            if existing:
                existing.update(
                    {
                        "title": str(event.get("title") or existing.get("title") or ""),
                        "last_seen_at": str(event.get("last_seen_at") or now_stamp),
                        "expires_at": expires_at,
                        "status": "active" if str(event.get("alert_state") or "watch") != "cooling" else "cooled",
                        "latest_alert_state": str(event.get("alert_state") or "watch"),
                        "member_count": int(event.get("member_count", 0) or 0),
                        "source_count": int(event.get("source_count", 0) or 0),
                        "composite_score": float(event.get("member_count", 0) or 0),
                    }
                )
                continue
            history.append(
                {
                    "history_id": f"aheh-{uuid4().hex[:12]}",
                    "event_id": event_id,
                    "title": str(event.get("title") or ""),
                    "first_seen_at": str(event.get("first_seen_at") or now_stamp),
                    "last_seen_at": str(event.get("last_seen_at") or now_stamp),
                    "expires_at": expires_at,
                    "status": "active",
                    "latest_alert_state": str(event.get("alert_state") or "watch"),
                    "member_count": int(event.get("member_count", 0) or 0),
                    "source_count": int(event.get("source_count", 0) or 0),
                    "composite_score": float(event.get("member_count", 0) or 0),
                }
            )
        for item in history:
            event_id = str(item.get("event_id") or "")
            if event_id not in current_events:
                item["status"] = "cooled"
        state["agent_html_event_history"] = self._prune_agent_html_event_history(history, now=now)
