"""Core Pydantic models for Auto News Studio.

Domain-specific models have been extracted into separate modules:
- models_publish.py: Publish/browser/WeChat/Douyin channel models
- models_intel.py: Intel/event/agent-html/discovery models
- models_llm.py: LLM provider and task configuration models

This file re-exports everything so all consumers can continue to
``from .models import ...`` unchanged.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .analysis import (  # noqa: F401
    AnalysisBatchRunInfo,
    AnalysisBatchStatusResponse,
    AnalysisFeedbackPayload,
    AnalysisFeedbackResponse,
    AnalysisFeedbackStatsResponse,
    AnalysisReportItem,
    AnalysisReportRequest,
    AnalysisReportResponse,
    AnalysisReportSections,
    AnalysisReportsResponse,
    AnalysisReportSummary,
    AnalysisSignalInfo,
    AnalysisSignalsResponse,
    AnalysisTopicEventInfo,
    AnalysisTopicEventsResponse,
    EventRelationInfo,
    EventRelationsResponse,
    TemporalRuleInfo,
    TemporalRulesResponse,
    TopicInfo,
    TopicPeriodicityInfo,
    TopicPeriodicityResponse,
    TopicsResponse,
    TrendSignalInfo,
    TrendSignalsResponse,
)

# Re-export intel/agent-html models
from .intel import (  # noqa: F401
    AgentHtmlAlertState,
    AgentHtmlDiscoverMode,
    AgentHtmlDiscoveryItem,
    AgentHtmlDiscoveryResponse,
    AgentHtmlDiscoveryRules,
    AgentHtmlDocument,
    AgentHtmlDocumentResponse,
    AgentHtmlDocumentRevision,
    AgentHtmlDocumentsResponse,
    AgentHtmlEvent,
    AgentHtmlEventChangeState,
    AgentHtmlEventHistoryItem,
    AgentHtmlEventResponse,
    AgentHtmlEventSnapshot,
    AgentHtmlEventsResponse,
    AgentHtmlExtractMode,
    AgentHtmlItemState,
    AgentHtmlMainlineBatchPayload,
    AgentHtmlRun,
    AgentHtmlRunBatchPayload,
    AgentHtmlRunResponse,
    AgentHtmlRunsResponse,
    AgentHtmlRunStatus,
    AgentHtmlTarget,
    AgentHtmlTargetCreatePayload,
    AgentHtmlTargetResponse,
    AgentHtmlTargetsResponse,
    AgentHtmlTargetType,
    AgentHtmlTargetUpdatePayload,
    DashboardTopBar,
    DeepDiveExtractStatus,
    DeepDiveFetchStatus,
    DeepDiveSourceItem,
    DeepDiveStatus,
    DiscoveryItem,
    DiscoveryItemsResponse,
    EntityWatchlistItem,
    EntityWatchlistPayload,
    EntityWatchlistResponse,
    EntityWatchlistSummaryItem,
    EventDeepDive,
    EventDeepDiveResponse,
    EventDeepDivesResponse,
    EventSnapshot,
    FreshnessSnapshot,
    HistoryRecordStatus,
    IntelAlert,
    IntelAlertHistoryItem,
    IntelAlertLevel,
    IntelAlertsResponse,
    IntelEvent,
    IntelEventChangeState,
    IntelEventHistoryItem,
    IntelEventResponse,
    IntelEventsResponse,
    IntelEventState,
    IntelItemChangeState,
    IntelOverviewSummary,
    IntelStreamItem,
    IntelSummaryResponse,
)

# Re-export LLM models
from .llm import (  # noqa: F401
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

# Re-export publish/browser models
from .publish import (  # noqa: F401
    BrowserSessionPayload,
    BrowserSessionResponse,
    BrowserSessionState,
    ChannelConfigPayload,
    DouyinArticleFillPayload,
    DouyinArticleStructureField,
    DouyinArticleStructureResponse,
    DouyinArticleStructureSnapshot,
    DouyinChannelConfig,
    DouyinChannelResponse,
    PublishBackendStatus,
    PublishBackendStatusResponse,
    PublishTask,
    PublishTasksResponse,
    WeChatAnalyticsDomResponse,
    WeChatAnalyticsDomSnapshot,
    WeChatAnalyticsOverview,
    WeChatArticleMetrics,
    WeChatChannelConfig,
    WeChatChannelResponse,
    WeChatDraftSyncCheckResponse,
    WeChatDraftSyncCheckResult,
    WeChatEditorDomField,
    WeChatEditorDomResponse,
    WeChatEditorDomSnapshot,
    WeChatMappingResponse,
    WeChatMappingRow,
    WeChatMappingSnapshot,
    WeChatMappingStatus,
    WeChatPublishHistoryResponse,
    WeChatPublishHistorySnapshot,
    WeChatPublishRecordItem,
    WeChatRemoteDraftItem,
)

# ---------------------------------------------------------------------------
# Literal type aliases — core system types
# ---------------------------------------------------------------------------
AutomationMode = Literal[
    "manual",
    "automated",
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
BriefLevel = Literal["rule", "enhanced", "article"]
BriefStage = Literal["prepared", "synced", "failed"]
BriefRecordStatus = Literal["local_only", "draft_synced", "published"]
BriefRecordException = Literal["pending_confirmation", "draft_check_failed", "publish_check_failed", "draft_missing"]
WorkflowMode = Literal["traditional", "agent"]
AgentWorkflowStatus = Literal["running", "completed", "failed", "abandoned"]
AgentWorkflowStep = Literal[
    "sources_sync",
    "event_selected",
    "deep_dive_ready",
    "material_brief_ready",
    "article_saved",
    "wechat_uploaded",
    "douyin_uploaded",
]
DeliveryMode = Literal["collect_only", "local_digest", "immediate", "scheduled_batch"]
AdmissionStrategy = Literal["top_scored", "conservative", "balanced", "aggressive"]

# Literal types moved to domain files but also needed here for re-export
PublishTaskStatus = Literal["pending", "running", "completed", "failed", "blocked"]


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
    brief_schedule_time: str | None = None
    delivery_target: AutomationDeliveryTarget = "local_only"
    selection_mode: AutomationSelectionMode = "all_new"
    brief_limit: int = Field(default=10, ge=1, le=100)
    publish_strategy: AutomationPublishStrategy = "disabled"
    publish_schedule_time: str | None = None
    require_approval: bool = True
    notes: str = ""


class RuntimePlan(BaseModel):
    launch_mode: RuntimeLaunchMode = "interval_now"
    start_at: str | None = None
    interval_minutes: int | None = Field(default=30, ge=5, le=360)
    timezone: str = "Asia/Shanghai"
    effective_mode: AutomationMode = "manual"
    work_scope: IntelWorkScope = "collect_events_alerts"
    delivery_mode: DeliveryMode = "collect_only"
    delivery_schedule_time: str | None = None
    admission_strategy: AdmissionStrategy = "top_scored"
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
    interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    priority: int = Field(ge=1, le=10)
    weight: float = Field(default=0.7, ge=0.0, le=1.0)
    auth: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    origin_repo: str
    origin_license: str
    health_status: SourceHealth = "idle"
    health_detail: str = ""
    item_count: int = Field(default=0, ge=0)
    last_synced_at: str | None = None
    last_error: str | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    last_duration_ms: int | None = Field(default=None, ge=0)
    avg_duration_ms: int | None = Field(default=None, ge=0)
    last_item_count: int = Field(default=0, ge=0)
    updated_at: str | None = None


class SourceConnectorPayload(BaseModel):
    enabled: bool
    schedule: str
    priority: int = Field(ge=1, le=10)
    url: str | None = None
    tags: list[str] = Field(default_factory=list)
    weight: float | None = Field(default=None, ge=0.0, le=1.0)


class CreateSourcePayload(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=128)
    kind: SourceKind = "rss"
    driver: str = "rss_feed"
    url: str | None = None
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


class BriefItem(BaseModel):
    id: str
    event_id: str
    deep_dive_id: str
    brief_level: BriefLevel = "rule"
    stage: BriefStage = "prepared"
    title: str
    summary: str = ""
    one_line: str = ""
    why_it_matters: str = ""
    facts: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    prompt_package_markdown: str = ""
    douyin_prompt_package_markdown: str = ""
    wechat_markdown: str = ""
    wechat_html: str = ""
    douyin_title: str = ""
    douyin_summary: str = ""
    douyin_markdown: str = ""
    wechat_target_id: str | None = None
    wechat_editor_url: str | None = None
    wechat_remote_appmsg_id: str | None = None
    preview_url: str | None = None
    delivery_status: str | None = None
    delivery_attempt_count: int = 0
    last_delivery_attempt_at: str | None = None
    last_verified_at: str | None = None
    last_delivery_error_kind: str | None = None
    needs_resync: bool = False
    last_synced_revision: str | None = None
    last_successful_upload_at: str | None = None
    last_error: str | None = None
    updated_at: str
    driver_label: str = ""
    record_status: BriefRecordStatus = "local_only"
    record_exception: BriefRecordException | None = None
    draft_remote_updated_at: str | None = None
    publish_record_published_at: str | None = None
    workflow_mode: WorkflowMode = "traditional"
    workflow_session_id: str | None = None
    read_count: int = 0
    like_count: int = 0
    share_count: int = 0
    recommend_count: int = 0
    comment_count: int = 0
    highlight_count: int = 0
    tip_amount: str = "0.00"
    reprint_count: int = 0
    metrics_fetched_at: str | None = None
    included_events: list[BriefIncludedEvent] = Field(default_factory=list)


class BriefIncludedEvent(BaseModel):
    event_id: str
    title: str
    alert_state: IntelEventState = "new"
    source_count: int = 0
    deep_dive_status: DeepDiveStatus | None = None
    representative_link: str = ""


class AgentWorkflowItem(BaseModel):
    workflow_session_id: str
    status: AgentWorkflowStatus = "running"
    current_step: AgentWorkflowStep = "sources_sync"
    event_id: str | None = None
    material_brief_id: str | None = None
    article_brief_id: str | None = None
    target_platforms: list[Literal["wechat", "douyin"]] = Field(default_factory=list)
    last_error: str | None = None
    started_at: str
    updated_at: str
    finished_at: str | None = None


class AgentArticlePayload(BaseModel):
    event_id: str
    title: str
    article_markdown: str
    summary: str = ""
    one_line: str = ""
    why_it_matters: str = ""
    facts: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    timeline: list[str] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    publish_to_wechat_draft: bool = False
    publish_to_douyin_article: bool = False
    triggered_by: str = "agent"
    driver_label: str = "external-ai"


class RuntimeSlowSource(BaseModel):
    source_key: str
    source_name: str
    duration_ms: int = 0
    status: str = "success"


class RuntimeIssueItem(BaseModel):
    source_key: str | None = None
    source_name: str | None = None
    error_kind: str
    message: str


class RuntimeCycleSummary(BaseModel):
    run_id: str | None = None
    mode_key: AutomationMode = "manual"
    started_at: str | None = None
    finished_at: str | None = None
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
    blocked_reason: str | None = None
    recent_selected_titles: list[str] = Field(default_factory=list)
    recent_brief_titles: list[str] = Field(default_factory=list)
    recent_synced_titles: list[str] = Field(default_factory=list)


class DictOkResponse(BaseModel):
    ok: bool = True
    message: str = ""


class HotClusterCard(BaseModel):
    cluster_id: str
    title: str
    final_score: float
    member_count: int = 0
    source_names: list[str] = Field(default_factory=list)
    published_at: str | None = None
    latest_collected_at: str | None = None
    signals: list[str] = Field(default_factory=list)


class GithubSignalItem(BaseModel):
    id: str
    repo_name: str
    summary: str
    link: str
    stars_signal: int = 0
    source_name: str
    published_at: str | None = None
    collected_at: str | None = None


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
    last_screenshot: str | None = None
    last_failed_task_label: str | None = None
    last_failed_task_at: str | None = None
    source_alerts: list[str] = Field(default_factory=list)


class SchedulerStatus(BaseModel):
    running: bool = False
    control_state: RuntimeControlState = "stopped"
    launch_mode: RuntimeLaunchMode = "interval_now"
    current_mode: AutomationMode = "manual"
    work_scope: IntelWorkScope = "collect_events_alerts"
    last_collect_at: str | None = None
    last_event_sync_at: str | None = None
    last_brief_at: str | None = None
    next_collect_at: str | None = None
    delivery_mode: DeliveryMode = "collect_only"
    delivery_schedule_time: str | None = None
    admission_strategy: AdmissionStrategy = "top_scored"
    batch_limit: int = 3
    current_cycle: str = "idle"
    current_cycle_progress_percent: int = 0
    current_cycle_progress_done: int = 0
    current_cycle_progress_total: int = 0
    current_cycle_progress_label: str | None = None
    stage_key: str = "idle"
    stage_label: str = "空闲"
    stage_index: int = 0
    stage_total: int = 0
    enabled_at: str | None = None
    scheduled_start_at: str | None = None
    current_cycle_started_at: str | None = None
    last_cycle_started_at: str | None = None
    last_cycle_finished_at: str | None = None
    last_cycle_duration_seconds: float | None = None
    uptime_seconds: int = 0
    completed_cycles_today: int = 0
    failed_cycles_today: int = 0
    last_error: str | None = None
    blocked_reason: str | None = None
    last_cycle_issue_count: int = 0
    last_cycle_issue_summary: str | None = None
    run_id: str | None = None
    run_status: AutomationRunStatus = "idle"
    run_stage: str = "idle"
    run_started_at: str | None = None
    run_heartbeat_at: str | None = None
    run_finished_at: str | None = None
    run_triggered_by: str | None = None
    run_error: str | None = None
    recovered_run_id: str | None = None
    run_stale: bool = False
    run_intent: RuntimeIntent = "normal_monitoring"
    last_run_outcome: RuntimeRunOutcome | None = None
    last_cycle_summary: RuntimeCycleSummary | None = None


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
    detail: str | None = None


class DashboardResponse(BaseModel):
    app_version: AppVersionInfo | None = None
    update_info: AppUpdateInfo | None = None
    stats: DashboardStats | None = None
    top_bar: DashboardTopBar | None = None
    freshness: FreshnessSnapshot | None = None
    intel_stream: list[IntelStreamItem] = Field(default_factory=list)
    hot_clusters: list[HotClusterCard] = Field(default_factory=list)
    github_watch: list[GithubSignalItem] = Field(default_factory=list)
    execution_chain: ExecutionChainSnapshot | None = None
    current_automation_mode: AutomationModeDefinition | None = None
    current_automation_profile: AutomationModeProfile | None = None
    automation_profiles: list[AutomationModeProfile] = Field(default_factory=list)
    runtime_plan: RuntimePlan | None = None
    runtime_status: SchedulerStatus | None = None
    last_cycle_summary: RuntimeCycleSummary | None = None
    recent_alerts_24h: list[IntelAlertHistoryItem] = Field(default_factory=list)
    recent_events_24h: list[IntelEventHistoryItem] = Field(default_factory=list)
    entity_watchlist_summary: list[EntityWatchlistSummaryItem] = Field(default_factory=list)
    recent_logs: list[LogItem] = Field(default_factory=list)
    briefs: list[BriefItem] = Field(default_factory=list)
    deep_dives: list[EventDeepDive] = Field(default_factory=list)
    sources: list[SourceConnector] = Field(default_factory=list)
    browser_session: BrowserSessionState | None = None
    publish_backends: list[PublishBackendStatus] = Field(default_factory=list)
    setup_status: dict[str, Any] = Field(default_factory=dict)
    doctor_summary: dict[str, Any] = Field(default_factory=dict)


class IntelSnapshotResponse(BaseModel):
    item: IntelSnapshot


class AutomationModeSelectionPayload(BaseModel):
    mode: AutomationMode


class RuntimePlanPayload(BaseModel):
    launch_mode: RuntimeLaunchMode
    start_at: str | None = None
    interval_minutes: int | None = Field(default=None, ge=5, le=360)
    timezone: str = "Asia/Shanghai"
    work_scope: IntelWorkScope = "collect_events_alerts"
    delivery_mode: DeliveryMode = "collect_only"
    delivery_schedule_time: str | None = None
    admission_strategy: AdmissionStrategy = "top_scored"
    batch_limit: int = Field(default=3, ge=1, le=20)
    admission_filters: dict[str, bool | int] = Field(default_factory=dict)


class SettingsUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_workers: int | None = Field(default=None, ge=1, le=20)
    tavily_api_key: str | None = None


class BriefResponse(BaseModel):
    item: BriefItem


class BriefStageCounts(BaseModel):
    all: int = 0
    prepared: int = 0
    synced: int = 0
    failed: int = 0


class BriefRecordCounts(BaseModel):
    all: int = 0
    local_only: int = 0
    draft_synced: int = 0
    published: int = 0
    exceptions: int = 0


class BriefsResponse(BaseModel):
    items: list[BriefItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False
    stage_counts: BriefStageCounts = Field(default_factory=BriefStageCounts)
    record_counts: BriefRecordCounts = Field(default_factory=BriefRecordCounts)


class AgentWorkflowResponse(BaseModel):
    item: AgentWorkflowItem


class AgentWorkflowsResponse(BaseModel):
    items: list[AgentWorkflowItem] = Field(default_factory=list)


class BriefCopyPackageResponse(BaseModel):
    markdown: str = ""


class SourceSyncResponse(BaseModel):
    raw_count: int
    normalized_count: int
    event_count: int
    synced_at: str
    warnings: list[str] = Field(default_factory=list)


class ReferenceProject(BaseModel):
    local_name: str
    upstream_repo: str
    branch: str
    commit_sha: str | None = None
    refreshed_at: str | None = None
    layer: Literal["discovery", "aggregation", "writing", "wechat", "ops"]
    tags: list[str] = Field(default_factory=list)
    refresh_status: RefreshStatus = "missing"
    notes: str | None = None
    local_exists: bool = False
    license_name: str = "unknown"
    borrow_mode: BorrowMode = "reference_only"
    borrow_targets: list[str] = Field(default_factory=list)


class ReferenceProjectsResponse(BaseModel):
    items: list[ReferenceProject]


class SourcesResponse(BaseModel):
    items: list[SourceConnector]


class EventDeepDivePayload(BaseModel):
    force: bool = False


class LogsResponse(BaseModel):
    items: list[LogItem]
    total: int = 0
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class SystemCheckItem(BaseModel):
    key: str
    label: str
    ok: bool
    detail: str
    next_action: str | None = None


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
    latest_version: str | None = None
    update_available: bool = False
    checked_at: str
    source: str = "unknown"
    release_url: str | None = None
    release_notes_url: str | None = None
    published_at: str | None = None
    error: str | None = None
    dismissed_version: str | None = None
    dismissed: bool = False


class AppUpdateResponse(BaseModel):
    item: AppUpdateInfo


class AppUpdateDismissPayload(BaseModel):
    version: str = ""


class SystemDoctorResponse(BaseModel):
    item: SystemDoctorResult


class ImportBackupResponse(BaseModel):
    ok: bool = True
    message: str = ""
    backup_path: str | None = None


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


class DictEnvelope(BaseModel):
    item: dict[str, Any]
