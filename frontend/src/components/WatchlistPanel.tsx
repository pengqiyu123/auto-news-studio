import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { IntelEvent } from "../types";

interface WatchlistPanelProps {
  items: IntelEvent[];
  busyEventId?: string | null;
  onCreateDraft: (eventId: string) => Promise<void>;
}

export function WatchlistPanel({ items, busyEventId, onCreateDraft }: WatchlistPanelProps) {
  const readyItems = items.filter((item) => item.draft_ready);
  const weakItems = items.filter((item) => !item.draft_ready);
  const draftedItems = items.filter((item) => item.draft_exists);

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">选题池</p>
          <h2>值得继续跟进、等待进入稿件生产的事件</h2>
        </div>
        <span className="subtle">{items.length} 个已观察事件</span>
      </div>
      <div className="intel-score-row" style={{ marginBottom: 12 }}>
        <span>证据充分 {readyItems.length}</span>
        <span>证据较弱 {weakItems.length}</span>
        <span>已生成稿件 {draftedItems.length}</span>
      </div>
      <div className="intel-list">
        {items.length ? items.map((event) => {
          const strong = event.draft_ready;
          const visibleTags = event.entity_names.slice(0, 3);
          const hiddenTagCount = Math.max(event.entity_names.length - visibleTags.length, 0);
          return (
          <article key={event.id} className="intel-row-card">
            <div className="intel-card-topline">
              <span className={`status-badge status-${strong ? "success" : "warning"}`}>{strong ? "证据充分" : "证据较弱"}</span>
              <span>{event.platform_count} 平台 / {event.source_count} 来源 / {event.member_count} 条素材</span>
            </div>
            <strong>{event.title}</strong>
            <p>{event.summary}</p>
            <div className="intel-score-row">
              <span>{event.alert_state}</span>
              <span>写稿分 {event.draft_score.toFixed(1)}</span>
              <span>{formatDateTime(event.published_at, { fallback: "发布时间未知" })}</span>
              <span>{formatRelativeTime(event.latest_collected_at, "刚抓到")}</span>
            </div>
            <p className="subtle">{event.draft_reason}</p>
            {visibleTags.length ? (
              <div className="entity-tag-row">
                {visibleTags.map((name) => (
                  <span key={`${event.id}-${name}`} className="entity-tag">
                    {name}
                  </span>
                ))}
                {hiddenTagCount ? <span className="entity-tag entity-tag-muted">+{hiddenTagCount}</span> : null}
              </div>
            ) : null}
            <div className="intel-inline-actions">
              {event.representative_link ? <a href={event.representative_link} target="_blank" rel="noreferrer">查看证据</a> : null}
              <button
                type="button"
                className="primary-button"
                disabled={busyEventId === event.id || event.draft_exists}
                onClick={() => void onCreateDraft(event.id)}
              >
                {busyEventId === event.id ? "生成中..." : event.draft_exists ? "已生成稿件" : "生成稿件"}
              </button>
            </div>
          </article>
        );
        }) : <p className="empty-state">还没有加入选题池的事件，先去热点簇把值得跟进的事件加入观察。</p>}
      </div>
    </section>
  );
}
