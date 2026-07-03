import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { FreshnessSnapshot, IntelOverviewSummary, RuntimePlan, SchedulerStatus, TrendSignalInfo } from "../../types";
import { OverviewPage } from "./page";

function buildRuntime(): SchedulerStatus {
  return {
    running: false,
    control_state: "stopped",
    launch_mode: "interval_now",
    current_mode: "manual",
    work_scope: "collect_events_alerts",
    last_collect_at: null,
    last_event_sync_at: null,
    last_brief_at: null,
    next_collect_at: null,
    delivery_mode: "collect_only",
    delivery_schedule_time: null,
    admission_strategy: "top_scored",
    batch_limit: 5,
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
}

function buildPlan(): RuntimePlan {
  return {
    launch_mode: "interval_now",
    start_at: null,
    interval_minutes: 30,
    timezone: "Asia/Shanghai",
    effective_mode: "manual",
    work_scope: "collect_events_alerts",
    delivery_mode: "collect_only",
    delivery_schedule_time: null,
    admission_strategy: "top_scored",
    batch_limit: 5,
    admission_filters: {
      require_watchlisted: false,
      require_entity_match: false,
      min_source_count: 0,
      min_fulltext_count: 1,
      breakout_only: false,
      exclude_existing_brief: true,
      exclude_synced_brief: true,
    },
  };
}

function buildSummary(): IntelOverviewSummary {
  return {
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
}

const freshness: FreshnessSnapshot = {
  latest_published_at: null,
  latest_collected_at: null,
  items_1h: 0,
  items_6h: 0,
  items_24h: 0,
  avg_collection_lag_minutes: null,
  stale_source_count: 0,
  has_staleness_alert: false,
  last_successful_sync_at: null,
};

const trends: TrendSignalInfo[] = [
  {
    entity_id: "apple",
    entity_name: "Apple",
    trend: "hot",
    trend_label: "近7天持续上升",
    sma_7d: 12,
    sma_14d: 8,
    signals: [],
  },
];

describe("OverviewPage", () => {
  it("shows trend indicators next to watchlist entities", () => {
    render(
      <OverviewPage
        summary={buildSummary()}
        runtime={buildRuntime()}
        freshness={freshness}
        entityWatchlistSummary={[
          {
            entity_id: "apple",
            entity_name: "Apple",
            entity_type: "COMPANY",
            watchlisted: true,
            event_count: 3,
            alert_count: 1,
            rising_count: 1,
            breakout_count: 0,
            last_seen_at: "2026-05-28T09:00:00+08:00",
          },
        ]}
        trends={trends}
        runtimePlan={buildPlan()}
        savingRuntimePlan={false}
        onSaveRuntimePlan={vi.fn().mockResolvedValue(undefined)}
        onSetAutomationMode={vi.fn().mockResolvedValue(undefined)}
        onStart={vi.fn().mockResolvedValue(undefined)}
        onStop={vi.fn().mockResolvedValue(undefined)}
        onRunIntent={vi.fn().mockResolvedValue(undefined)}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onOpenEntity={vi.fn()}
        onWatchEvent={vi.fn().mockResolvedValue(undefined)}
        onIgnoreEvent={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByLabelText("Apple 趋势 升温")).toBeInTheDocument();
  });
});
