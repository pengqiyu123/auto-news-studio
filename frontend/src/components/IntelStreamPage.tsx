import { RotateCcw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { DiscoveryItem } from "../types";

const PAGE_SIZE = 20;
type TimeFilter = "all" | "1h" | "6h" | "24h" | "72h";
type ChangeFilter = "all" | "new_item" | "updated_item" | "seen_item";
type HeatFilter = "all" | "none" | "low" | "mid" | "high";

interface IntelStreamPageProps {
  items: DiscoveryItem[];
}

export function IntelStreamPage({ items }: IntelStreamPageProps) {
  const [query, setQuery] = useState("");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("24h");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [changeFilter, setChangeFilter] = useState<ChangeFilter>("all");
  const [heatFilter, setHeatFilter] = useState<HeatFilter>("all");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const platformOptions = useMemo(
    () => Array.from(new Set(items.map((item) => item.platform).filter(Boolean))).sort((a, b) => a.localeCompare(b, "zh-CN")),
    [items],
  );

  const sourceOptions = useMemo(
    () => Array.from(new Set(items.map((item) => item.source_name).filter(Boolean))).sort((a, b) => a.localeCompare(b, "zh-CN")),
    [items],
  );

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [query, timeFilter, platformFilter, sourceFilter, changeFilter, heatFilter]);

  const filtered = useMemo(() => {
    const now = Date.now();
    const q = query.toLowerCase();

    return items.filter((item) => {
      const matchesQuery =
        !q.trim() ||
        (item.title ?? "").toLowerCase().includes(q) ||
        (item.summary ?? "").toLowerCase().includes(q) ||
        (item.source_name ?? "").toLowerCase().includes(q) ||
        (item.platform ?? "").toLowerCase().includes(q);

      const matchesPlatform = platformFilter === "all" || item.platform === platformFilter;
      const matchesSource = sourceFilter === "all" || item.source_name === sourceFilter;
      const matchesChange = changeFilter === "all" || item.item_state === changeFilter;
      const engagement = Number(item.engagement_score ?? 0);
      const matchesHeat =
        heatFilter === "all" ||
        (heatFilter === "none" && engagement <= 0) ||
        (heatFilter === "low" && engagement > 0 && engagement < 10) ||
        (heatFilter === "mid" && engagement >= 10 && engagement < 100) ||
        (heatFilter === "high" && engagement >= 100);

      let matchesTime = true;
      if (timeFilter !== "all") {
        const collectedAt = item.collected_at ? new Date(item.collected_at).getTime() : 0;
        const ageMs = now - collectedAt;
        const limitMs =
          timeFilter === "1h" ? 3600_000 :
          timeFilter === "6h" ? 6 * 3600_000 :
          timeFilter === "24h" ? 24 * 3600_000 :
          72 * 3600_000;
        matchesTime = collectedAt > 0 && ageMs <= limitMs;
      }

      return matchesQuery && matchesPlatform && matchesSource && matchesChange && matchesHeat && matchesTime;
    });
  }, [items, query, timeFilter, platformFilter, sourceFilter, changeFilter, heatFilter]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visibleCount < filtered.length;

  function resetFilters() {
    setQuery("");
    setTimeFilter("24h");
    setPlatformFilter("all");
    setSourceFilter("all");
    setChangeFilter("all");
    setHeatFilter("all");
  }

  function githubMeta(item: DiscoveryItem) {
    const metadata = (item.metadata ?? {}) as Record<string, unknown>;
    const stars = Number(metadata.github_stars_total ?? 0);
    const forks = Number(metadata.github_forks_total ?? 0);
    const watchers = Number(metadata.github_watchers_total ?? 0);
    const starsToday = Number(metadata.github_stars_today ?? 0);
    if (!stars && !forks && !watchers && !starsToday) return null;
    return { stars, forks, watchers, starsToday };
  }

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">实时流</p>
          <h2>进入聚类前的原始素材</h2>
        </div>
        <span className="subtle">{filtered.length} 条</span>
      </div>
      <div className="intel-filter-bar">
        <Search size={14} />
        <input
          type="text"
          placeholder="搜索标题、摘要、来源、平台..."
          value={query}
          onChange={(e) => { setQuery(e.target.value); }}
        />
        <select value={timeFilter} onChange={(e) => setTimeFilter(e.target.value as TimeFilter)}>
          <option value="all">全部时间</option>
          <option value="1h">近 1 小时</option>
          <option value="6h">近 6 小时</option>
          <option value="24h">近 24 小时</option>
          <option value="72h">近 72 小时</option>
        </select>
        <select value={platformFilter} onChange={(e) => setPlatformFilter(e.target.value)}>
          <option value="all">全部平台</option>
          {platformOptions.map((platform) => (
            <option key={platform} value={platform}>{platform}</option>
          ))}
        </select>
        <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
          <option value="all">全部来源</option>
          {sourceOptions.map((source) => (
            <option key={source} value={source}>{source}</option>
          ))}
        </select>
        <select value={changeFilter} onChange={(e) => setChangeFilter(e.target.value as ChangeFilter)}>
          <option value="all">全部变化</option>
          <option value="new_item">本轮新增</option>
          <option value="updated_item">内容更新</option>
          <option value="seen_item">重复出现</option>
        </select>
        <select value={heatFilter} onChange={(e) => setHeatFilter(e.target.value as HeatFilter)}>
          <option value="all">全部热度</option>
          <option value="none">无热度</option>
          <option value="low">1-9</option>
          <option value="mid">10-99</option>
          <option value="high">100+</option>
        </select>
        <button type="button" className="ghost-button compact intel-filter-reset" onClick={resetFilters} title="清空筛选">
          <RotateCcw size={14} />
        </button>
      </div>
      <div className="intel-score-row">
        <span>当前显示 {visible.length}/{filtered.length} 条</span>
        <span>总素材 {items.length} 条</span>
        <span>默认按抓取时间倒序</span>
      </div>
      <div className="intel-list">
        {visible.length ? visible.map((item) => (
          <article key={item.id} className="intel-row-card">
            {(() => {
              const gh = githubMeta(item);
              return (
                <>
            <div className="intel-card-topline">
              <span>{item.source_name}</span>
              <span>{formatRelativeTime(item.collected_at, "刚刚")}</span>
            </div>
            <strong>{item.title}</strong>
            <p>{item.summary}</p>
            <div className="intel-score-row">
              <span>{item.platform}</span>
              <span>
                {item.item_state === "new_item" ? "本轮新增" : item.item_state === "updated_item" ? "内容更新" : "重复出现"}
              </span>
              <span>{formatDateTime(item.published_at, { fallback: "发布时间未知" })}</span>
              <span>热度 {item.engagement_score}</span>
            </div>
            {gh ? (
              <div className="intel-score-row">
                <span>Stars {gh.stars}</span>
                <span>Forks {gh.forks}</span>
                {gh.watchers > 0 ? <span>Watch {gh.watchers}</span> : null}
                {gh.starsToday > 0 ? <span>今日 +{gh.starsToday}</span> : null}
              </div>
            ) : null}
            <a href={item.link} target="_blank" rel="noreferrer">查看原文</a>
                </>
              );
            })()}
          </article>
        )) : (
          <p className="empty-state">
            {items.length && filtered.length === 0 ? "当前筛选条件下没有匹配的素材。" : "本轮还没有抓到新的素材。"}
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
