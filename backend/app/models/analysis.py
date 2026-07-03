from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TopicInfo(BaseModel):
    topic_id: str
    label: str = ""
    keywords: list[str] = Field(default_factory=list)
    event_count: int = 0


class TopicsResponse(BaseModel):
    items: list[TopicInfo] = Field(default_factory=list)


class EventRelationInfo(BaseModel):
    event_id: str
    title: str = ""
    relation_type: str = ""
    weight: float = 0.0
    evidence: dict[str, Any] = Field(default_factory=dict)


class EventRelationsResponse(BaseModel):
    items: list[EventRelationInfo] = Field(default_factory=list)


class TrendSignalInfo(BaseModel):
    entity_id: str
    entity_name: str = ""
    trend: str
    trend_label: str = ""
    sma_7d: float = 0.0
    sma_14d: float = 0.0
    signals: list[dict[str, Any]] = Field(default_factory=list)


class TrendSignalsResponse(BaseModel):
    items: list[TrendSignalInfo] = Field(default_factory=list)


class AnalysisSignalInfo(BaseModel):
    entity_id: str
    entity_name: str = ""
    trend: str
    trend_label: str = ""
    sma_7d: float = 0.0
    sma_14d: float = 0.0
    recent_event_count: int = 0
    latest_event_title: str = ""
    latest_event_id: str = ""


class AnalysisSignalsResponse(BaseModel):
    items: list[AnalysisSignalInfo] = Field(default_factory=list)


class AnalysisTopicEventInfo(BaseModel):
    event_id: str
    title: str = ""
    composite_score: float = 0.0
    first_seen_at: str | None = None


class AnalysisTopicEventsResponse(BaseModel):
    items: list[AnalysisTopicEventInfo] = Field(default_factory=list)


class TopicPeriodicityInfo(BaseModel):
    topic_id: str
    label: str = ""
    period_days: int = 0
    confidence: float = 0.0
    detected_at: str = ""


class TopicPeriodicityResponse(BaseModel):
    items: list[TopicPeriodicityInfo] = Field(default_factory=list)


class TemporalRuleInfo(BaseModel):
    id: str
    antecedent_event_id: str
    consequent_event_id: str
    antecedent_title: str = ""
    consequent_title: str = ""
    lag_days: int = 0
    support: float = 0.0
    confidence: float = 0.0
    lift: float = 0.0


class TemporalRulesResponse(BaseModel):
    items: list[TemporalRuleInfo] = Field(default_factory=list)


class AnalysisFeedbackPayload(BaseModel):
    target_type: str
    target_id: str
    feedback_type: Literal["confirm", "correct", "dismiss"]
    correction: dict[str, Any] = Field(default_factory=dict)


class AnalysisFeedbackResponse(BaseModel):
    ok: bool = True
    feedback_id: str


class AnalysisReportRequest(BaseModel):
    scope: Literal["daily", "weekly", "monthly"]
    date_from: str
    date_to: str
    focus_entities: list[str] = Field(default_factory=list, max_length=30)
    focus_topics: list[str] = Field(default_factory=list, max_length=30)


class AnalysisReportSections(BaseModel):
    executive_summary: str = ""
    key_findings: str = ""
    risk_assessment: str = ""
    recommendation: str = ""


class AnalysisReportItem(BaseModel):
    report_id: str
    scope: str = "daily"
    period_start: str = ""
    period_end: str = ""
    status: str = "ready"
    markdown: str = ""
    sections: AnalysisReportSections = Field(default_factory=AnalysisReportSections)
    created_at: str = ""


class AnalysisReportResponse(BaseModel):
    item: AnalysisReportItem


class AnalysisReportSummary(BaseModel):
    report_id: str
    scope: str = "daily"
    period_start: str = ""
    period_end: str = ""
    status: str = "ready"
    preview: str = ""
    created_at: str = ""


class AnalysisReportsResponse(BaseModel):
    items: list[AnalysisReportSummary] = Field(default_factory=list)


class AnalysisFeedbackStatsResponse(BaseModel):
    total: int = 0
    accurate_pct: float = 0.0
    by_type: dict[str, int] = Field(default_factory=dict)


class AnalysisBatchRunInfo(BaseModel):
    id: str
    task_name: str
    status: Literal["running", "success", "failed"]
    started_at: str = ""
    finished_at: str | None = None
    items_processed: int = 0
    error_message: str = ""


class AnalysisBatchStatusResponse(BaseModel):
    items: list[AnalysisBatchRunInfo] = Field(default_factory=list)
