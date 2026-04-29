import { useMemo, useState } from "react";

import { explainAlertsEmptyState } from "../lib/runtimeIntent";
import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { HistoryRecordStatus, IntelAlert, IntelAlertHistoryItem, SchedulerStatus } from "../types";

const PAGE_SIZE = 20;

type FilterLevel = "all" | "breakout" | "rising" | "watch" | "cooling";
type HistoryFilter = "all" | "active" | "cooled" | "source_uncertain";

const FILTER_OPTIONS: Array<{ key: FilterLevel; label: string }> = [
  { key: "all", label: "全部" },
  { key: "breakout", label: "爆发" },
  { key: "rising", label: "上升" },
  { key: "watch", label: "关注" },
  { key: "cooling", label: "冷却" },
];

interface IntelAlertsPageProps {
  items: IntelAlert[];
  historyItems: IntelAlertHistoryItem[];
  runtime: SchedulerStatus;
  eventCount: number;
  selectedEntityId: string;
  onSelectedEntityChange: (entityId: string) => void;
  onCreateDraft: (eventId: string) => Promise<void>;
  busyEventId?: string | null;
}

function historyStatusLabel(status: HistoryRecordStatus) {
  if (status === "active") return "仍活跃";
  if (status === "source_uncertain") return "待确认";
  return "已回落";
}

function historyStatusTone(status: HistoryRecordStatus) {
  if (status === "active") return "success";
  if (status === "source_uncertain") return "warning";
  return "neutral";
}

export function IntelAlertsPage({
  items,
  historyItems,
  runtime,
  eventCount,
  selectedEntityId,
  onSelectedEntityChange,
  onCreateDraft,
  busyEventId,
}: IntelAlertsPageProps) {
  const [filter, setFilter] = useState<FilterLevel>("all");
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [historyVisibleCount, setHistoryVisibleCount] = useState(PAGE_SIZE);

  const entityOptions = useMemo(() => {
    const lookup = new Map<string, { entity_id: string; entity_name: string }>();
    for (const alert of items) {
      alert.entity_ids.forEach((entityId, index) => {
        const entityName = alert.entity_names[index];
        if (!entityId || !entityName || lookup.has(entityId)) return;
        lookup.set(entityId, { entity_id: entityId, entity_name: entityName });
      });
    }
    return [...lookup.values()].sort((a, b) => a.entity_name.localeCompare(b.entity_name, "zh-CN"));
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((alert) => {
      const matchesLevel = filter === "all" || alert.level === filter;
      const matchesEntity = selectedEntityId === "all" || alert.entity_ids.includes(selectedEntityId);
      return matchesLevel && matchesEntity;
    });
  }, [filter, items, selectedEntityId]);

  const filteredHistory = useMemo(() => {
    return historyItems
      .filter((alert) => {
        const matchesStatus = historyFilter === "all" || alert.status === historyFilter;
        const matchesEntity = selectedEntityId === "all" || alert.entity_ids.includes(selectedEntityId);
        return matchesStatus && matchesEntity;
      })
      .sort((left, right) => {
        const leftTime = Date.parse(left.last_triggered_at || left.first_triggered_at || "") || 0;
        const rightTime = Date.parse(right.last_triggered_at || right.first_triggered_at || "") || 0;
        return rightTime - leftTime;
      });
  }, [historyFilter, historyItems, selectedEntityId]);

  const visible = filtered.slice(0, visibleCount);
  const visibleHistory = filteredHistory.slice(0, historyVisibleCount);
  const hasMore = visibleCount < filtered.length;
  const hasMoreHistory = historyVisibleCount < filteredHistory.length;

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">预警台</p>
          <h2>上升中和爆发中的热点事件</h2>
        </div>
        <span className="subtle">{filtered.length} 条</span>
      </div>
      <div className="intel-chip-filter-bar">
        <div className="intel-chip-row">
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
        <div className="intel-inline-filter-tools">
          <select
            value={selectedEntityId}
            onChange={(event) => {
              onSelectedEntityChange(event.target.value);
              setVisibleCount(PAGE_SIZE);
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
      <div className="intel-list">
        {visible.length ? visible.map((alert) => {
          const visibleTags = alert.entity_names.slice(0, 3);
          const hiddenTagCount = Math.max(alert.entity_names.length - visibleTags.length, 0);
          return (
          <article key={alert.id} className="intel-row-card">
            <div className="intel-card-topline">
              <span className={`status-badge status-${alert.level === "breakout" ? "danger" : alert.level === "rising" ? "warning" : alert.level === "watch" ? "success" : "neutral"}`}>
                {alert.level}
              </span>
              <span>{formatRelativeTime(alert.triggered_at, "刚刚")}</span>
            </div>
            <strong>{alert.title}</strong>
            <p>{alert.reason}</p>
            {visibleTags.length ? (
              <div className="entity-tag-row">
                {visibleTags.map((name, index) => (
                  <button
                    key={`${alert.id}-${name}`}
                    type="button"
                    className={`entity-tag ${alert.entity_ids[index] === selectedEntityId ? "entity-tag-active" : ""}`}
                    onClick={() => onSelectedEntityChange(alert.entity_ids[index] ?? "all")}
                  >
                    {name}
                  </button>
                ))}
                {hiddenTagCount ? <span className="entity-tag entity-tag-muted">+{hiddenTagCount}</span> : null}
              </div>
            ) : null}
            <div className="intel-score-row">
              <span>速度 {alert.velocity_score}</span>
              <span>覆盖 {alert.coverage_score}</span>
              <span>新鲜 {alert.freshness_score}</span>
              <span>{alert.platform_count} 平台</span>
            </div>
            <div className="intel-inline-actions">
              <span>{formatDateTime(alert.triggered_at, { fallback: "未知" })}</span>
              <a href={alert.representative_link} target="_blank" rel="noreferrer">查看原文</a>
              <button
                type="button"
                className="primary-button compact"
                disabled={busyEventId === alert.event_id || alert.draft_exists}
                onClick={() => void onCreateDraft(alert.event_id)}
              >
                {busyEventId === alert.event_id ? "生成中..." : alert.draft_exists ? "已生成稿件" : "生成稿件"}
              </button>
            </div>
            <p className={`subtle ${alert.draft_ready ? "" : "warning-note"}`}>{alert.draft_reason}</p>
          </article>
        );
        }) : (
          <p className="empty-state">
            {(items.length && (filter !== "all" || selectedEntityId !== "all"))
              ? "当前筛选条件下没有匹配的预警。"
              : explainAlertsEmptyState(runtime, eventCount, items.length)}
          </p>
        )}
      </div>
      {hasMore ? (
        <div className="intel-load-more">
          <button type="button" className="ghost-button" onClick={() => setVisibleCount((c) => c + PAGE_SIZE)}>
            加载更多 ({filtered.length - visibleCount} 条)
          </button>
        </div>
      ) : null}

      <div className="intel-subsection-head">
        <div>
          <p className="eyebrow">24h 内已发现预警</p>
          <h3>今日已发现</h3>
        </div>
        <span className="subtle">{filteredHistory.length} 条</span>
      </div>
      <div className="intel-chip-filter-bar">
        <div className="intel-chip-row">
          {([
            { key: "all", label: "全部" },
            { key: "active", label: "仍活跃" },
            { key: "cooled", label: "已回落" },
            { key: "source_uncertain", label: "待确认" },
          ] as Array<{ key: HistoryFilter; label: string }>).map((opt) => (
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
        {visibleHistory.length ? visibleHistory.map((alert) => {
          const visibleTags = alert.entity_names.slice(0, 3);
          const hiddenTagCount = Math.max(alert.entity_names.length - visibleTags.length, 0);
          return (
            <article key={alert.history_id} className="intel-row-card">
              <div className="intel-card-topline">
                <span className={`status-badge status-${historyStatusTone(alert.status)}`}>
                  {historyStatusLabel(alert.status)}
                </span>
                <span className={`status-badge status-${alert.highest_level === "breakout" ? "danger" : "warning"}`}>
                  最高 {alert.highest_level}
                </span>
              </div>
              <strong>{alert.title}</strong>
              <p>{alert.reason}</p>
              {alert.status === "source_uncertain" ? (
                <p className="intel-history-note">本轮存在来源异常，未继续确认该信号。</p>
              ) : null}
              {visibleTags.length ? (
                <div className="entity-tag-row">
                  {visibleTags.map((name, index) => (
                    <button
                      key={`${alert.history_id}-${name}`}
                      type="button"
                      className={`entity-tag ${alert.entity_ids[index] === selectedEntityId ? "entity-tag-active" : ""}`}
                      onClick={() => onSelectedEntityChange(alert.entity_ids[index] ?? "all")}
                    >
                      {name}
                    </button>
                  ))}
                  {hiddenTagCount ? <span className="entity-tag entity-tag-muted">+{hiddenTagCount}</span> : null}
                </div>
              ) : null}
              <div className="intel-score-row">
                <span>速度 {alert.velocity_score}</span>
                <span>覆盖 {alert.coverage_score}</span>
                <span>新鲜 {alert.freshness_score}</span>
                <span>{alert.platform_count} 平台</span>
              </div>
              <div className="intel-inline-actions">
                <span>首次 {formatDateTime(alert.first_triggered_at, { fallback: "未知" })}</span>
                <span>最近 {formatDateTime(alert.last_triggered_at, { fallback: "未知" })}</span>
                <a href={alert.representative_link} target="_blank" rel="noreferrer">查看原文</a>
              </div>
            </article>
          );
        }) : (
          <p className="empty-state">
            {historyItems.length
              ? "当前筛选条件下没有匹配的 24 小时预警记录。"
              : "24 小时内暂无已发现预警记录。"}
          </p>
        )}
      </div>
      {hasMoreHistory ? (
        <div className="intel-load-more">
          <button type="button" className="ghost-button" onClick={() => setHistoryVisibleCount((c) => c + PAGE_SIZE)}>
            加载更多 ({filteredHistory.length - historyVisibleCount} 条)
          </button>
        </div>
      ) : null}
    </section>
  );
}
