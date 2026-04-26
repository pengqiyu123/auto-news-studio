from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import logging
import re
from typing import Any, TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from .llm import LLMService

UTC = timezone.utc
ARTICLE_VARIANT = "flash_explainer"
logger = logging.getLogger(__name__)

ARTICLE_SYSTEM_PROMPT = """你是一位资深的科技媒体编辑，正在为微信公众号撰写文章。

要求：
1. 使用中文撰写，风格专业但不晦涩
2. 使用 Markdown 格式（## 标题、- 列表、**加粗**）
3. 每篇文章 800-2000 字
4. 必须基于提供的事实和证据，不做无依据的推测
5. 避免投资建议和医疗建议
6. 包含具体的数字、时间、来源引用
7. 在适当位置标注信息来源"""

OUTLINE_SYSTEM_PROMPT = """你是一位资深的科技媒体编辑。根据提供的候选主题和事实信息，生成文章大纲。

输出 JSON 格式：
{
  "sections": [
    {"heading": "导语", "key_points": ["要点1", "要点2"]},
    {"heading": "关键信息", "key_points": ["要点1", "要点2"]},
    {"heading": "事件解读", "key_points": ["要点1", "要点2"]},
    {"heading": "影响判断", "key_points": ["要点1", "要点2"]},
    {"heading": "结尾", "key_points": ["要点1", "要点2"]}
  ]
}
只输出 JSON，不要输出其他内容。"""

TITLE_SYSTEM_PROMPT = """你是一位微信公众号编辑。根据文章标题和内容，生成 3-5 个吸引人的标题变体。

输出 JSON 数组：
["标题1", "标题2", "标题3"]
只输出 JSON 数组，不要输出其他内容。"""

SUMMARY_SYSTEM_PROMPT = """你是一位科技媒体编辑。根据文章内容生成一段 2-3 句话的读者摘要。

要求：
- 用第三人称，适合放在公众号摘要位置
- 突出核心事件和影响
- 100 字以内
只输出摘要文本，不要输出其他内容。"""


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _inline_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _markdown_to_html(markdown: str) -> str:
    html_parts: list[str] = []
    blocks = [block.strip() for block in markdown.split("\n\n") if block.strip()]
    in_code_fence = False
    code_lines: list[str] = []
    code_lang = ""

    for block in blocks:
        if block.startswith("```"):
            if in_code_fence:
                lang_attr = f' class="language-{escape(code_lang)}"' if code_lang else ""
                html_parts.append(f"<pre{lang_attr}><code>{escape(chr(10).join(code_lines))}</code></pre>")
                in_code_fence = False
                code_lines = []
                code_lang = ""
            else:
                in_code_fence = True
                first_line = block[3:].strip()
                code_lang = first_line
            continue

        if in_code_fence:
            code_lines.append(block)
            continue

        if block.startswith("### "):
            html_parts.append(f"<h3>{_inline_markdown(escape(block[4:]))}</h3>")
        elif block.startswith("## "):
            html_parts.append(f"<h2>{_inline_markdown(escape(block[3:]))}</h2>")
        elif block.startswith("# "):
            html_parts.append(f"<h1>{_inline_markdown(escape(block[2:]))}</h1>")
        elif block.startswith("> "):
            lines = [line[2:].strip() for line in block.splitlines() if line.startswith("> ")]
            content = "\n".join(_inline_markdown(escape(l)) for l in lines)
            html_parts.append(f"<blockquote>{content}</blockquote>")
        elif re.match(r"^\d+\. ", block):
            lines = [re.sub(r"^\d+\.\s*", "", line).strip() for line in block.splitlines() if re.match(r"^\d+\. ", line)]
            items = "".join(f"<li>{_inline_markdown(escape(line))}</li>" for line in lines)
            html_parts.append(f"<ol>{items}</ol>")
        elif block.startswith("- "):
            lines = [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]
            items = "".join(f"<li>{_inline_markdown(escape(line))}</li>" for line in lines)
            html_parts.append(f"<ul>{items}</ul>")
        elif block.strip() == "---":
            html_parts.append("<hr>")
        else:
            html_parts.append(f"<p>{_inline_markdown(escape(block))}</p>")

    if in_code_fence:
        lang_attr = f' class="language-{escape(code_lang)}"' if code_lang else ""
        html_parts.append(f"<pre{lang_attr}><code>{escape(chr(10).join(code_lines))}</code></pre>")

    return "\n".join(html_parts)


def _wechat_html(markdown: str) -> str:
    base = _markdown_to_html(markdown)
    return (
        "<section style='font-size:15px;line-height:1.8;color:#222;'>"
        f"{base}"
        "</section>"
    )


def _risk_flags(*segments: str, risk_keywords: list[str]) -> list[str]:
    text = "\n".join(segments).lower()
    flags = [keyword for keyword in risk_keywords if keyword.lower() in text]
    if "未经证实" in text or "爆料" in text:
        flags.append("存在未经证实表述")
    if "投资" in text:
        flags.append("涉及投资判断")
    return sorted(set(flags))


def _format_cn_time(value: str | None) -> str:
    if not value:
        return "发布时间未知"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return str(value)
    return f"{dt.year}年{dt.month}月{dt.day}日 {dt:%H:%M}"


def _source_phrase(source_names: list[str]) -> str:
    clean = [str(item).strip() for item in source_names if str(item).strip()]
    if not clean:
        return "多方信源"
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]}和{clean[1]}"
    return f"{clean[0]}等{len(clean)}个信源"


def _cover_suggestion(candidate: dict[str, Any]) -> str:
    return (
        "封面建议优先使用事件主体清晰的新闻图片，标题区只保留关键信息，"
        "不要把内部判断、评分或系统说明写到封面上。"
    )


def _pick_facts(candidate: dict[str, Any], normalized_item: dict[str, Any]) -> list[str]:
    facts = [str(item).strip(" \n-") for item in candidate.get("facts", []) if str(item).strip()]
    if facts:
        return facts[:5]
    published_at = _format_cn_time(candidate.get("published_at") or normalized_item.get("published_at"))
    return [
        f"核心事件：{candidate['title']}",
        f"当前摘要：{candidate['summary']}",
        f"主要信源：{_source_phrase(list(candidate.get('source_names', [])))}",
        f"源站时间：{published_at}",
    ]


def _build_title_options(candidate: dict[str, Any], normalized_item: dict[str, Any]) -> list[str]:
    title = str(candidate["title"]).strip()
    summary = str(candidate["summary"]).strip("。 ")
    published_at = _format_cn_time(candidate.get("published_at") or normalized_item.get("published_at"))
    options = [
        title,
        f"{title}，发生了什么",
        f"{title}：这件事对行业意味着什么",
        f"{published_at}，{summary[:24]}",
    ]
    unique: list[str] = []
    for item in options:
        if item not in unique:
            unique.append(item)
    return unique


def _build_image_slots(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    keywords = [str(candidate.get("title", "")).strip()]
    source_names = [str(item).strip() for item in candidate.get("source_names", []) if str(item).strip()]
    if source_names:
        keywords.append(source_names[0])
    return [
        {
            "slot_id": "hero",
            "label": "头图",
            "position": "lead",
            "suggestion": "优先选择事件主体官方图、发布会现场图或产品实拍图。",
            "required_image": True,
            "fulfilled": False,
            "keywords": keywords,
        },
        {
            "slot_id": "detail",
            "label": "正文配图",
            "position": "analysis",
            "suggestion": "可补一张参数表、关键界面或事件相关配图，增强正文可读性。",
            "required_image": False,
            "fulfilled": False,
            "keywords": keywords,
        },
    ]


def _build_intel_brief(candidate: dict[str, Any], normalized_item: dict[str, Any]) -> dict[str, Any]:
    published_at = candidate.get("published_at") or normalized_item.get("published_at")
    collected_at = candidate.get("collected_at")
    facts = _pick_facts(candidate, normalized_item)
    evidence_links = list(candidate.get("evidence_links", []))
    risk_notes: list[str] = []
    if not evidence_links:
        risk_notes.append("缺少证据链接，建议补充后再推进。")
    if not published_at:
        risk_notes.append("源站发布时间不完整，正文中应避免过度强调时点。")
    if int(candidate.get("source_count", 0) or 0) <= 1:
        risk_notes.append("当前事件仍以单一来源为主，建议继续等待更多跟进。")
    return {
        "headline": candidate["title"],
        "one_line": candidate["summary"],
        "facts": facts,
        "evidence_links": evidence_links,
        "source_names": list(candidate.get("source_names", [])),
        "source_count": int(candidate.get("source_count", 0) or 0),
        "published_at": published_at,
        "collected_at": collected_at,
        "event_judgement": "可按快讯解读处理，先交代事实，再给读者一个稳妥判断。",
        "risk_notes": risk_notes,
        "time_context": {
            "published_at_label": _format_cn_time(published_at),
            "collected_at_label": _format_cn_time(collected_at) if collected_at else "采集时间未知",
        },
    }


def _build_outline(
    candidate: dict[str, Any],
    normalized_item: dict[str, Any],
    brief: dict[str, Any],
    title_options: list[str],
    image_slots: list[dict[str, Any]],
) -> dict[str, Any]:
    published_at_label = brief["time_context"]["published_at_label"]
    lead = (
        f"{published_at_label}前后，{candidate['title']}进入市场与媒体视野。"
        f" 现阶段最重要的是先把已确认的信息说清楚，再判断它对行业和读者的实际影响。"
    )
    key_points = [
        fact for fact in brief["facts"][:4]
    ]
    section_order = ["导语", "关键信息", "事件解读", "影响判断", "结尾"]
    return {
        "title_options": title_options,
        "lead_direction": lead,
        "key_points": key_points,
        "section_order": section_order,
        "closing_line": "对公众号内容来说，这类新闻的价值不只在于快，更在于把重要变化讲明白。",
        "image_plan": image_slots,
    }


def _build_reader_summary(candidate: dict[str, Any], brief: dict[str, Any]) -> str:
    published_at = brief["time_context"]["published_at_label"]
    return (
        f"{published_at}，{candidate['title']}这条消息被{brief['source_count']}个信源纳入系统跟踪。"
        f" 对读者来说，重点不只是价格、发布或表态本身，更是它会不会带来接下来的市场动作。"
    )


def _build_body_blocks(
    candidate: dict[str, Any],
    normalized_item: dict[str, Any],
    brief: dict[str, Any],
    reader_summary: str,
) -> list[dict[str, Any]]:
    published_at = brief["time_context"]["published_at_label"]
    source_phrase = _source_phrase(list(candidate.get("source_names", [])))
    facts = brief["facts"][:4]
    evidence_links = list(candidate.get("evidence_links", []))
    core_signal = normalized_item.get("summary") or candidate.get("summary") or candidate.get("title")

    intro = (
        f"{published_at}，{candidate['title']}这条消息开始被广泛讨论。"
        f" 目前已经进入我们系统的可写主题池，原因并不复杂：它既有明确的事实锚点，也有足够清晰的后续观察空间。"
        f" 对公众号读者来说，先看懂这件事本身，再看它会不会改变行业节奏，比单纯转述一句消息更重要。"
    )
    key_info = "\n".join(f"- {fact}" for fact in facts)
    analysis_one = (
        f"先看事实层面，{source_phrase}已经给出了可以落笔的基础信息，"
        f"目前最稳妥的写法，是把已经确认的发布内容、时间节点和关键信号交代完整。"
        f" 这也是快讯解读最重要的一步：让读者先知道发生了什么，而不是一上来就灌输结论。"
    )
    analysis_two = (
        f"再看解读层面，{core_signal}之所以值得继续跟，不一定因为它已经定性了行业结果，"
        "而是因为它提供了一个明确的新观察点。无论是价格、产品、政策还是平台动作，"
        "只要后续还有更多信源补充，它就有机会从单条新闻扩展成更完整的连续报道。"
    )
    impact = (
        "对读者而言，这类消息的实际意义通常体现在两个维度："
        "第一，它会不会改变相关产品、公司或行业的短期关注度；第二，它有没有可能带出新的竞争动作、用户选择或者市场情绪。"
        " 所以现阶段最合适的判断不是夸大影响，而是把变化点和后续看点清楚交代出来。"
    )
    closing = (
        "如果后续出现更多官方细节、二次报道或用户反馈，这篇稿件还可以继续补充。"
        " 在正式发布之前，建议再核对一次时间、数字、主体名称，并补上一张能够支撑主题的配图，"
        "这样它会更像一篇稳定可发的公众号快讯，而不是内部测试稿。"
    )

    return [
        {
            "kind": "intro",
            "content": intro,
            "evidence_links": evidence_links[:1],
            "required_image": True,
        },
        {
            "kind": "bullet_list",
            "heading": "关键信息",
            "content": key_info,
            "evidence_links": evidence_links[:2],
            "required_image": False,
        },
        {
            "kind": "analysis",
            "heading": "事件解读",
            "content": analysis_one,
            "evidence_links": evidence_links[:2],
            "required_image": False,
        },
        {
            "kind": "analysis",
            "content": analysis_two,
            "evidence_links": evidence_links[:2],
            "required_image": False,
        },
        {
            "kind": "impact",
            "heading": "影响判断",
            "content": impact,
            "evidence_links": evidence_links[:1],
            "required_image": False,
        },
        {
            "kind": "closing",
            "heading": "结尾",
            "content": closing,
            "evidence_links": evidence_links[:1],
            "required_image": False,
        },
    ]


def _render_markdown(title: str, body_blocks: list[dict[str, Any]]) -> str:
    parts = [f"# {title}"]
    for block in body_blocks:
        heading = str(block.get("heading") or "").strip()
        content = str(block.get("content") or "").strip()
        if not content:
            continue
        if heading:
            parts.append(f"## {heading}\n{content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


def _build_editor_draft(
    candidate: dict[str, Any],
    brief: dict[str, Any],
    outline: dict[str, Any],
    reader_summary: str,
    body_blocks: list[dict[str, Any]],
) -> str:
    facts = "\n".join(f"- {item}" for item in brief["facts"])
    key_points = "\n".join(f"- {item}" for item in outline["key_points"])
    article_body = "\n\n".join(
        f"## {block['heading']}\n{block['content']}" if block.get("heading") else str(block["content"])
        for block in body_blocks
    )
    return "\n\n".join(
        [
            f"# 编辑初稿｜{candidate['title']}",
            "## 一句话摘要\n" + reader_summary,
            "## 已确认事实\n" + facts,
            "## 建议结构\n" + key_points,
            article_body,
        ]
    )


def _build_editor_notes(
    candidate: dict[str, Any],
    brief: dict[str, Any],
    image_slots: list[dict[str, Any]],
) -> list[str]:
    notes = [
        "正式稿已经移除内部评分、模式和推荐角度等系统话术。",
        "发布前请至少补一张头图，否则微信预览和发表会被拦下。",
        "标题、数字、主体名称建议在发送前再复核一次。",
    ]
    if brief["risk_notes"]:
        notes.extend(brief["risk_notes"])
    if any(slot.get("required_image") and not slot.get("fulfilled") for slot in image_slots):
        notes.append("当前仍处于待补图状态。")
    if int(candidate.get("source_count", 0) or 0) <= 1:
        notes.append("当前主要依赖单一来源，适合快讯，不适合写成强结论稿。")
    return notes


def _llm_generate_outline(
    llm: LLMService,
    candidate: dict[str, Any],
    brief: dict[str, Any],
) -> list[dict[str, str]]:
    facts_text = "\n".join(f"- {f}" for f in brief.get("facts", []))
    source_text = ", ".join(brief.get("source_names", []))
    user_msg = (
        f"## 候选主题\n{candidate['title']}\n\n"
        f"## 摘要\n{candidate['summary']}\n\n"
        f"## 推荐角度\n{candidate.get('recommended_angle', '')}\n\n"
        f"## 已确认事实\n{facts_text}\n\n"
        f"## 信源\n{source_text}（共 {brief.get('source_count', 0)} 个）\n\n"
        f"## 发布时间\n{brief.get('time_context', {}).get('published_at_label', '未知')}"
    )
    result = llm.generate(
        "outline",
        [
            {"role": "system", "content": OUTLINE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    try:
        import json
        parsed = json.loads(result["content"])
        if isinstance(parsed, dict) and "sections" in parsed:
            return parsed["sections"]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    logger.warning("LLM outline parse failed, falling back to default structure")
    return [
        {"heading": "导语", "key_points": [candidate["title"]]},
        {"heading": "关键信息", "key_points": brief.get("facts", [])[:3]},
        {"heading": "事件解读", "key_points": []},
        {"heading": "影响判断", "key_points": []},
        {"heading": "结尾", "key_points": []},
    ]


def _llm_generate_article(
    llm: LLMService,
    candidate: dict[str, Any],
    brief: dict[str, Any],
    outline: list[dict[str, str]],
) -> str:
    sections_text = "\n".join(
        f"### {s['heading']}\n" + "\n".join(f"- {kp}" for kp in s.get("key_points", []))
        for s in outline
    )
    facts_text = "\n".join(f"- {f}" for f in brief.get("facts", []))
    evidence_links = brief.get("evidence_links", [])
    user_msg = (
        f"## 主题\n{candidate['title']}\n\n"
        f"## 摘要\n{candidate['summary']}\n\n"
        f"## 大纲\n{sections_text}\n\n"
        f"## 事实依据\n{facts_text}\n\n"
        f"## 证据链接\n" + "\n".join(f"- {link}" for link in evidence_links[:5])
    )
    result = llm.generate(
        "article",
        [
            {"role": "system", "content": ARTICLE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    return result["content"]


def _llm_generate_titles(
    llm: LLMService,
    title: str,
    markdown: str,
) -> list[str]:
    preview = markdown[:500]
    result = llm.generate(
        "title",
        [
            {"role": "system", "content": TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": f"## 当前标题\n{title}\n\n## 文章开头\n{preview}"},
        ],
    )
    try:
        import json
        parsed = json.loads(result["content"])
        if isinstance(parsed, list):
            valid = [t for t in parsed if isinstance(t, str) and 5 <= len(t) <= 64]
            if valid:
                return valid
    except (json.JSONDecodeError, TypeError):
        pass
    return [title]


def _llm_generate_summary(
    llm: LLMService,
    candidate: dict[str, Any],
    brief: dict[str, Any],
) -> str:
    result = llm.generate(
        "summary",
        [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"主题：{candidate['title']}\n摘要：{candidate['summary']}\n信源：{', '.join(brief.get('source_names', []))}"},
        ],
    )
    return result["content"].strip()


def _llm_body_blocks_from_markdown(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            if current_lines:
                blocks.append({"kind": "section", "heading": current_heading, "content": "\n".join(current_lines)})
                current_lines = []
            continue
        if stripped.startswith("### "):
            if current_lines:
                blocks.append({"kind": "section", "heading": current_heading, "content": "\n".join(current_lines)})
                current_lines = []
            current_heading = stripped[4:]
        elif stripped.startswith("## "):
            if current_lines:
                blocks.append({"kind": "section", "heading": current_heading, "content": "\n".join(current_lines)})
                current_lines = []
            current_heading = stripped[3:]
        elif stripped.startswith("# "):
            if current_lines:
                blocks.append({"kind": "section", "heading": current_heading, "content": "\n".join(current_lines)})
                current_lines = []
            current_heading = stripped[2:]
        else:
            current_lines.append(stripped)
    if current_lines:
        blocks.append({"kind": "section", "heading": current_heading, "content": "\n".join(current_lines)})
    return blocks


def compose_draft(
    candidate: dict[str, Any],
    normalized_item: dict[str, Any],
    publish_mode: str,
    risk_keywords: list[str],
    llm_service: LLMService | None = None,
) -> dict[str, Any]:
    use_llm = llm_service is not None and llm_service.is_available()

    title_options = _build_title_options(candidate, normalized_item)
    brief = _build_intel_brief(candidate, normalized_item)
    image_slots = _build_image_slots(candidate)

    if use_llm:
        try:
            outline_sections = _llm_generate_outline(llm_service, candidate, brief)
            reader_summary = _llm_generate_summary(llm_service, candidate, brief)
            article_markdown = _llm_generate_article(llm_service, candidate, brief, outline_sections)
            title_options = _llm_generate_titles(llm_service, title_options[0], article_markdown[:500])
            body_blocks = _llm_body_blocks_from_markdown(article_markdown)
            markdown = _render_markdown(title_options[0], body_blocks)
            render_backend = f"llm-{llm_service._tasks.get('article', {}).get('model_id', 'unknown')}"
            logger.info("LLM draft generation succeeded for candidate %s", candidate.get("id"))
        except Exception as exc:
            logger.warning("LLM generation failed for candidate %s, falling back to template: %s", candidate.get("id"), exc)
            use_llm = False

    if not use_llm:
        outline = _build_outline(candidate, normalized_item, brief, title_options, image_slots)
        reader_summary = _build_reader_summary(candidate, brief)
        body_blocks = _build_body_blocks(candidate, normalized_item, brief, reader_summary)
        markdown = _render_markdown(title_options[0], body_blocks)
        render_backend = "python-compose-v3-flash-explainer"

    editor_draft_markdown = _build_editor_draft(candidate, brief, outline if not use_llm else {"title_options": title_options, "key_points": [b.get("content", "") for b in body_blocks[:3]]}, reader_summary, body_blocks)
    editor_notes = _build_editor_notes(candidate, brief, image_slots)
    risk_flags = _risk_flags(
        title_options[0],
        reader_summary,
        markdown,
        risk_keywords=risk_keywords,
    )
    blocked_reasons = ["命中风险词，需要人工复核。"] if risk_flags else []
    composition_trace = {
        "facts": brief["facts"],
        "angles": candidate.get("angles", []),
        "selected_angle": candidate.get("selected_angle") or candidate.get("recommended_angle"),
        "titles": title_options,
        "evidence": brief["evidence_links"],
        "generated_at": now_iso(),
        "brief": brief,
        "outline": outline if not use_llm else {"title_options": title_options, "key_points": [b.get("content", "") for b in body_blocks[:3]]},
        "editor_draft_markdown": editor_draft_markdown,
        "publish_article_markdown": markdown,
        "llm_used": use_llm,
    }
    approval_required = publish_mode != "full_auto" or bool(risk_flags)
    return {
        "id": f"draft-{uuid4().hex[:8]}",
        "candidate_topic_id": candidate["id"],
        "title": title_options[0],
        "section": "快讯解读",
        "source_count": int(candidate["source_count"]),
        "word_count": len(re.sub(r"\s+", "", markdown)),
        "publish_mode": publish_mode,
        "pipeline_stage": "drafted",
        "audit_status": "pending" if approval_required else "not_required",
        "summary": reader_summary,
        "brief": brief,
        "outline": outline if not use_llm else {"title_options": title_options, "key_points": [b.get("content", "") for b in body_blocks[:3]]},
        "article_variant": ARTICLE_VARIANT,
        "reader_summary": reader_summary,
        "body_blocks": body_blocks,
        "image_slots": image_slots,
        "editor_notes": editor_notes,
        "markdown": markdown,
        "html": _markdown_to_html(markdown),
        "wechat_html": _wechat_html(markdown),
        "updated_at": now_iso(),
        "cover_strategy": "manual",
        "cover_suggestion": _cover_suggestion(candidate),
        "risk_flags": risk_flags,
        "blocked_reasons": blocked_reasons,
        "evidence_links": list(candidate.get("evidence_links", [])),
        "title_options": title_options,
        "composition_trace": composition_trace,
        "render_backend": render_backend,
        "approval_required": approval_required,
        "wechat_draft_id": None,
        "wechat_editor_url": None,
        "wechat_remote_appmsg_id": None,
        "preview_url": None,
        "last_error": None,
    }
