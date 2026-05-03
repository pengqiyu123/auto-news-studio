import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime, formatDurationMs } from "../lib/time";
import type { SourceConnector } from "../types";

interface SourceHealthPageProps {
  sources: SourceConnector[];
  syncing: boolean;
  savingSourceKey?: string | null;
  syncingSourceKey?: string | null;
  onSyncSources: () => Promise<void>;
  onSyncSource: (sourceKey: string) => Promise<void>;
  onSaveSource: (sourceKey: string, payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">) => Promise<void>;
}

export function SourceHealthPage({
  sources,
  syncing,
  savingSourceKey,
  syncingSourceKey,
  onSyncSources,
  onSyncSource,
  onSaveSource,
}: SourceHealthPageProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedSources, setExpandedSources] = useState<Set<string>>(() => {
    // Warning/error sources are expanded by default
    const initial = new Set<string>();
    for (const s of sources) {
      if (s.health_status === "warning" || s.health_status === "error") {
        initial.add(s.key);
      }
    }
    return initial;
  });

  const toggleExpanded = (key: string) => {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };
  function healthLabel(source: SourceConnector) {
    if (!source.enabled || source.health_status === "idle") return "停用";
    if (source.health_status === "healthy") return "正常";
    if (source.health_status === "warning") return "告警";
    return "异常";
  }

  const filteredSources = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) return sources;
    return sources.filter((s) =>
      s.name.toLowerCase().includes(keyword) || s.platform.toLowerCase().includes(keyword)
    );
  }, [sources, searchTerm]);

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">来源健康</p>
          <h2>哪里坏了</h2>
        </div>
        <button type="button" className="ghost-button compact" disabled={syncing} onClick={() => void onSyncSources()}>
          {syncing ? "补抓中..." : "全部补抓一次"}
        </button>
      </div>
      <div className="draft-toolbar">
        <label className="draft-search">
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="搜索来源名称或平台"
          />
        </label>
      </div>
      <div className="intel-list">
        {filteredSources.length ? filteredSources.map((source) => (
          <article key={source.key} className="intel-row-card">
            <div className="intel-card-topline">
              <span className={`status-badge status-${source.health_status === "healthy" ? "success" : source.health_status === "warning" ? "warning" : source.health_status === "error" ? "danger" : "neutral"}`}>
                {healthLabel(source)}
              </span>
              <span>{source.platform} / 权重 {source.weight}</span>
            </div>
            <strong>{source.name}</strong>
            <p>{source.health_detail || "尚未同步"}</p>
            <button type="button" className="ghost-button compact" onClick={() => toggleExpanded(source.key)} style={{ marginTop: 4 }}>
              {expandedSources.has(source.key) ? "收起详情" : "展开详情"}
            </button>
            {expandedSources.has(source.key) ? (
              <>
            <div className="intel-score-row">
              <span>最近成功 {formatRelativeTime(source.last_success_at ?? source.last_synced_at, "从未成功")}</span>
              <span>连续失败 {source.consecutive_failures}</span>
              <span>最近 {formatDurationMs(source.last_duration_ms)}</span>
            </div>
            <div className="intel-score-row">
              <span>平均 {formatDurationMs(source.avg_duration_ms)}</span>
              <span>最近条数 {source.last_item_count}</span>
              <span>累计素材 {source.item_count}</span>
            </div>
            <div className="intel-score-row">
              <span>最近成功 {formatDateTime(source.last_success_at, { fallback: "暂无" })}</span>
              <span>最近失败 {formatDateTime(source.last_failure_at, { fallback: "暂无" })}</span>
              <span>最近尝试 {formatDateTime(source.last_attempt_at, { fallback: "暂无" })}</span>
            </div>
              </>
            ) : null}
            <div className="intel-inline-actions">
              <button
                type="button"
                className="ghost-button compact"
                disabled={syncingSourceKey === source.key}
                onClick={() => void onSyncSource(source.key)}
              >
                {syncingSourceKey === source.key ? "补抓中..." : "补抓"}
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
        )) : <p className="empty-state">还没有可用来源。</p>}
      </div>
    </section>
  );
}
