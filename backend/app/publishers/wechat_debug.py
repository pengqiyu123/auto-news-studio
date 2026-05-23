"""WeChat debug-chain functions: DOM inspection, editor debug, author-only fill, publish-settings test.

These functions are development / diagnostics helpers.  They were previously
loaded via ``_legacy.py`` from the old monolithic ``publishers.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
from .wechat.dom import _clamp_author, _open_wechat_analytics, _read_locator_value, _write_plain_field
from .wechat.editor import _apply_wechat_publish_settings, _ensure_wechat_author_before_publish_settings
from .wechat.session import (
    _browser_session_error_kind,
    _converge_context_to_target,
    _enforce_single_tab,
    _locate_editor_page_with_retry,
    _pick_required_selector,
    _retry_once,
    _safe_return_home,
    _wait_for_wechat_editor_in_current_page,
    _wait_for_wechat_editor_in_current_page_with_retry,
)


UTC = timezone.utc


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
