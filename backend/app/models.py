from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


PublishMode = Literal[
    "draft_only",
    "draft_and_preview",
    "draft_preview_browser",
    "auto_send_guarded",
    "full_auto",
]

AutomationMode = Literal[
    "radar_only",
    "radar_and_draft",
    "full_pipeline",
]
AutomationDraftTrigger = Literal["manual", "after_sync", "scheduled"]
AutomationDraftDelivery = Literal["local_only", "wechat_draft"]
AutomationSelectionMode = Literal["all_new", "top_scored"]
AutomationPublishStrategy = Literal["disabled", "wechat_draft_only", "guarded_send"]

PipelineStage = Literal[
    "collected",
    "curated",
    "drafted",
    "preview_ready",
    "approved",
    "published",
    "failed",
]

AuditStatus = Literal["pending", "approved", "rejected", "not_required"]
JobStatus = Literal["queued", "running", "completed", "failed"]
LogLevel = Literal["info", "warning", "error", "success"]
SourceKind = Literal[
    "rss",
    "rsshub",
    "newsnow",
    "bilibili",
    "toutiao",
    "reddit",
    "youtube",
    "github",
    "hackernews",
    "page",
]
SourceHealth = Literal["idle", "healthy", "warning", "error"]
CandidateStatus = Literal["new", "drafted", "parked"]
PublishTaskStatus = Literal["pending", "running", "completed", "failed", "blocked"]
RefreshStatus = Literal["ready", "updated", "pending_retry", "missing"]
BorrowMode = Literal["direct_copy", "ported", "reference_only"]
BackendHealth = Literal["healthy", "warning", "offline"]
ChainStatus = Literal["idle", "running", "healthy", "warning", "blocked"]
LogStream = Literal["system_runtime", "business_event"]
ArticleVariant = Literal["flash_explainer"]
RuntimeControlState = Literal["stopped", "armed", "running", "waiting"]
RuntimeLaunchMode = Literal["once_now", "once_at", "interval_now", "interval_at"]


class ModeDefinition(BaseModel):
    key: PublishMode
    label: str
    description: str
    auto_collect: bool
    auto_draft: bool
    sync_to_wechat_draft: bool
    auto_open_preview: bool
    requires_human_review: bool
    allow_auto_send: bool
    allow_auto_retry: bool


class AutomationModeDefinition(BaseModel):
    key: AutomationMode
    label: str
    description: str
    auto_collect: bool
    auto_generate_candidates: bool
    auto_generate_drafts: bool
    auto_publish_enabled: bool
    available: bool = True


class AutomationModeProfile(BaseModel):
    mode: AutomationMode
    collect_interval_minutes: int = Field(default=30, ge=5, le=360)
    draft_trigger: AutomationDraftTrigger = "manual"
    draft_schedule_time: Optional[str] = None
    draft_delivery: AutomationDraftDelivery = "local_only"
    draft_selection: AutomationSelectionMode = "all_new"
    draft_limit: int = Field(default=10, ge=1, le=100)
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


class SourceConnector(BaseModel):
    key: str
    name: str
    kind: SourceKind
    driver: str
    enabled: bool
    schedule: str
    priority: int = Field(ge=1, le=10)
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
    updated_at: Optional[str] = None


class SourceConnectorPayload(BaseModel):
    enabled: bool
    schedule: str
    priority: int = Field(ge=1, le=10)
    url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


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


class CandidateTopic(BaseModel):
    id: str
    normalized_item_id: str
    title: str
    summary: str
    recommended_angle: str
    article_type: str
    rationale: str
    evidence_links: list[str] = Field(default_factory=list)
    source_names: list[str] = Field(default_factory=list)
    source_count: int = Field(ge=0)
    score: float
    status: CandidateStatus = "new"
    recommended_mode: PublishMode = "draft_only"
    facts: list[str] = Field(default_factory=list)
    angles: list[dict[str, str]] = Field(default_factory=list)
    selected_angle: Optional[str] = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    published_at: Optional[str] = None
    collected_at: Optional[str] = None
    freshness_bucket: str = "unknown"
    draft_exists: bool = False
    normalized_score: float = 0.0
    updated_at: str


class BodyBlock(BaseModel):
    kind: str
    heading: Optional[str] = None
    content: str
    evidence_links: list[str] = Field(default_factory=list)
    required_image: bool = False


class ImageSlot(BaseModel):
    slot_id: str
    label: str
    position: str
    suggestion: str
    required_image: bool = False
    fulfilled: bool = False
    keywords: list[str] = Field(default_factory=list)


class DraftItem(BaseModel):
    id: str
    candidate_topic_id: str
    title: str
    section: str
    source_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    publish_mode: PublishMode
    pipeline_stage: PipelineStage
    audit_status: AuditStatus
    summary: str
    brief: dict[str, Any] = Field(default_factory=dict)
    outline: dict[str, Any] = Field(default_factory=dict)
    article_variant: ArticleVariant = "flash_explainer"
    reader_summary: str = ""
    body_blocks: list[BodyBlock] = Field(default_factory=list)
    image_slots: list[ImageSlot] = Field(default_factory=list)
    editor_notes: list[str] = Field(default_factory=list)
    markdown: str
    html: str
    wechat_html: str
    updated_at: str
    cover_strategy: str
    cover_suggestion: str
    risk_flags: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
    title_options: list[str] = Field(default_factory=list)
    composition_trace: dict[str, Any] = Field(default_factory=dict)
    render_backend: str = "python-template"
    approval_required: bool = True
    wechat_draft_id: Optional[str] = None
    wechat_editor_url: Optional[str] = None
    wechat_remote_appmsg_id: Optional[str] = None
    preview_url: Optional[str] = None
    last_error: Optional[str] = None


class PublishTask(BaseModel):
    id: str
    draft_id: str
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


class BrowserSessionPayload(BaseModel):
    browser_name: str
    user_data_dir: str


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
    waiting_review: int
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
    candidate_status: Optional[CandidateStatus] = None
    draft_stage: Optional[PipelineStage] = None
    candidate_id: Optional[str] = None
    draft_id: Optional[str] = None


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
    candidate_status: Optional[CandidateStatus] = None
    draft_stage: Optional[PipelineStage] = None
    candidate_id: Optional[str] = None
    draft_id: Optional[str] = None


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
    candidate_status: ChainStatus
    draft_status: ChainStatus
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
    last_collect_at: Optional[str] = None
    last_candidate_at: Optional[str] = None
    last_draft_at: Optional[str] = None
    next_collect_at: Optional[str] = None
    current_cycle: str = "idle"
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


class DashboardStats(BaseModel):
    current_mode: PublishMode
    mode_label: str
    total_sources: int
    healthy_sources: int
    collected_today: int
    candidate_count: int
    total_drafts: int
    waiting_review: int
    preview_ready: int
    published_today: int
    failed_jobs: int
    last_job_label: Optional[str] = None
    last_job_status: Optional[JobStatus] = None
    last_job_at: Optional[str] = None


class JobItem(BaseModel):
    id: str
    action: str
    label: str
    status: JobStatus
    triggered_by: str
    started_at: str
    finished_at: Optional[str] = None
    message: Optional[str] = None


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
    current_mode: ModeDefinition
    drafts: list[DraftItem]
    recent_jobs: list[JobItem]
    recent_logs: list[LogItem]
    recent_candidates: list[CandidateTopic]
    sources: list[SourceConnector]
    browser_session: BrowserSessionState
    publish_backends: list[PublishBackendStatus]


class IntelSnapshotResponse(BaseModel):
    item: IntelSnapshot


class ModeSelectionPayload(BaseModel):
    mode: PublishMode


class AutomationModeSelectionPayload(BaseModel):
    mode: AutomationMode


class RuntimePlanPayload(BaseModel):
    launch_mode: RuntimeLaunchMode
    start_at: Optional[str] = None
    interval_minutes: Optional[int] = Field(default=None, ge=5, le=360)
    timezone: str = "Asia/Shanghai"


class JobRunPayload(BaseModel):
    action: Literal[
        "collect_news",
        "rebuild_candidates",
        "build_digest",
        "sync_wechat_draft",
        "open_preview",
        "publish_pipeline",
        "check_browser",
    ]


class CandidateDraftPayload(BaseModel):
    publish_mode: Optional[PublishMode] = None


class DraftContentPayload(BaseModel):
    markdown: str
    title: str


class DraftApprovalPayload(BaseModel):
    approved: bool = True


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
    candidate_count: int
    synced_at: str
    warnings: list[str] = Field(default_factory=list)


class BatchDraftResponse(BaseModel):
    processed_count: int
    created_count: int
    skipped_count: int
    failed_count: int
    draft_ids: list[str] = Field(default_factory=list)
    message: str = ""


class ReferenceProjectsResponse(BaseModel):
    items: list[ReferenceProject]


class SourcesResponse(BaseModel):
    items: list[SourceConnector]


class CandidatesResponse(BaseModel):
    items: list[CandidateTopic]


class DraftsResponse(BaseModel):
    items: list[DraftItem]


class PublishTasksResponse(BaseModel):
    items: list[PublishTask]


class LogsResponse(BaseModel):
    items: list[LogItem]


class JobsResponse(BaseModel):
    items: list[JobItem]


class BrowserSessionResponse(BaseModel):
    item: BrowserSessionState


class WeChatChannelResponse(BaseModel):
    item: WeChatChannelConfig


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


class LLMProviderConfig(BaseModel):
    key: str
    api_key: str = ""
    base_url: str = ""
    enabled: bool = False
    last_tested_at: Optional[str] = None
    last_test_result: Optional[str] = None


class LLMTaskConfig(BaseModel):
    task_key: str
    label: str = ""
    provider_key: str = ""
    model_id: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=64, le=32768)
    system_prompt: str = ""


class LLMConfig(BaseModel):
    providers: list[LLMProviderConfig] = Field(default_factory=list)
    tasks: list[LLMTaskConfig] = Field(default_factory=list)
    usage_today: dict[str, dict[str, int]] = Field(default_factory=dict)


class LLMConfigResponse(BaseModel):
    item: LLMConfig


class LLMProviderPayload(BaseModel):
    key: str
    api_key: str = ""
    base_url: str = ""
    enabled: bool = False


class LLMTaskPayload(BaseModel):
    task_key: str
    label: str = ""
    provider_key: str = ""
    model_id: str = ""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=64, le=32768)
    system_prompt: str = ""


class LLMTestResult(BaseModel):
    ok: bool
    model: str = ""
    content: str = ""
    latency_ms: float = 0.0
    error: str = ""


class LLMUsageResponse(BaseModel):
    item: dict[str, dict[str, int]]


class DictEnvelope(BaseModel):
    item: dict[str, Any]
