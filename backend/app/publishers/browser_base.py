from __future__ import annotations

import ctypes
from pathlib import Path
import re
import webbrowser
from uuid import uuid4

from ..store_base import PROJECT_ROOT, RUNTIME_TEMP_DIR, now_iso
from ._legacy import legacy_publishers


ARTIFACT_ROOT = RUNTIME_TEMP_DIR / "publish_artifacts"
PROJECT_ROOT = PROJECT_ROOT
BROWSER_PROFILE_ROOT = PROJECT_ROOT / "runtime" / "browser"
DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS = 60
DEFAULT_EMPTY_CHECK_CONFIRMATIONS = 3
DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS = 120
WINDOWS_BROWSER_PATHS = {
    "edge": [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ],
    "chrome": [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ],
}

try:
    USER32 = ctypes.windll.user32
except Exception:  # pragma: no cover - non-Windows safety
    USER32 = None

SELECTOR_PROFILES = legacy_publishers.SELECTOR_PROFILES


def normalize_browser_name(value: object | None) -> str:
    compact = str(value or "").strip().lower()
    if compact in {"edge", "chrome"}:
        return compact
    return "edge"


def default_browser_profile_path(browser_name: str = "edge") -> Path:
    compact = normalize_browser_name(browser_name)
    return BROWSER_PROFILE_ROOT / f"wechat-{compact}-profile"


def default_douyin_browser_profile_path(browser_name: str = "edge") -> Path:
    compact = normalize_browser_name(browser_name)
    return BROWSER_PROFILE_ROOT / f"douyin-{compact}-profile"


def resolve_profile_path(value: object | None, browser_name: object | None = None) -> Path:
    compact = str(value or "").strip()
    if compact:
        return Path(compact).expanduser()
    return default_browser_profile_path(normalize_browser_name(browser_name))


def ensure_channel_defaults(channel: dict[str, object]) -> dict[str, object]:
    next_channel = dict(channel)
    browser_name = normalize_browser_name(next_channel.get("browser_name"))
    next_channel["browser_name"] = browser_name
    next_channel["browser_profile_path"] = str(resolve_profile_path(next_channel.get("browser_profile_path"), browser_name))
    next_channel["publish_entry_url"] = str(next_channel.get("publish_entry_url") or "https://mp.weixin.qq.com/")
    next_channel["selectors_version"] = str(next_channel.get("selectors_version") or "wechat-mp-v1")
    next_channel["sidecar_url"] = str(next_channel.get("sidecar_url") or "http://127.0.0.1:8091")
    return next_channel


def ensure_douyin_channel_defaults(channel: dict[str, object]) -> dict[str, object]:
    next_channel = dict(channel)
    browser_name = normalize_browser_name(next_channel.get("browser_name"))
    next_channel["browser_name"] = browser_name
    profile_path = str(next_channel.get("browser_profile_path") or "").strip()
    next_channel["browser_profile_path"] = profile_path or str(default_douyin_browser_profile_path(browser_name))
    next_channel["publish_entry_url"] = str(next_channel.get("publish_entry_url") or "https://creator.douyin.com/")
    next_channel["selectors_version"] = str(next_channel.get("selectors_version") or "douyin-creator-v1")
    next_channel["sidecar_url"] = str(next_channel.get("sidecar_url") or "http://127.0.0.1:8091")
    return next_channel


def browser_channel_name(browser_name: str) -> str:
    return "msedge" if normalize_browser_name(browser_name) == "edge" else "chrome"


def resolve_browser_executable(browser_name: str) -> str | None:
    compact = normalize_browser_name(browser_name)
    for path in WINDOWS_BROWSER_PATHS.get(compact, []):
        if path.exists():
            return str(path)
    return None


def build_wechat_target_id(target_id: str) -> str:
    return f"wx_shadow_{target_id.replace('brief-', '')}"


def build_preview_url(target_id: str) -> str:
    return f"https://mp.weixin.qq.com/cgi-bin/home?t=home/index&draft={target_id.replace('brief-', '')}"


def maybe_open_url(url: str) -> None:
    try:  # pragma: no cover - depends on host shell
        webbrowser.open(url, new=2)
    except Exception:
        pass


def get_selector_profile(version: str) -> dict[str, list[str] | str]:
    return SELECTOR_PROFILES.get(version, SELECTOR_PROFILES["wechat-mp-v1"])


def create_publish_task(
    target_id: str,
    action: str,
    status: str,
    message: str,
    triggered_by: str,
    selector_profile: str,
    artifacts: list[str] | None = None,
    step_logs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": f"task-{uuid4().hex[:8]}",
        "target_id": target_id,
        "action": action,
        "status": status,
        "stage": action,
        "message": message,
        "triggered_by": triggered_by,
        "created_at": now_iso(),
        "artifacts": artifacts or [],
        "step_logs": step_logs or [],
        "selector_profile": selector_profile,
    }


def build_remote_draft_key(
    title: str,
    url: str,
    appmsg_id: str | None = None,
    updated_at: str | None = None,
    occurrence: int | None = None,
) -> str:
    compact_url = str(url or "").strip()
    compact_id = str(appmsg_id or "").strip()
    if compact_id:
        return f"appmsg:{compact_id}"
    if compact_url:
        return f"url:{compact_url}"
    if occurrence is not None:
        return f"card:{occurrence}"
    return ""


def refresh_browser_session(channel: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    channel = ensure_channel_defaults(channel)
    profile_path = resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    last_opened_url = str(current.get("last_opened_url") or "") or entry_url
    current_page = str(current.get("current_page") or current.get("last_opened_url") or "") or entry_url

    next_state = dict(current)
    next_state.update(
        {
            "browser_name": channel.get("browser_name", "edge"),
            "user_data_dir": str(profile_path),
            "logged_in": bool(current.get("logged_in")) and profile_path.exists() and profile_path.is_dir(),
            "last_checked_at": now_iso(),
            "last_error": None if profile_path.exists() else "浏览器用户目录尚未创建，请先打开公众号后台完成首次登录。",
            "selectors_version": selector_version,
            "last_selector_check": selector_version,
            "last_opened_url": last_opened_url,
            "current_page": current_page,
            "sidecar_health": "offline",
            "manager_alive": bool(current.get("manager_alive")),
            "window_state": str(current.get("window_state") or "unknown"),
            "resident_page": current.get("resident_page"),
            "busy": bool(current.get("busy")),
            "last_reset_reason": current.get("last_reset_reason"),
            "session_generation": int(current.get("session_generation") or 0),
            "last_action": current.get("last_action"),
            "last_action_phase": current.get("last_action_phase"),
            "is_session_level_error": bool(current.get("is_session_level_error")),
        }
    )
    if not profile_path.parent.exists():
        profile_path.parent.mkdir(parents=True, exist_ok=True)
    next_state.update(legacy_publishers.WECHAT_BROWSER_MANAGER.manager_state())
    return next_state


def collect_backend_status(channel: dict[str, object], browser: dict[str, object]) -> list[dict[str, object]]:
    channel = ensure_channel_defaults(channel)
    profile_path = resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))
    if browser.get("logged_in"):
        browser_detail = "已匹配浏览器 profile，公众号登录态可复用。"
    elif profile_path.exists():
        browser_detail = "已匹配浏览器 profile，等待扫码登录后再验证。"
    else:
        browser_detail = "浏览器 profile 尚未生成，请先完成配置。"
    selector_profile = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_detail = f"当前选择器配置 {selector_profile}，包含 {len(get_selector_profile(selector_profile)) - 1} 组动作锚点。"
    return [
        {
            "key": "browser",
            "label": "浏览器登录会话",
            "health": "healthy" if browser.get("logged_in") else "warning",
            "detail": browser_detail,
            "configured": bool(str(channel.get("browser_profile_path", ""))),
        },
        {
            "key": "selectors",
            "label": "页面选择器配置",
            "health": "healthy" if selector_profile in SELECTOR_PROFILES else "warning",
            "detail": selector_detail,
            "configured": True,
        },
    ]


def refresh_douyin_browser_session(channel: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    channel = ensure_douyin_channel_defaults(channel)
    profile_path = Path(str(channel.get("browser_profile_path") or "")).expanduser()
    selector_version = str(channel.get("selectors_version", "douyin-creator-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://creator.douyin.com/"))
    next_state = dict(current)
    next_state.update(
        {
            "platform": "douyin_creator",
            "browser_name": channel.get("browser_name", "edge"),
            "user_data_dir": str(profile_path),
            "logged_in": bool(current.get("logged_in")) and profile_path.exists() and profile_path.is_dir(),
            "last_checked_at": now_iso(),
            "last_error": None if profile_path.exists() else "浏览器用户目录尚未创建，请先打开抖音创作者中心完成首次登录。",
            "selectors_version": selector_version,
            "last_selector_check": selector_version,
            "last_opened_url": str(current.get("last_opened_url") or "") or entry_url,
            "current_page": str(current.get("current_page") or current.get("last_opened_url") or "") or entry_url,
            "sidecar_health": "offline",
            "manager_alive": False,
            "window_state": str(current.get("window_state") or "unknown"),
            "resident_page": current.get("resident_page"),
            "busy": False,
            "last_reset_reason": current.get("last_reset_reason"),
            "session_generation": int(current.get("session_generation") or 0),
            "last_action": current.get("last_action"),
            "last_action_phase": current.get("last_action_phase"),
            "is_session_level_error": bool(current.get("is_session_level_error")),
        }
    )
    if not profile_path.parent.exists():
        profile_path.parent.mkdir(parents=True, exist_ok=True)
    return next_state


def collect_douyin_backend_status(channel: dict[str, object], browser: dict[str, object]) -> list[dict[str, object]]:
    channel = ensure_douyin_channel_defaults(channel)
    profile_path = Path(str(channel.get("browser_profile_path") or "")).expanduser()
    if browser.get("logged_in"):
        browser_detail = "已匹配浏览器 profile，抖音创作者中心登录态可复用。"
    elif profile_path.exists():
        browser_detail = "已匹配浏览器 profile，等待登录抖音创作者中心后再验证。"
    else:
        browser_detail = "浏览器 profile 尚未生成，请先完成配置。"
    selector_profile = str(channel.get("selectors_version", "douyin-creator-v1"))
    selector_detail = f"当前选择器配置 {selector_profile}，包含 {len(get_selector_profile(selector_profile)) - 1} 组动作锚点。"
    return [
        {
            "key": "douyin-browser",
            "label": "抖音浏览器登录会话",
            "health": "healthy" if browser.get("logged_in") else "warning",
            "detail": browser_detail,
            "configured": bool(str(channel.get("browser_profile_path", ""))),
        },
        {
            "key": "douyin-selectors",
            "label": "抖音页面选择器配置",
            "health": "healthy" if selector_profile in SELECTOR_PROFILES else "warning",
            "detail": selector_detail,
            "configured": True,
        },
    ]


def _write_debug_artifact(target: Path, lines: list[str]) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(target)


_pick_selector = legacy_publishers._pick_selector
_pick_visible_locator = legacy_publishers._pick_visible_locator
_page_url = legacy_publishers._page_url
_is_page_closed = legacy_publishers._is_page_closed
_list_live_context_pages = legacy_publishers._list_live_context_pages
_can_interact_with_page = legacy_publishers._can_interact_with_page
_count_context_pages = legacy_publishers._count_context_pages
_enforce_single_tab = legacy_publishers._enforce_single_tab
WechatBrowserManager = legacy_publishers.WechatBrowserManager
WECHAT_BROWSER_MANAGER = legacy_publishers.WECHAT_BROWSER_MANAGER
DOUYIN_BROWSER_MANAGER = legacy_publishers.DOUYIN_BROWSER_MANAGER

__all__ = [
    "ARTIFACT_ROOT",
    "PROJECT_ROOT",
    "BROWSER_PROFILE_ROOT",
    "DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS",
    "DEFAULT_EMPTY_CHECK_CONFIRMATIONS",
    "DEFAULT_BACKGROUND_POLL_INTERVAL_SECONDS",
    "WINDOWS_BROWSER_PATHS",
    "SELECTOR_PROFILES",
    "WechatBrowserManager",
    "WECHAT_BROWSER_MANAGER",
    "DOUYIN_BROWSER_MANAGER",
    "now_iso",
    "normalize_browser_name",
    "default_browser_profile_path",
    "default_douyin_browser_profile_path",
    "resolve_profile_path",
    "ensure_channel_defaults",
    "ensure_douyin_channel_defaults",
    "browser_channel_name",
    "resolve_browser_executable",
    "build_wechat_target_id",
    "build_preview_url",
    "maybe_open_url",
    "get_selector_profile",
    "create_publish_task",
    "build_remote_draft_key",
    "refresh_browser_session",
    "collect_backend_status",
    "refresh_douyin_browser_session",
    "collect_douyin_backend_status",
    "_write_debug_artifact",
    "_pick_selector",
    "_pick_visible_locator",
    "_page_url",
    "_is_page_closed",
    "_list_live_context_pages",
    "_can_interact_with_page",
    "_count_context_pages",
    "_enforce_single_tab",
]
