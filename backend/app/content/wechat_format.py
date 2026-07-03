from __future__ import annotations

import re
from html import escape, unescape

WECHAT_WRAPPER_STYLE = "font-size:15px;line-height:1.8;color:#222;"


def normalize_markdown_newlines(markdown: str) -> str:
    text = str(markdown or "")
    if not text:
        return ""
    actual_newlines = text.count("\n")
    powershell_escape_count = text.count("`n") + text.count("`r")
    if powershell_escape_count and (actual_newlines == 0 or powershell_escape_count >= max(3, actual_newlines * 2)):
        text = text.replace("`r`n", "\n").replace("`n", "\n").replace("`r", "\r")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def strip_markdown_title(markdown: str, title: str) -> str:
    lines = list(normalize_markdown_newlines(markdown).splitlines())
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ""
    first = lines[0].strip()
    if first.startswith("#"):
        normalized = first.lstrip("#").strip()
        if normalized == str(title or "").strip():
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
    return "\n".join(lines).strip()


def _render_inline_html(text: str) -> str:
    value = str(text or "")
    result: list[str] = []
    index = 0
    length = len(value)
    while index < length:
        if value.startswith("**", index):
            end = value.find("**", index + 2)
            if end > index + 2:
                result.append(f"<strong>{_render_inline_html(value[index + 2:end])}</strong>")
                index = end + 2
                continue
        if value.startswith("__", index):
            end = value.find("__", index + 2)
            if end > index + 2:
                result.append(f"<strong>{_render_inline_html(value[index + 2:end])}</strong>")
                index = end + 2
                continue
        if value[index] == "`":
            end = value.find("`", index + 1)
            if end > index + 1:
                result.append(f"<code>{escape(value[index + 1:end])}</code>")
                index = end + 1
                continue
        if value[index] == "[":
            match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", value[index:])
            if match:
                label = match.group(1).strip()
                href = match.group(2).strip()
                result.append(
                    f"<a href=\"{escape(href, quote=True)}\">{_render_inline_html(label)}</a>"
                )
                index += match.end()
                continue
        if value[index] == "*" and not value.startswith("**", index):
            end = value.find("*", index + 1)
            if end > index + 1:
                result.append(f"<em>{_render_inline_html(value[index + 1:end])}</em>")
                index = end + 1
                continue
        if value[index] == "_" and not value.startswith("__", index):
            end = value.find("_", index + 1)
            if end > index + 1:
                result.append(f"<em>{_render_inline_html(value[index + 1:end])}</em>")
                index = end + 1
                continue
        result.append(escape(value[index]))
        index += 1
    return "".join(result)


def markdown_to_wechat_html(markdown: str, *, include_wrapper: bool = True) -> str:
    blocks: list[str] = []
    paragraph_lines: list[str] = []
    quote_lines: list[str] = []
    unordered_items: list[str] = []
    ordered_items: list[str] = []
    code_lines: list[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            blocks.append("<p>" + "<br/>".join(_render_inline_html(item) for item in paragraph_lines) + "</p>")
            paragraph_lines = []

    def flush_quotes() -> None:
        nonlocal quote_lines
        if quote_lines:
            blocks.append("<blockquote><p>" + "<br/>".join(_render_inline_html(item) for item in quote_lines) + "</p></blockquote>")
            quote_lines = []

    def flush_unordered() -> None:
        nonlocal unordered_items
        if unordered_items:
            blocks.append("<ul>" + "".join(f"<li>{_render_inline_html(item)}</li>" for item in unordered_items) + "</ul>")
            unordered_items = []

    def flush_ordered() -> None:
        nonlocal ordered_items
        if ordered_items:
            blocks.append("<ol>" + "".join(f"<li>{_render_inline_html(item)}</li>" for item in ordered_items) + "</ol>")
            ordered_items = []

    def flush_code() -> None:
        nonlocal code_lines
        if code_lines:
            blocks.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")
            code_lines = []

    def flush_all() -> None:
        flush_paragraph()
        flush_quotes()
        flush_unordered()
        flush_ordered()
        flush_code()

    for raw in normalize_markdown_newlines(markdown).splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_code_block:
                flush_code()
                in_code_block = False
            else:
                flush_all()
                in_code_block = True
            continue
        if in_code_block:
            code_lines.append(raw.rstrip())
            continue
        if not stripped:
            flush_all()
            continue

        ordered_match = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        unordered_match = re.match(r"^[-*+]\s+(.*)$", stripped)

        if stripped.startswith("#"):
            flush_all()
            level = min(3, max(1, len(stripped) - len(stripped.lstrip("#"))))
            title = stripped[level:].strip()
            blocks.append(f"<h{level}>{_render_inline_html(title)}</h{level}>")
            continue
        if stripped.startswith("> "):
            flush_paragraph()
            flush_unordered()
            flush_ordered()
            quote_lines.append(stripped[2:].strip())
            continue
        if unordered_match:
            flush_paragraph()
            flush_quotes()
            flush_ordered()
            unordered_items.append(unordered_match.group(1).strip())
            continue
        if ordered_match:
            flush_paragraph()
            flush_quotes()
            flush_unordered()
            ordered_items.append(ordered_match.group(2).strip())
            continue
        flush_quotes()
        flush_unordered()
        flush_ordered()
        paragraph_lines.append(stripped)

    flush_all()
    content = "".join(blocks)
    if not content:
        content = "<p><br/></p>"
    if include_wrapper:
        return f"<section style='{WECHAT_WRAPPER_STYLE}'>{content}</section>"
    return content


def markdown_to_plain_text(markdown: str, *, limit: int = 12000) -> str:
    html = markdown_to_wechat_html(markdown, include_wrapper=False)
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</(p|h1|h2|h3|li|blockquote|pre|ul|ol|section)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]
