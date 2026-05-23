from __future__ import annotations

import ctypes
from pathlib import Path
from queue import Queue
import threading
from threading import Lock, Thread

from .browser_base import (
    _can_interact_with_page,
    _is_page_closed,
    _list_live_context_pages,
    browser_channel_name,
    ensure_channel_defaults,
    resolve_profile_path,
    DEFAULT_BROWSER_LOCK_TIMEOUT_SECONDS,
)

try:
    USER32 = ctypes.windll.user32
except Exception:  # pragma: no cover - non-Windows safety
    USER32 = None


# ---------------------------------------------------------------------------
# Win32 window helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# WechatBrowserManager
# ---------------------------------------------------------------------------

class WechatBrowserManager:
    """Thread-safe singleton manager for a persistent Playwright browser context."""

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

    # -- lifecycle -----------------------------------------------------------

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

    # -- status ---------------------------------------------------------------

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

    # -- context / page management -------------------------------------------

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

    # -- window management ---------------------------------------------------

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

    # -- state setters -------------------------------------------------------

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

    # -- session entry point -------------------------------------------------

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


# ---------------------------------------------------------------------------
# Singleton instances
# ---------------------------------------------------------------------------

WECHAT_BROWSER_MANAGER = WechatBrowserManager()
DOUYIN_BROWSER_MANAGER = WechatBrowserManager()
