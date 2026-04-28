import { useMemo, useState } from "react";

import { explainAlertsEmptyState } from "../lib/runtimeIntent";
import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { IntelAlert, SchedulerStatus } from "../types";

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
  runtime: SchedulerStatus;
  eventCount: number;
  selectedEntityId: string;
  onSelectedEntityChange: (entityId: string) => void;
}

export function IntelAlertsPage({ items, runtime, eventCount, selectedEntityId, onSelectedEntityChange }: IntelAlertsPageProps) {
  const [filter, setFilter] = useState<FilterLevel>("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

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

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

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
            </div>
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
    </section>
  );
}
