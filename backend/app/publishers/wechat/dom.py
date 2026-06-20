from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ...content.wechat_format import markdown_to_plain_text, strip_markdown_title
from ...store.base import UTC
from ..browser_base import _page_url, _pick_visible_locator, _write_debug_artifact


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
        if "action=list_card" in current_url:
            return False
        if "action=edit" not in current_url and "media/appmsg_edit" not in current_url:
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

def _open_wechat_analytics(page, selector_profile: dict[str, list[str] | str], step_logs: list[str]) -> bool:
    selector_candidates = selector_profile.get("analytics", [])
    selector_list = selector_candidates if isinstance(selector_candidates, list) else [selector_candidates]
    if not selector_list:
        return False
    failed_selectors: list[str] = []
    for selector in [str(item) for item in selector_list if str(item).strip()]:
        try:
            locator = page.locator(selector).first
            locator.wait_for(timeout=4000)
            href = ""
            try:
                href = str(locator.get_attribute("href", timeout=1200) or "").strip()
            except Exception:
                href = ""
            if href:
                target_url = href if href.startswith("http") else f"https://mp.weixin.qq.com{href}"
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
            else:
                try:
                    locator.click(timeout=2000)
                except Exception:
                    locator.click(timeout=2000, force=True)
                page.wait_for_timeout(2500)
            current_url = str(page.url or "")
            if "appmsganalysis" not in current_url:
                failed_selectors.append(selector)
                step_logs.append(f"内容分析入口未跳转 selector={selector} url={current_url}")
                continue
            step_logs.append(f"已点击数据分析入口 selector={selector}")
            step_logs.append(f"当前数据分析页面 url={current_url}")
            return True
        except Exception as exc:
            failed_selectors.append(selector)
            step_logs.append(f"数据分析入口点击失败 selector={selector} error={exc}")
            continue
    if failed_selectors:
        step_logs.append(f"数据分析入口全部尝试失败：{', '.join(failed_selectors)}")
    return False

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
