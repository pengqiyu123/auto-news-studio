import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type { DashboardResponse, IntelOverviewSummary, RuntimePlan } from "../../types";
import { useRuntimeState } from "./useRuntimeState";

vi.mock("../../lib/api", () => ({
  api: {
    getRuntimeStatus: vi.fn(),
    getAgentWorkflows: vi.fn(),
    startRuntime: vi.fn(),
    stopRuntime: vi.fn(),
    updateRuntimePlan: vi.fn(),
    runRuntimeIntent: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

const runtimeStatus: DashboardResponse["runtime_status"] = {
  running: true,
  control_state: "running",
  launch_mode: "interval_now",
  current_mode: "full_pipeline",
  work_scope: "collect_events_alerts",
  last_collect_at: null,
  last_event_sync_at: null,
  last_brief_at: null,
  next_collect_at: "2026-05-13T10:00:00+08:00",
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
  last_cycle_summary: null,
};

const dashboard: DashboardResponse = {
  app_version: {
    version: "0.2.11",
    release_channel: "stable",
    release_repo: "example/repo",
    release_notes_url: "https://example.com/release-notes",
  },
  update_info: {
    current_version: "0.2.11",
    latest_version: "0.2.11",
    update_available: false,
    checked_at: "2026-05-13T10:00:00+08:00",
    source: "github",
  },
  stats: {
    total_sources: 0,
    healthy_sources: 0,
    collected_today: 0,
    event_count: 0,
    deep_dive_ready: 0,
    brief_total: 0,
    brief_prepared: 0,
    brief_synced: 0,
    publish_blocked: 0,
  },
  top_bar: {
    current_mode_label: "智能模式",
    healthy_sources: 0,
    total_sources: 0,
    latest_collected_at: null,
    latest_published_at: null,
    pending_briefs: 0,
    blocked_publish_count: 0,
  },
  freshness: {
    latest_published_at: null,
    latest_collected_at: null,
    items_1h: 0,
    items_6h: 0,
    items_24h: 0,
    avg_collection_lag_minutes: null,
    stale_source_count: 0,
    has_staleness_alert: false,
    last_successful_sync_at: null,
  },
  intel_stream: [],
  hot_clusters: [],
  github_watch: [],
  execution_chain: {
    collect_status: "idle",
    admission_status: "idle",
    briefing_status: "idle",
    review_status: "idle",
    wechat_status: "idle",
    publish_status: "idle",
    blockers: [],
    stages: [],
    selectors_version: "wechat-mp-v1",
    browser_logged_in: true,
    source_alerts: [],
  },
  current_automation_mode: {
    key: "full_pipeline",
    label: "智能模式",
    description: "",
    auto_collect: true,
    auto_build_events: true,
    auto_build_briefs: true,
    auto_publish_enabled: false,
    available: true,
  },
  current_automation_profile: {
    mode: "full_pipeline",
    collect_interval_minutes: 15,
    brief_trigger: "manual",
    brief_schedule_time: null,
    delivery_target: "wechat_draft",
    selection_mode: "top_scored",
    brief_limit: 3,
    publish_strategy: "disabled",
    publish_schedule_time: null,
    require_approval: true,
    notes: "",
  },
  automation_profiles: [],
  runtime_plan: {
    launch_mode: "interval_now",
    start_at: null,
    interval_minutes: 15,
    timezone: "Asia/Shanghai",
    effective_mode: "full_pipeline",
    work_scope: "collect_events_alerts",
    delivery_mode: "immediate",
    delivery_schedule_time: null,
    admission_strategy: "balanced",
    batch_limit: 3,
    admission_filters: {},
  },
  runtime_status: runtimeStatus,
  last_cycle_summary: null,
  recent_alerts_24h: [],
  recent_events_24h: [],
  entity_watchlist_summary: [],
  recent_logs: [],
  briefs: [],
  deep_dives: [],
  sources: [],
  browser_session: {
    platform: "wechat_mp",
    browser_name: "edge",
    user_data_dir: "D:/profiles/wechat",
    logged_in: true,
    selectors_version: "wechat-mp-v1",
    sidecar_health: "healthy",
    manager_alive: true,
    window_state: "restored",
    resident_page: "home",
    busy: false,
  },
  publish_backends: [],
  setup_status: {},
  doctor_summary: {},
};

const summary: IntelOverviewSummary = {
  alert_count: 0,
  breakout_count: 0,
  rising_count: 0,
  watch_count: 0,
  event_count: 0,
  discovery_count: 0,
  new_items_count: 0,
  seen_items_count: 0,
  updated_items_count: 0,
  new_events_count: 0,
  growing_events_count: 0,
  stable_events_count: 0,
  cooling_events_count: 0,
  warning_sources: 0,
  error_sources: 0,
  healthy_sources: 0,
  total_sources: 0,
  recent_alert_count_24h: 0,
  recent_event_count_24h: 0,
  recent_breakout_count_24h: 0,
  recent_rising_count_24h: 0,
  last_sync_at: null,
  next_run_at: null,
  running: false,
  work_scope: "collect_events_alerts",
  top_alerts: [],
  top_events: [],
  recent_alerts_24h: [],
  recent_events_24h: [],
  source_alerts: [],
};

function makeHook() {
  const onReloadOverview = vi.fn().mockResolvedValue(undefined);
  const onRefreshAll = vi.fn().mockResolvedValue(undefined);
  const onError = vi.fn();
  const onToast = vi.fn();
  const onDashboardChange = vi.fn();
  const onSummaryChange = vi.fn();

  const hook = renderHook(() =>
    useRuntimeState({
      runtimePlan: dashboard.runtime_plan,
      onDashboardChange,
      onSummaryChange,
      onReloadOverview,
      onRefreshAll,
      onError,
      onToast,
    }),
  );

  return {
    ...hook,
    onReloadOverview,
    onRefreshAll,
    onError,
    onToast,
    onDashboardChange,
    onSummaryChange,
  };
}

describe("useRuntimeState", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("starts runtime and updates dashboard and summary through callbacks", async () => {
    mockedApi.getAgentWorkflows.mockResolvedValue({ items: [] });
    mockedApi.startRuntime.mockResolvedValue({ item: runtimeStatus });
    const { result, onReloadOverview, onToast, onDashboardChange, onSummaryChange } = makeHook();

    await act(async () => {
      await result.current.handleStartRuntime();
    });

    expect(mockedApi.startRuntime).toHaveBeenCalledTimes(1);
    expect(onReloadOverview).toHaveBeenCalledWith(false);
    expect(onToast).toHaveBeenCalledWith("已启动");
    expect(onDashboardChange).toHaveBeenCalledTimes(1);
    expect(onSummaryChange).toHaveBeenCalledTimes(1);

    const dashboardUpdater = onDashboardChange.mock.calls[0]?.[0] as (current: DashboardResponse | null) => DashboardResponse | null;
    const summaryUpdater = onSummaryChange.mock.calls[0]?.[0] as (current: IntelOverviewSummary | null) => IntelOverviewSummary | null;

    expect(dashboardUpdater(dashboard)?.runtime_status.running).toBe(true);
    expect(summaryUpdater(summary)?.running).toBe(true);
  });

  it("saves runtime plan and refreshes overview", async () => {
    const nextPlan: RuntimePlan = {
      launch_mode: "interval_now",
      start_at: null,
      interval_minutes: 30,
      timezone: "Asia/Shanghai",
      effective_mode: "full_pipeline",
      work_scope: "collect_events_alerts",
      delivery_mode: "immediate",
      delivery_schedule_time: null,
      admission_strategy: "balanced",
      batch_limit: 5,
      admission_filters: {},
    };
    mockedApi.updateRuntimePlan.mockResolvedValue({ item: nextPlan });
    const { result, onReloadOverview, onDashboardChange } = makeHook();

    await act(async () => {
      await result.current.handleSaveRuntimePlan({
        launch_mode: "interval_now",
        start_at: null,
        interval_minutes: 30,
        timezone: "Asia/Shanghai",
        work_scope: "collect_events_alerts",
        delivery_mode: "immediate",
        delivery_schedule_time: null,
        admission_strategy: "balanced",
        batch_limit: 5,
        admission_filters: {},
      });
    });

    expect(mockedApi.updateRuntimePlan).toHaveBeenCalledTimes(1);
    expect(onReloadOverview).toHaveBeenCalledWith(false);
    const dashboardUpdater = onDashboardChange.mock.calls[0]?.[0] as (current: DashboardResponse | null) => DashboardResponse | null;
    expect(dashboardUpdater(dashboard)?.runtime_plan.batch_limit).toBe(5);
  });

  it("runs a maintenance intent and refreshes all tabs", async () => {
    mockedApi.runRuntimeIntent.mockResolvedValue({ item: { ...runtimeStatus, run_intent: "normal_monitoring" } });
    const { result, onRefreshAll, onToast } = makeHook();

    await act(async () => {
      await result.current.handleRunRuntimeIntent("normal_monitoring");
    });

    expect(mockedApi.runRuntimeIntent).toHaveBeenCalledWith("normal_monitoring");
    expect(onRefreshAll).toHaveBeenCalledWith({ refreshActiveTab: true, forceBrowserRefresh: false });
    expect(onToast).toHaveBeenCalledWith("已执行一次完整补跑");
  });

  it("blocks full pipeline start when unfinished agent workflow exists", async () => {
    mockedApi.getAgentWorkflows.mockResolvedValue({
      items: [
        {
          workflow_session_id: "agentwf-1",
          status: "running",
          current_step: "article_saved",
          target_platforms: ["wechat"],
          started_at: "2026-05-13T10:00:00+08:00",
          updated_at: "2026-05-13T10:01:00+08:00",
        },
      ],
    });
    const { result, onError } = makeHook();

    await act(async () => {
      await result.current.handleStartRuntime();
    });

    expect(mockedApi.startRuntime).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith("当前存在未完成的 Agent 会话，请先完成或明确放弃后，再启动传统全流程。");
  });
});
