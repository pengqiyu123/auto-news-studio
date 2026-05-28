import { AlertTriangle, BellRing, CheckCircle2, CheckCircle, Clock3, Loader2, PauseCircle, PlayCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { MoreDropdown } from "../../components/MoreDropdown";
import { deriveRuntimeDisplayStatus, deriveRuntimeVisualState, describeLastOutcome, explainAlertsEmptyState, explainEventsEmptyState, getRuntimeProgressMeta, isLoopLaunchMode, runtimeDisplayTone } from "../../lib/runtimeIntent";
import { formatDateTime, formatDuration, formatRelativeTime, toDateTimeLocalValue } from "../../lib/time";
import { formatRuntimeIssueLabel } from "../../lib/runtimeUtils";
import type { AutomationMode, DeliveryMode, EntityWatchlistSummaryItem, FreshnessSnapshot, HistoryRecordStatus, IntelAlert, IntelAlertHistoryItem, IntelEvent, IntelEventHistoryItem, IntelOverviewSummary, RuntimeIntent, RuntimePlan, SchedulerStatus } from "../../types";

type OverviewTab = "alerts" | "events" | "source-health";

type GearMode = "manual_collect" | "scheduled_collect" | "full_auto";

const GEAR_MODE_LABELS: Record<GearMode, string> = {
  manual_collect: "手动爬取",
  scheduled_collect: "定时爬取",
  full_auto: "全自动运营",
};

const DELIVERY_MODE_LABELS: Record<DeliveryMode, string> = {
  collect_only: "不生成简报",
  local_digest: "仅生成本地简报",
  immediate: "立即上传微信",
  scheduled_batch: "定时批量上传",
};

function gearModeFromPlan(plan: RuntimePlan): GearMode {
  if (plan.effective_mode === "manual") return "manual_collect";
  if (plan.delivery_mode === "collect_only") return "scheduled_collect";
  return "full_auto";
}

function applyGearMode(gear: GearMode, currentPlan: Omit<RuntimePlan, "effective_mode">): { mode: AutomationMode; plan: Omit<RuntimePlan, "effective_mode"> } {
  const plan = { ...currentPlan };
  switch (gear) {
    case "manual_collect":
      return { mode: "manual", plan: { ...plan, delivery_mode: "collect_only" } };
    case "scheduled_collect":
      return { mode: "automated", plan: { ...plan, delivery_mode: "collect_only" } };
    case "full_auto":
      return { mode: "automated", plan: { ...plan, delivery_mode: plan.delivery_mode === "collect_only" ? "local_digest" : plan.delivery_mode } };
  }
}

interface OverviewPageProps {
  summary: IntelOverviewSummary;
  runtime: SchedulerStatus;
  freshness: FreshnessSnapshot;
  entityWatchlistSummary: EntityWatchlistSummaryItem[];
  runtimePlan: RuntimePlan;
  savingRuntimePlan: boolean;
  busyRuntimeAction?: "start" | "stop" | null;
  busyMaintenanceIntent?: RuntimeIntent | null;
  refreshing?: boolean;
  onSaveRuntimePlan: (payload: Omit<RuntimePlan, "effective_mode">) => Promise<void>;
  onSetAutomationMode: (mode: AutomationMode) => Promise<void>;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
  onRunIntent: (intent: RuntimeIntent) => Promise<void>;
  onRefresh: () => Promise<void>;
  onNavigate: (tab: OverviewTab) => void;
  onOpenEntity: (entityId: string) => void;
  onWatchEvent: (eventId: string) => Promise<void>;
  onIgnoreEvent: (eventId: string) => Promise<void>;
}

function buildPlanDraft(runtimePlan: RuntimePlan): Omit<RuntimePlan, "effective_mode"> {
  return {
    launch_mode: runtimePlan.launch_mode,
    start_at: runtimePlan.launch_mode.endsWith("_at") ? (runtimePlan.start_at ?? null) : null,
    interval_minutes: runtimePlan.launch_mode.includes("interval") ? (runtimePlan.interval_minutes ?? 30) : null,
    timezone: runtimePlan.timezone,
    work_scope: "collect_events_alerts",
    delivery_mode: runtimePlan.delivery_mode,
    delivery_schedule_time: runtimePlan.delivery_schedule_time ?? null,
    admission_strategy: runtimePlan.admission_strategy,
    batch_limit: runtimePlan.batch_limit,
    admission_filters: { ...runtimePlan.admission_filters },
  };
}

function alertTone(level: IntelAlert["level"]) {
  if (level === "breakout") return "danger";
  if (level === "rising") return "warning";
  if (level === "cooling") return "neutral";
  return "success";
}

function eventTone(event: IntelEvent) {
  if (event.alert_state === "breakout") return "danger";
  if (event.alert_state === "rising") return "warning";
  if (event.alert_state === "watch") return "success";
  return "neutral";
}

function historyStatusLabel(status: HistoryRecordStatus) {
  if (status === "active") return "仍活跃";
  if (status === "source_uncertain") return "待确认";
  return "已回落";
}

function historyStatusTone(status: HistoryRecordStatus) {
  if (status === "active") return "success";
  if (status === "source_uncertain") return "warning";
  return "neutral";
}

function historyLevelTone(level: IntelAlertHistoryItem["highest_level"] | IntelEventHistoryItem["latest_alert_state"]) {
  if (level === "breakout") return "danger";
  if (level === "rising") return "warning";
  if (level === "watch") return "success";
  return "neutral";
}

function formatCountdown(target?: string | null, fallback = "未安排", nowMs = Date.now()) {
  if (!target) return fallback;
  const date = new Date(target);
  if (Number.isNaN(date.getTime())) return fallback;
  const diffMs = date.getTime() - nowMs;
  if (diffMs <= 0) return "即将开始";
  const totalSeconds = Math.round(diffMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const restMinutes = minutes % 60;
    return `还有 ${hours}小时${restMinutes}分钟`;
  }
  if (minutes > 0) {
    return `还有 ${minutes}分${seconds}秒`;
  }
  return `还有 ${seconds}秒`;
}

function CountdownTimer({ target, fallback = "未安排" }: { target?: string | null; fallback?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return formatCountdown(target, fallback, now);
}

export function OverviewPage({
  summary,
  runtime,
  freshness,
  entityWatchlistSummary,
  runtimePlan,
  savingRuntimePlan,
  busyRuntimeAction,
  busyMaintenanceIntent,
  refreshing,
  onSaveRuntimePlan,
  onSetAutomationMode,
  onStart,
  onStop,
  onRunIntent,
  onRefresh,
  onNavigate,
  onOpenEntity,
  onWatchEvent,
  onIgnoreEvent,
}: OverviewPageProps) {
  const [planDraft, setPlanDraft] = useState<Omit<RuntimePlan, "effective_mode">>(buildPlanDraft(runtimePlan));
  const [gearMode, setGearMode] = useState<GearMode>(gearModeFromPlan(runtimePlan));
  const [cycleSummaryCollapsed, setCycleSummaryCollapsed] = useState(true);

  const cycleStartRef = useRef<number | null>(null);
  const prevPercentRef = useRef<number>(0);

  useEffect(() => {
    setPlanDraft(buildPlanDraft(runtimePlan));
    setGearMode(gearModeFromPlan(runtimePlan));
  }, [runtimePlan]);

  // Track when the cycle starts (first non-zero percent)
  useEffect(() => {
    const pct = runtime.current_cycle_progress_percent;
    if (pct > 0 && cycleStartRef.current === null) {
      cycleStartRef.current = Date.now();
    }
    // Reset when cycle ends
    if (pct === 0 && prevPercentRef.current > 0) {
      cycleStartRef.current = null;
    }
    prevPercentRef.current = pct;
  }, [runtime.current_cycle_progress_percent]);

  const estimatedRemaining = useMemo((): string | null => {
    const pct = runtime.current_cycle_progress_percent;
    const total = runtime.current_cycle_progress_total;
    if (
      cycleStartRef.current === null ||
      pct <= 0 ||
      pct >= 100 ||
      total <= 0
    ) return null;
    const elapsedMs = Date.now() - cycleStartRef.current;
    const estimatedTotalMs = (elapsedMs / pct) * 100;
    const remainingMs = estimatedTotalMs - elapsedMs;
    if (remainingMs <= 0) return null;
    const remainingSec = Math.round(remainingMs / 1000);
    if (remainingSec < 60) return `约 ${remainingSec}s`;
    return `约 ${Math.round(remainingSec / 60)}m`;
  }, [runtime.current_cycle_progress_percent, runtime.current_cycle_progress_total, runtime.current_cycle]);

  const displayStatus = useMemo(() => deriveRuntimeDisplayStatus(runtime), [runtime]);
  const visualState = useMemo(() => deriveRuntimeVisualState(runtime), [runtime]);
  const progressMeta = useMemo(() => getRuntimeProgressMeta(runtime), [runtime]);
  const cycleSummary = runtime.last_cycle_summary ?? null;
  const cycleIssuePreview = useMemo(() => {
    if (!cycleSummary?.issues?.length) {
      return runtime.last_cycle_issue_summary || "本轮无异常";
    }
    return cycleSummary.issues
      .slice(0, 2)
      .map((item) => formatRuntimeIssueLabel(item.source_name, item.message))
      .join("；");
  }, [cycleSummary, runtime.last_cycle_issue_summary]);
  const isLoopMode = isLoopLaunchMode(planDraft.launch_mode);
  const isManualMode = gearMode === "manual_collect";
  const isFullAuto = gearMode === "full_auto";
  const nextRunTime = summary.next_run_at ?? runtime.next_collect_at ?? null;
  const lastRunResultLabel = useMemo(() => {
    if (visualState === "one_shot_done") return "上一轮完成";
    if (visualState === "one_shot_failed") return "上一轮失败";
    return describeLastOutcome(runtime.last_run_outcome);
  }, [runtime.last_run_outcome, visualState]);
  const isRunning = visualState === "running" || visualState === "maintenance_running" || visualState === "waiting_start_once" || visualState === "waiting_start_loop" || visualState === "waiting_next";
  const isStopped = visualState === "stopped" || visualState === "one_shot_done" || visualState === "one_shot_failed";
  const footerPhaseLabel = useMemo(() => {
    if (progressMeta.active) {
      return progressMeta.stageLabel || runtime.current_cycle || "执行中";
    }
    return displayStatus;
  }, [displayStatus, progressMeta.active, progressMeta.stageLabel, runtime.current_cycle]);

  async function handleGearChange(newGear: GearMode) {
    setGearMode(newGear);
    const { mode, plan } = applyGearMode(newGear, planDraft);
    setPlanDraft(plan);
    await onSetAutomationMode(mode);
    await onSaveRuntimePlan(plan);
  }

  async function handleStart() {
    if (isManualMode) {
      await onRunIntent("normal_monitoring");
    } else {
      await onSaveRuntimePlan(planDraft);
      await onStart();
    }
  }

  return (
    <>
      {/* 主控条 - 简化版：档位 + 内联频率/交付 + 启停 + 更多 */}
      <section className="panel intel-hero-panel">
        <div className="intel-plan-compact-bar">
          <div className="intel-plan-compact-status">
            <span className={`status-badge status-${runtimeDisplayTone(displayStatus)}`}>
              {displayStatus}
            </span>
            <span className="intel-plan-inline-control">
              <select value={gearMode} onChange={(e) => void handleGearChange(e.target.value as GearMode)}>
                <option value="manual_collect">{GEAR_MODE_LABELS.manual_collect}</option>
                <option value="scheduled_collect">{GEAR_MODE_LABELS.scheduled_collect}</option>
                <option value="full_auto">{GEAR_MODE_LABELS.full_auto}</option>
              </select>
            </span>
            <span className="subtle">结果：{lastRunResultLabel}</span>
            {!isManualMode ? (
              <span className="intel-plan-inline-control">
                <span className="subtle">频率</span>
                <select
                  value={String(planDraft.interval_minutes ?? 30)}
                  onChange={(e) => setPlanDraft((c) => ({ ...c, interval_minutes: Number(e.target.value) }))}
                >
                  <option value="10">10 分钟</option>
                  <option value="15">15 分钟</option>
                  <option value="20">20 分钟</option>
                  <option value="30">30 分钟</option>
                  <option value="60">60 分钟</option>
                </select>
              </span>
            ) : null}
            {isFullAuto ? (
              <span className="intel-plan-inline-control">
                <span className="subtle">交付</span>
                <select
                  value={planDraft.delivery_mode}
                  onChange={(e) => setPlanDraft((c) => ({
                    ...c,
                    delivery_mode: e.target.value as DeliveryMode,
                    delivery_schedule_time: e.target.value === "scheduled_batch" ? (c.delivery_schedule_time ?? "09:00") : null,
                  }))}
                >
                  <option value="local_digest">仅生成本地简报</option>
                  <option value="immediate">立即上传微信</option>
                  <option value="scheduled_batch">定时批量上传</option>
                </select>
              </span>
            ) : null}
            {isFullAuto && planDraft.delivery_mode === "scheduled_batch" ? (
              <span className="intel-plan-inline-control">
                <input
                  type="time"
                  value={planDraft.delivery_schedule_time ?? "09:00"}
                  onChange={(e) => setPlanDraft((c) => ({ ...c, delivery_schedule_time: e.target.value || "09:00" }))}
                />
              </span>
            ) : null}
          </div>
          <div className="intel-hero-actions">
            {isStopped ? (
              <button
                type="button"
                className="primary-button"
                disabled={busyRuntimeAction === "start" || busyMaintenanceIntent !== null}
                onClick={() => void handleStart()}
              >
                <PlayCircle size={14} />
                {isManualMode
                  ? (busyMaintenanceIntent === "normal_monitoring" ? "采集中..." : "采集信息")
                  : (busyRuntimeAction === "start" ? "启动中..." : "启动")}
              </button>
            ) : null}
            {isRunning ? (
              <button
                type="button"
                className="ghost-button"
                disabled={busyRuntimeAction === "stop"}
                onClick={() => void onStop()}
              >
                <PauseCircle size={14} />
                {busyRuntimeAction === "stop" ? "停止中..." : "停止"}
              </button>
            ) : null}
            <MoreDropdown
              onRefresh={() => void onRefresh()}
              onRunIntent={(intent) => void onRunIntent(intent)}
              refreshing={refreshing}
              busyIntent={busyMaintenanceIntent}
              disabled={isRunning}
            />
          </div>
        </div>

        {/* 运行阶段指示器 — 活跃 / 完成 / 失败 */}
        {progressMeta.visible ? (
          <div className="intel-cycle-progress">
            {progressMeta.tone === "danger" ? (
              <AlertTriangle size={13} className="text-red-600" />
            ) : visualState === "one_shot_done" ? (
              <CheckCircle2 size={13} className="text-green-600" />
            ) : (
              <Loader2 size={13} className="spin" />
            )}
            <span className={`intel-cycle-stage intel-cycle-stage-${progressMeta.tone}${visualState === "one_shot_done" ? " intel-cycle-stage-done" : ""}`}>
              {progressMeta.stageLabel}
            </span>
            <span className="intel-cycle-percent">{runtime.current_cycle_progress_percent}%</span>
            {progressMeta.showEta && estimatedRemaining && runtime.run_status !== "failed" ? (
              <span className="subtle">剩余 {estimatedRemaining}</span>
            ) : null}
            {progressMeta.showCounters ? (
              <span className="subtle">
                {runtime.current_cycle_progress_done}/{runtime.current_cycle_progress_total}
              </span>
            ) : null}
            {runtime.current_cycle_started_at ? (
              <span className="subtle">{formatRelativeTime(runtime.current_cycle_started_at, "")}</span>
            ) : null}
          </div>
        ) : null}

        {progressMeta.meterVisible ? (
          <div className="intel-cycle-meter">
            <div
              className={`intel-cycle-meter-fill intel-cycle-meter-fill-${progressMeta.tone}`}
              style={{ width: `${Math.max(0, Math.min(runtime.current_cycle_progress_percent, 100))}%` }}
            />
          </div>
        ) : progressMeta.visible ? (
          <div className="intel-cycle-meter">
            <div
              className={`intel-cycle-meter-fill intel-cycle-meter-fill-${progressMeta.tone}`}
              style={{ width: "100%" }}
            />
          </div>
        ) : null}

        {(progressMeta.visible || runtime.current_cycle_progress_label) && (runtime.current_cycle_progress_label || runtime.run_error || runtime.last_error) ? (
          <p className="intel-cycle-label">{runtime.current_cycle_progress_label || runtime.run_error || runtime.last_error}</p>
        ) : null}

        {runtime.recovered_run_id ? (
          <p className="intel-cycle-label">已接管异常轮次 {runtime.recovered_run_id}，当前状态以最新轮次为准。</p>
        ) : null}

        {isRunning && (visualState === "waiting_start_once" || visualState === "waiting_start_loop" || visualState === "waiting_next") ? (
          <div className="intel-cycle-progress">
            <Clock3 size={13} />
            <span className="intel-cycle-stage intel-cycle-stage-warning">
              {visualState === "waiting_next" ? "下一次运行" : "计划开始时间"}
            </span>
            <span>{formatDateTime(nextRunTime, { fallback: "未设定" })}</span>
            <span className="subtle">
              {visualState === "waiting_next" ? "距离下一轮" : "距离开始"}：<CountdownTimer target={nextRunTime} />
            </span>
            {isLoopMode ? <span className="subtle">今日已运行 {runtime.completed_cycles_today} 次</span> : null}
            {isLoopMode ? <span className="subtle">最近一轮耗时 {formatDuration(runtime.last_cycle_duration_seconds, "暂无")}</span> : null}
          </div>
        ) : visualState === "stopped" && (runtime.last_cycle_started_at || runtime.completed_cycles_today > 0 || runtime.failed_cycles_today > 0) ? (
          <div className="intel-cycle-progress">
            <CheckCircle size={13} className="text-slate-400" />
            <span className="intel-cycle-stage intel-cycle-stage-neutral">已停止</span>
            <span className="subtle">上轮 {lastRunResultLabel}</span>
            {runtime.last_cycle_started_at ? (
              <span className="subtle">{formatRelativeTime(runtime.last_cycle_started_at, "")} 开始</span>
            ) : null}
            {runtime.last_cycle_duration_seconds ? (
              <span className="subtle">耗时 {formatDuration(runtime.last_cycle_duration_seconds, "")}</span>
            ) : null}
            <span className="subtle">今日 {runtime.completed_cycles_today} 成功 / {runtime.failed_cycles_today} 失败</span>
          </div>
        ) : null}
      </section>

      {/* 爆发预警 */}
      <section className="intel-overview-grid">
        <article className="panel intel-priority-panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">爆发预警</p>
              <h2>爆发预警</h2>
            </div>
            <button type="button" className="ghost-button compact" onClick={() => onNavigate("alerts")}>
              预警台
            </button>
          </div>

          <div className="intel-alert-stack">
            {summary.top_alerts.length ? summary.top_alerts.slice(0, 3).map((alert) => (
              <div key={alert.id} className={`intel-alert-card severity-${alert.level}`}>
                <div className="intel-card-topline">
                  <span className={`status-badge status-${alertTone(alert.level)}`}>{alert.level}</span>
                  <span>{formatRelativeTime(alert.triggered_at, "刚刚")}</span>
                </div>
                <strong>{alert.title}</strong>
                <p>{alert.reason}</p>
                <div className="intel-score-row">
                  <span>速度 {alert.velocity_score}</span>
                  <span>覆盖 {alert.coverage_score}</span>
                  <span>新鲜 {alert.freshness_score}</span>
                </div>
                <div className="intel-inline-actions">
                  <button type="button" className="ghost-button compact" onClick={() => onNavigate("events")}>
                    查看事件
                  </button>
                  <a href={alert.representative_link} target="_blank" rel="noreferrer">查看原文</a>
                </div>
              </div>
            )) : (
              <p className="empty-state">
                {summary.recent_alert_count_24h
                  ? `当前暂无活跃爆发，以下为 24 小时内已发现的 ${summary.recent_alert_count_24h} 条预警。`
                  : explainAlertsEmptyState(runtime, summary.event_count, summary.alert_count)}
              </p>
            )}
          </div>

          <div className="intel-subsection-head">
            <div>
              <p className="eyebrow">24h 内已发现预警</p>
              <h3>今日已发现</h3>
            </div>
            <span className="subtle">{summary.recent_alert_count_24h} 条</span>
          </div>
          <div className="intel-alert-stack">
            {summary.recent_alerts_24h.length ? summary.recent_alerts_24h.slice(0, 3).map((alert) => (
              <div key={alert.history_id} className={`intel-alert-card severity-${alert.highest_level}`}>
                <div className="intel-card-topline">
                  <span className={`status-badge status-${historyStatusTone(alert.status)}`}>{historyStatusLabel(alert.status)}</span>
                  <span className={`status-badge status-${historyLevelTone(alert.highest_level)}`}>最高 {alert.highest_level}</span>
                </div>
                <strong>{alert.title}</strong>
                <p>{alert.reason}</p>
                {alert.status === "source_uncertain" ? <p className="intel-history-note">本轮来源异常，未继续确认该信号。</p> : null}
                <div className="intel-score-row">
                  <span>速度 {alert.velocity_score}</span>
                  <span>覆盖 {alert.coverage_score}</span>
                  <span>最近 {formatRelativeTime(alert.last_triggered_at, "刚刚")}</span>
                </div>
                <div className="intel-inline-actions">
                  <button type="button" className="ghost-button compact" onClick={() => onNavigate("events")}>
                    查看事件
                  </button>
                  <a href={alert.representative_link} target="_blank" rel="noreferrer">查看原文</a>
                </div>
              </div>
            )) : <p className="empty-state">24 小时内暂无已发现预警。</p>}
          </div>
        </article>

        {/* 热点事件 */}
        <article className="panel intel-priority-panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">热点事件</p>
              <h2>热点事件</h2>
            </div>
            <button type="button" className="ghost-button compact" onClick={() => onNavigate("events")}>
              热点簇
            </button>
          </div>

          <div className="intel-event-stack">
            {summary.top_events.length ? summary.top_events.slice(0, 5).map((event) => (
              <div key={event.id} className={`intel-event-card state-${event.alert_state}`}>
                <div className="intel-card-topline">
                  <span className={`status-badge status-${eventTone(event)}`}>{event.alert_state}</span>
                  <span>{event.platform_count} 平台 / {event.source_count} 来源</span>
                </div>
                <strong>{event.title}</strong>
                <p>{event.summary}</p>
                <div className="intel-score-row">
                  <span>总分 {event.composite_score}</span>
                  <span>30m +{event.velocity_details.delta_mentions_30m ?? 0}</span>
                  <span>{formatRelativeTime(event.latest_collected_at, "刚抓到")}</span>
                </div>
                <div className="intel-inline-actions">
                  <a href={event.representative_link} target="_blank" rel="noreferrer">查看原文</a>
                  <button type="button" className="ghost-button compact" disabled={event.watchlisted} onClick={() => void onWatchEvent(event.id)}>
                    {event.watchlisted ? "已观察" : "观察"}
                  </button>
                  <button type="button" className="ghost-button compact" onClick={() => void onIgnoreEvent(event.id)}>
                    忽略
                  </button>
                </div>
              </div>
            )) : (
              <p className="empty-state">
                {explainEventsEmptyState(runtime)}
              </p>
            )}
          </div>
        </article>
      </section>

      {/* 系统摘要 */}
      <section className="intel-summary-grid">
        <article className="panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">系统状态</p>
              <h2>系统状态</h2>
            </div>
          </div>
          <div className="intel-stat-grid">
            <div className="intel-stat-card">
              <span>预警</span>
              <strong>{summary.alert_count}</strong>
              <p>{summary.breakout_count} 爆发 / {summary.rising_count} 上升</p>
            </div>
            <div className="intel-stat-card">
              <span>本轮动态</span>
              <strong>{summary.new_events_count + summary.growing_events_count}</strong>
              <p>新事件 {summary.new_events_count} / 升温 {summary.growing_events_count}</p>
            </div>
            <div className="intel-stat-card">
              <span>来源</span>
              <strong>{summary.healthy_sources}/{summary.total_sources}</strong>
              <p>警告 {summary.warning_sources} / 异常 {summary.error_sources}</p>
            </div>
            <div className="intel-stat-card">
              <span>数据新鲜度</span>
              <strong>
                {freshness?.latest_collected_at
                  ? formatRelativeTime(freshness.latest_collected_at, "暂无")
                  : "未采集"}
              </strong>
              <p>
                {freshness?.stale_source_count > 0
                  ? `${freshness.stale_source_count} 个来源过时`
                  : "全部来源正常"}
              </p>
              <p className="subtle">
                1h {freshness?.items_1h ?? 0} / 6h {freshness?.items_6h ?? 0} / 24h {freshness?.items_24h ?? 0}
              </p>
            </div>
          </div>
        </article>

        <article className="panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">执行摘要</p>
              <h2>执行摘要</h2>
            </div>
            <button type="button" className="ghost-button compact" onClick={() => onNavigate("source-health")}>
              来源健康
            </button>
          </div>
          <div className="intel-runtime-list">
            <div>
              <Clock3 size={16} />
              <div>
                <strong>上轮开始</strong>
                <p>{formatDateTime(cycleSummary?.started_at ?? runtime.last_cycle_started_at, { fallback: "尚未执行" })}</p>
              </div>
            </div>
            <div>
              <BellRing size={16} />
              <div>
                <strong>上轮耗时</strong>
                <p>{formatDuration((cycleSummary?.duration_ms ?? 0) / 1000 || runtime.last_cycle_duration_seconds, "暂无")}</p>
              </div>
            </div>
            <div>
              <AlertTriangle size={16} />
              <div>
                <strong>本轮异常</strong>
                <p>{cycleIssuePreview}</p>
              </div>
            </div>
          </div>
            {cycleSummary ? (
            <div className="intel-runtime-summary" style={cycleSummaryCollapsed ? { maxHeight: "3.5em", overflow: "hidden" } : undefined}>
              <button type="button" className="ghost-button compact" style={{ float: "right", fontSize: "0.75rem" }} onClick={() => setCycleSummaryCollapsed(c => !c)}>
                {cycleSummaryCollapsed ? "展开详情" : "收起"}
              </button>
              <div className="intel-score-row">
                <span>成功来源 {cycleSummary.success_source_count}</span>
                <span>失败来源 {cycleSummary.failed_source_count}</span>
                <span>新增素材 {cycleSummary.new_items_count}</span>
                <span>新事件 {cycleSummary.new_events_count}</span>
                <span>升温事件 {cycleSummary.growing_events_count}</span>
                <span>入选 {cycleSummary.selected_event_count}</span>
                <span>深挖 {cycleSummary.deep_dive_count}</span>
                <span>简报 {cycleSummary.brief_count}</span>
                <span>上传 {cycleSummary.wechat_sync_count}</span>
                <span>回查 {cycleSummary.wechat_verify_count}</span>
              </div>
              {runtime.blocked_reason || cycleSummary.blocked_reason ? (
                <div className="intel-runtime-section">
                  <strong>当前阻断</strong>
                  <p>{runtime.blocked_reason || cycleSummary.blocked_reason}</p>
                </div>
              ) : null}
              {cycleSummary.recent_selected_titles.length ? (
                <div className="intel-runtime-section">
                  <strong>最近入选事件</strong>
                  <div className="intel-runtime-chip-row">
                    {cycleSummary.recent_selected_titles.map((item) => (
                      <span key={item} className="subtle-chip">{item}</span>
                    ))}
                  </div>
                </div>
              ) : null}
              {cycleSummary.recent_brief_titles.length ? (
                <div className="intel-runtime-section">
                  <strong>最近生成简报</strong>
                  <div className="intel-runtime-chip-row">
                    {cycleSummary.recent_brief_titles.map((item) => (
                      <span key={item} className="subtle-chip">{item}</span>
                    ))}
                  </div>
                </div>
              ) : null}
              {cycleSummary.recent_synced_titles.length ? (
                <div className="intel-runtime-section">
                  <strong>最近上传草稿箱</strong>
                  <div className="intel-runtime-chip-row">
                    {cycleSummary.recent_synced_titles.map((item) => (
                      <span key={item} className="subtle-chip">{item}</span>
                    ))}
                  </div>
                </div>
              ) : null}
              {cycleSummary.slow_sources.length ? (
                <div className="intel-runtime-section">
                  <strong>最慢来源 Top 3</strong>
                  <div className="intel-runtime-chip-row">
                    {cycleSummary.slow_sources.map((item) => (
                      <span key={`${item.source_key}-${item.duration_ms}`} className="subtle-chip">
                        {item.source_name} {Math.round(item.duration_ms / 1000)}s
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              {cycleSummary.issues.length ? (
                <div className="intel-runtime-section">
                  <strong>整轮异常</strong>
                    <ul className="intel-runtime-issues">
                      {cycleSummary.issues.slice(0, 4).map((item, index) => (
                        <li key={`${item.source_key ?? "runtime"}-${index}`}>
                          {formatRuntimeIssueLabel(item.source_name, item.message)}
                        </li>
                      ))}
                    </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </article>

        <article className="panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">重点监控实体</p>
              <h2>首页重点监控摘要</h2>
            </div>
            <button type="button" className="ghost-button compact" onClick={() => onNavigate("events")}>
              热点簇
            </button>
          </div>
          <div className="entity-watchlist-list">
            {entityWatchlistSummary.length ? entityWatchlistSummary.slice(0, 5).map((item) => (
              <article key={item.entity_id} className="entity-watchlist-card">
                <div className="entity-watchlist-head">
                  <div>
                    <strong>{item.entity_name}</strong>
                    <p>{item.entity_type}</p>
                  </div>
                  <button type="button" className="ghost-button compact" onClick={() => onOpenEntity(item.entity_id)}>
                    查看
                  </button>
                </div>
                <div className="entity-watchlist-stats">
                  <span>事件 {item.event_count}</span>
                  <span>预警 {item.alert_count}</span>
                  <span>上升 {item.rising_count}</span>
                  <span>爆发 {item.breakout_count}</span>
                </div>
                <p className="subtle">最近出现 {formatDateTime(item.last_seen_at, { fallback: "暂无" })}</p>
              </article>
            )) : <p className="empty-state">还没有重点监控实体。</p>}
          </div>
        </article>
      </section>
    </>
  );
}
