"""WeChat debug-chain functions: DOM inspection, editor debug, author-only fill, publish-settings test.

These functions are development / diagnostics helpers.  They were previously
loaded via ``_legacy.py`` from the old monolithic ``publishers.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .browser_base import (
    ARTIFACT_ROOT,
    _page_url,
    _pick_visible_locator,
    _write_debug_artifact,
    ensure_channel_defaults,
    get_selector_profile,
    now_iso,
)
from .browser_manager import WECHAT_BROWSER_MANAGER
from .wechat.dom import _open_wechat_analytics, _validate_wechat_page_identity
from .wechat.drafts import _match_remote_draft_item, _open_wechat_draft_box, _scrape_wechat_draft_items_strict
from .wechat.editor import (
    _apply_wechat_publish_settings,
    _click_required_selector_once,
    _ensure_wechat_ai_cover,
    _ensure_wechat_author_before_publish_settings,
    _select_collection_ai_news,
    _select_claim_source_personal,
)
from .wechat.session import (
    _browser_session_error_kind,
    _converge_context_to_target,
    _enforce_single_tab,
    _locate_editor_page_with_retry,
    _pick_required_selector,
    _safe_return_home,
    _wait_for_wechat_editor_in_current_page_with_retry,
)

UTC = UTC


def _resolve_current_editor_page(context, page, selector_profile: dict[str, list[str] | str], step_logs: list[str], *, phase: str):
    editor_page = _locate_editor_page_with_retry(context, page, selector_profile, step_logs)
    if editor_page is not page:
        step_logs.append(f"检测到当前编辑页接管 URL={_page_url(editor_page)}")
    try:
        _converge_context_to_target(context, editor_page, step_logs, phase=phase)
    except Exception as exc:
        if not _validate_wechat_page_identity(editor_page, selector_profile, expected="editor"):
            raise
        step_logs.append(f"编辑页收敛未完成 phase={phase} error={exc}；目标编辑页已确认，继续。")
    try:
        WECHAT_BROWSER_MANAGER._page = editor_page
    except Exception:
        pass
    WECHAT_BROWSER_MANAGER.set_resident_page("editor")
    return editor_page


def _click_remote_draft_edit_button(page, title: str, step_logs: list[str]) -> dict[str, object]:
    compact_title = " ".join(str(title or "").replace("\xa0", " ").split()).strip().lower()
    if not compact_title:
        raise RuntimeError("缺少目标草稿标题。")

    def title_matches(left: str, right: str) -> bool:
        if not left or not right:
            return False
        left = left.replace("：", ":")
        right = right.replace("：", ":")
        if left == right:
            return True
        shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
        return len(shorter) >= 14 and (longer.startswith(shorter) or shorter in longer)

    rows = page.locator(".publish_card_container, .weui-desktop-card.weui-desktop-publish, .weui-desktop-media__list-col .weui-desktop-card")
    row_count = rows.count()
    for index in range(row_count):
        row = rows.nth(index)
        try:
            row_text = " ".join(str(row.inner_text(timeout=2000) or "").replace("\xa0", " ").split()).strip()
        except Exception:
            row_text = ""
        if not title_matches(row_text.lower(), compact_title):
            continue
        try:
            row.hover(timeout=3000)
        except Exception:
            pass
        page.wait_for_timeout(500)
        buttons = row.locator(
            ".weui-desktop-card__action .weui-desktop-tooltip__wrp.weui-desktop-link a.weui-desktop-icon20.weui-desktop-icon-btn"
        )
        button_count = buttons.count()
        if button_count < 2:
            buttons = row.locator(".weui-desktop-card__action a.weui-desktop-icon-btn")
            button_count = buttons.count()
        if button_count < 2:
            raise RuntimeError(f"目标草稿已找到，但未找到编辑按钮：buttons={button_count}")
        edit_button = buttons.nth(1)
        try:
            edit_button.click(timeout=5000)
        except Exception as exc:
            step_logs.append(f"编辑按钮普通点击失败：{exc}；改用 force")
            edit_button.click(timeout=3000, force=True)
        step_logs.append(f"已点击目标草稿编辑按钮 title={row_text[:80]}")
        return {"ok": True, "reason": "clicked", "title": row_text}
    raise RuntimeError(f"草稿箱中未找到目标草稿卡片：{title}")


# ---------------------------------------------------------------------------
# 1. inspect_wechat_analytics_dom
# ---------------------------------------------------------------------------

def inspect_wechat_analytics_dom(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"inspect-wechat-analytics-{timestamp}.png"
    debug_text_path = artifact_dir / f"inspect-wechat-analytics-{timestamp}.txt"
    html_path = artifact_dir / f"inspect-wechat-analytics-{timestamp}.html"
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
        "action=inspect_wechat_analytics_dom",
    ]
    artifacts: list[str] = []

    try:
        def _run(_context, page):
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="inspect_analytics_go_home")
            if not _open_wechat_analytics(page, selector_profile, step_logs):
                raise RuntimeError("未能进入微信数据分析页面。")

            field_specs = [
                ("menu_analysis", "数据分析菜单", selector_profile.get("analytics", [])),
                ("publish_card", "发表记录卡片", [".weui-desktop-mass-media", ".publish_hover_content", ".weui-desktop-mass-media__data-list"]),
                ("read_metric", "阅读人数", [".appmsg-view .weui-desktop-mass-media__data__inner", ".weui-desktop-mass-media__data.appmsg-view"]),
                ("like_metric", "点赞人数", [".appmsg-like .weui-desktop-mass-media__data__inner", ".weui-desktop-mass-media__data.appmsg-like"]),
                ("share_metric", "分享人数", [".appmsg-share .weui-desktop-mass-media__data__inner", ".weui-desktop-mass-media__data.appmsg-share"]),
                ("recommend_metric", "推荐人数", [".appmsg-haokan .weui-desktop-mass-media__data__inner", ".weui-desktop-mass-media__data.appmsg-haokan"]),
                ("comment_metric", "留言条数", [".appmsg-comment .weui-desktop-mass-media__data__inner", ".weui-desktop-mass-media__data.appmsg-comment"]),
                ("underline_metric", "划线人数", [".appmsg-underline .weui-desktop-mass-media__data__inner", ".weui-desktop-mass-media__data.appmsg-underline"]),
                ("reward_metric", "赞赏金额", [".appmsg-reward .weui-desktop-mass-media__data__inner", ".weui-desktop-mass-media__data.appmsg-reward"]),
                ("forward_metric", "被转载次数", [".appmsg-forward .weui-desktop-mass-media__data__inner", ".weui-desktop-mass-media__data.appmsg-forward"]),
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
                step_logs.append(f"导出数据分析页 HTML 失败：{exc}")

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
            snapshot["message"] = f"已导出微信数据分析页 DOM，命中 {sum(1 for field in fields if field.get('found'))}/{len(fields)} 个关键区块。"

            browser_state["last_opened_url"] = str(page.url or "")
            browser_state["current_page"] = str(page.url or "")
            browser_state["resident_page"] = "analytics"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            WECHAT_BROWSER_MANAGER.set_resident_page("analytics")
            step_logs.append(str(snapshot["message"]))

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, snapshot, artifacts, step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"导出微信数据分析页 DOM 失败：{exc}"
        step_logs.append(f"导出微信数据分析页 DOM 失败：{exc}")
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


def open_wechat_remote_draft_by_title(
    channel: dict[str, object],
    browser_state: dict[str, object],
    title: str,
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"open-remote-draft-{timestamp}.png"
    snapshot: dict[str, object] = {
        "checked_at": now_iso(),
        "url": "",
        "title": title,
        "message": "",
        "artifacts": [],
        "step_logs": [],
        "remote_item": None,
    }
    step_logs = [
        f"selector_profile={selector_version}",
        "action=open_wechat_remote_draft_by_title",
        f"entry_url={entry_url}",
        f"title={title}",
    ]
    artifacts: list[str] = []

    try:
        def _run(context, page):
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="open_remote_draft_go_home")
            if not _validate_wechat_page_identity(page, selector_profile, expected="home"):
                raise RuntimeError("首页未识别。")
            if not _open_wechat_draft_box(page, selector_profile, step_logs):
                raise RuntimeError("未能进入正式草稿箱页面。")
            page.wait_for_timeout(1800)
            if not _validate_wechat_page_identity(page, selector_profile, expected="draft_box"):
                raise RuntimeError(f"当前页面不是正式草稿箱：{page.url}")
            remote_items = _scrape_wechat_draft_items_strict(page)
            remote_item = _match_remote_draft_item(remote_items, remote_title=title)
            if not remote_item:
                raise RuntimeError(f"草稿箱中未找到目标草稿：{title}")
            snapshot["remote_item"] = remote_item
            _click_remote_draft_edit_button(page, str(remote_item.get("title") or title), step_logs)
            page.wait_for_timeout(2800)
            target = _locate_editor_page_with_retry(context, page, selector_profile, step_logs)
            if target is not page:
                step_logs.append(f"检测到编辑页接管 URL={_page_url(target)}")
                try:
                    _converge_context_to_target(context, target, step_logs, phase="open_remote_draft_editor")
                except Exception as exc:
                    if not _validate_wechat_page_identity(target, selector_profile, expected="editor"):
                        raise
                    step_logs.append(f"编辑页收敛未完成：{exc}；目标编辑页已确认，继续。")
                try:
                    WECHAT_BROWSER_MANAGER._page = target
                except Exception:
                    pass
            target.wait_for_timeout(1200)
            target.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            snapshot["url"] = str(target.url or "")
            snapshot["message"] = "已打开指定远端草稿编辑页。"
            snapshot["artifacts"] = list(artifacts)
            snapshot["step_logs"] = list(step_logs)
            browser_state["last_opened_url"] = str(target.url or "")
            browser_state["current_page"] = str(target.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            WECHAT_BROWSER_MANAGER.set_resident_page("editor")

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, snapshot, artifacts, step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"打开远端草稿失败：{exc}"
        step_logs.append(str(browser_state["last_error"]))
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
        snapshot["step_logs"] = list(step_logs)
        return browser_state, snapshot, artifacts, step_logs


def test_wechat_cover_only(
    channel: dict[str, object],
    browser_state: dict[str, object],
    title: str,
    summary: str = "",
    markdown: str = "",
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    selector_profile = get_selector_profile(selector_version)
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"test-wechat-cover-{timestamp}.png"
    snapshot: dict[str, object] = {
        "checked_at": now_iso(),
        "url": "",
        "message": "",
        "artifacts": [],
        "step_logs": [],
    }
    step_logs = [
        f"selector_profile={selector_version}",
        "action=test_wechat_cover_only",
        f"title={title}",
    ]
    artifacts: list[str] = []

    try:
        def _run(_context, page):
            target = _resolve_current_editor_page(_context, page, selector_profile, step_logs, phase="cover_only_editor_ready")
            _ensure_wechat_ai_cover(
                target,
                selector_profile,
                {
                    "title": title,
                    "summary": summary,
                    "markdown": markdown or f"# {title}\n\n{summary}",
                },
                step_logs,
            )
            target.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            snapshot["url"] = str(target.url or "")
            snapshot["message"] = "封面流程测试完成。"
            snapshot["artifacts"] = list(artifacts)
            snapshot["step_logs"] = list(step_logs)
            browser_state["last_opened_url"] = str(target.url or "")
            browser_state["current_page"] = str(target.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None
            WECHAT_BROWSER_MANAGER.set_resident_page("editor")

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, snapshot, artifacts, step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"封面流程测试失败：{exc}"
        step_logs.append(str(browser_state["last_error"]))
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
        snapshot["step_logs"] = list(step_logs)
        return browser_state, snapshot, artifacts, step_logs


# ---------------------------------------------------------------------------
# 2. inspect_wechat_editor_dom
# ---------------------------------------------------------------------------

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
            page = _locate_editor_page_with_retry(_context, page, selector_profile, step_logs)
            if page is not WECHAT_BROWSER_MANAGER._page:
                try:
                    _converge_context_to_target(_context, page, step_logs, phase="inspect_editor_dom_targeted")
                except Exception as exc:
                    if not _validate_wechat_page_identity(page, selector_profile, expected="editor"):
                        raise
                    step_logs.append(f"编辑页收敛未完成：{exc}；目标编辑页已确认，继续。")
                try:
                    WECHAT_BROWSER_MANAGER._page = page
                except Exception:
                    pass

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


# ---------------------------------------------------------------------------
# 3. open_wechat_editor_debug
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 4. fill_wechat_author_only
# ---------------------------------------------------------------------------

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
            editor_page = _resolve_current_editor_page(context, page, selector_profile, step_logs, phase="author_only_editor_ready")
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


# ---------------------------------------------------------------------------
# 5. test_wechat_publish_settings_only
# ---------------------------------------------------------------------------

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
            editor_page = _resolve_current_editor_page(context, page, selector_profile, step_logs, phase="settings_only_editor_ready")
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


# ---------------------------------------------------------------------------
# 6. inspect_wechat_publish_settings_dom
# ---------------------------------------------------------------------------
# Selector validation for collection tags (合集) and claim source (创作来源)
# on the WeChat article editor page.  This is a read-only diagnostic — it
# probes the DOM without clicking anything.

def inspect_wechat_publish_settings_dom(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"inspect-publish-settings-{timestamp}.png"
    html_path = artifact_dir / f"inspect-publish-settings-{timestamp}.html"
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
        "action=inspect_wechat_publish_settings_dom",
    ]
    artifacts: list[str] = []

    try:
        def _run(_context, page):
            selector_profile = get_selector_profile(selector_version)
            page = _resolve_current_editor_page(_context, page, selector_profile, step_logs, phase="inspect_publish_settings_dom_ready")

            # Selector candidates to probe, grouped by semantic purpose.
            # Multiple candidates per group increase the chance of a match
            # across different WeChat MP layout revisions.
            field_specs = [
                # ── 合集 checkbox area ──
                ("collection_checkbox", "合集 checkbox", [
                    "input.js_article_tags",
                    "#js_article_tags_area input.frm_checkbox",
                    "#js_article_tags_area .frm_checkbox_label",
                ]),
                # ── 合集 label (clickable area showing "未添加") ──
                ("collection_label", "合集标签区域", [
                    "div.js_article_tags_label",
                    "#js_article_tags_area .allow_click_opr",
                    "#js_article_tags_area .js_article_tags_content",
                    "#js_article_tags_area .lbl_content_desc",
                ]),
                # ── 合集 whole area ──
                ("collection_area", "合集区域容器", [
                    "#js_article_tags_area",
                    "div#js_article_tags_area",
                ]),
                # ── 合集 dropdown list (usually hidden, shown after click) ──
                ("collection_dropdown", "合集下拉列表", [
                    "div.select-opts-con",
                    ".select-opts-con ul.select-opts-ul",
                    "ul.select-opts-ul",
                ]),
                # ── 合集 specific item "AI新闻" ──
                ("collection_item_ai_news", "合集选项「AI新闻」", [
                    "li.select-opt-li:has-text('AI新闻')",
                    ".select-opt-li:has-text('AI新闻')",
                    "li:has-text('AI新闻')",
                ]),
                # ── 创作来源 checkbox ──
                ("claim_source_checkbox", "创作来源 checkbox", [
                    "input.js_claim_source",
                    ".js_claim_source",
                ]),
                # ── 创作来源 label (clickable area showing "未添加") ──
                ("claim_source_label", "创作来源标签区域", [
                    "label.claim_source_label_wrapper",
                    "div.js_claim_source_desc",
                    "div.allow_click_opr.js_claim_source_desc",
                ]),
                # ── 创作来源 whole area ──
                ("claim_source_area", "创作来源区域容器", [
                    "label.claim_source_label_wrapper",
                ]),
                # ── 创作来源 radio "个人观点，仅供参考" ──
                ("claim_source_option_personal", "创作来源选项「个人观点」", [
                    "input.weui-desktop-form__radio[value='4']",
                    ".weui-desktop-form__check-label:has-text('个人观点')",
                    "label.weui-desktop-form__check-label:has-text('个人观点，仅供参考')",
                ]),
                # ── 通用确认按钮 (合集/创作来源弹窗) ──
                ("confirm_button_primary", "确认按钮(蓝色)", [
                    "button.weui-desktop-btn.weui-desktop-btn_primary",
                    ".weui-desktop-btn_wrp button.weui-desktop-btn_primary",
                    "button.weui-desktop-btn_primary:has-text('确认')",
                    "button.weui-desktop-btn_primary:has-text('确定')",
                ]),
            ]

            fields: list[dict[str, object]] = []
            for key, label, selectors in field_specs:
                matched_selector = None
                matched_count = 0
                visible = False
                sample_text = ""
                sample_html = ""
                for selector in selectors:
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
                fields.append({
                    "key": key,
                    "label": label,
                    "found": bool(matched_selector),
                    "visible": visible,
                    "selector": matched_selector,
                    "count": matched_count,
                    "sample_text": sample_text[:500],
                    "sample_html": sample_html[:3000],
                })

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

            # Dump full HTML for offline inspection.
            try:
                html_content = str(page.content() or "")
                html_path.write_text(html_content, encoding="utf-8")
                artifacts.append(str(html_path))
            except Exception as exc:
                step_logs.append(f"导出发布设置页 HTML 失败：{exc}")

            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))

            # Build debug text report.
            debug_text_path = artifact_dir / f"inspect-publish-settings-{timestamp}.txt"
            debug_lines = [
                f"url={page.url}",
                f"title={page_title}",
                "",
                "body_excerpt:",
                body_excerpt[:3000],
                "",
            ]
            for field in fields:
                debug_lines.extend([
                    f"[{field['key']}] {field['label']}",
                    f"found={field['found']} visible={field['visible']} count={field['count']} selector={field['selector']}",
                    f"text={field['sample_text']}",
                    "html:",
                    str(field["sample_html"]),
                    "",
                ])
            _write_debug_artifact(debug_text_path, debug_lines)
            artifacts.append(str(debug_text_path))

            matched_count_total = sum(1 for f in fields if f.get("found"))
            snapshot["checked_at"] = now_iso()
            snapshot["url"] = str(page.url or "")
            snapshot["page_title"] = page_title
            snapshot["body_excerpt"] = body_excerpt[:3000]
            snapshot["items"] = fields
            snapshot["artifacts"] = list(artifacts)
            snapshot["message"] = f"已导出发布设置区域 DOM，命中 {matched_count_total}/{len(fields)} 个选择器。"

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
        browser_state["last_error"] = f"导出发布设置区域 DOM 失败：{exc}"
        step_logs.append(f"导出发布设置区域 DOM 失败：{exc}")
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


# ---------------------------------------------------------------------------
# 7. test_collection_click
# ---------------------------------------------------------------------------
# One-off diagnostic: click 合集 "未添加", then the picker input, then inspect
# dropdown items. This mirrors the production path closely without saving.

def test_collection_click(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"test-collection-click-{timestamp}.png"
    snapshot: dict[str, object] = {
        "checked_at": now_iso(),
        "url": "",
        "message": "",
        "dropdown_visible": False,
        "dropdown_items": [],
        "artifacts": [],
    }
    step_logs = [
        f"selector_profile={selector_version}",
        "action=test_collection_click",
    ]
    artifacts: list[str] = []

    try:
        def _run(context, page):
            selector_profile = get_selector_profile(selector_version)
            page = _resolve_current_editor_page(context, page, selector_profile, step_logs, phase="test_collection_click_editor_ready")
            step_logs.append(f"已锁定编辑器 URL={page.url}")

            _select_collection_ai_news(
                page,
                selector_profile,
                selector_profile.get("option_confirm_button", []),
                step_logs,
            )

            dropdown = page.locator("div.select-opts-con")
            dropdown_visible = False
            try:
                dropdown.first.wait_for(state="visible", timeout=1200)
                dropdown_visible = True
                display_val = str(dropdown.first.evaluate("el => el.style.display") or "")
                step_logs.append(f"下拉列表仍可见 display={display_val}")
            except Exception as e:
                step_logs.append(f"下拉列表当前不可见: {e}")

            items: list[str] = []
            if dropdown_visible:
                item_locators = page.locator("li.select-opt-li")
                item_count = item_locators.count()
                step_logs.append(f"下拉选项数量: {item_count}")
                for i in range(item_count):
                    try:
                        text = str(item_locators.nth(i).inner_text(timeout=2000) or "").strip()
                        items.append(text)
                        step_logs.append(f"  选项[{i}]={text}")
                    except Exception as e:
                        step_logs.append(f"  选项[{i}] 读取失败: {e}")
            else:
                area = page.locator("#js_article_tags_area")
                if area.count() > 0:
                    area_html = str(area.first.evaluate("el => el.outerHTML") or "")
                    step_logs.append(f"合集区域HTML: {area_html[:2000]}")

            selected_text = ""
            try:
                selected_text = str(page.locator("#js_article_tags_area .js_article_tags_content").first.inner_text(timeout=1500) or "").strip()
            except Exception:
                selected_text = ""
            snapshot["selected_text"] = selected_text
            step_logs.append(f"合集回读={selected_text}")

            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))

            snapshot["checked_at"] = now_iso()
            snapshot["url"] = str(page.url or "")
            snapshot["message"] = f"合集点击测试完成，下拉{'已出现' if dropdown_visible else '未出现'}"
            snapshot["dropdown_visible"] = dropdown_visible
            snapshot["dropdown_items"] = items
            snapshot["artifacts"] = list(artifacts)
            snapshot["step_logs"] = list(step_logs)

            browser_state["last_opened_url"] = str(page.url or "")
            browser_state["current_page"] = str(page.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, snapshot, artifacts, step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"合集点击测试失败：{exc}"
        step_logs.append(f"合集点击测试失败：{exc}")
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
        snapshot["step_logs"] = list(step_logs)
        return browser_state, snapshot, artifacts, step_logs


# ---------------------------------------------------------------------------
# 8. test_claim_source_click
# ---------------------------------------------------------------------------
# One-off diagnostic: click 创作来源, choose "个人观点，仅供参考", confirm, then
# read back the selected text. This mirrors production without saving.

def test_claim_source_click(
    channel: dict[str, object], browser_state: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"test-claim-source-click-{timestamp}.png"
    snapshot: dict[str, object] = {
        "checked_at": now_iso(),
        "url": "",
        "message": "",
        "selected_text": "",
        "default_text": "",
        "area_text": "",
        "artifacts": [],
    }
    step_logs = [
        f"selector_profile={selector_version}",
        "action=test_claim_source_click",
    ]
    artifacts: list[str] = []

    try:
        def _run(context, page):
            selector_profile = get_selector_profile(selector_version)
            page = _resolve_current_editor_page(context, page, selector_profile, step_logs, phase="test_claim_source_click_editor_ready")
            step_logs.append(f"已锁定编辑器 URL={page.url}")

            _select_claim_source_personal(
                page,
                selector_profile,
                selector_profile.get("option_confirm_button", []),
                step_logs,
            )

            readback = page.evaluate(
                """() => {
                    const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                    const area = document.querySelector("#js_claim_source_area, label.claim_source_label_wrapper");
                    return {
                        selectedText: normalize(area?.querySelector(".js_claim_source_selected")?.textContent),
                        defaultText: normalize(area?.querySelector(".lbl_content_desc_default")?.textContent),
                        areaText: normalize(area?.textContent),
                        areaHtml: String(area?.outerHTML || ""),
                    };
                }"""
            )
            if not isinstance(readback, dict):
                readback = {}
            selected_text = str(readback.get("selectedText") or "").strip()
            default_text = str(readback.get("defaultText") or "").strip()
            area_text = str(readback.get("areaText") or "").strip()
            area_html = str(readback.get("areaHtml") or "")
            snapshot["selected_text"] = selected_text
            snapshot["default_text"] = default_text
            snapshot["area_text"] = area_text
            step_logs.append(f"创作来源回读={selected_text or area_text}")
            step_logs.append(f"创作来源区域HTML: {area_html[:2000]}")

            page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))

            snapshot["checked_at"] = now_iso()
            snapshot["url"] = str(page.url or "")
            snapshot["message"] = "创作来源点击测试完成"
            snapshot["artifacts"] = list(artifacts)
            snapshot["step_logs"] = list(step_logs)

            browser_state["last_opened_url"] = str(page.url or "")
            browser_state["current_page"] = str(page.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, snapshot, artifacts, step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"创作来源点击测试失败：{exc}"
        step_logs.append(f"创作来源点击测试失败：{exc}")
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
        snapshot["step_logs"] = list(step_logs)
        return browser_state, snapshot, artifacts, step_logs


# ---------------------------------------------------------------------------
# 9. eval_wechat_editor_js  (通用 JS 执行端点 - 一次重启永久解决调试问题)
# ---------------------------------------------------------------------------
# Accepts arbitrary JavaScript and runs it on the current editor page via
# page.evaluate.  Returns whatever the script returns (must be JSON-serializable).
# This avoids the need to restart the backend every time we want to test a
# new DOM interaction.

def eval_wechat_editor_js(
    channel: dict[str, object],
    browser_state: dict[str, object],
    script: str,
) -> tuple[dict[str, object], dict[str, object], list[str], list[str]]:
    channel = ensure_channel_defaults(channel)
    browser_state = dict(browser_state)
    artifact_dir = ARTIFACT_ROOT / "session"
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    screenshot_path = artifact_dir / f"eval-js-{timestamp}.png"
    snapshot: dict[str, object] = {
        "checked_at": now_iso(),
        "url": "",
        "ok": False,
        "result": None,
        "error": "",
        "artifacts": [],
    }
    step_logs = [
        "action=eval_wechat_editor_js",
    ]
    artifacts: list[str] = []

    try:
        def _run(context, page):
            selector_profile = get_selector_profile(str(channel.get("selectors_version", "wechat-mp-v1")))
            page = _resolve_current_editor_page(context, page, selector_profile, step_logs, phase="eval_js_editor_ready")
            snapshot["url"] = str(page.url or "")
            step_logs.append(f"已锁定编辑器 URL={page.url}")
            step_logs.append(f"准备执行 JS, 长度={len(script)}")

            result = page.evaluate(script)
            snapshot["result"] = result
            snapshot["ok"] = True
            step_logs.append("JS 执行完成")

            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                artifacts.append(str(screenshot_path))
            except Exception as e:
                step_logs.append(f"截图失败: {e}")

            snapshot["checked_at"] = now_iso()
            snapshot["artifacts"] = list(artifacts)
            snapshot["step_logs"] = list(step_logs)

            browser_state["last_opened_url"] = str(page.url or "")
            browser_state["current_page"] = str(page.url or "")
            browser_state["resident_page"] = "editor"
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["last_error"] = None

        WECHAT_BROWSER_MANAGER.with_session(channel, restore_window=True, action_fn=_run)
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        return browser_state, snapshot, artifacts, step_logs
    except Exception as exc:
        browser_state.update(WECHAT_BROWSER_MANAGER.manager_state())
        browser_state["last_error"] = f"JS 执行失败：{exc}"
        step_logs.append(f"JS 执行失败：{exc}")
        snapshot["error"] = str(exc)
        snapshot["checked_at"] = now_iso()
        snapshot["artifacts"] = list(artifacts)
        snapshot["step_logs"] = list(step_logs)
        return browser_state, snapshot, artifacts, step_logs
