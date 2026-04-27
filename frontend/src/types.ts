export type PublishMode =
  | "draft_only"
  | "draft_and_preview"
  | "draft_preview_browser"
  | "auto_send_guarded"
  | "full_auto";

export type AutomationMode =
  | "radar_only"
  | "radar_and_draft"
  | "full_pipeline";
export type AutomationDraftTrigger = "manual" | "after_sync" | "scheduled";
export type AutomationDraftDelivery = "local_only" | "wechat_draft";
export type AutomationSelectionMode = "all_new" | "top_scored";
export type AutomationPublishStrategy = "disabled" | "wechat_draft_only" | "guarded_send";

export type PipelineStage =
  | "collected"
  | "curated"
  | "drafted"
  | "preview_ready"
  | "approved"
  | "published"
  | "failed";

export type AuditStatus = "pending" | "approved" | "rejected" | "not_required";
export type JobStatus = "queued" | "running" | "completed" | "failed";
export type LogLevel = "info" | "warning" | "error" | "success";
export type SourceKind =
  | "rss"
  | "rsshub"
  | "api"
  | "newsnow"
  | "bilibili"
  | "toutiao"
  | "reddit"
  | "youtube"
  | "github"
  | "hackernews"
  | "vvhan"
  | "legacy"
  | "page";
export type SourceHealth = "idle" | "healthy" | "warning" | "error";
export type AutomationRunStatus = "idle" | "running" | "completed" | "failed" | "abandoned";
export type CandidateStatus = "new" | "drafted" | "parked";
export type PublishTaskStatus = "pending" | "running" | "completed" | "failed" | "blocked";
export type RefreshStatus = "ready" | "updated" | "pending_retry" | "missing";
export type BorrowMode = "direct_copy" | "ported" | "reference_only";
export type BackendHealth = "healthy" | "warning" | "offline";
export type ChainStatus = "idle" | "running" | "healthy" | "warning" | "blocked";
export type LogStream = "system_runtime" | "business_event";
export type ArticleVariant = "flash_explainer";
export type RuntimeControlState = "stopped" | "armed" | "running" | "waiting";
export type RuntimeLaunchMode = "once_now" | "once_at" | "interval_now" | "interval_at";
export type IntelWorkScope = "collect_only" | "collect_events" | "collect_events_alerts";
export type IntelEventState = "new" | "watch" | "rising" | "breakout" | "cooling";
export type IntelAlertLevel = "watch" | "rising" | "breakout" | "cooling";
export type IntelItemChangeState = "new_item" | "seen_item" | "updated_item";
export type IntelEventChangeState = "new_event" | "growing_event" | "stable_event" | "cooling_event";

export interface ModeDefinition {
  key: PublishMode;
  label: string;
  description: string;
  auto_collect: boolean;
  auto_draft: boolean;
  sync_to_wechat_draft: boolean;
  auto_open_preview: boolean;
  requires_human_review: boolean;
  allow_auto_send: boolean;
  allow_auto_retry: boolean;
}

export interface AutomationModeDefinition {
  key: AutomationMode;
  label: string;
  description: string;
  auto_collect: boolean;
  auto_generate_candidates: boolean;
  auto_generate_drafts: boolean;
  auto_publish_enabled: boolean;
  available: boolean;
}

export interface AutomationModeProfile {
  mode: AutomationMode;
  collect_interval_minutes: number;
  draft_trigger: AutomationDraftTrigger;
  draft_schedule_time?: string | null;
  draft_delivery: AutomationDraftDelivery;
  draft_selection: AutomationSelectionMode;
  draft_limit: number;
  publish_strategy: AutomationPublishStrategy;
  publish_schedule_time?: string | null;
  require_approval: boolean;
  notes: string;
}

export interface RuntimePlan {
  launch_mode: RuntimeLaunchMode;
  start_at?: string | null;
  interval_minutes?: number | null;
  timezone: string;
  effective_mode: AutomationMode;
  work_scope: IntelWorkScope;
}

export interface SourceConnector {
  key: string;
  name: string;
  kind: SourceKind;
  driver: string;
  platform: string;
  enabled: boolean;
  schedule: string;
  interval_minutes?: number | null;
  priority: number;
  weight: number;
  auth: Record<string, string>;
  url?: string | null;
  tags: string[];
  capabilities: string[];
  origin_repo: string;
  origin_license: string;
  health_status: SourceHealth;
  health_detail: string;
  item_count: number;
  last_synced_at?: string | null;
  last_error?: string | null;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  consecutive_failures: number;
  last_duration_ms?: number | null;
  avg_duration_ms?: number | null;
  last_item_count: number;
  updated_at?: string | null;
}

export interface CandidateAngle {
  name: string;
  tone: string;
  focus: string;
  why: string;
}

export interface CandidateTopic {
  id: string;
  normalized_item_id: string;
  title: string;
  summary: string;
  recommended_angle: string;
  article_type: string;
  rationale: string;
  evidence_links: string[];
  source_names: string[];
  source_count: number;
  score: number;
  status: CandidateStatus;
  recommended_mode: PublishMode;
  facts: string[];
  angles: CandidateAngle[];
  selected_angle?: string | null;
  score_breakdown: Record<string, number>;
  published_at?: string | null;
  collected_at?: string | null;
  freshness_bucket: string;
  draft_exists: boolean;
  normalized_score: number;
  updated_at: string;
}

export interface DraftItem {
  id: string;
  candidate_topic_id: string;
  title: string;
  section: string;
  source_count: number;
  word_count: number;
  publish_mode: PublishMode;
  pipeline_stage: PipelineStage;
  audit_status: AuditStatus;
  summary: string;
  brief: {
    headline?: string;
    one_line?: string;
    facts?: string[];
    evidence_links?: string[];
    source_names?: string[];
    source_count?: number;
    published_at?: string | null;
    collected_at?: string | null;
    event_judgement?: string;
    risk_notes?: string[];
    time_context?: {
      published_at_label?: string;
      collected_at_label?: string;
    };
  };
  outline: {
    title_options?: string[];
    lead_direction?: string;
    key_points?: string[];
    section_order?: string[];
    closing_line?: string;
  };
  article_variant: ArticleVariant;
  reader_summary: string;
  body_blocks: Array<{
    kind: string;
    heading?: string | null;
    content: string;
    evidence_links?: string[];
    required_image?: boolean;
  }>;
  image_slots: Array<{
    slot_id: string;
    label: string;
    position: string;
    suggestion: string;
    required_image: boolean;
    fulfilled: boolean;
    keywords: string[];
  }>;
  editor_notes: string[];
  markdown: string;
  html: string;
  wechat_html: string;
  updated_at: string;
  cover_strategy: string;
  cover_suggestion: string;
  risk_flags: string[];
  blocked_reasons: string[];
  evidence_links: string[];
  title_options: string[];
  composition_trace: {
    facts?: string[];
    angles?: CandidateAngle[];
    selected_angle?: string;
    titles?: string[];
    evidence?: string[];
    generated_at?: string;
  };
  render_backend: string;
  approval_required: boolean;
  wechat_draft_id?: string | null;
  wechat_editor_url?: string | null;
  wechat_remote_appmsg_id?: string | null;
  preview_url?: string | null;
  last_error?: string | null;
}

export interface JobItem {
  id: string;
  action: string;
  label: string;
  status: JobStatus;
  triggered_by: string;
  started_at: string;
  finished_at?: string | null;
  message?: string | null;
}

export interface LogItem {
  id: string;
  level: LogLevel;
  message: string;
  created_at: string;
  category: string;
  stream: LogStream;
  actor: string;
  detail?: string | null;
}

export interface PublishTask {
  id: string;
  draft_id: string;
  action: string;
  status: PublishTaskStatus;
  stage: string;
  message: string;
  triggered_by: string;
  created_at: string;
  artifacts: string[];
  step_logs: string[];
  selector_profile: string;
}

export interface BrowserSessionState {
  platform: "wechat_mp";
  browser_name: string;
  user_data_dir: string;
  logged_in: boolean;
  last_checked_at?: string | null;
  last_opened_url?: string | null;
  last_error?: string | null;
  selectors_version: string;
  last_screenshot?: string | null;
  last_selector_check?: string | null;
  current_page?: string | null;
  sidecar_health: BackendHealth;
}

export interface PublishBackendStatus {
  key: string;
  label: string;
  health: BackendHealth;
  detail: string;
  configured: boolean;
}

export interface WeChatChannelConfig {
  app_id: string;
  app_secret_masked: string;
  author: string;
  default_cover_strategy: string;
  default_digest_strategy: string;
  draft_mode: boolean;
  preview_enabled: boolean;
  auto_send_window: string;
  risk_keywords: string[];
  browser_name: string;
  browser_profile_path: string;
  publish_entry_url: string;
  selectors_version: string;
  sidecar_url: string;
}

export interface ReferenceProject {
  local_name: string;
  upstream_repo: string;
  branch: string;
  commit_sha?: string | null;
  refreshed_at?: string | null;
  layer: "discovery" | "aggregation" | "writing" | "wechat" | "ops";
  tags: string[];
  refresh_status: RefreshStatus;
  notes?: string | null;
  local_exists: boolean;
  license_name: string;
  borrow_mode: BorrowMode;
  borrow_targets: string[];
}

export interface DashboardTopBar {
  current_mode_label: string;
  healthy_sources: number;
  total_sources: number;
  latest_collected_at?: string | null;
  latest_published_at?: string | null;
  waiting_review: number;
  blocked_publish_count: number;
}

export interface FreshnessSnapshot {
  latest_published_at?: string | null;
  latest_collected_at?: string | null;
  items_1h: number;
  items_6h: number;
  items_24h: number;
  avg_collection_lag_minutes?: number | null;
  stale_source_count: number;
  has_staleness_alert: boolean;
  last_successful_sync_at?: string | null;
}

export interface IntelStreamItem {
  id: string;
  title: string;
  summary: string;
  link: string;
  score: number;
  source_names: string[];
  source_count: number;
  published_at?: string | null;
  collected_at?: string | null;
  time_lag_minutes?: number | null;
  candidate_status?: CandidateStatus | null;
  draft_stage?: PipelineStage | null;
  candidate_id?: string | null;
  draft_id?: string | null;
}

export interface DiscoveryItem {
  id: string;
  raw_item_id: string;
  source_key: string;
  source_name: string;
  source_kind: string;
  platform: string;
  title: string;
  summary: string;
  content: string;
  link: string;
  canonical_link: string;
  dedupe_key: string;
  source_native_id?: string | null;
  title_tokens: string[];
  anchor_tokens: string[];
  published_at?: string | null;
  collected_at: string;
  tags: string[];
  engagement_score: number;
  item_state: IntelItemChangeState;
  metadata: Record<string, unknown>;
}

export interface IntelEvent {
  id: string;
  title: string;
  summary: string;
  representative_link: string;
  representative_source_name: string;
  representative_discovery_item_id: string;
  discovery_item_ids: string[];
  source_keys: string[];
  source_names: string[];
  platforms: string[];
  platform_count: number;
  source_count: number;
  member_count: number;
  published_at?: string | null;
  latest_collected_at?: string | null;
  first_seen_at?: string | null;
  last_seen_at?: string | null;
  tags: string[];
  anchor_tokens: string[];
  velocity_score: number;
  coverage_score: number;
  freshness_score: number;
  composite_score: number;
  velocity_details: Record<string, number>;
  alert_state: IntelEventState;
  change_state: IntelEventChangeState;
  alert_reason: string;
  watchlisted: boolean;
  ignored: boolean;
}

export interface IntelAlert {
  id: string;
  event_id: string;
  title: string;
  level: IntelAlertLevel;
  reason: string;
  velocity_score: number;
  coverage_score: number;
  freshness_score: number;
  composite_score: number;
  platform_count: number;
  source_count: number;
  representative_link: string;
  triggered_at: string;
}

export interface IntelOverviewSummary {
  alert_count: number;
  breakout_count: number;
  rising_count: number;
  watch_count: number;
  event_count: number;
  discovery_count: number;
  new_items_count: number;
  seen_items_count: number;
  updated_items_count: number;
  new_events_count: number;
  growing_events_count: number;
  stable_events_count: number;
  cooling_events_count: number;
  warning_sources: number;
  error_sources: number;
  healthy_sources: number;
  total_sources: number;
  last_sync_at?: string | null;
  next_run_at?: string | null;
  running: boolean;
  work_scope: IntelWorkScope;
  top_alerts: IntelAlert[];
  top_events: IntelEvent[];
  source_alerts: string[];
}

export interface HotClusterCard {
  cluster_id: string;
  title: string;
  final_score: number;
  member_count: number;
  source_names: string[];
  published_at?: string | null;
  latest_collected_at?: string | null;
  signals: string[];
}

export interface GithubSignalItem {
  id: string;
  repo_name: string;
  summary: string;
  link: string;
  stars_signal: number;
  source_name: string;
  published_at?: string | null;
  collected_at?: string | null;
  candidate_status?: CandidateStatus | null;
  draft_stage?: PipelineStage | null;
  candidate_id?: string | null;
  draft_id?: string | null;
}

export interface IntelSnapshot {
  stream: IntelStreamItem[];
  clusters: HotClusterCard[];
  github_watch: GithubSignalItem[];
  source_health: SourceConnector[];
}

export interface ChainStateCard {
  key: string;
  label: string;
  status: ChainStatus;
  detail: string;
}

export interface ExecutionChainSnapshot {
  collect_status: ChainStatus;
  candidate_status: ChainStatus;
  draft_status: ChainStatus;
  review_status: ChainStatus;
  wechat_status: ChainStatus;
  publish_status: ChainStatus;
  blockers: string[];
  stages: ChainStateCard[];
  selectors_version: string;
  browser_logged_in: boolean;
  last_screenshot?: string | null;
  last_failed_task_label?: string | null;
  last_failed_task_at?: string | null;
  source_alerts: string[];
}

export interface SchedulerStatus {
  running: boolean;
  control_state: RuntimeControlState;
  launch_mode: RuntimeLaunchMode;
  current_mode: AutomationMode;
  work_scope: IntelWorkScope;
  last_collect_at?: string | null;
  last_candidate_at?: string | null;
  last_draft_at?: string | null;
  next_collect_at?: string | null;
  current_cycle: string;
  current_cycle_progress_percent: number;
  current_cycle_progress_done: number;
  current_cycle_progress_total: number;
  current_cycle_progress_label?: string | null;
  enabled_at?: string | null;
  scheduled_start_at?: string | null;
  current_cycle_started_at?: string | null;
  last_cycle_started_at?: string | null;
  last_cycle_finished_at?: string | null;
  last_cycle_duration_seconds?: number | null;
  uptime_seconds: number;
  completed_cycles_today: number;
  failed_cycles_today: number;
  last_error?: string | null;
  run_id?: string | null;
  run_status: AutomationRunStatus;
  run_stage: string;
  run_started_at?: string | null;
  run_heartbeat_at?: string | null;
  run_finished_at?: string | null;
  run_triggered_by?: string | null;
  run_error?: string | null;
  recovered_run_id?: string | null;
  run_stale: boolean;
}

export interface BatchDraftResult {
  processed_count: number;
  created_count: number;
  skipped_count: number;
  failed_count: number;
  draft_ids: string[];
  message: string;
}

export type SettingsSectionKey = "channels" | "ai" | "sources" | "references" | "system";

export interface LLMProviderConfig {
  key: string;
  api_key: string;
  base_url: string;
  model_id: string;
  enabled: boolean;
  last_tested_at?: string | null;
  last_test_result?: string | null;
}

export interface LLMProfileConfig {
  id: string;
  label: string;
  description: string;
  provider_key: string;
  api_key: string;
  base_url: string;
  model_id: string;
  enabled: boolean;
  last_tested_at?: string | null;
  last_test_result?: string | null;
}

export interface LLMTaskConfig {
  task_key: string;
  label: string;
  provider_key: string;
  model_id: string;
  temperature: number;
  max_tokens: number;
  system_prompt: string;
}

export interface LLMConfig {
  current_profile_id: string;
  profiles: LLMProfileConfig[];
  providers: LLMProviderConfig[];
  tasks: LLMTaskConfig[];
  usage_today: Record<string, Record<string, number>>;
}

export interface LLMTestResult {
  ok: boolean;
  model: string;
  content: string;
  latency_ms: number;
  error: string;
}

export interface DashboardResponse {
  stats: {
    current_mode: PublishMode;
    mode_label: string;
    total_sources: number;
    healthy_sources: number;
    collected_today: number;
    candidate_count: number;
    total_drafts: number;
    waiting_review: number;
    preview_ready: number;
    published_today: number;
    failed_jobs: number;
    last_job_label?: string | null;
    last_job_status?: JobStatus | null;
    last_job_at?: string | null;
  };
  top_bar: DashboardTopBar;
  freshness: FreshnessSnapshot;
  intel_stream: IntelStreamItem[];
  hot_clusters: HotClusterCard[];
  github_watch: GithubSignalItem[];
  execution_chain: ExecutionChainSnapshot;
  current_automation_mode: AutomationModeDefinition;
  current_automation_profile: AutomationModeProfile;
  automation_profiles: AutomationModeProfile[];
  runtime_plan: RuntimePlan;
  runtime_status: SchedulerStatus;
  current_mode: ModeDefinition;
  drafts: DraftItem[];
  recent_jobs: JobItem[];
  recent_logs: LogItem[];
  recent_candidates: CandidateTopic[];
  sources: SourceConnector[];
  browser_session: BrowserSessionState;
  publish_backends: PublishBackendStatus[];
}
