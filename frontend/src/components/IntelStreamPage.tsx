import { Search } from "lucide-react";
import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { DiscoveryItem } from "../types";

const PAGE_SIZE = 20;

interface IntelStreamPageProps {
  items: DiscoveryItem[];
}

export function IntelStreamPage({ items }: IntelStreamPageProps) {
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const filtered = useMemo(() => {
    if (!query.trim()) return items;
    const q = query.toLowerCase();
    return items.filter(
      (item) =>
        (item.title ?? "").toLowerCase().includes(q) ||
        (item.source_name ?? "").toLowerCase().includes(q) ||
        (item.platform ?? "").toLowerCase().includes(q),
    );
  }, [items, query]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">实时流</p>
          <h2>实时流</h2>
        </div>
        <span className="subtle">{filtered.length} 条</span>
      </div>
      <div className="intel-filter-bar">
        <Search size={14} />
        <input
          type="text"
          placeholder="搜索标题、来源、平台..."
          value={query}
          onChange={(e) => { setQuery(e.target.value); setVisibleCount(PAGE_SIZE); }}
        />
      </div>
      <div className="intel-list">
        {visible.length ? visible.map((item) => (
          <article key={item.id} className="intel-row-card">
            <div className="intel-card-topline">
              <span>{item.source_name}</span>
              <span>{formatRelativeTime(item.collected_at, "刚刚")}</span>
            </div>
            <strong>{item.title}</strong>
            <p>{item.summary}</p>
            <div className="intel-score-row">
              <span>{item.platform}</span>
              <span>{formatDateTime(item.published_at, { fallback: "发布时间未知" })}</span>
              <span>热度 {item.engagement_score}</span>
            </div>
            <a href={item.link} target="_blank" rel="noreferrer">查看原文</a>
          </article>
        )) : <p className="empty-state">没有匹配的素材。</p>}
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
