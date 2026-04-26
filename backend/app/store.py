from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import re
from threading import RLock
from typing import Any
from uuid import uuid4

from .composer import _markdown_to_html, _wechat_html, compose_draft
from .connectors import collect_enabled_sources, collect_from_source
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
    ExecutionChainSnapshot,
    FreshnessSnapshot,
    GithubSignalItem,
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


DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "state.json"
UTC = timezone.utc
LOCAL_TZ = timezone(timedelta(hours=8))
MAX_RAW_ITEMS = 480


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
    # ── 占位/降级源（未适配的国内平台，保留入口） ──
    _api_source("bilibili-tech", "B站科技区", "legacy_bilibili", priority=5, enabled=False, tags=["cn", "video"]),
    _api_source("toutiao-tech", "今日头条科技", "legacy_toutiao", priority=5, enabled=False, tags=["cn", "headline"]),
    _api_source("youtube-ml", "YouTube ML 频道", "legacy_youtube", priority=4, enabled=False, schedule="0 */4 * * *", tags=["video"]),
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
            "normalized_items": [],
            "candidates": [],
            "drafts": [],
            "publish_tasks": [],
            "jobs": [],
            "logs": [],
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
            "llm": {
                "providers": [
                    {
                        "key": "glm",
                        "label": "智谱 GLM",
                        "base_url": "https://open.bigmodel.cn/api/paas/v4",
                        "api_key": "",
                        "model_id": "glm-4.7-flash",
                        "enabled": True,
                    },
                ],
                "tasks": [
                    {"task_key": "outline", "provider_key": "glm", "model_id": "glm-4.7-flash", "temperature": 0.4, "max_tokens": 2048},
                    {"task_key": "article", "provider_key": "glm", "model_id": "glm-4.7-flash", "temperature": 0.7, "max_tokens": 4096},
                    {"task_key": "title", "provider_key": "glm", "model_id": "glm-4.7-flash", "temperature": 0.8, "max_tokens": 512},
                    {"task_key": "summary", "provider_key": "glm", "model_id": "glm-4.7-flash", "temperature": 0.5, "max_tokens": 1024},
                ],
                "usage_today": {},
            },
            "reference_projects": reference_projects,
            "runtime_plan": {
                "launch_mode": "interval_now",
                "start_at": None,
                "interval_minutes": 30,
                "timezone": "Asia/Shanghai",
            },
            "runtime": {
                "scheduler_running": False,
                "control_state": "stopped",
                "launch_mode": "interval_now",
                "current_mode": "radar_only",
                "last_collect_at": None,
                "last_candidate_at": None,
                "last_draft_at": None,
                "next_collect_at": None,
                "current_cycle": "idle",
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
            },
        }
        self._sync_sources_internal(state, triggered_by="bootstrap")
        self._build_digest_internal(state, triggered_by="bootstrap", limit=3)
        self._refresh_browser_session(state)
        self._append_log(state, "info", "system", "已完成 Auto News Studio 信息层优先版状态初始化。", stream="system_runtime")
        return state

    def _build_source_registry(self) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = deepcopy(DEFAULT_SOURCES)
        seen_keys = {item["key"] for item in merged}
        seen_urls = {item["url"] for item in merged if item.get("url")}
        for source in build_legacy_rss_sources():
            if source["key"] in seen_keys or source.get("url") in seen_urls:
                continue
            merged.append(source)
            seen_keys.add(source["key"])
            if source.get("url"):
                seen_urls.add(source["url"])
        return merged

    def _read(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(self.data_file.read_text(encoding="utf-8"))

    def _write(self, payload: dict[str, Any]) -> None:
        with self._lock:
            temp_file = self.data_file.with_suffix(".tmp")
            temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_file.replace(self.data_file)

    def _upgrade_state(self, state: dict[str, Any]) -> dict[str, Any]:
        state.setdefault("llm", {"providers": [], "tasks": [], "usage_today": {}})
        llm = state["llm"]
        if not llm.get("providers"):
            llm["providers"] = [
                {
                    "key": "glm",
                    "label": "智谱 GLM",
                    "base_url": "https://open.bigmodel.cn/api/paas/v4",
                    "api_key": "",
                    "model_id": "glm-4.7-flash",
                    "enabled": True,
                },
            ]
        if not llm.get("tasks"):
            llm["tasks"] = [
                {"task_key": "outline", "provider_key": "glm", "model_id": "glm-4.7-flash", "temperature": 0.4, "max_tokens": 2048},
                {"task_key": "article", "provider_key": "glm", "model_id": "glm-4.7-flash", "temperature": 0.7, "max_tokens": 4096},
                {"task_key": "title", "provider_key": "glm", "model_id": "glm-4.7-flash", "temperature": 0.8, "max_tokens": 512},
                {"task_key": "summary", "provider_key": "glm", "model_id": "glm-4.7-flash", "temperature": 0.5, "max_tokens": 1024},
            ]
        state.setdefault("automation_mode", "radar_only")
        state.setdefault("automation_mode_definitions", deepcopy(AUTOMATION_MODE_DEFINITIONS))
        state.setdefault("automation_profiles", deepcopy(DEFAULT_AUTOMATION_PROFILES))
        state.setdefault("runtime_plan", {})
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
        runtime.setdefault("last_collect_at", None)
        runtime.setdefault("last_candidate_at", None)
        runtime.setdefault("last_draft_at", None)
        runtime.setdefault("next_collect_at", None)
        runtime.setdefault("current_cycle", "idle")
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
        }

    def _runtime_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        runtime_plan = state.setdefault("runtime_plan", {})
        defaults = self._default_runtime_plan(state)
        for key, value in defaults.items():
            runtime_plan.setdefault(key, value)
        runtime_plan["timezone"] = str(runtime_plan.get("timezone") or "Asia/Shanghai")
        runtime_plan["launch_mode"] = str(runtime_plan.get("launch_mode") or "interval_now")
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
        self._sync_runtime_counters(runtime)
        return runtime

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

    def _rebuild_candidates_for_state(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        raw_lookup = {item["id"]: item for item in state["raw_items"]}
        normalized = normalize_raw_items(state["raw_items"], self._sources_by_key(state))
        for item in normalized:
            collected_at = self._latest_collected_at(raw_lookup, item.get("raw_item_ids", []))
            item["collected_at"] = collected_at
            item["freshness_bucket"] = freshness_bucket(collected_at)
        candidates = build_candidates(normalized, state["current_mode"])
        draft_candidate_ids = {draft["candidate_topic_id"] for draft in state["drafts"]}
        for candidate in candidates:
            candidate["draft_exists"] = candidate["id"] in draft_candidate_ids
        state["normalized_items"] = normalized
        state["candidates"] = candidates
        runtime = self._runtime(state)
        runtime["last_candidate_at"] = now_iso()
        return candidates

    def _sync_due_sources(self, state: dict[str, Any], triggered_by: str, minimum_interval_minutes: int | None = None) -> SourceSyncResponse:
        now = datetime.now(UTC)
        sources_by_key = self._sources_by_key(state)
        runtime = self._runtime(state)
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
        for source in due_sources:
            try:
                items, warning = collect_from_source(source)
                collected.extend(items)
                if warning:
                    warnings.append(f"{source['name']}: {warning}")
            except Exception as exc:  # pragma: no cover - defensive
                warnings.append(f"{source['name']}: 抓取器异常，已跳过: {exc}")
                items = []
            count = len(items)
            source["item_count"] = count
            source["last_synced_at"] = stamp
            warning_text = next((item for item in warnings if item.startswith(f"{source['name']}:")), None)
            if warning_text and count:
                source["health_status"] = "warning"
                source["health_detail"] = warning_text
            elif warning_text:
                source["health_status"] = "error"
                source["health_detail"] = warning_text
            else:
                source["health_status"] = "healthy"
                source["health_detail"] = f"最近一次同步产生 {count} 条素材。"
            source["last_error"] = warning_text
        merged = sorted(existing + collected, key=lambda item: parse_time(item.get("collected_at")) or datetime.min.replace(tzinfo=UTC), reverse=True)
        state["raw_items"] = merged[:MAX_RAW_ITEMS]
        candidates = self._rebuild_candidates_for_state(state)
        runtime["last_collect_at"] = stamp
        runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        self._append_log(
            state,
            "success",
            "collection",
            f"自动同步 {len(due_sources)} 个来源，新增 {len(collected)} 条素材，候选池现有 {len(candidates)} 条。",
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
        raw_items, warnings = collect_enabled_sources(state["sources"])
        sources_by_key = self._sources_by_key(state)
        normalized = normalize_raw_items(raw_items, sources_by_key)
        stamp = now_iso()

        for source in state["sources"]:
            count = sum(1 for item in raw_items if item["source_key"] == source["key"])
            warning_text = next((warning for warning in warnings if warning.startswith(f"{source['name']}:")), None)
            source["item_count"] = count
            source["last_synced_at"] = stamp if source["enabled"] else source.get("last_synced_at")
            if not source["enabled"]:
                source["health_status"] = "idle"
                source["health_detail"] = "已停用"
            elif warning_text and count:
                source["health_status"] = "warning"
                source["health_detail"] = warning_text
            elif warning_text:
                source["health_status"] = "error"
                source["health_detail"] = warning_text
            else:
                source["health_status"] = "healthy"
                source["health_detail"] = f"最近一次同步产生 {count} 条素材。"
            source["last_error"] = warning_text

        state["raw_items"] = raw_items
        candidates = self._rebuild_candidates_for_state(state)
        state["reference_projects"] = write_reference_baseline()
        runtime = self._runtime(state)
        runtime["last_collect_at"] = stamp
        runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        self._append_log(
            state,
            "success",
            "collection",
            f"已同步 {len(raw_items)} 条素材，形成 {len(normalized)} 个标准化事件和 {len(candidates)} 个候选选题。",
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
            draft = compose_draft(candidate, normalized_item, publish_mode, risk_keywords)
            state["drafts"].insert(0, draft)
            candidate["status"] = "drafted"
            candidate["draft_exists"] = True
            candidate["updated_at"] = now_iso()
            drafted.append(draft)
            existing_candidate_ids.add(candidate["id"])
            if limit is not None and len(drafted) >= limit:
                break
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
            if runtime.get("control_state") != "running":
                runtime["scheduled_start_at"] = plan.get("start_at") if plan["launch_mode"] in {"once_at", "interval_at"} else None
            runtime["next_collect_at"] = self._calculate_next_collect_at(state)
            self._append_log(state, "success", "runtime", "已更新自动运行计划。", stream="business_event", actor=actor)
            self._write(state)
            return self._runtime_plan_from_state(state)

    def get_runtime_status(self) -> SchedulerStatus:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            runtime["launch_mode"] = self._runtime_plan(state).get("launch_mode", "interval_now")
            runtime["next_collect_at"] = self._calculate_next_collect_at(state)
            self._write(state)
            return self._scheduler_status_from_state(state)

    def _scheduler_status_from_state(self, state: dict[str, Any]) -> SchedulerStatus:
        runtime = self._runtime(state)
        control_state = str(runtime.get("control_state") or "stopped")
        enabled_at = runtime.get("enabled_at")
        enabled_dt = parse_time(enabled_at)
        uptime_seconds = 0
        if control_state != "stopped" and enabled_dt:
            uptime_seconds = max(int((datetime.now(UTC) - enabled_dt).total_seconds()), 0)
        return SchedulerStatus(
            running=control_state != "stopped",
            control_state=control_state,
            launch_mode=str(runtime.get("launch_mode") or self._runtime_plan(state).get("launch_mode") or "interval_now"),
            current_mode=state["automation_mode"],
            last_collect_at=runtime.get("last_collect_at"),
            last_candidate_at=runtime.get("last_candidate_at"),
            last_draft_at=runtime.get("last_draft_at"),
            next_collect_at=runtime.get("next_collect_at"),
            current_cycle=str(runtime.get("current_cycle", "idle")),
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
        )

    def set_scheduler_running(self, running: bool) -> None:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            runtime["scheduler_running"] = running
            if not running and runtime.get("control_state") != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
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
            runtime["scheduler_running"] = False
            runtime["control_state"] = "stopped"
            runtime["current_cycle"] = "idle"
            runtime["enabled_at"] = None
            runtime["scheduled_start_at"] = None
            runtime["current_cycle_started_at"] = None
            runtime["next_collect_at"] = None
            runtime["launch_mode"] = self._runtime_plan(state).get("launch_mode", "interval_now")
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
            plan = self._runtime_plan(state)
            now = datetime.now(UTC)
            runtime["scheduler_running"] = True
            runtime["current_mode"] = state["automation_mode"]
            runtime["launch_mode"] = plan["launch_mode"]
            runtime["last_error"] = None
            runtime["enabled_at"] = now.replace(microsecond=0).isoformat()
            runtime["scheduled_start_at"] = plan.get("start_at") if plan["launch_mode"] in {"once_at", "interval_at"} else None
            runtime["active_interval_minutes"] = plan.get("interval_minutes")
            if plan["launch_mode"] in {"once_at", "interval_at"} and runtime.get("scheduled_start_at"):
                scheduled_dt = parse_time(runtime["scheduled_start_at"])
                if scheduled_dt and scheduled_dt > now:
                    runtime["control_state"] = "armed"
                    runtime["current_cycle"] = "idle"
                    runtime["next_collect_at"] = runtime["scheduled_start_at"]
                    self._append_log(state, "info", "runtime", "自动运行计划已设定，等待到点启动。", stream="system_runtime", actor=actor)
                    self._append_log(state, "info", "runtime", "已从前端启用自动运行计划。", stream="business_event", actor=actor)
                    self._write(state)
                    return self._scheduler_status_from_state(state)
            runtime["control_state"] = "waiting"
            runtime["next_collect_at"] = self._calculate_next_collect_at(state)
            self._append_log(state, "info", "runtime", "后台自动调度器已启动。", stream="system_runtime", actor=actor)
            self._append_log(state, "info", "runtime", "已从前端恢复自动运行。", stream="business_event", actor=actor)
            result = None
            if plan["launch_mode"] in {"once_now", "interval_now"}:
                result = self._run_automation_cycle_locked(state, triggered_by="runtime_start", force=True)
            else:
                self._write(state)
            return self._scheduler_status_from_state(state if result is not None else self._upgrade_state(self._read()))

    def stop_runtime(self, actor: str = "dashboard") -> SchedulerStatus:
        with self._lock:
            state = self._upgrade_state(self._read())
            runtime = self._runtime(state)
            runtime["scheduler_running"] = False
            if runtime.get("control_state") != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                runtime["current_cycle_started_at"] = None
                runtime["enabled_at"] = None
            runtime["scheduled_start_at"] = None
            runtime["next_collect_at"] = None if runtime.get("control_state") != "running" else runtime.get("next_collect_at")
            self._append_log(state, "warning", "runtime", "后台自动调度器已暂停。", stream="system_runtime", actor=actor)
            self._append_log(state, "warning", "runtime", "已从前端暂停自动运行。", stream="business_event", actor=actor)
            self._write(state)
            return self._scheduler_status_from_state(state)

    def _run_automation_cycle_locked(self, state: dict[str, Any], triggered_by: str, force: bool = False) -> dict[str, Any]:
        runtime = self._runtime(state)
        plan = self._runtime_plan(state)
        mode = self._current_automation_mode_def(state)
        profile = self._current_automation_profile(state)
        now = datetime.now(UTC)
        control_state = str(runtime.get("control_state") or "stopped")

        if not force:
            if not runtime.get("scheduler_running") and control_state != "running":
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                runtime["next_collect_at"] = None
                self._write(state)
                return {"status": "stopped"}
            if control_state == "armed":
                scheduled_at = parse_time(runtime.get("scheduled_start_at"))
                if scheduled_at and now < scheduled_at:
                    runtime["next_collect_at"] = runtime.get("scheduled_start_at")
                    self._write(state)
                    return {"status": "armed"}
                runtime["control_state"] = "waiting"
            elif control_state == "stopped":
                runtime["next_collect_at"] = None
                self._write(state)
                return {"status": "stopped"}
            elif control_state == "waiting":
                next_due = parse_time(runtime.get("next_collect_at"))
                if next_due and now < next_due:
                    self._write(state)
                    return {"status": "waiting"}

        runtime["control_state"] = "running"
        runtime["current_mode"] = state["automation_mode"]
        runtime["current_cycle"] = "collecting"
        runtime["current_cycle_started_at"] = now.replace(microsecond=0).isoformat()
        runtime["last_cycle_started_at"] = runtime["current_cycle_started_at"]
        runtime["launch_mode"] = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")
        runtime["last_error"] = None
        self._sync_runtime_counters(runtime)

        start = datetime.now(UTC)
        try:
            sync_response = self._sync_due_sources(
                state,
                triggered_by="scheduler",
                minimum_interval_minutes=None,
            )
            drafted_count = 0
            synced_to_wechat = 0
            if mode.get("auto_generate_drafts"):
                should_build_drafts = False
                if profile.get("draft_trigger") == "after_sync":
                    should_build_drafts = True
                elif profile.get("draft_trigger") == "scheduled":
                    should_build_drafts = self._is_slot_due(runtime.get("last_draft_at"), str(profile.get("draft_schedule_time") or ""))
                if should_build_drafts:
                    runtime["current_cycle"] = "drafting"
                    drafted = self._build_digest_internal(
                        state,
                        triggered_by="scheduler",
                        limit=int(profile.get("draft_limit", 10) or 10),
                        selection_mode=str(profile.get("draft_selection") or "all_new"),
                    )
                    drafted_count = len(drafted)
                    if profile.get("draft_delivery") == "wechat_draft":
                        runtime["current_cycle"] = "wechat_sync"
                        for draft in drafted:
                            self._sync_wechat_draft_internal(state, draft, "scheduler")
                            synced_to_wechat += 1

            finish = datetime.now(UTC)
            duration = round((finish - start).total_seconds(), 1)
            runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
            runtime["last_cycle_duration_seconds"] = duration
            runtime["current_cycle_started_at"] = None
            runtime["completed_cycles_today"] = int(runtime.get("completed_cycles_today", 0) or 0) + 1
            launch_mode = str(runtime.get("launch_mode") or plan.get("launch_mode") or "interval_now")
            if not runtime.get("scheduler_running") or launch_mode in {"once_now", "once_at"}:
                runtime["scheduler_running"] = False
                runtime["control_state"] = "stopped"
                runtime["current_cycle"] = "idle"
                runtime["enabled_at"] = None
                runtime["scheduled_start_at"] = None
                runtime["active_interval_minutes"] = None
                runtime["next_collect_at"] = None
            else:
                runtime["control_state"] = "waiting"
                runtime["current_cycle"] = "idle"
                runtime["next_collect_at"] = self._calculate_runtime_next_collect_at(state, finish)
            self._append_job(
                state,
                "collect_news",
                f"自动轮次完成：素材 {sync_response.raw_count}，候选 {sync_response.candidate_count}，新增初稿 {drafted_count}，同步微信 {synced_to_wechat}，耗时 {duration}s。",
                triggered_by="scheduler",
            )
            self._write(state)
            return {
                "raw_count": sync_response.raw_count,
                "candidate_count": sync_response.candidate_count,
                "drafted_count": drafted_count,
                "wechat_synced_count": synced_to_wechat,
                "duration": duration,
            }
        except Exception as exc:  # pragma: no cover - scheduler guard
            finish = datetime.now(UTC)
            duration = round((finish - start).total_seconds(), 1)
            runtime["last_cycle_finished_at"] = finish.replace(microsecond=0).isoformat()
            runtime["last_cycle_duration_seconds"] = duration
            runtime["current_cycle_started_at"] = None
            runtime["failed_cycles_today"] = int(runtime.get("failed_cycles_today", 0) or 0) + 1
            runtime["last_error"] = str(exc)
            if not runtime.get("scheduler_running") or str(runtime.get("launch_mode") or plan.get("launch_mode")) in {"once_now", "once_at"}:
                runtime["scheduler_running"] = False
                runtime["control_state"] = "stopped"
                runtime["enabled_at"] = None
                runtime["scheduled_start_at"] = None
                runtime["next_collect_at"] = None
            else:
                runtime["control_state"] = "waiting"
                runtime["next_collect_at"] = self._calculate_runtime_next_collect_at(state, finish)
            runtime["current_cycle"] = "idle"
            self._append_log(state, "error", "runtime", f"自动轮次失败：{exc}", stream="system_runtime")
            self._write(state)
            raise

    def run_automation_cycle(self) -> dict[str, Any]:
        with self._lock:
            state = self._upgrade_state(self._read())
            return self._run_automation_cycle_locked(state, triggered_by="scheduler")

    def list_sources(self) -> list[SourceConnector]:
        state = self._upgrade_state(self._read())
        return [SourceConnector(**item) for item in state["sources"]]

    def update_source(self, source_key: str, payload: SourceConnectorPayload) -> SourceConnector:
        state = self._upgrade_state(self._read())
        source = self._find_source(state, source_key)
        source.update(payload.model_dump())
        source["updated_at"] = now_iso()
        self._append_log(state, "success", "source", f"已更新来源配置：{source['name']}")
        runtime = self._runtime(state)
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        self._write(state)
        return SourceConnector(**source)

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
        runtime["last_successful_sync_at"] = stamp
        runtime["next_collect_at"] = self._calculate_next_collect_at(state, minimum_interval_minutes=self._collect_interval_for_profile(state))
        self._append_log(
            state,
            "success" if not warning_text else "warning",
            "collection",
            f"已重抓来源 {source['name']}，新增 {len(items)} 条素材，候选池现有 {len(candidates)} 条。",
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

    def list_candidates(self) -> list[CandidateTopic]:
        state = self._upgrade_state(self._read())
        return [CandidateTopic(**item) for item in state["candidates"]]

    def _make_llm_service(self, state: dict[str, Any]) -> LLMService | None:
        llm_config = state.get("llm", {})
        if not llm_config or not llm_config.get("providers"):
            return None
        enabled = [p for p in llm_config.get("providers", []) if p.get("enabled")]
        if not enabled:
            return None
        return LLMService(llm_config)

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
                draft = compose_draft(candidate, normalized_item, publish_mode, risk_keywords)
            except Exception:  # pragma: no cover - defensive
                failed_count += 1
                continue
            state["drafts"].insert(0, draft)
            candidate["status"] = "drafted"
            candidate["draft_exists"] = True
            candidate["updated_at"] = now_iso()
            created.append(draft)

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

    # ── LLM config ────────────────────────────────────────────────

    def get_llm_config(self) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        cfg = state.get("llm", {})
        providers = cfg.get("providers", [])
        for p in providers:
            key = p.get("api_key", "")
            if key:
                p["api_key"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        return cfg

    def update_llm_config(self, config: dict[str, Any]) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        existing = state.get("llm", {})
        existing_providers = {p["key"]: p for p in existing.get("providers", [])}

        for provider in config.get("providers", []):
            key = provider["key"]
            api_key = provider.get("api_key", "")
            if api_key.endswith("****") and key in existing_providers:
                provider["api_key"] = existing_providers[key].get("api_key", "")
            existing_providers[key] = provider

        state["llm"] = {
            "providers": list(existing_providers.values()),
            "tasks": config.get("tasks", existing.get("tasks", [])),
            "usage_today": existing.get("usage_today", {}),
        }
        self._write(state)
        self._append_log(state, "info", "config", "已更新 AI 模型配置")
        return state["llm"]

    def test_llm_provider(self, provider_key: str) -> dict[str, Any]:
        state = self._upgrade_state(self._read())
        llm_service = self._make_llm_service(state)
        if not llm_service:
            raise ValueError("没有可用的 LLM 服务商配置")
        result = llm_service.test_connection(provider_key)
        providers = state.get("llm", {}).get("providers", [])
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
        browser = self._refresh_browser_session(state)
        backends = self._publish_backends(state)
        runtime = self._runtime(state)
        runtime["next_collect_at"] = self._calculate_next_collect_at(state)
        runtime["launch_mode"] = self._runtime_plan(state).get("launch_mode", "interval_now")
        runtime_status = SchedulerStatus(
            running=bool(runtime.get("control_state") != "stopped"),
            control_state=str(runtime.get("control_state", "stopped")),
            launch_mode=str(runtime.get("launch_mode", "interval_now")),
            current_mode=state["automation_mode"],
            last_collect_at=runtime.get("last_collect_at"),
            last_candidate_at=runtime.get("last_candidate_at"),
            last_draft_at=runtime.get("last_draft_at"),
            next_collect_at=runtime.get("next_collect_at"),
            current_cycle=str(runtime.get("current_cycle", "idle")),
            enabled_at=runtime.get("enabled_at"),
            scheduled_start_at=runtime.get("scheduled_start_at"),
            current_cycle_started_at=runtime.get("current_cycle_started_at"),
            last_cycle_started_at=runtime.get("last_cycle_started_at"),
            last_cycle_finished_at=runtime.get("last_cycle_finished_at"),
            last_cycle_duration_seconds=runtime.get("last_cycle_duration_seconds"),
            uptime_seconds=max(
                int((datetime.now(UTC) - parse_time(runtime.get("enabled_at"))).total_seconds()),
                0,
            ) if runtime.get("control_state") != "stopped" and parse_time(runtime.get("enabled_at")) else 0,
            completed_cycles_today=int(runtime.get("completed_cycles_today", 0) or 0),
            failed_cycles_today=int(runtime.get("failed_cycles_today", 0) or 0),
            last_error=runtime.get("last_error"),
        )
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
