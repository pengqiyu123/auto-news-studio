import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type { EventDeepDive, IntelEvent } from "../../types";

interface WatchlistPageProps {
  items: IntelEvent[];
  selectedDeepDive: EventDeepDive | null;
  busyEventId?: string | null;
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
}> = [
  {
    key: "today-pending",
    title: "待深挖",
    description: "今天进入处理范围，还没拿到可用正文。",
  },
  {
    key: "today-ready",
    title: "已深挖",
    description: "今天已完成正文深挖，可继续判断是否进入交付。",
  },
  {
    key: "past-pending",
    title: "往日待深挖",
    description: "之前留下的待处理事件，仍需补正文与核验。",
  },
  {
    key: "past-ready",
    title: "往日已深挖",
    description: "历史上已完成正文深挖的事件，可回看来源与结论。",
  },
];

export function WatchlistPage({
  items,
  selectedDeepDive,
  busyEventId,
  onDeepDive,
  onCreateBrief,
  onOpenDeepDive,
}: WatchlistPageProps) {
  const [activeSection, setActiveSection] = useState<DeepDiveSectionKey>("today-pending");
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
  const activeItems = sections[activeSection];

  function renderEventCard(event: IntelEvent) {
    const visibleTags = event.entity_names.slice(0, 3);
    const hiddenTagCount = Math.max(event.entity_names.length - visibleTags.length, 0);
    const expanded = selectedDeepDive?.event_id === event.id;
    const activity = pickActivityTime(event);

    return (
      <article key={event.id} className="intel-row-card">
        <div className="intel-card-topline">
          <span className={`status-badge status-${statusTone(event.deep_dive_status)}`}>
            {event.deep_dive_status ?? "pending"}
          </span>
          <span>{event.platform_count} 平台 / {event.source_count} 来源 / {event.member_count} 条素材</span>
        </div>
        <strong>{event.title}</strong>
        <p>{event.summary}</p>
        <div className="intel-score-row">
          <span>{event.alert_state}</span>
          <span>{event.deep_dive_summary || "尚未开始正文深挖。"}</span>
        </div>
        <div className="intel-score-row">
          <span>{formatDateTime(event.published_at, { fallback: "发布时间未知" })}</span>
          <span>{activity.label} {formatRelativeTime(activity.value, "时间未知")}</span>
        </div>
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
        <p className={`subtle ${event.worth_to_brief ? "" : "warning-note"}`}>{event.worth_reason || "尚未完成正文深挖。"}</p>
        <div className="intel-inline-actions">
          {event.representative_link ? <a href={event.representative_link} target="_blank" rel="noreferrer">查看原文</a> : null}
          <button type="button" className="ghost-button compact" onClick={() => void onOpenDeepDive(event.id)}>
            {expanded ? "收起来源" : "查看来源"}
          </button>
          <button
            type="button"
            className="ghost-button compact"
            disabled={busyEventId === event.id}
            onClick={() => void onDeepDive(event.id, true)}
          >
            {busyEventId === event.id ? "深挖中..." : event.deep_dive_id ? "重新深挖" : "立即深挖"}
          </button>
          <button
            type="button"
            className="primary-button compact"
            disabled={busyEventId === event.id}
            onClick={() => {
              if (!window.confirm("确认生成简报？将消耗 LLM token。")) return;
              void onCreateBrief(event.id);
            }}
          >
            {event.brief_id ? "更新简报" : "生成简报"}
          </button>
        </div>
        {busyEventId === event.id ? (
          <div className="draft-list-block">
            <span>进行中</span>
            <p>如已配置 Tavily，会先补充来源；随后抓取正文，并把全文交给 AI 生成简报。</p>
          </div>
        ) : null}
        {expanded && selectedDeepDive && busyEventId !== event.id ? (
          <div className="draft-section-card" style={{ marginTop: 16 }}>
            <div className="draft-section-head">
              <span className="draft-section-label">深挖详情</span>
              <span className="draft-chip muted">{selectedDeepDive.success_count}/{selectedDeepDive.attempted_count} 来源成功</span>
            </div>
            <div className="intel-score-row" style={{ marginBottom: 12 }}>
              <span>完整正文 {selectedDeepDive.full_text_sources.length} 篇</span>
              <span>事实 {selectedDeepDive.facts.length} 条</span>
              <span>引文 {selectedDeepDive.quotes.length} 条</span>
            </div>
            {!!selectedDeepDive.facts.length ? (
              <div className="draft-list-block">
                <span>核心事实</span>
                <ul>
                  {selectedDeepDive.facts.slice(0, 5).map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="draft-list-block">
              <span>来源明细</span>
              <ul>
                {selectedDeepDive.sources.slice(0, 8).map((item) => (
                  <li key={`${selectedDeepDive.id}-${item.canonical_link}`}>
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
            </div>
            {selectedDeepDive.full_text_sources.length ? (
              <div className="draft-list-block">
                <span>正文预览</span>
                <ul>
                  {selectedDeepDive.full_text_sources.slice(0, 3).map((item) => (
                    <li key={`${selectedDeepDive.id}-full-${item.canonical_link}`}>
                      <strong>{item.source_name || "未知来源"}</strong>
                      {" · "}
                      {item.word_count} 字
                      <p>{item.cleaned_full_text.slice(0, 220)}{item.cleaned_full_text.length > 220 ? "..." : ""}</p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
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

      <div className="intel-score-row" style={{ marginBottom: 12 }}>
        <span>深挖完成 {readyItems}</span>
        <span>部分完成 {partialItems}</span>
        <span>已有简报 {briefItems}</span>
      </div>

      <div className="segmented-control draft-workbench-tabs deep-dive-tabs">
        {SECTION_META.map((section) => (
          <button
            key={section.key}
            type="button"
            className={activeSection === section.key ? "segment-active" : ""}
            onClick={() => setActiveSection(section.key)}
          >
            <strong>{section.title}</strong>
            <span>{sections[section.key].length} 条</span>
          </button>
        ))}
      </div>

      <div className="deep-dive-inline-head">
        <div>
          <h3>{SECTION_META.find((section) => section.key === activeSection)?.title ?? "深挖池"}</h3>
          <p>{SECTION_META.find((section) => section.key === activeSection)?.description ?? ""}</p>
        </div>
      </div>

      <div className="intel-list">
        {activeItems.length ? activeItems.map((event) => renderEventCard(event)) : (
          <p className="empty-state">当前分组下没有事件。</p>
        )}
      </div>
    </section>
  );
}
