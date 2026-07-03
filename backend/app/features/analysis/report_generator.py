from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from ...models import AnalysisReportItem, AnalysisReportRequest, AnalysisReportSections


def _clean_text(value: Any, max_chars: int = 6000) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _compact_items(items: list[dict[str, Any]], limit: int, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in items[:limit]:
        compacted.append({field: item.get(field) for field in fields if item.get(field) not in (None, "", [])})
    return compacted


def _extract_json_object(text: str) -> dict[str, Any] | None:
    content = _clean_text(text, 20000)
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
    if fence:
        content = fence.group(1)
    else:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            content = content[start : end + 1]
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _sections_from_any(value: Any) -> AnalysisReportSections:
    payload = value if isinstance(value, dict) else {}
    return AnalysisReportSections(
        executive_summary=_clean_text(payload.get("executive_summary"), 2000),
        key_findings=_clean_text(payload.get("key_findings"), 3000),
        risk_assessment=_clean_text(payload.get("risk_assessment"), 3000),
        recommendation=_clean_text(payload.get("recommendation"), 3000),
    )


def _markdown_from_sections(sections: AnalysisReportSections) -> str:
    return "\n\n".join(
        [
            "# 研判报告",
            f"## 主结论\n{sections.executive_summary or '暂无足够信号形成明确结论。'}",
            f"## 关键发现\n{sections.key_findings or '暂无显著集中发现。'}",
            f"## 风险评估\n{sections.risk_assessment or '样本量和时效性仍需继续观察。'}",
            f"## 建议动作\n{sections.recommendation or '继续跟踪高热实体与新增主题。'}",
        ]
    )


def _build_weekly_digest_messages(
    request: AnalysisReportRequest,
    *,
    events: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    temporal_rules: list[dict[str, Any]],
) -> list[dict[str, str]]:
    payload = {
        "scope": request.scope,
        "period": {"date_from": request.date_from, "date_to": request.date_to},
        "topics": _compact_items(topics, 12, ("topic_id", "label", "event_count", "keywords")),
        "new_entities": _compact_items(
            [item for item in signals if item.get("trend") == "emerging"],
            12,
            ("entity_id", "entity_name", "trend", "trend_label", "recent_event_count", "latest_event_title"),
        ),
        "signals": _compact_items(
            signals,
            12,
            ("entity_id", "entity_name", "trend", "trend_label", "sma_7d", "sma_14d", "recent_event_count", "latest_event_title"),
        ),
        "temporal_rules": _compact_items(
            temporal_rules,
            8,
            ("antecedent_title", "consequent_title", "lag_days", "support", "confidence", "lift"),
        ),
        "events": _compact_items(
            events,
            20,
            ("id", "title", "summary", "entity_names", "source_names", "composite_score", "first_seen_at", "last_seen_at"),
        ),
    }
    return [
        {
            "role": "system",
            "content": (
                "你是科技情报研判分析师。请生成周度情报摘要。"
                "覆盖 Top 主题变化、新实体出现、趋势信号汇总和时序关联规则触发。"
                "只输出 JSON，不要输出 Markdown 代码围栏。JSON 格式："
                '{"sections":{"executive_summary":"","key_findings":"","risk_assessment":"","recommendation":""},"markdown":"# 周度情报摘要\\n..."}。'
                "不要编造数据里没有的事实、日期、公司动作或结论。"
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]


def _rule_based_report(
    request: AnalysisReportRequest,
    *,
    events: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    report_id: str,
    status: str = "no_llm",
) -> AnalysisReportItem:
    top_signal = signals[0] if signals else {}
    top_topic = topics[0] if topics else {}
    scope_label = {"daily": "日报", "weekly": "周报", "monthly": "月报"}.get(request.scope, request.scope)
    executive = (
        f"{scope_label}覆盖 {len(topics)} 个主题、{len(signals)} 个实体信号和 {len(events)} 条可见事件。"
        f" 当前最活跃实体为 {top_signal.get('entity_name') or '暂无'}。"
    )
    findings = (
        f"最高频主题为 {top_topic.get('label') or '暂无主题'}，事件数 {top_topic.get('event_count') or 0}。"
        f" 最新事件为 {top_signal.get('latest_event_title') or '暂无最新事件'}。"
    )
    risk = "当前报告由规则模板生成，适合作为运营线索，不应替代人工事实核验。"
    recommendation = "优先复核高热实体的最新事件，并关注主题是否继续扩散。"
    sections = AnalysisReportSections(
        executive_summary=executive,
        key_findings=findings,
        risk_assessment=risk,
        recommendation=recommendation,
    )
    return AnalysisReportItem(
        report_id=report_id,
        scope=request.scope,
        period_start=request.date_from,
        period_end=request.date_to,
        status=status,
        markdown=_markdown_from_sections(sections),
        sections=sections,
        created_at=datetime.now(UTC).isoformat(),
    )


def generate_weekly_digest(
    request: AnalysisReportRequest,
    *,
    events: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    temporal_rules: list[dict[str, Any]] | None = None,
    llm_service: Any | None = None,
    report_id: str,
) -> AnalysisReportItem:
    """Generate the weekly digest MVP using the same LLM contract with a deterministic fallback."""
    temporal_rules = temporal_rules or []
    if llm_service is None:
        top_topic = topics[0] if topics else {}
        emerging_signals = [item for item in signals if item.get("trend") == "emerging"]
        executive = (
            f"周度情报摘要覆盖 {len(events)} 条可见事件、{len(topics)} 个主题和 {len(signals)} 个实体信号。"
            f" 本周最高频主题为 {top_topic.get('label') or '暂无主题'}。"
        )
        findings = (
            f"新增或升温实体 {len(emerging_signals)} 个；"
            f"已识别可复核的时序关联规则 {len(temporal_rules)} 条。"
        )
        risk = "周度摘要由规则模板生成，适合做运营线索汇总，关键事实仍需人工复核。"
        recommendation = "优先跟进高频主题、升温实体与高置信时序规则触发的后续事件。"
        sections = AnalysisReportSections(
            executive_summary=executive,
            key_findings=findings,
            risk_assessment=risk,
            recommendation=recommendation,
        )
        return AnalysisReportItem(
            report_id=report_id,
            scope=request.scope,
            period_start=request.date_from,
            period_end=request.date_to,
            status="no_llm",
            markdown="\n\n".join(
                [
                    "# 周度情报摘要（研判报告）",
                    f"## 主结论\n{sections.executive_summary}",
                    f"## 关键发现\n{sections.key_findings}",
                    f"## 风险评估\n{sections.risk_assessment}",
                    f"## 建议动作\n{sections.recommendation}",
                ]
            ),
            sections=sections,
            created_at=datetime.now(UTC).isoformat(),
        )
    try:
        result = llm_service.generate(
            "article",
            _build_weekly_digest_messages(request, events=events, topics=topics, signals=signals, temporal_rules=temporal_rules),
            temperature=0.2,
            max_tokens=2200,
            timeout=90.0,
        )
        parsed = _extract_json_object(str(result.get("content") or ""))
        if not parsed:
            raise ValueError("LLM weekly digest response is not valid JSON")
        sections = _sections_from_any(parsed.get("sections"))
        markdown = _clean_text(parsed.get("markdown"), 12000) or _markdown_from_sections(sections)
        return AnalysisReportItem(
            report_id=report_id,
            scope=request.scope,
            period_start=request.date_from,
            period_end=request.date_to,
            status="ready",
            markdown=markdown,
            sections=sections,
            created_at=datetime.now(UTC).isoformat(),
        )
    except Exception:
        return generate_weekly_digest(
            request,
            events=events,
            topics=topics,
            signals=signals,
            temporal_rules=temporal_rules,
            llm_service=None,
            report_id=report_id,
        )


def _build_messages(
    request: AnalysisReportRequest,
    *,
    events: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> list[dict[str, str]]:
    payload = {
        "scope": request.scope,
        "period": {"date_from": request.date_from, "date_to": request.date_to},
        "focus_entities": request.focus_entities[:30],
        "focus_topics": request.focus_topics[:30],
        "topics": _compact_items(topics, 12, ("topic_id", "label", "event_count", "keywords")),
        "signals": _compact_items(
            signals,
            12,
            ("entity_id", "entity_name", "trend", "trend_label", "sma_7d", "sma_14d", "recent_event_count", "latest_event_title"),
        ),
        "events": _compact_items(
            events,
            20,
            ("id", "title", "summary", "entity_names", "source_names", "composite_score", "first_seen_at", "last_seen_at"),
        ),
    }
    return [
        {
            "role": "system",
            "content": (
                "你是科技情报研判分析师。请基于给定结构化数据输出运营可读的研判报告。"
                "只输出 JSON，不要输出 Markdown 代码围栏。JSON 格式："
                '{"sections":{"executive_summary":"","key_findings":"","risk_assessment":"","recommendation":""},"markdown":"# 研判报告\\n..."}。'
                "不要编造数据里没有的事实、日期、公司动作或结论。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
        },
    ]


def generate_analysis_report(
    request: AnalysisReportRequest,
    *,
    events: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    llm_service: Any | None = None,
    report_id: str,
) -> AnalysisReportItem:
    """Generate an analysis report, falling back to deterministic rules when LLM is unavailable."""
    if llm_service is None:
        return _rule_based_report(request, events=events, topics=topics, signals=signals, report_id=report_id, status="no_llm")

    try:
        result = llm_service.generate(
            "article",
            _build_messages(request, events=events, topics=topics, signals=signals),
            temperature=0.2,
            max_tokens=2200,
            timeout=90.0,
        )
        parsed = _extract_json_object(str(result.get("content") or ""))
        if not parsed:
            raise ValueError("LLM report response is not valid JSON")
        sections = _sections_from_any(parsed.get("sections"))
        markdown = _clean_text(parsed.get("markdown"), 12000) or _markdown_from_sections(sections)
        return AnalysisReportItem(
            report_id=report_id,
            scope=request.scope,
            period_start=request.date_from,
            period_end=request.date_to,
            status="ready",
            markdown=markdown,
            sections=sections,
            created_at=datetime.now(UTC).isoformat(),
        )
    except Exception:
        return _rule_based_report(request, events=events, topics=topics, signals=signals, report_id=report_id, status="no_llm")
