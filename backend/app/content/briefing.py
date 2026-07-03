from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .wechat_format import strip_markdown_title

WECHAT_TITLE_LIMIT = 64
WECHAT_TITLE_HOOK_LIMIT = 28
DOUYIN_TITLE_LIMIT = 30
DOUYIN_SUMMARY_LIMIT = 30
_DOUYIN_SUMMARY_WEAK_ENDINGS = (
    "正式",
    "已经",
    "正在",
    "将于",
    "关于",
    "有关",
    "相关",
)
_DOUYIN_SUMMARY_SHORTENERS = (
    (r"国行\s*Nintendo\s+Switch", "国行Switch"),
    (r"国行\s*Switch", "国行Switch"),
    (r"\bNintendo\s+Switch\b", "Switch"),
    (r"\bNintendo\s+e\s*商店\b", "e商店"),
    (r"\be\s+商店\b", "e商店"),
    (r"网络相关运营服务", "网络服务"),
    (r"网络相关服务", "网络服务"),
    (r"网络运营服务", "网络服务"),
    (r"正式停止", "停止"),
    (r"正式关停", "关停"),
    (r"正式结束", "结束"),
)
_LOW_SIGNAL_TITLE_TAILS = {
    "summary",
    "body",
    "article",
    "news",
    "update",
    "overview",
    "导语",
    "正文",
    "摘要",
    "文章",
}
_TITLE_HOOK_KEYWORDS = (
    "首次",
    "翻倍",
    "提速",
    "降本",
    "暴涨",
    "暴跌",
    "新高",
    "新低",
    "意味着",
    "背后",
    "反转",
    "停摆",
    "封禁",
    "裁员",
    "融资",
    "落地",
    "量产",
    "开源",
)

_AI_STYLE_BANNED_PHRASES = (
    "在人工智能技术飞速发展的今天",
    "随着大模型技术的不断演进",
    "在当今快速发展的",
    "值得关注",
    "引发关注",
    "引发热议",
    "引发了广泛关注",
    "具有重要意义",
    "不言而喻",
    "令人兴奋的是",
    "值得注意的是",
    "接下来我们来看看",
    "让我们深入探讨",
    "下面将详细介绍",
    "本文将从以下几个方面展开",
    "综上所述",
    "总而言之",
    "总的来说",
    "不仅是.*更是",
    "赋能",
    "深耕",
    "布局",
    "生态",
    "底层逻辑",
    "赛道",
    "范式",
    "核心驱动力",
    "不可或缺",
    "举足轻重",
    "重塑",
    "颠覆性",
    "全新升级",
)

_DOUYIN_DROP_SECTION_TITLES = {
    "来源链接",
    "参考资料",
    "延伸阅读",
    "相关阅读",
    "资料来源",
    "引用来源",
    "消息来源",
}
_DOUYIN_DAILY_NEWS_INTERNAL_PATTERNS = (
    r"\d+\s*个\s*平台\s*同时出现",
    r"\d+\s*分钟\s*新增\s*\d+\s*条",
    r"事件覆盖\s*\d+\s*个\s*平台",
    r"\d+\s*个\s*来源",
    r"成员数\s*\d+",
    r"事件已进入深挖池",
    r"可继续生成简报",
    r"更贴近公众号",
    r"来源仍偏少",
    r"当前来源仍偏少",
    r"还不确定",
    r"不确定项",
    r"正文深挖",
    r"brief",
    r"deep[_\s-]?dive",
)
_DOUYIN_DAILY_NEWS_ORDINALS = ("首先是", "第二条，", "第三条，", "第四条，", "最后一条，")


def _contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))


def _normalize_title_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()
    compact = re.sub(r"\s*([:：|｜/\\-])\s*", r"\1", compact)
    compact = compact.strip(" \t\r\n-—_|｜/\\:：;；，,。！？!?")
    return compact[:WECHAT_TITLE_LIMIT]


def _extract_markdown_heading(markdown: str) -> str:
    for raw in str(markdown or "").splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        break
    return ""


def _title_already_punchy(title: str) -> bool:
    compact = _normalize_title_text(title)
    if not compact:
        return False
    if re.search(r"[！？?!]", compact):
        return True
    if re.search(r"[：:].{3,}", compact):
        return True
    if re.search(r"\d", compact) or "%" in compact:
        return True
    return any(marker in compact for marker in _TITLE_HOOK_KEYWORDS)


def _clean_title_hook_candidate(text: str, base_title: str) -> str:
    compact = _normalize_title_text(text)
    compact = re.sub(r"^(一句话|导语|结论|摘要|核心事实|看点|重点)\s*[:：]\s*", "", compact)
    compact = re.sub(r"https?://\S+", "", compact).strip()
    compact = re.sub(r"^(这意味着|值得注意的是|需要注意的是|简单来说|换句话说|说白了|本质上)", "", compact)
    compact = compact.strip(" ：:，,、；;。！？!?")
    if base_title:
        compact = compact.replace(base_title, "").strip(" ：:，,、；;。！？!?")
    return _normalize_title_text(compact)


def _score_title_hook(candidate: str) -> int:
    score = 0
    if re.search(r"\d", candidate) or "%" in candidate:
        score += 4
    if any(marker in candidate for marker in _TITLE_HOOK_KEYWORDS):
        score += 2
    if 4 <= len(candidate) <= 12:
        score += 2
    if candidate.endswith(("发布", "回应", "消息", "文章")):
        score -= 2
    return score


def _derive_title_hook(source: str, base_title: str, *, max_len: int) -> str:
    cleaned = _clean_title_hook_candidate(source, base_title)
    if not cleaned:
        return ""
    candidates: list[str] = []
    for sentence in re.split(r"[。！？?!；;\n]", cleaned):
        for clause in re.split(r"[，,、]", sentence):
            candidate = _clean_title_hook_candidate(clause, base_title)
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered in _LOW_SIGNAL_TITLE_TAILS:
                continue
            if base_title and (candidate in base_title or base_title in candidate):
                continue
            candidate = candidate[:max_len].rstrip(" ：:，,、；;。！？!?")
            if len(candidate) < 4:
                continue
            if not _contains_cjk(candidate) and not re.search(r"\d", candidate):
                continue
            candidates.append(candidate)
    if not candidates:
        return ""
    ranked = sorted(
        candidates,
        key=lambda item: (_score_title_hook(item), -abs(len(item) - 8), -len(item)),
        reverse=True,
    )
    best = ranked[0].strip()
    if _score_title_hook(best) <= 0 and not _contains_cjk(best):
        return ""
    return best


def optimize_wechat_article_title(
    raw_title: str,
    *,
    one_line: str = "",
    facts: list[str] | None = None,
    article_markdown: str = "",
) -> str:
    normalized_facts = [_normalize_title_text(item) for item in list(facts or []) if _normalize_title_text(item)]
    base_title = _normalize_title_text(raw_title)
    if not base_title:
        base_title = _normalize_title_text(
            _extract_markdown_heading(article_markdown) or one_line or (normalized_facts[0] if normalized_facts else "")
        )
    if not base_title:
        return ""
    if len(base_title) > 20 or _title_already_punchy(base_title):
        return base_title
    if not (
        _contains_cjk(base_title)
        or _contains_cjk(one_line)
        or any(_contains_cjk(item) for item in normalized_facts)
    ):
        return base_title
    hook_budget = min(14, WECHAT_TITLE_HOOK_LIMIT - len(base_title) - 1)
    if hook_budget < 4:
        return base_title
    hook_sources = [str(one_line or "").strip(), *normalized_facts]
    for raw in str(article_markdown or "").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        hook_sources.append(stripped)
        if len(hook_sources) >= 6:
            break
    for source in hook_sources:
        hook = _derive_title_hook(source, base_title, max_len=hook_budget)
        if hook:
            return f"{base_title}：{hook}"[:WECHAT_TITLE_LIMIT]
    return base_title


def rewrite_markdown_title(markdown: str, previous_title: str, next_title: str) -> str:
    lines = str(markdown or "").splitlines()
    if not lines:
        return str(markdown or "").strip()
    previous_compact = _normalize_title_text(previous_title)
    next_compact = _normalize_title_text(next_title)
    if not next_compact:
        return str(markdown or "").strip()
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            continue
        if not stripped.startswith("#"):
            return str(markdown or "").strip()
        level = max(1, len(stripped) - len(stripped.lstrip("#")))
        heading = stripped.lstrip("#").strip()
        if heading not in {previous_compact, next_compact}:
            return str(markdown or "").strip()
        lines[index] = f"{'#' * level} {next_compact}"
        return "\n".join(lines).strip()
    return str(markdown or "").strip()


def _normalize_summary_text(value: str, *, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()
    compact = compact.strip(" \t\r\n-—_|｜/\\:：;；，,。！？!?")
    if not compact:
        return ""
    return compact[:limit].rstrip(" \t\r\n-—_|｜/\\:：;；，,。！？!?")


def build_brief_summary(
    *,
    summary: str = "",
    one_line: str = "",
    facts: list[str] | None = None,
    event_summary: str = "",
    limit: int = 120,
) -> str:
    candidates = [
        str(summary or "").strip(),
        str(one_line or "").strip(),
        next((str(item).strip() for item in list(facts or []) if str(item).strip()), ""),
        str(event_summary or "").strip(),
    ]
    for candidate in candidates:
        normalized = _normalize_summary_text(candidate, limit=limit)
        if normalized:
            return normalized
    return ""


def _normalize_compact_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()
    return compact.strip(" \t\r\n-—_|｜/\\:：;；，,。！？!?")


def _remove_inline_markdown(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("**", "").replace("__", "")
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)", r"\1", value)
    value = re.sub(r"(?<!_)_(?!_)([^_]+)(?<!_)_(?!_)", r"\1", value)
    return value


def _pick_first_sentence(value: str) -> str:
    compact = _normalize_compact_text(value)
    if not compact:
        return ""
    match = re.search(r"[。！？?!；;\n]", compact)
    if not match:
        return compact
    return compact[: match.end()].strip(" \t\r\n-—_|｜/\\:：;；，,。！？!?")


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


def _compact_douyin_summary_text(value: str) -> str:
    compact = _normalize_compact_text(_remove_inline_markdown(value))
    if not compact:
        return ""
    for pattern, replacement in _DOUYIN_SUMMARY_SHORTENERS:
        compact = re.sub(pattern, replacement, compact, flags=re.IGNORECASE)
    compact = re.sub(r"(?<=[A-Za-z0-9])\s+(?=[的地得])", "", compact)
    compact = re.sub(r"\s{2,}", " ", compact)
    return _normalize_compact_text(compact)


def _strip_douyin_summary_time_prefix(value: str) -> str:
    compact = _compact_douyin_summary_text(value)
    if not compact:
        return ""
    stripped = re.sub(
        r"^(今天|今日|今晚|今夜|当地时间)?\s*\d{0,4}(?:年)?\d{0,2}(?:月)?\d{0,2}(?:日)?\s*(?:凌晨|早上|上午|中午|下午|傍晚|晚上|晚间)?\s*\d{0,2}(?::\d{2})?(?:时|点|分)?\s*[，,:：]\s*",
        "",
        compact,
    ).strip()
    return _compact_douyin_summary_text(stripped)


def _is_complete_douyin_summary_candidate(value: str, *, min_len: int = 4) -> bool:
    candidate = _normalize_compact_text(value)
    if not candidate or len(candidate) < min_len:
        return False
    if candidate.endswith(("，", ",", "、", "：", ":", "；", ";", "-", "的")):
        return False
    return not candidate.endswith(_DOUYIN_SUMMARY_WEAK_ENDINGS)


def _pick_douyin_summary_candidate(value: str, limit: int) -> str:
    compact = _compact_douyin_summary_text(value)
    if not compact:
        return ""
    sentence = _pick_first_sentence(compact)
    if sentence and len(sentence) <= limit and _is_complete_douyin_summary_candidate(sentence):
        return sentence
    clause = _pick_best_prefix_within_limit(compact, limit, ("，", ",", "、", "：", ":", "；", ";"))
    if clause and len(clause) <= limit and len(clause) >= 8 and _is_complete_douyin_summary_candidate(clause):
        return clause
    if len(compact) <= limit and _is_complete_douyin_summary_candidate(compact):
        return compact
    return ""


def should_refresh_douyin_summary(raw_summary: str, raw_title: str, limit: int = DOUYIN_SUMMARY_LIMIT) -> bool:
    summary = _compact_douyin_summary_text(raw_summary)
    title = _compact_douyin_summary_text(raw_title)
    if not summary:
        return True
    if len(summary) > limit:
        return True
    if summary == title:
        return True
    return not _is_complete_douyin_summary_candidate(summary)


def build_douyin_title(raw_title: str, limit: int = DOUYIN_TITLE_LIMIT) -> str:
    compact = _normalize_compact_text(raw_title)
    if len(compact) <= limit:
        return compact

    headline = _pick_first_sentence(compact)
    if headline and len(headline) <= limit:
        return headline

    for marker in ("：", ":"):
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


def build_douyin_summary(
    raw_summary: str,
    raw_title: str,
    limit: int = DOUYIN_SUMMARY_LIMIT,
) -> str:
    summary = _compact_douyin_summary_text(raw_summary)
    title = _compact_douyin_summary_text(raw_title)

    stripped_time_prefix = _strip_douyin_summary_time_prefix(summary)
    for candidate_source in (stripped_time_prefix, summary):
        candidate = _pick_douyin_summary_candidate(candidate_source, limit)
        if candidate and candidate != title:
            return candidate

    if summary and title and summary.startswith(title):
        remainder = _compact_douyin_summary_text(summary[len(title) :].strip(" ，,、:：;；-"))
        candidate = _pick_douyin_summary_candidate(remainder, limit)
        if candidate:
            return candidate

    if title:
        derived = title
        for marker in ("：", ":"):
            if marker in title:
                prefix, suffix = title.split(marker, 1)
                prefix = prefix.strip()
                suffix = suffix.strip()
                if suffix and len(suffix) <= limit:
                    derived = suffix
                    break
                if prefix and len(prefix) <= limit:
                    derived = prefix
                    break
        if derived and len(derived) <= limit and derived != title:
            return derived

    fallback_candidates = [
        _pick_first_sentence(stripped_time_prefix),
        _pick_best_prefix_within_limit(stripped_time_prefix, limit, ("，", ",", "、", "：", ":", "；", ";")),
        _pick_first_sentence(summary),
        _pick_best_prefix_within_limit(summary, limit, ("，", ",", "、", "：", ":", "；", ";")),
        summary,
        title,
    ]
    for fallback in fallback_candidates:
        compact = _compact_douyin_summary_text(fallback)
        if compact and len(compact) <= limit and compact != title:
            return compact

    fallback = summary or title
    return _trim_to_limit(_compact_douyin_summary_text(fallback), limit)


def ensure_markdown_title(markdown: str, title: str) -> str:
    normalized_title = _normalize_title_text(title)
    if not normalized_title:
        return str(markdown or "").strip()

    lines = str(markdown or "").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip().startswith("#"):
        lines[0] = f"# {normalized_title}"
        return "\n".join(lines).strip()

    body = str(markdown or "").strip()
    if not body:
        return f"# {normalized_title}"
    return f"# {normalized_title}\n\n{body}".strip()


def _normalize_douyin_heading(text: str) -> str:
    return re.sub(r"[：:：。！？?!]+$", "", _normalize_compact_text(text))


def _is_douyin_source_heading(text: str) -> bool:
    compact = _normalize_douyin_heading(text)
    return compact in _DOUYIN_DROP_SECTION_TITLES


def _is_url_only(text: str) -> bool:
    return bool(re.fullmatch(r"https?://\S+", str(text or "").strip()))


def _extract_markdown_blocks(markdown: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    paragraph_lines: list[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            blocks.append(("paragraph", " ".join(paragraph_lines).strip()))
            paragraph_lines = []

    for raw in str(markdown or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            blocks.append(("heading", stripped.lstrip("#").strip()))
            continue
        quote_match = re.match(r"^>\s*(.*)$", stripped)
        if quote_match:
            flush_paragraph()
            blocks.append(("quote", quote_match.group(1).strip()))
            continue
        unordered_match = re.match(r"^[-*+]\s+(.*)$", stripped)
        if unordered_match:
            flush_paragraph()
            blocks.append(("item", unordered_match.group(1).strip()))
            continue
        ordered_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ordered_match:
            flush_paragraph()
            blocks.append(("item", ordered_match.group(1).strip()))
            continue
        paragraph_lines.append(stripped)

    flush_paragraph()
    return blocks


def _drop_leading_markdown_heading(markdown: str) -> str:
    lines = list(str(markdown or "").splitlines())
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip().startswith("#"):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    return "\n".join(lines).strip()


def _split_mobile_paragraph(text: str, *, max_chars: int = 72, max_sentences: int = 2) -> list[str]:
    compact = _normalize_compact_text(text)
    if not compact:
        return []

    sentences = [item.strip() for item in re.split(r"(?<=[。！？?!])\s*", compact) if item.strip()]
    if not sentences:
        sentences = [compact]

    parts: list[str] = []
    current = ""
    sentence_count = 0

    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{current}{sentence}" if current else sentence
        if current and (len(candidate) > max_chars or sentence_count >= max_sentences):
            parts.append(current.strip())
            current = sentence
            sentence_count = 1
            continue
        current = candidate
        sentence_count += 1

    if current.strip():
        parts.append(current.strip())

    if len(parts) == 1 and len(parts[0]) > max_chars:
        clauses = [item.strip() for item in re.split(r"(?<=[，、；;])\s*", parts[0]) if item.strip()]
        if len(clauses) > 1:
            parts = []
            current = ""
            for clause in clauses:
                candidate = f"{current}{clause}" if current else clause
                if current and len(candidate) > max_chars:
                    parts.append(current.strip())
                    current = clause
                    continue
                current = candidate
            if current.strip():
                parts.append(current.strip())

    return [item for item in parts if item]


def build_douyin_article_markdown(
    *,
    title: str,
    summary: str,
    article_markdown: str,
    one_line: str = "",
    why_it_matters: str = "",
    facts: list[str] | None = None,
    quotes: list[str] | None = None,
    timeline: list[str] | None = None,
    source_links: list[str] | None = None,
    max_body_chars: int = 980,
) -> str:
    douyin_title = build_douyin_title(title)
    seed_summary = build_douyin_summary(summary or one_line or why_it_matters, douyin_title or title)
    compact_one_line = _normalize_compact_text(one_line)
    compact_why = _normalize_compact_text(why_it_matters)
    body_markdown = _drop_leading_markdown_heading(article_markdown)
    if not body_markdown:
        body_markdown = strip_markdown_title(article_markdown, title)
    if title and body_markdown == str(article_markdown or "").strip():
        body_markdown = strip_markdown_title(article_markdown, douyin_title or title)

    blocks = _extract_markdown_blocks(body_markdown)
    paragraphs: list[str] = []
    seen: set[str] = set()
    stop_collecting = False

    def append_paragraph(text: str, *, keep_heading: bool = False) -> None:
        normalized = _normalize_compact_text(text)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        paragraphs.append(f"## {normalized}" if keep_heading else normalized)

    # 抖音正文先把结论打在最前面，避免像公众号那样慢慢铺。
    if compact_one_line:
        for part in _split_mobile_paragraph(compact_one_line, max_chars=60, max_sentences=1):
            append_paragraph(part)
            break
    if seed_summary and seed_summary != compact_one_line:
        for part in _split_mobile_paragraph(seed_summary, max_chars=60, max_sentences=1):
            append_paragraph(part)
            break
    if compact_why:
        for part in _split_mobile_paragraph(compact_why, max_chars=60, max_sentences=1):
            append_paragraph(part)
            break

    skip_first_title_like_heading = True
    for kind, raw_text in blocks:
        if stop_collecting:
            break
        text = _normalize_compact_text(_remove_inline_markdown(raw_text))
        if not text or _is_url_only(text):
            continue
        if _is_douyin_source_heading(text):
            stop_collecting = True
            continue
        if kind == "heading":
            heading = _normalize_douyin_heading(text)
            if heading and skip_first_title_like_heading and heading.startswith(_normalize_douyin_heading(douyin_title)):
                skip_first_title_like_heading = False
                continue
            if heading and heading != _normalize_douyin_heading(douyin_title):
                append_paragraph(heading, keep_heading=True)
                skip_first_title_like_heading = False
            continue
        for chunk in _split_mobile_paragraph(text):
            append_paragraph(chunk)

    if not paragraphs:
        fallback_candidates = [
            compact_one_line,
            compact_why,
            *[str(item).strip() for item in list(facts or []) if str(item).strip()],
            *[str(item).strip() for item in list(quotes or [])[:2] if str(item).strip()],
            *[str(item).strip() for item in list(timeline or [])[:2] if str(item).strip()],
        ]
        for candidate in fallback_candidates:
            for chunk in _split_mobile_paragraph(candidate):
                append_paragraph(chunk)
            if paragraphs:
                break

    trimmed: list[str] = []
    used_chars = 0
    for paragraph in paragraphs:
        normalized = paragraph.strip()
        if not normalized:
            continue
        if trimmed and trimmed[-1].startswith("## ") and normalized.startswith("## "):
            continue
        next_len = used_chars + len(normalized)
        if trimmed and next_len > max_body_chars:
            break
        trimmed.append(normalized)
        used_chars = next_len

    body = "\n\n".join(trimmed).strip()
    if not body:
        body = seed_summary or why_it_matters or douyin_title or _normalize_compact_text(article_markdown)

    # 再兜一层：如果正文太像公众号原文顺切，就重新组装成抖音节奏。
    if compact_why and compact_why not in body:
        body = "\n\n".join([item for item in [compact_one_line or seed_summary, compact_why, body] if item]).strip()

    return ensure_markdown_title(body, douyin_title or title)


def build_prompt_package_markdown(
    *,
    title: str,
    one_line: str,
    why_it_matters: str,
    facts: list[str],
    full_text_sources: list[dict[str, str]],
    source_quotes: list[dict[str, str]],
    timeline: list[str],
    risk_notes: list[str],
    source_links: list[str],
    article_writing_guide: str = "",
) -> str:
    guide = str(article_writing_guide or build_agent_article_writing_guide()).strip()
    lines = [
        "## 写作任务",
        "基于以下已核验素材，写一篇 800-1000 字的微信公众号发布稿。",
        "目标不是新闻简报，而是让普通读者愿意点开、读完、转发给朋友；不要输出后台素材稿或结构化审阅稿。",
        "标题要有冲突感、利益关系或悬念，开头 80 字内说清这件事和普通人、开发者、消费者、公司账单或未来设备有什么关系。",
        "同时生成一段 40-60 字的摘要，摘要与标题互补（标题说了 What，摘要说 Why 或 How），推送时显示在标题下方。",
        "",
    ]
    if guide:
        lines.extend(
            [
                "## 写作要求",
                guide,
                "",
            ]
        )
    lines.extend(
        [
        "## 事件标题",
        title.strip() or "未命名事件",
        "",
        "## 一句话结论",
        one_line.strip() or "请基于核心事实给出一句话结论。",
        "",
        "## 为什么值得关注",
        why_it_matters.strip() or "请结合事实、时间线和行业影响判断其重要性。",
        "",
        "## 核心事实",
    ])
    if facts:
        lines.extend([f"- {item}" for item in facts])
    else:
        lines.append("- 暂无足够正文事实，请结合来源链接补充核验。")

    lines.extend(["", "## 已抓取完整正文"])
    if full_text_sources:
        for item in full_text_sources:
            source_name = item.get("source_name", "未知来源")
            source_title = item.get("title", "")
            full_text = item.get("full_text", "")
            if not full_text:
                continue
            lines.append(f"来源：{source_name}")
            if source_title:
                lines.append(f"标题：{source_title}")
            lines.append("正文：")
            lines.append(full_text)
            lines.append("")
    else:
        lines.append("暂无可用完整正文")
        lines.append("")

    lines.extend(["", "## 正文摘录"])
    if source_quotes:
        for item in source_quotes:
            source_name = item.get("source_name", "未知来源")
            quote = item.get("quote", "")
            if not quote:
                continue
            lines.append(f"来源：{source_name}")
            lines.append(f"> {quote}")
            lines.append("")
    else:
        lines.append("> 暂无可用正文摘录")
        lines.append("")

    lines.extend(["## 时间线"])
    if timeline:
        lines.extend([f"- {item}" for item in timeline])
    else:
        lines.append("- 时间线待补充")

    lines.extend(["", "## 风险与不确定性"])
    if risk_notes:
        lines.extend([f"- {item}" for item in risk_notes])
    else:
        lines.append("- 暂未发现额外风险说明")

    lines.extend(["", "## 来源链接"])
    if source_links:
        lines.extend([f"- {item}" for item in source_links])
    else:
        lines.append("- 暂无来源链接")
    return "\n".join(lines).strip()


def build_douyin_article_writing_guide() -> str:
    banned_phrases = "、".join(_AI_STYLE_BANNED_PHRASES)
    return f"""\
## 抖音文章写作规范

### 目标
- 输出适合抖音创作者中心“文章”页的正文，而不是公众号长文
- 信息仍然要完整，但呈现必须更像移动端阅读：更短、更直接、更前置结论
- 成稿必须像“今天这件事我直接讲给你听”，而不是“公众号深度稿缩写版”

### 标题
- 标题控制在 30 个字以内
- 优先把产品名、时间点、结果放到前半句
- 不要用公众号双段式长标题，不要用“背后”“深度解析”这类拖长结构

### 摘要
- 摘要控制在 30 个字以内
- 只说最核心的新信息，不重复空话
- 适合直接出现在抖音文章摘要输入框

### 正文结构
- 正文建议 400-600 字，硬上限 800 字
- 开头 1-2 句内必须交代时间点、发生了什么、结论是什么
- 第一屏就要把最关键的新信息说出来，不要先讲背景
- 全文以短段落为主，每段 1-2 句，少用长分析段
- 结构优先采用下面这种抖音节奏：
  1. 先说结论：今天发生了什么
  2. 再说为什么值钱：这件事为什么重要
  3. 再拆 2-4 个关键点：价格、性能、变化、影响
  4. 最后收一句判断：接下来谁会受影响
- 如确有必要，可保留 2-4 个短小标题，但标题必须口语化、有信息量
- 小标题优先像这样写：
  - “最狠的是 5GHz”
  - “这不只是跑分升级”
  - “小米为什么最关键”
  - “下一轮会卷到哪里”
- 不要保留“来源链接”“延伸阅读”“参考资料”等公众号尾巴

### 风格要求
- 语气更直接，像在告诉用户“这件事现在到底意味着什么”
- 保持事实密度，但少写宏大铺垫，少写行业腔
- 可以有判断，但判断必须紧贴已核验事实
- 允许比公众号更口语一点，但不能夸张、不能煽动、不能标题党
- 多写短句、结论句、对比句，少写大段铺陈
- 可以保留一点“说人话”的表达，但不要用喊话体和情绪标题体
- 读起来应该像：
  - “最关键的不是 5GHz 本身，而是高通又把旗舰芯片拉回性能优先。”
  - “如果这代平台真落地，接下来两年安卓旗舰会重新围着芯片打。”
- 不应该像：
  - “这意味着行业正在迎来一场深刻变革”
  - “从更深层的逻辑来看”
  - “背后折射出的，是整个生态的重塑”

### 事实底线
- 所有数字、日期、产品名、公司名必须来自已核验素材
- 引号内内容必须来自真实原文摘录
- 不要把国行服务停止写成全球 Switch 停服
- 不要新增素材里没有的背景信息

### 禁止事项
- 不要写“本文将”“接下来我们来看”
- 不要堆来源链接到正文
- 不要用公众号结尾式总结
- 不要把公众号正文原样压缩后直接输出
- 不要保留明显公众号痕迹，比如“为什么值得关注”“来源链接”“时间线”“风险与不确定性”
- 不要连续 3 段以上都用同一种长度和句式
- 禁止使用这些高频 AI 味词或近义表达：{banned_phrases}
""".strip()


def build_douyin_prompt_package_markdown(
    *,
    title: str,
    one_line: str,
    why_it_matters: str,
    facts: list[str],
    full_text_sources: list[dict[str, str]],
    source_quotes: list[dict[str, str]],
    timeline: list[str],
    risk_notes: list[str],
    source_links: list[str],
    article_markdown: str,
    article_writing_guide: str = "",
) -> str:
    guide = str(article_writing_guide or build_douyin_article_writing_guide()).strip()
    lines = [
        "## 写作任务",
        "基于以下已核验素材，把现有成稿改写成适合抖音创作者中心文章页的版本。",
        "",
    ]
    if guide:
        lines.extend(["## 写作要求", guide, ""])
    lines.extend(
        [
            "## 事件标题",
            title.strip() or "未命名事件",
            "",
            "## 一句话结论",
            one_line.strip() or "请基于核心事实给出一句话结论。",
            "",
            "## 为什么值得关注",
            why_it_matters.strip() or "请结合事实与用户影响判断其重要性。",
            "",
            "## 核心事实",
        ]
    )
    if facts:
        lines.extend([f"- {item}" for item in facts])
    else:
        lines.append("- 暂无足够正文事实，请结合来源链接补充核验。")

    lines.extend(["", "## 已抓取完整正文"])
    if full_text_sources:
        for item in full_text_sources:
            source_name = item.get("source_name", "未知来源")
            source_title = item.get("title", "")
            full_text = item.get("full_text", "")
            if not full_text:
                continue
            lines.append(f"来源：{source_name}")
            if source_title:
                lines.append(f"标题：{source_title}")
            lines.append("正文：")
            lines.append(full_text)
            lines.append("")
    else:
        lines.append("暂无可用完整正文")
        lines.append("")

    lines.extend(["## 正文摘录"])
    if source_quotes:
        for item in source_quotes:
            source_name = item.get("source_name", "未知来源")
            quote = item.get("quote", "")
            if not quote:
                continue
            lines.append(f"来源：{source_name}")
            lines.append(f"> {quote}")
            lines.append("")
    else:
        lines.append("> 暂无可用正文摘录")
        lines.append("")

    lines.extend(["## 现有成稿（供改写参考）", article_markdown.strip() or "暂无现有成稿", ""])

    lines.extend(["## 时间线"])
    if timeline:
        lines.extend([f"- {item}" for item in timeline])
    else:
        lines.append("- 时间线待补充")

    lines.extend(["", "## 风险与不确定性"])
    if risk_notes:
        lines.extend([f"- {item}" for item in risk_notes])
    else:
        lines.append("- 暂未发现额外风险说明")

    lines.extend(["", "## 来源链接"])
    if source_links:
        lines.extend([f"- {item}" for item in source_links])
    else:
        lines.append("- 暂无来源链接")
    return "\n".join(lines).strip()


def build_rule_brief_payload(event: dict[str, Any], deep_dive: dict[str, Any]) -> dict[str, Any]:
    title = str(event.get("title") or deep_dive.get("title") or "未命名事件").strip()
    facts = [str(item).strip() for item in deep_dive.get("facts", []) if str(item).strip()]
    quotes = [str(item).strip() for item in deep_dive.get("quotes", []) if str(item).strip()]
    timeline = [str(item).strip() for item in deep_dive.get("timeline", []) if str(item).strip()]
    source_links = [
        str(item.get("canonical_link") or item.get("original_link") or "").strip()
        for item in deep_dive.get("sources", [])
        if str(item.get("canonical_link") or item.get("original_link") or "").strip()
    ]
    full_text_sources: list[dict[str, str]] = []
    source_quotes: list[dict[str, str]] = []
    for item in deep_dive.get("sources", []):
        source_name = str(item.get("source_name") or "未知来源").strip()
        cleaned_full_text = str(item.get("cleaned_full_text") or "").strip()
        if cleaned_full_text:
            full_text_sources.append(
                {
                    "source_name": source_name,
                    "title": str(item.get("title") or "").strip(),
                    "full_text": cleaned_full_text,
                }
            )
        for quote in item.get("quotes", [])[:1]:
            compact = str(quote).strip()
            if compact:
                source_quotes.append({"source_name": source_name, "quote": compact})
    worth_reason = str(deep_dive.get("worthiness", {}).get("reason") or "").strip()
    risk_notes: list[str] = []
    if deep_dive.get("status") in {"partial", "failed"}:
        risk_notes.append("仅完成部分正文核验，部分来源抓取或提取失败。")
    if not facts:
        risk_notes.append("当前事实仍偏少，建议继续人工核验来源。")
    if worth_reason:
        risk_notes.append(worth_reason)
    one_line = facts[0] if facts else (str(event.get("summary") or "").strip() or "信息仍待进一步确认。")
    why_it_matters = worth_reason or f"当前事件处于 {event.get('alert_state') or '观察'} 阶段，具备继续追踪价值。"
    summary = build_brief_summary(
        one_line=one_line,
        facts=facts,
        event_summary=str(event.get("summary") or "").strip(),
    )
    writing_guide = build_agent_article_writing_guide()
    prompt_package_markdown = build_prompt_package_markdown(
        title=title,
        one_line=one_line,
        why_it_matters=why_it_matters,
        facts=facts,
        full_text_sources=full_text_sources[:4],
        source_quotes=source_quotes[:4],
        timeline=timeline,
        risk_notes=risk_notes,
        source_links=source_links,
        article_writing_guide=writing_guide,
    )
    wechat_markdown = build_short_brief_markdown(event, deep_dive)
    douyin_title = build_douyin_title(title)
    douyin_summary = build_douyin_summary(summary or one_line, douyin_title or title)
    douyin_markdown = build_douyin_article_markdown(
        title=douyin_title or title,
        summary=douyin_summary,
        article_markdown=wechat_markdown,
        one_line=one_line,
        why_it_matters=why_it_matters,
        facts=facts[:6],
        quotes=quotes[:4],
        timeline=timeline[:6],
        source_links=source_links[:10],
    )
    douyin_prompt_package_markdown = build_douyin_prompt_package_markdown(
        title=title,
        one_line=one_line,
        why_it_matters=why_it_matters,
        facts=facts[:6],
        full_text_sources=full_text_sources[:4],
        source_quotes=source_quotes[:4],
        timeline=timeline[:6],
        risk_notes=risk_notes[:5],
        source_links=source_links[:10],
        article_markdown=wechat_markdown,
    )
    return {
        "title": title,
        "one_line": one_line,
        "why_it_matters": why_it_matters,
        "summary": summary,
        "facts": facts[:6],
        "quotes": quotes[:4],
        "timeline": timeline[:6],
        "entity_names": list(event.get("entity_names", [])),
        "source_links": source_links[:10],
        "risk_notes": risk_notes[:5],
        "article_writing_guide": writing_guide,
        "prompt_package_markdown": prompt_package_markdown,
        "wechat_markdown": wechat_markdown,
        "douyin_prompt_package_markdown": douyin_prompt_package_markdown,
        "douyin_title": douyin_title,
        "douyin_summary": douyin_summary,
        "douyin_markdown": douyin_markdown,
    }


def _deep_dive_source_links(deep_dive: dict[str, Any]) -> list[str]:
    links: list[str] = []
    for item in deep_dive.get("sources", []):
        if not isinstance(item, dict):
            continue
        link = str(item.get("canonical_link") or item.get("original_link") or "").strip()
        if link:
            links.append(link)
    return list(dict.fromkeys(links))


def _daily_digest_date_label() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _daily_digest_chinese_date_label() -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    return f"{now.year}年{now.month}月{now.day}日"


def _is_douyin_daily_news_internal_text(value: str) -> bool:
    compact = _normalize_compact_text(_remove_inline_markdown(value))
    if not compact:
        return True
    if _is_url_only(compact):
        return True
    return any(re.search(pattern, compact, flags=re.IGNORECASE) for pattern in _DOUYIN_DAILY_NEWS_INTERNAL_PATTERNS)


def _clean_douyin_daily_news_sentence(value: str, *, limit: int = 120) -> str:
    compact = _normalize_compact_text(_remove_inline_markdown(value))
    compact = re.sub(r"https?://\S+", "", compact).strip()
    compact = re.sub(r"^[\u4e00-\u9fffA-Za-z0-9·（）()《》]{2,18}(?:提到|报道|称|消息|获悉)[:：]\s*", "", compact)
    compact = compact.strip(" \t\r\n-—_|｜/\\:：;；，,。")
    if not compact or _is_douyin_daily_news_internal_text(compact):
        return ""
    sentence = _pick_first_sentence(compact) or compact
    sentence = sentence.strip(" \t\r\n-—_|｜/\\:：;；，,。")
    if not sentence or _is_douyin_daily_news_internal_text(sentence):
        return ""
    return _trim_to_limit(sentence, limit)


def _douyin_daily_news_display_title(value: str, *, limit: int = 80) -> str:
    title = _normalize_compact_text(_remove_inline_markdown(value))
    title = re.sub(r"https?://\S+", "", title).strip(" \t\r\n-—_|｜/\\:：;；，,。")
    if len(title) <= limit:
        return title
    for marker in ("。", "！", "？", "；", "，", "、"):
        prefix = title[:limit].rsplit(marker, 1)[0].strip(" ，,、:：;；-")
        if len(prefix) >= 18:
            return prefix
    return _trim_to_limit(title, limit)


def _douyin_daily_news_focus_title(value: str, *, limit: int = 28) -> str:
    title = _normalize_compact_text(value)
    if len(title) <= limit:
        return title
    for marker in ("：", ":", "｜", "|", "，", "、", " "):
        prefix = title.split(marker, 1)[0].strip(" ，,、:：;；-")
        if 4 <= len(prefix) <= limit:
            return prefix
    for marker in ("。", "！", "？", "；", "，", "、"):
        prefix = title[:limit].rsplit(marker, 1)[0].strip(" ，,、:：;；-")
        if len(prefix) >= 8:
            return prefix
    return _trim_to_limit(title, limit)


def _douyin_daily_news_source_texts(deep_dive: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for source in deep_dive.get("sources", []):
        if not isinstance(source, dict):
            continue
        for key in ("cleaned_full_text", "summary", "title"):
            text = str(source.get(key) or "").strip()
            if text:
                texts.append(text)
    return texts


def _extract_douyin_daily_news_codes(value: str) -> set[str]:
    compact = _normalize_compact_text(value).upper()
    return set(re.findall(r"\b[A-Z]{1,8}\d{2,8}[A-Z0-9-]*\b", compact))


def _conflicts_with_douyin_daily_news_title(candidate: str, event_title: str) -> bool:
    title_codes = _extract_douyin_daily_news_codes(event_title)
    if not title_codes:
        return False
    candidate_codes = _extract_douyin_daily_news_codes(candidate)
    return bool(candidate_codes - title_codes)


def _pick_douyin_daily_news_detail(
    event: dict[str, Any],
    deep_dive: dict[str, Any],
    event_facts: list[str],
    event_title: str,
) -> str:
    candidates: list[str] = []
    candidates.extend(event_facts)
    candidates.extend(_douyin_daily_news_source_texts(deep_dive))
    candidates.extend([str(event.get("summary") or ""), str(deep_dive.get("summary") or "")])

    normalized_title = _normalize_compact_text(event_title)
    for candidate in candidates:
        sentence = _clean_douyin_daily_news_sentence(candidate)
        if not sentence:
            continue
        if _conflicts_with_douyin_daily_news_title(sentence, normalized_title):
            continue
        if normalized_title and sentence == normalized_title:
            continue
        if normalized_title and sentence.startswith(normalized_title):
            tail = sentence[len(normalized_title) :].strip(" ，,、:：;；-")
            if tail and not _is_douyin_daily_news_internal_text(tail):
                return _trim_to_limit(tail, 120)
        return sentence
    return "这条消息已经进入今日信息池，但关键细节还要等更多来源补齐。"


def _pick_douyin_daily_news_details(
    event: dict[str, Any],
    deep_dive: dict[str, Any],
    event_facts: list[str],
    event_title: str,
    *,
    limit: int = 2,
) -> list[str]:
    details: list[str] = []
    candidates: list[str] = []
    candidates.extend(event_facts)
    candidates.extend(_douyin_daily_news_source_texts(deep_dive))
    candidates.extend([str(event.get("summary") or ""), str(deep_dive.get("summary") or "")])
    normalized_title = _normalize_compact_text(event_title)
    seen: set[str] = set()
    for candidate in candidates:
        sentence = _clean_douyin_daily_news_sentence(candidate)
        if not sentence:
            continue
        if _conflicts_with_douyin_daily_news_title(sentence, normalized_title):
            continue
        if normalized_title and sentence == normalized_title:
            continue
        if normalized_title and sentence.startswith(normalized_title):
            tail = sentence[len(normalized_title) :].strip(" ，,、:：;；-")
            if tail and not _is_douyin_daily_news_internal_text(tail):
                sentence = _trim_to_limit(tail, 120)
        key = _normalize_compact_text(sentence)
        if not key or key in seen:
            continue
        seen.add(key)
        details.append(sentence)
        if len(details) >= limit:
            break
    if details:
        return details
    return [_pick_douyin_daily_news_detail(event, deep_dive, event_facts, event_title)]


def _douyin_daily_news_watch_phrase(event: dict[str, Any]) -> str:
    tags = [str(item).strip() for item in event.get("tags", []) if str(item).strip()]
    title = str(event.get("title") or "")
    text = " ".join([title, *tags]).lower()
    if any(keyword in text for keyword in ("芯片", "半导体", "gpu", "pcie", "固态", "存储")):
        return "这背后最该看的是供应链、性能和量产节奏会不会真的跟上。"
    if any(keyword in text for keyword in ("ai", "大模型", "token", "agent", "gemini", "openai")):
        return "这背后最该看的是 AI 能力会不会真正变成用户和企业能用上的产品。"
    if any(keyword in text for keyword in ("机器人", "自动驾驶", "无人", "具身")):
        return "这背后最该看的是它能不能从演示走到真实场景里稳定干活。"
    if any(keyword in text for keyword in ("航天", "火箭", "spacex", "星舰", "卫星")):
        return "这背后最该看的是下一次验证能不能把商业化和规模化再往前推一步。"
    return "这件事后续最该看的是它能不能真正落到产品、价格或产业链变化上。"


def _build_douyin_daily_news_paragraph(index: int, event_title: str, detail: str) -> str:
    ordinal = _DOUYIN_DAILY_NEWS_ORDINALS[index - 1] if index <= len(_DOUYIN_DAILY_NEWS_ORDINALS) else f"第{index}条，"
    title_text = _normalize_compact_text(event_title)
    detail_text = _normalize_compact_text(detail)
    if detail_text and title_text and detail_text not in title_text:
        return f"{ordinal}{title_text}！{detail_text}，这件事后续最该看的是它能不能真正落到产品、价格或产业链变化上。"
    return f"{ordinal}{title_text}！这件事后续最该看的是它能不能真正落到产品、价格或产业链变化上。"


def _build_douyin_daily_news_story_paragraph(
    index: int,
    event: dict[str, Any],
    deep_dive: dict[str, Any],
    event_facts: list[str],
    event_title: str,
) -> str:
    ordinal = _DOUYIN_DAILY_NEWS_ORDINALS[index - 1] if index <= len(_DOUYIN_DAILY_NEWS_ORDINALS) else f"第{index}条，"
    title_text = _normalize_compact_text(event_title)
    details = _pick_douyin_daily_news_details(event, deep_dive, event_facts, event_title)
    proof = "；".join(details)
    watch_phrase = _douyin_daily_news_watch_phrase(event)
    if proof and title_text and proof not in title_text:
        return f"{ordinal}{title_text}！{proof}，{watch_phrase}"
    return f"{ordinal}{title_text}！{watch_phrase}"


def _normalize_douyin_daily_news_body(lines: list[str]) -> str:
    body = "\n\n".join(line.strip() for line in lines if str(line or "").strip()).strip()
    return re.sub(r"\n{3,}", "\n\n", body)


def build_douyin_daily_news_markdown(
    qualified: list[tuple[dict[str, Any], dict[str, Any], list[str], list[str]]],
    *,
    title: str = "今日5条科技要闻",
    max_items: int = 5,
) -> tuple[str, str, str]:
    """Build a Douyin-first daily tech-news roundup from verified events."""
    selected = qualified[:max_items]
    count = len(selected)
    douyin_title = _trim_to_limit(title, DOUYIN_TITLE_LIMIT)
    douyin_summary = _trim_to_limit(f"整理今日最值得关注的 {count} 条科技要闻", DOUYIN_SUMMARY_LIMIT)
    date_label = _daily_digest_chinese_date_label()
    lines = [
        f"朋友们，今天咱们来盘一盘{date_label}最值得关注的{count}条科技要闻，每一条都可能影响接下来的科技走向！",
    ]

    closing_titles: list[str] = []
    for index, (event, deep_dive, event_facts, _event_links) in enumerate(selected, start=1):
        event_title = _douyin_daily_news_display_title(str(event.get("title") or deep_dive.get("title") or f"科技要闻 {index}"))
        lines.append(_build_douyin_daily_news_story_paragraph(index, event, deep_dive, event_facts, event_title))
        closing_titles.append(event_title)

    if closing_titles:
        focus_titles = "，".join(_douyin_daily_news_focus_title(item) for item in closing_titles[:2])
        lines.append(f"朋友们，这{count}条新闻里，你最关心哪一个？是{focus_titles}，还是后面这些新变化？评论区聊聊你的看法呀！")

    body = _normalize_douyin_daily_news_body(lines)
    return douyin_title, douyin_summary, ensure_markdown_title(body, douyin_title)


def build_daily_digest_brief_payload(events: list[dict[str, Any]], deep_dives: list[dict[str, Any]]) -> dict[str, Any]:
    """Build one rule-only WeChat digest from multiple already-verified events."""
    def _clean_values(value: Any) -> list[str]:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, (list, tuple, set)):
            candidates = value
        else:
            return []
        return [str(item).strip() for item in candidates if str(item).strip()]

    deep_dive_by_event = {str(item.get("event_id") or ""): item for item in deep_dives if isinstance(item, dict)}
    qualified: list[tuple[dict[str, Any], dict[str, Any], list[str], list[str]]] = []
    for event in events:
        event_id = str(event.get("id") or "").strip()
        if not event_id or bool(event.get("ignored")):
            continue
        deep_dive = deep_dive_by_event.get(event_id)
        if not deep_dive or str(deep_dive.get("status") or "") not in {"ready", "partial"}:
            continue
        facts = [str(item).strip() for item in deep_dive.get("facts", []) if str(item).strip()]
        summary = str(event.get("summary") or "").strip()
        source_links = _deep_dive_source_links(deep_dive)
        if not source_links or not (facts or summary):
            continue
        qualified.append((event, deep_dive, facts, source_links))
        if len(qualified) >= 5:
            break

    if len(qualified) < 5:
        raise ValueError("今日短讯合集必须由 5 条合格事件组成。")

    date_label = _daily_digest_date_label()
    title = f"今日科技速递｜{date_label}"
    facts: list[str] = []
    timeline: list[str] = []
    risk_notes: list[str] = []
    source_links: list[str] = []
    entity_names: list[str] = []
    tags: list[str] = []
    alert_states: list[str] = []
    section_lines: list[str] = []
    source_lines: list[str] = []

    for index, (event, deep_dive, event_facts, event_links) in enumerate(qualified, start=1):
        event_title = str(event.get("title") or deep_dive.get("title") or f"事件 {index}").strip()
        first_fact = event_facts[0] if event_facts else str(event.get("summary") or "").strip()
        worth_reason = str(deep_dive.get("worthiness", {}).get("reason") or "").strip()
        uncertainty: list[str] = []
        if str(deep_dive.get("status") or "") == "partial":
            uncertainty.append("部分来源仍需继续核验")
        if int(event.get("source_count", 0) or 0) <= 1:
            uncertainty.append("当前来源仍偏少")

        section_lines.extend(["", f"## {index}. {event_title}", first_fact])
        if worth_reason:
            section_lines.append(worth_reason)
        if uncertainty:
            section_lines.append("不确定项：" + "；".join(list(dict.fromkeys(uncertainty))) + "。")

        facts.append(first_fact)
        facts.extend(event_facts[1:2])
        timeline.extend([str(item).strip() for item in deep_dive.get("timeline", []) if str(item).strip()][:1])
        risk_notes.extend(uncertainty)
        entity_names.extend(_clean_values(event.get("entity_names")))
        tags.extend(_clean_values(event.get("tags")))
        alert_state = str(event.get("alert_state") or "").strip().lower()
        if alert_state:
            alert_states.append(alert_state)
        for link in event_links[:2]:
            source_links.append(link)
            source_lines.append(f"- {event_title}：{link}")

    unique_links = list(dict.fromkeys(source_links))[:10]
    unique_entities = list(dict.fromkeys(entity_names))[:12]
    unique_tags = list(dict.fromkeys(tags))[:8]
    unique_risks = list(dict.fromkeys(risk_notes))[:5]
    summary = "今日筛选出 5 条值得关注的科技动态。"
    one_line = summary
    why_parts = [summary.rstrip("。")]
    if len(unique_entities) >= 3:
        why_parts.append(f"涉及 {'、'.join(unique_entities[:3])} 等主体的动态")
    elif unique_entities:
        why_parts.append(f"涉及 {'、'.join(unique_entities[:3])} 的动态")
    if unique_tags:
        tag_suffix = "等方向" if len(unique_tags) > 3 else "方向"
        why_parts.append(f"覆盖 {'、'.join(unique_tags[:3])} {tag_suffix}")
    breakout_count = alert_states.count("breakout")
    rising_count = alert_states.count("rising")
    status_parts: list[str] = []
    if breakout_count:
        status_parts.append(f"{breakout_count} 条处于爆发状态")
    if rising_count:
        status_parts.append(f"{rising_count} 条处于上升状态")
    if status_parts:
        why_parts.append("其中 " + "、".join(status_parts))
    why_it_matters = "，".join(why_parts) + "，组成一篇完整短讯合集。"
    wechat_markdown = "\n".join(
        [
            f"# {title}",
            "",
            why_it_matters,
            *section_lines,
            "",
            "## 来源链接",
            *list(dict.fromkeys(source_lines))[:10],
        ]
    ).strip()
    douyin_title, douyin_summary, douyin_markdown = build_douyin_daily_news_markdown(qualified)
    prompt_package_markdown = build_prompt_package_markdown(
        title=title,
        one_line=one_line,
        why_it_matters=why_it_matters,
        facts=facts[:8],
        full_text_sources=[],
        source_quotes=[],
        timeline=timeline[:8],
        risk_notes=unique_risks,
        source_links=unique_links,
        article_writing_guide=build_agent_article_writing_guide(),
    )
    douyin_prompt_package_markdown = build_douyin_prompt_package_markdown(
        title=title,
        one_line=one_line,
        why_it_matters=why_it_matters,
        facts=facts[:8],
        full_text_sources=[],
        source_quotes=[],
        timeline=timeline[:8],
        risk_notes=unique_risks,
        source_links=unique_links,
        article_markdown=wechat_markdown,
    )
    return {
        "included_event_ids": [str(event.get("id") or "") for event, _deep_dive, _facts, _links in qualified],
        "included_deep_dive_ids": [str(deep_dive.get("id") or "") for _event, deep_dive, _facts, _links in qualified],
        "title": title,
        "one_line": one_line,
        "why_it_matters": why_it_matters,
        "summary": summary,
        "facts": facts[:8],
        "quotes": [],
        "timeline": timeline[:8],
        "entity_names": unique_entities,
        "source_links": unique_links,
        "risk_notes": unique_risks,
        "prompt_package_markdown": prompt_package_markdown,
        "wechat_markdown": wechat_markdown,
        "douyin_prompt_package_markdown": douyin_prompt_package_markdown,
        "douyin_title": douyin_title,
        "douyin_summary": douyin_summary,
        "douyin_markdown": douyin_markdown,
    }


def build_short_brief_markdown(event: dict[str, Any], deep_dive: dict[str, Any]) -> str:
    """Build a rule-only WeChat short brief without asking an LLM to rewrite facts."""
    title = str(event.get("title") or deep_dive.get("title") or "未命名事件").strip()
    facts = [str(item).strip() for item in deep_dive.get("facts", []) if str(item).strip()]
    source_links = [
        str(item.get("canonical_link") or item.get("original_link") or "").strip()
        for item in deep_dive.get("sources", [])
        if isinstance(item, dict) and str(item.get("canonical_link") or item.get("original_link") or "").strip()
    ]
    worth_reason = str(deep_dive.get("worthiness", {}).get("reason") or "").strip()
    one_line = facts[0] if facts else (str(event.get("summary") or "").strip() or "信息仍待进一步确认。")
    why_it_matters = worth_reason or f"当前事件处于 {event.get('alert_state') or '观察'} 阶段，具备继续追踪价值。"

    uncertainty: list[str] = []
    if deep_dive.get("status") in {"partial", "failed"}:
        uncertainty.append("仅完成部分正文核验，部分来源抓取或提取失败。")
    if not facts:
        uncertainty.append("当前事实仍偏少，建议继续人工核验来源。")
    if int(event.get("source_count", 0) or 0) <= 1:
        uncertainty.append("当前来源仍偏少，后续判断需要等待更多信源交叉确认。")
    if not source_links:
        uncertainty.append("当前缺少可追溯来源链接，暂不应当作完整可发布稿。")

    lines = [
        f"# {title}",
        "",
        f"一句话：{one_line}",
        "",
        "## 核心事实",
    ]
    if facts:
        lines.extend(facts[:3])
    else:
        lines.append("暂无足够正文事实，请继续核验。")

    lines.extend(["", "## 这意味着什么", why_it_matters])
    lines.extend(["", "## 还不确定什么"])
    if uncertainty:
        lines.extend([f"- {item}" for item in list(dict.fromkeys(uncertainty))])
    else:
        lines.append("- 暂未发现额外不确定项，但仍需以来源后续更新为准。")

    lines.extend(["", "## 来源链接"])
    if source_links:
        lines.extend([f"- {item}" for item in source_links[:3]])
    else:
        lines.append("- 暂无来源链接")
    return "\n".join(lines).strip()


def build_agent_article_writing_guide() -> str:
    banned_phrases = "、".join(_AI_STYLE_BANNED_PHRASES)
    return f"""\
## 公众号文章写作规范

### 你是谁
你是一位在科技媒体行业深耕多年的资深记者，为微信公众号撰写深度科技分析文章。
你的写作不是汇报材料、不是论文，也不是为了凑字数的长文。你需要先判断当前事件适合短讯、长文，还是不写。

### 核心写作目标
- 目标是有事实纪律的强表达：事实准确是底线，表达要有点击理由、观点锋芒和普通人能感到的利益关系。
- 标题必须优先制造点击理由，而不是概括栏目名；读者一眼要知道为什么这和自己有关。
- 开头 80 字内必须回答：这件事和普通人、开发者、消费者、公司账单或未来设备有什么关系。
- 正文每个信息点都要用大白话解释“这是什么概念”“可能影响谁”“现在还不能确定什么”。
- 允许有冲突感、利益关系、悬念和口语表达，也可以写“开始让人付账”“谁会被迫改规则”“下一代入口正在抢位”这类判断句。
- 强表达的边界：不能把推测写成确定事实，不能把个体案例写成普遍结论，不能承诺素材没有证明的未来结果。
- 对泄露、传闻、媒体转述、个体反馈、测试中产品，必须保留“据报道”“有消息称”“还要等官方确认”“个体反馈不代表所有用户”等限定词。

### 先判断内容形态
不要默认写长文。先根据事件热度、来源数量、事实完整度和读者价值选择形态：

1. 不写
   - 来源不足、时间过旧、只是重复消息、没有明确读者价值，或者关键事实无法确认。
2. 短讯合集
   - 适合多数日常信息流。
   - 必须由 5 条相互衔接的科技要闻组成一篇完整文章，每条 2-3 句。
   - 单个事件不能叫短讯；单个事件只能写成长文、单事件快讯素材，或不写。
3. 长文
   - 只适合重大事件、复杂政策/产品变化、多来源冲突、需要对比分析或读者确实需要一次性搞懂的话题。
4. 混合
   - 当天有一个主事件和多个小事件时，可以写一篇长文加一篇 5 条短讯合集。

### 字数要求
- 短讯合集：由 5 条科技要闻组成，整体约 600-1000 字，不含来源链接。
- 长文：800-1000 字，不含标题、摘要和来源链接。

### 短讯合集结构
短讯不是单事件小长文。它必须像“今日5条科技要闻”一样，把 5 个信息点连成一篇完整速递。每条只回答三个问题：

1. 发生了什么？
2. 为什么值得看？
3. 现在还不能下什么结论？

本地审阅稿可以使用下面这种结构，方便核对事实和来源：

```markdown
# 今日科技速递｜YYYY-MM-DD

今天整理 5 条最值得关注的科技要闻，每条只说发生了什么、为什么该看、还要等什么确认。

## 1. 事件标题
2-3 句：发生了什么 + 为什么值得看 + 还不确定什么。

## 2. 事件标题
2-3 句。

## 3. 事件标题
2-3 句。

## 4. 事件标题
2-3 句。

## 5. 事件标题
2-3 句。

## 来源链接
- https://example.com
```

但发到微信、抖音或其他平台前，必须再润色成自然连贯的发布稿。发布稿不是后台素材卡，也不是 Markdown 目录；它应该像编辑直接讲给读者听：

```markdown
# 今日科技速递｜YYYY-MM-DD

朋友们，今天咱们不聊长篇大论，直接盘 5 条最近最值得关注的科技小新闻，全是干货。

首先是[事件1]——[发生了什么]。[为什么值得看]，不过[还不确定什么]。

然后是[事件2]——[发生了什么]。[为什么值得看]，但[还不确定什么]。

接下来是[事件3]——[发生了什么]。[为什么值得看]，还要等[不确定项]确认。

再说[事件4]——[发生了什么]。[为什么值得看]，风险在于[不确定项]。

最后是[事件5]——[发生了什么]。[为什么值得看]，后续还要观察[不确定项]。

这 5 条其实都指向同一个趋势：[用一句话收束共同趋势]。
```

平台发布稿要求：
- 不要保留 `## 1.`、`## 来源链接`、裸 URL 列表。
- 不要出现“核心事实”“这意味着什么”“还不确定什么”这类后台字段名。
- 5 条之间要用“首先 / 然后 / 接下来 / 再说 / 最后”自然衔接。
- 每条仍然必须包含事实、意义和不确定项，不能为了口语化丢掉事实纪律。
- 如果只完成了结构化素材稿，还不能上传，只能保存到本地。

可直接交给 AI 的短讯润色提示词：

```text
你会收到一份“本地短讯素材稿”，里面有 5 条科技新闻、事实、不确定项和来源。请把它改写成适合平台发布的一篇完整短讯合集。

目标风格：
- 像编辑在直接讲给读者听，口语自然，有冲突感和利益关系，但不要假确定。
- 不要写成长文分析，也不要写成机械列表。
- 一篇文章必须正好包含 5 条信息，不能少于 5 条，也不能把单条新闻写成短讯。

结构要求：
1. 开头用 1-2 句话直接抛出共同钩子，例如“AI 正从聊天框钻进电脑、账单、出行和随身设备里”。
2. 正文用“首先 / 然后 / 接下来 / 再说 / 最后”自然串联 5 条。
3. 每条用 2-4 句说清：发生了什么、普通人怎么理解、可能影响谁、还不确定什么。
4. 结尾用 1 段收束 5 条新闻共同指向的趋势。

禁止事项：
- 不要保留 `## 1.`、`## 来源链接`、裸 URL、素材包字段名。
- 不要出现“核心事实”“这意味着什么”“还不确定什么”这种后台栏目名。
- 不要新增素材里没有的数字、日期、价格、人名、产品能力。
- 不要把“可能”“预计”“测试中”写成已经确定发生。
- 不要把单个开发者反馈、单份研报、单地价格变化写成所有人都会立刻遇到的结果。

输入：
{{本地短讯素材稿}}

输出：
只输出平台发布稿 Markdown。标题用 `#`，正文只保留自然段，不要附来源链接列表。
```

短讯合集禁止事项：
- 不要把单个事件写成一篇短讯上传。
- 不要少于 5 条；如果不足 5 条合格事件，宁可不生成短讯合集。
- 不要为了凑字数写行业大背景。
- 不要把单一事实包装成趋势判断。
- 不要编造未来影响。
- 不要省略不确定项。

### 标题策略（决定打开率）
- 字数 14-25 字，前 14 字必须放最关键的信息点，避免折叠后失真
- 标题不要写成“今日科技速递”“5条科技小新闻”这类栏目名，除非后半句已经给出强钩子。
- 标题至少包含一个具体信息点：公司名、人名、数字、产品名
- 标题中的每个信息点必须在正文或素材中找到对应事实，不做标题党
- 标题优先选择“谁要付账”“谁被迫改规则”“普通人会感到什么变化”“旧格局哪里被挑战”这类利益或冲突角度
- 禁止使用”重磅””震惊””值得关注””引发热议”等空洞词汇
- 从以下公式中选择最适合当前事件的 1 种，生成 2-3 个备选标题：
  1. 数字冲击型：[公司] + [具体数字] + [事件后果]
     例：”OpenAI 完成 65 亿美元融资，估值突破 1500 亿”
  2. 反常识型：[违背常识的结论] + [事实支撑]
     例：”市值蒸发 2000 亿后，英伟达反而更值钱了”
  3. 身份代入型：[读者身份] + [与自身相关的变化]
     例：”开发者注意：GitHub Copilot 新规影响你的工作流”
  4. 悬念留白型：[事件前半段]，[暗示后续影响]
     例：”苹果刚发布的 AI 功能，可能改变整个行业格局”
  5. 对比冲突型：[A] vs [B]，[出人意料的结果]
     例：”实测 20 个场景：Claude 4 和 GPT-5 谁更强？”
  6. 直述事实型：刚刚/确认 + [核心事实]
     例：”确认：谷歌发布 Gemini 2.0，多模态能力翻倍”
  7. 付账/代价型：[变化] + [谁开始付账/承压]
     例：”AI 账单变贵了，开发者先感受到压力”
  8. 入口争夺型：[公司/产品] + [正在抢的入口]
     例：”Meta 想把 AI 入口挂到你身上”

### 摘要（推送时显示在标题下方，约 50 字）
- 摘要与标题互补，不重复标题
- 摘要优先补充 Why 或 How，而不只是重复 What
- 控制在 40-60 字，至少包含一个标题里没有的新信息点
- 例——标题”OpenAI 完成 65 亿美元融资”的摘要：”Thrive Capital 领投，微软跟投，创 AI 领域单轮融资记录”

### 长文结构（按顺序，用过渡句自然衔接）

**第一部分：导语（50-80 字，2-3 句）**
- 第一句必须是具体事实、数字或时间点，不要以宏大背景开头
- 第二句说明这件事意味着什么，为什么与读者有关；优先写普通人能感到的入口、账单、设备、工作流、出行、隐私或安全变化
- 导语不能只是“今天整理几条新闻”，必须给出一个共同钩子或冲突

**第二部分：背景与冲突（80-120 字）**
- 交代技术、商业或政策背景
- 必须呈现一个张力或冲突点：竞争格局、技术路线分歧、利益博弈

**第三部分：核心展开（2-3 个小节，共 400-600 字）**
- 用 ## 小标题分隔，每节聚焦一个明确论点而非一个”维度”
- 小标题本身必须传达信息，不要写”技术分析””商业影响”等空泛分类
- 优先把数字、判断、转折写进小标题
- 每个小节内部遵循”事实 -> 分析 -> 这意味着什么”的递进
- 引用原文穿插在相关段落中（用 > 格式，紧跟 1-2 句解读），不超过 2 条

**第四部分：展望与收束（50-100 字）**
- 不要写”总结”或”总之”，而是给出一个前瞻性判断

**第五部分：来源链接**
- 列出 2-4 条核心来源 URL

### 引文与事实底线（最高优先级，违反即废稿）

**所有信息必须可溯源，禁止编造任何内容。**

- 正文中出现的每一个数据、金额、百分比、日期、人名、公司名、产品名，必须来自深挖素材或你亲自核实过的公开来源
- 禁止编造数据：如果你不确定某个具体数字，不要猜。改写为定性描述或直接省略
  - 禁止：”融资 12 亿美元”（如果素材里没有这个数字）
  - 允许：”完成新一轮融资”（不编造金额）
  - 更好：”完成新一轮融资，具体金额未披露”
- 禁止编造引文：所有引号内的内容必须来自素材中的原文摘录，不可改写后放入引号
- 禁止编造人名、头衔、机构名：如果素材中只提到”某高管”，不要替他编造姓名
- 禁止拼凑时间线：日期和事件顺序必须与素材一致，不要为了叙事方便调整时间先后
- 你的网络研究补充内容同样必须真实可查。如果无法确认，用”据公开报道””有消息称”等限定词标注不确定性
- 区分事实与分析：事实用陈述句，分析用”这意味着””这表明”等引入语

### 写作风格

**信息密度**
- 每个段落必须包含至少一个具体事实、数据或引述
- 不允许出现只说空话、不提供新信息的段落
- 如果一段话删掉后读者不会少知道任何东西，这段话就不应该存在

**段落节奏**
- 段落长度必须有变化：允许 1 句成段的短段落制造冲击力，也允许 4-5 句的分析段落
- 禁止连续出现长度和结构相似的段落（这是 AI 写作最明显的标志）
- 每 2-3 个事实密集段落后，跟一段稍长的分析或解释作为节奏缓冲
- 全文至少设置一个”注意力高点”——一个让人忍不住截图发朋友圈的句子或数据

**数据使用**
- 多用阿拉伯数字和对比参照，例如”比去年降了 60%”，少用”显著提升””大幅增长”这类空泛表述
- 关键数据放段落首句或单独成段加粗

**技术术语**
- 首次出现时用括号做简短效果解释，不超过 15 字
- 解释用效果描述而非技术定义（”MoE（一种让模型只激活部分参数以降低成本的架构）”）

**视觉节奏**
- 段落之间保留一个空行
- 加粗只用于关键数据或核心判断，全文加粗不超过 5 处

### 格式要求
- Markdown 格式输出
- # 一级标题只用一次
- ## 二级标题用于小节分隔，且标题本身要有信息量
- > 仅用于引用原文，引文后必须紧跟 1-2 句解读
- - 仅用于来源链接列表
- 段落之间保留一个空行

### 禁止事项

**禁止出现的 AI 味写法：**
- 禁止以宏大背景开头（”在AI飞速发展的今天”、”随着大模型技术的不断演进”）
- 禁止空洞评价（”值得关注”、”引发了广泛关注”、”具有重要意义”、”不言而喻”）
- 禁止路标式过渡（”接下来我们来看看”、”让我们深入探讨”、”下面将详细介绍”）
- 禁止”不仅是X，更是Y”和”这不只是X，还关乎Y”的虚假对比句式
- 禁止总结套话（”综上所述”、”总而言之”、”总的来说”）
- 禁止用编号列表或 bullet-point 替代段落论述（这是文章不是PPT）
- 禁止正文堆砌来源链接
- 禁止每段结构完全一致（是什么->为什么->怎么做的三段式重复）
- 禁止出现”本文将从以下几个方面展开”之类的元描述
- 禁止过度使用”然而”、”与此同时”、”值得注意的是”等过渡词
- 禁止虚假确定：不能写“马上普及”“彻底改变”“再也不会卡顿”“不用担心安全问题”等素材没有证明的承诺
- 禁止把局部现象放大全局：例如个体账单、单地价格、测试城市、传闻产品，不能写成所有用户已经受到同等影响

**禁止出现这些高频 AI 味词或近义表达：{banned_phrases}
- 如果一个词在政府工作报告中经常出现，不要用在科技新闻正文中

### 自检清单（写完后逐项检查）
- [ ] 删掉第一段后，文章是否仍然成立？如果是，重写导语
- [ ] 是否有连续 3 段以上的段落长度和结构几乎一致？如果有，打破它
- [ ] 是否存在”说了半天什么新信息都没给”的段落？删掉它
- [ ] 每个小标题是否传达了具体信息而不是空泛分类？
- [ ] 小节之间是否有自然的过渡而不是生硬跳转？
- [ ] 文章是否有至少一个让读者想截图分享的句子或数据？
- [ ] 逐条检查所有数字、金额、百分比——每一个都能在素材或公开来源中找到依据吗？
- [ ] 逐条检查所有引号内容——每一条都是原文摘录而非你的改写吗？"""
