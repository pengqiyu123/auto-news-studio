export type AutomationMode =
  | "manual"
  | "automated"
  | "radar_only"
  | "radar_and_draft"
  | "full_pipeline";
export type AutomationBriefTrigger = "manual" | "after_sync" | "scheduled";
export type AutomationDeliveryTarget = "local_only" | "wechat_draft";
export type AutomationSelectionMode = "all_new" | "top_scored";
export type AutomationPublishStrategy = "disabled" | "wechat_draft_only" | "guarded_send";

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
export type PublishTaskStatus = "pending" | "running" | "completed" | "failed" | "blocked";
export type RefreshStatus = "ready" | "updated" | "pending_retry" | "missing";
export type BorrowMode = "direct_copy" | "ported" | "reference_only";
export type BackendHealth = "healthy" | "warning" | "offline";
export type ChainStatus = "idle" | "running" | "healthy" | "warning" | "blocked";
export type LogStream = "system_runtime" | "business_event";
export type RuntimeControlState = "stopped" | "armed" | "running" | "waiting";
export type RuntimeLaunchMode = "once_now" | "once_at" | "interval_now" | "interval_at";
export type IntelWorkScope = "collect_only" | "collect_events" | "collect_events_alerts";
export type RuntimeIntent = "normal_monitoring" | "collect_validation" | "event_rebuild" | "alert_rebuild";
export type RuntimeRunOutcome = "completed" | "failed" | "abandoned" | "stopped";
export type DeliveryMode = "collect_only" | "local_digest" | "immediate" | "scheduled_batch";
export type AdmissionStrategy = "top_scored" | "conservative" | "balanced" | "aggressive";
export type IntelEventState = "new" | "watch" | "rising" | "breakout" | "cooling";
export type IntelAlertLevel = "watch" | "rising" | "breakout" | "cooling";
export type IntelItemChangeState = "new_item" | "seen_item" | "updated_item";
export type IntelEventChangeState = "new_event" | "growing_event" | "stable_event" | "cooling_event";
export type HistoryRecordStatus = "active" | "cooled" | "source_uncertain";
export type DeepDiveStatus = "pending" | "running" | "partial" | "ready" | "failed";
export type DeepDiveFetchStatus = "pending" | "fetched" | "fetch_failed" | "fetch_blocked" | "non_html";
export type DeepDiveExtractStatus = "pending" | "extracted" | "extract_failed" | "too_short";
export type BriefLevel = "rule" | "enhanced" | "article";
export type BriefStage = "prepared" | "synced" | "failed";
export type BriefRecordStatus = "local_only" | "draft_synced" | "published";
export type BriefRecordException = "pending_confirmation" | "draft_check_failed" | "publish_check_failed" | "draft_missing";
export type WorkflowMode = "traditional" | "agent";
export type AgentWorkflowStatus = "running" | "completed" | "failed" | "abandoned";
export type AgentWorkflowStep =
  | "sources_sync"
  | "event_selected"
  | "deep_dive_ready"
  | "material_brief_ready"
  | "article_saved"
  | "wechat_uploaded"
  | "douyin_uploaded";

export interface AutomationModeDefinition {
  key: AutomationMode;
  label: string;
  description: string;
  auto_collect: boolean;
  auto_build_events: boolean;
  auto_build_briefs: boolean;
  auto_publish_enabled: boolean;
  available: boolean;
}

export interface AutomationModeProfile {
  mode: AutomationMode;
  collect_interval_minutes: number;
  brief_trigger: AutomationBriefTrigger;
  brief_schedule_time?: string | null;
  delivery_target: AutomationDeliveryTarget;
  selection_mode: AutomationSelectionMode;
  brief_limit: number;
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
  delivery_mode: DeliveryMode;
  delivery_schedule_time?: string | null;
  admission_strategy: AdmissionStrategy;
  batch_limit: number;
  admission_filters: {
    require_watchlisted?: boolean;
    require_entity_match?: boolean;
    min_source_count?: number;
    min_fulltext_count?: number;
    breakout_only?: boolean;
    exclude_existing_brief?: boolean;
    exclude_synced_brief?: boolean;
  };
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
  target_id: string;
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
  manager_alive?: boolean;
  window_state?: "restored" | "minimized" | "unknown";
  resident_page?: string | null;
  busy?: boolean;
  last_reset_reason?: string | null;
  session_generation?: number;
  last_action?: string | null;
  last_action_phase?: string | null;
  is_session_level_error?: boolean;
  last_draft_check?: WeChatDraftSyncCheckResult | null;
  last_analytics_overview?: WeChatAnalyticsOverview | null;
  last_publish_history_check?: WeChatPublishHistorySnapshot | null;
}

export interface WeChatRemoteDraftItem {
  title: string;
  url: string;
  appmsg_id?: string | null;
  updated_at?: string | null;
  remote_key?: string | null;
}

export interface WeChatDraftSyncCheckResult {
  checked_at: string;
  remote_count: number;
  matched_count: number;
  missing_count: number;
  items: WeChatRemoteDraftItem[];
  message: string;
  check_ok?: boolean;
}

export interface WeChatPublishRecordItem {
  title: string;
  url: string;
  appmsg_id?: string | null;
  published_at?: string | null;
  remote_key?: string | null;
  read_count: number;
  like_count: number;
  share_count: number;
  recommend_count: number;
  comment_count: number;
  highlight_count: number;
  tip_amount: string;
  reprint_count: number;
  thumbnail?: string;
}

export interface WeChatAnalyticsOverview {
  total_users: number;
  yesterday_reads: number;
  yesterday_shares: number;
  yesterday_new_follows: number;
  stats_window_label: string;
  fetched_at: string;
  avatar_url?: string;
  account_name?: string;
  original_count?: number;
}

export interface WeChatPublishHistorySnapshot {
  checked_at: string;
  record_count: number;
  items: WeChatPublishRecordItem[];
  overview?: WeChatAnalyticsOverview | null;
  message: string;
  check_ok?: boolean;
}

export type WeChatMappingStatus = "matched" | "remote_only" | "local_only" | "unresolved";

export interface WeChatMappingRow {
  remote_title: string;
  remote_key?: string | null;
  remote_appmsg_id?: string | null;
  remote_url: string;
  remote_updated_at?: string | null;
  local_brief_id?: string | null;
  local_brief_title?: string | null;
  local_stage?: BriefStage | null;
  mapping_status: WeChatMappingStatus;
}

export interface WeChatMappingSnapshot {
  checked_at?: string | null;
  remote_count: number;
  matched_count: number;
  missing_count: number;
  message: string;
  items: WeChatRemoteDraftItem[];
  mapping_rows: WeChatMappingRow[];
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

export interface SystemCheckItem {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
  next_action?: string | null;
}

export interface SystemDoctorResult {
  checked_at: string;
  ok: boolean;
  items: SystemCheckItem[];
  summary: string;
}

export interface AppVersionInfo {
  version: string;
  release_channel: string;
  release_repo: string;
  release_notes_url: string;
}

export interface AppUpdateInfo {
  current_version: string;
  latest_version?: string | null;
  update_available: boolean;
  checked_at: string;
  source: string;
  release_url?: string | null;
  release_notes_url?: string | null;
  published_at?: string | null;
  error?: string | null;
  dismissed_version?: string | null;
  dismissed?: boolean;
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
  pending_briefs: number;
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
  entity_ids: string[];
  entity_names: string[];
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
  story_count: number;
  member_delta: number;
  platform_delta: number;
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
  entity_ids: string[];
  entity_names: string[];
  watchlisted: boolean;
  ignored: boolean;
  deep_dive_id?: string | null;
  brief_id?: string | null;
  deep_dive_status?: DeepDiveStatus | null;
  deep_dive_started_at?: string | null;
  deep_dive_finished_at?: string | null;
  deep_dive_updated_at?: string | null;
  brief_status?: BriefStage | null;
  deep_dive_summary?: string;
  worth_to_brief?: boolean;
  worth_reason?: string;
}

export interface IntelAlert {
  id: string;
  event_id: string;
  title: string;
  summary?: string;
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
  entity_ids: string[];
  entity_names: string[];
  deep_dive_id?: string | null;
  brief_id?: string | null;
  deep_dive_status?: DeepDiveStatus | null;
  brief_status?: BriefStage | null;
  deep_dive_summary?: string;
  worth_to_brief?: boolean;
  worth_reason?: string;
}

export interface DeepDiveSourceItem {
  source_key: string;
  source_name: string;
  original_link: string;
  canonical_link: string;
  title: string;
  published_at?: string | null;
  fetch_status: DeepDiveFetchStatus;
  extract_status: DeepDiveExtractStatus;
  word_count: number;
  cleaned_full_text: string;
  excerpt: string;
  quotes: string[];
  error?: string | null;
}

export interface EventDeepDive {
  id: string;
  event_id: string;
  status: DeepDiveStatus;
  started_at?: string | null;
  finished_at?: string | null;
  updated_at: string;
  attempted_count: number;
  success_count: number;
  failed_count: number;
  resolved_evidence_pack: Array<{
    discovery_item_id: string;
    source_key?: string;
    source_name: string;
    title: string;
    summary?: string;
    link: string;
    canonical_link?: string;
    published_at?: string | null;
    collected_at?: string | null;
    entity_names?: string[];
  }>;
  full_text_sources: DeepDiveSourceItem[];
  sources: DeepDiveSourceItem[];
  facts: string[];
  quotes: string[];
  timeline: string[];
  worthiness: {
    worth_to_brief?: boolean;
    reason?: string;
  };
  last_error?: string | null;
}

export interface BriefItem {
  id: string;
  event_id: string;
  deep_dive_id: string;
  brief_level: BriefLevel;
  stage: BriefStage;
  title: string;
  one_line: string;
  why_it_matters: string;
  facts: string[];
  quotes: string[];
  timeline: string[];
  entity_names: string[];
  source_links: string[];
  risk_notes: string[];
  prompt_package_markdown: string;
  wechat_markdown: string;
  wechat_html: string;
  wechat_target_id?: string | null;
  wechat_editor_url?: string | null;
  wechat_remote_appmsg_id?: string | null;
  preview_url?: string | null;
  delivery_status?: string | null;
  delivery_attempt_count?: number;
  last_delivery_attempt_at?: string | null;
  last_verified_at?: string | null;
  last_delivery_error_kind?: string | null;
  needs_resync?: boolean;
  last_synced_revision?: string | null;
  last_successful_upload_at?: string | null;
  last_error?: string | null;
  updated_at: string;
  driver_label?: string;
  record_status: BriefRecordStatus;
  record_exception?: BriefRecordException | null;
  draft_remote_updated_at?: string | null;
  publish_record_published_at?: string | null;
  workflow_mode: WorkflowMode;
  workflow_session_id?: string | null;
  read_count?: number;
  like_count?: number;
  share_count?: number;
  recommend_count?: number;
  comment_count?: number;
  highlight_count?: number;
  tip_amount?: string;
  reprint_count?: number;
  metrics_fetched_at?: string | null;
  included_events?: BriefIncludedEvent[];
}

export interface BriefIncludedEvent {
  event_id: string;
  title: string;
  alert_state: IntelEventState;
  source_count: number;
  deep_dive_status?: DeepDiveStatus | null;
  representative_link: string;
}

export interface AgentWorkflowItem {
  workflow_session_id: string;
  status: AgentWorkflowStatus;
  current_step: AgentWorkflowStep;
  event_id?: string | null;
  material_brief_id?: string | null;
  article_brief_id?: string | null;
  target_platforms: Array<"wechat" | "douyin">;
  last_error?: string | null;
  started_at: string;
  updated_at: string;
  finished_at?: string | null;
}

export interface IntelEventHistoryItem {
  history_id: string;
  event_id: string;
  title: string;
  summary: string;
  representative_link: string;
  entity_ids: string[];
  entity_names: string[];
  discovered_at: string;
  last_seen_at: string;
  expires_at: string;
  status: HistoryRecordStatus;
  latest_alert_state: IntelEventState;
  platform_count: number;
  source_count: number;
  member_count: number;
  member_delta: number;
  platform_delta: number;
  composite_score: number;
}

export interface IntelAlertHistoryItem {
  history_id: string;
  event_id: string;
  title: string;
  representative_link: string;
  entity_ids: string[];
  entity_names: string[];
  first_triggered_at: string;
  last_triggered_at: string;
  expires_at: string;
  highest_level: IntelAlertLevel;
  latest_level: IntelAlertLevel;
  status: HistoryRecordStatus;
  reason: string;
  platform_count: number;
  source_count: number;
  velocity_score: number;
  coverage_score: number;
  freshness_score: number;
  composite_score: number;
}

export interface EntityWatchlistItem {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  watchlisted: boolean;
  added_at?: string | null;
}

export interface EntityWatchlistSummaryItem extends EntityWatchlistItem {
  event_count: number;
  alert_count: number;
  rising_count: number;
  breakout_count: number;
  last_seen_at?: string | null;
}

export interface TopicInfo {
  topic_id: string;
  label: string;
  keywords: string[];
  event_count: number;
}

export interface TopicsResponse {
  items: TopicInfo[];
}

export interface EventRelationInfo {
  event_id: string;
  title: string;
  relation_type: string;
  weight: number;
  evidence: Record<string, unknown>;
}

export interface EventRelationsResponse {
  items: EventRelationInfo[];
}

export interface TrendSignalInfo {
  entity_id: string;
  entity_name: string;
  trend: string;
  trend_label: string;
  sma_7d: number;
  sma_14d: number;
  signals: Array<Record<string, unknown>>;
}

export interface TrendSignalsResponse {
  items: TrendSignalInfo[];
}

export interface AnalysisSignalInfo {
  entity_id: string;
  entity_name: string;
  trend: string;
  trend_label: string;
  sma_7d: number;
  sma_14d: number;
  recent_event_count: number;
  latest_event_title: string;
  latest_event_id?: string;
}

export interface AnalysisSignalsResponse {
  items: AnalysisSignalInfo[];
}

export interface AnalysisTopicEventInfo {
  event_id: string;
  title: string;
  composite_score: number;
  first_seen_at?: string | null;
}

export interface AnalysisTopicEventsResponse {
  items: AnalysisTopicEventInfo[];
}

export interface TopicPeriodicityInfo {
  topic_id: string;
  label: string;
  period_days: number;
  confidence: number;
  detected_at?: string;
}

export interface TopicPeriodicityResponse {
  items: TopicPeriodicityInfo[];
}

export interface TemporalRuleInfo {
  id: string;
  antecedent_event_id: string;
  consequent_event_id: string;
  antecedent_title: string;
  consequent_title: string;
  lag_days: number;
  support: number;
  confidence: number;
  lift: number;
}

export interface TemporalRulesResponse {
  items: TemporalRuleInfo[];
}

export type AnalysisBatchRunStatus = "running" | "success" | "failed";

export interface AnalysisBatchRunInfo {
  id: string;
  task_name: string;
  status: AnalysisBatchRunStatus;
  started_at: string;
  finished_at?: string | null;
  items_processed: number;
  error_message: string;
}

export interface AnalysisBatchStatusResponse {
  items: AnalysisBatchRunInfo[];
}

export type AnalysisFeedbackType = "confirm" | "correct" | "dismiss";

export interface AnalysisFeedbackPayload {
  target_type: string;
  target_id: string;
  feedback_type: AnalysisFeedbackType;
  correction?: {
    note?: string;
  };
}

export interface AnalysisFeedbackResponse {
  ok: boolean;
  feedback_id: string;
}

export type AnalysisReportScope = "daily" | "weekly" | "monthly";

export interface AnalysisReportRequest {
  scope: AnalysisReportScope;
  date_from: string;
  date_to: string;
  focus_entities?: string[];
  focus_topics?: string[];
}

export interface AnalysisReportSections {
  executive_summary: string;
  key_findings: string;
  risk_assessment: string;
  recommendation: string;
}

export interface AnalysisReportItem {
  report_id: string;
  scope: AnalysisReportScope | string;
  period_start: string;
  period_end: string;
  status: string;
  markdown: string;
  sections: AnalysisReportSections;
  created_at?: string;
}

export interface AnalysisReportResponse {
  item: AnalysisReportItem;
}

export interface AnalysisReportSummary {
  report_id: string;
  scope: AnalysisReportScope | string;
  period_start: string;
  period_end: string;
  status: string;
  preview: string;
  created_at?: string;
}

export interface AnalysisReportsResponse {
  items: AnalysisReportSummary[];
}

export interface AnalysisFeedbackStats {
  total: number;
  accurate_pct: number;
  by_type: Record<AnalysisFeedbackType, number>;
}

export interface RuntimeSlowSource {
  source_key: string;
  source_name: string;
  duration_ms: number;
  status: string;
}

export interface RuntimeIssueItem {
  source_key?: string | null;
  source_name?: string | null;
  error_kind: string;
  message: string;
}

export interface RuntimeCycleSummary {
  run_id?: string | null;
  mode_key: AutomationMode;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms: number;
  success_source_count: number;
  failed_source_count: number;
  new_items_count: number;
  new_events_count: number;
  growing_events_count: number;
  slow_sources: RuntimeSlowSource[];
  issues: RuntimeIssueItem[];
  selected_event_count: number;
  deep_dive_count: number;
  brief_count: number;
  wechat_sync_count: number;
  wechat_verify_count: number;
  publish_count: number;
  blocked_reason?: string | null;
  recent_selected_titles: string[];
  recent_brief_titles: string[];
  recent_synced_titles: string[];
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
  recent_alert_count_24h: number;
  recent_event_count_24h: number;
  recent_breakout_count_24h: number;
  recent_rising_count_24h: number;
  last_sync_at?: string | null;
  next_run_at?: string | null;
  running: boolean;
  work_scope: IntelWorkScope;
  top_alerts: IntelAlert[];
  top_events: IntelEvent[];
  recent_alerts_24h: IntelAlertHistoryItem[];
  recent_events_24h: IntelEventHistoryItem[];
  source_alerts: string[];
}

export interface IntelEventsResponse {
  items: IntelEvent[];
  history_items: IntelEventHistoryItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface DiscoveryItemsResponse {
  items: DiscoveryItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  available_platforms?: string[];
  available_sources?: string[];
}

export interface IntelAlertsResponse {
  items: IntelAlert[];
  history_items: IntelAlertHistoryItem[];
}

export interface EventDeepDivesResponse {
  items: EventDeepDive[];
}

export interface BriefStageCounts {
  all: number;
  prepared: number;
  synced: number;
  failed: number;
}

export interface BriefRecordCounts {
  all: number;
  local_only: number;
  draft_synced: number;
  published: number;
  exceptions: number;
}

export interface BriefsResponse {
  items: BriefItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
  stage_counts: BriefStageCounts;
  record_counts: BriefRecordCounts;
}

export interface PublishTasksResponse {
  items: PublishTask[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface LogsResponse {
  items: LogItem[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
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
}

export interface ChainStateCard {
  key: string;
  label: string;
  status: ChainStatus;
  detail: string;
}

export interface ExecutionChainSnapshot {
  collect_status: ChainStatus;
  admission_status: ChainStatus;
  briefing_status: ChainStatus;
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
  last_event_sync_at?: string | null;
  last_brief_at?: string | null;
  next_collect_at?: string | null;
  delivery_mode: DeliveryMode;
  delivery_schedule_time?: string | null;
  admission_strategy: AdmissionStrategy;
  batch_limit: number;
  current_cycle: string;
  current_cycle_progress_percent: number;
  current_cycle_progress_done: number;
  current_cycle_progress_total: number;
  current_cycle_progress_label?: string | null;
  stage_key: string;
  stage_label: string;
  stage_index: number;
  stage_total: number;
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
  blocked_reason?: string | null;
  last_cycle_issue_count: number;
  last_cycle_issue_summary?: string | null;
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
  run_intent: RuntimeIntent;
  last_run_outcome?: RuntimeRunOutcome | null;
  last_cycle_summary?: RuntimeCycleSummary | null;
}

export type SettingsSectionKey = "ai" | "sources" | "browser" | "references" | "runtime" | "system";

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
  source?: string;
  cc_app_type?: string | null;
  cc_api_format?: "openai_chat" | "openai_responses" | "anthropic" | "gemini_native" | null;
  cc_is_full_url?: boolean | null;
  cc_endpoint_auto_select?: boolean | null;
  cc_endpoint_candidates?: string[];
  cc_base_url_raw?: string | null;
  cc_usage_base_url?: string | null;
  cc_last_verified_endpoint?: string | null;
  cc_last_verified_format?: string | null;
  cc_last_verified_model?: string | null;
  cc_probe_status?: string | null;
  cc_probe_message?: string | null;
}

export interface CCSwitchProviderInfo {
  id: string;
  label: string;
  description: string;
  provider_key: string;
  base_url: string;
  has_api_key: boolean;
  api_key_preview: string;
  model_id: string;
  cc_app_type: string;
  cc_category: string;
  cc_is_current: boolean;
  cc_api_format?: string | null;
  cc_is_full_url?: boolean | null;
  cc_endpoint_auto_select?: boolean | null;
  cc_endpoint_candidates?: string[];
  cc_health?: { is_healthy: boolean; consecutive_failures: number; last_error?: string | null } | null;
}

export interface LLMConfig {
  current_profile_id: string;
  fallback_profile_id?: string | null;
  profiles: LLMProfileConfig[];
  providers: LLMProviderConfig[];
  usage_today: Record<string, Record<string, number>>;
}

export interface LLMTestResult {
  ok: boolean;
  model: string;
  content: string;
  latency_ms: number;
  error: string;
  probe_status: string;
  probe_message: string;
  resolved_endpoint: string;
  resolved_format: string;
  resolved_model: string;
  supports_generation: boolean;
}

export interface DashboardResponse {
  app_version: AppVersionInfo;
  update_info: AppUpdateInfo;
  stats: {
    total_sources: number;
    healthy_sources: number;
    collected_today: number;
    event_count: number;
    deep_dive_ready: number;
    brief_total: number;
    brief_prepared: number;
    brief_synced: number;
    publish_blocked: number;
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
  last_cycle_summary?: RuntimeCycleSummary | null;
  recent_alerts_24h: IntelAlertHistoryItem[];
  recent_events_24h: IntelEventHistoryItem[];
  entity_watchlist_summary: EntityWatchlistSummaryItem[];
  recent_logs: LogItem[];
  briefs: BriefItem[];
  deep_dives: EventDeepDive[];
  sources: SourceConnector[];
  browser_session: BrowserSessionState;
  publish_backends: PublishBackendStatus[];
  setup_status?: Record<string, unknown>;
  doctor_summary?: Record<string, unknown>;
}
