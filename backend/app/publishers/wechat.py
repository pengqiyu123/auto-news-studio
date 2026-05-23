from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from ..wechat_format import markdown_to_plain_text, markdown_to_wechat_html, strip_markdown_title
from ..store_base import UTC
from ._legacy import legacy_publishers
from .browser_base import (
    ARTIFACT_ROOT,
    WECHAT_BROWSER_MANAGER,
    _can_interact_with_page,
    _count_context_pages,
    _is_page_closed,
    _list_live_context_pages,
    _page_url,
    _pick_selector,
    _pick_visible_locator,
    _write_debug_artifact,
    ensure_channel_defaults,
    get_selector_profile,
)


def _plain_text_from_markdown(markdown: str) -> str:
    return markdown_to_plain_text(markdown, limit=12000)


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

    strategies: list[tuple[str, object]] = [
        ("dom_paragraphs", _set_dom_paragraphs),
        ("exec_command_insert", _exec_command_insert),
        ("clipboard_paste", lambda: _clipboard_paste_into_element(page, selector, value)),
    ]

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


def _extract_wechat_analytics_overview(page) -> dict[str, object]:
    result = page.evaluate(
        """() => {
            const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
            const parseNum = (value) => {
                const text = normalize(value);
                const digits = text.replace(/[^0-9]/g, "");
                const parsed = parseInt(digits || "0", 10);
                return Number.isFinite(parsed) ? parsed : 0;
            };

            const findMetricByLabel = (label) => {
                const nodes = Array.from(document.querySelectorAll("body *"));
                for (const node of nodes) {
                    const text = normalize(node.textContent || "");
                    if (text !== label) continue;
                    const container = node.closest('.channel-session-stat') || node.parentElement || node;
                    const candidateTexts = [
                        normalize(container.querySelector("strong")?.textContent || ""),
                        normalize(container.parentElement?.querySelector("strong")?.textContent || ""),
                        normalize(node.previousElementSibling?.textContent || ""),
                        normalize(node.nextElementSibling?.textContent || ""),
                    ].filter(Boolean);
                    for (const candidate of candidateTexts) {
                        if (/^[0-9,]+$/.test(candidate.replace(/\\s+/g, ""))) {
                            return parseNum(candidate);
                        }
                    }
                }
                return 0;
            };

            const bodyText = normalize(document.body?.innerText || "");
            const lines = bodyText.split(/\\n+/).map((line) => normalize(line)).filter(Boolean);
            const windowLine = lines.find((line) => line.startsWith("数据统计时间"));
            const windowMatch = windowLine ? windowLine.match(/数据统计时间[:：]\\s*(.+)$/) : null;
            const accountImg = document.querySelector('.weui-desktop-account__img');
            const avatarUrl = accountImg ? (accountImg.getAttribute('src') || '') : '';
            const accountName = normalize(document.querySelector('.weui-desktop_name')?.textContent || '');
            const originalCountEl = document.querySelector('.original_cnt span');
            const originalCount = parseNum(originalCountEl?.textContent || '0');
            return {
                total_users: findMetricByLabel("总用户数"),
                yesterday_reads: findMetricByLabel("昨日阅读(人)"),
                yesterday_shares: findMetricByLabel("昨日分享(人)"),
                yesterday_new_follows: findMetricByLabel("昨日新增关注(人)"),
                stats_window_label: windowMatch ? normalize(windowMatch[1]) : "",
                fetched_at: new Date().toISOString(),
                avatar_url: avatarUrl,
                account_name: accountName,
                original_count: originalCount,
            };
        }"""
    )
    if not isinstance(result, dict):
        return {
            "total_users": 0,
            "yesterday_reads": 0,
            "yesterday_shares": 0,
            "yesterday_new_follows": 0,
            "stats_window_label": "",
            "fetched_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
    result["fetched_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    return result


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


inspect_wechat_editor_dom = legacy_publishers.inspect_wechat_editor_dom
inspect_wechat_analytics_dom = legacy_publishers.inspect_wechat_analytics_dom


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

            const extractThumbnail = (container) => {
                if (!container) return '';
                const thumb = container.querySelector('.weui-desktop-mass-appmsg__thumb');
                if (!thumb) return '';
                const bg = thumb.style?.backgroundImage || '';
                const m = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
                return m ? absolutize(m[1]) : '';
            };

            const extractMetrics = (container) => {
                const zero = { read_count: 0, like_count: 0, share_count: 0, recommend_count: 0, comment_count: 0, highlight_count: 0, tip_amount: '0.00', reprint_count: 0 };
                if (!container) return zero;
                const dataList = container.querySelector('.weui-desktop-mass-media__data-list');
                if (!dataList) return zero;
                const parseNum = (el) => { const t = normalize(el?.textContent || '0'); const n = parseInt(t.replace(/[^0-9]/g, ''), 10); return isNaN(n) ? 0 : n; };
                const parseMoney = (el) => { const t = normalize(el?.textContent || '0'); return t.replace(/[^0-9.]/g, '') || '0.00'; };
                return {
                    read_count: parseNum(dataList.querySelector('.appmsg-view .weui-desktop-mass-media__data__inner')),
                    like_count: parseNum(dataList.querySelector('.appmsg-like .weui-desktop-mass-media__data__inner')),
                    share_count: parseNum(dataList.querySelector('.appmsg-share .weui-desktop-mass-media__data__inner')),
                    recommend_count: parseNum(dataList.querySelector('.appmsg-haokan .weui-desktop-mass-media__data__inner')),
                    comment_count: parseNum(dataList.querySelector('.appmsg-comment .weui-desktop-mass-media__data__inner')),
                    highlight_count: parseNum(dataList.querySelector('.appmsg-underline .weui-desktop-mass-media__data__inner')),
                    tip_amount: parseMoney(dataList.querySelector('.appmsg-reward .weui-desktop-mass-media__data__inner')),
                    reprint_count: parseNum(dataList.querySelector('.appmsg-forward .weui-desktop-mass-media__data__inner')),
                };
            };

            const pushItem = (title, url, publishedAt, occurrence, metricsContainer) => {
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
                const metrics = extractMetrics(metricsContainer || container);
                results.push({
                    title: cleanTitle,
                    url: normalizedUrl,
                    appmsg_id: appmsgId,
                    published_at: normalize(publishedAt),
                    remote_key: stableKey,
                    read_count: metrics.read_count,
                    like_count: metrics.like_count,
                    share_count: metrics.share_count,
                    recommend_count: metrics.recommend_count,
                    comment_count: metrics.comment_count,
                    highlight_count: metrics.highlight_count,
                    tip_amount: metrics.tip_amount,
                    reprint_count: metrics.reprint_count,
                    thumbnail: extractThumbnail(container),
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
                pushItem(title, href, publishedAt, index, container);
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
                    pushItem(title, href, publishedAt, index, container);
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
                "read_count": int(row.get("read_count") or 0),
                "like_count": int(row.get("like_count") or 0),
                "share_count": int(row.get("share_count") or 0),
                "recommend_count": int(row.get("recommend_count") or 0),
                "comment_count": int(row.get("comment_count") or 0),
                "highlight_count": int(row.get("highlight_count") or 0),
                "tip_amount": str(row.get("tip_amount") or "0.00"),
                "reprint_count": int(row.get("reprint_count") or 0),
                "thumbnail": str(row.get("thumbnail") or "").strip(),
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
            all_items: list[dict[str, str | None]] = []
            seen_keys: set[str] = set()
            for page_num in range(1, 11):
                current_page.wait_for_timeout(1500)
                page_items = _scrape_wechat_publish_history_items(current_page, step_logs)
                new_count = 0
                for row in page_items:
                    key = str(row.get("remote_key") or row.get("url") or "").strip()
                    if not key or key in seen_keys:
                        continue
                    seen_keys.add(key)
                    all_items.append(row)
                    new_count += 1
                step_logs.append(f"第 {page_num} 页抓取 {len(page_items)} 条，新增 {new_count} 条，累计 {len(all_items)} 条。")
                if new_count == 0:
                    break
                next_btn = current_page.locator("a.weui-desktop-btn:has-text('下一页')")
                if next_btn.count() == 0 or not next_btn.first.is_enabled():
                    break
                try:
                    next_btn.first.click()
                except Exception:
                    break
            current_page.screenshot(path=str(screenshot_path), full_page=True)
            artifacts.append(str(screenshot_path))
            browser_state["last_opened_url"] = current_page.url
            browser_state["current_page"] = current_page.url
            browser_state["last_screenshot"] = str(screenshot_path)
            browser_state["resident_page"] = "publish_history"
            WECHAT_BROWSER_MANAGER.set_resident_page("publish_history")
            browser_state["last_error"] = None
            step_logs.append(f"共读取到 {len(all_items)} 条微信发表记录。")
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "return_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_publish_history_return_home_final")
            browser_state["last_opened_url"] = page.url
            browser_state["current_page"] = page.url
            browser_state["resident_page"] = "home"
            WECHAT_BROWSER_MANAGER.set_resident_page("home")
            return all_items

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


def inspect_wechat_publish_history_with_overview(
    channel: dict[str, object],
    browser_state: dict[str, object],
) -> tuple[dict[str, object], list[str], list[str], list[dict[str, str | None]], dict[str, object] | None]:
    channel = ensure_channel_defaults(channel)
    selector_version = str(channel.get("selectors_version", "wechat-mp-v1"))
    entry_url = str(channel.get("publish_entry_url", "https://mp.weixin.qq.com/"))
    selector_profile = get_selector_profile(selector_version)
    browser_state = dict(browser_state)
    step_logs = [
        f"selector_profile={selector_version}",
        f"entry_url={entry_url}",
        "action=check_publish_history_with_overview",
    ]
    artifacts: list[str] = []
    overview: dict[str, object] | None = None
    browser_state["is_session_level_error"] = False

    if not browser_state.get("logged_in"):
        browser_state["last_error"] = "浏览器登录态不可用，无法检查微信发表记录。"
        browser_state["is_session_level_error"] = True
        return browser_state, artifacts, step_logs + ["未执行发表记录检查：登录态不可用。"], [], None

    artifact_dir = ARTIFACT_ROOT / "session"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = artifact_dir / f"check-publish-history-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"

    try:
        def _run(_context, page):
            nonlocal overview
            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "go_home")
            _safe_return_home(page, entry_url, selector_profile, step_logs, step_name="check_publish_history_return_home")

            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "scrape_overview")
            page.wait_for_timeout(2000)
            try:
                overview = _extract_wechat_analytics_overview(page)
                step_logs.append(f"已抓取首页总览：总用户 {overview.get('total_users', '?')}，昨日阅读 {overview.get('yesterday_reads', '?')}。")
            except Exception as exc:
                overview = None
                step_logs.append(f"抓取首页总览失败：{exc}")

            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "open_publish_history")
            if not _open_wechat_publish_history(page, selector_profile, step_logs):
                raise RuntimeError("未能进入正式发表记录页面（/cgi-bin/appmsgpublish?...）。")
            current_page = page
            current_page.wait_for_timeout(2000)
            if "appmsgpublish" not in str(current_page.url or ""):
                raise RuntimeError(f"当前页面不是发表记录：{current_page.url}")

            WECHAT_BROWSER_MANAGER.set_action_state("check_publish_history", "scrape")
            all_items: list[dict[str, str | None]] = []
            seen_keys: set[str] = set()
            max_pages = 10
            for page_num in range(1, max_pages + 1):
                current_page.wait_for_timeout(1500)
                page_items = _scrape_wechat_publish_history_items(current_page, step_logs)
                new_count = 0
                for row in page_items:
                    key = str(row.get("remote_key") or row.get("url") or "").strip()
                    if not key or key in seen_keys:
                        continue
                    seen_keys.add(key)
                    all_items.append(row)
                    new_count += 1
                step_logs.append(f"第 {page_num} 页抓取 {len(page_items)} 条，新增 {new_count} 条，累计 {len(all_items)} 条。")
                if new_count == 0:
                    break
                next_btn = current_page.locator("a.weui-desktop-btn:has-text('下一页')")
                if next_btn.count() == 0 or not next_btn.first.is_enabled():
                    break
                try:
                    next_btn.first.click()
                    step_logs.append(f"点击下一页，进入第 {page_num + 1} 页。")
                except Exception as exc:
                    step_logs.append(f"点击下一页失败：{exc}")
                    break
            items = all_items
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
        return browser_state, artifacts, step_logs, remote_items, overview
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
        return browser_state, artifacts, step_logs, [], overview


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


open_wechat_editor_debug = legacy_publishers.open_wechat_editor_debug
fill_wechat_author_only = legacy_publishers.fill_wechat_author_only
test_wechat_publish_settings_only = legacy_publishers.test_wechat_publish_settings_only


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

__all__ = [
    "_plain_text_from_markdown",
    "_apply_wechat_publish_settings",
    "_fill_wechat_editor",
    "_clamp_author",
    "_converge_context_to_target",
    "_locate_editor_page_with_retry",
    "extract_wechat_appmsg_id",
    "delete_wechat_remote_draft",
    "inspect_wechat_draft_box",
    "inspect_wechat_editor_dom",
    "inspect_wechat_analytics_dom",
    "inspect_wechat_publish_history",
    "inspect_wechat_publish_history_with_overview",
    "launch_wechat_dashboard",
    "inspect_wechat_session",
    "open_wechat_editor_debug",
    "fill_wechat_author_only",
    "test_wechat_publish_settings_only",
    "run_browser_action",
    "_wait_for_wechat_editor_in_current_page",
    "_enforce_single_tab",
]
