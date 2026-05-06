import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LogsPanel } from "./LogsPanel";
import type { LogItem, SchedulerStatus } from "../types";

const runtime: SchedulerStatus = {
  running: false,
  control_state: "stopped",
  launch_mode: "interval_now",
  current_mode: "radar_only",
  work_scope: "collect_events_alerts",
  delivery_mode: "immediate",
  admission_strategy: "balanced",
  batch_limit: 3,
  current_cycle: "idle",
  current_cycle_progress_percent: 0,
  current_cycle_progress_done: 0,
  current_cycle_progress_total: 0,
  stage_key: "idle",
  stage_label: "空闲",
  stage_index: 0,
  stage_total: 0,
  uptime_seconds: 0,
  completed_cycles_today: 0,
  failed_cycles_today: 0,
  last_cycle_issue_count: 0,
  run_status: "idle",
  run_stage: "idle",
  run_stale: false,
  run_intent: "normal_monitoring",
};

const logs: LogItem[] = [
  {
    id: "log-1",
    level: "warning",
    message: "source warning",
    created_at: "2026-05-05T12:00:00+00:00",
    category: "collection",
    stream: "business_event",
    actor: "system",
    detail: "detail",
  },
];

describe("LogsPanel", () => {
  it("wires level filter, search, and pagination callbacks", () => {
    const onLevelFilterChange = vi.fn();
    const onSearchChange = vi.fn();
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();

    render(
      <LogsPanel
        logs={logs}
        page={1}
        pageSize={20}
        total={30}
        levelFilter="all"
        searchQuery=""
        runtime={runtime}
        onLevelFilterChange={onLevelFilterChange}
        onSearchChange={onSearchChange}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />,
    );

    fireEvent.click(screen.getByText("warning"));
    expect(onLevelFilterChange).toHaveBeenCalledWith("warning");

    fireEvent.change(screen.getByPlaceholderText("搜索日志内容"), { target: { value: "source" } });
    expect(onSearchChange).toHaveBeenCalledWith("source");

    fireEvent.click(screen.getByLabelText("下一页"));
    expect(onPageChange).toHaveBeenCalledWith(2);

    fireEvent.change(screen.getByDisplayValue("20"), { target: { value: "50" } });
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
  });
});
