import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { IntelEvent } from "../types";

const PAGE_SIZE = 20;

type SortKey = "composite_score" | "velocity_score" | "coverage_score" | "freshness_score";

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: "composite_score", label: "总分" },
  { key: "velocity_score", label: "速度" },
  { key: "coverage_score", label: "覆盖" },
  { key: "freshness_score", label: "新鲜" },
];

interface IntelEventsPageProps {
  items: IntelEvent[];
  onWatchEvent: (eventId: string) => Promise<void>;
  onIgnoreEvent: (eventId: string) => Promise<void>;
}

export function IntelEventsPage({ items, onWatchEvent, onIgnoreEvent }: IntelEventsPageProps) {
  const [sortBy, setSortBy] = useState<SortKey>("composite_score");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const sorted = useMemo(() => {
    return [...items].sort((a, b) => (b[sortBy] ?? 0) - (a[sortBy] ?? 0));
  }, [items, sortBy]);

  const visible = sorted.slice(0, visibleCount);
  const hasMore = visibleCount < sorted.length;

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">热点簇</p>
          <h2>热点簇</h2>
        </div>
        <span className="subtle">{sorted.length} 个事件</span>
      </div>
      <div className="intel-filter-bar">
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            type="button"
            className={`filter-chip ${sortBy === opt.key ? "filter-chip-active" : ""}`}
            onClick={() => { setSortBy(opt.key); setVisibleCount(PAGE_SIZE); }}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="intel-list">
        {visible.length ? visible.map((event) => (
          <article key={event.id} className="intel-row-card">
            <div className="intel-card-topline">
              <span className={`status-badge status-${event.alert_state === "breakout" ? "danger" : event.alert_state === "rising" ? "warning" : event.alert_state === "watch" ? "success" : "neutral"}`}>
                {event.alert_state}
              </span>
              <span>{event.platform_count} 平台 / {event.source_count} 来源 / {event.member_count} 条素材</span>
            </div>
            <strong>{event.title}</strong>
            <p>{event.summary}</p>
            <div className="intel-score-row">
              <span>总分 {event.composite_score}</span>
              <span>速度 {event.velocity_score}</span>
              <span>覆盖 {event.coverage_score}</span>
              <span>新鲜 {event.freshness_score}</span>
              <span>{formatRelativeTime(event.latest_collected_at, "刚抓到")}</span>
            </div>
            <div className="intel-score-row">
              <span>首次 {formatDateTime(event.first_seen_at, { fallback: "未知" })}</span>
              <span>最近 {formatDateTime(event.last_seen_at, { fallback: "未知" })}</span>
            </div>
            <div className="intel-inline-actions">
              <a href={event.representative_link} target="_blank" rel="noreferrer">查看原文</a>
              <button type="button" className="ghost-button compact" disabled={event.watchlisted} onClick={() => void onWatchEvent(event.id)}>
                {event.watchlisted ? "已观察" : "观察"}
              </button>
              <button type="button" className="ghost-button compact" onClick={() => void onIgnoreEvent(event.id)}>
                忽略
              </button>
            </div>
          </article>
        )) : <p className="empty-state">还没有形成热点簇。</p>}
      </div>
      {hasMore ? (
        <div className="intel-load-more">
          <button type="button" className="ghost-button" onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}>
            加载更多 ({sorted.length - visibleCount} 个)
          </button>
        </div>
      ) : null}
    </section>
  );
}
