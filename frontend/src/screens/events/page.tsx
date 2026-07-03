import { useEffect, useMemo, useState } from "react";

import { PaginationControls } from "../../components/PaginationControls";
import { api } from "../../lib/api";
import { explainEventsEmptyState } from "../../lib/runtimeIntent";
import { historyStatusLabel, historyStatusTone } from "../../lib/eventUtils";
import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type { EntityWatchlistItem, EntityWatchlistSummaryItem, EventRelationInfo, HistoryRecordStatus, IntelEvent, IntelEventHistoryItem, SchedulerStatus, TrendSignalInfo } from "../../types";
import { EntityWatchlistPanel } from "./entity_watchlist_panel";
import type { EventsFilters } from "./state";

const PAGE_SIZE = 20;

type SortKey = "composite_score" | "velocity_score" | "coverage_score" | "freshness_score";
type ExtendedSortKey = SortKey | "member_delta" | "platform_delta" | "latest_seen";

const PRIMARY_SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: "composite_score", label: "总分" },
  { key: "velocity_score", label: "速度" },
  { key: "coverage_score", label: "覆盖" },
  { key: "freshness_score", label: "新鲜" },
];

const EXTENDED_SORT_OPTIONS: Array<{ key: ExtendedSortKey; label: string }> = [
  { key: "member_delta", label: "成员增量" },
  { key: "platform_delta", label: "平台增量" },
  { key: "latest_seen", label: "最新出现" },
];

function eventsFiltersEqual(left: EventsFilters, right: EventsFilters) {
  return (
    left.entity_id === right.entity_id &&
    left.event_id === right.event_id &&
    left.sort_by === right.sort_by &&
    left.ignore_mode === right.ignore_mode
  );
}

function severityForHistory(status: HistoryRecordStatus) {
  if (status === "active") return "watch";
  if (status === "cooled") return "cooling";
  return "new";
}

function relationTypeLabel(relationType: string) {
  if (relationType === "entity_shared") return "实体重合";
  if (relationType === "topic_shared") return "主题同类";
  if (relationType === "temporal_proximity") return "时间接近";
  if (relationType === "anchor_overlap") return "锚点重合";
  return relationType || "关联";
}

interface EventsPageProps {
  items: IntelEvent[];
  page: number;
  pageSize: number;
  total: number;
  historyItems: IntelEventHistoryItem[];
  runtime: SchedulerStatus;
  entityWatchlist: EntityWatchlistItem[];
  entityWatchlistSummary: EntityWatchlistSummaryItem[];
  trends?: TrendSignalInfo[];
  selectedEntityId: string;
  onSelectedEntityChange: (entityId: string) => void;
  onFilterChange: (filters: EventsFilters) => void;
  onUpdateEntityWatchlist: (items: EntityWatchlistItem[]) => Promise<void>;
  onOpenEntity: (entityId: string) => void;
  onWatchEvent: (eventId: string) => Promise<void>;
  onIgnoreEvent: (eventId: string) => Promise<void>;
  onDeepDive: (eventId: string) => Promise<void>;
  onNavigateToAlerts?: (eventId: string) => void;
  highlightEventId?: string;
  busyEventId?: string | null;
  loading?: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export function EventsPage({
  items,
  page,
  pageSize,
  total,
  historyItems,
  runtime,
  entityWatchlist,
  entityWatchlistSummary,
  trends = [],
  selectedEntityId,
  onSelectedEntityChange,
  onFilterChange,
  onUpdateEntityWatchlist,
  onOpenEntity,
  onWatchEvent,
  onIgnoreEvent,
  onDeepDive,
  onNavigateToAlerts,
  highlightEventId,
  busyEventId,
  loading = false,
  onPageChange,
  onPageSizeChange,
}: EventsPageProps) {
  const [sortBy, setSortBy] = useState<ExtendedSortKey>("composite_score");
  const [historyFilter, setHistoryFilter] = useState<HistoryRecordStatus | "all">("all");
  const [historyVisibleCount, setHistoryVisibleCount] = useState(PAGE_SIZE);
  const [expandedCards, setExpandedCards] = useState<Set<string>>(() => new Set());
  const [relatedByEventId, setRelatedByEventId] = useState<Record<string, EventRelationInfo[]>>({});
  const [relatedErrors, setRelatedErrors] = useState<Record<string, string>>({});
  const [loadingRelatedIds, setLoadingRelatedIds] = useState<Set<string>>(() => new Set());
  const filters = useMemo<EventsFilters>(() => ({
    entity_id: selectedEntityId !== "all" ? selectedEntityId : undefined,
    sort_by: sortBy,
    ignore_mode: "visible",
  }), [selectedEntityId, sortBy]);
  const [lastEmittedFilters, setLastEmittedFilters] = useState<EventsFilters>(filters);

  useEffect(() => {
    if (!highlightEventId) return;
    setExpandedCards((prev) => {
      const next = new Set(prev);
      next.add(highlightEventId);
      return next;
    });
    void ensureRelatedLoaded(highlightEventId);
  }, [highlightEventId]);

  function emitFilters(nextFilters: EventsFilters) {
    if (eventsFiltersEqual(lastEmittedFilters, nextFilters)) return;
    setLastEmittedFilters(nextFilters);
    onFilterChange(nextFilters);
  }

  function toggleExpanded(id: string) {
    setExpandedCards((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        void ensureRelatedLoaded(id);
      }
      return next;
    });
  }

  async function ensureRelatedLoaded(eventId: string) {
    if (relatedByEventId[eventId] || loadingRelatedIds.has(eventId)) {
      return;
    }
    setLoadingRelatedIds((prev) => new Set(prev).add(eventId));
    setRelatedErrors((prev) => {
      const next = { ...prev };
      delete next[eventId];
      return next;
    });
    try {
      const response = await api.fetchRelatedEvents(eventId);
      setRelatedByEventId((prev) => ({ ...prev, [eventId]: response.items ?? [] }));
    } catch (err) {
      setRelatedErrors((prev) => ({
        ...prev,
        [eventId]: err instanceof Error ? err.message : "关联事件加载失败",
      }));
    } finally {
      setLoadingRelatedIds((prev) => {
        const next = new Set(prev);
        next.delete(eventId);
        return next;
      });
    }
  }
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

  const filteredHistory = useMemo(() => {
    return historyItems
      .filter((item) => {
        const matchesStatus = historyFilter === "all" || item.status === historyFilter;
        const matchesEntity = selectedEntityId === "all" || item.entity_ids.includes(selectedEntityId);
        return matchesStatus && matchesEntity;
      })
      .sort((left, right) => {
        const leftTime = Date.parse(left.last_seen_at || left.discovered_at || "") || 0;
        const rightTime = Date.parse(right.last_seen_at || right.discovered_at || "") || 0;
        return rightTime - leftTime;
      });
  }, [historyFilter, historyItems, selectedEntityId]);
  const visibleHistory = filteredHistory.slice(0, historyVisibleCount);
  const hasMoreHistory = historyVisibleCount < filteredHistory.length;

  return (
    <div className="intel-page-with-sidepanel">
      <section className="panel">
        <div className="panel-header compact">
          <div>
            <p className="eyebrow">热点簇</p>
            <h2>已聚合的热点事件</h2>
          </div>
          <span className="subtle">{items.length} 个事件</span>
        </div>
        <div className="intel-chip-filter-bar">
          <div className="intel-chip-row">
            {PRIMARY_SORT_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                className={`filter-chip ${sortBy === opt.key ? "filter-chip-active" : ""}`}
                onClick={() => {
                  setSortBy(opt.key);
                  emitFilters({
                    entity_id: selectedEntityId !== "all" ? selectedEntityId : undefined,
                    sort_by: opt.key,
                    ignore_mode: "visible",
                  });
                }}
              >
              {opt.label}
              </button>
            ))}
            <select
              value={PRIMARY_SORT_OPTIONS.some((opt) => opt.key === sortBy) ? "" : sortBy}
              onChange={(event) => {
                if (!event.target.value) return;
                const nextSort = event.target.value as ExtendedSortKey;
                setSortBy(nextSort);
                emitFilters({
                  entity_id: selectedEntityId !== "all" ? selectedEntityId : undefined,
                  sort_by: nextSort,
                  ignore_mode: "visible",
                });
              }}
            >
              <option value="">更多排序</option>
              {EXTENDED_SORT_OPTIONS.map((opt) => (
                <option key={opt.key} value={opt.key}>{opt.label}</option>
              ))}
            </select>
          </div>
          <div className="intel-inline-filter-tools">
            <select
              value={selectedEntityId}
              onChange={(event) => {
                const nextEntityId = event.target.value;
                const nextFilters = {
                  entity_id: nextEntityId !== "all" ? nextEntityId : undefined,
                  sort_by: sortBy,
                  ignore_mode: "visible",
                };
                onSelectedEntityChange(nextEntityId);
                emitFilters(nextFilters);
                setHistoryVisibleCount(PAGE_SIZE);
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
        <div className="intel-score-row" style={{ marginBottom: 4 }}>
          <span>共 {total} 个事件</span>
        </div>
        <div className="intel-list">
          {items.length ? items.map((event) => {
            const visibleTags = event.entity_names.slice(0, 3);
            const hiddenTagCount = Math.max(event.entity_names.length - visibleTags.length, 0);
            return (
              <article key={event.id} className={`intel-row-card severity-${event.alert_state} ${highlightEventId === event.id ? "focus-card" : ""}`}>
                <div className="intel-card-topline">
                  <span className={`status-badge status-${event.alert_state === "breakout" ? "danger" : event.alert_state === "rising" ? "warning" : event.alert_state === "watch" ? "success" : "neutral"}`}>
                    {event.alert_state}
                  </span>
                  <span>{event.platform_count} 平台 / {event.source_count} 来源 / {event.member_count} 条素材</span>
                </div>
                <strong>{event.title}</strong>
                <p>{event.summary}</p>
                {visibleTags.length ? (
                  <div className="entity-tag-row">
                    {visibleTags.map((name, index) => (
                      <button
                        key={`${event.id}-${name}`}
                        type="button"
                        className={`entity-tag ${event.entity_ids[index] === selectedEntityId ? "entity-tag-active" : ""}`}
                        onClick={() => {
                          const nextEntityId = event.entity_ids[index] ?? "all";
                          onSelectedEntityChange(nextEntityId);
                          emitFilters({
                            entity_id: nextEntityId !== "all" ? nextEntityId : undefined,
                            sort_by: sortBy,
                            ignore_mode: "visible",
                          });
                        }}
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

                <button
                  type="button"
                  className="intel-expand-trigger"
                  onClick={() => toggleExpanded(event.id)}>
                  {expandedCards.has(event.id) ? "收起详情 ▲" : "展开详情 ▼"}
                </button>
                {expandedCards.has(event.id) ? (
                  <div className="intel-event-detail">
                    <div className="intel-score-row">
                      <span>成员增量 {event.member_delta >= 0 ? `+${event.member_delta}` : event.member_delta}</span>
                      <span>平台增量 {event.platform_delta >= 0 ? `+${event.platform_delta}` : event.platform_delta}</span>
                      <span>首次 {formatDateTime(event.first_seen_at, { fallback: "未知" })}</span>
                      <span>最近 {formatDateTime(event.last_seen_at, { fallback: "未知" })}</span>
                    </div>
                    <div className="related-events-section">
                      <div className="related-events-head">
                        <span>关联事件</span>
                        {relatedByEventId[event.id] ? <span className="subtle">{relatedByEventId[event.id].length} 条</span> : null}
                      </div>
                      {loadingRelatedIds.has(event.id) ? (
                        <p className="subtle">正在加载关联事件...</p>
                      ) : relatedErrors[event.id] ? (
                        <p className="warning-note">{relatedErrors[event.id]}</p>
                      ) : (relatedByEventId[event.id] ?? []).length ? (
                        <div className="related-events-list">
                          {(relatedByEventId[event.id] ?? []).map((relation) => {
                            const percentage = Math.max(0, Math.min(100, Math.round((relation.weight || 0) * 100)));
                            return (
                              <div key={`${event.id}-${relation.event_id}`} className="related-event-item">
                                <div className="related-event-topline">
                                  <strong>{relation.title || relation.event_id}</strong>
                                  <span className="entity-tag entity-tag-muted">{relationTypeLabel(relation.relation_type)}</span>
                                  <span className="subtle">{percentage}%</span>
                                </div>
                                <div className="related-event-meter" aria-hidden="true">
                                  <span style={{ width: `${percentage}%` }} />
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="subtle">暂无关联事件。</p>
                      )}
                    </div>
                  </div>
                ) : null}
                <div className="intel-event-actions">
                  <div className="intel-secondary-actions">
                    <a href={event.representative_link} target="_blank" rel="noreferrer">查看原文</a>
                    {event.alert_state !== "new" ? (
                      <button type="button" className="ghost-button compact" onClick={() => onNavigateToAlerts?.(event.id)}>
                        查看预警
                      </button>
                    ) : null}
                    <button type="button" className="ghost-button compact" disabled={event.watchlisted} onClick={() => void onWatchEvent(event.id)}>
                      {event.watchlisted ? "已加入深挖池" : "加入深挖池"}
                    </button>
                    <button type="button" className="ghost-button compact" onClick={() => void onIgnoreEvent(event.id)}>
                      忽略
                    </button>
                  </div>
                  <button
                    type="button"
                    className="primary-button compact"
                    disabled={busyEventId === event.id}
                    onClick={() => void onDeepDive(event.id)}
                  >
                    {busyEventId === event.id ? "深挖中..." : event.deep_dive_id ? "重新深挖" : "立即深挖"}
                  </button>
                </div>
                <p className={`subtle ${event.worth_to_brief ? "" : "warning-note"}`}>{event.worth_reason || event.deep_dive_summary || "尚未完成正文深挖。"}</p>
              </article>
            );
          }) : <p className="empty-state">{selectedEntityId !== "all" ? "当前筛选条件下没有匹配的热点事件。" : explainEventsEmptyState(runtime)}</p>}
        </div>
        <PaginationControls
          page={page}
          pageSize={pageSize}
          total={total}
          currentCount={items.length}
          itemLabel="个事件"
          loading={loading}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />

        <div className="intel-subsection-head">
          <div>
            <p className="eyebrow">24h 内已发现热点</p>
            <h3>今日已发现</h3>
          </div>
          <span className="subtle">{filteredHistory.length} 个事件</span>
        </div>
        <div className="intel-chip-filter-bar">
          <div className="intel-chip-row">
            {([
              { key: "all", label: "全部" },
              { key: "active", label: "仍活跃" },
              { key: "cooled", label: "已回落" },
              { key: "source_uncertain", label: "待确认" },
            ] as Array<{ key: HistoryRecordStatus | "all"; label: string }>).map((opt) => (
              <button
                key={opt.key}
                type="button"
                className={`filter-chip ${historyFilter === opt.key ? "filter-chip-active" : ""}`}
                onClick={() => { setHistoryFilter(opt.key); setHistoryVisibleCount(PAGE_SIZE); }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className="intel-list">
          {visibleHistory.length ? visibleHistory.map((event) => {
            const visibleTags = event.entity_names.slice(0, 3);
            const hiddenTagCount = Math.max(event.entity_names.length - visibleTags.length, 0);
            return (
              <article key={event.history_id} className={`intel-row-card severity-${severityForHistory(event.status)}`}>
                <div className="intel-card-topline">
                  <span className={`status-badge status-${historyStatusTone(event.status)}`}>{historyStatusLabel(event.status)}</span>
                  <span>{event.platform_count} 平台 / {event.source_count} 来源 / {event.member_count} 条素材</span>
                </div>
                <strong>{event.title}</strong>
                <p>{event.summary}</p>
                {event.status === "source_uncertain" ? (
                  <p className="intel-history-note">本轮存在来源异常，未继续确认该信号。</p>
                ) : null}
                {visibleTags.length ? (
                  <div className="entity-tag-row">
                    {visibleTags.map((name, index) => (
                      <button
                        key={`${event.history_id}-${name}`}
                        type="button"
                        className={`entity-tag ${event.entity_ids[index] === selectedEntityId ? "entity-tag-active" : ""}`}
                        onClick={() => {
                          const nextEntityId = event.entity_ids[index] ?? "all";
                          onSelectedEntityChange(nextEntityId);
                          emitFilters({
                            entity_id: nextEntityId !== "all" ? nextEntityId : undefined,
                            sort_by: sortBy,
                            ignore_mode: "visible",
                          });
                        }}
                      >
                        {name}
                      </button>
                    ))}
                    {hiddenTagCount ? <span className="entity-tag entity-tag-muted">+{hiddenTagCount}</span> : null}
                  </div>
                ) : null}
                <div className="intel-score-row">
                  <span>总分 {event.composite_score}</span>
                  <span>成员增量 {event.member_delta >= 0 ? `+${event.member_delta}` : event.member_delta}</span>
                  <span>平台增量 {event.platform_delta >= 0 ? `+${event.platform_delta}` : event.platform_delta}</span>
                </div>
                <div className="intel-inline-actions">
                  <span>首次 {formatDateTime(event.discovered_at, { fallback: "未知" })}</span>
                  <span>最近 {formatDateTime(event.last_seen_at, { fallback: "未知" })}</span>
                  <a href={event.representative_link} target="_blank" rel="noreferrer">查看原文</a>
                </div>
              </article>
            );
          }) : (
            <p className="empty-state">
              {historyItems.length
                ? "当前筛选条件下没有匹配的 24 小时热点记录。"
                : "24 小时内暂无已发现热点记录。"}
            </p>
          )}
        </div>
        {hasMoreHistory ? (
          <div className="intel-load-more">
            <button type="button" className="ghost-button" onClick={() => setHistoryVisibleCount((c) => c + PAGE_SIZE)}>
              加载更多 ({filteredHistory.length - historyVisibleCount} 个)
            </button>
          </div>
        ) : null}
      </section>

      <EntityWatchlistPanel
        items={entityWatchlist}
        summary={entityWatchlistSummary}
        trends={trends}
        availableEntities={entityOptions}
        selectedEntityId={selectedEntityId}
        onSelectEntity={onSelectedEntityChange}
        onUpdateWatchlist={onUpdateEntityWatchlist}
        onOpenEntity={onOpenEntity}
      />
    </div>
  );
}
