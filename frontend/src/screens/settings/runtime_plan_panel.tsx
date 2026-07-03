import { useEffect, useState } from "react";
import { Save } from "lucide-react";

import { formatDateTime, formatDuration, toDateTimeLocalValue } from "../../lib/time";
import type { AdmissionStrategy, AutomationMode, RuntimePlan, SchedulerStatus } from "../../types";

const ADMISSION_STRATEGY_LABELS: Record<AdmissionStrategy, string> = {
  top_scored: "按热度自动选（推荐）",
  conservative: "仅爆发",
  balanced: "上升+爆发",
  aggressive: "上升+爆发+观察",
};

const LAUNCH_MODE_LABELS: Record<RuntimePlan["launch_mode"], string> = {
  once_now: "立即一次",
  once_at: "定时一次",
  interval_now: "立即循环",
  interval_at: "定时循环",
};

interface RuntimePlanPanelProps {
  runtimePlan: RuntimePlan;
  runtime: SchedulerStatus;
  savingRuntimePlan: boolean;
  onSaveRuntimePlan: (payload: Omit<RuntimePlan, "effective_mode">) => Promise<void>;
  onSetAutomationMode: (mode: AutomationMode) => Promise<void>;
}

export function RuntimePlanPanel({
  runtimePlan,
  runtime,
  savingRuntimePlan,
  onSaveRuntimePlan,
  onSetAutomationMode,
}: RuntimePlanPanelProps) {
  const [draft, setDraft] = useState<Omit<RuntimePlan, "effective_mode">>(buildDraft(runtimePlan));

  useEffect(() => {
    setDraft(buildDraft(runtimePlan));
  }, [runtimePlan]);

  const dirty = draft.launch_mode !== runtimePlan.launch_mode
    || draft.interval_minutes !== runtimePlan.interval_minutes
    || draft.start_at !== runtimePlan.start_at
    || draft.admission_strategy !== runtimePlan.admission_strategy
    || draft.batch_limit !== runtimePlan.batch_limit;

  function handleSave() {
    void onSaveRuntimePlan(draft);
  }

  const isAutomated = runtimePlan.effective_mode === "automated";

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">运行计划</p>
          <h2>高级运行配置</h2>
          <p className="subtle">低频调整的配置项，大多数用户不需要修改。</p>
        </div>
      </div>

      <div className="panel-body">
        <div className="intel-plan-grid">
          <label>
            <span>运行模式</span>
            <select
              value={runtimePlan.effective_mode}
              onChange={(e) => void onSetAutomationMode(e.target.value as AutomationMode)}
            >
              <option value="manual">手动模式</option>
              <option value="automated">计划模式</option>
            </select>
          </label>

          <label>
            <span>信息获取方式</span>
            <select
              value={draft.launch_mode}
              onChange={(e) => setDraft((c) => ({
                ...c,
                launch_mode: e.target.value as RuntimePlan["launch_mode"],
                start_at: e.target.value.endsWith("_at") ? c.start_at : null,
                interval_minutes: e.target.value.includes("interval") ? c.interval_minutes ?? 30 : null,
              }))}
            >
              {Object.entries(LAUNCH_MODE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>

          {draft.launch_mode === "once_at" || draft.launch_mode === "interval_at" ? (
            <label>
              <span>开始时间</span>
              <input
                type="datetime-local"
                value={toDateTimeLocalValue(draft.start_at)}
                onChange={(e) => setDraft((c) => ({
                  ...c,
                  start_at: e.target.value ? new Date(e.target.value).toISOString() : null,
                }))}
              />
            </label>
          ) : null}

          {isAutomated ? (
            <label>
              <span>准入策略</span>
              <select
                value={draft.admission_strategy}
                onChange={(e) => setDraft((c) => ({
                  ...c,
                  admission_strategy: e.target.value as AdmissionStrategy,
                }))}
              >
                {Object.entries(ADMISSION_STRATEGY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
          ) : null}

          {isAutomated ? (
            <label>
              <span>每轮上限</span>
              <select
                value={String(draft.batch_limit)}
                onChange={(e) => setDraft((c) => ({ ...c, batch_limit: Number(e.target.value) }))}
              >
                <option value="1">1 条</option>
                <option value="2">2 条</option>
                <option value="3">3 条</option>
                <option value="5">5 条</option>
              </select>
            </label>
          ) : null}
        </div>

        <div className="intel-plan-footer">
          {dirty ? <span className="dirty-chip">有未保存变更</span> : <span className="subtle-chip">已保存</span>}
          <button type="button" className="primary-button" disabled={savingRuntimePlan || !dirty} onClick={handleSave}>
            <Save size={14} />
            {savingRuntimePlan ? "保存中..." : "保存"}
          </button>
        </div>

        <div className="intel-runtime-section">
          <span className="subtle">当前状态：{runtime.run_status}</span>
          <span className="subtle">上轮：{formatDateTime(runtime.last_cycle_started_at, { fallback: "尚未执行" })}</span>
          <span className="subtle">耗时：{formatDuration(runtime.last_cycle_duration_seconds, "暂无")}</span>
          <span className="subtle">今日已运行：{runtime.completed_cycles_today} 次</span>
        </div>
      </div>
    </section>
  );
}

function buildDraft(plan: RuntimePlan): Omit<RuntimePlan, "effective_mode"> {
  return {
    launch_mode: plan.launch_mode,
    start_at: plan.launch_mode.endsWith("_at") ? (plan.start_at ?? null) : null,
    interval_minutes: plan.launch_mode.includes("interval") ? (plan.interval_minutes ?? 30) : null,
    timezone: plan.timezone,
    work_scope: "collect_events_alerts",
    delivery_mode: plan.delivery_mode,
    delivery_schedule_time: plan.delivery_schedule_time ?? null,
    admission_strategy: plan.admission_strategy,
    batch_limit: plan.batch_limit,
    admission_filters: { ...plan.admission_filters },
  };
}
