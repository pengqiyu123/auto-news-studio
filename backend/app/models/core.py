"""Core Pydantic models for Auto News Studio.

Domain-specific models have been extracted into separate modules:
- models_publish.py: Publish/browser/WeChat/Douyin channel models
- models_intel.py: Intel/event/agent-html/discovery models
- models_llm.py: LLM provider and task configuration models

This file re-exports everything so all consumers can continue to
``from .models import ...`` unchanged.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

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

# Re-export intel/agent-html models
from .intel import (  # noqa: F401
    AgentHtmlDiscoveryItem,
    AgentHtmlDiscoveryResponse,
    AgentHtmlDiscoveryRules,
    AgentHtmlDocument,
    AgentHtmlDocumentResponse,
    AgentHtmlDocumentRevision,
    AgentHtmlDocumentsResponse,
    AgentHtmlEvent,
    AgentHtmlEventHistoryItem,
    AgentHtmlEventResponse,
    AgentHtmlEventSnapshot,
    AgentHtmlEventsResponse,
    AgentHtmlItemState,
    AgentHtmlMainlineBatchPayload,
    AgentHtmlRun,
    AgentHtmlRunBatchPayload,
    AgentHtmlRunResponse,
    AgentHtmlRunStatus,
    AgentHtmlRunsResponse,
    AgentHtmlTarget,
    AgentHtmlTargetCreatePayload,
    AgentHtmlTargetResponse,
    AgentHtmlTargetsResponse,
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
    IntelAlert,
    IntelAlertHistoryItem,
    IntelAlertLevel,
    IntelAlertsResponse,
    IntelEvent,
    IntelEventChangeState,
    IntelEventHistoryItem,
    IntelEventResponse,
    IntelEventState,
    IntelEventsResponse,
    IntelItemChangeState,
    IntelOverviewSummary,
    IntelStreamItem,
    IntelSummaryResponse,
    AgentHtmlAlertState,
    AgentHtmlDiscoverMode,
    AgentHtmlEventChangeState,
    AgentHtmlExtractMode,
    AgentHtmlTargetType,
    HistoryRecordStatus,
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
    effective_mode: AutomationMode = "manual"
    work_scope: IntelWorkScope = "collect_events_alerts"
    delivery_mode: DeliveryMode = "collect_only"
    delivery_schedule_time: Optional[str] = None
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
    driver_label: str = ""
    record_status: BriefRecordStatus = "local_only"
    record_exception: Optional[BriefRecordException] = None
    draft_remote_updated_at: Optional[str] = None
    publish_record_published_at: Optional[str] = None
    workflow_mode: WorkflowMode = "traditional"
    workflow_session_id: Optional[str] = None
    read_count: int = 0
    like_count: int = 0
    share_count: int = 0
    recommend_count: int = 0
    comment_count: int = 0
    highlight_count: int = 0
    tip_amount: str = "0.00"
    reprint_count: int = 0
    metrics_fetched_at: Optional[str] = None
    included_events: list["BriefIncludedEvent"] = Field(default_factory=list)


class BriefIncludedEvent(BaseModel):
    event_id: str
    title: str
    alert_state: IntelEventState = "new"
    source_count: int = 0
    deep_dive_status: Optional[DeepDiveStatus] = None
    representative_link: str = ""


class AgentWorkflowItem(BaseModel):
    workflow_session_id: str
    status: AgentWorkflowStatus = "running"
    current_step: AgentWorkflowStep = "sources_sync"
    event_id: Optional[str] = None
    material_brief_id: Optional[str] = None
    article_brief_id: Optional[str] = None
    target_platforms: list[Literal["wechat", "douyin"]] = Field(default_factory=list)
    last_error: Optional[str] = None
    started_at: str
    updated_at: str
    finished_at: Optional[str] = None


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
    publish_to_wechat_draft: bool = True
    publish_to_douyin_article: bool = False
    triggered_by: str = "agent"
    driver_label: str = "external-ai"


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
    mode_key: AutomationMode = "manual"
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
    current_mode: AutomationMode = "manual"
    work_scope: IntelWorkScope = "collect_events_alerts"
    last_collect_at: Optional[str] = None
    last_event_sync_at: Optional[str] = None
    last_brief_at: Optional[str] = None
    next_collect_at: Optional[str] = None
    delivery_mode: DeliveryMode = "collect_only"
    delivery_schedule_time: Optional[str] = None
    admission_strategy: AdmissionStrategy = "top_scored"
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
    app_version: Optional[AppVersionInfo] = None
    update_info: Optional[AppUpdateInfo] = None
    stats: Optional[DashboardStats] = None
    top_bar: Optional[DashboardTopBar] = None
    freshness: Optional[FreshnessSnapshot] = None
    intel_stream: list[IntelStreamItem] = Field(default_factory=list)
    hot_clusters: list[HotClusterCard] = Field(default_factory=list)
    github_watch: list[GithubSignalItem] = Field(default_factory=list)
    execution_chain: Optional[ExecutionChainSnapshot] = None
    current_automation_mode: Optional[AutomationModeDefinition] = None
    current_automation_profile: Optional[AutomationModeProfile] = None
    automation_profiles: list[AutomationModeProfile] = Field(default_factory=list)
    runtime_plan: Optional[RuntimePlan] = None
    runtime_status: Optional[SchedulerStatus] = None
    last_cycle_summary: Optional[RuntimeCycleSummary] = None
    recent_alerts_24h: list[IntelAlertHistoryItem] = Field(default_factory=list)
    recent_events_24h: list[IntelEventHistoryItem] = Field(default_factory=list)
    entity_watchlist_summary: list[EntityWatchlistSummaryItem] = Field(default_factory=list)
    recent_logs: list[LogItem] = Field(default_factory=list)
    briefs: list[BriefItem] = Field(default_factory=list)
    deep_dives: list[EventDeepDive] = Field(default_factory=list)
    sources: list[SourceConnector] = Field(default_factory=list)
    browser_session: Optional[BrowserSessionState] = None
    publish_backends: list[PublishBackendStatus] = Field(default_factory=list)
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
    delivery_mode: DeliveryMode = "collect_only"
    delivery_schedule_time: Optional[str] = None
    admission_strategy: AdmissionStrategy = "top_scored"
    batch_limit: int = Field(default=3, ge=1, le=20)
    admission_filters: dict[str, bool | int] = Field(default_factory=dict)


class SettingsUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_workers: Optional[int] = Field(default=None, ge=1, le=20)
    tavily_api_key: Optional[str] = None


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


class DictEnvelope(BaseModel):
    item: dict[str, Any]
