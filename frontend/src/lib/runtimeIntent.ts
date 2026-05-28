import type { RuntimeIntent, RuntimeRunOutcome, RuntimeLaunchMode, SchedulerStatus } from "../types";

export type RuntimeDisplayStatus =
  | "监测中"
  | "等待执行"
  | "等待启动"
  | "等待下一轮"
  | "已停止"
  | "本轮完成"
  | "本轮失败"
  | "维护任务执行中";

export type RuntimeVisualState =
  | "stopped"
  | "waiting_start_once"
  | "waiting_start_loop"
  | "running"
  | "waiting_next"
  | "one_shot_done"
  | "one_shot_failed"
  | "maintenance_running";

export const RUNTIME_INTENT_LABELS: Record<RuntimeIntent, string> = {
  normal_monitoring: "正常监测",
  collect_validation: "仅采集素材",
  event_rebuild: "重建事件",
  alert_rebuild: "重算预警",
};

const DEFAULT_STAGE_LABELS: Record<string, string> = {
  idle: "空闲",
  starting: "准备中",
  collecting: "采集中",
  clustering: "聚合中",
  scoring: "分析中",
  deep_dive: "深挖正文中",
  briefing: "生成简报中",
  wechat_sync: "上传微信中",
  wechat_verify: "回查草稿箱中",
  completed: "已完成",
  failed: "执行失败",
  abandoned: "已接管异常轮次",
};

const INTENT_STAGE_LABELS: Record<RuntimeIntent, Partial<Record<string, string>>> = {
  normal_monitoring: {
    starting: "正在启动监测",
    collecting: "正在采集来源",
    clustering: "正在聚合热点事件",
    scoring: "正在判断热度与预警",
    deep_dive: "正在深挖正文",
    briefing: "正在生成简报",
    wechat_sync: "正在上传微信草稿箱",
    wechat_verify: "正在回查微信草稿箱",
    completed: "监测完成",
    failed: "监测失败",
  },
  collect_validation: {
    starting: "正在启动素材校验",
    collecting: "正在采集素材",
    completed: "素材采集完成",
    failed: "素材采集失败",
  },
  event_rebuild: {
    starting: "正在启动事件重建",
    clustering: "正在重建热点事件",
    completed: "事件重建完成",
    failed: "事件重建失败",
  },
  alert_rebuild: {
    starting: "正在启动预警重算",
    collecting: "正在补采素材",
    clustering: "正在重建热点事件",
    scoring: "正在重算预警",
    completed: "预警重算完成",
    failed: "预警重算失败",
  },
};

export interface RuntimeProgressMeta {
  visible: boolean;
  active: boolean;
  meterVisible: boolean;
  stageLabel: string;
  tone: "success" | "warning" | "danger" | "neutral";
  showCounters: boolean;
  showEta: boolean;
}

export function isMaintenanceIntent(intent: RuntimeIntent) {
  return intent !== "normal_monitoring";
}

export function isOneShotLaunchMode(launchMode?: RuntimeLaunchMode | string | null) {
  return launchMode === "once_now" || launchMode === "once_at";
}

export function isLoopLaunchMode(launchMode?: RuntimeLaunchMode | string | null) {
  return launchMode === "interval_now" || launchMode === "interval_at";
}

export function hasRuntimeStarted(runtime: SchedulerStatus) {
  return Boolean(
    runtime.run_started_at ||
    runtime.run_finished_at ||
    runtime.last_cycle_started_at ||
    runtime.last_cycle_finished_at ||
    runtime.completed_cycles_today > 0 ||
    runtime.failed_cycles_today > 0
  );
}

export function deriveRuntimeVisualState(runtime: SchedulerStatus): RuntimeVisualState {
  const launchMode = runtime.launch_mode;
  const oneShot = isOneShotLaunchMode(launchMode);
  const loop = isLoopLaunchMode(launchMode);
  const intent = runtime.run_intent ?? "normal_monitoring";
  const hasStarted = hasRuntimeStarted(runtime);
  const outcome = runtime.last_run_outcome ?? null;

  if (runtime.run_status === "running" || runtime.control_state === "running" || isRuntimeActivelyProcessing(runtime)) {
    return isMaintenanceIntent(intent) ? "maintenance_running" : "running";
  }

  if (runtime.control_state === "armed") {
    if (loop) {
      return hasStarted ? "waiting_next" : "waiting_start_loop";
    }
    if (oneShot) {
      return "waiting_start_once";
    }
  }

  if (runtime.control_state === "waiting") {
    if (loop) {
      return hasStarted ? "waiting_next" : "waiting_start_loop";
    }
    if (oneShot) {
      if (runtime.run_status === "completed" || outcome === "completed") {
        return "one_shot_done";
      }
      if (runtime.run_status === "failed" || outcome === "failed" || outcome === "abandoned") {
        return "one_shot_failed";
      }
      return "waiting_start_once";
    }
  }

  if (oneShot) {
    if (runtime.run_status === "failed" || outcome === "failed" || outcome === "abandoned") {
      return "one_shot_failed";
    }
    if (runtime.run_status === "completed" || outcome === "completed") {
      return "one_shot_done";
    }
  }

  return "stopped";
}

export function getRuntimeStageLabel(runtime: SchedulerStatus) {
  if (runtime.stage_label?.trim()) {
    if (runtime.run_status === "failed") {
      return runtime.stage_label;
    }
    if (runtime.current_cycle !== "idle" || runtime.run_status === "completed" || runtime.run_status === "running") {
      return runtime.stage_label;
    }
  }
  const intent = runtime.run_intent ?? "normal_monitoring";
  const cycle = runtime.current_cycle || runtime.run_stage || "idle";
  const intentLabels = INTENT_STAGE_LABELS[intent] ?? {};
  if (runtime.run_status === "failed") {
    return intentLabels.failed ?? DEFAULT_STAGE_LABELS.failed;
  }
  if (runtime.run_status === "abandoned") {
    return DEFAULT_STAGE_LABELS.abandoned;
  }
  if (cycle === "completed" || runtime.run_status === "completed") {
    return intentLabels.completed ?? DEFAULT_STAGE_LABELS.completed;
  }
  return intentLabels[cycle] ?? DEFAULT_STAGE_LABELS[cycle] ?? cycle;
}

export function deriveRuntimeDisplayStatus(runtime: SchedulerStatus): RuntimeDisplayStatus {
  switch (deriveRuntimeVisualState(runtime)) {
    case "maintenance_running":
      return "维护任务执行中";
    case "running":
      return "监测中";
    case "waiting_start_once":
      return "等待执行";
    case "waiting_start_loop":
      return "等待启动";
    case "waiting_next":
      return "等待下一轮";
    case "one_shot_done":
      return "本轮完成";
    case "one_shot_failed":
      return "本轮失败";
    default:
      return "已停止";
  }
}

export function runtimeDisplayTone(status: RuntimeDisplayStatus) {
  if (status === "本轮失败") return "danger";
  if (status === "等待下一轮" || status === "等待执行" || status === "等待启动") return "warning";
  if (status === "监测中" || status === "维护任务执行中") return "success";
  return "neutral";
}

export function isRuntimeActivelyProcessing(runtime: SchedulerStatus) {
  if (runtime.run_status === "running" || runtime.control_state === "running") {
    return true;
  }
  return ["starting", "collecting", "clustering", "scoring", "deep_dive", "briefing", "wechat_sync", "wechat_verify"].includes(runtime.current_cycle);
}

export function getRuntimeProgressMeta(runtime: SchedulerStatus): RuntimeProgressMeta {
  const visualState = deriveRuntimeVisualState(runtime);
  const active = isRuntimeActivelyProcessing(runtime);
  const hasCompletedOrFailed =
    visualState === "one_shot_done" || visualState === "one_shot_failed";
  const hasProgressSignal =
    active ||
    visualState === "maintenance_running" ||
    hasCompletedOrFailed;
  const showCounters = runtime.current_cycle_progress_total > 0;
  const stageLabel = getRuntimeStageLabel(runtime);
  let tone: RuntimeProgressMeta["tone"] = "neutral";
  if (visualState === "one_shot_failed" || runtime.run_status === "failed" || runtime.current_cycle === "failed") {
    tone = "danger";
  } else if (active || visualState === "maintenance_running") {
    tone = isMaintenanceIntent(runtime.run_intent) ? "warning" : "success";
  } else if (visualState === "one_shot_done") {
    tone = "success";
  }

  return {
    visible: hasProgressSignal,
    active,
    meterVisible: (active || hasCompletedOrFailed) && runtime.current_cycle_progress_percent > 0,
    stageLabel,
    tone,
    showCounters,
    showEta: active && showCounters,
  };
}

function runtimeStageRank(runtime: SchedulerStatus) {
  if (runtime.stage_index && runtime.stage_total) {
    if (runtime.run_status === "failed") return runtime.stage_total + 1;
    if (runtime.run_status === "abandoned") return runtime.stage_total + 2;
    if (runtime.run_status === "completed") return runtime.stage_total;
    return runtime.stage_index;
  }
  const cycle = runtime.current_cycle || runtime.run_stage || "idle";
  const order: Record<string, number> = {
    idle: 0,
    starting: 1,
    collecting: 2,
    clustering: 3,
    scoring: 4,
    deep_dive: 5,
    briefing: 6,
    wechat_sync: 7,
    wechat_verify: 8,
    completed: 9,
    failed: 10,
    abandoned: 11,
  };
  return order[cycle] ?? 0;
}

function runtimeReferenceTime(runtime: SchedulerStatus) {
  const candidates = [
    runtime.run_finished_at,
    runtime.run_heartbeat_at,
    runtime.run_started_at,
    runtime.current_cycle_started_at,
    runtime.last_cycle_finished_at,
    runtime.last_cycle_started_at,
    runtime.enabled_at,
  ];
  for (const value of candidates) {
    if (!value) continue;
    const ts = Date.parse(value);
    if (!Number.isNaN(ts)) return ts;
  }
  return 0;
}

export function pickNewerRuntimeStatus(current: SchedulerStatus | null | undefined, incoming: SchedulerStatus | null | undefined) {
  if (!current) return incoming ?? current ?? null;
  if (!incoming) return current;

  const currentTime = runtimeReferenceTime(current);
  const incomingTime = runtimeReferenceTime(incoming);
  const sameRun = Boolean(current.run_id) && Boolean(incoming.run_id) && current.run_id === incoming.run_id;

  if (sameRun) {
    if (incomingTime < currentTime) {
      return current;
    }
    if (incomingTime > currentTime) {
      return incoming;
    }
    const currentRank = runtimeStageRank(current);
    const incomingRank = runtimeStageRank(incoming);
    if (incomingRank < currentRank) {
      return current;
    }
    if (incomingRank > currentRank) {
      return incoming;
    }
    if (
      incoming.run_status === current.run_status &&
      incoming.current_cycle_progress_percent < current.current_cycle_progress_percent
    ) {
      return current;
    }
    return incoming;
  }

  if (incomingTime > currentTime) {
    return incoming;
  }
  if (incomingTime < currentTime) {
    return current;
  }

  const currentActive = isRuntimeActivelyProcessing(current);
  const incomingActive = isRuntimeActivelyProcessing(incoming);
  if (incomingActive && !currentActive) {
    return incoming;
  }
  if (currentActive && !incomingActive) {
    return current;
  }

  if (incoming.current_cycle_progress_percent >= current.current_cycle_progress_percent) {
    return incoming;
  }
  return current;
}

export function explainEventsEmptyState(runtime: SchedulerStatus) {
  if (runtime.run_intent === "collect_validation") {
    return "当前运行模式仅采集素材，不生成热点事件。";
  }
  return "本轮还没有形成可聚合的热点事件。";
}

export function explainAlertsEmptyState(runtime: SchedulerStatus, eventCount: number, alertCount: number) {
  if (runtime.run_intent === "collect_validation" || runtime.run_intent === "event_rebuild") {
    return "当前运行模式不生成预警。";
  }
  if (eventCount === 0) {
    return "本轮还没有形成可用于判断趋势的热点事件。";
  }
  if (!alertCount && (runtime.completed_cycles_today <= 1 || runtime.last_run_outcome !== "completed")) {
    return "预警需要连续轮次积累趋势数据。";
  }
  return "本轮暂无上升或爆发事件。";
}

export function explainStreamEmptyState() {
  return "本轮还没有抓到新的素材。";
}

export function describeLastOutcome(outcome?: RuntimeRunOutcome | null) {
  if (outcome === "completed") return "上一轮完成";
  if (outcome === "failed") return "上一轮失败";
  if (outcome === "abandoned") return "上一轮被接管";
  if (outcome === "stopped") return "已手动停止";
  return "尚未执行";
}
