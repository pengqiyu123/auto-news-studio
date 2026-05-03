from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .models_llm import (
    LLMConfig,
    LLMConfigResponse,
    LLMProfileConfig,
    LLMProviderConfig,
    LLMProviderPayload,
    LLMTaskConfig,
    LLMTaskPayload,
    LLMTestResult,
    LLMUsageResponse,
)


AutomationMode = Literal[
    "radar_only",
    "radar_and_draft",
    "full_pipeline",
]
AutomationBriefTrigger = Literal["manual", "after_sync", "scheduled"]
AutomationDeliveryTarget = Literal["local_only", "wechat_draft"]
AutomationSelectionMode = Literal["all_new", "top_scored"]
AutomationPublishStrategy = Literal["disabled", "wechat_draft_only", "guarded_send"]

AuditStatus = Literal["pending", "approved", "rejected", "not_required"]
JobStatus = Literal["queued", "running", "completed", "failed"]
LogLevel = Literal["info", "warning", "error", "success"]
SourceKind = Literal[
    "rss",
    "rsshub",
    "api",
    "newsnow",
    "bilibili",
    "toutiao",
    "reddit",
    "youtube",
    "github",
    "hackernews",
    "vvhan",
    "legacy",
    "page",
    "monitor",
    "wordpress",
]
SourceHealth = Literal["idle", "healthy", "warning", "error"]
AutomationRunStatus = Literal["idle", "running", "completed", "failed", "abandoned"]
PublishTaskStatus = Literal["pending", "running", "completed", "failed", "blocked"]
RefreshStatus = Literal["ready", "updated", "pending_retry", "missing"]
BorrowMode = Literal["direct_copy", "ported", "reference_only"]
BackendHealth = Literal["healthy", "warning", "offline"]
ChainStatus = Literal["idle", "running", "healthy", "warning", "blocked"]
LogStream = Literal["system_runtime", "business_event"]
RuntimeControlState = Literal["stopped", "armed", "running", "waiting"]
RuntimeLaunchMode = Literal["once_now", "once_at", "interval_now", "interval_at"]
IntelWorkScope = Literal["collect_only", "collect_events", "collect_events_alerts"]
RuntimeIntent = Literal["normal_monitoring", "collect_validation", "event_rebuild", "alert_rebuild"]
RuntimeRunOutcome = Literal["completed", "failed", "abandoned", "stopped"]
IntelEventState = Literal["new", "watch", "rising", "breakout", "cooling"]
IntelAlertLevel = Literal["watch", "rising", "breakout", "cooling"]
IntelItemChangeState = Literal["new_item", "seen_item", "updated_item"]
IntelEventChangeState = Literal["new_event", "growing_event", "stable_event", "cooling_event"]
HistoryRecordStatus = Literal["active", "cooled", "source_uncertain"]
DeepDiveStatus = Literal["pending", "running", "partial", "ready", "failed"]
DeepDiveFetchStatus = Literal["pending", "fetched", "fetch_failed", "fetch_blocked", "non_html"]
DeepDiveExtractStatus = Literal["pending", "extracted", "extract_failed", "too_short"]
BriefLevel = Literal["rule", "enhanced"]
BriefStage = Literal["prepared", "synced", "failed"]
DeliveryMode = Literal["immediate", "scheduled_batch"]
AdmissionStrategy = Literal["conservative", "balanced", "aggressive"]


class AutomationModeDefinition(BaseModel):
    key: AutomationMode
    label: str
    description: str
    auto_collect: bool
    auto_build_events: bool
    auto_build_briefs: bool
    auto_publish_enabled: bool
    available: bool = True


class AutomationModeProfile(BaseModel):
    mode: AutomationMode
    collect_interval_minutes: int = Field(default=30, ge=5, le=360)
    brief_trigger: AutomationBriefTrigger = "manual"
    brief_schedule_time: Optional[str] = None
    delivery_target: AutomationDeliveryTarget = "local_only"
    selection_mode: AutomationSelectionMode = "all_new"
    brief_limit: int = Field(default=10, ge=1, le=100)
    publish_strategy: AutomationPublishStrategy = "disabled"
    publish_schedule_time: Optional[str] = None
    require_approval: bool = True
    notes: str = ""


class RuntimePlan(BaseModel):
    launch_mode: RuntimeLaunchMode = "interval_now"
    start_at: Optional[str] = None
    interval_minutes: Optional[int] = Field(default=30, ge=5, le=360)
    timezone: str = "Asia/Shanghai"
    effective_mode: AutomationMode = "radar_only"
    work_scope: IntelWorkScope = "collect_events_alerts"
    delivery_mode: DeliveryMode = "immediate"
    delivery_schedule_time: Optional[str] = None
    admission_strategy: AdmissionStrategy = "balanced"
    batch_limit: int = Field(default=3, ge=1, le=20)
    admission_filters: dict[str, bool | int] = Field(default_factory=dict)


class SourceConnector(BaseModel):
    key: str
    name: str
    kind: SourceKind
    driver: str
    platform: str = "rss"
    enabled: bool
    schedule: str
    interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    priority: int = Field(ge=1, le=10)
    weight: float = Field(default=0.7, ge=0.0, le=1.0)
    auth: dict[str, str] = Field(default_factory=dict)
    url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    origin_repo: str
    origin_license: str
    health_status: SourceHealth = "idle"
    health_detail: str = ""
    item_count: int = Field(default=0, ge=0)
    last_synced_at: Optional[str] = None
    last_error: Optional[str] = None
    last_attempt_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    consecutive_failures: int = Field(default=0, ge=0)
    last_duration_ms: Optional[int] = Field(default=None, ge=0)
    avg_duration_ms: Optional[int] = Field(default=None, ge=0)
    last_item_count: int = Field(default=0, ge=0)
    updated_at: Optional[str] = None


class SourceConnectorPayload(BaseModel):
    enabled: bool
    schedule: str
    priority: int = Field(ge=1, le=10)
    url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CreateSourcePayload(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=128)
    kind: SourceKind = "rss"
    driver: str = "rss_feed"
    url: Optional[str] = None
    enabled: bool = True
    schedule: str = "*/30 * * * *"
    priority: int = Field(default=5, ge=1, le=10)
    weight: float = Field(default=0.7, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    auth: dict[str, str] = Field(default_factory=dict)


class RawItem(BaseModel):
    id: str
    source_key: str
    source_name: str
    source_kind: SourceKind
    title: str
    link: str
    published_at: str
    collected_at: str
    summary: str
    content: str
    author: str = ""
    tags: list[str] = Field(default_factory=list)
    engagement: dict[str, float | int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedItem(BaseModel):
    id: str
    raw_item_ids: list[str]
    title: str
    link: str
    summary: str
    published_at: str
    cluster_id: str
    cluster_members: list[str] = Field(default_factory=list)
    dedupe_key: str
    source_names: list[str]
    origin_sources: list[str] = Field(default_factory=list)
    source_weight: float
    trend_score: float
    final_score: float
    signals: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class PublishTask(BaseModel):
    id: str
    target_id: str
    action: str
    status: PublishTaskStatus
    stage: str
    message: str
    triggered_by: str
    created_at: str
    artifacts: list[str] = Field(default_factory=list)
    step_logs: list[str] = Field(default_factory=list)
    selector_profile: str = "wechat-mp-v1"


class BrowserSessionState(BaseModel):
    platform: Literal["wechat_mp"] = "wechat_mp"
    browser_name: str = "edge"
    user_data_dir: str = ""
    logged_in: bool = False
    last_checked_at: Optional[str] = None
    last_opened_url: Optional[str] = None
    last_error: Optional[str] = None
    selectors_version: str = "wechat-mp-v1"
    last_screenshot: Optional[str] = None
    last_selector_check: Optional[str] = None
    current_page: Optional[str] = None
    sidecar_health: BackendHealth = "offline"
    manager_alive: bool = False
    window_state: Optional[Literal["restored", "minimized", "unknown"]] = "unknown"
    resident_page: Optional[str] = None
    busy: bool = False
    last_reset_reason: Optional[str] = None
    session_generation: int = 0
    last_action: Optional[str] = None
    last_action_phase: Optional[str] = None
    is_session_level_error: bool = False
    last_draft_check: Optional["WeChatDraftSyncCheckResult"] = None


class BrowserSessionPayload(BaseModel):
    browser_name: str
    user_data_dir: str


class WeChatRemoteDraftItem(BaseModel):
    title: str = ""
    url: str = ""
    appmsg_id: Optional[str] = None
    updated_at: Optional[str] = None
    remote_key: Optional[str] = None


class WeChatDraftSyncCheckResult(BaseModel):
    checked_at: str
    remote_count: int = 0
    matched_count: int = 0
    missing_count: int = 0
    items: list[WeChatRemoteDraftItem] = Field(default_factory=list)
    message: str = ""


class WeChatDraftSyncCheckResponse(BaseModel):
    item: WeChatDraftSyncCheckResult


class WeChatMappingStatus(str):
    pass


class WeChatMappingRow(BaseModel):
    remote_title: str = ""
    remote_key: Optional[str] = None
    remote_appmsg_id: Optional[str] = None
    remote_url: str = ""
    remote_updated_at: Optional[str] = None
    local_brief_id: Optional[str] = None
    local_brief_title: Optional[str] = None
    local_stage: Optional[BriefStage] = None
    mapping_status: str = "unresolved"


class WeChatMappingSnapshot(BaseModel):
    checked_at: Optional[str] = None
    remote_count: int = 0
    matched_count: int = 0
    missing_count: int = 0
    message: str = ""
    items: list[WeChatRemoteDraftItem] = Field(default_factory=list)
    mapping_rows: list[WeChatMappingRow] = Field(default_factory=list)


class WeChatMappingResponse(BaseModel):
    item: WeChatMappingSnapshot


class PublishBackendStatus(BaseModel):
    key: str
    label: str
    health: BackendHealth
    detail: str
    configured: bool


class PublishBackendStatusResponse(BaseModel):
    items: list[PublishBackendStatus]


class ReferenceProject(BaseModel):
    local_name: str
    upstream_repo: str
    branch: str
    commit_sha: Optional[str] = None
    refreshed_at: Optional[str] = None
    layer: Literal["discovery", "aggregation", "writing", "wechat", "ops"]
    tags: list[str] = Field(default_factory=list)
    refresh_status: RefreshStatus = "missing"
    notes: Optional[str] = None
    local_exists: bool = False
    license_name: str = "unknown"
    borrow_mode: BorrowMode = "reference_only"
    borrow_targets: list[str] = Field(default_factory=list)


class WeChatChannelConfig(BaseModel):
    app_id: str = ""
    app_secret_masked: str = ""
    author: str = "Auto News Studio"
    default_cover_strategy: str = "auto"
    default_digest_strategy: str = "balanced"
    draft_mode: bool = True
    preview_enabled: bool = True
    auto_send_window: str = "09:00-10:00"
    risk_keywords: list[str] = Field(default_factory=list)
    browser_name: str = "edge"
    browser_profile_path: str = ""
    publish_entry_url: str = "https://mp.weixin.qq.com/"
    selectors_version: str = "wechat-mp-v1"
    sidecar_url: str = "http://127.0.0.1:8091"


class DashboardTopBar(BaseModel):
    current_mode_label: str
    healthy_sources: int
    total_sources: int
    latest_collected_at: Optional[str] = None
    latest_published_at: Optional[str] = None
    pending_briefs: int
    blocked_publish_count: int


class FreshnessSnapshot(BaseModel):
    latest_published_at: Optional[str] = None
    latest_collected_at: Optional[str] = None
    items_1h: int = 0
    items_6h: int = 0
    items_24h: int = 0
    avg_collection_lag_minutes: Optional[float] = None
    stale_source_count: int = 0
    has_staleness_alert: bool = False
    last_successful_sync_at: Optional[str] = None


class IntelStreamItem(BaseModel):
    id: str
    title: str
    summary: str
    link: str
    score: float
    source_names: list[str] = Field(default_factory=list)
    source_count: int = 0
    published_at: Optional[str] = None
    collected_at: Optional[str] = None
    time_lag_minutes: Optional[float] = None


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
    source_native_id: Optional[str] = None
    title_tokens: list[str] = Field(default_factory=list)
    anchor_tokens: list[str] = Field(default_factory=list)
    published_at: Optional[str] = None
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
    published_at: Optional[str] = None
    latest_collected_at: Optional[str] = None
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    anchor_tokens: list[str] = Field(default_factory=list)
    velocity_score: float = 0.0
    coverage_score: float = 0.0
    freshness_score: float = 0.0
    composite_score: float = 0.0
    velocity_details: dict[str, float] = Field(default_factory=dict)
    alert_state: IntelEventState = "new"
    change_state: IntelEventChangeState = "new_event"
    alert_reason: str = ""
    entity_ids: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    watchlisted: bool = False
    ignored: bool = False
    deep_dive_id: Optional[str] = None
    brief_id: Optional[str] = None
    deep_dive_status: Optional[DeepDiveStatus] = None
    brief_status: Optional[BriefStage] = None
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
    composite_score: float = 0.0
    alert_state: IntelEventState = "new"


class IntelAlert(BaseModel):
    id: str
    event_id: str
    title: str
    level: IntelAlertLevel
    reason: str
    velocity_score: float = 0.0
    coverage_score: float = 0.0
    freshness_score: float = 0.0
    composite_score: float = 0.0
    platform_count: int = 0
    source_count: int = 0
    representative_link: str
    triggered_at: str
    entity_ids: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    deep_dive_id: Optional[str] = None
    brief_id: Optional[str] = None
    deep_dive_status: Optional[DeepDiveStatus] = None
    brief_status: Optional[BriefStage] = None
    deep_dive_summary: str = ""
    worth_to_brief: bool = False
    worth_reason: str = ""


class DeepDiveSourceItem(BaseModel):
    source_key: str = ""
    source_name: str = ""
    original_link: str
    canonical_link: str
    title: str = ""
    published_at: Optional[str] = None
    fetch_status: DeepDiveFetchStatus = "pending"
    extract_status: DeepDiveExtractStatus = "pending"
    word_count: int = 0
    cleaned_full_text: str = ""
    excerpt: str = ""
    quotes: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class EventDeepDive(BaseModel):
    id: str
    event_id: str
    status: DeepDiveStatus = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
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
    last_error: Optional[str] = None


class BriefItem(BaseModel):
    id: str
    event_id: str
    deep_dive_id: str
    brief_level: BriefLevel = "rule"
    stage: BriefStage = "prepared"
    title: str
    one_line: str = ""
    why_it_matters: str = ""
    facts: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    prompt_package_markdown: str = ""
    wechat_markdown: str = ""
    wechat_html: str = ""
    wechat_target_id: Optional[str] = None
    wechat_editor_url: Optional[str] = None
    wechat_remote_appmsg_id: Optional[str] = None
    preview_url: Optional[str] = None
    delivery_status: Optional[str] = None
    delivery_attempt_count: int = 0
    last_delivery_attempt_at: Optional[str] = None
    last_verified_at: Optional[str] = None
    last_delivery_error_kind: Optional[str] = None
    needs_resync: bool = False
    last_synced_revision: Optional[str] = None
    last_successful_upload_at: Optional[str] = None
    last_error: Optional[str] = None
    updated_at: str


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
    added_at: Optional[str] = None


class EntityWatchlistSummaryItem(EntityWatchlistItem):
    event_count: int = 0
    alert_count: int = 0
    rising_count: int = 0
    breakout_count: int = 0
    last_seen_at: Optional[str] = None


class RuntimeSlowSource(BaseModel):
    source_key: str
    source_name: str
    duration_ms: int = 0
    status: str = "success"


class RuntimeIssueItem(BaseModel):
    source_key: Optional[str] = None
    source_name: Optional[str] = None
    error_kind: str
    message: str


class RuntimeCycleSummary(BaseModel):
    run_id: Optional[str] = None
    mode_key: AutomationMode = "radar_only"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: int = 0
    success_source_count: int = 0
    failed_source_count: int = 0
    new_items_count: int = 0
    new_events_count: int = 0
    growing_events_count: int = 0
    slow_sources: list[RuntimeSlowSource] = Field(default_factory=list)
    issues: list[RuntimeIssueItem] = Field(default_factory=list)
    selected_event_count: int = 0
    deep_dive_count: int = 0
    brief_count: int = 0
    wechat_sync_count: int = 0
    wechat_verify_count: int = 0
    publish_count: int = 0
    blocked_reason: Optional[str] = None
    recent_selected_titles: list[str] = Field(default_factory=list)
    recent_brief_titles: list[str] = Field(default_factory=list)
    recent_synced_titles: list[str] = Field(default_factory=list)


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
    last_sync_at: Optional[str] = None
    next_run_at: Optional[str] = None
    running: bool = False
    work_scope: IntelWorkScope = "collect_events_alerts"
    top_alerts: list[IntelAlert] = Field(default_factory=list)
    top_events: list[IntelEvent] = Field(default_factory=list)
    recent_alerts_24h: list[IntelAlertHistoryItem] = Field(default_factory=list)
    recent_events_24h: list[IntelEventHistoryItem] = Field(default_factory=list)
    source_alerts: list[str] = Field(default_factory=list)


class IntelSummaryResponse(BaseModel):
    item: IntelOverviewSummary


class DiscoveryItemsResponse(BaseModel):
    items: list[DiscoveryItem]


class IntelEventsResponse(BaseModel):
    items: list[IntelEvent]
    history_items: list[IntelEventHistoryItem] = Field(default_factory=list)


class IntelAlertsResponse(BaseModel):
    items: list[IntelAlert]
    history_items: list[IntelAlertHistoryItem] = Field(default_factory=list)


class IntelEventResponse(BaseModel):
    item: IntelEvent


class EventDeepDiveResponse(BaseModel):
    item: EventDeepDive


class EventDeepDivesResponse(BaseModel):
    items: list[EventDeepDive] = Field(default_factory=list)


class BriefResponse(BaseModel):
    item: BriefItem


class BriefsResponse(BaseModel):
    items: list[BriefItem] = Field(default_factory=list)


class DictOkResponse(BaseModel):
    ok: bool = True
    message: str = ""


class HotClusterCard(BaseModel):
    cluster_id: str
    title: str
    final_score: float
    member_count: int = 0
    source_names: list[str] = Field(default_factory=list)
    published_at: Optional[str] = None
    latest_collected_at: Optional[str] = None
    signals: list[str] = Field(default_factory=list)


class GithubSignalItem(BaseModel):
    id: str
    repo_name: str
    summary: str
    link: str
    stars_signal: int = 0
    source_name: str
    published_at: Optional[str] = None
    collected_at: Optional[str] = None


class IntelSnapshot(BaseModel):
    stream: list[IntelStreamItem]
    clusters: list[HotClusterCard]
    github_watch: list[GithubSignalItem]
    source_health: list[SourceConnector]


class ChainStateCard(BaseModel):
    key: str
    label: str
    status: ChainStatus
    detail: str


class ExecutionChainSnapshot(BaseModel):
    collect_status: ChainStatus
    admission_status: ChainStatus
    briefing_status: ChainStatus
    review_status: ChainStatus
    wechat_status: ChainStatus
    publish_status: ChainStatus
    blockers: list[str] = Field(default_factory=list)
    stages: list[ChainStateCard] = Field(default_factory=list)
    selectors_version: str
    browser_logged_in: bool = False
    last_screenshot: Optional[str] = None
    last_failed_task_label: Optional[str] = None
    last_failed_task_at: Optional[str] = None
    source_alerts: list[str] = Field(default_factory=list)


class SchedulerStatus(BaseModel):
    running: bool = False
    control_state: RuntimeControlState = "stopped"
    launch_mode: RuntimeLaunchMode = "interval_now"
    current_mode: AutomationMode = "radar_only"
    work_scope: IntelWorkScope = "collect_events_alerts"
    last_collect_at: Optional[str] = None
    last_event_sync_at: Optional[str] = None
    last_brief_at: Optional[str] = None
    next_collect_at: Optional[str] = None
    delivery_mode: DeliveryMode = "immediate"
    delivery_schedule_time: Optional[str] = None
    admission_strategy: AdmissionStrategy = "balanced"
    batch_limit: int = 3
    current_cycle: str = "idle"
    current_cycle_progress_percent: int = 0
    current_cycle_progress_done: int = 0
    current_cycle_progress_total: int = 0
    current_cycle_progress_label: Optional[str] = None
    stage_key: str = "idle"
    stage_label: str = "空闲"
    stage_index: int = 0
    stage_total: int = 0
    enabled_at: Optional[str] = None
    scheduled_start_at: Optional[str] = None
    current_cycle_started_at: Optional[str] = None
    last_cycle_started_at: Optional[str] = None
    last_cycle_finished_at: Optional[str] = None
    last_cycle_duration_seconds: Optional[float] = None
    uptime_seconds: int = 0
    completed_cycles_today: int = 0
    failed_cycles_today: int = 0
    last_error: Optional[str] = None
    blocked_reason: Optional[str] = None
    last_cycle_issue_count: int = 0
    last_cycle_issue_summary: Optional[str] = None
    run_id: Optional[str] = None
    run_status: AutomationRunStatus = "idle"
    run_stage: str = "idle"
    run_started_at: Optional[str] = None
    run_heartbeat_at: Optional[str] = None
    run_finished_at: Optional[str] = None
    run_triggered_by: Optional[str] = None
    run_error: Optional[str] = None
    recovered_run_id: Optional[str] = None
    run_stale: bool = False
    run_intent: RuntimeIntent = "normal_monitoring"
    last_run_outcome: Optional[RuntimeRunOutcome] = None
    last_cycle_summary: Optional[RuntimeCycleSummary] = None


class RuntimeIntentPayload(BaseModel):
    intent: RuntimeIntent


class DashboardStats(BaseModel):
    total_sources: int
    healthy_sources: int
    collected_today: int
    event_count: int
    deep_dive_ready: int = 0
    brief_total: int = 0
    brief_prepared: int = 0
    brief_synced: int = 0
    publish_blocked: int = 0


class LogItem(BaseModel):
    id: str
    level: LogLevel
    message: str
    created_at: str
    category: str
    stream: LogStream = "business_event"
    actor: str = "system"
    detail: Optional[str] = None


class DashboardResponse(BaseModel):
    app_version: AppVersionInfo
    update_info: AppUpdateInfo
    stats: DashboardStats
    top_bar: DashboardTopBar
    freshness: FreshnessSnapshot
    intel_stream: list[IntelStreamItem]
    hot_clusters: list[HotClusterCard]
    github_watch: list[GithubSignalItem]
    execution_chain: ExecutionChainSnapshot
    current_automation_mode: AutomationModeDefinition
    current_automation_profile: AutomationModeProfile
    automation_profiles: list[AutomationModeProfile]
    runtime_plan: RuntimePlan
    runtime_status: SchedulerStatus
    last_cycle_summary: Optional[RuntimeCycleSummary] = None
    recent_alerts_24h: list[IntelAlertHistoryItem] = Field(default_factory=list)
    recent_events_24h: list[IntelEventHistoryItem] = Field(default_factory=list)
    entity_watchlist_summary: list[EntityWatchlistSummaryItem] = Field(default_factory=list)
    recent_logs: list[LogItem]
    briefs: list[BriefItem] = Field(default_factory=list)
    deep_dives: list[EventDeepDive] = Field(default_factory=list)
    sources: list[SourceConnector]
    browser_session: BrowserSessionState
    publish_backends: list[PublishBackendStatus]
    setup_status: dict[str, Any] = Field(default_factory=dict)
    doctor_summary: dict[str, Any] = Field(default_factory=dict)


class IntelSnapshotResponse(BaseModel):
    item: IntelSnapshot


class AutomationModeSelectionPayload(BaseModel):
    mode: AutomationMode


class RuntimePlanPayload(BaseModel):
    launch_mode: RuntimeLaunchMode
    start_at: Optional[str] = None
    interval_minutes: Optional[int] = Field(default=None, ge=5, le=360)
    timezone: str = "Asia/Shanghai"
    work_scope: IntelWorkScope = "collect_events_alerts"
    delivery_mode: DeliveryMode = "immediate"
    delivery_schedule_time: Optional[str] = None
    admission_strategy: AdmissionStrategy = "balanced"
    batch_limit: int = Field(default=3, ge=1, le=20)
    admission_filters: dict[str, bool | int] = Field(default_factory=dict)


class EntityWatchlistPayload(BaseModel):
    items: list[EntityWatchlistItem] = Field(default_factory=list)


class EntityWatchlistResponse(BaseModel):
    items: list[EntityWatchlistItem] = Field(default_factory=list)


class BriefCopyPackageResponse(BaseModel):
    markdown: str = ""

class ChannelConfigPayload(BaseModel):
    app_id: str
    app_secret_masked: str
    author: str
    default_cover_strategy: str
    default_digest_strategy: str
    draft_mode: bool
    preview_enabled: bool
    auto_send_window: str
    risk_keywords: list[str]
    browser_name: str
    browser_profile_path: str
    publish_entry_url: str
    selectors_version: str
    sidecar_url: str


class SourceSyncResponse(BaseModel):
    raw_count: int
    normalized_count: int
    event_count: int
    synced_at: str
    warnings: list[str] = Field(default_factory=list)


class ReferenceProjectsResponse(BaseModel):
    items: list[ReferenceProject]


class SourcesResponse(BaseModel):
    items: list[SourceConnector]


class EventDeepDivePayload(BaseModel):
    force: bool = False


class PublishTasksResponse(BaseModel):
    items: list[PublishTask]


class LogsResponse(BaseModel):
    items: list[LogItem]


class BrowserSessionResponse(BaseModel):
    item: BrowserSessionState


class WeChatChannelResponse(BaseModel):
    item: WeChatChannelConfig


class SystemCheckItem(BaseModel):
    key: str
    label: str
    ok: bool
    detail: str
    next_action: Optional[str] = None


class SystemDoctorResult(BaseModel):
    checked_at: str
    ok: bool = False
    items: list[SystemCheckItem] = Field(default_factory=list)
    summary: str = ""


class AppVersionInfo(BaseModel):
    version: str
    release_channel: str = "stable"
    release_repo: str
    release_notes_url: str


class AppUpdateInfo(BaseModel):
    current_version: str
    latest_version: Optional[str] = None
    update_available: bool = False
    checked_at: str
    source: str = "unknown"
    release_url: Optional[str] = None
    release_notes_url: Optional[str] = None
    published_at: Optional[str] = None
    error: Optional[str] = None
    dismissed_version: Optional[str] = None


class AppUpdateResponse(BaseModel):
    item: AppUpdateInfo


class AppUpdateDismissPayload(BaseModel):
    version: str = ""


class SystemDoctorResponse(BaseModel):
    item: SystemDoctorResult


class ImportBackupResponse(BaseModel):
    ok: bool = True
    message: str = ""
    backup_path: Optional[str] = None


class AutomationModesResponse(BaseModel):
    current: AutomationModeDefinition
    items: list[AutomationModeDefinition]


class AutomationProfilesResponse(BaseModel):
    current: AutomationModeProfile
    items: list[AutomationModeProfile]


class SchedulerStatusResponse(BaseModel):
    item: SchedulerStatus


class RuntimePlanResponse(BaseModel):
    item: RuntimePlan


# LLM models have been moved to models_llm.py


class DictEnvelope(BaseModel):
    item: dict[str, Any]
