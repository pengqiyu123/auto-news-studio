import { useMemo, useState } from "react";

import { EntityWatchlistPanel } from "./EntityWatchlistPanel";
import { explainEventsEmptyState } from "../lib/runtimeIntent";
import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { EntityWatchlistItem, EntityWatchlistSummaryItem, IntelEvent, SchedulerStatus } from "../types";

const PAGE_SIZE = 20;

type SortKey = "composite_score" | "velocity_score" | "coverage_score" | "freshness_score";
type ExtendedSortKey = SortKey | "member_delta" | "platform_delta" | "latest_seen";

const SORT_OPTIONS: Array<{ key: ExtendedSortKey; label: string }> = [
  { key: "composite_score", label: "总分" },
  { key: "velocity_score", label: "速度" },
  { key: "coverage_score", label: "覆盖" },
  { key: "freshness_score", label: "新鲜" },
  { key: "member_delta", label: "成员增量" },
  { key: "platform_delta", label: "平台增量" },
  { key: "latest_seen", label: "最新出现" },
];

interface IntelEventsPageProps {
  items: IntelEvent[];
  runtime: SchedulerStatus;
  entityWatchlist: EntityWatchlistItem[];
  entityWatchlistSummary: EntityWatchlistSummaryItem[];
  selectedEntityId: string;
  onSelectedEntityChange: (entityId: string) => void;
  onUpdateEntityWatchlist: (items: EntityWatchlistItem[]) => Promise<void>;
  onOpenEntity: (entityId: string) => void;
  onWatchEvent: (eventId: string) => Promise<void>;
  onIgnoreEvent: (eventId: string) => Promise<void>;
}

export function IntelEventsPage({
  items,
  runtime,
  entityWatchlist,
  entityWatchlistSummary,
  selectedEntityId,
  onSelectedEntityChange,
  onUpdateEntityWatchlist,
  onOpenEntity,
  onWatchEvent,
  onIgnoreEvent,
}: IntelEventsPageProps) {
  const [sortBy, setSortBy] = useState<ExtendedSortKey>("composite_score");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const entityOptions = useMemo(() => {
    const lookup = new Map<string, { entity_id: string; entity_name: string }>();
    for (const event of items) {
      event.entity_ids.forEach((entityId, index) => {
        const entityName = event.entity_names[index];
        if (!entityId || !entityName || lookup.has(entityId)) return;
        lookup.set(entityId, { entity_id: entityId, entity_name: entityName });
      });
    }
    for (const item of entityWatchlist) {
      if (!item.entity_id || !item.entity_name || lookup.has(item.entity_id)) continue;
      lookup.set(item.entity_id, { entity_id: item.entity_id, entity_name: item.entity_name });
    }
    return [...lookup.values()].sort((a, b) => a.entity_name.localeCompare(b.entity_name, "zh-CN"));
  }, [entityWatchlist, items]);

  const filtered = useMemo(() => {
    if (selectedEntityId === "all") return items;
    return items.filter((item) => item.entity_ids.includes(selectedEntityId));
  }, [items, selectedEntityId]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      if (sortBy === "latest_seen") {
        const left = Date.parse(a.last_seen_at ?? a.latest_collected_at ?? a.first_seen_at ?? "") || 0;
        const right = Date.parse(b.last_seen_at ?? b.latest_collected_at ?? b.first_seen_at ?? "") || 0;
        return right - left;
      }
      return (b[sortBy] ?? 0) - (a[sortBy] ?? 0);
    });
  }, [filtered, sortBy]);

  const visible = sorted.slice(0, visibleCount);
  const hasMore = visibleCount < sorted.length;

  return (
    <div className="intel-page-with-sidepanel">
      <section className="panel">
        <div className="panel-header compact">
          <div>
            <p className="eyebrow">热点簇</p>
            <h2>已聚合的热点事件</h2>
          </div>
          <span className="subtle">{sorted.length} 个事件</span>
        </div>
        <div className="intel-chip-filter-bar">
          <div className="intel-chip-row">
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
          <div className="intel-inline-filter-tools">
            <select
              value={selectedEntityId}
              onChange={(event) => {
                onSelectedEntityChange(event.target.value);
                setVisibleCount(PAGE_SIZE);
              }}
            >
              <option value="all">全部实体</option>
              {entityOptions.map((item) => (
                <option key={item.entity_id} value={item.entity_id}>
                  {item.entity_name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="intel-list">
          {visible.length ? visible.map((event) => {
            const visibleTags = event.entity_names.slice(0, 3);
            const hiddenTagCount = Math.max(event.entity_names.length - visibleTags.length, 0);
            return (
              <article key={event.id} className="intel-row-card">
                <div className="intel-card-topline">
                  <span className={`status-badge status-${event.alert_state === "breakout" ? "danger" : event.alert_state === "rising" ? "warning" : event.alert_state === "watch" ? "success" : "neutral"}`}>
                    {event.alert_state}
                  </span>
                  <span>{event.platform_count} 平台 / {event.source_count} 来源 / {event.member_count} 条素材</span>
                </div>
                <strong>{event.title}</strong>
                <p>{event.summary}</p>
                {event.summary_translated ? (
                  <p className="intel-translation">译：{event.summary_translated}</p>
                ) : null}
                {visibleTags.length ? (
                  <div className="entity-tag-row">
                    {visibleTags.map((name, index) => (
                      <button
                        key={`${event.id}-${name}`}
                        type="button"
                        className={`entity-tag ${event.entity_ids[index] === selectedEntityId ? "entity-tag-active" : ""}`}
                        onClick={() => onSelectedEntityChange(event.entity_ids[index] ?? "all")}
                      >
                        {name}
                      </button>
                    ))}
                    {hiddenTagCount ? <span className="entity-tag entity-tag-muted">+{hiddenTagCount}</span> : null}
                  </div>
                ) : null}
                <div className="intel-score-row">
                  <span>总分 {event.composite_score}</span>
                  <span>速度 {event.velocity_score}</span>
                  <span>覆盖 {event.coverage_score}</span>
                  <span>新鲜 {event.freshness_score}</span>
                  <span>{formatRelativeTime(event.latest_collected_at, "刚抓到")}</span>
                </div>
                <div className="intel-score-row">
                  <span>成员增量 {event.member_delta >= 0 ? `+${event.member_delta}` : event.member_delta}</span>
                  <span>平台增量 {event.platform_delta >= 0 ? `+${event.platform_delta}` : event.platform_delta}</span>
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
            );
          }) : <p className="empty-state">{selectedEntityId !== "all" ? "当前筛选条件下没有匹配的热点事件。" : explainEventsEmptyState(runtime)}</p>}
        </div>
        {hasMore ? (
          <div className="intel-load-more">
            <button type="button" className="ghost-button" onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}>
              加载更多 ({sorted.length - visibleCount} 个)
            </button>
          </div>
        ) : null}
      </section>

      <EntityWatchlistPanel
        items={entityWatchlist}
        summary={entityWatchlistSummary}
        availableEntities={entityOptions}
        selectedEntityId={selectedEntityId}
        onSelectEntity={onSelectedEntityChange}
        onUpdateWatchlist={onUpdateEntityWatchlist}
        onOpenEntity={onOpenEntity}
      />
    </div>
  );
}
