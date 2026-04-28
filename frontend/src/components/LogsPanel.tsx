import { formatDateTime, formatDuration } from "../lib/time";
import type { LogItem, SchedulerStatus } from "../types";

interface LogsPanelProps {
  logs: LogItem[];
  runtime: SchedulerStatus;
}

function formatRuntimeIssueLabel(sourceName: string | null | undefined, message: string) {
  return `${sourceName?.trim() ? `${sourceName}: ` : "系统异常："}${message}`;
}

export function LogsPanel({ logs, runtime }: LogsPanelProps) {
  const sortedLogs = [...logs].sort((a, b) => {
    const ta = a.created_at ?? "";
    const tb = b.created_at ?? "";
    return tb > ta ? 1 : tb < ta ? -1 : 0;
  });
  const cycleSummary = runtime.last_cycle_summary ?? null;

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">日志</p>
          <h2>运行日志</h2>
        </div>
      </div>

      <div className="runtime-card-grid">
        <div className="runtime-card">
          <span>状态</span>
          <strong>{runtime.running ? runtime.current_cycle : "已停止"}</strong>
          <p>
            {runtime.current_cycle_progress_label
              ? runtime.current_cycle_progress_label
              : `上轮耗时 ${formatDuration(runtime.last_cycle_duration_seconds, "暂无")}`}
          </p>
        </div>
        <div className="runtime-card">
          <span>今日</span>
          <strong>{runtime.completed_cycles_today} 成功 / {runtime.failed_cycles_today} 失败</strong>
          <p>{runtime.last_error ?? "无异常"}</p>
        </div>
      </div>

      {cycleSummary ? (
        <section className="intel-runtime-section">
          <div className="intel-score-row">
            <span>成功来源 {cycleSummary.success_source_count}</span>
            <span>失败来源 {cycleSummary.failed_source_count}</span>
            <span>新增素材 {cycleSummary.new_items_count}</span>
            <span>新事件 {cycleSummary.new_events_count}</span>
          </div>
          {cycleSummary.issues.length ? (
            <ul className="intel-runtime-issues compact">
              {cycleSummary.issues.map((item, index) => (
                <li key={`${item.source_key ?? "runtime"}-${index}`}>
                  {formatRuntimeIssueLabel(item.source_name, item.message)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="subtle">最近一轮没有记录到异常。</p>
          )}
        </section>
      ) : null}

      <div className="log-plain-list">
        {sortedLogs.map((log) => (
          <div key={log.id} className={`log-plain-row log-plain-${log.level}`}>
            <span className="log-plain-time">{formatDateTime(log.created_at, { fallback: "--:--" })}</span>
            <span className="log-plain-level">{log.level}</span>
            <span className="log-plain-cat">{log.category}</span>
            <div className="log-plain-body">
              <span className="log-plain-msg">{log.message}</span>
              <span className="log-plain-meta">{log.stream} / {log.actor}</span>
              {log.detail ? <pre className="log-plain-detail">{log.detail}</pre> : null}
            </div>
          </div>
        ))}
        {!sortedLogs.length ? <p className="empty-state">暂无日志。</p> : null}
      </div>
    </section>
  );
}
