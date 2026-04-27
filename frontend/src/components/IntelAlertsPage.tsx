import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { IntelAlert } from "../types";

const PAGE_SIZE = 20;

type FilterLevel = "all" | "breakout" | "rising" | "watch" | "cooling";

const FILTER_OPTIONS: Array<{ key: FilterLevel; label: string }> = [
  { key: "all", label: "全部" },
  { key: "breakout", label: "爆发" },
  { key: "rising", label: "上升" },
  { key: "watch", label: "关注" },
  { key: "cooling", label: "冷却" },
];

interface IntelAlertsPageProps {
  items: IntelAlert[];
}

export function IntelAlertsPage({ items }: IntelAlertsPageProps) {
  const [filter, setFilter] = useState<FilterLevel>("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const filtered = useMemo(() => {
    if (filter === "all") return items;
    return items.filter((alert) => alert.level === filter);
  }, [items, filter]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">预警台</p>
          <h2>预警台</h2>
        </div>
        <span className="subtle">{filtered.length} 条</span>
      </div>
      <div className="intel-filter-bar">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            type="button"
            className={`filter-chip ${filter === opt.key ? "filter-chip-active" : ""}`}
            onClick={() => { setFilter(opt.key); setVisibleCount(PAGE_SIZE); }}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="intel-list">
        {visible.length ? visible.map((alert) => (
          <article key={alert.id} className="intel-row-card">
            <div className="intel-card-topline">
              <span className={`status-badge status-${alert.level === "breakout" ? "danger" : alert.level === "rising" ? "warning" : alert.level === "watch" ? "success" : "neutral"}`}>
                {alert.level}
              </span>
              <span>{formatRelativeTime(alert.triggered_at, "刚刚")}</span>
            </div>
            <strong>{alert.title}</strong>
            <p>{alert.reason}</p>
            <div className="intel-score-row">
              <span>速度 {alert.velocity_score}</span>
              <span>覆盖 {alert.coverage_score}</span>
              <span>新鲜 {alert.freshness_score}</span>
              <span>{alert.platform_count} 平台</span>
            </div>
            <div className="intel-inline-actions">
              <span>{formatDateTime(alert.triggered_at, { fallback: "未知" })}</span>
              <a href={alert.representative_link} target="_blank" rel="noreferrer">查看原文</a>
            </div>
          </article>
        )) : <p className="empty-state">没有匹配的预警。</p>}
      </div>
      {hasMore ? (
        <div className="intel-load-more">
          <button type="button" className="ghost-button" onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}>
            加载更多 ({filtered.length - visibleCount} 条)
          </button>
        </div>
      ) : null}
    </section>
  );
}
