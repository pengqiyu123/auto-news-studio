import { formatDateTime, formatDuration } from "../lib/time";
import type { LogItem, SchedulerStatus } from "../types";
import { LogBadge } from "./StatusBadge";

interface LogsPanelProps {
  logs: LogItem[];
  runtime: SchedulerStatus;
}

function LogStreamColumn({ title, description, items }: { title: string; description: string; items: LogItem[] }) {
  return (
    <section className="panel log-stream-panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">{title}</p>
          <h2>{description}</h2>
        </div>
      </div>
      <div className="log-list">
        {items.map((log) => (
          <article key={log.id} className="log-row">
            <div className="row-with-badge">
              <strong>{log.category}</strong>
              <LogBadge level={log.level} />
            </div>
            <p>{log.message}</p>
            {log.detail ? <p>{log.detail}</p> : null}
            <span>{log.actor} · {formatDateTime(log.created_at, { fallback: "暂无" })}</span>
          </article>
        ))}
        {!items.length ? <p className="empty-state">暂无记录。</p> : null}
      </div>
    </section>
  );
}

export function LogsPanel({ logs, runtime }: LogsPanelProps) {
  const runtimeLogs = logs.filter((item) => item.stream === "system_runtime");
  const businessLogs = logs.filter((item) => item.stream === "business_event");

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">日志与告警</p>
          <h2>系统运行日志 + 业务动作日志</h2>
          <p className="subtle">现在可以直接区分“系统是否持续运行”与“是谁手动做了什么”。</p>
        </div>
      </div>

      <div className="runtime-card-grid">
        <article className="runtime-card">
          <span>自动运行状态</span>
          <strong>{runtime.control_state === "stopped" ? "已关闭" : runtime.control_state}</strong>
          <p>当前轮次：{runtime.current_cycle}</p>
        </article>
        <article className="runtime-card">
          <span>最近一轮开始</span>
          <strong>{formatDateTime(runtime.last_cycle_started_at, { fallback: "暂无" })}</strong>
          <p>下一次：{formatDateTime(runtime.next_collect_at, { fallback: "暂无" })}</p>
        </article>
        <article className="runtime-card">
          <span>运行时长</span>
          <strong>{formatDuration(runtime.uptime_seconds, "0秒")}</strong>
          <p>上轮耗时：{formatDuration(runtime.last_cycle_duration_seconds, "暂无")}</p>
        </article>
        <article className="runtime-card">
          <span>今日轮次</span>
          <strong>{runtime.completed_cycles_today} 成功 / {runtime.failed_cycles_today} 失败</strong>
          <p>{runtime.last_error ?? "当前没有自动调度异常。"}</p>
        </article>
      </div>

      <div className="logs-split-layout">
        <LogStreamColumn title="system_runtime" description="服务启动、调度轮次、自动采集与自动成稿" items={runtimeLogs} />
        <LogStreamColumn title="business_event" description="来源保存、模式切换、手动采集、审核与发布尝试" items={businessLogs} />
      </div>
    </section>
  );
}
