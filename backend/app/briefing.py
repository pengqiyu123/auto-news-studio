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

_AI_STYLE_BANNED_PHRASES = (
    "在人工智能技术飞速发展的今天",
    "随着大模型技术的不断演进",
    "值得关注",
    "引发关注",
    "引发热议",
    "具有重要意义",
    "不言而喻",
    "接下来我们来看看",
    "让我们深入探讨",
    "下面将详细介绍",
    "本文将从以下几个方面展开",
    "综上所述",
    "总而言之",
    "总的来说",
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
        "基于以下已核验素材，写一篇公众号文章。",
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
        "wechat_markdown": "\n".join(wechat_lines).strip(),
    }


def build_agent_article_writing_guide() -> str:
    banned_phrases = "、".join(_AI_STYLE_BANNED_PHRASES)
    return f"""\
## 公众号文章写作规范

### 字数要求
正文 1500-3000 字。不含标题、摘要和来源链接。

### 标题策略（决定打开率）
- 标题长度 14-25 字，前 14 字必须放最关键的信息点，避免折叠后失真
- 标题至少包含一个具体信息点：公司名、人名、数字、产品名、价格、金额、时间点
- 优先使用“核心事实 + 结果/影响”的双段式，不要写平铺直叙的新闻播报标题
- 标题中的每个信息点必须在正文或素材中找到对应事实，不做标题党
- 禁止使用“重磅”“震惊”“值得关注”“引发热议”等空洞词汇

### 摘要（推送时显示在标题下方）
- 摘要与标题互补，不重复标题
- 摘要优先补充 Why 或 How，而不只是重复 What
- 控制在 40-60 字，至少包含一个标题里没有的新信息点

### 文章结构（按顺序，用过渡句自然衔接）
1. **导语**（50-80 字，2-3 句）
   - 第一句必须是具体事实、数字或时间点，不要以宏大背景开头
   - 第二句说明这件事意味着什么，为什么与读者有关
2. **背景与冲突**（100-200 字）
   - 交代技术、商业或政策背景
   - 必须呈现一个张力或冲突点，例如竞争格局、技术路线分歧、利益博弈
3. **核心展开**（3-5 个小节）
   - 用 ## 小标题分隔，每节聚焦一个明确论点，而不是泛泛维度
   - 每个小节内部遵循“事实 -> 分析 -> 这意味着什么”的递进
   - 小节之间要有自然衔接，不要硬切
4. **展望与收束**（100-200 字）
   - 不要写“总结”或“总之”
   - 回答“接下来会怎样”“读者该继续关注什么”
5. **来源链接**
   - 列出 3-6 条核心来源 URL

### 小标题要求
- 小标题本身必须传达信息，不要写“技术分析”“商业影响”这类空泛分类
- 优先把数字、判断、转折写进小标题，例如“推理成本降 60%，价格战正式打响”

### 写作风格
- 目标风格：36 氪的信息密度 + 极客公园的深度叙事，专业但不学术，快但不浅
- 每个段落至少提供一个具体事实、数据或引述，不要写删掉后不影响理解的空段落
- 段落长度必须有变化，可以有 1 句短段，也可以有 4-5 句分析段，不要连续多段结构完全一致
- 多用阿拉伯数字和对比参照，例如“比去年降了 60%”，少用“显著提升”“大幅增长”这类空泛表述
- 技术术语首次出现时用括号做简短效果解释，不超过 15 字
- 加粗只用于关键数据或核心判断，全文加粗不超过 8 处

### 引文与事实底线（最高优先级）
- 所有数字、金额、百分比、日期、人名、公司名、产品名，必须来自素材或可核实公开来源
- 如果具体数字不确定，不要猜，改成定性描述或明确写“未披露”
- 所有引号中的内容必须来自原文摘录，不允许改写后再加引号
- 日期和事件顺序必须与素材一致，不要为了叙事调整时间线
- 区分事实与分析：事实直接陈述，分析用“这意味着”“这表明”等引入

### 格式要求
- Markdown 格式输出
- # 一级标题只用一次
- ## 二级标题用于小节分隔，且标题本身要有信息量
- > 仅用于引用原文，引文后必须紧跟 1-2 句解读
- - 仅用于来源链接列表
- 段落之间保留一个空行

### 禁止事项
- 不要写 bullet-point 简报，这是一篇完整文章
- 不要用“1. 2. 3.”编号列表替代段落论述
- 不要在正文堆砌来源链接
- 不要以“总结：”“总之：”“综上所述”开头写结尾
- 不要用“本文将从以下几个方面展开”之类的元描述
- 不要使用宏大背景开头，不要用空洞评价、路标句、假对比句式
- 禁止出现这些高频 AI 味词或近义表达：{banned_phrases}

### 自检清单
- 删掉第一段后，文章是否仍然成立？如果是，重写导语
- 是否有连续 3 段以上结构和长度几乎一致？如果有，打散节奏
- 每个小标题是否传达了具体信息，而不是空泛分类？
- 每个数字和引号内容是否都能在素材或公开来源中找到依据？
- 是否至少有一个足够具体、值得读者截图分享的句子或数据？"""
