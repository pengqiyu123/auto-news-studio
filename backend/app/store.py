from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import time
import traceback
from pathlib import Path
import re
from threading import RLock, Thread
from typing import Any
from uuid import uuid4

from .composer import _markdown_to_html, _wechat_html, compose_draft
from .connectors import _collect_with_retry, collect_enabled_sources, collect_from_source
from .intel_pipeline import build_intel_state
from .llm import LLMService
from .legacy_sources import build_legacy_rss_sources
from .models import (
    AutomationMode,
    AutomationModeDefinition,
    AutomationModeProfile,
    BatchDraftResponse,
    BrowserSessionPayload,
    BrowserSessionState,
    CandidateTopic,
    ChannelConfigPayload,
    ChainStateCard,
    DashboardResponse,
    DashboardStats,
    DashboardTopBar,
    DraftItem,
    DiscoveryItem,
    ExecutionChainSnapshot,
    FreshnessSnapshot,
    GithubSignalItem,
    IntelAlert,
    IntelAlertsResponse,
    IntelEvent,
    IntelEventResponse,
    IntelEventsResponse,
    IntelOverviewSummary,
    IntelSummaryResponse,
    HotClusterCard,
    IntelSnapshot,
    IntelStreamItem,
    JobItem,
    LogItem,
    SchedulerStatus,
    ModeDefinition,
    PublishBackendStatus,
    PublishMode,
    PublishTask,
    ReferenceProject,
    RuntimePlan,
    RuntimePlanPayload,
    SourceConnector,
    SourceConnectorPayload,
    CreateSourcePayload,
    SourceSyncResponse,
    WeChatChannelConfig,
)
from .pipeline import build_candidates, normalize_raw_items
from .publishers import (
    build_preview_url,
    build_wechat_draft_id,
    collect_backend_status,
    create_publish_task,
    default_browser_profile_path,
    ensure_channel_defaults,
    extract_wechat_appmsg_id,
    inspect_wechat_session,
    launch_wechat_dashboard,
    refresh_browser_session,
    run_browser_action,
)
from .reference_projects import write_reference_baseline
from .sources import discover_sources


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "state.json"
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
RUN_STALE_SECONDS = 180


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


def default_image_slots(draft: dict[str, Any]) -> list[dict[str, Any]]:
    title = str(draft.get("title") or "").strip()
    return [
        {
            "slot_id": "hero",
            "label": "头图",
            "position": "lead",
            "suggestion": "请补一张与主题直接相关的头图后再走预览或发表。",
            "required_image": True,
            "fulfilled": False,
            "keywords": [title] if title else [],
        }
    ]


def legacy_body_blocks(draft: dict[str, Any]) -> list[dict[str, Any]]:
    markdown = str(draft.get("markdown") or "").strip()
    if not markdown:
        summary = str(draft.get("summary") or "").strip()
        if not summary:
            return []
        return [{"kind": "intro", "content": summary, "evidence_links": list(draft.get("evidence_links", [])), "required_image": True}]
    blocks: list[dict[str, Any]] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            if current_lines:
                blocks.append(
                    {
                        "kind": "section",
                        "heading": current_heading,
                        "content": "\n".join(current_lines).strip(),
                        "evidence_links": list(draft.get("evidence_links", []))[:2],
                        "required_image": current_heading in {None, "正文初稿"},
                    }
                )
                current_lines = []
            current_heading = line[3:].strip()
            continue
        current_lines.append(line)
    if current_lines:
        blocks.append(
            {
                "kind": "section",
                "heading": current_heading,
                "content": "\n".join(current_lines).strip(),
                "evidence_links": list(draft.get("evidence_links", []))[:2],
                "required_image": current_heading in {None, "正文初稿"},
            }
        )
    return blocks


def legacy_brief(draft: dict[str, Any]) -> dict[str, Any]:
    trace = draft.get("composition_trace", {}) if isinstance(draft.get("composition_trace"), dict) else {}
    facts = [str(item).strip() for item in trace.get("facts", []) if str(item).strip()]
    return {
        "headline": draft.get("title", ""),
        "one_line": draft.get("summary", ""),
        "facts": facts,
        "evidence_links": list(draft.get("evidence_links", [])),
        "source_names": [],
        "source_count": int(draft.get("source_count", 0) or 0),
        "published_at": None,
        "collected_at": None,
        "event_judgement": "该稿件来自旧版生成器，建议重新生成后再发布。",
        "risk_notes": list(draft.get("risk_flags", [])),
        "time_context": {
            "published_at_label": "发布时间未知",
            "collected_at_label": "采集时间未知",
        },
    }


def automation_to_publish_mode(mode: str) -> str:
    if mode == "full_pipeline":
        return "draft_preview_browser"
    return "draft_only"


MODE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "draft_only",
        "label": "仅初稿",
        "description": "先采集、先写初稿、允许排入微信草稿队列，但不自动预览、不自动发送。",
        "auto_collect": True,
        "auto_draft": True,
        "sync_to_wechat_draft": True,
        "auto_open_preview": False,
        "requires_human_review": True,
        "allow_auto_send": False,
        "allow_auto_retry": True,
    },
    {
        "key": "draft_and_preview",
        "label": "草稿加预览",
        "description": "自动准备系统草稿和预览入口，人工看过后再决定是否推进。",
        "auto_collect": True,
        "auto_draft": True,
        "sync_to_wechat_draft": True,
        "auto_open_preview": True,
        "requires_human_review": True,
        "allow_auto_send": False,
        "allow_auto_retry": True,
    },
    {
        "key": "draft_preview_browser",
        "label": "草稿加浏览器预览",
        "description": "自动打开公众号后台和预览链路，但不自动点击最终发布。",
        "auto_collect": True,
        "auto_draft": True,
        "sync_to_wechat_draft": True,
        "auto_open_preview": True,
        "requires_human_review": True,
        "allow_auto_send": False,
        "allow_auto_retry": True,
    },
    {
        "key": "auto_send_guarded",
        "label": "自动发送(带守卫)",
        "description": "通过审核、风控和浏览器健康检查后，允许进入自动发布尝试。",
        "auto_collect": True,
        "auto_draft": True,
        "sync_to_wechat_draft": True,
        "auto_open_preview": True,
        "requires_human_review": True,
        "allow_auto_send": True,
        "allow_auto_retry": True,
    },
    {
        "key": "full_auto",
        "label": "全自动",
        "description": "保留接口用于后续扩展，不作为当前默认运行档位。",
        "auto_collect": True,
        "auto_draft": True,
        "sync_to_wechat_draft": True,
        "auto_open_preview": True,
        "requires_human_review": False,
        "allow_auto_send": True,
        "allow_auto_retry": True,
    },
]

AUTOMATION_MODE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "radar_only",
        "label": "雷达捕获",
        "description": "只做信息发现、标准化和候选池更新，不自动成稿，也不触发微信链路。",
        "auto_collect": True,
        "auto_generate_candidates": True,
        "auto_generate_drafts": False,
        "auto_publish_enabled": False,
        "available": True,
    },
    {
        "key": "radar_and_draft",
        "label": "稿件撰写",
        "description": "持续抓取、自动成稿，并按设置决定先留在项目本地还是同步进微信公众号草稿箱。",
        "auto_collect": True,
        "auto_generate_candidates": True,
        "auto_generate_drafts": True,
        "auto_publish_enabled": False,
        "available": True,
    },
    {
        "key": "full_pipeline",
        "label": "自动全流程",
        "description": "从抓取、成稿、微信草稿箱到受控发表的完整链路，适合做定时运营策略。",
        "auto_collect": True,
        "auto_generate_candidates": True,
        "auto_generate_drafts": True,
        "auto_publish_enabled": True,
        "available": False,
    },
]

DEFAULT_AUTOMATION_PROFILES: list[dict[str, Any]] = [
    {
        "mode": "radar_only",
        "collect_interval_minutes": 30,
        "draft_trigger": "manual",
        "draft_schedule_time": None,
        "draft_delivery": "local_only",
        "draft_selection": "top_scored",
        "draft_limit": 8,
        "publish_strategy": "disabled",
        "publish_schedule_time": None,
        "require_approval": True,
        "notes": "适合先把消息抓全、看全，不自动成稿。",
    },
    {
        "mode": "radar_and_draft",
        "collect_interval_minutes": 20,
        "draft_trigger": "after_sync",
        "draft_schedule_time": None,
        "draft_delivery": "local_only",
        "draft_selection": "top_scored",
        "draft_limit": 6,
        "publish_strategy": "wechat_draft_only",
        "publish_schedule_time": "10:30",
        "require_approval": True,
        "notes": "适合自动搜集后快速出稿，默认先留在项目本地，可切到微信草稿箱。",
    },
    {
        "mode": "full_pipeline",
        "collect_interval_minutes": 15,
        "draft_trigger": "scheduled",
        "draft_schedule_time": "09:30",
        "draft_delivery": "wechat_draft",
        "draft_selection": "top_scored",
        "draft_limit": 4,
        "publish_strategy": "guarded_send",
        "publish_schedule_time": "18:00",
        "require_approval": True,
        "notes": "适合固定时间批量运营，首版仍建议保留人工审核守卫。",
    },
]

DEFAULT_LLM_PROFILES: list[dict[str, Any]] = [
    {
        "id": "nvidia-qwen35-122b",
        "label": "NVIDIA Qwen 122B",
        "description": "主力强模型，实测连通快，适合优先做正式稿。",
        "provider_key": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key": "",
        "model_id": "qwen/qwen3.5-122b-a10b",
        "enabled": False,
    },
    {
        "id": "nvidia-glm47",
        "label": "NVIDIA GLM 4.7",
        "description": "NVIDIA 通道下的 GLM 备选，实测可用且响应很快。",
        "provider_key": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key": "",
        "model_id": "z-ai/glm4.7",
        "enabled": False,
    },
    {
        "id": "nvidia-minimax-m27",
        "label": "NVIDIA MiniMax M2.7",
        "description": "实测可用，但接近 10 秒边界，适合作为额外备选。",
        "provider_key": "nvidia",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key": "",
        "model_id": "minimaxai/minimax-m2.7",
        "enabled": False,
    },
    {
        "id": "siliconflow-glm4-9b",
        "label": "SiliconFlow GLM 4 9B",
        "description": "免费且快，适合做稳态兜底。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": "THUDM/GLM-4-9B-0414",
        "enabled": False,
    },
    {
        "id": "siliconflow-glmz1-9b",
        "label": "SiliconFlow GLM Z1 9B",
        "description": "免费备选，实测连通和速度都不错。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": "THUDM/GLM-Z1-9B-0414",
        "enabled": False,
    },
    {
        "id": "siliconflow-deepseek-r1-qwen3-8b",
        "label": "SiliconFlow DeepSeek R1 Qwen3 8B",
        "description": "免费推理型备选，适合做判断和摘要。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        "enabled": False,
    },
    {
        "id": "siliconflow-qwen3-8b",
        "label": "SiliconFlow Qwen3 8B",
        "description": "免费通用备选，适合快速切换测试。",
        "provider_key": "siliconflow",
        "base_url": "https://api.siliconflow.cn/v1",
        "api_key": "",
        "model_id": "Qwen/Qwen3-8B",
        "enabled": False,
    },
]

DEFAULT_LLM_TASK_TEMPLATE: list[dict[str, Any]] = [
    {"task_key": "judgement", "label": "初步判断", "temperature": 0.2, "max_tokens": 2048},
    {"task_key": "outline", "label": "写作提纲", "temperature": 0.4, "max_tokens": 2048},
    {"task_key": "article", "label": "正文生成", "temperature": 0.7, "max_tokens": 4096},
    {"task_key": "title", "label": "标题润色", "temperature": 0.8, "max_tokens": 512},
    {"task_key": "summary", "label": "摘要生成", "temperature": 0.5, "max_tokens": 1024},
]


def build_provider_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": str(profile.get("provider_key") or "").strip(),
        "label": str(profile.get("label") or "").strip(),
        "base_url": str(profile.get("base_url") or "").strip(),
        "api_key": str(profile.get("api_key") or "").strip(),
        "model_id": str(profile.get("model_id") or "").strip(),
        "enabled": bool(profile.get("enabled")) and bool(str(profile.get("api_key") or "").strip()),
        "last_tested_at": profile.get("last_tested_at"),
        "last_test_result": profile.get("last_test_result"),
    }


def build_tasks_from_profile(profile: dict[str, Any]) -> list[dict[str, Any]]:
    provider_key = str(profile.get("provider_key") or "").strip()
    model_id = str(profile.get("model_id") or "").strip()
    return [
        {
            **task,
            "provider_key": provider_key if bool(profile.get("enabled")) and model_id else "",
            "model_id": model_id if bool(profile.get("enabled")) else "",
        }
        for task in deepcopy(DEFAULT_LLM_TASK_TEMPLATE)
    ]


def default_llm_state() -> dict[str, Any]:
    profiles = deepcopy(DEFAULT_LLM_PROFILES)
    current_profile_id = profiles[0]["id"] if profiles else ""
    active_profile = next((item for item in profiles if item["id"] == current_profile_id), {})
    return {
        "current_profile_id": current_profile_id,
        "profiles": profiles,
        "providers": [build_provider_from_profile(active_profile)] if active_profile else [],
        "tasks": build_tasks_from_profile(active_profile) if active_profile else [],
        "usage_today": {},
    }


def merge_llm_profiles(
    incoming_profiles: list[dict[str, Any]],
    existing_profiles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    existing_by_id = {
        str(item.get("id")): deepcopy(item)
        for item in (existing_profiles or [])
        if isinstance(item, dict) and item.get("id")
    }
    merged_by_id: dict[str, dict[str, Any]] = {
        item["id"]: {**item, **existing_by_id.get(item["id"], {})}
        for item in deepcopy(DEFAULT_LLM_PROFILES)
    }
    for item in incoming_profiles:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        profile_id = str(item["id"])
        profile = {**merged_by_id.get(profile_id, {}), **deepcopy(item)}
        existing = existing_by_id.get(profile_id, {})
        api_key = str(profile.get("api_key") or "").strip()
        if "****" in api_key and existing:
            profile["api_key"] = str(existing.get("api_key") or "")
        merged_by_id[profile_id] = profile

    provider_keys: dict[str, str] = {}
    for profile in list(merged_by_id.values()) + list(existing_by_id.values()):
        provider_key = str(profile.get("provider_key") or "").strip()
        api_key = str(profile.get("api_key") or "").strip()
        if provider_key and api_key and "****" not in api_key:
            provider_keys[provider_key] = api_key

    for profile in merged_by_id.values():
        provider_key = str(profile.get("provider_key") or "").strip()
        if provider_key and not str(profile.get("api_key") or "").strip():
            profile["api_key"] = provider_keys.get(provider_key, "")
        profile["enabled"] = bool(profile.get("enabled")) and bool(str(profile.get("api_key") or "").strip())

    return list(merged_by_id.values())


def _rss(
    key: str,
    name: str,
    url: str,
    *,
    priority: int = 7,
    schedule: str = "*/30 * * * *",
    enabled: bool = True,
    tags: list[str] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "kind": "rss",
        "driver": "feedparser",
        "enabled": enabled,
        "schedule": schedule,
        "priority": priority,
        "auth": {},
        "url": url,
        "tags": tags or [language],
        "capabilities": ["rss"],
        "origin_repo": "curated",
        "origin_license": "rss",
        "health_status": "idle",
        "health_detail": "等待首次同步",
        "item_count": 0,
        "last_synced_at": None,
        "last_error": None,
        "updated_at": None,
    }


def _api_source(
    key: str,
    name: str,
    driver: str,
    *,
    url: str | None = None,
    priority: int = 7,
    schedule: str = "*/30 * * * *",
    enabled: bool = True,
    tags: list[str] | None = None,
    auth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "name": name,
        "kind": driver.split("_")[0],
        "driver": driver,
        "enabled": enabled,
        "schedule": schedule,
        "priority": priority,
        "auth": auth or {},
        "url": url,
        "tags": tags or ["api"],
        "capabilities": ["api"],
        "origin_repo": "curated",
        "origin_license": "api",
        "health_status": "idle",
        "health_detail": "等待首次同步",
        "item_count": 0,
        "last_synced_at": None,
        "last_error": None,
        "updated_at": None,
    }


DEFAULT_SOURCES: list[dict[str, Any]] = [
    # ── AI / LLM 厂商官方博客（英文，优先级最高） ──
    _rss("rss-openai", "OpenAI Blog", "https://openai.com/blog/rss.xml", priority=9, tags=["ai", "models"]),
    _rss("rss-anthropic", "Anthropic News", "https://www.anthropic.com/news/rss.xml", priority=9, tags=["ai", "safety"]),
    _rss("rss-google-ai", "Google AI Blog", "https://blog.google/technology/ai/rss/", priority=9, tags=["ai", "google"]),
    _rss("rss-deepmind", "DeepMind Blog", "https://deepmind.google/blog/rss.xml", priority=9, tags=["ai", "research"]),
    _rss("rss-huggingface", "Hugging Face Blog", "https://huggingface.co/blog/feed.xml", priority=8, tags=["ai", "oss"]),
    _rss("rss-openai-cookbook", "OpenAI Cookbook", "https://cookbook.openai.com/rss.xml", priority=8, tags=["ai", "dev"]),
    _rss("rss-meta-ai", "Meta AI Blog", "https://ai.meta.com/blog/rss/", priority=8, tags=["ai", "meta"]),
    _rss("rss-nvidia-ai", "NVIDIA AI Blog", "https://blogs.nvidia.com/feed/", priority=8, tags=["ai", "chip"]),
    _rss("rss-mistral", "Mistral AI Blog", "https://mistral.ai/news/feed.xml", priority=8, tags=["ai", "europe"]),
    # ── 英文科技媒体 ──
    _rss("rss-techcrunch", "TechCrunch", "https://techcrunch.com/feed/", priority=8, schedule="*/20 * * * *"),
    _rss("rss-theverge", "The Verge", "https://www.theverge.com/rss/index.xml", priority=8),
    _rss("rss-arstechnica", "Ars Technica", "https://feeds.arstechnica.com/arstechnica/features", priority=8),
    _rss("rss-wired", "Wired", "https://www.wired.com/feed/rss", priority=7),
    _rss("rss-mit-tech", "MIT Technology Review", "https://www.technologyreview.com/feed/", priority=8, tags=["ai", "research"]),
    _rss("rss-github-blog", "GitHub Blog", "https://github.blog/feed/", priority=7, tags=["oss", "github"]),
    _rss("rss-hn-front", "Hacker News (RSS)", "https://hnrss.org/frontpage", priority=8, tags=["community", "hn"]),
    # ── 中文科技媒体 ──
    _rss("rss-36kr", "36氪", "https://36kr.com/feed", priority=8, tags=["cn", "startup"], language="zh"),
    _rss("rss-sspai", "少数派", "https://sspai.com/feed", priority=7, tags=["cn", "digital"], language="zh"),
    _rss("rss-jiqizhixin", "机器之心", "https://www.jiqizhixin.com/rss", priority=8, tags=["cn", "ai"], language="zh"),
    _rss("rss-ithome", "IT之家", "https://www.ithome.com/rss/", priority=7, tags=["cn", "tech"], language="zh"),
    _rss("rss-ifanr", "爱范儿", "https://www.ifanr.com/feed", priority=7, tags=["cn", "digital"], language="zh"),
    _rss("rss-ruanyifeng", "阮一峰的网络日志", "https://www.ruanyifeng.com/blog/atom.xml", priority=6, tags=["cn", "dev"], language="zh"),
    # ── AI/ML 研究前沿 ──
    _rss("rss-arxiv-cs-ai", "arXiv CS.AI", "http://export.arxiv.org/rss/cs.AI", priority=7, tags=["research", "arxiv"]),
    _rss("rss-arxiv-cs-cl", "arXiv CS.CL (NLP)", "http://export.arxiv.org/rss/cs.CL", priority=7, tags=["research", "nlp"]),
    _rss("rss-arxiv-cs-cv", "arXiv CS.CV", "http://export.arxiv.org/rss/cs.CV", priority=7, tags=["research", "vision"]),
    _rss("rss-distill", "Distill.pub", "https://distill.pub/feed.xml", priority=7, tags=["research", "viz"]),
    # ── Reddit 社区（JSON API） ──
    _api_source("reddit-chatgpt", "Reddit r/ChatGPT", "reddit_hot", priority=7, tags=["community", "ai"], auth={"subreddit": "ChatGPT"}),
    _api_source("reddit-claudeai", "Reddit r/ClaudeAI", "reddit_hot", priority=7, tags=["community", "ai"], auth={"subreddit": "ClaudeAI"}),
    _api_source("reddit-local-llama", "Reddit r/LocalLLaMA", "reddit_hot", priority=6, tags=["community", "oss"], auth={"subreddit": "LocalLLaMA"}),
    _api_source("reddit-machinelearning", "Reddit r/MachineLearning", "reddit_hot", priority=7, tags=["community", "research"], auth={"subreddit": "MachineLearning"}),
    _api_source("reddit-singularity", "Reddit r/singularity", "reddit_hot", priority=6, tags=["community", "future"], auth={"subreddit": "singularity"}),
    # ── API / 爬虫数据源 ──
    _api_source("hn-frontpage", "Hacker News Front Page", "hackernews_frontpage", priority=8, tags=["community", "hn"]),
    _api_source("github-trending", "GitHub Trending", "github_trending", priority=7, tags=["oss", "github"]),
    _api_source("vvhan-hotlist", "VVhan 热榜聚合", "vvhan_hotlist", priority=7, schedule="*/15 * * * *", tags=["cn", "hot"]),
    # ── RSSHub 路由（中文社交平台，依赖 rsshub.app 公共实例） ──
    _rss("rsshub-weibo-hot", "微博热搜 (RSSHub)", "https://rsshub.app/weibo/hot", priority=7, schedule="*/15 * * * *", tags=["cn", "weibo"], language="zh"),
    _rss("rsshub-zhihu-hot", "知乎热榜 (RSSHub)", "https://rsshub.app/zhihu/hotlist", priority=7, schedule="*/15 * * * *", tags=["cn", "zhihu"], language="zh"),
    _rss("rsshub-juejin-trend", "掘金前端趋势 (RSSHub)", "https://rsshub.app/juejin/trending/frontend/monthly", priority=6, schedule="0 */4 * * *", tags=["cn", "dev"], language="zh"),
    _rss("rsshub-github-trending", "GitHub Trending (RSSHub)", "https://rsshub.app/github/trending/daily", priority=7, tags=["oss", "github"]),
    _rss("rsshub-producthunt", "Product Hunt (RSSHub)", "https://rsshub.app/producthunt/daily", priority=6, tags=["startup", "product"]),
]


JOB_LABELS = {
    "collect_news": "雷达获取",
    "rebuild_candidates": "重建候选池",
    "build_digest": "批量生成初稿",
    "sync_wechat_draft": "同步微信草稿",
    "open_preview": "准备网页预览",
    "publish_pipeline": "执行浏览器发布链",
    "check_browser": "检查浏览器会话",
}


class StudioStore:
    def __init__(self, data_file: Path = DATA_FILE):
        self.data_file = data_file
        self._lock = RLock()
        self._progress_snapshot: dict[str, Any] = {
            "percent": 0, "done": 0, "total": 0,
            "label": None, "cycle": "idle",
            "cycle_started_at": None,
        }
        self._completion_hold_until: float = 0.0
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_file.exists():
            self._write(self._bootstrap_state())
            return
        state = self._upgrade_state(self._read())
        required_keys = {"current_mode", "sources", "channels", "browser", "reference_projects"}
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

    def _bootstrap_state(self) -> dict[str, Any]:
        reference_projects = write_reference_baseline()
        sources = self._build_source_registry()
        state = {
            "automation_mode": "radar_only",
            "current_mode": "draft_only",
            "automation_mode_definitions": deepcopy(AUTOMATION_MODE_DEFINITIONS),
            "automation_profiles": deepcopy(DEFAULT_AUTOMATION_PROFILES),
            "mode_definitions": deepcopy(MODE_DEFINITIONS),
            "sources": sources,
            "raw_items": [],
            "discovery_items": [],
            "intel_events": [],
            "event_snapshots": [],
            "intel_alerts": [],
            "normalized_items": [],
            "candidates": [],
            "drafts": [],
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
                }
            },
            "llm": default_llm_state(),
            "settings": {
                "max_workers": 8,
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
                "last_candidate_at": None,
                "last_draft_at": None,
                "next_collect_at": None,
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
                "last_successful_sync_at": None,
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
                },
            },
        }
        self._append_log(
            state,
            "info",
            "system",
            "已完成 Auto News Studio 初始化，当前未自动抓取素材，也未自动生成稿件。",
            stream="system_runtime",
        )
        return state

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

        candidates = build_candidates(normalized, state.get("current_mode", "draft_only"))
        candidate_ids = {item["id"] for item in candidates}

        drafts_before = list(state.get("drafts", []))
        drafts: list[dict[str, Any]] = []
        for draft in drafts_before:
            if draft.get("candidate_topic_id") not in candidate_ids:
                continue
            if (
                _contains_synthetic_marker(draft.get("evidence_links"))
                or _contains_synthetic_marker(draft.get("markdown"))
                or _contains_synthetic_marker(draft.get("brief"))
                or _contains_synthetic_marker(draft.get("composition_trace"))
            ):
                continue
            drafts.append(draft)

        draft_candidate_ids = {draft["candidate_topic_id"] for draft in drafts}
        for candidate in candidates:
            candidate["draft_exists"] = candidate["id"] in draft_candidate_ids
            if candidate["draft_exists"]:
                candidate["status"] = "drafted"

        kept_draft_ids = {draft["id"] for draft in drafts}
        publish_tasks = [task for task in state.get("publish_tasks", []) if task.get("draft_id") in kept_draft_ids]
        logs = [
            log
            for log in state.get("logs", [])
            if not _contains_synthetic_marker(log.get("message")) and not _contains_synthetic_marker(log.get("detail"))
        ]
        jobs = [job for job in state.get("jobs", []) if not _contains_synthetic_marker(job.get("message"))]

        removed_drafts = len(drafts_before) - len(drafts)
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
        state["candidates"] = candidates
        state["drafts"] = drafts
        state["publish_tasks"] = publish_tasks
        state["logs"] = logs
        state["jobs"] = jobs

        if removed_raw or removed_drafts or removed_logs:
            self._append_log(
                state,
                "warning",
                "cleanup",
                f"已清理历史伪造数据：删除 {removed_raw} 条伪素材、{removed_drafts} 篇关联稿件。",
                stream="system_runtime",
                actor="system",
            )

    def _read(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(self.data_file.read_text(encoding="utf-8"))

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
        self._prune_unsupported_sources(state)
        state.setdefault("llm", default_llm_state())
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
        if active_profile:
            active_profile["enabled"] = bool(str(active_profile.get("api_key") or "").strip()) and bool(active_profile.get("enabled"))
            llm["providers"] = [build_provider_from_profile(active_profile)]
            llm["tasks"] = build_tasks_from_profile(active_profile)
        else:
            llm["providers"] = []
            llm["tasks"] = []
        llm.setdefault("usage_today", {})
        state.setdefault("automation_mode", "radar_only")
        state.setdefault("automation_mode_definitions", deepcopy(AUTOMATION_MODE_DEFINITIONS))
        state.setdefault("automation_profiles", deepcopy(DEFAULT_AUTOMATION_PROFILES))
        state.setdefault("discovery_items", [])
        state.setdefault("intel_events", [])
        state.setdefault("event_snapshots", [])
        state.setdefault("intel_alerts", [])
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
        raw_wechat_channel = dict(channels.setdefault("wechat", {}))
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
        runtime = state.setdefault("runtime", {})
        runtime.setdefault("scheduler_running", False)
        runtime.setdefault("control_state", "stopped")
        runtime.setdefault("launch_mode", "interval_now")
        runtime.setdefault("current_mode", state.get("automation_mode", "radar_only"))
        runtime.setdefault("work_scope", state.get("runtime_plan", {}).get("work_scope", "collect_events_alerts"))
        runtime.setdefault("last_collect_at", None)
        runtime.setdefault("last_candidate_at", None)
        runtime.setdefault("last_draft_at", None)
        runtime.setdefault("next_collect_at", None)
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
        runtime.setdefault("last_successful_sync_at", None)
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
        for candidate in state.get("candidates", []):
            candidate.setdefault("published_at", None)
            candidate.setdefault("collected_at", None)
            candidate.setdefault("freshness_bucket", "unknown")
            candidate.setdefault("draft_exists", False)
            candidate.setdefault("normalized_score", float(candidate.get("score", 0)))
        for draft in state.get("drafts", []):
            draft.setdefault("brief", legacy_brief(draft))
            draft.setdefault("outline", {
                "title_options": list(draft.get("title_options", [])),
                "lead_direction": str(draft.get("summary", "")),
                "key_points": list(draft.get("composition_trace", {}).get("facts", [])) if isinstance(draft.get("composition_trace"), dict) else [],
                "section_order": ["导语", "关键信息", "事件解读", "影响判断", "结尾"],
                "closing_line": "旧版稿件建议重新生成后再进入正式发布链路。",
            })
            draft.setdefault("article_variant", "flash_explainer")
            draft.setdefault("reader_summary", str(draft.get("summary", "")))
            draft.setdefault("body_blocks", legacy_body_blocks(draft))
            draft.setdefault("image_slots", default_image_slots(draft))
            draft.setdefault("editor_notes", ["这是旧版稿件，建议点击“重生成”切换到正式稿结构。"])
            draft.setdefault("wechat_draft_id", None)
            draft.setdefault("wechat_editor_url", None)
            draft.setdefault("wechat_remote_appmsg_id", None)
            draft.setdefault("preview_url", None)
            draft.setdefault("last_error", None)
            draft.setdefault("render_backend", "python-template")
            draft.setdefault("approval_required", True)
            draft.setdefault("composition_trace", {})
            if not draft.get("summary") and draft.get("reader_summary"):
                draft["summary"] = draft["reader_summary"]
            if not draft.get("brief"):
                draft["brief"] = legacy_brief(draft)
            if not draft.get("body_blocks"):
                draft["body_blocks"] = legacy_body_blocks(draft)
        profiles_by_mode = {item["mode"]: item for item in state.get("automation_profiles", []) if isinstance(item, dict)}
        merged_profiles: list[dict[str, Any]] = []
        for default_profile in deepcopy(DEFAULT_AUTOMATION_PROFILES):
            profile = profiles_by_mode.get(default_profile["mode"], {})
            merged = {**default_profile, **profile}
            merged_profiles.append(merged)
        state["automation_profiles"] = merged_profiles
        mode_defs_by_key = {item["key"]: item for item in state.get("automation_mode_definitions", []) if isinstance(item, dict)}
        merged_mode_defs: list[dict[str, Any]] = []
        for default_mode in deepcopy(AUTOMATION_MODE_DEFINITIONS):
            existing_mode = mode_defs_by_key.get(default_mode["key"], {})
            merged_mode_defs.append({**existing_mode, **default_mode})
        state["automation_mode_definitions"] = merged_mode_defs
        return state

    def _draft_image_blockers(self, draft: dict[str, Any]) -> list[str]:
        image_slots = draft.get("image_slots", [])
        if not isinstance(image_slots, list):
            return ["稿件图片槽位信息缺失，请重新生成稿件。"]
        pending = [
            slot for slot in image_slots
            if isinstance(slot, dict) and slot.get("required_image") and not slot.get("fulfilled")
        ]
        if not pending:
            return []
        labels = "、".join(str(slot.get("label") or "配图") for slot in pending)
        return [f"待补图：{labels} 尚未满足，当前不能进入微信预览或发表。"]

    def _mode_map(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {item["key"]: item for item in state["mode_definitions"]}

    def _current_mode_def(self, state: dict[str, Any]) -> dict[str, Any]:
        return self._mode_map(state)[state["current_mode"]]

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
        }

    def _runtime_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        runtime_plan = state.setdefault("runtime_plan", {})
        defaults = self._default_runtime_plan(state)
        for key, value in defaults.items():
            runtime_plan.setdefault(key, value)
        runtime_plan["timezone"] = str(runtime_plan.get("timezone") or "Asia/Shanghai")
        runtime_plan["launch_mode"] = str(runtime_plan.get("launch_mode") or "interval_now")
        runtime_plan["work_scope"] = str(runtime_plan.get("work_scope") or defaults["work_scope"])
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

    def _find_candidate(self, state: dict[str, Any], candidate_id: str) -> dict[str, Any]:
        for candidate in state["candidates"]:
            if candidate["id"] == candidate_id:
                return candidate
        raise ValueError(f"Candidate not found: {candidate_id}")

    def _find_draft(self, state: dict[str, Any], draft_id: str) -> dict[str, Any]:
        for draft in state["drafts"]:
            if draft["id"] == draft_id:
                return draft
        raise ValueError(f"Draft not found: {draft_id}")

    def _refresh_browser_session(self, state: dict[str, Any]) -> dict[str, Any]:
        current = state["browser"]["wechat"]
        channel = state["channels"]["wechat"]
        next_state = refresh_browser_session(channel, current)
        state["browser"]["wechat"] = next_state
        return next_state

    def _runtime(self, state: dict[str, Any]) -> dict[str, Any]:
        runtime = state.setdefault("runtime", {})
        runtime.setdefault("scheduler_running", False)
        runtime.setdefault("control_state", "stopped")
        runtime.setdefault("launch_mode", "interval_now")
        runtime.setdefault("current_mode", state.get("automation_mode", "radar_only"))
        runtime.setdefault("last_collect_at", None)
        runtime.setdefault("last_candidate_at", None)
        runtime.setdefault("last_draft_at", None)
        runtime.setdefault("next_collect_at", None)
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
        runtime.setdefault("last_successful_sync_at", None)
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

    def _start_runtime_run(self, runtime: dict[str, Any], *, stage: str, triggered_by: str, now: datetime | None = None) -> dict[str, Any]:
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
            now=now,
        )
        runtime["last_error"] = str(run.get("error") or f"轮次 {recovered_run_id or 'unknown'} 超时未完成，已标记异常。")
        runtime["current_cycle"] = "failed"
        runtime["current_cycle_progress_label"] = runtime["last_error"]
        runtime["control_state"] = "waiting" if runtime.get("scheduler_running") else "stopped"
        self._progress_snapshot["cycle"] = "failed"
        self._progress_snapshot["label"] = runtime["last_error"]
        self._append_log(
            state,
            "warning",
            "runtime",
            f"检测到异常轮次并已接管：{recovered_run_id or 'unknown'}",
            stream="system_runtime",
            actor=actor,
            detail=runtime["last_error"],
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

    def _project_candidates_from_events(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        normalized_by_event = {item.get("cluster_id"): item for item in state.get("normalized_items", [])}
        watched_events = [
            event for event in state.get("intel_events", [])
            if event.get("watchlisted") and not event.get("ignored")
        ]
        draft_candidate_ids = {draft["candidate_topic_id"] for draft in state["drafts"]}
        candidates: list[dict[str, Any]] = []
        for event in watched_events:
            normalized = normalized_by_event.get(event["id"])
            if not normalized:
                continue
            candidate_id = f"cand-{event['id']}"
            candidates.append(
                {
                    "id": candidate_id,
                    "normalized_item_id": normalized["id"],
                    "title": event["title"],
                    "summary": event.get("summary", ""),
                    "recommended_angle": "持续追踪事件变化、平台扩散和下一步影响。",
                    "article_type": "专题" if float(event.get("composite_score", 0) or 0) >= 75 else "快讯",
                    "rationale": event.get("alert_reason") or "已人工加入重点观察。",
                    "evidence_links": [event.get("representative_link", "")],
                    "source_names": list(event.get("source_names", [])),
                    "source_count": int(event.get("source_count", 0) or 0),
                    "score": float(event.get("composite_score", 0) or 0),
                    "status": "new",
                    "recommended_mode": state["current_mode"],
                    "facts": [
                        f"30 分钟速度分 {event.get('velocity_score', 0)}",
                        f"覆盖 {event.get('platform_count', 0)} 个平台 / {event.get('source_count', 0)} 个来源",
                        str(event.get("alert_reason") or ""),
                    ],
                    "angles": [
                        {
                            "name": "热点快评",
                            "tone": "克制",
                            "focus": "先说事件本身，再说它为什么值得继续跟。",
                            "why": "适合公众号运营做持续观察。",
                        }
                    ],
                    "selected_angle": "先说事件本身，再说它为什么值得继续跟。",
                    "score_breakdown": {
                        "velocity": float(event.get("velocity_score", 0) or 0),
                        "coverage": float(event.get("coverage_score", 0) or 0),
                        "freshness": float(event.get("freshness_score", 0) or 0),
                    },
                    "published_at": event.get("published_at"),
                    "collected_at": event.get("latest_collected_at"),
                    "freshness_bucket": freshness_bucket(event.get("latest_collected_at")),
                    "draft_exists": candidate_id in draft_candidate_ids,
                    "normalized_score": float(event.get("composite_score", 0) or 0),
                    "updated_at": now_iso(),
                }
            )
        candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
        return candidates

    def _rebuild_intel_for_state(self, state: dict[str, Any], stamp: str | None = None) -> None:
        work_scope = self._work_scope(state)
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
            state["intel_events"] = []
            state["intel_alerts"] = []
            state["event_snapshots"] = []
            state["normalized_items"] = []
            state["candidates"] = []
            return
        state["event_snapshots"] = intel["event_snapshots"]
        state["intel_events"] = intel["intel_events"]
        if work_scope == "collect_events":
            state["intel_alerts"] = []
        elif work_scope == "collect_events_alerts":
            state["intel_alerts"] = intel["intel_alerts"]
        else:
            state["intel_alerts"] = []
        state["normalized_items"] = self._project_normalized_items_from_events(state)
        state["candidates"] = self._project_candidates_from_events(state)
        runtime = self._runtime(state)
        runtime["last_candidate_at"] = now_iso()

    def _rebuild_candidates_for_state(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self._rebuild_intel_for_state(state)
        candidates = state.get("candidates", [])
        if candidates:
            self._apply_llm_candidate_judgement(state, candidates)
        return candidates

    def _sync_due_sources(self, state: dict[str, Any], triggered_by: str, minimum_interval_minutes: int | None = None) -> SourceSyncResponse:
        now = datetime.now(UTC)
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
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
                candidate_count=len(state["candidates"]),
                synced_at=now_iso(),
                warnings=[],
            )

        existing = [item for item in state["raw_items"] if item["source_key"] not in {source["key"] for source in due_sources}]
        collected: list[dict[str, Any]] = []
        warnings: list[str] = []
        stamp = now_iso()
        total_sources = len(due_sources)
        max_workers = max(1, min(int(state.get("settings", {}).get("max_workers", 8)), 20))
        self._set_runtime_progress(runtime, percent=8, done=0, total=total_sources, label=f"正在并发采集 {total_sources} 个来源 ({max_workers} 线程)")
        self._heartbeat_runtime_run(runtime, stage="collecting", now=now)
        with self._lock:
            self._write(state)

        def _collect_one(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], str | None, str | None, datetime, datetime]:
            started_at = datetime.now(UTC)
            try:
                items, warning = _collect_with_retry(source)
                return source, items, warning, None, started_at, datetime.now(UTC)
            except Exception as exc:
                tb = traceback.format_exc()
                return source, [], None, f"{source['name']}: 抓取器异常:\n{tb}", started_at, datetime.now(UTC)

        source_map: dict[str, dict[str, Any]] = {src["key"]: src for src in due_sources}
        futures = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for src in due_sources:
                futures[pool.submit(_collect_one, src)] = src["key"]
            completed = 0
            for future in as_completed(futures):
                src_key = futures[future]
                source = source_map[src_key]
                try:
                    src_collected, items, warning, error, started_at, completed_at = future.result()
                except Exception:
                    items, warning, error = [], None, f"{source['name']}: 未知异常"
                    started_at = datetime.now(UTC)
                    completed_at = started_at
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
                self._finalize_source_health(source, now=completed_at)
                completed += 1
                self._set_runtime_progress(
                    runtime,
                    percent=8 + round(completed / max(total_sources, 1) * 62),
                    done=completed,
                    total=total_sources,
                    label=f"已采集 {completed}/{total_sources} 个来源",
                )
                self._heartbeat_runtime_run(runtime, stage=f"collecting:{source['key']}", error=warning_text, now=completed_at)
                with self._lock:
                    self._write(state)
        merged = sorted(existing + collected, key=lambda item: parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        state["raw_items"] = merged[:MAX_RAW_ITEMS]
        candidates = self._rebuild_candidates_for_state(state)
        runtime["last_collect_at"] = stamp
        if collected:
            runtime["last_successful_sync_at"] = stamp
        self._set_runtime_progress(runtime, percent=72, done=total_sources, total=total_sources, label="采集完成，正在整理结果")
        self._heartbeat_runtime_run(runtime, stage="collecting:complete", now=datetime.now(UTC))
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        level = "success"
        message = f"自动同步 {len(due_sources)} 个来源，新增 {len(collected)} 条素材，候选池现有 {len(candidates)} 条。"
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
        state["reference_projects"] = write_reference_baseline()
        return SourceSyncResponse(
            raw_count=len(state["raw_items"]),
            normalized_count=len(state["normalized_items"]),
            candidate_count=len(state["candidates"]),
            synced_at=stamp,
            warnings=warnings,
        )

    def _sync_sources_internal(self, state: dict[str, Any], triggered_by: str) -> SourceSyncResponse:
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
        candidates = self._rebuild_candidates_for_state(state)
        state["reference_projects"] = write_reference_baseline()
        runtime = self._runtime(state)
        runtime["last_collect_at"] = stamp
        if raw_items:
            runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        level = "success"
        message = f"已同步 {len(raw_items)} 条素材，形成 {len(normalized)} 个标准化事件和 {len(candidates)} 个候选选题。"
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
            candidate_count=len(candidates),
            synced_at=stamp,
            warnings=warnings,
        )

    def _build_digest_internal(
        self,
        state: dict[str, Any],
        triggered_by: str,
        limit: int | None = 2,
        selection_mode: str = "all_new",
    ) -> list[dict[str, Any]]:
        if not state["candidates"]:
            self._sync_sources_internal(state, triggered_by=triggered_by)
        publish_mode = automation_to_publish_mode(state.get("automation_mode", "radar_only"))
        risk_keywords = state["channels"]["wechat"]["risk_keywords"]
        llm_service = self._make_llm_service(state)
        normalized_map = {item["id"]: item for item in state["normalized_items"]}
        existing_candidate_ids = {draft["candidate_topic_id"] for draft in state["drafts"]}
        drafted: list[dict[str, Any]] = []
        candidates = list(state["candidates"])
        if selection_mode == "top_scored":
            candidates.sort(
                key=lambda item: (
                    float(item.get("score", 0) or 0),
                    parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC),
                ),
                reverse=True,
            )
        for candidate in candidates:
            if candidate["id"] in existing_candidate_ids:
                continue
            normalized_item = normalized_map.get(candidate["normalized_item_id"])
            if not normalized_item:
                continue
            draft = compose_draft(candidate, normalized_item, publish_mode, risk_keywords, llm_service=llm_service)
            state["drafts"].insert(0, draft)
            candidate["status"] = "drafted"
            candidate["draft_exists"] = True
            candidate["updated_at"] = now_iso()
            drafted.append(draft)
            existing_candidate_ids.add(candidate["id"])
            if limit is not None and len(drafted) >= limit:
                break
        self._sync_llm_usage(state, llm_service)
        if drafted:
            runtime = self._runtime(state)
            runtime["last_draft_at"] = now_iso()
            self._append_log(
                state,
                "success",
                "draft",
                f"本轮生成 {len(drafted)} 篇初稿。",
                stream="system_runtime" if triggered_by == "scheduler" else "business_event",
                actor=triggered_by,
            )
        return drafted

    def _publish_backends(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return collect_backend_status(state["channels"]["wechat"], state["browser"]["wechat"])

    def _sync_shadow_wechat_draft(self, state: dict[str, Any], draft: dict[str, Any], triggered_by: str) -> dict[str, Any]:
        browser = self._refresh_browser_session(state)
        if not draft.get("wechat_draft_id"):
            draft["wechat_draft_id"] = build_wechat_draft_id(draft["id"])
        draft["updated_at"] = now_iso()
        detail = "已写入本地微信草稿队列，完成浏览器配置后即可继续推进。"
        if browser.get("logged_in"):
            detail = "已写入微信草稿队列，可继续通过浏览器链路打开和校验。"
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                draft["id"],
                "wechat_draft",
                "completed",
                detail,
                triggered_by,
                str(state["channels"]["wechat"]["selectors_version"]),
                step_logs=[detail],
            ),
        )
        self._append_log(state, "success", "wechat", f"已排入微信草稿：{draft['title']}")
        state["publish_tasks"] = state["publish_tasks"][:80]
        return draft

    def _sync_wechat_draft_internal(self, state: dict[str, Any], draft: dict[str, Any], triggered_by: str) -> dict[str, Any]:
        self._sync_shadow_wechat_draft(state, draft, triggered_by)
        browser = self._refresh_browser_session(state)
        if browser.get("logged_in"):
            browser, artifacts, step_logs = run_browser_action("sync_wechat_draft", draft, state["channels"]["wechat"], browser)
            state["browser"]["wechat"] = browser
            status = "completed" if not browser.get("last_error") else "blocked"
            message = "已写入公众号草稿编辑器并尝试保存。"
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    draft["id"],
                    "sync_wechat_draft",
                    status,
                    message,
                    triggered_by,
                    str(state["channels"]["wechat"]["selectors_version"]),
                    artifacts=artifacts,
                    step_logs=step_logs,
                ),
            )
            if browser.get("last_error"):
                draft["last_error"] = browser.get("last_error")
            else:
                draft["last_error"] = None
                draft["wechat_editor_url"] = browser.get("last_opened_url")
                draft["wechat_remote_appmsg_id"] = extract_wechat_appmsg_id(str(browser.get("last_opened_url") or ""))
                draft["updated_at"] = now_iso()
        return draft

    def list_modes(self) -> list[ModeDefinition]:
        state = self._read()
        return [ModeDefinition(**mode) for mode in state["mode_definitions"]]

    def get_current_mode(self) -> ModeDefinition:
        state = self._read()
        return ModeDefinition(**self._current_mode_def(state))

    def set_current_mode(self, mode: PublishMode) -> ModeDefinition:
        state = self._read()
        modes = self._mode_map(state)
        if mode not in modes:
            raise ValueError(f"Unknown mode: {mode}")
        state["current_mode"] = mode
        for draft in state["drafts"]:
            if draft["pipeline_stage"] != "published":
                draft["publish_mode"] = mode
                draft["updated_at"] = now_iso()
        self._append_log(state, "info", "mode", f"切换发布模式为 {modes[mode]['label']}")
        self._write(state)
        return ModeDefinition(**modes[mode])

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
        with self._lock:
            state = self._upgrade_state(self._read())
            plan = self._runtime_plan_from_state(state)
            self._write(state)
            return plan

    def update_runtime_plan(self, payload: RuntimePlanPayload, actor: str = "dashboard") -> RuntimePlan:
        with self._lock:
            state = self._upgrade_state(self._read())
            plan = self._runtime_plan(state)
            plan.update(payload.model_dump())
            runtime = self._runtime(state)
            runtime["launch_mode"] = plan["launch_mode"]
            runtime["work_scope"] = plan.get("work_scope", "collect_events_alerts")
            if runtime.get("control_state") != "running":
                runtime["scheduled_start_at"] = plan.get("start_at") if plan["launch_mode"] in {"once_at", "interval_at"} else None
            runtime["next_collect_at"] = self._calculate_next_collect_at(state)
            self._append_log(state, "success", "runtime", "已更新自动运行计划。", stream="business_event", actor=actor)
            self._write(state)
            return self._runtime_plan_from_state(state)

    def get_runtime_status(self) -> SchedulerStatus:
        snapshot = self._progress_snapshot
        now_mono = time.monotonic()
        in_completion_hold = now_mono < self._completion_hold_until
        with self._lock:
            state = self._upgrade_state(self._read())
            recovered_run_id = self._recover_stale_runtime_run(state, actor="runtime_status")
            runtime = self._runtime(state)
            run = self._runtime_run(runtime)
            plan_launch = self._runtime_plan(state).get("launch_mode", "interval_now")
            next_at = self._calculate_next_collect_at(state)
            running = runtime.get("control_state", "stopped") != "stopped"
            control_state = str(runtime.get("control_state") or "stopped")
            current_mode = state["automation_mode"]
            work_scope = str(runtime.get("work_scope") or "collect_events_alerts")
            last_collect_at = runtime.get("last_collect_at")
            last_candidate_at = runtime.get("last_candidate_at")
            last_draft_at = runtime.get("last_draft_at")
            enabled_at = runtime.get("enabled_at")
            scheduled_start_at = runtime.get("scheduled_start_at")
            cycle_started_at = runtime.get("current_cycle_started_at")
            last_cycle_started_at = runtime.get("last_cycle_started_at")
            last_cycle_finished_at = runtime.get("last_cycle_finished_at")
            last_cycle_duration_seconds = runtime.get("last_cycle_duration_seconds")
            completed_cycles_today = int(runtime.get("completed_cycles_today", 0) or 0)
            failed_cycles_today = int(runtime.get("failed_cycles_today", 0) or 0)
            last_error = runtime.get("last_error")
            if recovered_run_id:
                self._write(state)
        if in_completion_hold:
            cycle = "completed"
            percent = 100
            done = snapshot.get("done", 1)
            total = snapshot.get("total", 1)
            label = snapshot.get("label") or "本轮已完成"
        else:
            cycle = str(snapshot.get("cycle") or runtime.get("current_cycle", "idle"))
            percent = int(snapshot.get("percent", 0))
            done = int(snapshot.get("done", 0))
            total = int(snapshot.get("total", 0))
            label = snapshot.get("label")
        return SchedulerStatus(
            running=running,
            control_state=control_state,
            launch_mode=plan_launch,
            current_mode=current_mode,
            work_scope=work_scope,
            last_collect_at=last_collect_at,
            last_candidate_at=last_candidate_at,
            last_draft_at=last_draft_at,
            next_collect_at=next_at,
            current_cycle=cycle,
            current_cycle_progress_percent=percent,
            current_cycle_progress_done=done,
            current_cycle_progress_total=total,
            current_cycle_progress_label=label,
            enabled_at=enabled_at,
            scheduled_start_at=scheduled_start_at,
            current_cycle_started_at=cycle_started_at,
            last_cycle_started_at=last_cycle_started_at,
            last_cycle_finished_at=last_cycle_finished_at,
            last_cycle_duration_seconds=last_cycle_duration_seconds,
            uptime_seconds=0,
            completed_cycles_today=completed_cycles_today,
            failed_cycles_today=failed_cycles_today,
            last_error=last_error,
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
        )

    def _scheduler_status_from_state(self, state: dict[str, Any]) -> SchedulerStatus:
        runtime = self._runtime(state)
        run = self._runtime_run(runtime)
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
        return SchedulerStatus(
            running=control_state != "stopped",
            control_state=control_state,
            launch_mode=str(runtime.get("launch_mode") or self._runtime_plan(state).get("launch_mode") or "interval_now"),
            current_mode=state["automation_mode"],
            work_scope=str(runtime.get("work_scope") or self._runtime_plan(state).get("work_scope") or "collect_events_alerts"),
            last_collect_at=runtime.get("last_collect_at"),
            last_candidate_at=runtime.get("last_candidate_at"),
            last_draft_at=runtime.get("last_draft_at"),
            next_collect_at=runtime.get("next_collect_at"),
            current_cycle=current_cycle,
            current_cycle_progress_percent=progress_percent,
            current_cycle_progress_done=progress_done,
            current_cycle_progress_total=progress_total,
            current_cycle_progress_label=progress_label,
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
            runtime["last_error"] = None
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
                self._finish_runtime_run(runtime, status="idle", stage="idle", error=None, recovered_run_id=None)
            runtime["scheduled_start_at"] = None
            runtime["next_collect_at"] = None if runtime.get("control_state") != "running" else runtime.get("next_collect_at")
            self._append_log(state, "warning", "runtime", "后台自动调度器已暂停。", stream="system_runtime", actor=actor)
            self._append_log(state, "warning", "runtime", "已从前端暂停自动运行。", stream="business_event", actor=actor)
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
        mode = self._current_automation_mode_def(state)
        profile = self._current_automation_profile(state)
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
        self._set_runtime_progress(runtime, percent=5, done=0, total=0, label="正在准备采集来源")
        self._progress_snapshot["cycle"] = "collecting"
        self._start_runtime_run(runtime, stage="collecting", triggered_by=triggered_by, now=now)
        if recovered_run_id:
            self._runtime_run(runtime)["recovered_run_id"] = recovered_run_id
        runtime["launch_mode"] = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")
        runtime["last_error"] = None
        self._sync_runtime_counters(runtime)
        self._append_log(state, "info", "runtime", f"轮次启动：launch_mode={runtime['launch_mode']}, work_scope={runtime['work_scope']}, force={force}", stream="system_runtime", actor=triggered_by)
        with self._lock:
            self._write(state)

        start = datetime.now(UTC)
        try:
            self._append_log(state, "info", "runtime", "阶段 1/4：开始采集到期来源...", stream="system_runtime", actor=triggered_by)
            self._heartbeat_runtime_run(runtime, stage="collecting", now=start)
            with self._lock:
                self._write(state)
            sync_response = self._sync_due_sources(
                state,
                triggered_by="scheduler",
                minimum_interval_minutes=None,
            )
            self._append_log(state, "info", "runtime", f"阶段 1/4 完成：采集 {sync_response.raw_count} 条素材", stream="system_runtime", actor=triggered_by)
            with self._lock:
                self._write(state)
            drafted_count = 0
            synced_to_wechat = 0
            if mode.get("auto_generate_drafts"):
                should_build_drafts = False
                if profile.get("draft_trigger") == "after_sync":
                    should_build_drafts = True
                elif profile.get("draft_trigger") == "scheduled":
                    should_build_drafts = self._is_slot_due(runtime.get("last_draft_at"), str(profile.get("draft_schedule_time") or ""))
                if should_build_drafts:
                    self._append_log(state, "info", "runtime", "阶段 2/4：开始生成稿件...", stream="system_runtime", actor=triggered_by)
                    runtime["current_cycle"] = "drafting"
                    self._set_runtime_progress(runtime, percent=80, done=0, total=0, label="正在生成事件稿件")
                    self._progress_snapshot["cycle"] = "drafting"
                    self._heartbeat_runtime_run(runtime, stage="drafting")
                    with self._lock:
                        self._write(state)
                    drafted = self._build_digest_internal(
                        state,
                        triggered_by="scheduler",
                        limit=int(profile.get("draft_limit", 10) or 10),
                        selection_mode=str(profile.get("draft_selection") or "all_new"),
                    )
                    drafted_count = len(drafted)
                    self._append_log(state, "info", "runtime", f"阶段 2/4 完成：生成 {drafted_count} 篇稿件", stream="system_runtime", actor=triggered_by)
                    if profile.get("draft_delivery") == "wechat_draft" and drafted:
                        self._append_log(state, "info", "runtime", f"阶段 3/4：开始同步 {len(drafted)} 篇到微信...", stream="system_runtime", actor=triggered_by)
                        runtime["current_cycle"] = "wechat_sync"
                        self._set_runtime_progress(runtime, percent=90, done=0, total=max(len(drafted), 1), label="正在同步到微信草稿箱")
                        self._progress_snapshot["cycle"] = "wechat_sync"
                        self._heartbeat_runtime_run(runtime, stage="wechat_sync")
                        with self._lock:
                            self._write(state)
                        for draft in drafted:
                            self._sync_wechat_draft_internal(state, draft, "scheduler")
                            synced_to_wechat += 1
                            self._set_runtime_progress(
                                runtime,
                                percent=90 + round(synced_to_wechat / max(len(drafted), 1) * 10),
                                done=synced_to_wechat,
                                total=max(len(drafted), 1),
                                label=f"已同步微信草稿 {synced_to_wechat}/{max(len(drafted), 1)}",
                            )
                        self._append_log(state, "info", "runtime", f"阶段 3/4 完成：同步 {synced_to_wechat} 篇到微信", stream="system_runtime", actor=triggered_by)

            self._append_log(state, "info", "runtime", "阶段 4/4：收尾...", stream="system_runtime", actor=triggered_by)
            finish = datetime.now(UTC)
            duration = round((finish - start).total_seconds(), 1)
            self._append_log(state, "info", "runtime", f"轮次完成，总耗时 {duration}s", stream="system_runtime", actor=triggered_by)
            runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
            runtime["last_cycle_duration_seconds"] = duration
            runtime["current_cycle_started_at"] = None
            self._set_runtime_progress(runtime, percent=100, done=1, total=1, label="本轮已完成")
            self._finish_runtime_run(runtime, status="completed", stage="done", error=None, now=finish)
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
                f"自动轮次完成：素材 {sync_response.raw_count}，候选 {sync_response.candidate_count}，新增初稿 {drafted_count}，同步微信 {synced_to_wechat}，耗时 {duration}s。",
                triggered_by="scheduler",
            )
            with self._lock:
                self._write(state)
            return {
                "raw_count": sync_response.raw_count,
                "candidate_count": sync_response.candidate_count,
                "drafted_count": drafted_count,
                "wechat_synced_count": synced_to_wechat,
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
            self._finish_runtime_run(runtime, status="failed", stage="failed", error=str(exc), now=finish)
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
        self._append_log(state, "success", "source", f"已更新来源配置：{source['name']}")
        runtime = self._runtime(state)
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
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
        self._append_log(state, "success", "source", f"已删除来源：{source_key}")
        self._write(state)

    def sync_sources(self) -> SourceSyncResponse:
        state = self._upgrade_state(self._read())
        response = self._sync_sources_internal(state, triggered_by="dashboard")
        self._append_job(state, "collect_news", f"已采集 {response.raw_count} 条素材并刷新候选池。")
        self._write(state)
        return response

    def sync_source(self, source_key: str) -> SourceSyncResponse:
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
        message = f"已重抓来源 {source['name']}，新增 {len(items)} 条素材，候选池现有 {len(candidates)} 条。"
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
            actor="dashboard",
        )
        for warning in warnings[:3]:
            self._append_log(state, "warning", "collection", warning, stream="business_event", actor="dashboard")
        self._append_job(state, "collect_news", f"已重抓来源《{source['name']}》。", triggered_by="dashboard")
        self._write(state)
        return SourceSyncResponse(
            raw_count=len(state["raw_items"]),
            normalized_count=len(state["normalized_items"]),
            candidate_count=len(state["candidates"]),
            synced_at=stamp,
            warnings=warnings,
        )

    def get_settings(self) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        return state.get("settings", {})

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        settings = state.setdefault("settings", {})
        if "max_workers" in updates:
            value = int(updates["max_workers"])
            if not 1 <= value <= 20:
                raise ValueError("max_workers 必须在 1-20 之间")
            settings["max_workers"] = value
        self._append_log(state, "success", "settings", f"已更新设置: {list(updates.keys())}")
        self._write(state)
        return settings

    def list_candidates(self) -> list[CandidateTopic]:
        state = self._upgrade_state(self._read())
        return [CandidateTopic(**item) for item in state["candidates"]]

    def _make_llm_service(self, state: dict[str, Any]) -> LLMService | None:
        llm_config = state.get("llm", {})
        if not llm_config or not llm_config.get("providers"):
            return None
        enabled = [
            p
            for p in llm_config.get("providers", [])
            if p.get("enabled") and str(p.get("api_key", "")).strip() and "****" not in str(p.get("api_key", ""))
        ]
        if not enabled:
            return None
        config = deepcopy(llm_config)
        config["providers"] = enabled
        return LLMService(config)

    def _sync_llm_usage(self, state: dict[str, Any], llm_service: LLMService | None) -> None:
        if not llm_service:
            return
        state.setdefault("llm", {}).setdefault("usage_today", {})
        state["llm"]["usage_today"] = llm_service.get_usage()

    def _apply_llm_candidate_judgement(self, state: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
        if not candidates:
            return
        llm_service = self._make_llm_service(state)
        if not llm_service or "judgement" not in getattr(llm_service, "_tasks", {}):
            return

        payload = {
            "items": [
                {
                    "id": candidate["id"],
                    "title": candidate["title"],
                    "summary": candidate.get("summary", ""),
                    "source_names": candidate.get("source_names", []),
                    "source_count": candidate.get("source_count", 0),
                    "score": candidate.get("score", 0),
                    "published_at": candidate.get("published_at"),
                    "collected_at": candidate.get("collected_at"),
                    "existing_facts": candidate.get("facts", []),
                    "existing_angle": candidate.get("recommended_angle", ""),
                }
                for candidate in candidates[:16]
            ]
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Auto News Studio 的中文技术编辑。"
                    "请只基于给定素材做初步判断，不要编造事实。"
                    "输出纯 JSON 对象，格式为 {\"items\":[...] }。"
                    "每个 items 元素必须包含：id, summary, recommended_angle, rationale, facts, article_type。"
                    "facts 只能是 2 到 4 条中文事实句。"
                    "如果证据不足，要在 rationale 或 facts 中明确写出“信息仍待进一步确认”。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, indent=2),
            },
        ]
        try:
            response = llm_service.generate("judgement", messages, temperature=0.2, max_tokens=2400)
            parsed = _extract_json_payload(response.get("content", ""))
            items = parsed.get("items", []) if isinstance(parsed, dict) else []
            updates = {
                item.get("id"): item
                for item in items
                if isinstance(item, dict) and item.get("id")
            }
            for candidate in candidates:
                update = updates.get(candidate["id"])
                if not update:
                    continue
                summary = str(update.get("summary", "") or "").strip()
                recommended_angle = str(update.get("recommended_angle", "") or "").strip()
                rationale = str(update.get("rationale", "") or "").strip()
                facts = [str(item).strip() for item in update.get("facts", []) if str(item).strip()]
                article_type = str(update.get("article_type", "") or "").strip()
                if summary:
                    candidate["summary"] = summary
                if recommended_angle:
                    candidate["recommended_angle"] = recommended_angle
                    candidate["selected_angle"] = recommended_angle
                if rationale:
                    candidate["rationale"] = rationale
                if facts:
                    candidate["facts"] = facts[:4]
                if article_type in {"快讯", "专题", "深度"}:
                    candidate["article_type"] = article_type
            self._sync_llm_usage(state, llm_service)
        except Exception as exc:
            self._append_log(
                state,
                "warning",
                "llm",
                "GLM 初步判断未执行，已回退到规则判断。",
                detail=str(exc),
                stream="system_runtime",
                actor="system",
            )

    def create_draft_from_candidate(self, candidate_id: str, publish_mode: PublishMode | None = None) -> DraftItem:
        state = self._upgrade_state(self._read())
        candidate = self._find_candidate(state, candidate_id)
        normalized_map = {item["id"]: item for item in state["normalized_items"]}
        normalized_item = normalized_map.get(candidate["normalized_item_id"])
        if not normalized_item:
            raise ValueError("Candidate evidence is missing.")
        mode = publish_mode or state["current_mode"]
        llm_service = self._make_llm_service(state)
        draft = compose_draft(candidate, normalized_item, mode, state["channels"]["wechat"]["risk_keywords"], llm_service=llm_service)
        self._sync_llm_usage(state, llm_service)
        candidate["status"] = "drafted"
        candidate["draft_exists"] = True
        candidate["updated_at"] = now_iso()
        state["drafts"].insert(0, draft)
        self._append_log(state, "success", "draft", f"已从候选池生成初稿：{draft['title']}")
        runtime = self._runtime(state)
        runtime["last_draft_at"] = now_iso()
        self._write(state)
        return DraftItem(**draft)

    def batch_create_drafts(self) -> BatchDraftResponse:
        state = self._upgrade_state(self._read())
        if not state["candidates"]:
            self._sync_sources_internal(state, triggered_by="dashboard")
        publish_mode = automation_to_publish_mode(state.get("automation_mode", "radar_only"))
        risk_keywords = state["channels"]["wechat"]["risk_keywords"]
        llm_service = self._make_llm_service(state)
        normalized_map = {item["id"]: item for item in state["normalized_items"]}
        existing_candidate_ids = {draft["candidate_topic_id"] for draft in state["drafts"]}
        pending_candidates = [item for item in state["candidates"] if item["id"] not in existing_candidate_ids]
        created: list[dict[str, Any]] = []
        failed_count = 0

        for candidate in pending_candidates:
            normalized_item = normalized_map.get(candidate["normalized_item_id"])
            if not normalized_item:
                failed_count += 1
                continue
            try:
                draft = compose_draft(candidate, normalized_item, publish_mode, risk_keywords, llm_service=llm_service)
            except Exception:  # pragma: no cover - defensive
                failed_count += 1
                continue
            state["drafts"].insert(0, draft)
            candidate["status"] = "drafted"
            candidate["draft_exists"] = True
            candidate["updated_at"] = now_iso()
            created.append(draft)
        self._sync_llm_usage(state, llm_service)

        if created:
            runtime = self._runtime(state)
            runtime["last_draft_at"] = now_iso()
        message = f"已批量生成 {len(created)} 篇初稿，跳过 {len(state['candidates']) - len(pending_candidates)} 条，失败 {failed_count} 条。"
        self._append_log(state, "success" if created else "warning", "draft", message, stream="business_event", actor="dashboard")
        self._append_job(state, "build_digest", message, triggered_by="dashboard")
        self._write(state)
        return BatchDraftResponse(
            processed_count=len(pending_candidates),
            created_count=len(created),
            skipped_count=len(state["candidates"]) - len(pending_candidates),
            failed_count=failed_count,
            draft_ids=[item["id"] for item in created],
            message=message,
        )

    def list_drafts(self) -> list[DraftItem]:
        state = self._upgrade_state(self._read())
        return [DraftItem(**item) for item in state["drafts"]]

    def regenerate_draft(self, draft_id: str) -> DraftItem:
        state = self._upgrade_state(self._read())
        draft = self._find_draft(state, draft_id)
        candidate = self._find_candidate(state, draft["candidate_topic_id"])
        normalized_map = {item["id"]: item for item in state["normalized_items"]}
        normalized_item = normalized_map.get(candidate["normalized_item_id"])
        if not normalized_item:
            raise ValueError("Candidate evidence is missing.")
        llm_service = self._make_llm_service(state)
        regenerated = compose_draft(candidate, normalized_item, draft["publish_mode"], state["channels"]["wechat"]["risk_keywords"], llm_service=llm_service)
        self._sync_llm_usage(state, llm_service)
        regenerated["id"] = draft["id"]
        regenerated["wechat_draft_id"] = None
        regenerated["wechat_editor_url"] = None
        regenerated["wechat_remote_appmsg_id"] = None
        regenerated["preview_url"] = None
        regenerated["last_error"] = None
        index = next(index for index, item in enumerate(state["drafts"]) if item["id"] == draft_id)
        state["drafts"][index] = regenerated
        self._append_log(state, "success", "draft", f"已重新生成稿件：{draft['title']}")
        self._write(state)
        return DraftItem(**regenerated)

    def approve_draft(self, draft_id: str, approved: bool) -> DraftItem:
        state = self._upgrade_state(self._read())
        draft = self._find_draft(state, draft_id)
        draft["audit_status"] = "approved" if approved else "rejected"
        draft["pipeline_stage"] = "approved" if approved else "drafted"
        draft["updated_at"] = now_iso()
        message = "已通过审核" if approved else "已驳回稿件"
        self._append_log(state, "success" if approved else "warning", "audit", f"{message}：{draft['title']}")
        self._write(state)
        return DraftItem(**draft)

    def update_draft_content(self, draft_id: str, markdown: str, title: str) -> DraftItem:
        state = self._upgrade_state(self._read())
        draft = self._find_draft(state, draft_id)
        draft["markdown"] = markdown
        draft["title"] = title
        draft["html"] = _markdown_to_html(markdown)
        draft["wechat_html"] = _wechat_html(markdown)
        draft["word_count"] = len(re.sub(r"\s+", "", markdown))
        draft["updated_at"] = now_iso()
        self._append_log(state, "info", "draft", f"已更新稿件内容：{title}")
        self._write(state)
        return DraftItem(**draft)

    def sync_wechat_draft(self, draft_id: str, triggered_by: str = "dashboard") -> DraftItem:
        state = self._upgrade_state(self._read())
        draft = self._find_draft(state, draft_id)
        self._sync_wechat_draft_internal(state, draft, triggered_by)
        self._write(state)
        return DraftItem(**draft)

    def open_preview(self, draft_id: str) -> DraftItem:
        state = self._upgrade_state(self._read())
        draft = self._find_draft(state, draft_id)
        image_blockers = self._draft_image_blockers(draft)
        if image_blockers:
            draft["blocked_reasons"] = sorted(set(list(draft.get("blocked_reasons", [])) + image_blockers))
            draft["last_error"] = image_blockers[-1]
            draft["updated_at"] = now_iso()
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    draft_id,
                    "open_preview",
                    "blocked",
                    "稿件待补图，已阻止进入微信预览。",
                    "dashboard",
                    str(state["channels"]["wechat"]["selectors_version"]),
                    step_logs=image_blockers,
                ),
            )
            self._append_log(state, "warning", "preview", f"预览被阻止：{draft['title']}", detail=image_blockers[-1])
            self._write(state)
            return DraftItem(**draft)
        if not draft.get("wechat_draft_id"):
            self._sync_shadow_wechat_draft(state, draft, "dashboard")
        draft["preview_url"] = build_preview_url(draft_id)
        draft["pipeline_stage"] = "preview_ready"
        draft["last_error"] = None
        draft["updated_at"] = now_iso()
        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = run_browser_action("open_preview", draft, state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        if browser.get("last_error"):
            draft["last_error"] = str(browser.get("last_error"))
        else:
            draft["wechat_editor_url"] = browser.get("last_opened_url") or draft.get("wechat_editor_url")
            draft["wechat_remote_appmsg_id"] = extract_wechat_appmsg_id(str(draft.get("wechat_editor_url") or ""))
            draft["last_error"] = None
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                draft_id,
                "open_preview",
                "completed" if not browser.get("last_error") else "blocked",
                "已准备浏览器预览链路。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._append_log(state, "info", "preview", f"已生成预览链路：{draft['title']}")
        self._write(state)
        return DraftItem(**draft)

    def publish_draft(self, draft_id: str) -> DraftItem:
        state = self._upgrade_state(self._read())
        draft = self._find_draft(state, draft_id)
        mode = self._current_mode_def(state)
        browser = self._refresh_browser_session(state)

        if not draft.get("wechat_draft_id"):
            self._sync_shadow_wechat_draft(state, draft, "dashboard")
        if not draft.get("preview_url"):
            draft["preview_url"] = build_preview_url(draft_id)

        blocked_reasons = list(draft.get("blocked_reasons", []))
        blocked_reasons.extend(self._draft_image_blockers(draft))
        if draft.get("risk_flags"):
            blocked_reasons.append("命中风险词，禁止自动发送。")
        if mode["requires_human_review"] and draft["audit_status"] != "approved":
            blocked_reasons.append("当前模式要求先通过人工审核。")
        if not mode["allow_auto_send"]:
            blocked_reasons.append("当前模式不允许自动发送。")
        if not browser.get("logged_in"):
            blocked_reasons.append("浏览器登录态不可用。")

        if blocked_reasons:
            draft["pipeline_stage"] = "preview_ready"
            draft["last_error"] = blocked_reasons[-1]
            draft["blocked_reasons"] = sorted(set(blocked_reasons))
            draft["updated_at"] = now_iso()
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    draft_id,
                    "publish",
                    "blocked",
                    "发布守卫阻止了本次自动发送。",
                    "dashboard",
                    str(state["channels"]["wechat"]["selectors_version"]),
                    step_logs=draft["blocked_reasons"],
                ),
            )
            self._append_log(state, "warning", "publish", f"稿件被守卫阻止：{draft['title']}")
            self._write(state)
            return DraftItem(**draft)

        browser, artifacts, step_logs = run_browser_action("publish", draft, state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        draft["pipeline_stage"] = "preview_ready"
        draft["last_error"] = browser.get("last_error") or "已完成浏览器发布尝试，等待页面校准后启用最终点击。"
        draft["updated_at"] = now_iso()
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                draft_id,
                "publish",
                "blocked" if draft["last_error"] else "completed",
                "已执行浏览器发布尝试。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._append_log(state, "info", "publish", f"已执行浏览器发布尝试：{draft['title']}")
        self._write(state)
        return DraftItem(**draft)

    def list_publish_tasks(self) -> list[PublishTask]:
        state = self._upgrade_state(self._read())
        return [PublishTask(**item) for item in state["publish_tasks"]]

    def list_jobs(self) -> list[JobItem]:
        state = self._upgrade_state(self._read())
        return [JobItem(**item) for item in state["jobs"]]

    def run_job(self, action: str) -> JobItem:
        with self._lock:
            state = self._upgrade_state(self._read())
            if action not in JOB_LABELS:
                raise ValueError(f"Unknown job action: {action}")

            runtime = self._runtime(state)
            if str(runtime.get("control_state") or "stopped") != "stopped":
                raise ValueError("自动运行已启用，请先停止再手动补跑。")

            if action == "collect_news":
                result = self._sync_sources_internal(state, triggered_by="job")
                job = self._append_job(state, action, f"已采集 {result.raw_count} 条素材。", triggered_by="job")
            elif action == "rebuild_candidates":
                candidates = self._rebuild_candidates_for_state(state)
                job = self._append_job(state, action, f"已重建候选池，当前 {len(candidates)} 个候选主题。", triggered_by="job")
                self._append_log(state, "info", "candidate", "已手动重建候选池。", stream="business_event", actor="job")
            elif action == "build_digest":
                drafts = self._build_digest_internal(state, triggered_by="job", limit=None)
                job = self._append_job(state, action, f"新增 {len(drafts)} 篇初稿。", triggered_by="job")
            elif action == "sync_wechat_draft":
                if not state["drafts"]:
                    self._build_digest_internal(state, triggered_by="job", limit=1)
                draft = state["drafts"][0]
                self._sync_shadow_wechat_draft(state, draft, "job")
                job = self._append_job(state, action, f"已将《{draft['title']}》写入微信草稿队列。", triggered_by="job")
            elif action == "open_preview":
                if not state["drafts"]:
                    self._build_digest_internal(state, triggered_by="job", limit=1)
                draft = state["drafts"][0]
                self.open_preview(draft["id"])
                state = self._upgrade_state(self._read())
                job = self._append_job(state, action, f"已为《{draft['title']}》准备预览。", triggered_by="job")
            elif action == "publish_pipeline":
                if not state["drafts"]:
                    self._build_digest_internal(state, triggered_by="job", limit=1)
                draft = state["drafts"][0]
                self.publish_draft(draft["id"])
                state = self._upgrade_state(self._read())
                job = self._append_job(state, action, f"已推动《{draft['title']}》进入浏览器发布链。", triggered_by="job")
            else:
                browser = self.check_browser_session().model_dump()
                state = self._upgrade_state(self._read())
                job = self._append_job(
                    state,
                    action,
                    f"浏览器检查完成，登录态={'已登录' if browser.get('logged_in') else '未登录'}。",
                    triggered_by="job",
                )
            self._write(state)
            return JobItem(**job)

    def get_wechat_config(self) -> WeChatChannelConfig:
        state = self._upgrade_state(self._read())
        return WeChatChannelConfig(**state["channels"]["wechat"])

    def update_wechat_config(self, payload: ChannelConfigPayload) -> WeChatChannelConfig:
        state = self._upgrade_state(self._read())
        state["channels"]["wechat"].update(payload.model_dump())
        state["channels"]["wechat"] = ensure_channel_defaults(state["channels"]["wechat"])
        self._refresh_browser_session(state)
        self._append_log(state, "success", "channel", "已更新微信公众号配置。")
        self._write(state)
        return WeChatChannelConfig(**state["channels"]["wechat"])

    def get_browser_session(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        self._write(state)
        return BrowserSessionState(**browser)

    def update_browser_session(self, payload: BrowserSessionPayload) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        state["channels"]["wechat"]["browser_name"] = payload.browser_name
        state["channels"]["wechat"]["browser_profile_path"] = payload.user_data_dir
        state["channels"]["wechat"] = ensure_channel_defaults(state["channels"]["wechat"])
        browser = self._refresh_browser_session(state)
        self._append_log(state, "info", "browser", "已刷新浏览器会话配置。")
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

    def get_publish_backends(self) -> list[PublishBackendStatus]:
        state = self._upgrade_state(self._read())
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

    def list_logs(self) -> list[LogItem]:
        state = self._upgrade_state(self._read())
        self._write(state)
        return [LogItem(**item) for item in state["logs"]]

    def _candidate_by_normalized(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        mapping: dict[str, dict[str, Any]] = {}
        for candidate in state["candidates"]:
            mapping.setdefault(candidate["normalized_item_id"], candidate)
        return mapping

    def _draft_by_candidate(self, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
        mapping: dict[str, dict[str, Any]] = {}
        for draft in state["drafts"]:
            mapping.setdefault(draft["candidate_topic_id"], draft)
        return mapping

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
        blocked_draft_ids = {
            item["id"] for item in state["drafts"] if item.get("blocked_reasons")
        }
        blocked_draft_ids.update(
            item["draft_id"] for item in state["publish_tasks"] if item.get("status") == "blocked"
        )
        return DashboardTopBar(
            current_mode_label=self._current_automation_mode_def(state)["label"],
            healthy_sources=len([item for item in state["sources"] if item["health_status"] == "healthy"]),
            total_sources=len(state["sources"]),
            latest_collected_at=freshness.latest_collected_at,
            latest_published_at=freshness.latest_published_at,
            waiting_review=len([item for item in state["drafts"] if item["audit_status"] == "pending"]),
            blocked_publish_count=len(blocked_draft_ids),
        )

    def _intel_stream(self, state: dict[str, Any]) -> list[IntelStreamItem]:
        raw_lookup = {item["id"]: item for item in state["raw_items"]}
        candidate_by_normalized = self._candidate_by_normalized(state)
        draft_by_candidate = self._draft_by_candidate(state)
        stream: list[IntelStreamItem] = []

        for normalized in state["normalized_items"]:
            candidate = candidate_by_normalized.get(normalized["id"])
            draft = draft_by_candidate.get(candidate["id"]) if candidate else None
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
                    candidate_status=candidate.get("status") if candidate else None,
                    draft_stage=draft.get("pipeline_stage") if draft else None,
                    candidate_id=candidate.get("id") if candidate else None,
                    draft_id=draft.get("id") if draft else None,
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
        normalized_by_link = {item["link"]: item for item in state["normalized_items"]}
        candidate_by_normalized = self._candidate_by_normalized(state)
        draft_by_candidate = self._draft_by_candidate(state)
        github_items: list[GithubSignalItem] = []

        for raw_item in state["raw_items"]:
            source = sources_by_key.get(raw_item["source_key"])
            if not self._is_github_signal(raw_item, source):
                continue
            normalized = normalized_by_link.get(raw_item.get("link"))
            candidate = candidate_by_normalized.get(normalized["id"]) if normalized else None
            draft = draft_by_candidate.get(candidate["id"]) if candidate else None
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
                    candidate_status=candidate.get("status") if candidate else None,
                    draft_stage=draft.get("pipeline_stage") if draft else None,
                    candidate_id=candidate.get("id") if candidate else None,
                    draft_id=draft.get("id") if draft else None,
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
        draft_errors = [item for item in state["drafts"] if item.get("last_error") or item.get("pipeline_stage") == "failed"]
        pending_review = [item for item in state["drafts"] if item["audit_status"] == "pending"]

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

        if any(item["action"] == "build_digest" for item in running_jobs):
            candidate_status = "running"
        elif state["candidates"]:
            candidate_status = "healthy"
        elif state["raw_items"]:
            candidate_status = "warning"
        else:
            candidate_status = "idle"

        if any(item["action"] in {"sync_wechat_draft", "open_preview"} for item in running_jobs):
            draft_status = "running"
        elif draft_errors:
            draft_status = "warning"
        elif state["drafts"]:
            draft_status = "healthy"
        else:
            draft_status = "idle"

        if pending_review:
            review_status = "warning"
        elif state["drafts"]:
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
        elif any(item["pipeline_stage"] == "published" for item in state["drafts"]):
            publish_status = "healthy"
        else:
            publish_status = "idle"

        blockers: list[str] = []
        blockers.extend([f"来源异常：{item['name']}" for item in source_errors[:2]])
        blockers.extend(item["blocked_reasons"][0] for item in state["drafts"] if item.get("blocked_reasons")[:1])
        if not browser.get("logged_in"):
            blockers.append("微信公众号浏览器登录态不可用。")
        browser_error = browser.get("last_error")
        if browser_error:
            blockers.append(browser_error.replace("None ", "").strip())
        if blocked_tasks:
            blockers.append(blocked_tasks[0]["message"])
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
            ChainStateCard(key="candidate", label="候选", status=candidate_status, detail=f"{len(state['candidates'])} 个候选主题"),
            ChainStateCard(key="draft", label="草稿", status=draft_status, detail=f"{len(state['drafts'])} 篇稿件"),
            ChainStateCard(key="review", label="审核", status=review_status, detail=f"{len(pending_review)} 篇待审核"),
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
            candidate_status=candidate_status,
            draft_status=draft_status,
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
            state = self._upgrade_state(self._read())
            recovered_run_id = self._recover_stale_runtime_run(state, actor="intel_summary")
            runtime = self._runtime(state)
            if recovered_run_id:
                self._write(state)

        alerts = [IntelAlert(**item) for item in state.get("intel_alerts", [])]
        events = [IntelEvent(**item) for item in state.get("intel_events", [])]
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
            last_sync_at=runtime.get("last_successful_sync_at") or runtime.get("last_collect_at"),
            next_run_at=self._calculate_next_collect_at(state),
            running=runtime.get("control_state") != "stopped",
            work_scope=self._work_scope(state),
            top_alerts=alerts[:6],
            top_events=events[:8],
            source_alerts=source_alerts[:6],
        )

    def list_discovery_items(self) -> list[DiscoveryItem]:
        state = self._upgrade_state(self._read())
        return [DiscoveryItem(**item) for item in state.get("discovery_items", [])]

    def list_intel_events(self) -> list[IntelEvent]:
        state = self._upgrade_state(self._read())
        return [IntelEvent(**item) for item in state.get("intel_events", [])]

    def get_intel_event(self, event_id: str) -> IntelEvent:
        state = self._upgrade_state(self._read())
        return IntelEvent(**self._find_event(state, event_id))

    def list_intel_alerts(self) -> list[IntelAlert]:
        state = self._upgrade_state(self._read())
        return [IntelAlert(**item) for item in state.get("intel_alerts", [])]

    def list_intel_sources(self) -> list[SourceConnector]:
        state = self._upgrade_state(self._read())
        return [SourceConnector(**item) for item in state.get("sources", [])]

    def watchlist_event(self, event_id: str) -> IntelEvent:
        with self._lock:
            state = self._upgrade_state(self._read())
            event = self._find_event(state, event_id)
            event["watchlisted"] = True
            event["ignored"] = False
            state["normalized_items"] = self._project_normalized_items_from_events(state)
            state["candidates"] = self._project_candidates_from_events(state)
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
            state["candidates"] = self._project_candidates_from_events(state)
            self._append_log(state, "warning", "intel", f"已忽略事件：{event['title']}", actor="dashboard")
            self._write(state)
            return IntelEvent(**event)

    # ── LLM config ────────────────────────────────────────────────

    def get_llm_config(self) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        cfg = deepcopy(state.get("llm", {}))
        for collection_key in ("profiles", "providers"):
            for item in cfg.get(collection_key, []):
                key = item.get("api_key", "")
                if key:
                    item["api_key"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
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
        if active_profile:
            active_profile["enabled"] = bool(str(active_profile.get("api_key") or "").strip())
        state["llm"] = {
            "current_profile_id": current_profile_id,
            "profiles": profiles,
            "providers": [build_provider_from_profile(active_profile)] if active_profile else [],
            "tasks": build_tasks_from_profile(active_profile) if active_profile else [],
            "usage_today": existing.get("usage_today", {}),
        }
        self._write(state)
        self._append_log(state, "info", "config", "已更新 AI 模型配置")
        return state["llm"]

    def test_llm_provider(self, provider_key: str) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        providers = state.get("llm", {}).get("providers", [])
        provider = next((item for item in providers if item.get("key") == provider_key), None)
        if not provider:
            raise ValueError(f"未找到服务商配置：{provider_key}")
        if not str(provider.get("api_key", "")).strip() or "****" in str(provider.get("api_key", "")):
            raise ValueError(f"Provider {provider_key} has no API key configured")
        llm_config = deepcopy(state.get("llm", {}))
        llm_config["providers"] = [{**provider, "enabled": True}]
        llm_service = LLMService(llm_config)
        result = llm_service.test_connection(provider_key)
        current_profile_id = str(state.get("llm", {}).get("current_profile_id") or "")
        for profile in state.get("llm", {}).get("profiles", []):
            if profile.get("id") == current_profile_id:
                profile["last_tested_at"] = now_iso()
                profile["last_test_result"] = "ok" if result.get("ok") else result.get("error", "failed")
                break
        for p in providers:
            if p["key"] == provider_key:
                p["last_tested_at"] = now_iso()
                p["last_test_result"] = "ok" if result.get("ok") else result.get("error", "failed")
        self._write(state)
        return result

    def get_llm_usage(self) -> dict[str, dict[str, int]]:
        state = self._upgrade_state(self._read())
        return state.get("llm", {}).get("usage_today", {})

    # ── Dashboard ────────────────────────────────────────────────

    def get_dashboard(self) -> DashboardResponse:
        state = self._upgrade_state(self._read())
        recovered_run_id = self._recover_stale_runtime_run(state, actor="dashboard")
        previous_browser = deepcopy(state.get("browser", {}).get("wechat", {}))
        browser = self._refresh_browser_session(state)
        backends = self._publish_backends(state)
        runtime = self._runtime(state)
        runtime["next_collect_at"] = self._calculate_next_collect_at(state)
        runtime["launch_mode"] = self._runtime_plan(state).get("launch_mode", "interval_now")
        runtime_status = self._scheduler_status_from_state(state)
        freshness = self._freshness_snapshot(state)
        top_bar = self._dashboard_top_bar(state, freshness)
        intel_stream = self._intel_stream(state)
        hot_clusters = self._hot_clusters(state)
        github_watch = self._github_watch(state)
        execution_chain = self._execution_chain(state, browser)
        stats = {
            "current_mode": state["current_mode"],
            "mode_label": self._current_automation_mode_def(state)["label"],
            "total_sources": top_bar.total_sources,
            "healthy_sources": top_bar.healthy_sources,
            "collected_today": freshness.items_24h,
            "candidate_count": len(state["candidates"]),
            "total_drafts": len(state["drafts"]),
            "waiting_review": top_bar.waiting_review,
            "preview_ready": len([item for item in state["drafts"] if item["pipeline_stage"] == "preview_ready"]),
            "published_today": len([item for item in state["drafts"] if item["pipeline_stage"] == "published"]),
            "failed_jobs": len([item for item in state["jobs"] if item["status"] == "failed"]),
            "last_job_label": state["jobs"][0]["label"] if state["jobs"] else None,
            "last_job_status": state["jobs"][0]["status"] if state["jobs"] else None,
            "last_job_at": (state["jobs"][0]["finished_at"] if state["jobs"] else None),
        }
        state["browser"]["wechat"] = browser
        if recovered_run_id or browser != previous_browser:
            self._write(state)
        return DashboardResponse(
            stats=DashboardStats(**stats),
            top_bar=top_bar,
            freshness=freshness,
            intel_stream=intel_stream,
            hot_clusters=hot_clusters,
            github_watch=github_watch,
            execution_chain=execution_chain,
            current_automation_mode=AutomationModeDefinition(**self._current_automation_mode_def(state)),
            current_automation_profile=AutomationModeProfile(**self._current_automation_profile(state)),
            automation_profiles=[AutomationModeProfile(**item) for item in state["automation_profiles"]],
            runtime_plan=self._runtime_plan_from_state(state),
            runtime_status=runtime_status,
            current_mode=ModeDefinition(**self._current_mode_def(state)),
            drafts=[DraftItem(**item) for item in state["drafts"][:6]],
            recent_jobs=[JobItem(**item) for item in state["jobs"][:8]],
            recent_logs=[LogItem(**item) for item in state["logs"][:8]],
            recent_candidates=[CandidateTopic(**item) for item in state["candidates"][:6]],
            sources=[SourceConnector(**item) for item in state["sources"]],
            browser_session=BrowserSessionState(**browser),
            publish_backends=[PublishBackendStatus(**item) for item in backends],
        )
