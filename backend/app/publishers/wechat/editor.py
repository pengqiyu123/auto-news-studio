from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ...store.base import UTC
from ...content.wechat_format import markdown_to_wechat_html
from ..browser_base import (
    ARTIFACT_ROOT,
    _page_url,
    _pick_selector,
    _pick_visible_locator,
    _write_debug_artifact,
    ensure_channel_defaults,
    get_selector_profile,
    now_iso,
)
from ..browser_manager import WECHAT_BROWSER_MANAGER
from .dom import (
    _clamp_author,
    _dump_wechat_editor_dom,
    _plain_text_from_markdown,
    _read_locator_value,
    _strip_markdown_title,
    _validate_wechat_page_identity,
    _write_plain_field,
    _write_rich_html_field,
    extract_wechat_appmsg_id,
)
from .drafts import _open_wechat_draft_box, _scrape_wechat_draft_items_strict
from .session import (
    _browser_session_error_kind,
    _converge_context_to_target,
    _enforce_single_tab,
    _locate_editor_page_with_retry,
    _pick_required_selector,
    _return_to_wechat_home,
    _retry_once,
    _safe_return_home,
    _wait_for_wechat_editor_in_current_page_with_retry,
)

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

def _fill_wechat_editor(
    page,
    draft: dict[str, object],
    channel: dict[str, object],
    selector_profile: dict[str, list[str] | str],
    step_logs: list[str],
    *,
    artifact_dir: Path | None = None,
) -> None:
    try:
        debug_path = ARTIFACT_ROOT / "debug-fill-editor.png"
        page.screenshot(path=str(debug_path), full_page=True)
        for key in ["title_input", "author_input", "digest_input", "editor"]:
            selectors = selector_profile.get(key, [])
            for selector in selectors:
                try:
                    count = page.locator(selector).count()
                    step_logs.append(f"DEBUG {key} selector={selector} count={count}")
                except Exception as exc:
                    step_logs.append(f"DEBUG {key} selector={selector} error={exc}")
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
def _fill_wechat_editor_with_retry(
    page,
    draft: dict[str, object],
    channel: dict[str, object],
    selector_profile: dict[str, list[str] | str],
    step_logs: list[str],
    *,
    artifact_dir: Path | None = None,
) -> None:
    def _fill_once() -> None:
        _fill_wechat_editor(
            page,
            draft,
            channel,
            selector_profile,
            step_logs,
            artifact_dir=artifact_dir,
        )

    _retry_once("fill_wechat_editor", step_logs, _fill_once)
