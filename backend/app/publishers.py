from __future__ import annotations

import ctypes
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
import re
import subprocess
import time
from threading import Lock, Thread
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser
from uuid import uuid4

from .wechat_format import markdown_to_plain_text, markdown_to_wechat_html, strip_markdown_title


UTC = timezone.utc
ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "data" / "artifacts"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
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

SELECTOR_PROFILES: dict[str, dict[str, list[str] | str]] = {
    "wechat-mp-v1": {
        "logged_in": [
            ".weui-desktop-account__thumb",
            ".weui-desktop-layout__main",
            ".weui-desktop-side-menu",
        ],
        "new_article": [
            ".new-creation__menu-item:has(.new-creation__menu-title:text-is('文章'))",
            ".new-creation__menu-content:has(.new-creation__menu-title:text-is('文章'))",
            ".new-creation__menu-title:text-is('文章')",
        ],
        "draft_box": [
            "a#menu_10125[href*='action=list_card']",
            "a.weui-desktop-menu__link.menu_report[href*='action=list_card']",
            "a:has-text('草稿箱')",
            "div:has-text('草稿箱')",
            "a[href*='action=list_card']",
            "text=草稿箱",
            "a[href*='draft']",
            "text=草稿箱",
        ],
        "publish_history": [
            "a#menu_10126[href*='appmsgpublish']",
            "a.weui-desktop-menu__link.menu_report[href*='appmsgpublish']",
            "a:has-text('发表记录')",
            "div:has-text('发表记录')",
            "a[href*='appmsgpublish']",
            "text=发表记录",
        ],
        "content_manage": [
            "span.weui-desktop-menu__link[title='内容管理']",
            "span.weui-desktop-menu__name:has-text('内容管理')",
            "a:has-text('内容管理')",
            "div:has-text('内容管理')",
            "text=内容管理",
        ],
        "title_input": [
            "div.ProseMirror[data-placeholder*='请在这里输入标题']",
            "div.ProseMirror[data-placeholder*='标题']",
            "textarea.js_article_title",
            "input[placeholder*='标题']",
            "textarea[placeholder*='标题']",
        ],
        "author_input": [
            "input.js_author",
            "input[placeholder*='作者']",
        ],
        "digest_input": [
            "textarea.js_desc",
            "textarea[placeholder*='摘要']",
        ],
        "editor": [
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']",
            "#edui1_iframeholder .mock-iframe-body .rich_media_content div.ProseMirror[contenteditable='true']",
            ".editor-v-root .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']",
            "div.ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])",
            "div.ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])[style*='min-height']",
            ".rich_media_content .ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])",
            "div.ProseMirror:has(.editor_content_placeholder)",
            ".rich_media_content [contenteditable='true']",
            ".rich_media_content",
        ],
        "preview_button": [
            "button:has-text('预览')",
            "span:has-text('预览')",
            "text=预览",
        ],
        "save_draft_button": [
            "button:has-text('保存为草稿')",
            "span:has-text('保存为草稿')",
            "text=保存为草稿",
        ],
        "original_setting": [
            "#js_original",
            ".js_original_apply_cell",
            ".appmsg-editor__setting-group.origined__setting-group",
        ],
        "reward_setting": [
            "#js_reward_setting_area",
            ".reward__setting-group.js_reward_open_cell",
            ".reward__setting-group",
        ],
        "primary_confirm_button": [
            "button.weui-desktop-btn.weui-desktop-btn_primary:has-text('确定')",
            "button.weui-desktop-btn_primary:has-text('确定')",
            "button:has-text('确定')",
        ],
        "publish_button": [
            "button:has-text('发表')",
            "span:has-text('发表')",
            "text=发表",
        ],
        "confirm_publish": [
            "button:has-text('确定')",
            ".weui-dialog__btn_primary",
            "text=确认",
        ],
    },
    "douyin-creator-v1": {
        "logged_in": [
            "text=发布文章",
            "text=发布作品",
            "text=内容管理",
            "text=创作者中心",
            "[href*='content/manage']",
            "[href*='creator-micro']",
        ],
        "publish_entry": [
            "text=发布文章",
            "div:has-text('发布文章')",
            ".title-HvY9Az:has-text('发布文章')",
            "text=发布作品",
            "text=去发布",
            "a[href*='upload']",
            "a[href*='publish']",
            "button:has-text('发布文章')",
            "button:has-text('发布作品')",
        ],
        "start_article": [
            "text=我要发文",
            "button:has-text('我要发文')",
            ".semi-button-content:has-text('我要发文')",
        ],
        "title_input": [
            "input[placeholder*='标题']",
            "div:has-text('文章标题') input",
            "textarea[placeholder*='标题']",
            "[contenteditable='true'][data-placeholder*='标题']",
            "div[contenteditable='true'][placeholder*='标题']",
        ],
        "summary_input": [
            "textarea[placeholder*='摘要']",
            "input[placeholder*='摘要']",
            "div:has-text('文章摘要') textarea",
            "div:has-text('文章摘要') input",
        ],
        "content_editor": [
            "div:has-text('文章正文') .ProseMirror[contenteditable='true']",
            "[contenteditable='true'][data-placeholder*='正文']",
            "[contenteditable='true'][placeholder*='正文']",
            ".ProseMirror[contenteditable='true']",
            "div[role='textbox'][contenteditable='true']",
            "[contenteditable='true']",
        ],
        "cover_upload": [
            "input[type='file']",
            "text=上传封面",
            "text=添加封面",
            "text=上传图片",
            "button:has-text('上传图片')",
        ],
        "images_panel": [
            "text=图片",
            "text=封面",
            "text=配图",
            "[class*='upload']",
            "[class*='image']",
        ],
        "submit_button": [
            "button:has-text('发布')",
            "button:has-text('提交')",
            "button:has-text('保存')",
            "button:has-text('预览')",
        ],
        "ai_illustration": [
            "text=AI 配图",
            "span:has-text('AI 配图')",
            "[class*='iconContainer']:has-text('AI 配图')",
            "[class*='mycard-info-text-icon']:has-text('AI 配图')",
        ],
    },
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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
    next_state.update(WECHAT_BROWSER_MANAGER.manager_state())
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


def _pick_selector(page, selectors: list[str] | str, timeout: int = 2200) -> str | None:
    selector_list = selectors if isinstance(selectors, list) else [selectors]
    for selector in selector_list:
        try:
            locator = page.locator(str(selector))
            count = locator.count()
            if count <= 0:
                continue
            matched_visible = False
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    candidate.wait_for(state="visible", timeout=timeout)
                    matched_visible = True
                    break
                except Exception:
                    continue
            if matched_visible:
                return str(selector)
            locator.first.wait_for(timeout=timeout)
            return str(selector)
        except Exception:
            continue
    return None


def _pick_visible_locator(page, selector: str, timeout: int = 2200):
    locator = page.locator(selector)
    count = locator.count()
    if count <= 0:
        return locator.first
    for index in range(count):
        candidate = locator.nth(index)
        try:
            candidate.wait_for(state="visible", timeout=timeout)
            return candidate
        except Exception:
            continue
    return locator.first


def _page_url(page) -> str:
    try:
        return str(getattr(page, "url", "") or "")
    except Exception:
        return ""


def _is_page_closed(page) -> bool:
    try:
        checker = getattr(page, "is_closed", None)
        if callable(checker):
            return bool(checker())
    except Exception:
        return False
    return bool(getattr(page, "closed", False))


def _count_context_pages(context) -> int:
    try:
        pages = list(getattr(context, "pages", []) or [])
    except Exception:
        return 0
    return sum(0 if _is_page_closed(page) else 1 for page in pages)


def _list_live_context_pages(context) -> list[object]:
    try:
        pages = list(getattr(context, "pages", []) or [])
    except Exception:
        return []
    return [page for page in pages if not _is_page_closed(page)]


def _can_interact_with_page(page) -> bool:
    if page is None or _is_page_closed(page):
        return False
    try:
        evaluator = getattr(page, "evaluate", None)
        if callable(evaluator):
            evaluator("() => document.readyState")
        else:
            _ = getattr(page, "url", "")
        return True
    except Exception:
        return False


def _enforce_single_tab(context, page, step_logs: list[str], *, phase: str, allow_recover: bool = False) -> None:
    pages = _list_live_context_pages(context)
    page_count = len(pages)
    step_logs.append(f"单标签页检查 phase={phase} page_count={page_count}")
    if page_count <= 1:
        return

    home_page = None
    for candidate in pages:
        candidate_url = _page_url(candidate)
        if "mp.weixin.qq.com" in candidate_url and "appmsg" not in candidate_url and "action=list_card" not in candidate_url:
            home_page = candidate
            break

    if allow_recover:
        keep_page = home_page or page
        closed_count = 0
        for candidate in pages:
            if candidate is keep_page:
                continue
            try:
                candidate.close()
                closed_count += 1
            except Exception:
                pass
        step_logs.append(f"单标签页恢复 phase={phase} closed_tabs={closed_count}")
        remaining = _count_context_pages(context)
        step_logs.append(f"单标签页恢复后 page_count={remaining}")
        if remaining <= 1:
            return

    raise RuntimeError(f"违反单标签页约束：检测到 {page_count} 个标签页。")


def _converge_context_to_target(context, target_page, step_logs: list[str], *, phase: str) -> None:
    pages = _list_live_context_pages(context)
    closed_count = 0
    for candidate in pages:
        if candidate is target_page:
            continue
        try:
            candidate.close()
            closed_count += 1
        except Exception as exc:
            step_logs.append(f"单标签页收敛关闭失败 phase={phase} url={_page_url(candidate)} error={exc}")
    remaining = _count_context_pages(context)
    step_logs.append(f"单标签页收敛 phase={phase} closed_tabs={closed_count} remaining={remaining}")
    if remaining > 1:
        raise RuntimeError(f"违反单标签页约束：检测到 {remaining} 个标签页。")


def _window_pid(hwnd: int) -> int:
    if USER32 is None:
        return 0
    process_id = ctypes.c_ulong()
    USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value or 0)


def _find_window_for_pid(pid: int) -> int | None:
    if USER32 is None or pid <= 0:
        return None

    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_handler(hwnd, _lparam):
        handle = int(hwnd)
        if not USER32.IsWindowVisible(handle):
            return True
        if _window_pid(handle) != pid:
            return True
        found.append(handle)
        return False

    USER32.EnumWindows(enum_handler, 0)
    return found[0] if found else None


def _set_window_state(hwnd: int | None, *, minimize: bool) -> bool:
    if USER32 is None or not hwnd:
        return False
    try:
        if not USER32.IsWindow(hwnd):
            return False
        show_code = 6 if minimize else 9  # SW_MINIMIZE / SW_RESTORE
        USER32.ShowWindow(hwnd, show_code)
        if not minimize:
            try:
                USER32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        return True
    except Exception:
        return False


class WechatBrowserManager:
    def __init__(self) -> None:
        self._playwright = None
        self._context = None
        self._page = None
        self._browser_pid: int | None = None
        self._hwnd: int | None = None
        self._lock = Lock()
        self._channel_signature: tuple[str, str, str, str] | None = None
        self._window_state: str = "unknown"
        self._worker: Thread | None = None
        self._queue: Queue | None = None
        self._worker_thread_id: int | None = None
        self._manager_alive: bool = False
        self._resident_page: str | None = None
        self._last_reset_reason: str | None = None
        self._session_generation: int = 0
        self._last_action: str | None = None
        self._last_action_phase: str | None = None

    def startup(self) -> None:
        self._ensure_worker()

    def _ensure_worker(self) -> None:
        if self._worker and self._worker.is_alive() and self._queue is not None:
            return
        self._queue = Queue()
        self._worker = Thread(target=self._worker_loop, name="wechat-browser-manager", daemon=True)
        self._worker.start()

    def _worker_loop(self) -> None:
        self._worker_thread_id = threading.get_ident()
        self._manager_alive = True
        assert self._queue is not None
        while True:
            item = self._queue.get()
            if item is None:
                break
            fn, result_box = item
            try:
                result_box["result"] = fn()
            except Exception as exc:
                result_box["error"] = exc
            finally:
                result_box["event"].set()
        self._close_runtime_internal()
        self._manager_alive = False
        self._worker_thread_id = None

    def _run_in_worker(self, fn):
        self._ensure_worker()
        result_box = {"result": None, "error": None, "event": threading.Event()}
        assert self._queue is not None
        self._queue.put((fn, result_box))
        result_box["event"].wait()
        if result_box["error"] is not None:
            raise result_box["error"]
        return result_box["result"]

    def shutdown(self) -> None:
        if self._worker_thread_id == threading.get_ident():
            self._close_runtime_internal()
            self._manager_alive = False
            return
        if self._queue is not None:
            self._queue.put(None)
        if self._worker is not None:
            self._worker.join(timeout=10)
        self._worker = None
        self._queue = None
        self._worker_thread_id = None
        self._manager_alive = False

    def _close_runtime_internal(self) -> None:
        page = self._page
        context = self._context
        playwright = self._playwright
        self._page = None
        self._context = None
        self._playwright = None
        self._browser_pid = None
        self._hwnd = None
        self._channel_signature = None
        self._window_state = "unknown"
        self._resident_page = None
        self._last_action = None
        self._last_action_phase = None
        for closable in (page, context):
            if closable is None:
                continue
            try:
                closable.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass

    def is_alive(self) -> bool:
        return bool(self._manager_alive and self._worker is not None and self._worker.is_alive())

    def is_busy(self) -> bool:
        return self._lock.locked()

    def signature_for(self, channel: dict[str, object]) -> tuple[str, str, str, str]:
        normalized = ensure_channel_defaults(channel)
        return (
            str(normalized.get("browser_name") or "edge"),
            str(normalized.get("browser_profile_path") or ""),
            str(normalized.get("publish_entry_url") or "https://mp.weixin.qq.com/"),
            str(normalized.get("selectors_version") or "wechat-mp-v1"),
        )

    def reset(self, reason: str = "") -> None:
        self._resident_page = f"reset:{reason or 'unknown'}"
        self._last_reset_reason = reason or "unknown"
        if self._worker_thread_id == threading.get_ident():
            self._close_runtime_internal()
            return
        try:
            self._run_in_worker(self._close_runtime_internal)
        except Exception:
            self._close_runtime_internal()

    def _ensure_playwright(self):
        if self._playwright is not None:
            return self._playwright
        from playwright.sync_api import sync_playwright  # type: ignore

        self._playwright = sync_playwright().start()
        return self._playwright

    def _extract_browser_pid(self) -> int | None:
        context = self._context
        if context is None:
            return None
        impl = getattr(context, "_impl_obj", None)
        browser = getattr(impl, "_browser", None) if impl is not None else None
        connection = getattr(browser, "_connection", None) if browser is not None else None
        transport = getattr(connection, "_transport", None) if connection is not None else None
        proc = getattr(transport, "_proc", None) if transport is not None else None
        pid = getattr(proc, "pid", None)
        try:
            return int(pid) if pid is not None else None
        except Exception:
            return None

    def _close_extra_pages(self, context, keep_page) -> None:
        for candidate in _list_live_context_pages(context):
            if candidate is keep_page:
                continue
            try:
                candidate.close()
            except Exception:
                pass

    def _prepare_working_page(self, context, entry_url: str, *, phase: str):
        page = None
        page_factory = getattr(context, "new_page", None)
        if callable(page_factory):
            try:
                page = page_factory()
            except Exception:
                page = None
        if not _can_interact_with_page(page):
            live_pages = [item for item in _list_live_context_pages(context) if _can_interact_with_page(item)]
            page = live_pages[0] if live_pages else None
        if page is None:
            raise RuntimeError("违反单标签页约束：当前浏览器上下文中没有可复用标签页。")
        try:
            page.evaluate("() => { document.title = 'AutoNews-微信专用'; }")
        except Exception:
            pass
        try:
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        self._close_extra_pages(context, page)
        self._page = page
        self._resident_page = "home"
        self._last_action_phase = phase
        return page

    def ensure_context(self, channel: dict[str, object]):
        signature = self.signature_for(channel)
        if self._context is not None and self.is_alive() and signature == self._channel_signature:
            live_pages = [page for page in _list_live_context_pages(self._context) if _can_interact_with_page(page)]
            if live_pages:
                if not _can_interact_with_page(self._page):
                    self._page = live_pages[0]
                self._resident_page = f"{self._resident_page or 'home'}|context_reused"
                return self._context
        self._close_runtime_internal()
        playwright = self._ensure_playwright()
        normalized = ensure_channel_defaults(channel)
        context = playwright.chromium.launch_persistent_context(
            str(resolve_profile_path(normalized.get("browser_profile_path"), normalized.get("browser_name"))),
            headless=False,
            channel=browser_channel_name(str(normalized.get("browser_name"))),
        )
        self._context = context
        self._page = None
        self._channel_signature = signature
        self._browser_pid = self._extract_browser_pid()
        self._hwnd = _find_window_for_pid(int(self._browser_pid or 0))
        self._window_state = "unknown"
        self._resident_page = "boot"
        self._session_generation += 1
        self._last_action_phase = "context_created"
        return context

    def ensure_page(self, channel: dict[str, object], entry_url: str):
        context = self.ensure_context(channel)
        if _can_interact_with_page(self._page):
            self._last_action_phase = "page_reused"
            return self._page
        self._page = None
        live_pages = [page for page in _list_live_context_pages(context) if _can_interact_with_page(page)]
        phase = "page_recovered" if live_pages else "page_created"
        return self._prepare_working_page(context, entry_url, phase=phase)

    def ensure_window_handle(self) -> int | None:
        if self._hwnd and USER32 is not None and USER32.IsWindow(self._hwnd):
            return self._hwnd
        self._hwnd = _find_window_for_pid(int(self._browser_pid or 0))
        return self._hwnd

    def restore_window(self) -> None:
        handle = self.ensure_window_handle()
        if _set_window_state(handle, minimize=False):
            self._window_state = "restored"

    def minimize_window(self) -> None:
        handle = self.ensure_window_handle()
        if _set_window_state(handle, minimize=True):
            self._window_state = "minimized"

    def set_resident_page(self, value: str | None) -> None:
        self._resident_page = value

    def set_action_state(self, action: str | None = None, phase: str | None = None) -> None:
        if action is not None:
            self._last_action = action
        if phase is not None:
            self._last_action_phase = phase

    def capture_screenshot(self, target: Path) -> tuple[bool, str | None]:
        def _capture() -> tuple[bool, str | None]:
            page = self._page
            if page is None:
                return False, None
            try:
                page.screenshot(path=str(target), full_page=True)
                return True, str(page.url or "")
            except Exception:
                return False, None

        try:
            return self._run_in_worker(_capture)
        except Exception:
            return False, None

    def with_session(
        self,
        channel: dict[str, object],
        *,
        restore_window: bool,
        action_fn,
        timeout_seconds: int = DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS,
    ):
        acquired = self._lock.acquire(timeout=timeout_seconds)
        if not acquired:
            raise RuntimeError("浏览器忙，稍后重试")
        try:
            def _execute():
                normalized = ensure_channel_defaults(channel)
                page = self.ensure_page(normalized, str(normalized.get("publish_entry_url") or "https://mp.weixin.qq.com/"))
                if restore_window:
                    self.restore_window()
                try:
                    return action_fn(self._context, page)
                finally:
                    try:
                        self.minimize_window()
                    except Exception:
                        pass

            return self._run_in_worker(_execute)
        except Exception:
            try:
                self.reset("with_session_failed")
            except Exception:
                self._last_reset_reason = "with_session_failed"
                self._close_runtime_internal()
            raise
        finally:
            try:
                self._lock.release()
            except Exception:
                pass

    def manager_state(self) -> dict[str, object]:
        return {
            "manager_alive": self.is_alive(),
            "window_state": self._window_state,
            "resident_page": self._resident_page,
            "busy": self.is_busy(),
            "last_reset_reason": self._last_reset_reason,
            "session_generation": self._session_generation,
            "last_action": self._last_action,
            "last_action_phase": self._last_action_phase,
        }


WECHAT_BROWSER_MANAGER = WechatBrowserManager()
DOUYIN_BROWSER_MANAGER = WechatBrowserManager()


def _plain_text_from_markdown(markdown: str) -> str:
    return markdown_to_plain_text(markdown, limit=12000)


def _normalize_compact_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    compact = compact.replace("： ", "：").replace(" - ", "-")
    return compact


def _pick_first_sentence(value: str) -> str:
    compact = _normalize_compact_text(value)
    if not compact:
        return ""
    parts = re.split(r"[。！？!?；;]\s*", compact, maxsplit=1)
    return parts[0].strip(" ，,、:：;；")


def _pick_best_prefix_within_limit(value: str, limit: int, markers: tuple[str, ...]) -> str:
    compact = _normalize_compact_text(value)
    if not compact:
        return ""
    best = ""
    for marker in markers:
        start = 0
        while True:
            index = compact.find(marker, start)
            if index < 0 or index >= limit:
                break
            candidate = compact[:index].strip(" ，,、:：;；-")
            if len(candidate) > len(best):
                best = candidate
            start = index + len(marker)
    return best


def _trim_to_limit(value: str, limit: int) -> str:
    compact = _normalize_compact_text(value)
    if len(compact) <= limit:
        return compact
    trimmed = compact[:limit].rstrip(" ，,、:：;；-")
    return trimmed or compact[:limit]


def _build_douyin_title(raw_title: str, limit: int = 30) -> str:
    compact = _normalize_compact_text(raw_title)
    if len(compact) <= limit:
        return compact

    headline = _pick_first_sentence(compact)
    if headline and len(headline) <= limit:
        return headline

    colon_variants = ("：", ":")
    for marker in colon_variants:
        if marker in compact:
            prefix, suffix = compact.split(marker, 1)
            prefix = prefix.strip()
            suffix = suffix.strip()
            if prefix and len(prefix) <= limit:
                return prefix
            if suffix and len(suffix) <= limit:
                return suffix
            if prefix and suffix:
                merged = f"{prefix}{marker}{suffix}"
                if len(merged) <= limit:
                    return merged

    for marker in ("，", ",", "、", " - ", "-"):
        if marker in compact:
            segment = compact.split(marker, 1)[0].strip()
            if segment and len(segment) <= limit:
                return segment

    return _trim_to_limit(compact, limit)


def _build_douyin_summary(raw_summary: str, raw_title: str, limit: int = 30) -> str:
    from .briefing import build_douyin_summary

    return build_douyin_summary(raw_summary, raw_title, limit)


def _clamp_author(author: str) -> str:
    compact = re.sub(r"\s+", " ", author.strip())
    if not compact:
        return ""
    return compact[:8]


def _strip_markdown_title(markdown: str, title: str) -> str:
    return strip_markdown_title(markdown, title)


def _fill_locator_value(page, selector: str, value: str, *, is_rich_text: bool = False) -> None:
    locator = _pick_visible_locator(page, selector)
    locator.click()
    if is_rich_text:
        try:
            locator.fill(value)
            return
        except Exception:
            page.evaluate(
                """({ selector, value }) => {
                    const node = document.querySelector(selector);
                    if (!node) return;
                    node.focus();
                    node.textContent = value;
                    node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
                }""",
                {"selector": selector, "value": value},
            )
            return
    try:
        locator.fill(value)
        return
    except Exception:
        pass
    try:
        locator.press("Control+A")
        locator.type(value, delay=10)
        return
    except Exception:
        page.evaluate(
            """({ selector, value }) => {
                const node = document.querySelector(selector);
                if (!node) return;
                node.focus();
                if ('value' in node) {
                    node.value = value;
                } else {
                    node.textContent = value;
                }
                node.dispatchEvent(new Event('input', { bubbles: true }));
                node.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            {"selector": selector, "value": value},
        )


def _clipboard_paste_text(page, text: str) -> None:
    """Simulate clipboard paste via JS + Ctrl+V, the only reliable way to write into ProseMirror."""
    page.evaluate(
        """(text) => {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        }""",
        text,
    )
    page.keyboard.press("Control+v")


def _clipboard_paste_into_element(page, selector: str, text: str) -> None:
    """Focus element via selector, select all existing content, then paste new text."""
    loc = page.locator(selector).first
    loc.click(timeout=4000)
    page.wait_for_timeout(300)
    page.keyboard.press("Control+a")
    page.wait_for_timeout(200)
    _clipboard_paste_text(page, text)
    page.wait_for_timeout(500)


def _dump_wechat_editor_dom(page, artifact_dir: Path, step_logs: list[str], *, label: str) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    html_path = artifact_dir / f"{label}.html"
    report_path = artifact_dir / f"{label}.txt"
    try:
        html_path.write_text(str(page.content() or ""), encoding="utf-8")
        step_logs.append(f"已导出编辑页 HTML={html_path}")
    except Exception as exc:
        step_logs.append(f"导出编辑页 HTML 失败：{exc}")
        return

    selector_groups = {
        "title": [
            "div.ProseMirror[data-placeholder*='请在这里输入标题']",
            "div.ProseMirror[data-placeholder*='标题']",
            "textarea.js_article_title",
        ],
        "author": [
            "input.js_author",
            "input[placeholder*='作者']",
        ],
        "digest": [
            "textarea.js_desc",
            "textarea[placeholder*='摘要']",
        ],
        "editor": [
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']",
            "#edui1_iframeholder .mock-iframe-body .rich_media_content div.ProseMirror[contenteditable='true']",
            ".editor-v-root .mock-iframe-body .rich_media_content > div.ProseMirror[contenteditable='true']",
            "div.ProseMirror[contenteditable='true'][style*='min-height']",
            "div.ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])",
            "div.ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])[style*='min-height']",
            ".rich_media_content .ProseMirror:not([data-placeholder*='请在这里输入标题']):not([data-placeholder*='标题'])",
            "#edui1_iframeholder .mock-iframe-body .rich_media_content > div.ProseMirror",
            ".editor-v-root .mock-iframe-body .rich_media_content > div.ProseMirror",
            "div.ProseMirror:has(.editor_content_placeholder)",
            ".ProseMirror",
        ],
    }
    lines = [f"url={_page_url(page)}"]
    for group, selectors in selector_groups.items():
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
                lines.append(f"[{group}] selector={selector} count={count}")
                if count <= 0:
                    continue
                first = locator.first
                outer_html = str(first.evaluate("(el) => el.outerHTML || ''")).strip()
                inner_text = str(first.evaluate("(el) => el.innerText || el.textContent || ''")).strip()
                lines.append(f"[{group}] outerHTML={outer_html[:4000]}")
                lines.append(f"[{group}] innerText={inner_text[:1000]}")
            except Exception as exc:
                lines.append(f"[{group}] selector={selector} error={exc}")
    _write_debug_artifact(report_path, lines)
    step_logs.append(f"已导出编辑页节点报告={report_path}")


def _read_locator_value(page, selector: str, *, rich_text: bool = False) -> str:
    script = """({ selector, richText }) => {
        const node = document.querySelector(selector);
        if (!node) return "";
        if (richText) {
            const clone = node.cloneNode(true);
            clone.querySelectorAll('.editor_content_placeholder, .ProseMirror-widget, [data-placeholder]').forEach((child) => {
                if (child !== clone) child.remove();
            });
            return String(clone.innerText || clone.textContent || "").replace(/\\s+/g, " ").trim();
        }
        if ("value" in node) {
            return String(node.value || "").trim();
        }
        return String(node.textContent || "").trim();
    }"""
    try:
        value = page.evaluate(script, {"selector": selector, "richText": rich_text})
    except Exception:
        return ""
    return str(value or "").strip()


def _write_plain_field(page, selector: str, value: str, step_logs: list[str], *, field_label: str) -> int:
    locator = _pick_visible_locator(page, selector, timeout=4000)
    try:
        locator.fill(value)
    except Exception:
        try:
            locator.click(timeout=4000)
            page.wait_for_timeout(250)
            page.keyboard.press("Control+a")
            page.wait_for_timeout(150)
            locator.type(value, delay=8)
        except Exception:
            _clipboard_paste_into_element(page, selector, value)
    page.wait_for_timeout(350)
    resolved_value = _read_locator_value(page, selector, rich_text=False)
    resolved_length = len(resolved_value)
    step_logs.append(f"{field_label}回读长度={resolved_length} selector={selector}")
    if value.strip() and not resolved_value.strip():
        raise RuntimeError(f"{field_label}写入后回读为空。")
    if value.strip():
        expected_prefix = value.strip()[: min(12, len(value.strip()))]
        if expected_prefix and expected_prefix not in resolved_value:
            raise RuntimeError(f"{field_label}写入后回读未命中预期前缀。")
    return resolved_length


def _write_rich_text_field(page, selector: str, value: str, step_logs: list[str], *, minimum_length: int) -> int:
    editor = _pick_visible_locator(page, selector, timeout=4000)

    def _readback(strategy: str) -> int:
        page.wait_for_timeout(900)
        resolved_text = _read_locator_value(page, selector, rich_text=True)
        resolved_length = len(resolved_text)
        step_logs.append(f"正文回读长度={resolved_length} selector={selector} strategy={strategy}")
        return resolved_length

    strategies: list[tuple[str, object]] = []

    def _exec_command_insert() -> None:
        page.evaluate(
            """({ selector, value }) => {
                const node = document.querySelector(selector);
                if (!node) return;
                node.focus();
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(node);
                selection.removeAllRanges();
                selection.addRange(range);
                document.execCommand('delete', false);
                document.execCommand('insertText', false, value);
            }""",
            {"selector": selector, "value": value},
        )

    def _set_dom_paragraphs() -> None:
        page.evaluate(
            """({ selector, value }) => {
                const node = document.querySelector(selector);
                if (!node) return;
                node.focus();
                node.innerHTML = '';
                const blocks = String(value || '').split(/\\n+/).map((item) => item.trim()).filter(Boolean);
                const section = document.createElement('section');
                if (!blocks.length) {
                    const span = document.createElement('span');
                    span.setAttribute('leaf', '');
                    span.innerHTML = '<br class="ProseMirror-trailingBreak">';
                    section.appendChild(span);
                } else {
                    for (const block of blocks) {
                        const p = document.createElement('p');
                        p.textContent = block;
                        section.appendChild(p);
                    }
                }
                node.appendChild(section);
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(node);
                range.collapse(false);
                selection.removeAllRanges();
                selection.addRange(range);
                node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
                node.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            {"selector": selector, "value": value},
        )

    def _paste_clipboard() -> None:
        _clipboard_paste_into_element(page, selector, value)

    strategies.extend(
        [
            ("dom_paragraphs", _set_dom_paragraphs),
            ("exec_command_insert", _exec_command_insert),
            ("clipboard_paste", _paste_clipboard),
        ]
    )

    last_length = 0
    for strategy_name, strategy_fn in strategies:
        try:
            editor.click(timeout=4000)
            page.wait_for_timeout(250)
            page.keyboard.press("Control+a")
            page.wait_for_timeout(150)
            try:
                page.keyboard.press("Delete")
            except Exception:
                pass
            page.wait_for_timeout(150)
            strategy_fn()
            last_length = _readback(strategy_name)
            if last_length >= minimum_length:
                return last_length
        except Exception as exc:
            step_logs.append(f"正文写入策略失败 strategy={strategy_name} error={exc}")

    raise RuntimeError("正文写入后回读长度不足。")


def _write_rich_html_field(
    page,
    selector: str,
    html: str,
    plain_text: str,
    step_logs: list[str],
    *,
    minimum_length: int,
) -> int:
    editor = _pick_visible_locator(page, selector, timeout=4000)

    def _readback(strategy: str) -> int:
        page.wait_for_timeout(900)
        resolved_text = _read_locator_value(page, selector, rich_text=True)
        resolved_length = len(resolved_text)
        step_logs.append(f"正文回读长度={resolved_length} selector={selector} strategy={strategy}")
        return resolved_length

    def _set_html_blocks() -> None:
        page.evaluate(
            """({ selector, html }) => {
                const node = document.querySelector(selector);
                if (!node) return;
                node.focus();
                node.innerHTML = html || '<section><span leaf=""><br class="ProseMirror-trailingBreak"></span></section>';
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(node);
                range.collapse(false);
                selection.removeAllRanges();
                selection.addRange(range);
                node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: node.innerText || '' }));
                node.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            {"selector": selector, "html": html},
        )

    try:
        editor.click(timeout=4000)
        page.wait_for_timeout(250)
        _set_html_blocks()
        last_length = _readback("html_blocks")
        if last_length >= minimum_length:
            return last_length
    except Exception as exc:
        step_logs.append(f"正文 HTML 写入失败 strategy=html_blocks error={exc}")

    return _write_rich_text_field(page, selector, plain_text, step_logs, minimum_length=minimum_length)


def _fill_wechat_editor(
    page,
    draft: dict[str, object],
    channel: dict[str, object],
    selector_profile: dict[str, list[str] | str],
    step_logs: list[str],
    *,
    artifact_dir: Path | None = None,
) -> None:
    # Debug: screenshot editor page and dump selector results
    try:
        debug_path = ARTIFACT_ROOT / "debug-fill-editor.png"
        page.screenshot(path=str(debug_path), full_page=True)
        for key in ["title_input", "author_input", "digest_input", "editor"]:
            selectors = selector_profile.get(key, [])
            for s in selectors:
                try:
                    c = page.locator(s).count()
                    step_logs.append(f"DEBUG {key} selector={s} count={c}")
                except Exception as e:
                    step_logs.append(f"DEBUG {key} selector={s} error={e}")
        if artifact_dir is not None:
            _dump_wechat_editor_dom(page, artifact_dir, step_logs, label="wechat-editor-dom")
    except Exception:
        pass

    title_selector = _pick_selector(page, selector_profile.get("title_input", []))
    author_selector = _pick_selector(page, selector_profile.get("author_input", []))
    digest_selector = _pick_selector(page, selector_profile.get("digest_input", []))
    editor_selector = _pick_selector(page, selector_profile.get("editor", []), timeout=4000)
    if not title_selector or not editor_selector:
        raise RuntimeError("未定位到标题框或正文编辑区。")

    title = str(draft.get("title", "")).strip()[:64]
    author = _clamp_author(str(channel.get("author") or ""))
    digest = str(draft.get("summary") or "").strip()[:120]
    raw_markdown = str(draft.get("markdown") or "")
    body_markdown = _strip_markdown_title(raw_markdown, title)
    normalized_body_markdown = body_markdown or raw_markdown
    body_text = _plain_text_from_markdown(normalized_body_markdown)
    body_html = markdown_to_wechat_html(normalized_body_markdown, include_wrapper=False)

    if not _validate_wechat_page_identity(page, selector_profile, expected="editor"):
        raise RuntimeError(f"已命中编辑页 URL，但编辑器 DOM 未就绪：{_page_url(page)}")

    title_length = _write_plain_field(page, title_selector, title, step_logs, field_label="标题")
    step_logs.append(f"已填充标题 selector={title_selector}")
    step_logs.append(f"标题最终长度={title_length}")

    if author_selector and author:
        _write_plain_field(page, author_selector, author, step_logs, field_label="作者")
        step_logs.append(f"已填充作者 selector={author_selector}")

    if digest_selector and digest:
        digest_length = _write_plain_field(page, digest_selector, digest, step_logs, field_label="摘要")
        step_logs.append(f"已填充摘要 selector={digest_selector}")
        step_logs.append(f"摘要最终长度={digest_length}")

    minimum_body_length = max(20, min(len(body_text.strip()), 120))
    body_length = _write_rich_html_field(
        page,
        editor_selector,
        body_html,
        body_text,
        step_logs,
        minimum_length=minimum_body_length,
    )
    step_logs.append(f"已填充正文 selector={editor_selector} (rich html)")
    step_logs.append(f"正文最终长度={body_length}")


def _wait_for_wechat_editor_in_current_page(page, selector_profile: dict[str, list[str] | str], timeout_ms: int = 12000):
    deadline = datetime.now(UTC).timestamp() + (timeout_ms / 1000)
    while datetime.now(UTC).timestamp() < deadline:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=1500)
        except Exception:
            pass
        if _validate_wechat_page_identity(page, selector_profile, expected="editor"):
            return page
        try:
            page.wait_for_timeout(500)
        except Exception:
            break
    raise RuntimeError("当前页未进入编辑器。")


def _locate_editor_page(context, fallback_page, timeout_ms: int = 12000):
    """Find the editor page across ALL tabs (WeChat opens editor in a new tab)."""
    deadline = datetime.now(UTC).timestamp() + (timeout_ms / 1000)
    candidate = fallback_page
    while datetime.now(UTC).timestamp() < deadline:
        pages = _list_live_context_pages(context)
        for page in pages:
            if _is_page_closed(page):
                continue
            if "appmsg" in _page_url(page) or "media/appmsg_edit" in _page_url(page):
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=1500)
                except Exception:
                    pass
                return page
            candidate = page
        try:
            fallback_page.wait_for_timeout(500)
        except Exception:
            break
    return candidate


def _locate_editor_page_with_retry(context, fallback_page, selector_profile: dict[str, list[str] | str], step_logs: list[str]):
    def _locate_once():
        candidate = _locate_editor_page(context, fallback_page)
        if not _validate_wechat_page_identity(candidate, selector_profile, expected="editor"):
            live_pages = _list_live_context_pages(context)
            page_urls = ", ".join(_page_url(page) or "<empty>" for page in live_pages) or "<none>"
            if candidate is fallback_page:
                raise RuntimeError(f"未找到新开的编辑页。当前页集合：{page_urls}")
            raise RuntimeError(f"已命中编辑页 URL，但编辑器 DOM 未就绪：{_page_url(candidate)}")
        return candidate

    return _retry_once("locate_editor_page", step_logs, _locate_once)


def extract_wechat_appmsg_id(url: str | None) -> str | None:
    if not url:
        return None
    try:
        values = parse_qs(urlparse(url).query).get("appmsgid", [])
    except Exception:
        return None
    for value in values:
        compact = str(value).strip()
        if compact:
            return compact
    return None


def resolve_editor_url(draft: dict[str, object], browser_state: dict[str, object], entry_url: str) -> str:
    candidates = [
        draft.get("wechat_editor_url"),
        browser_state.get("last_opened_url"),
        browser_state.get("current_page"),
        draft.get("preview_url"),
        entry_url,
    ]
    for candidate in candidates:
        compact = str(candidate or "").strip()
        if "appmsg" in compact:
            return compact
    return str(entry_url)


def detect_editor_blockers(page) -> list[str]:
    try:
        body_text = page.locator("body").inner_text(timeout=2500)
    except Exception:
        return []
    text = str(body_text or "")
    blockers: list[str] = []
    if "必须插入一张图片" in text:
        blockers.append("微信校验未通过：正文必须至少插入一张图片。")
    if "请在这里输入标题" in text:
        blockers.append("微信校验未通过：标题仍为空。")
    return blockers


def _scrape_wechat_draft_items(page) -> list[dict[str, str | None]]:
    try:
        rows = page.evaluate(
            """() => {
                const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const results = [];
                const seenStable = new Set();
                const normalizeTitleKey = (value) =>
                    normalize(value)
                        .replace(/[“”]/g, '"')
                        .replace(/[‘’]/g, "'")
                        .replace(/[：:]/g, ':')
                        .toLowerCase();
                const pushItem = (title, url, updatedAt, occurrence) => {
                    const cleanTitle = normalize(title);
                    const cleanUrl = normalize(url);
                    if (cleanTitle.length < 8) return;
                    const normalizedUrl = cleanUrl.startsWith('javascript:') ? '' : cleanUrl;
                    let appmsgId = null;
                    try {
                        if (normalizedUrl) {
                            const parsed = new URL(normalizedUrl, window.location.origin);
                            appmsgId = parsed.searchParams.get("appmsgid");
                        }
                    } catch (_) {}
                    const stableKey = appmsgId
                        ? `appmsg:${appmsgId}`
                        : normalizedUrl
                            ? `url:${normalizedUrl}`
                            : '';
                    const titleKey = normalizeTitleKey(cleanTitle);
                    const dedupeKey = stableKey || `title:${titleKey}|updated:${normalize(updatedAt)}`;
                    if (seenStable.has(dedupeKey)) return;
                    seenStable.add(dedupeKey);
                    results.push({
                        title: cleanTitle,
                        url: normalizedUrl,
                        appmsg_id: appmsgId,
                        updated_at: normalize(updatedAt),
                        remote_key: stableKey || `card:${titleKey}|updated:${normalize(updatedAt)}|${occurrence}`,
                    });
                };

                const containers = Array.from(
                    document.querySelectorAll(
                        '.publish_card_container, .weui-desktop-card.weui-desktop-publish, .weui-desktop-media__list-col .weui-desktop-card'
                    )
                );

                containers.forEach((container, index) => {
                    const titleNode =
                        container.querySelector('.weui-desktop-publish__cover__title span') ||
                        container.querySelector('.weui-desktop-publish__cover__title') ||
                        container.querySelector('.weui-desktop-card__title');
                    const title = normalize(titleNode ? titleNode.textContent : '');
                    const linkNode =
                        container.querySelector('.weui-desktop-publish__cover__title') ||
                        container.querySelector('a[href]');
                    const href = normalize(linkNode ? linkNode.getAttribute('href') : '');
                    const containerText = normalize(container.innerText || '');
                    const updatedAtMatch = containerText.match(/更新于\\s*([0-9]{1,2}:[0-9]{2}|[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2})/);
                    const updatedAt = updatedAtMatch ? `更新于 ${updatedAtMatch[1]}` : '';
                    pushItem(title, href, updatedAt, index);
                });

                return results
                    .filter((item) => item.title || item.url)
                    .slice(0, 80);
            }"""
        )
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    items: list[dict[str, str | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "appmsg_id": str(row.get("appmsg_id") or "").strip() or None,
                "updated_at": str(row.get("updated_at") or "").strip() or None,
                "remote_key": str(row.get("remote_key") or "").strip() or None,
            }
        )
    return items


def _merge_browser_state_delta(browser_state: dict[str, object], delta: dict[str, object] | None) -> None:
    if not delta:
        return
    for key, value in delta.items():
        browser_state[key] = value


def _run_session_recovery(context, page, entry_url: str, selector_profile: dict[str, list[str] | str], browser_state: dict[str, object], step_logs: list[str]) -> tuple[dict[str, object], list[str], list[str], object]:
    WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "session_recovery")
    _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="return_home_session_recovery")
    return (
        {
            "resident_page": "home",
            "current_page": page.url,
            "last_opened_url": page.url,
            "is_session_level_error": False,
        },
        [],
        step_logs,
        page,
    )


def _run_upload(context, page, draft: dict[str, object], channel: dict[str, object], entry_url: str, selector_profile: dict[str, list[str] | str], browser_state: dict[str, object], step_logs: list[str]) -> tuple[dict[str, object], list[str], list[str], object]:
    _enforce_single_tab(context, page, step_logs, phase="before_upload", allow_recover=True)
    _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="return_home_before_upload")
    if not _validate_wechat_page_identity(page, selector_profile, expected="home"):
        raise RuntimeError("首页未识别。")
    step_logs.append("已从公众号后台首页开始上传。")
    WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "open_editor")
    new_article_selector = _pick_required_selector(
        page,
        selector_profile.get("new_article", []),
        step_logs,
        step_name="pick_new_article_selector",
        timeout=5000,
    )
    step_logs.append(f"已命中文章入口 selector={new_article_selector}")
    page.locator(new_article_selector).first.click()
    page.wait_for_timeout(2500)
    step_logs.append(f"点击文章后 live_page_count={_count_context_pages(context)}")
    target = _locate_editor_page_with_retry(context, page, selector_profile, step_logs)
    if target is not page:
        step_logs.append(f"检测到新编辑页接管 URL={_page_url(target)}")
        _converge_context_to_target(context, target, step_logs, phase="after_editor_targeted")
        try:
            WECHAT_BROWSER_MANAGER._page = target
        except Exception:
            pass
    _enforce_single_tab(context, target, step_logs, phase="after_editor_located", allow_recover=False)
    target.wait_for_timeout(2000)
    step_logs.append(f"编辑页 URL={target.url}")
    WECHAT_BROWSER_MANAGER.set_resident_page("editor")
    WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "fill_editor")
    _fill_wechat_editor_with_retry(target, draft, channel, selector_profile, step_logs)
    _ensure_wechat_author_before_publish_settings(target, channel, selector_profile, step_logs)
    WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "apply_publish_settings")
    _apply_wechat_publish_settings(target, selector_profile, step_logs)

    save_selector = _pick_required_selector(
        target,
        selector_profile.get("save_draft_button", []),
        step_logs,
        step_name="pick_save_draft_selector",
        timeout=6000,
    )

    def _save_draft_once() -> None:
        WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "save_draft")
        _pick_visible_locator(target, save_selector, timeout=4000).click()
        target.wait_for_timeout(3500)

    _retry_once("save_draft", step_logs, _save_draft_once)
    step_logs.append(f"已点击保存草稿 selector={save_selector}")
    _enforce_single_tab(context, target, step_logs, phase="after_save_draft", allow_recover=False)
    landing_page = target
    _safe_return_home(landing_page, entry_url, selector_profile, step_logs, step_name="return_home_after_upload")
    return (
        {
            "resident_page": "home",
            "current_page": landing_page.url,
            "last_opened_url": landing_page.url,
            "last_synced_editor_url": str(target.url or ""),
            "is_session_level_error": False,
        },
        [],
        step_logs,
        landing_page,
    )


def _run_verify(context, landing_page, draft: dict[str, object], entry_url: str, selector_profile: dict[str, list[str] | str], browser_state: dict[str, object], step_logs: list[str], screenshot_path: Path) -> tuple[dict[str, object], list[str], list[str], object]:
    artifacts: list[str] = []

    def _verify_once() -> tuple[bool, list[dict[str, str | None]], dict[str, str | None] | None]:
        _enforce_single_tab(context, landing_page, step_logs, phase="before_verify", allow_recover=False)
        WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "draft_box_verify")
        _safe_return_home(landing_page, entry_url, selector_profile, step_logs, step_name="return_home_before_verify")
        if not _open_wechat_draft_box(landing_page, selector_profile, step_logs):
            raise RuntimeError("未能进入正式草稿箱页面（/cgi-bin/appmsg?...action=list_card...）。")
        if not _validate_wechat_page_identity(landing_page, selector_profile, expected="draft_box"):
            raise RuntimeError(f"草稿箱页面身份验证失败：{landing_page.url}")
        landing_page.wait_for_timeout(1800)
        remote_items = _scrape_wechat_draft_items_strict(landing_page)
        remote_appmsg_id = extract_wechat_appmsg_id(str(browser_state.get("last_synced_editor_url") or "")) or extract_wechat_appmsg_id(str(landing_page.url or ""))
        target_title = str(draft.get("title") or "").strip()
        matched = False
        matched_item: dict[str, str | None] | None = None
        if remote_appmsg_id or target_title:
            for item in remote_items:
                item_appmsg = str(item.get("appmsg_id") or "").strip()
                item_title = str(item.get("title") or "").strip()
                if remote_appmsg_id and item_appmsg and item_appmsg == remote_appmsg_id:
                    matched = True
                    matched_item = item
                    break
                if target_title and item_title and (item_title == target_title or target_title.startswith(item_title) or item_title.startswith(target_title)):
                    matched = True
                    matched_item = item
                    break
        return matched, remote_items, matched_item

    try:
        matched, remote_items, matched_item = _retry_once("draft_box_verify", step_logs, _verify_once)
        landing_page.screenshot(path=str(screenshot_path), full_page=True)
        artifacts.append(str(screenshot_path))
        step_logs.append(f"保存草稿后已读取正式草稿箱，共 {len(remote_items)} 条。")
        delta: dict[str, object] = {
            "resident_page": "draft_box",
            "current_page": landing_page.url,
            "last_opened_url": landing_page.url,
            "is_session_level_error": False,
        }
        if matched:
            delta["verification_status"] = "verified"
            delta["verification_message"] = "已上传并确认目标稿件存在。"
            delta["last_verified_at"] = now_iso()
            if matched_item:
                delta["last_verified_remote_url"] = str(matched_item.get("url") or "") or None
                delta["last_verified_remote_appmsg_id"] = str(matched_item.get("appmsg_id") or "") or None
            step_logs.append("已在正式草稿箱确认到目标稿件。")
        else:
            delta["verification_status"] = "target_missing"
            delta["verification_message"] = "已上传，但正式草稿箱暂未确认到目标稿件。"
            step_logs.append("正式草稿箱中暂未确认到目标稿件。")

        try:
            _safe_return_home(landing_page, entry_url, selector_profile, step_logs, step_name="return_home_final")
            delta["resident_page"] = "home"
            delta["current_page"] = landing_page.url
            delta["last_opened_url"] = landing_page.url
        except Exception:
            delta["is_session_level_error"] = True
            delta["last_error"] = "最终回首页失败。"
            raise
        return delta, artifacts, step_logs, landing_page
    except Exception as exc:
        error_text = str(exc)
        if "抓取结果格式异常" in error_text or "evaluate" in error_text.lower():
            verification_status = "scrape_failed"
            verification_message = f"已上传，但草稿箱抓取失败：{exc}"
            is_session_level_error = False
        elif _browser_session_error_kind(exc, recovery_ok=False):
            verification_status = "check_failed"
            verification_message = f"草稿箱检查发生会话级故障：{exc}"
            is_session_level_error = True
        else:
            verification_status = "check_failed"
            verification_message = f"已上传，但草稿箱检查失败：{exc}"
            is_session_level_error = False
        step_logs.append(verification_message)
        delta = {
            "verification_status": verification_status,
            "verification_message": verification_message,
            "is_session_level_error": is_session_level_error,
        }
        try:
            _safe_return_home(landing_page, entry_url, selector_profile, step_logs, step_name="return_home_after_verify_failure")
            delta["resident_page"] = "home"
            delta["current_page"] = landing_page.url
            delta["last_opened_url"] = landing_page.url
        except Exception:
            delta["is_session_level_error"] = True
            delta["last_error"] = "校验失败后无法恢复首页。"
        return delta, artifacts, step_logs, landing_page


def _match_remote_draft_item(
    items: list[dict[str, str | None]],
    *,
    remote_id: str = "",
    remote_url: str = "",
    remote_title: str = "",
) -> dict[str, str | None] | None:
    compact_id = str(remote_id or "").strip()
    compact_url = str(remote_url or "").strip()
    compact_title = re.sub(r"\s+", " ", str(remote_title or "").replace("\xa0", " ")).strip().lower()

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

    if compact_id:
        for item in items:
            if str(item.get("appmsg_id") or "").strip() == compact_id:
                return item
    if compact_url:
        for item in items:
            if str(item.get("url") or "").strip() == compact_url:
                return item
    if compact_title:
        matches = [
            item for item in items
            if title_matches(
                compact_title,
                re.sub(r"\s+", " ", str(item.get("title") or "").replace("\xa0", " ")).strip().lower(),
            )
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _delete_wechat_draft_in_page(page, target: dict[str, object], step_logs: list[str]) -> None:
    compact_key = str(target.get("remote_key") or "").strip()
    compact_id = str(target.get("appmsg_id") or "").strip()
    compact_url = str(target.get("url") or "").strip()
    compact_title = re.sub(r"\s+", " ", str(target.get("title") or "").replace("\xa0", " ")).strip()

    def title_matches(left: str, right: str) -> bool:
        if not left or not right:
            return False
        left_compact = left.lower()
        right_compact = right.lower()
        if left_compact == right_compact:
            return True
        shorter, longer = (left_compact, right_compact) if len(left_compact) <= len(right_compact) else (right_compact, left_compact)
        if len(shorter) >= 18 and longer.startswith(shorter):
            return True
        if len(shorter) >= 18 and shorter in longer:
            return True
        return False

    rows = page.locator(".publish_card_container, .weui-desktop-card.weui-desktop-publish, .weui-desktop-media__list-col .weui-desktop-card")
    count = rows.count()
    matched_index: int | None = None
    if compact_key.startswith("card:"):
        try:
            raw_index = int(compact_key.split(":", 1)[1])
            if 0 <= raw_index < count:
                matched_index = raw_index
        except Exception:
            matched_index = None
    for index in range(count):
        if matched_index is not None:
            break
        row = rows.nth(index)
        try:
            row.hover(timeout=2500)
        except Exception:
            pass
        title = ""
        href = ""
        try:
            title = page.evaluate(
                """(node) => {
                    const titleNode =
                        node.querySelector('.weui-desktop-publish__cover__title span') ||
                        node.querySelector('.weui-desktop-publish__cover__title') ||
                        node.querySelector('.weui-desktop-card__title');
                    return String(titleNode ? titleNode.textContent : '').replace(/\\s+/g, ' ').trim();
                }""",
                row.element_handle(),
            )
        except Exception:
            title = ""
        try:
            href = page.evaluate(
                """(node) => {
                    const linkNode =
                        node.querySelector('.weui-desktop-publish__cover__title') ||
                        node.querySelector('a[href]');
                    return String(linkNode ? linkNode.getAttribute('href') : '').replace(/\\s+/g, ' ').trim();
                }""",
                row.element_handle(),
            )
        except Exception:
            href = ""
        row_title = re.sub(r"\s+", " ", str(title or "").replace("\xa0", " ")).strip()
        row_title_lower = row_title.lower()
        row_id = extract_wechat_appmsg_id(href)
        if compact_id and row_id == compact_id:
            matched_index = index
            break
        if compact_url and href == compact_url:
            matched_index = index
            break
        if compact_title and title_matches(row_title_lower, compact_title):
            matched_index = index
            break

    if matched_index is None:
        raise RuntimeError("无法稳定定位远端草稿。")

    row = rows.nth(matched_index)
    row.hover(timeout=2500)
    delete_target = row.locator(".weui-desktop-popover__wrp .weui-desktop-popover__target").first
    delete_button_candidates = [
        ".weui-desktop-publish__opr a.weui-desktop-icon20.weui-desktop-icon-btn",
        ".weui-desktop-link-group a.weui-desktop-icon20.weui-desktop-icon-btn",
        "a.weui-desktop-icon20.weui-desktop-icon-btn",
    ]
    delete_button = None
    for candidate in delete_button_candidates:
        locator = row.locator(candidate).first
        try:
            locator.wait_for(timeout=1500)
            delete_button = locator
            break
        except Exception:
            continue
    if not delete_button:
        raise RuntimeError("无法定位删除按钮。")
    if delete_target.count() > 0:
        try:
            delete_target.hover(timeout=2000)
        except Exception:
            pass
    try:
        delete_button.hover(timeout=2000)
    except Exception:
        pass
    delete_button.click(timeout=3000)
    step_logs.append(f"已触发删除悬浮按钮 title={compact_title or compact_id or compact_url}")

    popover = row.locator(".weui-desktop-popover__wrp .weui-desktop-popover").first
    try:
        popover.wait_for(state="visible", timeout=3000)
    except Exception:
        if delete_target.count() > 0:
            delete_target.click(timeout=2000)
        else:
            delete_button.click(timeout=2000)
        popover.wait_for(state="visible", timeout=3000)
    confirm_dialog = popover.locator(".comfirm_delete_wording").first
    confirm_dialog.wait_for(timeout=3000)
    confirm_button = popover.locator("button.weui-desktop-btn_primary").filter(has_text="删除").first
    confirm_button.wait_for(timeout=3000)
    confirm_button.click(timeout=3000)
    step_logs.append("已点击删除确认按钮。")
    try:
        row.wait_for(state="detached", timeout=8000)
    except Exception:
        page.wait_for_timeout(2500)
    step_logs.append("已等待远端草稿卡片消失或列表刷新。")


def delete_wechat_remote_draft(
    target: dict[str, object],
    channel: dict[str, object],
    browser_state: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        "action=delete_wechat_draft",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []
    browser_state = dict(browser_state)
    browser_state.pop("verification_status", None)
    browser_state.pop("verification_message", None)
    browser_state.pop("last_synced_editor_url", None)
    browser_state.pop("last_verified_remote_url", None)
    browser_state.pop("last_verified_remote_appmsg_id", None)
    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器登录态不可用，无法删除微信草稿。"
        return browser_state, artifacts, step_logs + ["未执行远端删除：登录态不可用。"]

    artifact_dir = ARTIFACT_ROOT / f"remote-delete-{uuid4().hex[:8]}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"delete-wechat-draft-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        def _run(_context, page):
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1800)
            if not _validate_wechat_page_identity(page, selector_profile, expected="home"):
                page.wait_for_timeout(3000)
                if not _validate_wechat_page_identity(page, selector_profile, expected="home"):
                    step_logs.append("首页验证未通过，尝试继续导航。")
            if not _open_wechat_draft_box(page, selector_profile, step_logs):
                direct_url = "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=list_card"
                step_logs.append(f"侧栏导航失败，尝试直接跳转草稿箱 {direct_url}")
                page.goto(direct_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)
                if "action=list_card" not in str(page.url or ""):
                    raise RuntimeError(f"直接跳转后仍未进入草稿箱：{page.url}")
                step_logs.append(f"已直接跳转到草稿箱 url={page.url}")
            _enforce_single_tab(_context, page, step_logs, phase="delete_remote_draft", allow_recover=False)
            active_page = page
            active_page.wait_for_timeout(2000)
            if "action=list_card" not in str(active_page.url or ""):
                raise RuntimeError(f"当前页面不是正式草稿箱：{active_page.url}")
            _delete_wechat_draft_in_page(active_page, target, step_logs)
            active_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = active_page.url
            browser_state["current_page"] = active_page.url
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["resident_page"] = "draft_box"
            WECHAT_BROWSER_MANAGER.set_resident_page("draft_box")
            browser_state["last_error"] = None

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"远端草稿删除失败：{exc}"
        step_logs.append(f"远端草稿删除失败：{exc}")
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        return browser_state, artifacts, step_logs


def _open_wechat_draft_box(page, selector_profile: dict[str, list[str] | str], step_logs: list[str]) -> bool:
    content_manage_selector = _pick_selector(page, selector_profile.get("content_manage", []), timeout=2500)
    if content_manage_selector:
        try:
            page.locator(content_manage_selector).first.click()
            page.wait_for_timeout(1200)
            step_logs.append(f"已展开内容管理 selector={content_manage_selector}")
        except Exception:
            step_logs.append(f"尝试展开内容管理失败 selector={content_manage_selector}")

    selector_candidates = selector_profile.get("draft_box", [])
    selector_list = selector_candidates if isinstance(selector_candidates, list) else [selector_candidates]
    if not selector_list:
        return False
    failed_selectors: list[str] = []
    for selector in [str(item) for item in selector_list if str(item).strip()]:
        try:
            locator = page.locator(selector).first
            try:
                locator.wait_for(timeout=4000)
            except Exception:
                href = ""
                try:
                    href = str(locator.get_attribute("href", timeout=1200) or "").strip()
                except Exception:
                    href = ""
                if href and "action=list_card" in href:
                    target_url = href if href.startswith("http") else f"https://mp.weixin.qq.com{href}"
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1200)
                else:
                    raise
            else:
                try:
                    locator.click(timeout=2000)
                except Exception:
                    href = ""
                    try:
                        href = str(locator.get_attribute("href", timeout=1200) or "").strip()
                    except Exception:
                        href = ""
                    if href and "action=list_card" in href:
                        target_url = href if href.startswith("http") else f"https://mp.weixin.qq.com{href}"
                        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(1200)
                    else:
                        locator.click(timeout=2000, force=True)
            try:
                page.wait_for_url("**action=list_card**", timeout=8000)
            except Exception:
                page.wait_for_timeout(2500)
            current_url = str(page.url or "")
            if "action=list_card" not in current_url:
                failed_selectors.append(selector)
                step_logs.append(f"草稿箱入口未跳转 selector={selector} url={current_url}")
                continue
            step_logs.append(f"已点击草稿箱入口 selector={selector}")
            step_logs.append(f"已进入草稿箱页面 url={current_url}")
            return True
        except Exception as exc:
            failed_selectors.append(selector)
            step_logs.append(f"草稿箱入口点击失败 selector={selector} error={exc}")
            continue
    if failed_selectors:
        step_logs.append(f"草稿箱入口全部尝试失败：{', '.join(failed_selectors)}")
    return False


def _return_to_wechat_home(page, entry_url: str, step_logs: list[str]) -> None:
    page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    step_logs.append("已返回公众号后台首页。")


def _validate_wechat_page_identity(page, selector_profile: dict[str, list[str] | str], *, expected: str) -> bool:
    current_url = str(getattr(page, "url", "") or "")
    if "mp.weixin.qq.com" not in current_url:
        return False
    if expected == "home":
        selectors = [
            *[str(item) for item in selector_profile.get("logged_in", []) if isinstance(item, str)],
            *[str(item) for item in selector_profile.get("content_manage", []) if isinstance(item, str)],
        ]
        for selector in selectors:
            try:
                if page.locator(selector).first.count() > 0:
                    return True
            except Exception:
                continue
        return False
    if expected == "draft_box":
        if "action=list_card" not in current_url:
            return False
        for selector in [
            ".publish_card_container",
            ".weui-desktop-card.weui-desktop-publish",
            ".weui-desktop-media__list-col .weui-desktop-card",
            ".weui-desktop-panel__bd",
        ]:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False
    if expected == "editor":
        if "appmsg" not in current_url and "media/appmsg_edit" not in current_url:
            return False
        selectors = [
            *[str(item) for item in selector_profile.get("title_input", []) if isinstance(item, str)],
            *[str(item) for item in selector_profile.get("editor", []) if isinstance(item, str)],
        ]
        for selector in selectors:
            try:
                if page.locator(selector).first.count() > 0:
                    return True
            except Exception:
                continue
        return False
    return False


def _browser_session_error_kind(exc: Exception | None, *, recovery_ok: bool) -> bool:
    if recovery_ok:
        return False
    if exc is None:
        return True
    message = str(exc or "").lower()
    session_markers = [
        "浏览器忙",
        "未登录",
        "登录态",
        "page closed",
        "target page",
        "target closed",
        "browser has been closed",
        "connection closed",
        "cannot find context",
        "context closed",
        "playwright connection",
        "无法恢复到首页",
        "浏览器启动失败",
    ]
    return any(marker in message for marker in session_markers)


def _retry_once(step_name: str, step_logs: list[str], fn):
    try:
        return fn()
    except Exception as exc:
        step_logs.append(f"{step_name} 首次失败：{exc}；5 秒后重试一次。")
        time.sleep(5)
        return fn()


def _safe_return_home(page, entry_url: str, selector_profile: dict[str, list[str] | str], step_logs: list[str], *, step_name: str) -> None:
    def _go_home_once() -> None:
        _return_to_wechat_home(page, entry_url, step_logs)
        if not _validate_wechat_page_identity(page, selector_profile, expected="home"):
            raise RuntimeError("未能恢复到有效首页。")

    _retry_once(step_name, step_logs, _go_home_once)


def _pick_required_selector(page, selectors: list[str] | str, step_logs: list[str], *, step_name: str, timeout: int) -> str:
    def _pick_once() -> str:
        selected = _pick_selector(page, selectors, timeout=timeout)
        if not selected:
            raise RuntimeError(f"{step_name} 未找到目标 selector。")
        return selected

    return _retry_once(step_name, step_logs, _pick_once)


def _fill_wechat_editor_with_retry(page, draft: dict[str, object], channel: dict[str, object], selector_profile: dict[str, list[str] | str], step_logs: list[str]) -> None:
    _retry_once(
        "fill_wechat_editor",
        step_logs,
        lambda: _fill_wechat_editor(page, draft, channel, selector_profile, step_logs),
    )


def _ensure_wechat_author_before_publish_settings(
    page,
    channel: dict[str, object],
    selector_profile: dict[str, list[str] | str],
    step_logs: list[str],
) -> str:
    raw_author = str(channel.get("author") or "").strip()
    author = _clamp_author(raw_author)
    if not author:
        raise RuntimeError("原创声明前需要先填写作者，且作者长度不能超过 8 个字。")
    author_selector = _pick_required_selector(
        page,
        selector_profile.get("author_input", []),
        step_logs,
        step_name="pick_author_before_publish_settings",
        timeout=5000,
    )
    current_author = _read_locator_value(page, author_selector, rich_text=False)
    if current_author != author:
        author_length = _write_plain_field(page, author_selector, author, step_logs, field_label="作者")
        step_logs.append(f"声明前已补齐作者 selector={author_selector}")
        step_logs.append(f"声明前作者最终长度={author_length}")
        if raw_author and raw_author != author:
            step_logs.append(f"声明前作者已截断为 {author}")
    else:
        step_logs.append(f"声明前作者已就绪 selector={author_selector}")
    page.wait_for_timeout(600)
    return author


def _click_required_selector_once(
    page,
    selectors: list[str] | str,
    step_logs: list[str],
    *,
    step_name: str,
    timeout: int = 5000,
    settle_ms: int = 1200,
) -> str:
    selector = _pick_required_selector(
        page,
        selectors,
        step_logs,
        step_name=f"{step_name}_selector",
        timeout=timeout,
    )
    _pick_visible_locator(page, selector, timeout=timeout).click()
    page.wait_for_timeout(settle_ms)
    step_logs.append(f"{step_name} 已点击 selector={selector}")
    return selector


def _apply_wechat_publish_settings(
    page,
    selector_profile: dict[str, list[str] | str],
    step_logs: list[str],
) -> None:
    def _apply_once() -> None:
        _click_required_selector_once(
            page,
            selector_profile.get("original_setting", []),
            step_logs,
            step_name="open_original_setting",
            timeout=6000,
            settle_ms=1200,
        )
        _click_required_selector_once(
            page,
            selector_profile.get("primary_confirm_button", []),
            step_logs,
            step_name="confirm_original_setting",
            timeout=6000,
            settle_ms=1800,
        )
        _click_required_selector_once(
            page,
            selector_profile.get("reward_setting", []),
            step_logs,
            step_name="open_reward_setting",
            timeout=6000,
            settle_ms=1200,
        )
        _click_required_selector_once(
            page,
            selector_profile.get("primary_confirm_button", []),
            step_logs,
            step_name="confirm_reward_setting",
            timeout=6000,
            settle_ms=1800,
        )

    _retry_once("apply_wechat_publish_settings", step_logs, _apply_once)


def _wait_for_wechat_editor_in_current_page_with_retry(page, selector_profile: dict[str, list[str] | str], step_logs: list[str]):
    def _locate_once():
        return _wait_for_wechat_editor_in_current_page(page, selector_profile)

    return _retry_once("wait_current_editor_page", step_logs, _locate_once)


def _scrape_wechat_draft_items_strict(page) -> list[dict[str, str | None]]:
    rows = page.evaluate(
        """() => {
            const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
            const results = [];
            const seenStable = new Set();
            const normalizeTitleKey = (value) =>
                normalize(value)
                    .replace(/[“”]/g, '"')
                    .replace(/[‘’]/g, "'")
                    .replace(/[：:]/g, ':')
                    .toLowerCase();
            const containers = Array.from(
                document.querySelectorAll(
                    '.publish_card_container, .weui-desktop-card.weui-desktop-publish, .weui-desktop-media__list-col .weui-desktop-card'
                )
            );

            const resolveTitleNode = (container) =>
                container.querySelector('.weui-desktop-publish__cover__title span') ||
                container.querySelector('.weui-desktop-publish__cover__title') ||
                container.querySelector('.weui-desktop-card__title') ||
                container.querySelector('a[title]');

            const resolveLinkNode = (container) =>
                container.querySelector('a.weui-desktop-publish__cover__title[href]') ||
                container.querySelector('.weui-desktop-publish__cover__title[href]') ||
                container.querySelector('a[href]');

            containers.forEach((container, index) => {
                const titleNode = resolveTitleNode(container);
                const linkNode = resolveLinkNode(container);
                const title = normalize(titleNode ? titleNode.textContent : '');
                const href = normalize(linkNode ? linkNode.getAttribute('href') : '');
                if (!title && !href) return;
                const containerText = normalize(container.innerText || '');
                const updatedAtMatch = containerText.match(/(昨天\s*[0-9]{1,2}:[0-9]{2}|星期[一二三四五六日天]\s*[0-9]{1,2}:[0-9]{2}|[0-9]{1,2}月[0-9]{1,2}日|[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2}|[0-9]{1,2}:[0-9]{2})/);
                const updatedAt = updatedAtMatch ? normalize(updatedAtMatch[1]) : '';
                const normalizedHref = href && !href.startsWith('javascript:') ? (href.startsWith('/') ? `${window.location.origin}${href}` : href) : '';
                let appmsgId = null;
                try {
                    if (normalizedHref) {
                        const parsed = new URL(normalizedHref, window.location.origin);
                        appmsgId = parsed.searchParams.get('appmsgid');
                    }
                } catch (_) {}
                const titleKey = normalizeTitleKey(title);
                const stableKey = appmsgId ? `appmsg:${appmsgId}` : normalizedHref ? `url:${normalizedHref}` : '';
                const dedupeKey = stableKey || `title:${titleKey}|updated:${updatedAt}`;
                if (seenStable.has(dedupeKey)) return;
                seenStable.add(dedupeKey);
                results.push({
                    title,
                    url: normalizedHref,
                    appmsg_id: appmsgId,
                    updated_at: updatedAt,
                    remote_key: stableKey || `card:${titleKey}|updated:${updatedAt}|${index}`,
                });
            });

            return results.slice(0, 80);
        }"""
    )
    if not isinstance(rows, list):
        raise RuntimeError("草稿箱抓取结果格式异常。")
    items: list[dict[str, str | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "appmsg_id": str(row.get("appmsg_id") or "").strip() or None,
                "updated_at": str(row.get("updated_at") or "").strip() or None,
                "remote_key": str(row.get("remote_key") or "").strip() or None,
            }
        )
    return items


def _open_wechat_publish_history(page, selector_profile: dict[str, list[str] | str], step_logs: list[str]) -> bool:
    content_manage_selector = _pick_selector(page, selector_profile.get("content_manage", []), timeout=2500)
    if content_manage_selector:
        try:
            page.locator(content_manage_selector).first.click()
            page.wait_for_timeout(1200)
            step_logs.append(f"已展开内容管理 selector={content_manage_selector}")
        except Exception:
            step_logs.append(f"尝试展开内容管理失败 selector={content_manage_selector}")

    selector_candidates = selector_profile.get("publish_history", [])
    selector_list = selector_candidates if isinstance(selector_candidates, list) else [selector_candidates]
    if not selector_list:
        return False
    failed_selectors: list[str] = []
    for selector in [str(item) for item in selector_list if str(item).strip()]:
        try:
            locator = page.locator(selector).first
            try:
                locator.wait_for(timeout=4000)
            except Exception:
                href = ""
                try:
                    href = str(locator.get_attribute("href", timeout=1200) or "").strip()
                except Exception:
                    href = ""
                if href and "appmsgpublish" in href:
                    target_url = href if href.startswith("http") else f"https://mp.weixin.qq.com{href}"
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1200)
                else:
                    raise
            else:
                try:
                    locator.click(timeout=2000)
                except Exception:
                    href = ""
                    try:
                        href = str(locator.get_attribute("href", timeout=1200) or "").strip()
                    except Exception:
                        href = ""
                    if href and "appmsgpublish" in href:
                        target_url = href if href.startswith("http") else f"https://mp.weixin.qq.com{href}"
                        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(1200)
                    else:
                        locator.click(timeout=2000, force=True)
            try:
                page.wait_for_url("**appmsgpublish**", timeout=8000)
            except Exception:
                page.wait_for_timeout(2500)
            current_url = str(page.url or "")
            if "appmsgpublish" not in current_url:
                failed_selectors.append(selector)
                step_logs.append(f"发表记录入口未跳转 selector={selector} url={current_url}")
                continue
            step_logs.append(f"已点击发表记录入口 selector={selector}")
            step_logs.append(f"已进入发表记录页面 url={current_url}")
            return True
        except Exception as exc:
            failed_selectors.append(selector)
            step_logs.append(f"发表记录入口点击失败 selector={selector} error={exc}")
            continue
    if failed_selectors:
        step_logs.append(f"发表记录入口全部尝试失败：{', '.join(failed_selectors)}")
    return False


def _inspect_wechat_publish_history_document(target) -> dict[str, object]:
    result = target.evaluate(
        """() => {
            const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const titleAnchors = Array.from(document.querySelectorAll('a.weui-desktop-mass-appmsg__title, a.weui-desktop-publish__title, a[href*="mp.weixin.qq.com/s/"]'));
            const timeNodes = Array.from(document.querySelectorAll('.weui-desktop-mass__time, .weui-desktop-publish__time, .publish_time'));
            const hoverCards = Array.from(document.querySelectorAll('.publish_hover_content'));
            const massCards = Array.from(document.querySelectorAll('.weui-desktop-mass-media, .weui-desktop-mass-appmsg'));
            const sampleTitles = titleAnchors
                .map((node) => normalize(node.textContent || node.getAttribute('title') || ''))
                .filter(Boolean)
                .slice(0, 5);
            const sampleTimes = timeNodes
                .map((node) => normalize(node.textContent || ''))
                .filter(Boolean)
                .slice(0, 5);
            return {
                href: window.location.href,
                title: document.title || '',
                readyState: document.readyState || '',
                title_anchor_count: titleAnchors.length,
                time_count: timeNodes.length,
                hover_card_count: hoverCards.length,
                mass_card_count: massCards.length,
                sample_titles: sampleTitles,
                sample_times: sampleTimes,
                body_text_head: normalize((document.body && document.body.innerText) || '').slice(0, 240),
            };
        }"""
    )
    if not isinstance(result, dict):
        return {}
    return result


def _scrape_wechat_publish_history_from_target(target) -> list[dict[str, str | None]]:
    rows = target.evaluate(
        """() => {
            const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const cleanTitleLabel = (value) => normalize(value).replace(/\\s*原创\\s*$/u, '').trim();
            const results = [];
            const seenStable = new Set();
            const cardSelector = '.publish_hover_content, .weui-desktop-mass-media, .weui-desktop-mass-appmsg, .publish_card_container, .weui-desktop-card.weui-desktop-publish, .weui-desktop-media__list-col .weui-desktop-card, .publish_list .publish_item';

            const absolutize = (value) => {
                const raw = normalize(value);
                if (!raw || raw.startsWith('javascript:')) return '';
                if (raw.startsWith('//')) return `${window.location.protocol}${raw}`;
                if (raw.startsWith('/')) return `${window.location.origin}${raw}`;
                return raw;
            };

            const pushItem = (title, url, publishedAt, occurrence) => {
                const cleanTitle = cleanTitleLabel(title);
                const normalizedUrl = absolutize(url);
                if (cleanTitle.length < 2) return;
                let appmsgId = null;
                try {
                    if (normalizedUrl) {
                        const parsed = new URL(normalizedUrl, window.location.origin);
                        appmsgId = parsed.searchParams.get('appmsgid');
                    }
                } catch (_) {}
                const stableKey = appmsgId
                    ? `appmsg:${appmsgId}`
                    : normalizedUrl
                        ? `url:${normalizedUrl}`
                        : `publish:${cleanTitle}|${normalize(publishedAt)}|${occurrence}`;
                if (seenStable.has(stableKey)) return;
                seenStable.add(stableKey);
                results.push({
                    title: cleanTitle,
                    url: normalizedUrl,
                    appmsg_id: appmsgId,
                    published_at: normalize(publishedAt),
                    remote_key: stableKey,
                });
            };

            const extractPublishedAt = (container) => {
                const dateNode =
                    container?.querySelector('.weui-desktop-mass__time') ||
                    container?.querySelector('.weui-desktop-publish__time') ||
                    container?.querySelector('.publish_time') ||
                    container?.querySelector('.weui-desktop-card__time');
                let publishedAt = normalize(dateNode ? dateNode.textContent : '');
                if (!publishedAt) {
                    const text = normalize(container?.innerText || '');
                    const match = text.match(/((?:昨天|前天|星期[一二三四五六日天])?\\s*[0-9]{1,2}:[0-9]{2}|[0-9]{1,2}月[0-9]{1,2}日|[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2})/);
                    publishedAt = match ? normalize(match[1]) : '';
                }
                return publishedAt;
            };

            const findBestContainer = (node) => {
                if (!node) return null;
                const directPublish = node.closest('.publish_hover_content');
                if (directPublish) return directPublish;
                let current = node;
                while (current && current !== document.body) {
                    if (current.matches && current.matches(cardSelector)) {
                        const hasTimeNode = current.querySelector('.weui-desktop-mass__time, .weui-desktop-publish__time, .publish_time, .weui-desktop-card__time');
                        if (hasTimeNode) return current;
                    }
                    current = current.parentElement;
                }
                return node.closest(cardSelector) || node.parentElement || node;
            };

            const titleAnchors = Array.from(
                document.querySelectorAll('a.weui-desktop-mass-appmsg__title, a.weui-desktop-publish__title, a[href*="mp.weixin.qq.com/s/"]')
            );
            titleAnchors.forEach((anchor, index) => {
                const container = findBestContainer(anchor);
                const href = anchor.getAttribute('href') || '';
                const title =
                    cleanTitleLabel(anchor.textContent || '') ||
                    cleanTitleLabel(anchor.getAttribute('title') || '') ||
                    cleanTitleLabel(anchor.querySelector('span')?.textContent || '');
                const publishedAt = extractPublishedAt(container);
                pushItem(title, href, publishedAt, index);
            });

            if (!results.length) {
                const containers = Array.from(document.querySelectorAll(cardSelector));
                containers.forEach((container, index) => {
                    const titleNode =
                        container.querySelector('.weui-desktop-mass-appmsg__title span') ||
                        container.querySelector('.weui-desktop-mass-appmsg__title') ||
                        container.querySelector('.weui-desktop-publish__title span') ||
                        container.querySelector('.weui-desktop-publish__title') ||
                        container.querySelector('.weui-desktop-publish__cover__title span') ||
                        container.querySelector('.weui-desktop-publish__cover__title') ||
                        container.querySelector('.weui-desktop-card__title') ||
                        container.querySelector('a[title]') ||
                        container.querySelector('h3');
                    const linkNode =
                        container.querySelector('a.weui-desktop-mass-appmsg__title') ||
                        container.querySelector('a.weui-desktop-publish__title') ||
                        container.querySelector('a[href*="mp.weixin.qq.com/s/"]') ||
                        container.querySelector('a[href]');
                    const title = cleanTitleLabel(titleNode ? titleNode.textContent : '');
                    const href = linkNode ? linkNode.getAttribute('href') || '' : '';
                    const publishedAt = extractPublishedAt(container);
                    pushItem(title, href, publishedAt, index);
                });
            }

            return results.slice(0, 80);
        }"""
    )
    if not isinstance(rows, list):
        raise RuntimeError("发表记录抓取结果格式异常。")
    items: list[dict[str, str | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "title": str(row.get("title") or "").strip(),
                "url": str(row.get("url") or "").strip(),
                "appmsg_id": str(row.get("appmsg_id") or "").strip() or None,
                "published_at": str(row.get("published_at") or "").strip() or None,
                "remote_key": str(row.get("remote_key") or "").strip() or None,
            }
        )
    return items


def _scrape_wechat_publish_history_items(page, step_logs: list[str] | None = None) -> list[dict[str, str | None]]:
    diagnostic_logs = step_logs if step_logs is not None else []
    targets = [("page", page)]
    try:
        frames = list(page.frames)
    except Exception:
        frames = []
    for index, frame in enumerate(frames):
        if frame is page.main_frame:
            continue
        targets.append((f"frame[{index}]", frame))

    merged: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for label, target in targets:
        try:
            diag = _inspect_wechat_publish_history_document(target)
            if diag:
                diagnostic_logs.append(
                    "发表记录DOM "
                    f"{label} url={diag.get('href') or ''} "
                    f"titleAnchors={diag.get('title_anchor_count', 0)} "
                    f"timeNodes={diag.get('time_count', 0)} "
                    f"hoverCards={diag.get('hover_card_count', 0)} "
                    f"massCards={diag.get('mass_card_count', 0)} "
                    f"samples={','.join(str(item) for item in (diag.get('sample_titles') or [])[:3]) or 'none'}"
                )
            rows = _scrape_wechat_publish_history_from_target(target)
            diagnostic_logs.append(f"发表记录抽取 {label} rows={len(rows)}")
        except Exception as exc:
            diagnostic_logs.append(f"发表记录抽取 {label} 失败：{exc}")
            continue
        for row in rows:
            stable_key = (
                str(row.get("remote_key") or "").strip()
                or str(row.get("url") or "").strip()
                or f"{str(row.get('title') or '').strip()}|{str(row.get('published_at') or '').strip()}"
            )
            if not stable_key or stable_key in seen:
                continue
            seen.add(stable_key)
            merged.append(row)
    return merged


def inspect_wechat_draft_box(
    channel: dict[str, object],
    browser_state: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str], list[dict[str, str | None]]]:
    channel = ensure_channel_defaults(channel)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        f"entry_url={entry_url}",
        "action=check_draft_box",
    ]
    artifacts: list[str] = []
    browser_state = dict(browser_state)
    browser_state["is_session_level_error"] = False

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器登录态不可用，无法检查微信草稿箱。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行草稿箱检查：登录态不可用。"], []

    artifact_dir = ARTIFACT_ROOT / "session"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"check-draft-box-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        def _run(_context, page):
            WECHAT_BROWSER_MANAGER.set_action_state("check_draft_box", "go_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_draft_box_return_home")
            WECHAT_BROWSER_MANAGER.set_action_state("check_draft_box", "open_draft_box")
            if not _open_wechat_draft_box(page, selector_profile, step_logs):
                raise RuntimeError("未能进入正式草稿箱页面（/cgi-bin/appmsg?...action=list_card...）。")
            current_page = page
            current_page.wait_for_timeout(2000)
            if not _validate_wechat_page_identity(current_page, selector_profile, expected="draft_box"):
                raise RuntimeError(f"当前页面不是正式草稿箱：{current_page.url}")
            WECHAT_BROWSER_MANAGER.set_action_state("check_draft_box", "scrape")
            items = _scrape_wechat_draft_items_strict(current_page)
            current_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = current_page.url
            browser_state["current_page"] = current_page.url
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["resident_page"] = "draft_box"
            WECHAT_BROWSER_MANAGER.set_resident_page("draft_box")
            browser_state["last_error"] = None
            step_logs.append(f"共读取到 {len(items)} 条微信草稿记录。")
            WECHAT_BROWSER_MANAGER.set_action_state("check_draft_box", "return_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_draft_box_return_home_final")
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            WECHAT_BROWSER_MANAGER.set_resident_page("home")
            return items

        remote_items = WECHAT_BROWSER_MANAGER.with_session(
            channel,
            restore_window=False,
            action_fn=_run,
        )
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs, remote_items
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"草稿箱检查失败：{exc}"
        browser_state["is_session_level_error"] = _browser_session_error_kind(exc, recovery_ok=False)
        step_logs.append(f"草稿箱检查失败：{exc}")
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        return browser_state, artifacts, step_logs, []


def inspect_wechat_publish_history(
    channel: dict[str, object],
    browser_state: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str], list[dict[str, str | None]]]:
    channel = ensure_channel_defaults(channel)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        f"entry_url={entry_url}",
        "action=check_publish_history",
    ]
    artifacts: list[str] = []
    browser_state = dict(browser_state)
    browser_state["is_session_level_error"] = False

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器登录态不可用，无法检查微信发表记录。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行发表记录检查：登录态不可用。"], []

    artifact_dir = ARTIFACT_ROOT / "session"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"check-publish-history-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        def _run(_context, page):
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "go_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_publish_history_return_home")
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "open_publish_history")
            if not _open_wechat_publish_history(page, selector_profile, step_logs):
                raise RuntimeError("未能进入正式发表记录页面（/cgi-bin/appmsgpublish?...）。")
            current_page = page
            current_page.wait_for_timeout(2000)
            if "appmsgpublish" not in str(current_page.url or ""):
                raise RuntimeError(f"当前页面不是发表记录：{current_page.url}")
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "scrape")
            items = _scrape_wechat_publish_history_items(current_page, step_logs)
            current_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = current_page.url
            browser_state["current_page"] = current_page.url
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["resident_page"] = "publish_history"
            WECHAT_BROWSER_MANAGER.set_resident_page("publish_history")
            browser_state["last_error"] = None
            step_logs.append(f"共读取到 {len(items)} 条微信发表记录。")
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "return_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_publish_history_return_home_final")
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            WECHAT_BROWSER_MANAGER.set_resident_page("home")
            return items

        remote_items = WECHAT_BROWSER_MANAGER.with_session(
            channel,
            restore_window=False,
            action_fn=_run,
        )
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs, remote_items
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"发表记录检查失败：{exc}"
        browser_state["is_session_level_error"] = _browser_session_error_kind(exc, recovery_ok=False)
        step_logs.append(f"发表记录检查失败：{exc}")
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        return browser_state, artifacts, step_logs, []


def launch_wechat_dashboard(channel: dict[str, object], browser_state: dict[str, object]) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    step_logs = [
        f"browser={normalize_browser_name(channel.get('browser_name'))}",
        f"profile={resolve_profile_path(channel.get('browser_profile_path'), channel.get('browser_name'))}",
        f"entry_url={entry_url}",
    ]
    try:
        def _run(_context, page):
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            try:
                page.evaluate("() => { document.title = 'AutoNews-微信专用'; }")
            except Exception:
                pass
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            WECHAT_BROWSER_MANAGER.set_resident_page("home")
            browser_state["last_checked_at"] = now_iso()
            browser_state["last_error"] = None
            step_logs.append("已恢复微信专用浏览器并打开公众号后台首页。")

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, [], step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"浏览器启动失败：{exc}"
        return browser_state, [], step_logs + [f"浏览器启动失败：{exc}"]


def inspect_wechat_session(channel: dict[str, object], browser_state: dict[str, object]) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    profile_path = resolve_profile_path(channel.get("browser_profile_path"), channel.get("browser_name"))
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    screenshot_path = artifact_dir / f"check-browser-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"
    debug_text_path = artifact_dir / f"check-browser-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.txt"
    step_logs = [
        f"selector_profile={selector_version}",
        f"profile={resolve_profile_path(channel.get('browser_profile_path'), channel.get('browser_name'))}",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []

    try:
        from playwright.sync_api import Error as PlaywrightError  # type: ignore

        def _run(_context, page):
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            logged_in = False
            matched_selector = None
            for selector in selector_profile.get("logged_in", []):
                try:
                    page.wait_for_selector(str(selector), timeout=1200)
                    logged_in = True
                    matched_selector = str(selector)
                    break
                except PlaywrightError:
                    continue
            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["browser_name"] = normalize_browser_name(channel.get("browser_name"))
            browser_state["user_data_dir"] = str(profile_path)
            browser_state["logged_in"] = logged_in
            browser_state["last_checked_at"] = now_iso()
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            WECHAT_BROWSER_MANAGER.set_resident_page("home")
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None if logged_in else "未检测到公众号后台登录态，当前可能仍停留在登录页。"
            if matched_selector:
                step_logs.append(f"检测到登录态选择器：{matched_selector}")
            else:
                step_logs.append("未命中登录态选择器。")

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
    except Exception as exc:  # pragma: no cover - host/browser dependent
        artifact = _write_debug_artifact(
            debug_text_path,
            [
                "浏览器会话检查失败。",
                f"profile={profile_path}",
                f"entry_url={entry_url}",
                f"error={exc}",
            ],
        )
        artifacts.append(artifact)
        browser_state["logged_in"] = False
        browser_state["last_checked_at"] = now_iso()
        browser_state["last_screenshot"] = artifact
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"浏览器会话检查失败：{exc}"
        return browser_state, artifacts, step_logs + [f"会话检查失败：{exc}"]

    return browser_state, artifacts, step_logs


def inspect_wechat_editor_dom(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"inspect-wechat-editor-{timestamp}.png"
    debug_text_path = artifact_dir / f"inspect-wechat-editor-{timestamp}.txt"
    html_path = artifact_dir / f"inspect-wechat-editor-{timestamp}.html"
    snapshot: dict[str, object] = {
        "checked_at": now_iso(),
        "url": "",
        "page_title": "",
        "body_excerpt": "",
        "message": "",
        "items": [],
        "artifacts": [],
    }
    step_logs = [
        f"selector_profile={selector_version}",
        "action=inspect_wechat_editor_dom",
    ]
    artifacts: list[str] = []

    try:
        def _run(_context, page):
            current_url = str(page.url or "")
            if "appmsg" not in current_url and "media/appmsg_edit" not in current_url:
                raise RuntimeError(f"当前不在微信编辑页：{current_url}")

            field_specs = [
                ("title", "标题", selector_profile.get("title_input", [])),
                ("author", "作者", selector_profile.get("author_input", [])),
                ("digest", "摘要", selector_profile.get("digest_input", [])),
                ("editor", "正文", selector_profile.get("editor", [])),
            ]
            fields: list[dict[str, object]] = []
            for key, label, selectors in field_specs:
                selector_list = selectors if isinstance(selectors, list) else [selectors]
                matched_selector = None
                matched_count = 0
                visible = False
                sample_text = ""
                sample_html = ""
                for selector in [str(item) for item in selector_list if str(item).strip()]:
                    try:
                        locator = page.locator(selector)
                        count = locator.count()
                        if count <= 0:
                            continue
                        matched_selector = selector
                        matched_count = count
                        try:
                            locator.first.wait_for(state="visible", timeout=1500)
                            visible = True
                        except Exception:
                            visible = False
                        try:
                            sample_text = str(locator.first.inner_text(timeout=1500) or "").strip()
                        except Exception:
                            sample_text = ""
                        try:
                            sample_html = str(locator.first.evaluate("(el) => el.outerHTML || ''") or "").strip()
                        except Exception:
                            sample_html = ""
                        break
                    except Exception:
                        continue
                fields.append(
                    {
                        "key": key,
                        "label": label,
                        "found": bool(matched_selector),
                        "visible": visible,
                        "selector": matched_selector,
                        "count": matched_count,
                        "sample_text": sample_text[:500],
                        "sample_html": sample_html[:3000],
                    }
                )

            page_title = ""
            body_excerpt = ""
            html_content = ""
            try:
                page_title = str(page.title() or "")
            except Exception:
                page_title = ""
            try:
                body_excerpt = str(page.locator("body").inner_text(timeout=2500) or "").strip()
            except Exception:
                body_excerpt = ""
            try:
                html_content = str(page.content() or "")
                html_path.write_text(html_content, encoding="utf-8")
                artifacts.append(str(html_path))
            except Exception as exc:
                step_logs.append(f"导出当前页 HTML 失败：{exc}")

            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            debug_lines = [
                f"url={page.url}",
                f"title={page_title}",
                "",
                "body_excerpt:",
                body_excerpt[:3000],
                "",
            ]
            for field in fields:
                debug_lines.extend(
                    [
                        f"[{field['key']}] {field['label']}",
                        f"found={field['found']} visible={field['visible']} count={field['count']} selector={field['selector']}",
                        f"text={field['sample_text']}",
                        "html:",
                        str(field["sample_html"]),
                        "",
                    ]
                )
            artifacts.append(_write_debug_artifact(debug_text_path, debug_lines))

            snapshot["checked_at"] = now_iso()
            snapshot["url"] = str(page.url or "")
            snapshot["page_title"] = page_title
            snapshot["body_excerpt"] = body_excerpt[:3000]
            snapshot["items"] = fields
            snapshot["artifacts"] = list(artifacts)
            snapshot["message"] = f"已导出微信编辑页 DOM，命中 {sum(1 for field in fields if field.get('found'))}/{len(fields)} 个关键区块。"

            browser_state["last_opened_url"] = str(page.url or "")
            browser_state["current_page"] = str(page.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            WECHAT_BROWSER_MANAGER.set_resident_page("editor")
            step_logs.append(str(snapshot["message"]))

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, snapshot, artifacts, step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"导出微信编辑页 DOM 失败：{exc}"
        step_logs.append(f"导出微信编辑页 DOM 失败：{exc}")
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
                snapshot["url"] = current_url
        snapshot["checked_at"] = now_iso()
        snapshot["message"] = str(browser_state["last_error"])
        snapshot["artifacts"] = list(artifacts)
        return browser_state, snapshot, artifacts, step_logs


def open_wechat_editor_debug(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        "action=open_wechat_editor_debug",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []
    artifact_dir = ARTIFACT_ROOT / "session"
    screenshot_path = artifact_dir / f"open-wechat-editor-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器用户目录不存在或尚未建立登录态。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行打开编辑页：登录态不可用。"]

    try:
        def _run(context, page):
            _enforce_single_tab(context, page, step_logs, phase="open_editor_debug_start", allow_recover=True)
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="open_editor_debug_go_home")
            new_article_selector = _pick_required_selector(
                page,
                selector_profile.get("new_article", []),
                step_logs,
                step_name="open_editor_debug_pick_new_article",
                timeout=8000,
            )
            page.locator(new_article_selector).first.click()
            step_logs.append(f"已点击新建文章入口 selector={new_article_selector}")
            page.wait_for_timeout(2500)
            target = _locate_editor_page_with_retry(context, page, selector_profile, step_logs)
            if target is not page:
                step_logs.append(f"检测到新编辑页接管 URL={_page_url(target)}")
                _converge_context_to_target(context, target, step_logs, phase="open_editor_debug_targeted")
                try:
                    WECHAT_BROWSER_MANAGER._page = target
                except Exception:
                    pass
            try:
                target.wait_for_load_state("domcontentloaded", timeout=4000)
            except Exception:
                pass
            target.wait_for_timeout(1800)
            _enforce_single_tab(context, target, step_logs, phase="open_editor_debug_after_open", allow_recover=False)
            target.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = str(target.url or "")
            browser_state["current_page"] = str(target.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            WECHAT_BROWSER_MANAGER.set_resident_page("editor")
            step_logs.append(f"已进入微信编辑页 URL={target.url}")

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs
    except Exception as exc:
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"打开微信编辑页失败：{exc}"
        browser_state["is_session_level_error"] = _browser_session_error_kind(exc, recovery_ok=False)
        step_logs.append(f"打开微信编辑页失败：{exc}")
        return browser_state, artifacts, step_logs


def fill_wechat_author_only(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        "action=fill_wechat_author_only",
    ]
    artifacts: list[str] = []
    artifact_dir = ARTIFACT_ROOT / "session"
    screenshot_path = artifact_dir / f"wechat-author-only-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器用户目录不存在或尚未建立登录态。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行作者填写：登录态不可用。"]

    try:
        def _run(context, page):
            _enforce_single_tab(context, page, step_logs, phase="author_only_start", allow_recover=True)
            editor_page = _wait_for_wechat_editor_in_current_page_with_retry(page, selector_profile, step_logs)
            _enforce_single_tab(context, editor_page, step_logs, phase="author_only_editor_ready", allow_recover=False)
            editor_page.wait_for_timeout(1200)
            step_logs.append(f"已锁定当前微信编辑页 URL={editor_page.url}")
            WECHAT_BROWSER_MANAGER.set_resident_page("editor")
            WECHAT_BROWSER_MANAGER.set_action_state("fill_wechat_author_only", "fill_author")
            author = _ensure_wechat_author_before_publish_settings(editor_page, channel, selector_profile, step_logs)
            step_logs.append(f"作者已填写为 {author}")

            editor_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = str(editor_page.url or "")
            browser_state["current_page"] = str(editor_page.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            browser_state["is_session_level_error"] = False

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs
    except Exception as exc:
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"微信作者填写失败：{exc}"
        browser_state["is_session_level_error"] = _browser_session_error_kind(exc, recovery_ok=False)
        step_logs.append(f"微信作者填写失败：{exc}")
        return browser_state, artifacts, step_logs


def test_wechat_publish_settings_only(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        "action=test_wechat_publish_settings_only",
    ]
    artifacts: list[str] = []
    artifact_dir = ARTIFACT_ROOT / "session"
    screenshot_path = artifact_dir / f"wechat-settings-only-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器用户目录不存在或尚未建立登录态。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行后半段调试：登录态不可用。"]

    try:
        def _run(context, page):
            _enforce_single_tab(context, page, step_logs, phase="settings_only_start", allow_recover=True)
            editor_page = _wait_for_wechat_editor_in_current_page_with_retry(page, selector_profile, step_logs)
            _enforce_single_tab(context, editor_page, step_logs, phase="settings_only_editor_ready", allow_recover=False)
            editor_page.wait_for_timeout(1200)
            step_logs.append(f"已锁定当前微信编辑页 URL={editor_page.url}")
            WECHAT_BROWSER_MANAGER.set_resident_page("editor")
            _ensure_wechat_author_before_publish_settings(editor_page, channel, selector_profile, step_logs)
            WECHAT_BROWSER_MANAGER.set_action_state("test_wechat_publish_settings_only", "apply_publish_settings")
            _apply_wechat_publish_settings(editor_page, selector_profile, step_logs)

            save_selector = _pick_required_selector(
                editor_page,
                selector_profile.get("save_draft_button", []),
                step_logs,
                step_name="settings_only_pick_save_draft_selector",
                timeout=6000,
            )
            WECHAT_BROWSER_MANAGER.set_action_state("test_wechat_publish_settings_only", "save_draft")
            _pick_visible_locator(editor_page, save_selector, timeout=4000).click()
            editor_page.wait_for_timeout(3500)
            step_logs.append(f"已点击保存草稿 selector={save_selector}")

            editor_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = str(editor_page.url or "")
            browser_state["current_page"] = str(editor_page.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            browser_state["is_session_level_error"] = False

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs
    except Exception as exc:
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"微信后半段流程调试失败：{exc}"
        browser_state["is_session_level_error"] = _browser_session_error_kind(exc, recovery_ok=False)
        step_logs.append(f"微信后半段流程调试失败：{exc}")
        return browser_state, artifacts, step_logs


def launch_douyin_dashboard(channel: dict[str, object], browser_state: dict[str, object]) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_douyin_channel_defaults(channel)
    browser_state = dict(browser_state)
    entry_url = str(channel.get("publish_entry_url", "https://creator.douyin.com/"))
    profile_path = Path(str(channel.get("browser_profile_path") or "")).expanduser()
    selector_version = str(channel.get("selectors_version", "douyin-creator-v1"))
    step_logs = [
        f"selector_profile={selector_version}",
        f"browser={normalize_browser_name(channel.get('browser_name'))}",
        f"profile={profile_path}",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []
    try:
        def _run(_context, page):
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2200)
            try:
                page.evaluate("() => { document.title = 'AutoNews-抖音探测'; }")
            except Exception:
                pass
            browser_state["platform"] = "douyin_creator"
            browser_state["browser_name"] = normalize_browser_name(channel.get("browser_name"))
            browser_state["user_data_dir"] = str(profile_path)
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            DOUYIN_BROWSER_MANAGER.set_resident_page("home")
            browser_state["last_checked_at"] = now_iso()
            browser_state["last_error"] = None
            step_logs.append(f"已打开抖音创作者中心首页 url={page.url}")

        DOUYIN_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs
    except Exception as exc:
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"抖音浏览器启动失败：{exc}"
        return browser_state, artifacts, step_logs + [f"抖音浏览器启动失败：{exc}"]


def inspect_douyin_session(channel: dict[str, object], browser_state: dict[str, object]) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_douyin_channel_defaults(channel)
    browser_state = dict(browser_state)
    entry_url = str(channel.get("publish_entry_url", "https://creator.douyin.com/"))
    profile_path = Path(str(channel.get("browser_profile_path") or "")).expanduser()
    selector_version = str(channel.get("selectors_version", "douyin-creator-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    screenshot_path = artifact_dir / f"check-douyin-browser-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"
    debug_text_path = artifact_dir / f"check-douyin-browser-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.txt"
    step_logs = [
        f"selector_profile={selector_version}",
        f"profile={profile_path}",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []

    try:
        def _run(_context, page):
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2600)
            logged_in = False
            matched_selector = None
            for selector in selector_profile.get("logged_in", []):
                try:
                    if page.locator(str(selector)).first.count() > 0:
                        logged_in = True
                        matched_selector = str(selector)
                        break
                except Exception:
                    continue

            publish_selector = None
            if logged_in:
                for selector in selector_profile.get("publish_entry", []):
                    try:
                        if page.locator(str(selector)).first.count() > 0:
                            publish_selector = str(selector)
                            break
                    except Exception:
                        continue

            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["platform"] = "douyin_creator"
            browser_state["browser_name"] = normalize_browser_name(channel.get("browser_name"))
            browser_state["user_data_dir"] = str(profile_path)
            browser_state["logged_in"] = logged_in
            browser_state["last_checked_at"] = now_iso()
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            DOUYIN_BROWSER_MANAGER.set_resident_page("home")
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None if logged_in else "未检测到抖音创作者中心登录态，当前可能仍停留在登录页。"
            if matched_selector:
                step_logs.append(f"检测到抖音登录态选择器：{matched_selector}")
            else:
                step_logs.append("未命中抖音登录态选择器。")
            if publish_selector:
                step_logs.append(f"检测到抖音发布入口：{publish_selector}")
            elif logged_in:
                step_logs.append("已登录，但暂未识别到明确发布入口。")

        DOUYIN_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
    except Exception as exc:  # pragma: no cover - host/browser dependent
        artifact = _write_debug_artifact(
            debug_text_path,
            [
                "抖音浏览器会话检查失败。",
                f"profile={profile_path}",
                f"entry_url={entry_url}",
                f"error={exc}",
            ],
        )
        artifacts.append(artifact)
        browser_state["platform"] = "douyin_creator"
        browser_state["logged_in"] = False
        browser_state["last_checked_at"] = now_iso()
        browser_state["last_screenshot"] = artifact
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"抖音浏览器会话检查失败：{exc}"
        return browser_state, artifacts, step_logs + [f"抖音会话检查失败：{exc}"]

    return browser_state, artifacts, step_logs


def open_douyin_article_publish(channel: dict[str, object], browser_state: dict[str, object]) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_douyin_channel_defaults(channel)
    browser_state = dict(browser_state)
    entry_url = str(channel.get("publish_entry_url", "https://creator.douyin.com/"))
    selector_version = str(channel.get("selectors_version", "douyin-creator-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    screenshot_path = artifact_dir / f"open-douyin-article-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"
    step_logs = [
        f"selector_profile={selector_version}",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []

    try:
        def _run(_context, page):
            page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2600)
            publish_selector = None
            start_article_selector = None
            for selector in selector_profile.get("publish_entry", []):
                try:
                    locator = page.locator(str(selector)).first
                    if locator.count() > 0:
                        publish_selector = str(selector)
                        try:
                            locator.click(timeout=2500)
                        except Exception:
                            locator.click(timeout=2500, force=True)
                        break
                except Exception:
                    continue

            if not publish_selector:
                raise RuntimeError("未识别到“发布文章”入口。")

            page.wait_for_timeout(3500)
            for selector in selector_profile.get("start_article", []):
                try:
                    locator = page.locator(str(selector)).first
                    if locator.count() > 0 and locator.is_visible():
                        start_article_selector = str(selector)
                        try:
                            locator.click(timeout=2500)
                        except Exception:
                            locator.click(timeout=2500, force=True)
                        page.wait_for_timeout(3200)
                        break
                except Exception:
                    continue
            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["platform"] = "douyin_creator"
            browser_state["logged_in"] = True
            browser_state["last_checked_at"] = now_iso()
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "article_publish"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            DOUYIN_BROWSER_MANAGER.set_resident_page("article_publish")
            step_logs.append(f"已点击抖音发布入口：{publish_selector}")
            if start_article_selector:
                step_logs.append(f"已点击抖音二级入口：{start_article_selector}")
            else:
                step_logs.append("当前流程未出现“我要发文”二级入口。")
            step_logs.append(f"当前页面 url={page.url}")

        DOUYIN_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs
    except Exception as exc:
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"打开抖音发布文章页失败：{exc}"
        step_logs.append(f"打开抖音发布文章页失败：{exc}")
        ok, current_url = DOUYIN_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        return browser_state, artifacts, step_logs


def inspect_douyin_article_structure(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_douyin_channel_defaults(channel)
    browser_state = dict(browser_state)
    entry_url = str(channel.get("publish_entry_url", "https://creator.douyin.com/"))
    selector_version = str(channel.get("selectors_version", "douyin-creator-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"inspect-douyin-article-{timestamp}.png"
    debug_text_path = artifact_dir / f"inspect-douyin-article-{timestamp}.txt"
    step_logs = [
        f"selector_profile={selector_version}",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []
    snapshot: dict[str, object] = {
        "checked_at": now_iso(),
        "url": "",
        "page_title": "",
        "body_excerpt": "",
        "message": "",
        "items": [],
        "artifacts": [],
    }

    try:
        def _run(_context, page):
            current_url = str(page.url or "")
            if "creator.douyin.com" not in current_url:
                page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2600)
            current_url = str(page.url or "")
            if "/content/post/article" not in current_url:
                raise RuntimeError("当前不在抖音文章发布页，请先打开“发布文章”页面。")

            fields: list[dict[str, object]] = []
            inspect_specs = [
                ("title_input", "标题区"),
                ("content_editor", "正文编辑区"),
                ("cover_upload", "上传入口"),
                ("images_panel", "图片/封面区"),
                ("submit_button", "底部操作按钮"),
            ]

            for key, label in inspect_specs:
                matched_selector = None
                matched_count = 0
                visible = False
                sample_text = ""
                sample_html = ""
                for selector in selector_profile.get(key, []):
                    try:
                        locator = page.locator(str(selector))
                        count = locator.count()
                        if count <= 0:
                            continue
                        first = locator.first
                        matched_selector = str(selector)
                        matched_count = int(count)
                        try:
                            visible = bool(first.is_visible())
                        except Exception:
                            visible = False
                        try:
                            sample_text = str(first.inner_text(timeout=1200) or "").strip()
                        except Exception:
                            sample_text = ""
                        try:
                            sample_html = str(first.evaluate("(el) => el.outerHTML")).strip()
                        except Exception:
                            sample_html = ""
                        break
                    except Exception:
                        continue

                fields.append(
                    {
                        "key": key,
                        "label": label,
                        "found": bool(matched_selector),
                        "visible": visible,
                        "selector": matched_selector,
                        "count": matched_count,
                        "sample_text": sample_text[:300],
                        "sample_html": sample_html[:1200],
                    }
                )

            page_title = ""
            body_excerpt = ""
            try:
                page_title = str(page.title() or "")
            except Exception:
                page_title = ""
            try:
                body_excerpt = str(page.locator("body").inner_text(timeout=2500) or "").strip()
            except Exception:
                body_excerpt = ""

            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            debug_lines = [
                f"url={page.url}",
                f"title={page_title}",
                "",
                "body_excerpt:",
                body_excerpt[:2000],
                "",
            ]
            for field in fields:
                debug_lines.extend(
                    [
                        f"[{field['key']}] {field['label']}",
                        f"found={field['found']} visible={field['visible']} count={field['count']} selector={field['selector']}",
                        f"text={field['sample_text']}",
                        "html:",
                        str(field["sample_html"]),
                        "",
                    ]
                )
            artifacts.append(_write_debug_artifact(debug_text_path, debug_lines))

            found_count = sum(1 for field in fields if field.get("found"))
            snapshot["checked_at"] = now_iso()
            snapshot["url"] = str(page.url or "")
            snapshot["page_title"] = page_title
            snapshot["body_excerpt"] = body_excerpt[:2000]
            snapshot["items"] = fields
            snapshot["artifacts"] = list(artifacts)
            snapshot["message"] = f"已探测抖音文章发布页结构，命中 {found_count}/{len(fields)} 个关键区块。"

            browser_state["platform"] = "douyin_creator"
            browser_state["logged_in"] = True
            browser_state["last_checked_at"] = now_iso()
            browser_state["last_opened_url"] = str(page.url or "")
            browser_state["current_page"] = str(page.url or "")
            browser_state["resident_page"] = "article_publish"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            DOUYIN_BROWSER_MANAGER.set_resident_page("article_publish")
            step_logs.append(snapshot["message"])
            step_logs.append(f"当前页面 url={page.url}")

        DOUYIN_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        return browser_state, snapshot, artifacts, step_logs
    except Exception as exc:
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"探测抖音文章发布页结构失败：{exc}"
        step_logs.append(f"探测抖音文章发布页结构失败：{exc}")
        ok, current_url = DOUYIN_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
                snapshot["url"] = current_url
        snapshot["checked_at"] = now_iso()
        snapshot["message"] = str(browser_state["last_error"])
        snapshot["artifacts"] = list(artifacts)
        return browser_state, snapshot, artifacts, step_logs


def fill_douyin_article_from_brief(
    channel: dict[str, object], browser_state: dict[str, object], draft: dict[str, object]
) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_douyin_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "douyin-creator-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"fill-douyin-article-{timestamp}.png"
    debug_text_path = artifact_dir / f"fill-douyin-article-{timestamp}.txt"
    step_logs = [
        f"selector_profile={selector_version}",
        f"brief_id={draft.get('id')}",
    ]
    artifacts: list[str] = []

    try:
        def _run(_context, page):
            current_url = str(page.url or "")
            if "/content/post/article" not in current_url:
                raise RuntimeError("当前不在抖音文章发布页，请先打开“发布文章”页面。")

            title_selector = _pick_selector(page, selector_profile.get("title_input", []), timeout=3000)
            summary_selector = _pick_selector(page, selector_profile.get("summary_input", []), timeout=3000)
            editor_selector = _pick_selector(page, selector_profile.get("content_editor", []), timeout=4000)
            ai_selector = _pick_selector(page, selector_profile.get("ai_illustration", []), timeout=2500)
            if not title_selector or not summary_selector or not editor_selector:
                raise RuntimeError("未定位到标题、摘要或正文输入区。")

            raw_title = str(draft.get("title") or "").strip()
            raw_summary = str(draft.get("summary") or "").strip()
            markdown = str(draft.get("markdown") or "").strip()
            body_markdown = _strip_markdown_title(markdown, raw_title)
            body_text = _plain_text_from_markdown(body_markdown)[:8000]
            title = _build_douyin_title(raw_title)
            summary = _build_douyin_summary(raw_summary, raw_title)

            if not title:
                raise RuntimeError("待填充标题为空。")
            if not body_text:
                raise RuntimeError("待填充正文为空。")

            _fill_locator_value(page, title_selector, title)
            step_logs.append(f"已填充抖音标题 selector={title_selector}")
            if raw_title != title:
                step_logs.append(f"标题已截断至 {len(title)} 字。")

            _fill_locator_value(page, summary_selector, summary)
            step_logs.append(f"已填充抖音摘要 selector={summary_selector}")
            if raw_summary != summary:
                step_logs.append(f"摘要已截断至 {len(summary)} 字。")

            _fill_locator_value(page, editor_selector, body_text, is_rich_text=True)
            step_logs.append(f"已填充抖音正文 selector={editor_selector}")

            if ai_selector:
                ai_locator = page.locator(ai_selector).first
                try:
                    ai_locator.click(timeout=2500)
                except Exception:
                    ai_locator.click(timeout=2500, force=True)
                page.wait_for_timeout(3500)
                step_logs.append(f"已点击 AI 配图 selector={ai_selector}")
            else:
                step_logs.append("未定位到 AI 配图入口。")

            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            artifacts.append(
                _write_debug_artifact(
                    debug_text_path,
                    [
                        f"url={page.url}",
                        f"title_selector={title_selector}",
                        f"summary_selector={summary_selector}",
                        f"editor_selector={editor_selector}",
                        f"ai_selector={ai_selector}",
                        f"title={title}",
                        f"summary={summary}",
                        f"body_length={len(body_text)}",
                    ],
                )
            )
            browser_state["platform"] = "douyin_creator"
            browser_state["logged_in"] = True
            browser_state["last_checked_at"] = now_iso()
            browser_state["last_opened_url"] = str(page.url or "")
            browser_state["current_page"] = str(page.url or "")
            browser_state["resident_page"] = "article_publish"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            DOUYIN_BROWSER_MANAGER.set_resident_page("article_publish")
            step_logs.append(f"当前页面 url={page.url}")

        DOUYIN_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        return browser_state, artifacts, step_logs
    except Exception as exc:
        browser_state.update(DOUYIN_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"填充抖音文章页失败：{exc}"
        step_logs.append(f"填充抖音文章页失败：{exc}")
        ok, current_url = DOUYIN_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            artifacts.append(str(screenshot_path))
            browser_state["last_screenshot"] = str(screenshot_path)
            if current_url:
                browser_state["last_opened_url"] = current_url
                browser_state["current_page"] = current_url
        return browser_state, artifacts, step_logs


def run_browser_action(
    action: str,
    draft: dict[str, object],
    channel: dict[str, object],
    browser_state: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    step_logs = [
        f"selector_profile={selector_version}",
        f"action={action}",
        f"entry_url={entry_url}",
    ]
    artifacts: list[str] = []
    browser_state = dict(browser_state)
    browser_state["is_session_level_error"] = False

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器用户目录不存在或尚未建立登录态。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行浏览器动作：登录态不可用。"]

    artifact_dir = ARTIFACT_ROOT / draft["id"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"{action}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        if action != "sync_wechat_draft":
            def _run_generic(context, page):
                _enforce_single_tab(context, page, step_logs, phase=f"{action}_start", allow_recover=True)
                WECHAT_BROWSER_MANAGER.set_action_state(action, "go_home")
                _return_to_wechat_home(page, entry_url, step_logs)
                if action == "open_preview":
                    editor_url = resolve_editor_url(draft, browser_state, entry_url)
                    page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2200)
                    _enforce_single_tab(context, page, step_logs, phase="open_preview_editor", allow_recover=False)
                    target = _wait_for_wechat_editor_in_current_page_with_retry(page, selector_profile, step_logs)
                    target.wait_for_timeout(1800)
                    preview_selector = _pick_selector(target, selector_profile.get("preview_button", []), timeout=6000)
                    if not preview_selector:
                        raise RuntimeError("未找到“预览”按钮。")
                    target.locator(preview_selector).first.click()
                    target.wait_for_timeout(2500)
                    blockers = detect_editor_blockers(target)
                    if blockers:
                        raise RuntimeError("；".join(blockers))
                    target.screenshot(path=str(screenshot_path), full_page=True)
                    browser_state["last_opened_url"] = target.url
                    browser_state["current_page"] = target.url
                    browser_state["resident_page"] = "editor"
                    WECHAT_BROWSER_MANAGER.set_resident_page("editor")
                    WECHAT_BROWSER_MANAGER.set_action_state(action, "preview_opened")
                    step_logs.append(f"已打开稿件编辑页 URL={target.url}")
                    step_logs.append(f"已点击预览 selector={preview_selector}")
                else:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    browser_state["last_opened_url"] = page.url
                    browser_state["current_page"] = page.url
                    browser_state["resident_page"] = "home"
                    WECHAT_BROWSER_MANAGER.set_resident_page("home")
                    WECHAT_BROWSER_MANAGER.set_action_state(action, "home")
                    step_logs.append(f"已打开页面 {page.url}")
                    if action == "publish" and draft.get("preview_url"):
                        step_logs.append("当前版本不会在无页面校准证据时自动点击最终发布按钮。")
                browser_state["last_error"] = None

            WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run_generic)
            browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
            browser_state["last_screenshot"] = str(screenshot_path)
            artifacts.append(str(screenshot_path))
            return browser_state, artifacts, step_logs

        def _run(context, page):
            session_delta, session_artifacts, _session_logs, recovered_page = _run_session_recovery(
                context, page, entry_url, selector_profile, browser_state, step_logs
            )
            _merge_browser_state_delta(browser_state, session_delta)
            artifacts.extend(session_artifacts)

            upload_delta, upload_artifacts, _upload_logs, landing_page = _run_upload(
                context, recovered_page, draft, channel, entry_url, selector_profile, browser_state, step_logs
            )
            _merge_browser_state_delta(browser_state, upload_delta)
            artifacts.extend(upload_artifacts)

            verify_delta, verify_artifacts, _verify_logs, _final_page = _run_verify(
                context, landing_page, draft, entry_url, selector_profile, browser_state, step_logs, screenshot_path
            )
            _merge_browser_state_delta(browser_state, verify_delta)
            artifacts.extend(verify_artifacts)
            browser_state["last_error"] = None if not browser_state.get("is_session_level_error") else browser_state.get("last_error")

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        if Path(screenshot_path).exists():
            browser_state["last_screenshot"] = str(screenshot_path)
    except Exception as exc:
        ok, current_url = WECHAT_BROWSER_MANAGER.capture_screenshot(screenshot_path)
        if ok:
            browser_state["last_opened_url"] = current_url or entry_url
            browser_state["current_page"] = current_url or entry_url
        else:
            _write_debug_artifact(
                screenshot_path.with_suffix(".txt"),
                [f"action={action}", f"error={exc}", f"entry_url={entry_url}"],
            )
            browser_state["last_opened_url"] = entry_url
            browser_state["current_page"] = entry_url
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = str(exc)
        browser_state["is_session_level_error"] = _browser_session_error_kind(exc, recovery_ok=False)
        browser_state["last_screenshot"] = str(screenshot_path)
        if str(screenshot_path) not in artifacts:
            artifacts.append(str(screenshot_path))
        step_logs.append(f"浏览器动作失败：{exc}")
    return browser_state, artifacts, step_logs
