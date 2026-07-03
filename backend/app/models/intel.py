"""Intel/event/agent-html Pydantic models for Auto News Studio.

Extracted from models.py to reduce file size and improve domain grouping.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Literal types that are primarily used by intel/agent-html models.
# Duplicated here to avoid circular imports; models.py re-exports these.
IntelEventState = Literal["new", "watch", "rising", "breakout", "cooling"]
IntelAlertLevel = Literal["watch", "rising", "breakout", "cooling"]
IntelItemChangeState = Literal["new_item", "seen_item", "updated_item"]
IntelEventChangeState = Literal["new_event", "growing_event", "stable_event", "cooling_event"]
HistoryRecordStatus = Literal["active", "cooled", "source_uncertain"]
DeepDiveStatus = Literal["pending", "running", "partial", "ready", "failed"]
DeepDiveFetchStatus = Literal["pending", "fetched", "fetch_failed", "fetch_blocked", "non_html"]
DeepDiveExtractStatus = Literal["pending", "extracted", "extract_failed", "too_short"]
AgentHtmlTargetType = Literal["newsroom", "blog", "updates", "press", "custom"]
AgentHtmlRunStatus = Literal["pending", "running", "completed", "partial", "failed"]
AgentHtmlItemState = Literal["new_item", "seen_item", "updated_item"]
AgentHtmlDiscoverMode = Literal["rule_only", "rule_with_ai_fallback", "ai_only"]
AgentHtmlExtractMode = Literal["best_effort_html"]
AgentHtmlAlertState = Literal["watch", "rising", "breakout", "cooling"]
AgentHtmlEventChangeState = Literal["new_event", "growing_event", "stable_event", "cooling_event"]


class DashboardTopBar(BaseModel):
    current_mode_label: str
    healthy_sources: int
    total_sources: int
    latest_collected_at: str | None = None
    latest_published_at: str | None = None
    pending_briefs: int
    blocked_publish_count: int


class FreshnessSnapshot(BaseModel):
    latest_published_at: str | None = None
    latest_collected_at: str | None = None
    items_1h: int = 0
    items_6h: int = 0
    items_24h: int = 0
    avg_collection_lag_minutes: float | None = None
    stale_source_count: int = 0
    has_staleness_alert: bool = False
    last_successful_sync_at: str | None = None


class IntelStreamItem(BaseModel):
    id: str
    title: str
    summary: str
    link: str
    score: float
    source_names: list[str] = Field(default_factory=list)
    source_count: int = 0
    published_at: str | None = None
    collected_at: str | None = None
    time_lag_minutes: float | None = None


class DiscoveryItem(BaseModel):
    id: str
    raw_item_id: str
    source_key: str
    source_name: str
    source_kind: str
    platform: str
    title: str
    summary: str
    content: str
    link: str
    canonical_link: str
    dedupe_key: str
    source_native_id: str | None = None
    title_tokens: list[str] = Field(default_factory=list)
    anchor_tokens: list[str] = Field(default_factory=list)
    published_at: str | None = None
    collected_at: str
    tags: list[str] = Field(default_factory=list)
    engagement_score: float = 0.0
    item_state: IntelItemChangeState = "new_item"
    entity_ids: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntelEvent(BaseModel):
    id: str
    title: str
    summary: str
    representative_link: str
    representative_source_name: str
    representative_discovery_item_id: str
    discovery_item_ids: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    platform_count: int = 0
    source_count: int = 0
    member_count: int = 0
    story_count: int = 0
    member_delta: int = 0
    platform_delta: int = 0
    published_at: str | None = None
    latest_collected_at: str | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    anchor_tokens: list[str] = Field(default_factory=list)
    velocity_score: float = 0.0
    coverage_score: float = 0.0
    freshness_score: float = 0.0
    audience_fit_score: float = 0.0
    composite_score: float = 0.0
    velocity_details: dict[str, float] = Field(default_factory=dict)
    alert_state: IntelEventState = "new"
    change_state: IntelEventChangeState = "new_event"
    alert_reason: str = ""
    entity_ids: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    watchlisted: bool = False
    ignored: bool = False
    deep_dive_id: str | None = None
    brief_id: str | None = None
    deep_dive_status: DeepDiveStatus | None = None
    deep_dive_started_at: str | None = None
    deep_dive_finished_at: str | None = None
    deep_dive_updated_at: str | None = None
    brief_status: Literal["prepared", "synced", "failed"] | None = None
    deep_dive_summary: str = ""
    worth_to_brief: bool = False
    worth_reason: str = ""


class EventSnapshot(BaseModel):
    id: str
    event_id: str
    captured_at: str
    member_count: int = 0
    platform_count: int = 0
    source_count: int = 0
    velocity_score: float = 0.0
    coverage_score: float = 0.0
    freshness_score: float = 0.0
    audience_fit_score: float = 0.0
    composite_score: float = 0.0
    alert_state: IntelEventState = "new"


class IntelAlert(BaseModel):
    id: str
    event_id: str
    title: str
    summary: str = ""
    level: IntelAlertLevel
    reason: str
    velocity_score: float = 0.0
    coverage_score: float = 0.0
    freshness_score: float = 0.0
    audience_fit_score: float = 0.0
    composite_score: float = 0.0
    platform_count: int = 0
    source_count: int = 0
    representative_link: str
    triggered_at: str
    entity_ids: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    deep_dive_id: str | None = None
    brief_id: str | None = None
    deep_dive_status: DeepDiveStatus | None = None
    brief_status: Literal["prepared", "synced", "failed"] | None = None
    deep_dive_summary: str = ""
    worth_to_brief: bool = False
    worth_reason: str = ""


class DeepDiveSourceItem(BaseModel):
    source_key: str = ""
    source_name: str = ""
    original_link: str
    canonical_link: str
    title: str = ""
    published_at: str | None = None
    fetch_status: DeepDiveFetchStatus = "pending"
    extract_status: DeepDiveExtractStatus = "pending"
    word_count: int = 0
    cleaned_full_text: str = ""
    excerpt: str = ""
    quotes: list[str] = Field(default_factory=list)
    error: str | None = None


class EventDeepDive(BaseModel):
    id: str
    event_id: str
    status: DeepDiveStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str
    attempted_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    resolved_evidence_pack: list[dict[str, Any]] = Field(default_factory=list)
    full_text_sources: list[DeepDiveSourceItem] = Field(default_factory=list)
    sources: list[DeepDiveSourceItem] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    worthiness: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = None
    article_writing_guide: str = ""


class AgentHtmlDiscoveryRules(BaseModel):
    link_selector: str = ""
    title_selector: str = ""
    time_selector: str = ""
    summary_selector: str = ""
    link_allow_patterns: list[str] = Field(default_factory=list)
    link_deny_patterns: list[str] = Field(default_factory=list)


class AgentHtmlTarget(BaseModel):
    id: str
    brand: str
    name: str
    entry_url: str
    target_type: AgentHtmlTargetType = "newsroom"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    discover_mode: AgentHtmlDiscoverMode = "rule_with_ai_fallback"
    extract_mode: AgentHtmlExtractMode = "best_effort_html"
    discovery_rules: AgentHtmlDiscoveryRules = Field(default_factory=AgentHtmlDiscoveryRules)
    last_run_at: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    created_at: str
    updated_at: str


class AgentHtmlTargetCreatePayload(BaseModel):
    brand: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    entry_url: str = Field(min_length=1, max_length=1000)
    target_type: AgentHtmlTargetType = "newsroom"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    discover_mode: AgentHtmlDiscoverMode = "rule_with_ai_fallback"
    extract_mode: AgentHtmlExtractMode = "best_effort_html"
    discovery_rules: AgentHtmlDiscoveryRules = Field(default_factory=AgentHtmlDiscoveryRules)


class AgentHtmlTargetUpdatePayload(BaseModel):
    brand: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    entry_url: str | None = Field(default=None, min_length=1, max_length=1000)
    target_type: AgentHtmlTargetType | None = None
    enabled: bool | None = None
    tags: list[str] | None = None
    discover_mode: AgentHtmlDiscoverMode | None = None
    extract_mode: AgentHtmlExtractMode | None = None
    discovery_rules: AgentHtmlDiscoveryRules | None = None


class AgentHtmlRun(BaseModel):
    id: str
    target_id: str
    status: AgentHtmlRunStatus = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    discovered_count: int = 0
    new_discovery_count: int = 0
    updated_discovery_count: int = 0
    fetched_count: int = 0
    extracted_count: int = 0
    failed_count: int = 0
    list_fetch_status: str = "pending"
    ai_fallback_used: bool = False
    error_summary: str | None = None
    triggered_by: str = "dashboard"
    created_at: str
    updated_at: str


class AgentHtmlRunBatchPayload(BaseModel):
    target_ids: list[str] = Field(default_factory=list)
    triggered_by: str = "dashboard"


class AgentHtmlMainlineBatchPayload(BaseModel):
    target_ids: list[str] = Field(default_factory=list)
    triggered_by: str = "dashboard"


class AgentHtmlRunResponse(BaseModel):
    item: AgentHtmlRun


class AgentHtmlRunsResponse(BaseModel):
    items: list[AgentHtmlRun] = Field(default_factory=list)


class AgentHtmlDiscoveryItem(BaseModel):
    id: str
    target_id: str
    run_id: str
    source_name: str
    title: str
    summary: str
    link: str
    canonical_link: str
    published_at: str | None = None
    collected_at: str
    dedupe_key: str
    content_hash: str = ""
    item_state: AgentHtmlItemState = "new_item"
    document_id: str | None = None
    event_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentHtmlDocumentRevision(BaseModel):
    id: str
    document_id: str
    run_id: str
    source_url: str
    title: str = ""
    content_text: str = ""
    excerpt: str = ""
    content_hash: str = ""
    word_count: int = 0
    extractor: str = ""
    published_at: str | None = None
    fetched_at: str
    revision_index: int = 1
    change_summary: str = ""


class AgentHtmlDocument(BaseModel):
    id: str
    target_id: str
    canonical_url: str
    current_revision_id: str
    title: str = ""
    published_at: str | None = None
    latest_seen_at: str | None = None
    current_content_hash: str = ""
    word_count: int = 0
    extractor: str = ""
    first_seen_at: str
    updated_at: str
    revisions: list[AgentHtmlDocumentRevision] = Field(default_factory=list)


class AgentHtmlEvent(BaseModel):
    id: str
    title: str
    summary: str
    representative_document_id: str | None = None
    representative_link: str = ""
    discovery_item_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    member_count: int = 0
    source_count: int = 0
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    change_state: AgentHtmlEventChangeState = "new_event"
    alert_state: AgentHtmlAlertState = "watch"
    entity_names: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AgentHtmlEventSnapshot(BaseModel):
    id: str
    event_id: str
    captured_at: str
    member_count: int = 0
    document_count: int = 0
    source_count: int = 0
    freshness_score: float = 0.0
    coverage_score: float = 0.0
    composite_score: float = 0.0
    change_state: AgentHtmlEventChangeState = "new_event"


class AgentHtmlEventHistoryItem(BaseModel):
    history_id: str
    event_id: str
    title: str
    first_seen_at: str
    last_seen_at: str
    expires_at: str
    status: HistoryRecordStatus = "active"
    latest_alert_state: AgentHtmlAlertState = "watch"
    member_count: int = 0
    source_count: int = 0
    composite_score: float = 0.0


class AgentHtmlTargetResponse(BaseModel):
    item: AgentHtmlTarget


class AgentHtmlTargetsResponse(BaseModel):
    items: list[AgentHtmlTarget] = Field(default_factory=list)


class AgentHtmlDiscoveryResponse(BaseModel):
    items: list[AgentHtmlDiscoveryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class AgentHtmlEventResponse(BaseModel):
    item: AgentHtmlEvent


class AgentHtmlEventsResponse(BaseModel):
    items: list[AgentHtmlEvent] = Field(default_factory=list)
    history_items: list[AgentHtmlEventHistoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class AgentHtmlDocumentResponse(BaseModel):
    item: AgentHtmlDocument


class AgentHtmlDocumentsResponse(BaseModel):
    items: list[AgentHtmlDocument] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class IntelEventHistoryItem(BaseModel):
    history_id: str
    event_id: str
    title: str
    summary: str
    representative_link: str
    entity_ids: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    discovered_at: str
    last_seen_at: str
    expires_at: str
    status: HistoryRecordStatus = "active"
    latest_alert_state: IntelEventState = "new"
    platform_count: int = 0
    source_count: int = 0
    member_count: int = 0
    member_delta: int = 0
    platform_delta: int = 0
    composite_score: float = 0.0


class IntelAlertHistoryItem(BaseModel):
    history_id: str
    event_id: str
    title: str
    representative_link: str
    entity_ids: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    first_triggered_at: str
    last_triggered_at: str
    expires_at: str
    highest_level: IntelAlertLevel = "watch"
    latest_level: IntelAlertLevel = "watch"
    status: HistoryRecordStatus = "active"
    reason: str
    platform_count: int = 0
    source_count: int = 0
    velocity_score: float = 0.0
    coverage_score: float = 0.0
    freshness_score: float = 0.0
    composite_score: float = 0.0


class EntityWatchlistItem(BaseModel):
    entity_id: str
    entity_name: str
    entity_type: str
    watchlisted: bool = True
    added_at: str | None = None


class EntityWatchlistSummaryItem(EntityWatchlistItem):
    event_count: int = 0
    alert_count: int = 0
    rising_count: int = 0
    breakout_count: int = 0
    last_seen_at: str | None = None


class IntelOverviewSummary(BaseModel):
    alert_count: int = 0
    breakout_count: int = 0
    rising_count: int = 0
    watch_count: int = 0
    event_count: int = 0
    discovery_count: int = 0
    new_items_count: int = 0
    seen_items_count: int = 0
    updated_items_count: int = 0
    new_events_count: int = 0
    growing_events_count: int = 0
    stable_events_count: int = 0
    cooling_events_count: int = 0
    warning_sources: int = 0
    error_sources: int = 0
    healthy_sources: int = 0
    total_sources: int = 0
    recent_alert_count_24h: int = 0
    recent_event_count_24h: int = 0
    recent_breakout_count_24h: int = 0
    recent_rising_count_24h: int = 0
    last_sync_at: str | None = None
    next_run_at: str | None = None
    running: bool = False
    work_scope: Literal["collect_only", "collect_events", "collect_events_alerts"] = "collect_events_alerts"
    top_alerts: list[IntelAlert] = Field(default_factory=list)
    top_events: list[IntelEvent] = Field(default_factory=list)
    recent_alerts_24h: list[IntelAlertHistoryItem] = Field(default_factory=list)
    recent_events_24h: list[IntelEventHistoryItem] = Field(default_factory=list)
    source_alerts: list[str] = Field(default_factory=list)


class IntelSummaryResponse(BaseModel):
    item: IntelOverviewSummary


class DiscoveryItemsResponse(BaseModel):
    items: list[DiscoveryItem]
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False
    available_platforms: list[str] = Field(default_factory=list)
    available_sources: list[str] = Field(default_factory=list)


class IntelEventsResponse(BaseModel):
    items: list[IntelEvent]
    history_items: list[IntelEventHistoryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class IntelAlertsResponse(BaseModel):
    items: list[IntelAlert]
    history_items: list[IntelAlertHistoryItem] = Field(default_factory=list)


class IntelEventResponse(BaseModel):
    item: IntelEvent


class EventDeepDiveResponse(BaseModel):
    item: EventDeepDive


class EventDeepDivesResponse(BaseModel):
    items: list[EventDeepDive] = Field(default_factory=list)


class EntityWatchlistPayload(BaseModel):
    items: list[EntityWatchlistItem] = Field(default_factory=list)


class EntityWatchlistResponse(BaseModel):
    items: list[EntityWatchlistItem] = Field(default_factory=list)
