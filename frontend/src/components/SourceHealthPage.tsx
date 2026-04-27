import { formatDateTime, formatRelativeTime } from "../lib/time";
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
      <div className="intel-list">
        {sources.length ? sources.map((source) => (
          <article key={source.key} className="intel-row-card">
            <div className="intel-card-topline">
              <span className={`status-badge status-${source.health_status === "healthy" ? "success" : source.health_status === "warning" ? "warning" : source.health_status === "error" ? "danger" : "neutral"}`}>
                {source.health_status}
              </span>
              <span>{source.platform} / 权重 {source.weight}</span>
            </div>
            <strong>{source.name}</strong>
            <p>{source.health_detail || "尚未同步"}</p>
            <div className="intel-score-row">
              <span>{source.item_count} 条素材</span>
              <span>{formatDateTime(source.last_synced_at, { fallback: "从未同步" })}</span>
              <span>{formatRelativeTime(source.last_synced_at, "从未同步")}</span>
            </div>
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
