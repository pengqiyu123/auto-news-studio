import { ChevronDown, PauseCircle, PlayCircle, Radar, RefreshCcw, Save, Sparkles, Timer } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { formatDateTime, formatDuration, formatRelativeTime, toDateTimeLocalValue } from "../lib/time";
import type {
  AutomationMode,
  AutomationModeDefinition,
  AutomationModeProfile,
  RuntimePlan,
  SchedulerStatus,
} from "../types";

interface GlobalControlBarProps {
  runtime: SchedulerStatus;
  runtimePlan: RuntimePlan;
  currentMode: AutomationMode;
  modes: AutomationModeDefinition[];
  profiles: AutomationModeProfile[];
  pendingMode?: AutomationMode | null;
  savingProfileMode?: AutomationMode | null;
  savingRuntimePlan?: boolean;
  busyRuntimeAction?: "start" | "stop" | null;
  refreshing?: boolean;
  onModeChange: (mode: AutomationMode) => Promise<void>;
  onSaveProfile: (mode: AutomationMode, profile: AutomationModeProfile) => Promise<void>;
  onSaveRuntimePlan: (payload: Omit<RuntimePlan, "effective_mode">) => Promise<void>;
  onStart: () => Promise<void>;
  onStop: () => Promise<void>;
  onRefresh: () => Promise<void>;
}

function modeStateLabel(item: AutomationModeDefinition, currentMode: AutomationMode, runtime: SchedulerStatus) {
  if (!item.available) {
    return "后续开放";
  }
  if (item.key !== currentMode) {
    return "未选中";
  }
  if (runtime.control_state === "stopped") {
    return "已选中";
  }
  return "生效中";
}

function modeStateTone(item: AutomationModeDefinition, currentMode: AutomationMode, runtime: SchedulerStatus) {
  if (!item.available) {
    return "warning";
  }
  if (item.key !== currentMode) {
    return "neutral";
  }
  if (runtime.control_state === "stopped") {
    return "warning";
  }
  return "success";
}

function formatStepTime(label: string, value?: string | null, emptyText = "尚未执行") {
  return {
    label,
    value: formatDateTime(value, { fallback: emptyText }),
    helper: value ? formatRelativeTime(value) : emptyText
  };
}

function draftTriggerLabel(trigger: AutomationModeProfile["draft_trigger"]) {
  if (trigger === "after_sync") {
    return "每轮同步后自动成稿";
  }
  if (trigger === "scheduled") {
    return "按固定时间统一成稿";
  }
  return "仅手动成稿";
}

function draftDeliveryLabel(delivery: AutomationModeProfile["draft_delivery"]) {
  return delivery === "wechat_draft" ? "自动同步微信草稿箱" : "只保存在项目本地";
}

function publishStrategyLabel(strategy: AutomationModeProfile["publish_strategy"]) {
  if (strategy === "wechat_draft_only") {
    return "只进微信草稿箱，不自动发表";
  }
  if (strategy === "guarded_send") {
    return "按计划进入受控发表";
  }
  return "不自动触发发布";
}

function controlStateLabel(runtime: SchedulerStatus) {
  if (runtime.control_state === "armed") {
    return "等待开始";
  }
  if (runtime.control_state === "running") {
    return "正在运行";
  }
  if (runtime.control_state === "waiting") {
    return "等待下一轮";
  }
  return "自动运行已关闭";
}

function launchModeLabel(value: RuntimePlan["launch_mode"]) {
  const map: Record<RuntimePlan["launch_mode"], string> = {
    once_now: "立即执行一次",
    once_at: "指定时间执行一次",
    interval_now: "立即开始循环",
    interval_at: "指定时间后循环",
  };
  return map[value];
}

function currentRunSummary(runtime: SchedulerStatus) {
  if (runtime.control_state === "armed") {
    return `已设定开始时间：${formatDateTime(runtime.scheduled_start_at, { fallback: "暂无" })}`;
  }
  if (runtime.control_state === "running") {
    return `当前阶段：${runtime.current_cycle}`;
  }
  if (runtime.control_state === "waiting") {
    return `下一轮：${formatDateTime(runtime.next_collect_at, { fallback: "暂无" })}`;
  }
  return "自动计划当前没有启用。";
}

function profilesEqual(left: AutomationModeProfile | null, right: AutomationModeProfile | null) {
  if (!left || !right) {
    return false;
  }
  return JSON.stringify(left) === JSON.stringify(right);
}

function plansEqual(left: Omit<RuntimePlan, "effective_mode">, right: RuntimePlan) {
  return (
    left.launch_mode === right.launch_mode &&
    (left.start_at ?? null) === (right.start_at ?? null) &&
    (left.interval_minutes ?? null) === (right.interval_minutes ?? null) &&
    left.timezone === right.timezone &&
    left.delivery_mode === right.delivery_mode &&
    (left.delivery_schedule_time ?? null) === (right.delivery_schedule_time ?? null) &&
    left.admission_strategy === right.admission_strategy &&
    left.batch_limit === right.batch_limit &&
    JSON.stringify(left.admission_filters ?? {}) === JSON.stringify(right.admission_filters ?? {})
  );
}

export function GlobalControlBar({
  runtime,
  runtimePlan,
  currentMode,
  modes,
  profiles,
  pendingMode,
  savingProfileMode,
  savingRuntimePlan,
  busyRuntimeAction,
  refreshing,
  onModeChange,
  onSaveProfile,
  onSaveRuntimePlan,
  onStart,
  onStop,
  onRefresh
}: GlobalControlBarProps) {
  const [editingMode, setEditingMode] = useState<AutomationMode>(currentMode);
  const currentProfile = useMemo(
    () => profiles.find((item) => item.mode === editingMode) ?? profiles[0],
    [profiles, editingMode]
  );
  const [draft, setDraft] = useState<AutomationModeProfile | null>(currentProfile ?? null);
  const [runtimeDraft, setRuntimeDraft] = useState<Omit<RuntimePlan, "effective_mode">>({
    launch_mode: runtimePlan.launch_mode,
    start_at: runtimePlan.start_at ?? null,
    interval_minutes: runtimePlan.interval_minutes ?? 30,
    timezone: runtimePlan.timezone,
    work_scope: runtimePlan.work_scope,
    delivery_mode: runtimePlan.delivery_mode,
    delivery_schedule_time: runtimePlan.delivery_schedule_time ?? null,
    admission_strategy: runtimePlan.admission_strategy,
    batch_limit: runtimePlan.batch_limit,
    admission_filters: { ...runtimePlan.admission_filters }
  });

  useEffect(() => {
    setDraft(currentProfile ?? null);
  }, [currentProfile]);

  useEffect(() => {
    setEditingMode(currentMode);
  }, [currentMode]);

  useEffect(() => {
    setRuntimeDraft({
      launch_mode: runtimePlan.launch_mode,
      start_at: runtimePlan.start_at ?? null,
      interval_minutes: runtimePlan.interval_minutes ?? 30,
      timezone: runtimePlan.timezone,
      work_scope: runtimePlan.work_scope,
      delivery_mode: runtimePlan.delivery_mode,
      delivery_schedule_time: runtimePlan.delivery_schedule_time ?? null,
      admission_strategy: runtimePlan.admission_strategy,
      batch_limit: runtimePlan.batch_limit,
      admission_filters: { ...runtimePlan.admission_filters }
    });
  }, [runtimePlan]);

  if (!draft) {
    return null;
  }

  const currentModeDef = modes.find((item) => item.key === currentMode);
  const modeDirty = !profilesEqual(draft, currentProfile ?? null);
  const runtimePlanDirty = !plansEqual(runtimeDraft, runtimePlan);
  const checkpoints = [
    formatStepTime("采集", runtime.last_collect_at),
    formatStepTime("候选", runtime.last_candidate_at),
    formatStepTime(
      "初稿",
      runtime.last_draft_at,
      currentModeDef?.auto_generate_drafts ? "尚未生成" : "本模式不自动成稿"
    )
  ];

  async function handleStartClick() {
    if (runtimePlanDirty) {
      await onSaveRuntimePlan(runtimeDraft);
    }
    await onStart();
  }

  return (
    <section className="global-control-bar">
      <div className="global-control-main">
        <div className="global-control-title">
          <div className="panel-icon">
            <Radar size={18} />
          </div>
          <div>
            <strong>全局主控</strong>
            <p>先选模式，再定时间计划。你改完计划后直接点启动，系统会先保存计划再启动。</p>
          </div>
        </div>

        <div className="global-mode-group">
          {modes.map((item) => {
            const disabled = !item.available;
            const selected = item.key === currentMode;
            return (
              <button
                key={item.key}
                type="button"
                className={`mode-chip ${selected ? "mode-chip-active" : ""}`}
                disabled={disabled || selected || pendingMode === item.key}
                onClick={() => void onModeChange(item.key)}
                title={disabled ? "后续开放" : item.description}
              >
                {pendingMode === item.key ? "切换中..." : item.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="global-control-stats">
        <div className="global-stat">
          <span>自动运行状态</span>
          <strong>{controlStateLabel(runtime)}</strong>
        </div>
        <div className="global-stat">
          <span>当前启动方式</span>
          <strong>{launchModeLabel(runtimePlan.launch_mode)}</strong>
        </div>
        <div className="global-stat">
          <span>计划开始</span>
          <strong>{formatDateTime(runtime.scheduled_start_at ?? runtimePlan.start_at, { fallback: "立即" })}</strong>
        </div>
        <div className="global-stat">
          <span>已运行时长</span>
          <strong>{formatDuration(runtime.uptime_seconds, "0秒")}</strong>
        </div>
        <div className="global-stat">
          <span>当前阶段</span>
          <strong>{runtime.current_cycle || "idle"}</strong>
        </div>
        <div className="global-stat">
          <span>下一轮</span>
          <strong>{formatDateTime(runtime.next_collect_at, { fallback: "未设定" })}</strong>
        </div>
        <div className="global-stat">
          <span>今日轮次</span>
          <strong>{runtime.completed_cycles_today} 成功 / {runtime.failed_cycles_today} 失败</strong>
        </div>
      </div>

      <div className="mode-compact-grid">
        {modes.map((item) => {
          const profile = profiles.find((entry) => entry.mode === item.key);
          const selected = item.key === currentMode;
          const compactSummary = profile
            ? item.key === "radar_only"
              ? "自动采集与候选更新，不自动成稿"
              : item.key === "radar_and_draft"
                ? `${draftTriggerLabel(profile.draft_trigger)}，${draftDeliveryLabel(profile.draft_delivery)}`
                : `${draftTriggerLabel(profile.draft_trigger)}，${publishStrategyLabel(profile.publish_strategy)}`
            : item.description;
          return (
            <article
              key={item.key}
              className={`mode-compact-card ${selected ? "mode-compact-card-active" : ""} ${!item.available ? "mode-compact-card-disabled" : ""}`}
              onClick={() => setEditingMode(item.key)}
            >
              <div className="mode-visibility-head">
                <div>
                  <div className="row-with-badge">
                    <strong>{item.label}</strong>
                    <span className={`status-badge status-${modeStateTone(item, currentMode, runtime)}`}>
                      {modeStateLabel(item, currentMode, runtime)}
                    </span>
                  </div>
                  <p>{compactSummary}</p>
                </div>
                <div className="panel-icon">
                  {item.key === "radar_only" ? <Radar size={16} /> : <Sparkles size={16} />}
                </div>
              </div>
              {profile ? (
                <div className="mode-compact-meta">
                  <span>{profile.draft_delivery === "wechat_draft" ? "进微信草稿箱" : "本地优先"}</span>
                  <span>{profile.draft_limit} 篇 / 轮</span>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      <details className="mode-config-details" open>
        <summary className="mode-config-summary-row">
          <div>
            <strong>{modes.find((item) => item.key === editingMode)?.label ?? draft.mode} 参数设置</strong>
            <p>
              {editingMode === "radar_only"
                ? "这个模式只负责抓取、标准化、聚类和候选更新。"
                : editingMode === "radar_and_draft"
                  ? `${draftTriggerLabel(draft.draft_trigger)}，${draftDeliveryLabel(draft.draft_delivery)}。`
                  : `${draftTriggerLabel(draft.draft_trigger)}，${publishStrategyLabel(draft.publish_strategy)}。`}
            </p>
          </div>
          <span className="mode-config-toggle">
            展开模式设置
            <ChevronDown size={16} />
          </span>
        </summary>

        <section className="mode-config-panel">
          <div className="mode-config-grid">
            {editingMode !== "radar_only" ? (
              <>
                <label>
                  <span>成稿时机</span>
                  <select
                    value={draft.draft_trigger}
                    onChange={(event) =>
                      setDraft((current) => current ? { ...current, draft_trigger: event.target.value as AutomationModeProfile["draft_trigger"] } : current)
                    }
                  >
                    <option value="after_sync">每轮同步后立即成稿</option>
                    <option value="scheduled">按固定时间统一成稿</option>
                    <option value="manual">只手动成稿</option>
                  </select>
                </label>

                <label>
                  <span>成稿去向</span>
                  <select
                    value={draft.draft_delivery}
                    onChange={(event) =>
                      setDraft((current) => current ? { ...current, draft_delivery: event.target.value as AutomationModeProfile["draft_delivery"] } : current)
                    }
                  >
                    <option value="local_only">只保存在项目本地</option>
                    <option value="wechat_draft">自动同步到微信草稿箱</option>
                  </select>
                </label>

                <label>
                  <span>候选选择</span>
                  <select
                    value={draft.draft_selection}
                    onChange={(event) =>
                      setDraft((current) => current ? { ...current, draft_selection: event.target.value as AutomationModeProfile["draft_selection"] } : current)
                    }
                  >
                    <option value="all_new">全部新增候选</option>
                    <option value="top_scored">优先高分候选</option>
                  </select>
                </label>

                <label>
                  <span>单轮最多成稿数</span>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={draft.draft_limit}
                    onChange={(event) =>
                      setDraft((current) => current ? { ...current, draft_limit: Number(event.target.value || 1) } : current)
                    }
                  />
                </label>
              </>
            ) : null}

            {draft.draft_trigger === "scheduled" && editingMode !== "radar_only" ? (
              <label>
                <span>定时成稿时间</span>
                <input
                  type="time"
                  value={draft.draft_schedule_time ?? ""}
                  onChange={(event) =>
                    setDraft((current) => current ? { ...current, draft_schedule_time: event.target.value } : current)
                  }
                />
              </label>
            ) : null}

            {editingMode === "full_pipeline" ? (
              <>
                <label>
                  <span>发布策略</span>
                  <select
                    value={draft.publish_strategy}
                    onChange={(event) =>
                      setDraft((current) => current ? { ...current, publish_strategy: event.target.value as AutomationModeProfile["publish_strategy"] } : current)
                    }
                  >
                    <option value="disabled">不自动发布</option>
                    <option value="wechat_draft_only">只进微信草稿箱</option>
                    <option value="guarded_send">按计划受控发表</option>
                  </select>
                </label>

                <label>
                  <span>计划发表时间</span>
                  <input
                    type="time"
                    value={draft.publish_schedule_time ?? ""}
                    onChange={(event) =>
                      setDraft((current) => current ? { ...current, publish_schedule_time: event.target.value } : current)
                    }
                  />
                </label>

                <label className="toggle-field">
                  <span>仅允许已审核稿件进入发表</span>
                  <input
                    type="checkbox"
                    checked={draft.require_approval}
                    onChange={(event) =>
                      setDraft((current) => current ? { ...current, require_approval: event.target.checked } : current)
                    }
                  />
                </label>
              </>
            ) : null}
          </div>

          <div className="mode-config-explainer">
            <div className="mode-config-summary">
              <span>当前会怎么跑</span>
              <strong>{currentRunSummary(runtime)}</strong>
              <p>{draft.notes || "模式负责定义抓取、成稿和后续推进策略；运行时间计划在下方单独设置。"}</p>
            </div>
            <div className="mode-visibility-checkpoints">
              {checkpoints.map((checkpoint) => (
                <div key={checkpoint.label} className="mode-checkpoint">
                  <span>{checkpoint.label}</span>
                  <strong>{checkpoint.value}</strong>
                  <p>{checkpoint.helper}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mode-config-actions">
            {modeDirty ? <span className="dirty-chip">有未保存修改</span> : <span className="subtle-chip">当前已同步</span>}
            <button
              type="button"
              className="primary-button"
              disabled={savingProfileMode === draft.mode}
              onClick={() => void onSaveProfile(draft.mode, draft)}
            >
              <Save size={16} />
              {savingProfileMode === draft.mode ? "保存中..." : "保存当前模式参数"}
            </button>
            {runtime.last_error ? <span className="error-note">{runtime.last_error}</span> : null}
          </div>
          <div className="mode-config-divider" />

          <div className="mode-config-subhead">
            <div>
              <strong>自动运行计划</strong>
              <p>这里决定什么时候开始、跑一次还是循环跑。</p>
            </div>
            <div className="runtime-plan-summary">
              <span className={`status-badge status-${runtime.control_state === "stopped" ? "warning" : "success"}`}>
                {controlStateLabel(runtime)}
              </span>
              {runtimePlanDirty ? <span className="dirty-chip">计划未保存</span> : <span className="subtle-chip">计划已保存</span>}
            </div>
          </div>

          <div className="mode-config-grid">
            <label>
              <span>启动方式</span>
              <select
                value={runtimeDraft.launch_mode}
                onChange={(event) =>
                  setRuntimeDraft((current) => ({
                    ...current,
                    launch_mode: event.target.value as RuntimePlan["launch_mode"],
                    start_at: event.target.value.endsWith("_at") ? current.start_at : null,
                    interval_minutes: event.target.value.includes("interval") ? current.interval_minutes ?? 30 : null,
                  }))
                }
              >
                <option value="once_now">立即执行一次</option>
                <option value="once_at">指定时间执行一次</option>
                <option value="interval_now">立即开始循环</option>
                <option value="interval_at">指定时间后循环</option>
              </select>
            </label>

            {(runtimeDraft.launch_mode === "once_at" || runtimeDraft.launch_mode === "interval_at") ? (
              <label>
                <span>开始时间</span>
                <input
                  type="datetime-local"
                  value={toDateTimeLocalValue(runtimeDraft.start_at)}
                  onChange={(event) =>
                    setRuntimeDraft((current) => ({
                      ...current,
                      start_at: event.target.value ? new Date(event.target.value).toISOString() : null,
                    }))
                  }
                />
              </label>
            ) : null}

            {(runtimeDraft.launch_mode === "interval_now" || runtimeDraft.launch_mode === "interval_at") ? (
              <label>
                <span>循环频率</span>
                <select
                  value={String(runtimeDraft.interval_minutes ?? 30)}
                  onChange={(event) =>
                    setRuntimeDraft((current) => ({
                      ...current,
                      interval_minutes: Number(event.target.value),
                    }))
                  }
                >
                  <option value="10">每 10 分钟</option>
                  <option value="15">每 15 分钟</option>
                  <option value="20">每 20 分钟</option>
                  <option value="30">每 30 分钟</option>
                  <option value="60">每 60 分钟</option>
                </select>
              </label>
            ) : null}

            <label>
              <span>时区</span>
              <input value={runtimeDraft.timezone} readOnly />
            </label>
          </div>

          <div className="runtime-plan-brief">
            <div className="mode-config-summary">
              <span>当前计划</span>
              <strong>
                {launchModeLabel(runtimeDraft.launch_mode)}
                {runtimeDraft.launch_mode.includes("interval") ? ` · 每 ${runtimeDraft.interval_minutes ?? 30} 分钟` : ""}
              </strong>
              <p>
                {runtimeDraft.launch_mode.endsWith("_at")
                  ? `开始时间：${formatDateTime(runtimeDraft.start_at, { fallback: "请选择" })}`
                  : "点击启动后会立刻按当前计划执行。"}
              </p>
            </div>

            <div className="mode-visibility-checkpoints">
              <div className="mode-checkpoint">
                <span>已启用时间</span>
                <strong>{formatDateTime(runtime.enabled_at, { fallback: "暂无" })}</strong>
                <p>{formatRelativeTime(runtime.enabled_at, "尚未启用")}</p>
              </div>
              <div className="mode-checkpoint">
                <span>上轮开始</span>
                <strong>{formatDateTime(runtime.last_cycle_started_at, { fallback: "暂无" })}</strong>
                <p>{formatRelativeTime(runtime.last_cycle_started_at, "尚未执行")}</p>
              </div>
              <div className="mode-checkpoint">
                <span>上轮耗时</span>
                <strong>{formatDuration(runtime.last_cycle_duration_seconds, "暂无")}</strong>
                <p>{runtime.last_error ? "最近一轮有异常" : "最近一轮无异常"}</p>
              </div>
            </div>
          </div>

          <div className="mode-config-actions runtime-plan-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={Boolean(savingRuntimePlan)}
              onClick={() => void onSaveRuntimePlan(runtimeDraft)}
            >
              <Timer size={16} />
              {savingRuntimePlan ? "保存中..." : "保存计划"}
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={busyRuntimeAction === "start" || runtime.control_state !== "stopped"}
              onClick={() => void handleStartClick()}
            >
              <PlayCircle size={16} />
              {busyRuntimeAction === "start" ? "启动中..." : runtimePlanDirty ? "保存并启动" : "启动自动运行"}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={busyRuntimeAction === "stop" || runtime.control_state === "stopped"}
              onClick={() => void onStop()}
            >
              <PauseCircle size={16} />
              {busyRuntimeAction === "stop" ? "停止中..." : "停止自动运行"}
            </button>
            <button type="button" className="ghost-button" disabled={refreshing} onClick={() => void onRefresh()}>
              <RefreshCcw size={16} />
              {refreshing ? "刷新中..." : "刷新状态"}
            </button>
          </div>

          <div className="runtime-plan-notes">
            <span>{currentRunSummary(runtime)}</span>
            {!modes.find((item) => item.key === "full_pipeline")?.available ? (
              <span>“自动全流程” 目前仍为预留模式，暂不开放无人值守自动发布。</span>
            ) : null}
          </div>
        </section>
      </details>
    </section>
  );
}
