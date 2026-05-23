from __future__ import annotations

from datetime import datetime
import re
from uuid import uuid4

from ...store.base import UTC
from ..browser_base import ARTIFACT_ROOT, _pick_selector, ensure_channel_defaults, get_selector_profile
from ..browser_manager import WECHAT_BROWSER_MANAGER
from .dom import extract_wechat_appmsg_id, _validate_wechat_page_identity
from .session import _browser_session_error_kind, _enforce_single_tab, _safe_return_home

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

def _scrape_wechat_draft_items_strict(page) -> list[dict[str, str | None]]:
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
                const updatedAtMatch = containerText.match(/(昨天\\s*[0-9]{1,2}:[0-9]{2}|星期[一二三四五六日天]\\s*[0-9]{1,2}:[0-9]{2}|[0-9]{1,2}月[0-9]{1,2}日|[0-9]{4}[-/.][0-9]{1,2}[-/.][0-9]{1,2}|[0-9]{1,2}:[0-9]{2})/);
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
