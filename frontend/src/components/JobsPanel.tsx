import { Bot, Layers3, PlayCircle, ScanSearch, Send, WandSparkles } from "lucide-react";

import { formatDateTime, formatDuration } from "../lib/time";
import type { AutomationModeDefinition, JobItem, PublishTask, RuntimePlan, SchedulerStatus } from "../types";
import { JobBadge, PublishTaskBadge } from "./StatusBadge";

interface JobsPanelProps {
  jobs: JobItem[];
  publishTasks: PublishTask[];
  runtime: SchedulerStatus;
  runtimePlan: RuntimePlan;
  currentAutomationMode: AutomationModeDefinition;
  busyAction?: string | null;
  onRun: (action: string) => Promise<void>;
}

const primaryActions = [
  { action: "collect_news", label: "雷达获取一次", icon: ScanSearch },
  { action: "rebuild_candidates", label: "重建候选一次", icon: WandSparkles },
  { action: "build_digest", label: "批量生成初稿一次", icon: WandSparkles }
];

const advancedActions = [
  { action: "sync_wechat_draft", label: "同步草稿箱", icon: Layers3 },
  { action: "open_preview", label: "准备预览", icon: Bot },
  { action: "publish_pipeline", label: "执行完整链路", icon: Send },
  { action: "check_browser", label: "检查浏览器", icon: PlayCircle }
];

function launchModeLabel(value: RuntimePlan["launch_mode"]) {
  const map: Record<RuntimePlan["launch_mode"], string> = {
    once_now: "立即执行一次",
    once_at: "指定时间执行一次",
    interval_now: "立即开始循环",
    interval_at: "指定时间后循环",
  };
  return map[value];
}

function formatRuntimeIssueLabel(sourceName: string | null | undefined, message: string) {
  return `${sourceName?.trim() ? `${sourceName}: ` : "系统异常："}${message}`;
}

export function JobsPanel({
  jobs,
  publishTasks,
  runtime,
  runtimePlan,
  currentAutomationMode,
  busyAction,
  onRun
}: JobsPanelProps) {
  const manualDisabled = runtime.control_state !== "stopped";
  const cycleSummary = runtime.last_cycle_summary ?? null;

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">手动任务中心</p>
          <h2>只在自动关闭时开放的补跑入口</h2>
          <p className="subtle">
            自动运行归驾驶舱统一控制；这里只负责手动补跑、重建和排查，不和自动调度混在一起。
          </p>
        </div>
      </div>

      <div className="runtime-card-grid">
        <article className="runtime-card">
          <span>自动运行状态</span>
          <strong>{runtime.control_state === "stopped" ? "已关闭" : "已启用"}</strong>
          <p>当前模式：{currentAutomationMode.label}</p>
        </article>
        <article className="runtime-card">
          <span>当前计划</span>
          <strong>{launchModeLabel(runtimePlan.launch_mode)}</strong>
          <p>下一次：{formatDateTime(runtime.next_collect_at, { fallback: "未设定" })}</p>
        </article>
        <article className="runtime-card">
          <span>最近一轮开始</span>
          <strong>{formatDateTime(runtime.last_cycle_started_at, { fallback: "暂无" })}</strong>
          <p>耗时：{formatDuration(runtime.last_cycle_duration_seconds, "暂无")}</p>
        </article>
        <article className="runtime-card">
          <span>今日轮次</span>
          <strong>{runtime.completed_cycles_today} 成功 / {runtime.failed_cycles_today} 失败</strong>
          <p>{runtime.last_error ? `最近错误：${runtime.last_error}` : "当前没有自动调度错误"}</p>
        </article>
      </div>

      {cycleSummary ? (
        <section className="intel-runtime-section">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">最近一轮</p>
              <h3>执行摘要</h3>
            </div>
          </div>
          <div className="intel-score-row">
            <span>新增素材 {cycleSummary.new_items_count}</span>
            <span>新事件 {cycleSummary.new_events_count}</span>
            <span>升温事件 {cycleSummary.growing_events_count}</span>
            <span>失败来源 {cycleSummary.failed_source_count}</span>
          </div>
          {cycleSummary.slow_sources.length ? (
            <div className="intel-runtime-chip-row">
              {cycleSummary.slow_sources.map((item) => (
                <span key={`${item.source_key}-${item.duration_ms}`} className="subtle-chip">
                  {item.source_name} {Math.round(item.duration_ms / 1000)}s
                </span>
              ))}
            </div>
          ) : null}
          {cycleSummary.issues.length ? (
            <ul className="intel-runtime-issues compact">
              {cycleSummary.issues.slice(0, 4).map((item, index) => (
                <li key={`${item.source_key ?? "runtime"}-${index}`}>
                  {formatRuntimeIssueLabel(item.source_name, item.message)}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      <section className="job-control-cluster">
        <div className="job-control-header">
          <div>
            <p className="eyebrow">手动补跑动作</p>
            <h3>只有自动关闭时才可以执行</h3>
            <p className="subtle">
              这样可以避免自动轮次和手动补跑同时写数据，导致你判断不清现在看到的到底是哪一轮结果。
            </p>
          </div>
        </div>

        <div className="quick-action-grid">
          {primaryActions.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.action}
                type="button"
                className="quick-action"
                disabled={manualDisabled || busyAction === item.action}
                onClick={() => void onRun(item.action)}
              >
                <Icon size={16} />
                <span>{busyAction === item.action ? "执行中..." : item.label}</span>
              </button>
            );
          })}
        </div>

        <div className="manual-hint">
          {manualDisabled
            ? "自动运行已启用，请先回驾驶舱停止自动运行，再使用这里的手动补跑动作。"
            : "当前自动运行已关闭，这里的动作会直接刷新情报、候选和稿件相关数据。"}
        </div>

        <details className="advanced-jobs">
          <summary>高级动作与发布链路</summary>
          <div className="quick-action-grid secondary">
            {advancedActions.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.action}
                  type="button"
                  className="quick-action subdued"
                  disabled={manualDisabled || busyAction === item.action}
                  onClick={() => void onRun(item.action)}
                >
                  <Icon size={16} />
                  <span>{busyAction === item.action ? "执行中..." : item.label}</span>
                </button>
              );
            })}
          </div>
        </details>
      </section>

      <div className="jobs-layout">
        <div className="job-list">
          {jobs.map((job) => (
            <article key={job.id} className="job-row">
              <div>
                <strong>{job.label}</strong>
                <p>{job.message}</p>
              </div>
              <div className="job-meta">
                <JobBadge status={job.status} />
                <span>{formatDateTime(job.finished_at ?? job.started_at, { fallback: "暂无" })}</span>
              </div>
            </article>
          ))}
        </div>
        <div className="task-list">
          {publishTasks.map((task) => (
            <article key={task.id} className="mini-row stacked">
              <div className="row-with-badge">
                <strong>{task.action}</strong>
                <PublishTaskBadge status={task.status} />
              </div>
              <p>{task.message}</p>
              {task.step_logs.length ? <p>步骤：{task.step_logs.slice(0, 2).join(" | ")}</p> : null}
              {task.artifacts.length ? <p>产物：{task.artifacts[0]}</p> : null}
              <span className="tiny-meta">{formatDateTime(task.created_at, { fallback: "暂无" })}</span>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
