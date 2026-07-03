import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime, formatDurationMs } from "../../lib/time";
import type { SourceConnector } from "../../types";

interface SourceHealthScreenProps {
  sources: SourceConnector[];
  syncing: boolean;
  savingSourceKey?: string | null;
  syncingSourceKey?: string | null;
  onSyncSources: () => Promise<void>;
  onSyncSource: (sourceKey: string) => Promise<void>;
  onSaveSource: (sourceKey: string, payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">) => Promise<void>;
}

type StatusFilter = "all" | "healthy" | "warning" | "error" | "idle";
type Severity = Exclude<StatusFilter, "all">;

const STATUS_FILTERS: Array<{ key: StatusFilter; label: string }> = [
  { key: "all", label: "全部" },
  { key: "error", label: "异常" },
  { key: "warning", label: "告警" },
  { key: "healthy", label: "正常" },
  { key: "idle", label: "停用" },
];

const STAT_ITEMS: Array<{ key: Severity; label: string }> = [
  { key: "healthy", label: "正常" },
  { key: "warning", label: "告警" },
  { key: "error", label: "异常" },
  { key: "idle", label: "停用" },
];

const SEVERITY_ORDER: Record<Severity, number> = {
  error: 0,
  warning: 1,
  healthy: 2,
  idle: 3,
};

function sourceSeverity(source: SourceConnector): Severity {
  if (!source.enabled || source.health_status === "idle") return "idle";
  return source.health_status;
}

function healthLabel(source: SourceConnector) {
  const severity = sourceSeverity(source);
  if (severity === "healthy") return "正常";
  if (severity === "warning") return "告警";
  if (severity === "error") return "异常";
  return "停用";
}

function statusTone(severity: Severity) {
  if (severity === "healthy") return "success";
  if (severity === "warning") return "warning";
  if (severity === "error") return "danger";
  return "neutral";
}

function failureClass(source: SourceConnector) {
  if (source.consecutive_failures >= 3 || sourceSeverity(source) === "error") return "source-health-failure-count critical";
  if (source.consecutive_failures > 0 || sourceSeverity(source) === "warning") return "source-health-failure-count";
  return "source-health-failure-count";
}

export function SourceHealthPage({
  sources,
  syncing,
  savingSourceKey,
  syncingSourceKey,
  onSyncSources,
  onSyncSource,
  onSaveSource,
}: SourceHealthScreenProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [expandedSources, setExpandedSources] = useState<Set<string>>(() => new Set());

  const stats = useMemo(() => {
    return sources.reduce<Record<Severity, number>>(
      (acc, source) => {
        acc[sourceSeverity(source)] += 1;
        return acc;
      },
      { healthy: 0, warning: 0, error: 0, idle: 0 },
    );
  }, [sources]);

  const platformOptions = useMemo(() => {
    return Array.from(new Set(sources.map((source) => source.platform).filter(Boolean))).sort((a, b) => a.localeCompare(b, "zh-CN"));
  }, [sources]);

  const filteredSources = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    return sources
      .filter((source) => statusFilter === "all" || sourceSeverity(source) === statusFilter)
      .filter((source) => platformFilter === "all" || source.platform === platformFilter)
      .filter((source) => {
        if (!keyword) return true;
        return (
          source.name.toLowerCase().includes(keyword)
          || source.platform.toLowerCase().includes(keyword)
          || source.key.toLowerCase().includes(keyword)
        );
      })
      .sort((left, right) => {
        const severityDiff = SEVERITY_ORDER[sourceSeverity(left)] - SEVERITY_ORDER[sourceSeverity(right)];
        if (severityDiff !== 0) return severityDiff;
        return left.name.localeCompare(right.name, "zh-CN");
      });
  }, [platformFilter, searchTerm, sources, statusFilter]);

  function toggleExpanded(key: string) {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleStatFilter(key: Severity) {
    setStatusFilter((current) => current === key ? "all" : key);
  }

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">来源健康</p>
          <h2>数据源状态监控</h2>
        </div>
        <button type="button" className="ghost-button compact" disabled={syncing} onClick={() => void onSyncSources()}>
          {syncing ? "重新抓取中..." : "全部重新抓取"}
        </button>
      </div>

      <div className="source-health-stats">
        {STAT_ITEMS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`source-health-stat stat-${item.key} ${statusFilter === item.key ? `source-health-stat-active stat-${item.key}` : ""}`}
            aria-label={`${item.label} ${stats[item.key]} 个`}
            onClick={() => toggleStatFilter(item.key)}
          >
            <span className="source-health-stat-value">{stats[item.key]}</span>
            <span className="source-health-stat-label">{item.label}</span>
          </button>
        ))}
      </div>

      <div className="source-health-filter-bar">
        <div className="intel-chip-row">
          {STATUS_FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`filter-chip compact ${statusFilter === item.key ? "filter-chip-active" : ""}`}
              onClick={() => setStatusFilter(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="source-health-filter-tools">
          <label>
            <span className="sr-only">平台筛选</span>
            <select aria-label="平台筛选" value={platformFilter} onChange={(event) => setPlatformFilter(event.target.value)}>
              <option value="all">全部平台</option>
              {platformOptions.map((platform) => (
                <option key={platform} value={platform}>{platform}</option>
              ))}
            </select>
          </label>
          <input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="搜索来源名称或平台"
          />
        </div>
      </div>

      {filteredSources.length ? (
        <div className="source-health-grid">
          {filteredSources.map((source) => {
            const severity = sourceSeverity(source);
            const expanded = expandedSources.has(source.key);
            return (
              <article key={source.key} className={`source-health-card severity-${severity}`}>
                <div className="intel-card-topline">
                  <span className={`status-badge status-${statusTone(severity)} status-badge-compact`}>
                    {healthLabel(source)}
                  </span>
                  <span>{source.platform} / 权重 {source.weight}</span>
                </div>

                <strong>{source.name}</strong>

                <div className="source-health-metrics">
                  <span className={failureClass(source)}>失败 {source.consecutive_failures} 次</span>
                  <span>上次成功 {formatRelativeTime(source.last_success_at ?? source.last_synced_at, "从未成功")}</span>
                  <span>耗时 {formatDurationMs(source.last_duration_ms)}</span>
                  <span>累计 {source.item_count} 条</span>
                </div>

                <button type="button" className="source-health-expand" onClick={() => toggleExpanded(source.key)}>
                  {expanded ? "收起详情 ▲" : "查看详情 ▼"}
                </button>

                {expanded ? (
                  <div className="source-health-detail">
                    <div className="source-health-metrics">
                      <span>最近尝试 {formatDateTime(source.last_attempt_at, { fallback: "暂无" })}</span>
                      <span>最近成功 {formatDateTime(source.last_success_at, { fallback: "暂无" })}</span>
                      <span>最近失败 {formatDateTime(source.last_failure_at, { fallback: "暂无" })}</span>
                      <span>平均耗时 {formatDurationMs(source.avg_duration_ms)}</span>
                      <span>最近条数 {source.last_item_count}</span>
                    </div>
                    {source.health_detail ? (
                      <pre className="source-health-error-text">{source.health_detail}</pre>
                    ) : null}
                  </div>
                ) : null}

                <div className="source-health-actions">
                  <button
                    type="button"
                    className="ghost-button compact"
                    disabled={syncingSourceKey === source.key}
                    onClick={() => void onSyncSource(source.key)}
                  >
                    {syncingSourceKey === source.key ? "重新抓取中..." : "重新抓取"}
                  </button>
                  <button
                    type="button"
                    className="ghost-button compact"
                    disabled={savingSourceKey === source.key}
                    onClick={() => void onSaveSource(source.key, {
                      enabled: !source.enabled,
                      schedule: source.schedule,
                      priority: source.priority,
                      url: source.url,
                      tags: source.tags,
                    })}
                  >
                    {savingSourceKey === source.key ? "保存中..." : source.enabled ? "停用" : "启用"}
                  </button>
                  {source.url ? <a href={source.url} target="_blank" rel="noreferrer">打开来源</a> : null}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="empty-state">
          {sources.length ? "当前筛选条件下没有匹配的数据源。" : "还没有配置数据源。"}
        </p>
      )}
    </section>
  );
}
