from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from ..store_base import UTC, now_iso
from .browser_base import (
    ARTIFACT_ROOT,
    _pick_selector,
    _write_debug_artifact,
    ensure_douyin_channel_defaults,
    get_selector_profile,
    normalize_browser_name,
)
from .browser_manager import DOUYIN_BROWSER_MANAGER
from .wechat import _fill_locator_value, _plain_text_from_markdown, _strip_markdown_title


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
    from ..briefing import build_douyin_summary

    return build_douyin_summary(raw_summary, raw_title, limit)


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
    except Exception as exc:
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

__all__ = [
    "_build_douyin_title",
    "_build_douyin_summary",
    "launch_douyin_dashboard",
    "inspect_douyin_session",
    "open_douyin_article_publish",
    "inspect_douyin_article_structure",
    "fill_douyin_article_from_brief",
]
