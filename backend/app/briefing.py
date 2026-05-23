from __future__ import annotations

import re
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
        "基于以下已核验素材，写一篇 1500-3000 字的公众号深度文章。",
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
- 正文建议 400-900 字，硬上限 1000 字
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
    wechat_lines = [
        f"# {title}",
        "",
        f"一句话：{one_line}",
        "",
        "## 核心事实",
    ]
    if facts:
        wechat_lines.extend([f"- {item}" for item in facts[:5]])
    else:
        wechat_lines.append("- 暂无足够正文事实，请继续核验。")
    if quotes:
        wechat_lines.extend(["", "## 关键引文"])
        for quote in quotes[:3]:
            wechat_lines.append(f"> {quote}")
    if timeline:
        wechat_lines.extend(["", "## 时间线"])
        wechat_lines.extend([f"- {item}" for item in timeline[:5]])
    if source_links:
        wechat_lines.extend(["", "## 来源链接"])
        wechat_lines.extend([f"- {item}" for item in source_links[:6]])
    wechat_markdown = "\n".join(wechat_lines).strip()
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


def build_agent_article_writing_guide() -> str:
    banned_phrases = "、".join(_AI_STYLE_BANNED_PHRASES)
    return f"""\
## 公众号文章写作规范

### 你是谁
你是一位在科技媒体行业深耕多年的资深记者，为微信公众号撰写深度科技分析文章。
你的写作不是汇报材料、不是论文、不是简报——而是一篇让普通读者愿意一口气读完的好文章。

### 字数要求
正文 1500-3000 字。不含标题、摘要和来源链接。

### 标题策略（决定打开率）
- 字数 14-25 字，前 14 字必须放最关键的信息点，避免折叠后失真
- 标题至少包含一个具体信息点：公司名、人名、数字、产品名
- 标题中的每个信息点必须在正文或素材中找到对应事实，不做标题党
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

### 摘要（推送时显示在标题下方，约 50 字）
- 摘要与标题互补，不重复标题
- 摘要优先补充 Why 或 How，而不只是重复 What
- 控制在 40-60 字，至少包含一个标题里没有的新信息点
- 例——标题”OpenAI 完成 65 亿美元融资”的摘要：”Thrive Capital 领投，微软跟投，创 AI 领域单轮融资记录”

### 文章结构（按顺序，用过渡句自然衔接）

**第一部分：导语（50-80 字，2-3 句）**
- 第一句必须是具体事实、数字或时间点，不要以宏大背景开头
- 第二句说明这件事意味着什么，为什么与读者有关

好的导语：
> 谷歌今天凌晨发布了 Gemini 2.0。多模态推理能力是上一代的 3 倍，API 调用价格降了一半。

差的导语：
> 在人工智能技术飞速发展的今天，谷歌再次震撼了整个行业，发布了备受瞩目的 Gemini 2.0 模型，标志着多模态AI进入了新的发展阶段。

**第二部分：背景与冲突（100-200 字）**
- 交代技术、商业或政策背景
- 必须呈现一个张力或冲突点：竞争格局、技术路线分歧、利益博弈

**第三部分：核心展开（3-5 个小节，共 1000-2000 字）**
- 用 ## 小标题分隔，每节聚焦一个明确论点而非一个”维度”
- 小标题本身必须传达信息，不要写”技术分析””商业影响”等空泛分类
- 优先把数字、判断、转折写进小标题，例如”推理成本降 60%，价格战正式打响”
- 每个小节内部遵循”事实 -> 分析 -> 这意味着什么”的递进
- 小节之间要有自然衔接，不要硬切
- 引用原文穿插在相关段落中（用 > 格式，紧跟 1-2 句解读），不要集中放在一个区块
- 只引用最有信息量的原文，不超过 3 条

**第四部分：展望与收束（100-200 字）**
- 不要写”总结”或”总之”，而是给出一个前瞻性判断
- 用以下方式之一自然收束：
  - 一句有力的判断（”这场价格战才刚刚开始，最终赢家可能不是模型最强的那一个”）
  - 对读者的直接提问（”你觉得这个变化会影响你的工作吗？”）
  - 前瞻暗示（”下周的 Google I/O 可能会有更多细节”）

**第五部分：来源链接**
- 列出 3-6 条核心来源 URL

### 事实底线（最高优先级，违反即废稿）

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
- 每 300-500 字设置一个”注意力高点”——一个让人忍不住截图发朋友圈的句子或数据

**数据使用**
- 多用阿拉伯数字和对比参照，例如”比去年降了 60%”，少用”显著提升””大幅增长”这类空泛表述
- 关键数据放段落首句或单独成段加粗

**技术术语**
- 首次出现时用括号做简短效果解释，不超过 15 字
- 解释用效果描述而非技术定义（”MoE（一种让模型只激活部分参数以降低成本的架构）”）

**视觉节奏**
- 段落之间保留一个空行
- 每 500 字左右标注一个配图建议位置：<!-- 配图建议：[图片内容描述] -->
- 加粗只用于关键数据或核心判断，全文加粗不超过 8 处

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
