from __future__ import annotations

import json
import re
from typing import Any

from ..llm import LLMService
from ..store.base import _extract_json_payload


class LLMEnhanceMixin:
    """LLM-powered brief enhancement and Douyin article rewriting."""

    def _extract_enhanced_brief_payload(self, content: str) -> dict[str, Any]:
        payload = _extract_json_payload(content)
        if isinstance(payload, dict):
            return payload
        fenced = str(content or "").strip()
        fenced = re.sub(r"^```json\s*", "", fenced, flags=re.IGNORECASE)
        fenced = re.sub(r"^```\s*", "", fenced)
        fenced = re.sub(r"\s*```$", "", fenced)

        extracted: dict[str, Any] = {}
        one_line_match = re.search(r'"one_line"\s*:\s*"(.*?)",\s*"why_it_matters"', fenced, re.S)
        if one_line_match:
            extracted["one_line"] = one_line_match.group(1).replace('\\"', '"').strip()
        why_match = re.search(r'"why_it_matters"\s*:\s*"(.*?)",\s*"risk_notes"', fenced, re.S)
        if why_match:
            extracted["why_it_matters"] = why_match.group(1).replace('\\"', '"').strip()
        risk_match = re.search(r'"risk_notes"\s*:\s*(\[[\s\S]*?\])\s*\}?', fenced, re.S)
        if risk_match:
            try:
                parsed_risks = json.loads(risk_match.group(1))
                if isinstance(parsed_risks, list):
                    extracted["risk_notes"] = [str(item).strip() for item in parsed_risks if str(item).strip()]
            except Exception:
                pass
        return extracted

    def _build_enhancement_messages(
        self,
        event: dict[str, Any],
        brief_payload: dict[str, Any],
        full_text_sources: list[dict[str, Any]],
        *,
        retry: bool = False,
    ) -> list[dict[str, str]]:
        system_text = (
            "你是新闻编辑助手。你会收到事件元数据、已核验事实，以及系统抓取并清洗后的完整正文。"
            "请只根据这些内容输出简洁 JSON，不要补充未给出的事实，不要输出 Markdown。"
            "所有字符串值中不要使用半角双引号，如需强调请改用中文引号或直接省略引号。"
        )
        task = (
            "请阅读完整正文与已核验事实，补充一句话结论、为什么值得关注、风险说明。"
            "必须严格返回 JSON，且 JSON 字符串值中不要出现未转义的半角双引号。"
        )
        if retry:
            task = (
                "上一次输出不合格。现在只返回一个 JSON 对象，不要代码块，不要解释，不要 Markdown。"
                "字段只能是 one_line、why_it_matters、risk_notes。"
                "one_line 和 why_it_matters 必须为非空字符串，risk_notes 必须为字符串数组。"
            )
        return [
            {"role": "system", "content": system_text},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "event_title": str(event.get("title") or ""),
                        "event_summary": str(event.get("summary") or ""),
                        "event_state": str(event.get("alert_state") or ""),
                        "facts": list(brief_payload.get("facts", []))[:5],
                        "quotes": list(brief_payload.get("quotes", []))[:3],
                        "timeline": list(brief_payload.get("timeline", []))[:5],
                        "risk_notes": list(brief_payload.get("risk_notes", []))[:4],
                        "full_text_sources": full_text_sources,
                        "schema": {
                            "one_line": "string",
                            "why_it_matters": "string",
                            "risk_notes": ["string"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def _validate_enhanced_brief_payload(
        self,
        payload: dict[str, Any],
    ) -> tuple[str, str, list[str]] | None:
        one_line = str(payload.get("one_line") or "").strip()
        why_it_matters = str(payload.get("why_it_matters") or "").strip()
        raw_risk_notes = payload.get("risk_notes", [])
        risk_notes = [str(item).strip() for item in raw_risk_notes if str(item).strip()] if isinstance(raw_risk_notes, list) else []
        if not one_line or not why_it_matters:
            return None
        return one_line, why_it_matters, risk_notes[:5]

    def _extract_douyin_rewrite_payload(self, content: str) -> dict[str, Any]:
        payload = _extract_json_payload(content)
        if isinstance(payload, dict):
            return payload
        fenced = str(content or "").strip()
        fenced = re.sub(r"^```json\s*", "", fenced, flags=re.IGNORECASE)
        fenced = re.sub(r"^```\s*", "", fenced)
        fenced = re.sub(r"\s*```$", "", fenced)

        extracted: dict[str, Any] = {}
        title_match = re.search(r'"title"\s*:\s*"(.*?)",\s*"summary"', fenced, re.S)
        if title_match:
            extracted["title"] = title_match.group(1).replace('\\"', '"').strip()
        summary_match = re.search(r'"summary"\s*:\s*"(.*?)",\s*"markdown"', fenced, re.S)
        if summary_match:
            extracted["summary"] = summary_match.group(1).replace('\\"', '"').strip()
        markdown_match = re.search(r'"markdown"\s*:\s*"(.*)"\s*\}?$', fenced, re.S)
        if markdown_match:
            extracted["markdown"] = markdown_match.group(1).replace('\\"', '"').replace("\\n", "\n").strip()
        return extracted

    def _build_douyin_rewrite_messages(
        self,
        *,
        event: dict[str, Any],
        brief_payload: dict[str, Any],
        full_text_sources: list[dict[str, Any]],
        article_markdown: str,
        retry: bool = False,
    ) -> list[dict[str, str]]:
        system_text = (
            "你是抖音图文编辑。你会收到已核验事实、完整正文和一版现有成稿。"
            "请把成稿改写成适合抖音创作者中心文章页的版本。"
            "必须严格返回 JSON，不要解释，不要代码块，不要补充素材里没有的新事实。"
            "所有字符串值中不要使用未转义的半角双引号。"
        )
        task = (
            "输出字段只能是 title、summary、markdown。"
            "title 控制在 30 字内，summary 控制在 30 字内，markdown 必须是 600-1200 字的移动端短段落正文。"
            "正文必须保留事实密度，但段落更短、更直接，去掉来源链接、参考资料、公众号结尾腔。"
        )
        if retry:
            task = (
                "上一次输出不合格。现在只返回一个 JSON 对象，不要代码块，不要解释。"
                "title、summary、markdown 都必须是非空字符串。"
                "title 不超过 30 字，summary 不超过 30 字，markdown 必须以一级标题开头。"
            )
        return [
            {"role": "system", "content": system_text},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "event_title": str(event.get("title") or ""),
                        "event_summary": str(event.get("summary") or ""),
                        "event_state": str(event.get("alert_state") or ""),
                        "one_line": str(brief_payload.get("one_line") or ""),
                        "why_it_matters": str(brief_payload.get("why_it_matters") or ""),
                        "facts": list(brief_payload.get("facts", []))[:6],
                        "quotes": list(brief_payload.get("quotes", []))[:4],
                        "timeline": list(brief_payload.get("timeline", []))[:6],
                        "risk_notes": list(brief_payload.get("risk_notes", []))[:5],
                        "full_text_sources": full_text_sources,
                        "article_markdown": article_markdown,
                        "schema": {
                            "title": "string <= 30 chars",
                            "summary": "string <= 30 chars",
                            "markdown": "markdown article for douyin",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def _validate_douyin_rewrite_payload(self, payload: dict[str, Any]) -> tuple[str, str, str] | None:
        from ..content.briefing import build_douyin_summary, build_douyin_title, ensure_markdown_title

        title = build_douyin_title(str(payload.get("title") or "").strip())
        summary = build_douyin_summary(str(payload.get("summary") or "").strip(), title)
        markdown = str(payload.get("markdown") or "").strip()
        if not title or not summary or not markdown:
            return None
        markdown = ensure_markdown_title(markdown, title)
        if not markdown.startswith("# "):
            return None
        if len(summary) > 30 or len(title) > 30:
            return None
        body = markdown.split("\n", 1)[1].strip() if "\n" in markdown else ""
        compact_body = body.replace("\n", "")
        if len(compact_body) > 1000:
            return None
        return title, summary, markdown

    def _rewrite_article_for_douyin(
        self,
        llm_service: LLMService | None,
        *,
        event: dict[str, Any],
        deep_dive: dict[str, Any],
        brief_payload: dict[str, Any],
        article_markdown: str,
        fallback_title: str,
        fallback_summary: str,
        fallback_markdown: str,
    ) -> tuple[str, str, str]:
        if not llm_service:
            return fallback_title, fallback_summary, fallback_markdown
        full_text_sources = self._build_full_text_sources_for_ai(deep_dive, limit=4)
        if not full_text_sources:
            return fallback_title, fallback_summary, fallback_markdown
        for retry in (False, True):
            try:
                messages = self._build_douyin_rewrite_messages(
                    event=event,
                    brief_payload=brief_payload,
                    full_text_sources=full_text_sources,
                    article_markdown=article_markdown,
                    retry=retry,
                )
                result = llm_service.generate("article", messages, temperature=0.3, max_tokens=1800, timeout=90.0)
                payload = self._extract_douyin_rewrite_payload(str(result.get("content") or ""))
                validated = self._validate_douyin_rewrite_payload(payload)
                if validated:
                    return validated
            except Exception:
                continue
        return fallback_title, fallback_summary, fallback_markdown

    def _maybe_enhance_brief(
        self,
        llm_service: LLMService | None,
        event: dict[str, Any],
        deep_dive: dict[str, Any],
        brief_payload: dict[str, Any],
    ) -> tuple[str, str, list[str], str]:
        if not llm_service:
            return (
                str(brief_payload.get("one_line") or ""),
                str(brief_payload.get("why_it_matters") or ""),
                list(brief_payload.get("risk_notes", [])),
                "rule",
            )
        full_text_sources = self._build_full_text_sources_for_ai(deep_dive)
        if not full_text_sources:
            return (
                str(brief_payload.get("one_line") or ""),
                str(brief_payload.get("why_it_matters") or ""),
                list(brief_payload.get("risk_notes", [])),
                "rule",
            )
        for retry in (False, True):
            try:
                messages = self._build_enhancement_messages(
                    event,
                    brief_payload,
                    full_text_sources,
                    retry=retry,
                )
                result = llm_service.generate("article", messages, temperature=0.2, max_tokens=700, timeout=90.0)
                payload = self._extract_enhanced_brief_payload(str(result.get("content") or ""))
                validated = self._validate_enhanced_brief_payload(payload)
                if not validated:
                    continue
                one_line, why_it_matters, risk_notes = validated
                if not risk_notes:
                    risk_notes = list(brief_payload.get("risk_notes", []))
                return one_line, why_it_matters, risk_notes[:5], "enhanced"
            except Exception:
                continue
        return (
            str(brief_payload.get("one_line") or ""),
            str(brief_payload.get("why_it_matters") or ""),
            list(brief_payload.get("risk_notes", [])),
            "rule",
        )
