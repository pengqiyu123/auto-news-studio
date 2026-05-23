from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

from ...store.base import UTC
from ..browser_base import (
    ARTIFACT_ROOT,
    _can_interact_with_page,
    _count_context_pages,
    _is_page_closed,
    _list_live_context_pages,
    _page_url,
    _pick_selector,
    _write_debug_artifact,
    ensure_channel_defaults,
    get_selector_profile,
)
from ..browser_manager import WECHAT_BROWSER_MANAGER
from .dom import _validate_wechat_page_identity

def _retry_once(step_name: str, step_logs: list[str], fn):
    try:
        return fn()
    except Exception as exc:
        step_logs.append(f"{step_name} 首次失败：{exc}；5 秒后重试一次。")
        time.sleep(5)
        return fn()

def _return_to_wechat_home(page, entry_url: str, step_logs: list[str]) -> None:
    page.goto(entry_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    step_logs.append("已返回公众号后台首页。")

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

def _wait_for_wechat_editor_in_current_page_with_retry(page, selector_profile: dict[str, list[str] | str], step_logs: list[str]):
    def _locate_once():
        return _wait_for_wechat_editor_in_current_page(page, selector_profile)

    return _retry_once("wait_current_editor_page", step_logs, _locate_once)

def _locate_editor_page(context, fallback_page, timeout_ms: int = 12000):
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

def _converge_context_to_target(context, target_page, step_logs: list[str], *, phase: str) -> None:
    pages = [page for page in getattr(context, "pages", []) if not _is_page_closed(page)]
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

def _enforce_single_tab(context, page, step_logs: list[str], *, phase: str, allow_recover: bool = False) -> None:
    pages = [candidate for candidate in getattr(context, "pages", []) if not _is_page_closed(candidate)]
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

def launch_wechat_dashboard(channel: dict[str, object], browser_state: dict[str, object]) -> tuple[dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    step_logs = [
        f"browser={channel.get('browser_name')}",
        f"profile={channel.get('browser_profile_path')}",
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
            browser_state["last_checked_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
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
    profile_path = channel.get("browser_profile_path")
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"check-browser-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"
    debug_text_path = artifact_dir / f"check-browser-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.txt"
    step_logs = [
        f"selector_profile={selector_version}",
        f"profile={profile_path}",
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
            browser_state["browser_name"] = channel.get("browser_name")
            browser_state["user_data_dir"] = str(profile_path or "")
            browser_state["logged_in"] = logged_in
            browser_state["last_checked_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
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
    except Exception as exc:
        artifact = _write_debug_artifact(
            Path(debug_text_path),
            [
                "浏览器会话检查失败。",
                f"profile={profile_path}",
                f"entry_url={entry_url}",
                f"error={exc}",
            ],
        )
        artifacts.append(artifact)
        browser_state["logged_in"] = False
        browser_state["last_checked_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
        browser_state["last_screenshot"] = artifact
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"浏览器会话检查失败：{exc}"
        return browser_state, artifacts, step_logs + [f"会话检查失败：{exc}"]

    return browser_state, artifacts, step_logs
