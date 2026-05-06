import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAdaptivePolling } from "./useAdaptivePolling";
import type { SchedulerStatus } from "../types";

const baseRuntime: SchedulerStatus = {
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

describe("useAdaptivePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("uses active interval when runtime is actively processing", () => {
    const task = vi.fn();
    renderHook(() =>
      useAdaptivePolling(
        "overview",
        { ...baseRuntime, running: true, control_state: "running", current_cycle: "collecting" },
        task,
        true,
      ),
    );

    vi.advanceTimersByTime(1999);
    expect(task).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(task).toHaveBeenCalledTimes(1);
  });

  it("does not recreate cadence when callback identity changes", () => {
    const firstTask = vi.fn();
    const secondTask = vi.fn();
    const clearSpy = vi.spyOn(window, "clearInterval");

    const { rerender } = renderHook(
      ({ task }) =>
        useAdaptivePolling(
          "logs",
          { ...baseRuntime, running: true, control_state: "armed", current_cycle: "idle" },
          task,
          true,
          { active: 2000, running: 6000, idle: 60000 },
        ),
      { initialProps: { task: firstTask } },
    );

    rerender({ task: secondTask });

    vi.advanceTimersByTime(6000);
    expect(firstTask).not.toHaveBeenCalled();
    expect(secondTask).toHaveBeenCalledTimes(1);
    expect(clearSpy).not.toHaveBeenCalled();
  });
});
