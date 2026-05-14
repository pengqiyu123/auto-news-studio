from __future__ import annotations

import re
from typing import Any


WECHAT_TITLE_LIMIT = 64
WECHAT_TITLE_HOOK_LIMIT = 28
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
) -> str:
    lines = [
        "## 写作任务",
        "基于以下已核验素材，写一篇公众号文章。",
        "",
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
    ]
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
    return {
        "title": title,
        "one_line": one_line,
        "why_it_matters": why_it_matters,
        "facts": facts[:6],
        "quotes": quotes[:4],
        "timeline": timeline[:6],
        "entity_names": list(event.get("entity_names", [])),
        "source_links": source_links[:10],
        "risk_notes": risk_notes[:5],
        "prompt_package_markdown": prompt_package_markdown,
        "wechat_markdown": "\n".join(wechat_lines).strip(),
    }


def build_agent_article_writing_guide() -> str:
    return """\
## 公众号文章写作规范

### 字数要求
正文 1500-3000 字。不含标题和来源链接。

### 文章结构（按顺序）
1. **标题** — 吸引眼球但不标题党，20 字以内
   优先写成“核心事实 + 结果/影响”的双段式标题，避免“某公司发布新产品”这种平铺直叙
2. **导语** — 2-3 句话概括核心事实和影响，让读者 10 秒内决定是否继续读
3. **背景铺垫** — 1-2 段，交代事件的技术/商业/政策背景，让非专业读者也能跟上
4. **核心事实展开** — 2-4 个小节（用 ## 小标题），每节聚焦一个维度：
   - 技术细节（用了什么、怎么实现的）
   - 商业影响（对行业格局、股价、竞争的意义）
   - 用户/社会影响（对普通人的实际影响）
   - 关键数据（具体数字、百分比、金额）
5. **引文分析** — 引用 1-3 条关键原文，用 > 引用格式，然后加 1-2 句你的解读
6. **影响展望** — 未来走向、可能的后续发展、值得持续关注的点
7. **来源链接** — 列出 3-6 条核心来源 URL

### 写作风格
- 专业但易懂，类似 36 氪/极客公园/极客公园风格
- 多用具体数字（"融了 12 亿美元"），少用空泛形容词（"具有重要意义"）
- 每段 3-5 句话，不要出现超过 200 字的超长段落
- 适当使用 **加粗** 标记关键信息，但不要满篇加粗
- 技术术语第一次出现时用括号简短解释

### 格式要求
- Markdown 格式
- # 一级标题只用一次（文章大标题）
- ## 二级标题用于小节分隔
- > 用于引用原文
- - 用于来源列表，不要在正文中堆砌链接
- 不要用编号列表替代段落论述

### 禁止事项
- 不要写 bullet-point 简报（这不是简报，是完整文章）
- 不要用"1. 2. 3."编号列表替代段落
- 不要在正文堆砌链接
- 不要以"总结：""总之："开头写结尾，自然收束即可
- 不要出现"本文将从以下几个方面展开"之类的套话开头
- 不要写"值得关注""引发关注"等空洞评价，用具体事实说话"""
