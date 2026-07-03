import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type { EventDeepDive, IntelEvent } from "../../types";

interface WatchlistPageProps {
  items: IntelEvent[];
  selectedDeepDive: EventDeepDive | null;
  busyEventId?: string | null;
  loading?: boolean;
  onDeepDive: (eventId: string, force?: boolean) => Promise<void>;
  onCreateBrief: (eventId: string) => Promise<void>;
  onOpenDeepDive: (eventId: string) => Promise<void>;
}

function statusTone(status?: string | null) {
  if (status === "ready") return "success";
  if (status === "partial") return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

type DeepDiveSectionKey = "today-pending" | "today-ready" | "past-pending" | "past-ready";

function parseDate(value?: string | null) {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function isSameLocalDay(left: Date, right: Date) {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

function hasCompletedDeepDive(event: IntelEvent) {
  return event.deep_dive_status === "ready" || event.deep_dive_status === "partial";
}

function pickDeepDiveMoment(event: IntelEvent) {
  return event.deep_dive_finished_at || event.deep_dive_updated_at || event.deep_dive_started_at || null;
}

function pickCollectionMoment(event: IntelEvent) {
  return event.latest_collected_at || event.last_seen_at || event.first_seen_at || event.published_at || null;
}

function classifySection(event: IntelEvent, now: Date): DeepDiveSectionKey {
  const completed = hasCompletedDeepDive(event);
  const workMoment = completed ? pickDeepDiveMoment(event) : (pickDeepDiveMoment(event) || pickCollectionMoment(event));
  const isToday = workMoment ? (() => {
    const parsed = parseDate(workMoment);
    return parsed ? isSameLocalDay(parsed, now) : false;
  })() : false;
  if (completed) {
    return isToday ? "today-ready" : "past-ready";
  }
  return isToday ? "today-pending" : "past-pending";
}

function pickActivityTime(event: IntelEvent) {
  if (hasCompletedDeepDive(event)) {
    return {
      label: "深挖更新",
      value: pickDeepDiveMoment(event),
    };
  }
  const attemptedMoment = pickDeepDiveMoment(event);
  if (attemptedMoment) {
    return {
      label: "上次尝试",
      value: attemptedMoment,
    };
  }
  return {
    label: "最近采集",
    value: pickCollectionMoment(event),
  };
}

const SECTION_META: Array<{
  key: DeepDiveSectionKey;
  title: string;
  description: string;
  emptyHint: string;
}> = [
  {
    key: "today-pending",
    title: "待深挖",
    description: "今天进入处理范围，还没拿到可用正文。",
    emptyHint: "待深挖暂无事件。",
  },
  {
    key: "today-ready",
    title: "已深挖",
    description: "今天已完成正文深挖，可继续判断是否进入交付。",
    emptyHint: "已深挖暂无事件。",
  },
  {
    key: "past-pending",
    title: "往日待深挖",
    description: "之前留下的待处理事件，仍需补正文与核验。",
    emptyHint: "往日待深挖暂无事件。",
  },
  {
    key: "past-ready",
    title: "往日已深挖",
    description: "历史上已完成正文深挖的事件，可回看来源与结论。",
    emptyHint: "往日已深挖暂无事件。",
  },
];

function statusLabel(status?: string | null) {
  if (status === "ready") return "已完成";
  if (status === "partial") return "部分完成";
  if (status === "failed") return "失败";
  if (status === "running") return "深挖中";
  return "待深挖";
}

function severityClass(status?: string | null) {
  if (status === "ready") return "ready";
  if (status === "partial") return "partial";
  if (status === "failed") return "failed";
  return "pending";
}

function buildSearchText(event: IntelEvent) {
  return [
    event.title,
    event.summary,
    event.representative_source_name,
    event.deep_dive_summary,
    event.worth_reason,
    ...event.entity_names,
  ].filter(Boolean).join(" ").toLowerCase();
}

export function WatchlistPage({
  items,
  selectedDeepDive,
  busyEventId,
  loading = false,
  onDeepDive,
  onCreateBrief,
  onOpenDeepDive,
}: WatchlistPageProps) {
  const [activeSection, setActiveSection] = useState<DeepDiveSectionKey>("today-pending");
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const { readyCount: readyItems, partialCount: partialItems, briefCount: briefItems, sections } = useMemo(() => {
    let ready = 0;
    let partial = 0;
    let brief = 0;
    const nextSections: Record<DeepDiveSectionKey, IntelEvent[]> = {
      "today-pending": [],
      "today-ready": [],
      "past-pending": [],
      "past-ready": [],
    };
    const now = new Date();
    for (const item of items) {
      if (item.deep_dive_status === "ready") ready++;
      if (item.deep_dive_status === "partial") partial++;
      if (item.brief_id) brief++;
      nextSections[classifySection(item, now)].push(item);
    }
    for (const sectionItems of Object.values(nextSections)) {
      sectionItems.sort((left, right) => {
        const leftTime = parseDate(pickActivityTime(left).value)?.getTime() ?? 0;
        const rightTime = parseDate(pickActivityTime(right).value)?.getTime() ?? 0;
        return rightTime - leftTime;
      });
    }
    return { readyCount: ready, partialCount: partial, briefCount: brief, sections: nextSections };
  }, [items]);
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const activeItems = useMemo(() => {
    const sectionItems = sections[activeSection] ?? [];
    if (!normalizedSearch) {
      return sectionItems;
    }
    return sectionItems.filter((event) => buildSearchText(event).includes(normalizedSearch));
  }, [activeSection, normalizedSearch, sections]);
  const activeMeta = SECTION_META.find((section) => section.key === activeSection) ?? SECTION_META[0];

  function toggleExpanded(eventId: string) {
    const nextExpanded = !expandedCards.has(eventId);
    setExpandedCards((previous) => {
      const next = new Set(previous);
      if (nextExpanded) {
        next.add(eventId);
      } else {
        next.delete(eventId);
      }
      return next;
    });
    if (nextExpanded && selectedDeepDive?.event_id !== eventId) {
      void onOpenDeepDive(eventId);
    }
  }

  function renderSkeleton() {
    return (
      <div className="skeleton-list watchlist-skeleton" aria-label="深挖池加载中">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={`watchlist-skeleton-${index}`} className="skeleton-card">
            <div className="skeleton-line skeleton-short" />
            <div className="skeleton-line skeleton-long" />
            <div className="skeleton-line skeleton-medium" />
          </div>
        ))}
      </div>
    );
  }

  function renderEmptyState() {
    if (!items.length) {
      return <p className="empty-state">深挖池暂无事件。</p>;
    }
    if (normalizedSearch) {
      return <p className="empty-state">没有匹配的深挖事件。</p>;
    }
    return <p className="empty-state">{activeMeta.emptyHint}</p>;
  }

  function renderEventCard(event: IntelEvent) {
    const visibleTags = event.entity_names.slice(0, 3);
    const hiddenTagCount = Math.max(event.entity_names.length - visibleTags.length, 0);
    const expanded = expandedCards.has(event.id) || selectedDeepDive?.event_id === event.id;
    const visibleDeepDive = selectedDeepDive?.event_id === event.id ? selectedDeepDive : null;
    const activity = pickActivityTime(event);
    const busy = busyEventId === event.id;
    const worthLabel = event.worth_to_brief ? "值得交付" : hasCompletedDeepDive(event) ? "继续观察" : "待评估";

    return (
      <article key={event.id} className={`watchlist-card severity-${severityClass(event.deep_dive_status)}`}>
        <div className="watchlist-card-topline">
          <span className={`status-badge status-${statusTone(event.deep_dive_status)}`}>
            {statusLabel(event.deep_dive_status)}
          </span>
          <span className="watchlist-meta">
            {(event.platforms.length ? event.platforms.slice(0, 2).join(" / ") : "平台未知")}
            {" · "}
            {event.source_count} 来源
            {" · "}
            {event.member_count} 条素材
          </span>
        </div>

        <div className="watchlist-card-main">
          <strong>{event.title}</strong>
          {event.summary ? <p>{event.summary}</p> : null}
        </div>

        <div className="watchlist-evaluation-row">
          <span className={`watchlist-worth-badge ${event.worth_to_brief ? "worth-yes" : "worth-pending"}`}>
            {worthLabel}
          </span>
          {visibleTags.length ? (
            <div className="entity-tag-row">
              {visibleTags.map((name) => (
                <span key={`${event.id}-${name}`} className="entity-tag entity-tag-muted">
                  {name}
                </span>
              ))}
              {hiddenTagCount ? <span className="entity-tag entity-tag-muted">+{hiddenTagCount}</span> : null}
            </div>
          ) : null}
        </div>

        <div className="watchlist-time-row">
          <span>{activity.label} · {formatRelativeTime(activity.value, "时间未知")}</span>
          {event.representative_source_name ? <span>{event.representative_source_name}</span> : null}
        </div>

        <div className="watchlist-actions">
          <button type="button" className="watchlist-expand" onClick={() => toggleExpanded(event.id)}>
            {expanded ? "收起详情 ▲" : "查看详情 ▼"}
          </button>
          {event.representative_link ? <a href={event.representative_link} target="_blank" rel="noreferrer">查看原文</a> : null}
          <button
            type="button"
            className="ghost-button compact"
            disabled={busy}
            onClick={() => void onDeepDive(event.id, true)}
          >
            {busy ? "深挖中..." : event.deep_dive_id ? "重新深挖" : "立即深挖"}
          </button>
          <button
            type="button"
            className="primary-button compact"
            disabled={busy}
            onClick={() => void onCreateBrief(event.id)}
          >
            {event.brief_id ? "更新简报" : "生成简报"}
          </button>
        </div>

        {busy ? (
          <div className="watchlist-busy">
            <span className="watchlist-busy-dot" />
            <span>深挖处理中</span>
          </div>
        ) : null}

        {expanded && !busy ? (
          <div className="watchlist-detail">
            {visibleDeepDive ? (
              <>
                <div className="watchlist-detail-head">
                  <span>深挖详情</span>
                  <span className="draft-chip muted">{visibleDeepDive.success_count}/{visibleDeepDive.attempted_count} 来源成功</span>
                </div>
                <div className="watchlist-detail-metrics">
                  <span>完整正文 {visibleDeepDive.full_text_sources.length} 篇</span>
                  <span>事实 {visibleDeepDive.facts.length} 条</span>
                  <span>引文 {visibleDeepDive.quotes.length} 条</span>
                  <span>更新 {formatDateTime(visibleDeepDive.updated_at, { fallback: "时间未知" })}</span>
                </div>
                <p className={`watchlist-worth-note ${event.worth_to_brief ? "" : "warning-note"}`}>
                  {visibleDeepDive.worthiness.reason || event.worth_reason || event.deep_dive_summary || "尚未形成交付判断。"}
                </p>
                {!!visibleDeepDive.facts.length ? (
                  <div className="draft-list-block">
                    <span>核心事实</span>
                    <ul>
                      {visibleDeepDive.facts.slice(0, 5).map((fact) => (
                        <li key={fact}>{fact}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <div className="draft-list-block">
                  <span>来源明细</span>
                  {visibleDeepDive.sources.length ? (
                    <ul>
                      {visibleDeepDive.sources.slice(0, 8).map((item) => (
                        <li key={`${visibleDeepDive.id}-${item.canonical_link || item.original_link || item.title}`}>
                          {item.source_name || "未知来源"} · {item.extract_status} · {item.word_count} 字
                          {item.canonical_link ? (
                            <>
                              {" "}
                              <a href={item.canonical_link} target="_blank" rel="noreferrer">打开</a>
                            </>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>暂无来源明细。</p>
                  )}
                </div>
                {visibleDeepDive.full_text_sources.length ? (
                  <div className="draft-list-block">
                    <span>正文预览</span>
                    <ul>
                      {visibleDeepDive.full_text_sources.slice(0, 3).map((item) => (
                        <li key={`${visibleDeepDive.id}-full-${item.canonical_link || item.original_link || item.title}`}>
                          <strong>{item.source_name || "未知来源"}</strong>
                          {" · "}
                          {item.word_count} 字
                          <p>{item.cleaned_full_text.slice(0, 220)}{item.cleaned_full_text.length > 220 ? "..." : ""}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <div className="watchlist-detail-head">
                  <span>深挖详情</span>
                  <span className="subtle">展开后读取来源与正文</span>
                </div>
                <p className="watchlist-worth-note">{event.worth_reason || event.deep_dive_summary || "尚未完成正文深挖。"}</p>
              </>
            )}
            <div className="watchlist-detail-metrics">
              <span>发布时间 {formatDateTime(event.published_at, { fallback: "未知" })}</span>
              <span>首次发现 {formatDateTime(event.first_seen_at, { fallback: "未知" })}</span>
              <span>最近采集 {formatDateTime(event.latest_collected_at, { fallback: "未知" })}</span>
            </div>
          </div>
        ) : null}
      </article>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">深挖池</p>
          <h2>先拿到正文，再决定哪些事件值得交付成简报</h2>
        </div>
        <span className="subtle">{items.length} 个已观察事件</span>
      </div>

      <div className="watchlist-summary-row">
        <span>深挖完成 {readyItems}</span>
        <span>部分完成 {partialItems}</span>
        <span>已有简报 {briefItems}</span>
      </div>

      <div className="watchlist-stats">
        {SECTION_META.map((section) => (
          <button
            key={section.key}
            type="button"
            aria-label={`${section.title} ${sections[section.key].length} 条`}
            className={`watchlist-stat ${activeSection === section.key ? "watchlist-stat-active" : ""} stat-${section.key}`}
            onClick={() => setActiveSection(section.key)}
          >
            <span className="watchlist-stat-value">{sections[section.key].length}</span>
            <span className="watchlist-stat-label">{section.title}</span>
          </button>
        ))}
      </div>

      <div className="watchlist-filter-bar">
        <span className="subtle">{activeMeta.description}</span>
        <input
          type="search"
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          placeholder="搜索标题、摘要或实体"
          aria-label="搜索深挖事件"
        />
      </div>

      <div className="watchlist-grid">
        {loading && !items.length ? renderSkeleton() : (
          activeItems.length ? activeItems.map((event) => renderEventCard(event)) : renderEmptyState()
        )}
      </div>
    </section>
  );
}
