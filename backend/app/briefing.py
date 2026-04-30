from __future__ import annotations

from typing import Any


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
