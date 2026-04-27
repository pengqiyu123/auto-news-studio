import { AlertTriangle, BellRing, CheckCircle2, ChevronDown, ChevronUp, Clock3, Loader2, PauseCircle, PlayCircle, RadioTower, RefreshCcw, Save } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { formatDateTime, formatDuration, formatRelativeTime, toDateTimeLocalValue } from "../lib/time";
import type { IntelAlert, IntelEvent, IntelOverviewSummary, IntelWorkScope, RuntimePlan, SchedulerStatus } from "../types";

type OverviewTab = "alerts" | "events" | "source-health";

interface IntelOverviewPageProps {
  summary: IntelOverviewSummary;
  runtime: SchedulerStatus;
  runtimePlan: RuntimePlan;
  savingRuntimePlan: boolean;
  busyRuntimeAction?: "start" | "stop" | null;
  refreshing?: boolean;
  onSaveRuntimePlan: (payload: Omit<RuntimePlan, "effective_mode">) => Promise<void>;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
  onSyncNow: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onNavigate: (tab: OverviewTab) => void;
  onWatchEvent: (eventId: string) => Promise<void>;
  onIgnoreEvent: (eventId: string) => Promise<void>;
}

const WORK_SCOPE_LABELS: Record<IntelWorkScope, string> = {
  collect_only: "只采集",
  collect_events: "采集 + 事件",
  collect_events_alerts: "采集 + 事件 + 预警",
};

const LAUNCH_MODE_LABELS: Record<RuntimePlan["launch_mode"], string> = {
  once_now: "立即一次",
  once_at: "定时一次",
  interval_now: "立即循环",
  interval_at: "定时循环",
};

const CYCLE_LABELS: Record<string, string> = {
  idle: "空闲",
  starting: "启动中",
  collecting: "采集中",
  clustering: "聚类中",
  scoring: "评分中",
  drafting: "生成稿件中",
  wechat_sync: "同步微信",
  completed: "已完成",
};

function plansEqual(left: Omit<RuntimePlan, "effective_mode">, right: RuntimePlan) {
  const leftStartAt = left.launch_mode.endsWith("_at") ? (left.start_at ?? null) : null;
  const rightStartAt = right.launch_mode.endsWith("_at") ? (right.start_at ?? null) : null;
  const leftInterval = left.launch_mode.includes("interval") ? (left.interval_minutes ?? null) : null;
  const rightInterval = right.launch_mode.includes("interval") ? (right.interval_minutes ?? null) : null;
  return (
    left.launch_mode === right.launch_mode &&
    leftStartAt === rightStartAt &&
    leftInterval === rightInterval &&
    left.timezone === right.timezone &&
    left.work_scope === right.work_scope
  );
}

function buildPlanDraft(runtimePlan: RuntimePlan): Omit<RuntimePlan, "effective_mode"> {
  return {
    launch_mode: runtimePlan.launch_mode,
    start_at: runtimePlan.launch_mode.endsWith("_at") ? (runtimePlan.start_at ?? null) : null,
    interval_minutes: runtimePlan.launch_mode.includes("interval") ? (runtimePlan.interval_minutes ?? 30) : null,
    timezone: runtimePlan.timezone,
    work_scope: runtimePlan.work_scope,
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

function runtimeTone(runtime: SchedulerStatus) {
  if (runtime.run_status === "failed") return "danger";
  if (runtime.recovered_run_id || runtime.run_status === "abandoned") return "warning";
  if (runtime.control_state === "running" || runtime.run_status === "running") return "success";
  if (runtime.control_state === "armed" || runtime.control_state === "waiting") return "warning";
  return "neutral";
}

function runtimeLabel(runtime: SchedulerStatus) {
  if (runtime.run_status === "failed") return "本轮失败";
  if (runtime.recovered_run_id || runtime.run_status === "abandoned") return "已接管异常轮次";
  if (runtime.control_state === "running" || runtime.run_status === "running") return "运行中";
  if (runtime.control_state === "armed" || runtime.control_state === "waiting") return "等待下一轮";
  return "已停止";
}

export function IntelOverviewPage({
  summary,
  runtime,
  runtimePlan,
  savingRuntimePlan,
  busyRuntimeAction,
  refreshing,
  onSaveRuntimePlan,
  onStart,
  onStop,
  onSyncNow,
  onRefresh,
  onNavigate,
  onWatchEvent,
  onIgnoreEvent,
}: IntelOverviewPageProps) {
  const [planDraft, setPlanDraft] = useState<Omit<RuntimePlan, "effective_mode">>(buildPlanDraft(runtimePlan));
  const [planExpanded, setPlanExpanded] = useState(false);

  const cycleStartRef = useRef<number | null>(null);
  const prevPercentRef = useRef<number>(0);

  useEffect(() => {
    setPlanDraft(buildPlanDraft(runtimePlan));
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

  const planDirty = useMemo(() => !plansEqual(planDraft, runtimePlan), [planDraft, runtimePlan]);
  const showCycleStatus =
    runtime.current_cycle !== "idle" ||
    runtime.run_status === "running" ||
    runtime.run_status === "failed" ||
    runtime.run_status === "abandoned";
  const nextRunLabel = useMemo(() => {
    if (showCycleStatus) {
      return "本轮执行中";
    }
    if (runtime.control_state === "armed" || runtime.control_state === "waiting") {
      return formatRelativeTime(summary.next_run_at, "等待计划");
    }
    return formatRelativeTime(summary.next_run_at, "未安排");
  }, [runtime.control_state, summary.next_run_at, showCycleStatus]);

  async function handleStart() {
    if (planDirty) {
      await onSaveRuntimePlan(planDraft);
    }
    await onStart();
  }

  return (
    <>
      {/* 主控条 - 始终可见，紧凑单行 */}
      <section className="panel intel-hero-panel">
        <div className="intel-plan-compact-bar">
          <div className="intel-plan-compact-status">
            <span className={`status-badge status-${runtimeTone(runtime)}`}>
              {runtimeLabel(runtime)}
            </span>
            <span>{WORK_SCOPE_LABELS[planDraft.work_scope]}</span>
            <span>{LAUNCH_MODE_LABELS[planDraft.launch_mode]}</span>
            {planDraft.launch_mode.includes("interval") ? <span>每 {planDraft.interval_minutes ?? 30} 分钟</span> : null}
            <span className="subtle">{nextRunLabel}</span>
          </div>
          <div className="intel-hero-actions">
            <button type="button" className="ghost-button" disabled={refreshing} onClick={() => void onRefresh()}>
              <RefreshCcw size={14} />
            </button>
            <button type="button" className="ghost-button" onClick={() => void onSyncNow()}>
              <RadioTower size={14} />
              补抓
            </button>
            <button
              type="button"
              className="ghost-button compact"
              onClick={() => setPlanExpanded((v) => !v)}
            >
              {planExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              计划
              {planDirty ? <span className="dirty-dot" /> : null}
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={busyRuntimeAction === "start" || runtime.running}
              onClick={() => void handleStart()}
            >
              <PlayCircle size={14} />
              {busyRuntimeAction === "start" ? "启动中..." : "开始"}
            </button>
            <button
              type="button"
              className="ghost-button"
              disabled={busyRuntimeAction === "stop" || !runtime.running}
              onClick={() => void onStop()}
            >
              <PauseCircle size={14} />
              {busyRuntimeAction === "stop" ? "停止中..." : "停止"}
            </button>
          </div>
        </div>

        {/* 运行阶段指示器 */}
        {showCycleStatus ? (
          <div className="intel-cycle-progress">
            {runtime.run_status === "failed" ? (
              <AlertTriangle size={13} className="text-red-600" />
            ) : runtime.current_cycle === "completed" ? (
              <CheckCircle2 size={13} className="text-green-600" />
            ) : (
              <Loader2 size={13} className="spin" />
            )}
            <span className={`intel-cycle-stage${runtime.current_cycle === "completed" ? " intel-cycle-stage-done" : ""}`}>
              {runtime.run_status === "failed" ? "本轮失败" : (CYCLE_LABELS[runtime.current_cycle] ?? runtime.current_cycle)}
            </span>
            <span className="intel-cycle-percent">{runtime.current_cycle_progress_percent}%</span>
            {estimatedRemaining && runtime.current_cycle !== "completed" && runtime.run_status !== "failed" ? (
              <span className="subtle">剩余 {estimatedRemaining}</span>
            ) : null}
            {runtime.current_cycle_progress_total > 0 ? (
              <span className="subtle">
                {runtime.current_cycle_progress_done}/{runtime.current_cycle_progress_total}
              </span>
            ) : null}
            {runtime.current_cycle_started_at ? (
              <span className="subtle">{formatRelativeTime(runtime.current_cycle_started_at, "")}</span>
            ) : null}
          </div>
        ) : null}

        {showCycleStatus && runtime.current_cycle_progress_percent > 0 ? (
          <div className="intel-cycle-meter">
            <div
              className="intel-cycle-meter-fill"
              style={{ width: `${Math.max(0, Math.min(runtime.current_cycle_progress_percent, 100))}%` }}
            />
          </div>
        ) : null}

        {(showCycleStatus || runtime.current_cycle_progress_label) && (runtime.current_cycle_progress_label || runtime.run_error || runtime.last_error) ? (
          <p className="intel-cycle-label">{runtime.current_cycle_progress_label || runtime.run_error || runtime.last_error}</p>
        ) : null}

        {runtime.recovered_run_id ? (
          <p className="intel-cycle-label">已接管异常轮次 {runtime.recovered_run_id}，当前状态以最新轮次为准。</p>
        ) : null}

        {/* 展开的计划配置面板 */}
        {planExpanded ? (
          <div className="intel-plan-grid">
            <label>
              <span>工作内容</span>
              <select
                value={planDraft.work_scope}
                onChange={(event) =>
                  setPlanDraft((current) => ({
                    ...current,
                    work_scope: event.target.value as IntelWorkScope,
                  }))
                }
              >
                <option value="collect_only">只采集</option>
                <option value="collect_events">采集 + 事件</option>
                <option value="collect_events_alerts">采集 + 事件 + 预警</option>
              </select>
            </label>

            <label>
              <span>启动方式</span>
              <select
                value={planDraft.launch_mode}
                onChange={(event) =>
                  setPlanDraft((current) => ({
                    ...current,
                    launch_mode: event.target.value as RuntimePlan["launch_mode"],
                    start_at: event.target.value.endsWith("_at") ? current.start_at : null,
                    interval_minutes: event.target.value.includes("interval") ? current.interval_minutes ?? 30 : null,
                  }))
                }
              >
                <option value="once_now">立即一次</option>
                <option value="once_at">定时一次</option>
                <option value="interval_now">立即循环</option>
                <option value="interval_at">定时循环</option>
              </select>
            </label>

            {(planDraft.launch_mode === "once_at" || planDraft.launch_mode === "interval_at") ? (
              <label>
                <span>开始时间</span>
                <input
                  type="datetime-local"
                  value={toDateTimeLocalValue(planDraft.start_at)}
                  onChange={(event) =>
                    setPlanDraft((current) => ({
                      ...current,
                      start_at: event.target.value ? new Date(event.target.value).toISOString() : null,
                    }))
                  }
                />
              </label>
            ) : null}

            {(planDraft.launch_mode === "interval_now" || planDraft.launch_mode === "interval_at") ? (
              <label>
                <span>频率</span>
                <select
                  value={String(planDraft.interval_minutes ?? 30)}
                  onChange={(event) =>
                    setPlanDraft((current) => ({
                      ...current,
                      interval_minutes: Number(event.target.value),
                    }))
                  }
                >
                  <option value="10">10 分钟</option>
                  <option value="15">15 分钟</option>
                  <option value="20">20 分钟</option>
                  <option value="30">30 分钟</option>
                  <option value="60">60 分钟</option>
                </select>
              </label>
            ) : null}
          </div>
        ) : null}

        {/* 展开时的保存行 */}
        {planExpanded ? (
          <div className="intel-plan-footer">
            <div className="intel-plan-status">
              <span>当前阶段: {runtime.current_cycle || "idle"}</span>
              <span>上轮: {formatDateTime(runtime.last_cycle_started_at, { fallback: "尚未执行" })}</span>
              <span>耗时: {formatDuration(runtime.last_cycle_duration_seconds, "暂无")}</span>
            </div>
            <div className="intel-plan-actions">
              {planDirty ? <span className="dirty-chip">有未保存变更</span> : <span className="subtle-chip">已保存</span>}
              <button type="button" className="ghost-button compact" disabled={savingRuntimePlan} onClick={() => void onSaveRuntimePlan(planDraft)}>
                <Save size={14} />
                {savingRuntimePlan ? "保存中..." : "保存"}
              </button>
            </div>
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
            {summary.top_alerts.length ? summary.top_alerts.slice(0, 4).map((alert) => (
              <div key={alert.id} className="intel-alert-card">
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
                <a href={alert.representative_link} target="_blank" rel="noreferrer">查看原文</a>
              </div>
            )) : <p className="empty-state">当前没有爆发或上升中的预警。</p>}
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
              <div key={event.id} className="intel-event-card">
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
            )) : <p className="empty-state">还没有形成热点事件。</p>}
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
              <span>素材变化</span>
              <strong>{summary.new_items_count}</strong>
              <p>更新 {summary.updated_items_count} / 已见过 {summary.seen_items_count}</p>
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
                <p>{formatDateTime(runtime.last_cycle_started_at, { fallback: "尚未执行" })}</p>
              </div>
            </div>
            <div>
              <BellRing size={16} />
              <div>
                <strong>上轮耗时</strong>
                <p>{formatDuration(runtime.last_cycle_duration_seconds, "暂无")}</p>
              </div>
            </div>
            <div>
              <AlertTriangle size={16} />
              <div>
                <strong>最近异常</strong>
                <p>{runtime.run_error || runtime.last_error || summary.source_alerts[0] || "暂无异常"}</p>
              </div>
            </div>
          </div>
        </article>
      </section>
    </>
  );
}
