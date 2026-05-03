from __future__ import annotations

import ctypes
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
import re
import subprocess
from threading import Lock, Thread
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser
from uuid import uuid4


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
            "div.new-creation__menu-item:has-text('文章')",
            "text=文章",
            "a[href*='appmsg']",
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
        "content_manage": [
            "span.weui-desktop-menu__link[title='内容管理']",
            "span.weui-desktop-menu__name:has-text('内容管理')",
            "a:has-text('内容管理')",
            "div:has-text('内容管理')",
            "text=内容管理",
        ],
        "title_input": [
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
            ".ProseMirror",
            ".rich_media_content [contenteditable='true']",
            "[contenteditable='true']",
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
    }
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


def _write_debug_artifact(target: Path, lines: list[str]) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(target)


def _pick_selector(page, selectors: list[str] | str, timeout: int = 2200) -> str | None:
    selector_list = selectors if isinstance(selectors, list) else [selectors]
    for selector in selector_list:
        try:
            page.locator(str(selector)).first.wait_for(timeout=timeout)
            return str(selector)
        except Exception:
            continue
    return None


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

    def ensure_context(self, channel: dict[str, object]):
        signature = self.signature_for(channel)
        if self._context is not None and self.is_alive() and signature == self._channel_signature:
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
        self._page = context.pages[0] if context.pages else None
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
        if self._page is not None:
            try:
                _ = self._page.url
                self._last_action_phase = "page_reused"
                return self._page
            except Exception:
                self._page = None
        page = context.new_page()
        page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.evaluate("() => { document.title = 'AutoNews-微信专用'; }")
        except Exception:
            pass
        self._page = page
        self._resident_page = "home"
        self._last_action_phase = "page_created"
        return page

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
            if self._worker_thread_id == threading.get_ident():
                self._close_runtime_internal()
            else:
                self._last_reset_reason = "with_session_failed"
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


def _plain_text_from_markdown(markdown: str) -> str:
    lines: list[str] = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        if line.startswith(("- ", "* ")):
            line = f"• {line[2:].strip()}"
        lines.append(line)
    text = "\n".join(lines).strip()
    return text[:12000]


def _clamp_author(author: str) -> str:
    compact = author.strip()
    if not compact:
        return ""
    return compact[:8]


def _fill_wechat_editor(page, draft: dict[str, object], channel: dict[str, object], selector_profile: dict[str, list[str] | str], step_logs: list[str]) -> None:
    title_selector = _pick_selector(page, selector_profile.get("title_input", []))
    author_selector = _pick_selector(page, selector_profile.get("author_input", []))
    digest_selector = _pick_selector(page, selector_profile.get("digest_input", []))
    editor_selector = _pick_selector(page, selector_profile.get("editor", []), timeout=4000)
    if not title_selector or not editor_selector:
        raise RuntimeError("未定位到标题框或正文编辑区。")

    title = str(draft.get("title", "")).strip()[:64]
    author = _clamp_author(str(channel.get("author") or ""))
    digest = str(draft.get("summary") or "").strip()[:120]
    body_text = _plain_text_from_markdown(str(draft.get("markdown") or ""))

    page.locator(title_selector).first.fill(title)
    step_logs.append(f"已填充标题 selector={title_selector}")
    if author_selector and author:
        page.locator(author_selector).first.fill(author)
        step_logs.append(f"已填充作者 selector={author_selector}")
    if digest_selector and digest:
        page.locator(digest_selector).first.fill(digest)
        step_logs.append(f"已填充摘要 selector={digest_selector}")
    editor = page.locator(editor_selector).first
    editor.click()
    try:
        editor.fill(body_text)
    except Exception:
        page.evaluate(
            """({ selector, value }) => {
                const node = document.querySelector(selector);
                if (!node) return;
                node.focus();
                node.textContent = value;
                node.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
            }""",
            {"selector": editor_selector, "value": body_text},
        )
    step_logs.append(f"已填充正文 selector={editor_selector}")


def _locate_editor_page(context, fallback_page, timeout_ms: int = 12000):
    deadline = datetime.now(UTC).timestamp() + (timeout_ms / 1000)
    candidate = fallback_page
    while datetime.now(UTC).timestamp() < deadline:
        for page in context.pages:
            if "appmsg" in page.url or "media/appmsg_edit" in page.url:
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
                    if (stableKey) {
                        if (seenStable.has(stableKey)) return;
                        seenStable.add(stableKey);
                    }
                    results.push({
                        title: cleanTitle,
                        url: normalizedUrl,
                        appmsg_id: appmsgId,
                        updated_at: normalize(updatedAt),
                        remote_key: stableKey || `card:${cleanTitle}|${normalize(updatedAt)}|${occurrence}`,
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
    WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "open_editor")
    new_article_selector = _pick_required_selector(
        page,
        selector_profile.get("new_article", []),
        step_logs,
        step_name="pick_new_article_selector",
        timeout=5000,
    )
    page.locator(new_article_selector).first.click()
    page.wait_for_timeout(2500)
    target = _locate_editor_page_with_retry(context, page, selector_profile, step_logs)
    target.wait_for_timeout(2000)
    step_logs.append(f"编辑页 URL={target.url}")
    WECHAT_BROWSER_MANAGER.set_resident_page("editor")
    WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "fill_editor")
    _fill_wechat_editor_with_retry(target, draft, channel, selector_profile, step_logs)

    save_selector = _pick_required_selector(
        target,
        selector_profile.get("save_draft_button", []),
        step_logs,
        step_name="pick_save_draft_selector",
        timeout=6000,
    )

    def _save_draft_once() -> None:
        WECHAT_BROWSER_MANAGER.set_action_state("sync_wechat_draft", "save_draft")
        target.locator(save_selector).first.click()
        target.wait_for_timeout(3500)

    _retry_once("save_draft", step_logs, _save_draft_once)
    step_logs.append(f"已点击保存草稿 selector={save_selector}")

    landing_page = page
    if target != page:
        try:
            target.close()
            step_logs.append("已关闭编辑页，准备返回公众号后台。")
        except Exception:
            step_logs.append("关闭编辑页失败，改为直接复用当前标签返回公众号后台。")
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
    delete_button = row.locator("a.weui-desktop-icon20.weui-desktop-icon-btn").first
    if delete_target.count() > 0:
        try:
            delete_target.hover(timeout=2000)
        except Exception:
            pass
    delete_button.wait_for(timeout=3000)
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
            if not _open_wechat_draft_box(page, selector_profile, step_logs):
                raise RuntimeError("未能进入正式草稿箱页面（/cgi-bin/appmsg?...action=list_card...）。")
            current_page = _context.pages[-1] if _context.pages else page
            current_page.wait_for_timeout(2000)
            if "action=list_card" not in str(current_page.url or ""):
                raise RuntimeError(f"当前页面不是正式草稿箱：{current_page.url}")
            _delete_wechat_draft_in_page(current_page, target, step_logs)
            current_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = current_page.url
            browser_state["current_page"] = current_page.url
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


def _locate_editor_page_with_retry(context, fallback_page, selector_profile: dict[str, list[str] | str], step_logs: list[str]):
    def _locate_once():
        candidate = _locate_editor_page(context, fallback_page)
        if not _validate_wechat_page_identity(candidate, selector_profile, expected="editor"):
            raise RuntimeError(f"未能稳定定位到有效编辑页：{getattr(candidate, 'url', '')}")
        return candidate

    return _retry_once("locate_editor_page", step_logs, _locate_once)


def _scrape_wechat_draft_items_strict(page) -> list[dict[str, str | None]]:
    rows = page.evaluate(
        """() => {
            const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const results = [];
            const seenStable = new Set();
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
                if (stableKey) {
                    if (seenStable.has(stableKey)) return;
                    seenStable.add(stableKey);
                }
                results.push({
                    title: cleanTitle,
                    url: normalizedUrl,
                    appmsg_id: appmsgId,
                    updated_at: normalize(updatedAt),
                    remote_key: stableKey || `card:${cleanTitle}|${normalize(updatedAt)}|${occurrence}`,
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

            return results.filter((item) => item.title || item.url).slice(0, 80);
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
                WECHAT_BROWSER_MANAGER.set_action_state(action, "go_home")
                _return_to_wechat_home(page, entry_url, step_logs)
                if action == "open_preview":
                    editor_url = resolve_editor_url(draft, browser_state, entry_url)
                    page.goto(editor_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(2200)
                    target = _locate_editor_page(context, page)
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
