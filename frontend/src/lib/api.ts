import type {
  AppUpdateInfo,
  AutomationMode,
  AutomationModeDefinition,
  AutomationModeProfile,
  BrowserSessionState,
  BriefItem,
  BriefsResponse,
  ChainStateCard,
  DashboardResponse,
  DiscoveryItem,
  EntityWatchlistItem,
  EventDeepDive,
  EventDeepDivesResponse,
  EntityWatchlistSummaryItem,
  ExecutionChainSnapshot,
  FreshnessSnapshot,
  IntelAlert,
  IntelAlertsResponse,
  IntelEvent,
  IntelEventsResponse,
  IntelOverviewSummary,
  GithubSignalItem,
  HotClusterCard,
  IntelStreamItem,
  LogItem,
  LLMConfig,
  LLMTestResult,
  PublishBackendStatus,
  PublishTask,
  ReferenceProject,
  RuntimePlan,
  RuntimeIntent,
  SchedulerStatus,
  SourceConnector,
  SystemDoctorResult,
  WeChatChannelConfig,
  WeChatDraftSyncCheckResult,
  WeChatMappingSnapshot
} from "../types";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ??
  (typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:8000");

function normalizeDashboard(payload: DashboardResponse | Record<string, unknown>): DashboardResponse {
  const dashboard = payload as Partial<DashboardResponse>;
  const stats = dashboard.stats ?? {
    total_sources: 0,
    healthy_sources: 0,
    collected_today: 0,
    event_count: 0,
    deep_dive_ready: 0,
    brief_total: 0,
    brief_prepared: 0,
    brief_synced: 0,
    publish_blocked: 0
  };

  const topBar = dashboard.top_bar ?? {
    current_mode_label: dashboard.current_automation_mode?.label ?? "自动监测",
    healthy_sources: stats.healthy_sources,
    total_sources: stats.total_sources,
    latest_collected_at: null,
    latest_published_at: null,
    pending_briefs: stats.brief_prepared,
    blocked_publish_count: 0
  };

  const freshness: FreshnessSnapshot = dashboard.freshness ?? {
    latest_published_at: null,
    latest_collected_at: null,
    items_1h: 0,
    items_6h: 0,
    items_24h: stats.collected_today,
    avg_collection_lag_minutes: null,
    stale_source_count: 0,
    has_staleness_alert: false,
    last_successful_sync_at: null
  };

  const currentAutomationMode: AutomationModeDefinition = dashboard.current_automation_mode ?? {
    key: "radar_only",
    label: "仅雷达捕获",
    description: "",
    auto_collect: true,
    auto_build_events: true,
    auto_build_briefs: false,
    auto_publish_enabled: false,
    available: true
  };

  const runtimeStatus: SchedulerStatus = dashboard.runtime_status ?? {
    running: false,
    control_state: "stopped",
    launch_mode: "interval_now",
    current_mode: currentAutomationMode.key,
    work_scope: "collect_events_alerts",
    last_collect_at: null,
    last_event_sync_at: null,
    last_brief_at: null,
    next_collect_at: null,
    delivery_mode: "immediate",
    delivery_schedule_time: null,
    admission_strategy: "balanced",
    batch_limit: 3,
    current_cycle: "idle",
    current_cycle_progress_percent: 0,
    current_cycle_progress_done: 0,
    current_cycle_progress_total: 0,
    current_cycle_progress_label: null,
    stage_key: "idle",
    stage_label: "空闲",
    stage_index: 0,
    stage_total: 0,
    enabled_at: null,
    scheduled_start_at: null,
    current_cycle_started_at: null,
    last_cycle_started_at: null,
    last_cycle_finished_at: null,
    last_cycle_duration_seconds: null,
    uptime_seconds: 0,
    completed_cycles_today: 0,
    failed_cycles_today: 0,
    last_error: null,
    blocked_reason: null,
    last_cycle_issue_count: 0,
    last_cycle_issue_summary: null,
    run_id: null,
    run_status: "idle",
    run_stage: "idle",
    run_started_at: null,
    run_heartbeat_at: null,
    run_finished_at: null,
    run_triggered_by: null,
    run_error: null,
    recovered_run_id: null,
    run_stale: false,
    run_intent: "normal_monitoring",
    last_run_outcome: null,
    last_cycle_summary: null
  };

  const currentAutomationProfile: AutomationModeProfile = dashboard.current_automation_profile ?? {
    mode: currentAutomationMode.key,
    collect_interval_minutes: 30,
    brief_trigger: currentAutomationMode.auto_build_briefs ? "after_sync" : "manual",
    brief_schedule_time: null,
    delivery_target: "local_only",
    selection_mode: "top_scored",
    brief_limit: 6,
    publish_strategy: "disabled",
    publish_schedule_time: null,
    require_approval: true,
    notes: ""
  };

  const runtimePlan: RuntimePlan = dashboard.runtime_plan ?? {
    launch_mode: "interval_now",
    start_at: null,
    interval_minutes: currentAutomationProfile.collect_interval_minutes,
    timezone: "Asia/Shanghai",
    effective_mode: currentAutomationMode.key,
    work_scope: "collect_events_alerts",
    delivery_mode: "immediate",
    delivery_schedule_time: null,
    admission_strategy: "balanced",
    batch_limit: 3,
    admission_filters: {
      require_watchlisted: false,
      require_entity_match: false,
      min_source_count: 0,
      min_fulltext_count: 1,
      breakout_only: false,
      exclude_existing_brief: true,
      exclude_synced_brief: true
    }
  };

  const executionChain: ExecutionChainSnapshot = dashboard.execution_chain ?? {
    collect_status: "idle",
    admission_status: "idle",
    briefing_status: "idle",
    review_status: "idle",
    wechat_status: "idle",
    publish_status: "idle",
    blockers: [],
    stages: [] as ChainStateCard[],
    selectors_version: dashboard.browser_session?.selectors_version ?? "wechat-mp-v1",
    browser_logged_in: Boolean(dashboard.browser_session?.logged_in),
    last_screenshot: dashboard.browser_session?.last_screenshot ?? null,
    last_failed_task_label: null,
    last_failed_task_at: null,
    source_alerts: []
  };

  const appVersion = dashboard.app_version ?? {
    version: "0.2.2",
    release_channel: "stable",
    release_repo: "pengqiyu123/auto-news-studio",
    release_notes_url: "https://github.com/pengqiyu123/auto-news-studio/releases"
  };

  const updateInfo: AppUpdateInfo = dashboard.update_info ?? {
    current_version: appVersion.version,
    latest_version: null,
    update_available: false,
    checked_at: new Date().toISOString(),
    source: "unknown",
    release_url: appVersion.release_notes_url,
    release_notes_url: appVersion.release_notes_url,
    published_at: null,
    error: null,
    dismissed_version: null
  };

  return {
    app_version: appVersion,
    update_info: updateInfo,
    stats,
    top_bar: topBar,
    freshness,
    intel_stream: (dashboard.intel_stream ?? []) as IntelStreamItem[],
    hot_clusters: (dashboard.hot_clusters ?? []) as HotClusterCard[],
    github_watch: (dashboard.github_watch ?? []) as GithubSignalItem[],
    execution_chain: executionChain,
    current_automation_mode: currentAutomationMode,
    current_automation_profile: currentAutomationProfile,
    automation_profiles: (dashboard.automation_profiles ?? [currentAutomationProfile]) as AutomationModeProfile[],
    runtime_plan: runtimePlan,
    runtime_status: runtimeStatus,
    last_cycle_summary: dashboard.last_cycle_summary ?? runtimeStatus.last_cycle_summary ?? null,
    recent_alerts_24h: dashboard.recent_alerts_24h ?? [],
    recent_events_24h: dashboard.recent_events_24h ?? [],
    entity_watchlist_summary: (dashboard.entity_watchlist_summary ?? []) as EntityWatchlistSummaryItem[],
    recent_logs: dashboard.recent_logs ?? [],
    briefs: dashboard.briefs ?? [],
    deep_dives: dashboard.deep_dives ?? [],
    sources: dashboard.sources ?? [],
    browser_session: dashboard.browser_session ?? {
      platform: "wechat_mp",
      browser_name: "edge",
      user_data_dir: "",
      logged_in: false,
      selectors_version: "wechat-mp-v1",
      sidecar_health: "offline",
      manager_alive: false,
      window_state: "unknown",
      resident_page: null,
      busy: false
    },
    publish_backends: dashboard.publish_backends ?? []
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  getDashboard: async () => normalizeDashboard(await request<DashboardResponse>("/api/admin/dashboard")),
  getIntelSummary: () => request<{ item: IntelOverviewSummary }>("/api/admin/intel/summary"),
  getDiscoveryItems: () => request<{ items: DiscoveryItem[] }>("/api/admin/intel/stream"),
  getIntelEvents: () => request<IntelEventsResponse>("/api/admin/intel/events"),
  getIntelEvent: (eventId: string) => request<{ item: IntelEvent }>(`/api/admin/intel/events/${eventId}`),
  getIntelAlerts: () => request<IntelAlertsResponse>("/api/admin/intel/alerts"),
  createEventDeepDive: (eventId: string, force = false) =>
    request<{ item: EventDeepDive }>(`/api/admin/intel/events/${eventId}/deep-dive`, {
      method: "POST",
      body: JSON.stringify({ force })
    }),
  getEventDeepDives: () => request<EventDeepDivesResponse>("/api/admin/intel/deep-dives"),
  getEventDeepDive: (eventId: string) => request<{ item: EventDeepDive }>(`/api/admin/intel/deep-dives/${eventId}`),
  createBriefFromEvent: (eventId: string) =>
    request<{ item: BriefItem }>(`/api/admin/intel/events/${eventId}/brief`, {
      method: "POST"
    }),
  getBriefs: () => request<BriefsResponse>("/api/admin/briefs"),
  getBrief: (briefId: string) => request<{ item: BriefItem }>(`/api/admin/briefs/${briefId}`),
  syncBriefWeChatDraft: (briefId: string) =>
    request<{ item: BriefItem }>(`/api/admin/briefs/${briefId}/wechat-draft`, {
      method: "POST"
    }),
  deleteBrief: (briefId: string, remote = "auto") =>
    request<{ ok: boolean; message: string }>(`/api/admin/briefs/${briefId}?remote=${encodeURIComponent(remote)}`, {
      method: "DELETE"
    }),
  copyBriefPackage: (briefId: string) =>
    request<{ markdown: string }>(`/api/admin/briefs/${briefId}/copy-package`, {
      method: "POST"
    }),
  getEntityWatchlist: () => request<{ items: EntityWatchlistItem[] }>("/api/admin/entities/watchlist"),
  updateEntityWatchlist: (items: EntityWatchlistItem[]) =>
    request<{ items: EntityWatchlistItem[] }>("/api/admin/entities/watchlist", {
      method: "PUT",
      body: JSON.stringify({ items })
    }),
  getIntelSources: () => request<{ items: SourceConnector[] }>("/api/admin/intel/sources"),
  watchlistEvent: (eventId: string) =>
    request<{ item: IntelEvent }>(`/api/admin/intel/watchlist/${eventId}`, { method: "POST" }),
  ignoreEvent: (eventId: string) =>
    request<{ item: IntelEvent }>(`/api/admin/intel/ignore/${eventId}`, { method: "POST" }),
  getAutomationModes: () =>
    request<{ current: AutomationModeDefinition; items: AutomationModeDefinition[] }>("/api/admin/automation/modes"),
  getCurrentAutomationMode: () =>
    request<{ current: AutomationModeDefinition; items: AutomationModeDefinition[] }>("/api/admin/automation/current"),
  setAutomationMode: (mode: AutomationMode) =>
    request<{ current: AutomationModeDefinition; items: AutomationModeDefinition[] }>("/api/admin/automation/current", {
      method: "PUT",
      body: JSON.stringify({ mode })
    }),
  getAutomationProfiles: () =>
    request<{ current: AutomationModeProfile; items: AutomationModeProfile[] }>("/api/admin/automation/profiles"),
  updateAutomationProfile: (mode: AutomationMode, payload: AutomationModeProfile) =>
    request<{ current: AutomationModeProfile; items: AutomationModeProfile[] }>(`/api/admin/automation/profiles/${mode}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  getRuntimeStatus: () => request<{ item: SchedulerStatus }>("/api/admin/runtime/status"),
  getRuntimePlan: () => request<{ item: RuntimePlan }>("/api/admin/runtime/plan"),
  updateRuntimePlan: (payload: Omit<RuntimePlan, "effective_mode">) =>
    request<{ item: RuntimePlan }>("/api/admin/runtime/plan", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  startRuntime: () => request<{ item: SchedulerStatus }>("/api/admin/runtime/start", { method: "POST" }),
  stopRuntime: () => request<{ item: SchedulerStatus }>("/api/admin/runtime/stop", { method: "POST" }),
  runRuntimeIntent: (intent: RuntimeIntent) =>
    request<{ item: SchedulerStatus }>("/api/admin/runtime/run-intent", {
      method: "POST",
      body: JSON.stringify({ intent })
    }),
  getSources: () => request<{ items: SourceConnector[] }>("/api/admin/sources"),
  updateSource: (sourceKey: string, payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">) =>
    request<{ item: SourceConnector }>(`/api/admin/sources/${sourceKey}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  createSource: (payload: {
    key: string;
    name: string;
    kind: string;
    driver: string;
    url?: string;
    enabled?: boolean;
    schedule?: string;
    priority?: number;
    weight?: number;
    tags?: string[];
    auth?: Record<string, string>;
  }) =>
    request<{ item: SourceConnector }>("/api/admin/sources", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  deleteSource: (sourceKey: string) =>
    request<{ ok: boolean }>(`/api/admin/sources/${sourceKey}`, { method: "DELETE" }),
  syncSources: () =>
    request<{ raw_count: number; normalized_count: number; event_count: number; synced_at: string; warnings: string[] }>(
      "/api/admin/sources/sync",
      { method: "POST" }
    ),
  syncSource: (sourceKey: string) =>
    request<{ raw_count: number; normalized_count: number; event_count: number; synced_at: string; warnings: string[] }>(
      `/api/admin/sources/${sourceKey}/sync`,
      { method: "POST" }
    ),
  getPublishTasks: () => request<{ items: PublishTask[] }>("/api/admin/publish-tasks"),
  getWeChatConfig: () =>
    request<{ item: WeChatChannelConfig }>("/api/admin/channels/wechat"),
  updateWeChatConfig: (payload: WeChatChannelConfig) =>
    request<{ item: WeChatChannelConfig }>("/api/admin/channels/wechat", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  getBrowserSession: () =>
    request<{ item: BrowserSessionState }>("/api/admin/browser/wechat/session"),
  updateBrowserSession: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) =>
    request<{ item: BrowserSessionState }>("/api/admin/browser/wechat/session", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  openWeChatDashboard: () =>
    request<{ item: BrowserSessionState }>("/api/admin/browser/wechat/open-dashboard", {
      method: "POST"
    }),
  checkWeChatBrowserSession: () =>
    request<{ item: BrowserSessionState }>("/api/admin/browser/wechat/check", {
      method: "POST"
    }),
  checkWeChatDraftBox: () =>
    request<{ item: WeChatDraftSyncCheckResult }>("/api/admin/browser/wechat/check-drafts", {
      method: "POST"
    }),
  getWeChatMapping: () =>
    request<{ item: WeChatMappingSnapshot }>("/api/admin/wechat/mapping"),
  refreshWeChatMapping: () =>
    request<{ item: WeChatMappingSnapshot }>("/api/admin/wechat/mapping/refresh", {
      method: "POST"
    }),
  deleteWeChatRemoteDraft: (remoteId: string) =>
    request<{ ok: boolean; message: string }>(`/api/admin/wechat/remote-drafts/${encodeURIComponent(remoteId)}`, {
      method: "DELETE"
    }),
  getPublishBackends: () =>
    request<{ items: PublishBackendStatus[] }>("/api/admin/publish/backends"),
  getReferenceProjects: () =>
    request<{ items: ReferenceProject[] }>("/api/admin/reference-projects"),
  getLogs: () => request<{ items: LogItem[] }>("/api/admin/logs"),
  uploadImage: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetch(`${API_BASE}/api/admin/images/upload`, {
      method: "POST",
      body: formData
    }).then((res) => {
      if (!res.ok) throw new Error("Image upload failed");
      return res.json() as Promise<{ url: string }>;
    });
  },
  getLLMConfig: () => request<{ item: LLMConfig }>("/api/admin/llm/config"),
  updateLLMConfig: (payload: LLMConfig) =>
    request<{ item: LLMConfig }>("/api/admin/llm/config", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  testLLMProvider: (providerKey: string) =>
    request<LLMTestResult>(`/api/admin/llm/test/${providerKey}`, { method: "POST" }),
  getLLMUsage: () => request<{ item: Record<string, Record<string, number>> }>("/api/admin/llm/usage"),
  getCCSwitchProviders: () =>
    request<{ providers: import("../types").CCSwitchProviderInfo[]; db_available: boolean }>("/api/admin/llm/cc-switch/providers"),
  importCCSwitchProviders: (providerIds: string[]) =>
    request<{ item: LLMConfig }>("/api/admin/llm/cc-switch/import", {
      method: "POST",
      body: JSON.stringify({ provider_ids: providerIds }),
    }),
  openCCSwitch: () =>
    request<{ ok: boolean }>("/api/admin/llm/cc-switch/open", { method: "POST" }),
  getSettings: () => request<{ item: Record<string, unknown> }>("/api/admin/settings"),
  updateSettings: (payload: Record<string, unknown>) =>
    request<{ item: Record<string, unknown> }>("/api/admin/settings", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  getSystemDoctor: () => request<{ item: SystemDoctorResult }>("/api/admin/system/doctor"),
  getSystemUpdate: (force = false) =>
    request<{ item: AppUpdateInfo }>(`/api/admin/system/update?force=${force ? "true" : "false"}`),
  dismissSystemUpdate: (version: string) =>
    request<{ item: AppUpdateInfo }>("/api/admin/system/update/dismiss", {
      method: "POST",
      body: JSON.stringify({ version })
    }),
  exportSystemConfig: async () => {
    const response = await fetch(`${API_BASE}/api/admin/system/export-config`, { method: "POST" });
    if (!response.ok) throw new Error("导出配置失败");
    return response.blob();
  },
  exportSystemBackup: async () => {
    const response = await fetch(`${API_BASE}/api/admin/system/export-backup`, { method: "POST" });
    if (!response.ok) throw new Error("导出备份失败");
    return response.blob();
  },
  importSystemBackup: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(`${API_BASE}/api/admin/system/import-backup`, {
      method: "POST",
      body: formData
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json() as Promise<{ ok: boolean; message: string; backup_path?: string | null }>;
  }
};
