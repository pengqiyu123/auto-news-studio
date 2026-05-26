import { useEffect, useRef } from "react";

import { isRuntimeActivelyProcessing } from "../../lib/runtimeIntent";
import type { SchedulerStatus } from "../../types";

type PollTask = () => void | Promise<void>;
type PollIntervals = {
  active: number;
  running: number;
  idle: number;
};

const DEFAULT_INTERVALS: PollIntervals = {
  active: 2000,
  running: 6000,
  idle: 60000,
};

export function useAdaptivePolling(
  activeTab: string,
  runtime: SchedulerStatus | null | undefined,
  task: PollTask,
  isEnabled: boolean,
  intervals: PollIntervals = DEFAULT_INTERVALS,
) {
  const isRunning = Boolean(runtime?.running);
  const isActiveCycle = runtime ? isRuntimeActivelyProcessing(runtime) : false;
  const taskRef = useRef<PollTask>(task);
  const inFlightRef = useRef(false);

  useEffect(() => {
    taskRef.current = task;
  }, [task]);

  useEffect(() => {
    if (!isEnabled) {
      return;
    }
    const intervalMs = isActiveCycle ? intervals.active : isRunning ? intervals.running : intervals.idle;
    const timer = window.setInterval(async () => {
      // Skip if previous poll is still in flight
      if (inFlightRef.current) {
        return;
      }
      inFlightRef.current = true;
      try {
        await taskRef.current();
      } finally {
        inFlightRef.current = false;
      }
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [activeTab, intervals.active, intervals.idle, intervals.running, isEnabled, isRunning, isActiveCycle]);
}
