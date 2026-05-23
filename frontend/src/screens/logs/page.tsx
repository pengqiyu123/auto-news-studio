import { ChevronDown, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { formatDateTime, formatDuration } from "../../lib/time";
import { formatRuntimeIssueLabel } from "../../lib/runtimeUtils";
import type { LogItem, SchedulerStatus } from "../../types";
import { PaginationControls } from "../../components/PaginationControls";

interface LogsPageProps {
  logs: LogItem[];
  page: number;
  pageSize: number;
  total: number;
  levelFilter: "all" | "info" | "warning" | "error";
  searchQuery: string;
  loading?: boolean;
  runtime: SchedulerStatus;
  onLevelFilterChange: (value: "all" | "info" | "warning" | "error") => void;
  onSearchChange: (value: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

type SourceLogGroup = {
  key: string;
  label: string;
  logs: LogItem[];
};

function renderLogRow(log: LogItem) {
  const actorLabel = log.actor === "agent" ? "Agent" : log.actor;
  const actorTone = log.actor === "agent" ? "log-actor-agent" : "";
  return (
    <div key={log.id} className={`log-plain-row log-plain-${log.level} ${log.actor === "agent" ? "log-plain-agent" : ""}`}>
      <span className="log-plain-time">{formatDateTime(log.created_at, { fallback: "--:--" })}</span>
      <span className="log-plain-level">{log.level}</span>
      <span className="log-plain-cat">{log.category}</span>
      <div className="log-plain-body">
        <span className="log-plain-msg">{log.message}</span>
        <span className="log-plain-meta">
          {log.stream} / <strong className={actorTone}>{actorLabel}</strong>
        </span>
        {log.detail ? <pre className="log-plain-detail">{log.detail}</pre> : null}
      </div>
    </div>
  );
}

export function LogsPage({
  logs,
  page,
  pageSize,
  total,
  levelFilter,
  searchQuery,
  loading = false,
  runtime,
  onLevelFilterChange,
  onSearchChange,
  onPageChange,
  onPageSizeChange,
}: LogsPageProps) {
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [sourceSummaryCollapsed, setSourceSummaryCollapsed] = useState(true);
  const systemLogListRef = useRef<HTMLDivElement>(null);

  const filteredLogs = useMemo(() => {
    return [...logs].sort((a, b) => {
        const ta = a.created_at ?? "";
        const tb = b.created_at ?? "";
        return ta < tb ? 1 : ta > tb ? -1 : 0;
      });
  }, [logs]);

  const sourceLogGroups = useMemo<SourceLogGroup[]>(() => {
    const grouped = new Map<string, SourceLogGroup>();
    for (const log of filteredLogs) {
      const isSourceLog =
        log.category === "collection" || log.category === "source";
      if (!isSourceLog) {
        continue;
      }
      let label = "信息源运行";
      const matchedSource = log.message.match(/来源[《\s]?([^》，。,:\s]+)/);
      if (matchedSource?.[1]) {
        label = `来源：${matchedSource[1]}`;
      } else if (log.category === "source") {
        label = "来源配置";
      } else if (log.category === "collection") {
        label = "来源采集";
      }
      const key = label;
      const current = grouped.get(key) ?? { key, label, logs: [] };
      current.logs.push(log);
      grouped.set(key, current);
    }
    return [...grouped.values()].sort((a, b) => {
      const aTime = a.logs[0]?.created_at ?? "";
      const bTime = b.logs[0]?.created_at ?? "";
      return aTime < bTime ? 1 : aTime > bTime ? -1 : 0;
    });
  }, [filteredLogs]);

  const systemLogs = useMemo(() => {
    const sourceLogIds = new Set(sourceLogGroups.flatMap((group) => group.logs.map((log) => log.id)));
    return filteredLogs.filter((log) => !sourceLogIds.has(log.id));
  }, [filteredLogs, sourceLogGroups]);

  useEffect(() => {
    setCollapsedGroups((current) => {
      const next = { ...current };
      for (const group of sourceLogGroups) {
        if (!(group.key in next)) {
          next[group.key] = true;
        }
      }
      return next;
    });
  }, [sourceLogGroups]);

  useEffect(() => {
    if (systemLogListRef.current) {
      systemLogListRef.current.scrollTop = 0;
    }
  }, [systemLogs]);

  const cycleSummary = runtime.last_cycle_summary ?? null;

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">日志</p>
          <h2>运行日志</h2>
        </div>
      </div>

      <div className="intel-chip-filter-bar">
        <div className="intel-chip-row">
          {(["all", "info", "warning", "error"] as const).map((level) => (
            <button
              key={level}
              type="button"
              className={`filter-chip ${levelFilter === level ? "filter-chip-active" : ""}`}
              onClick={() => onLevelFilterChange(level)}
            >
              {level === "all" ? "全部" : level}
            </button>
          ))}
        </div>
      </div>
      <div className="draft-toolbar">
        <label className="draft-search">
          <input
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜索日志内容"
          />
        </label>
      </div>

      <PaginationControls
        page={page}
        pageSize={pageSize}
        total={total}
        currentCount={filteredLogs.length}
        itemLabel="条日志"
        loading={loading}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />

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
          <button
            type="button"
            className="logs-group-toggle logs-summary-toggle"
            onClick={() => setSourceSummaryCollapsed((value) => !value)}
          >
            <span className="logs-group-title">
              {sourceSummaryCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
              <strong>信息源摘要</strong>
            </span>
            <span className="subtle">
              成功 {cycleSummary.success_source_count} / 失败 {cycleSummary.failed_source_count}
            </span>
          </button>
          {!sourceSummaryCollapsed ? (
            <>
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
            </>
          ) : (
            null
          )}
        </section>
      ) : null}

      <section className="logs-section">
        <div className="logs-section-head">
          <div>
            <p className="eyebrow">信息源日志</p>
            <h3>来源运行记录</h3>
          </div>
        </div>
        {sourceLogGroups.length ? (
          <div className="logs-accordion">
            {sourceLogGroups.map((group) => {
              const collapsed = collapsedGroups[group.key] ?? false;
              return (
                <article key={group.key} className="logs-group-card">
                  <button
                    type="button"
                    className="logs-group-toggle"
                    onClick={() => setCollapsedGroups((current) => ({ ...current, [group.key]: !collapsed }))}
                  >
                    <span className="logs-group-title">
                      {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                      <strong>{group.label}</strong>
                    </span>
                    <span className="subtle">{group.logs.length} 条</span>
                  </button>
                  {!collapsed ? <div className="log-plain-list">{group.logs.map(renderLogRow)}</div> : null}
                </article>
              );
            })}
          </div>
        ) : (
          <p className="empty-state">暂无信息源相关日志。</p>
        )}
      </section>

      <section className="logs-section">
        <div className="logs-section-head">
          <div>
            <p className="eyebrow">系统日志</p>
            <h3>系统与交付异常</h3>
          </div>
        </div>
        <div ref={systemLogListRef} className="log-plain-list">
          {systemLogs.map(renderLogRow)}
          {!systemLogs.length ? <p className="empty-state">暂无系统日志。</p> : null}
        </div>
      </section>
    </section>
  );
}
