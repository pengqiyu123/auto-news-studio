import { RotateCcw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PaginationControls } from "../../components/PaginationControls";
import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type { DiscoveryItem } from "../../types";
import type { StreamFilters } from "./state";
type TimeFilter = "all" | "1h" | "6h" | "24h" | "72h";
type ChangeFilter = "all" | "new_item" | "updated_item" | "seen_item";
type HeatFilter = "all" | "none" | "low" | "mid" | "high";
type SortKey = "collected_at" | "engagement_score" | "platform" | "source_name";

const SORT_OPTIONS: Array<{ key: SortKey; label: string }> = [
  { key: "collected_at", label: "抓取时间" },
  { key: "engagement_score", label: "热度" },
  { key: "platform", label: "平台" },
  { key: "source_name", label: "来源" },
];

interface StreamPageProps {
  items: DiscoveryItem[];
  page: number;
  pageSize: number;
  total: number;
  availablePlatforms?: string[];
  availableSources?: string[];
  loading?: boolean;
  onFilterChange: (filters: StreamFilters) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

interface GithubMeta {
  stars: number;
  forks: number;
  watchers: number;
  starsToday: number;
}

function StreamCard({ item }: { item: DiscoveryItem }) {
  function githubMeta(entry: DiscoveryItem): GithubMeta | null {
    const metadata = (entry.metadata ?? {}) as Record<string, unknown>;
    const stars = Number(metadata.github_stars_total ?? 0);
    const forks = Number(metadata.github_forks_total ?? 0);
    const watchers = Number(metadata.github_watchers_total ?? 0);
    const starsToday = Number(metadata.github_stars_today ?? 0);
    if (!stars && !forks && !watchers && !starsToday) return null;
    return { stars, forks, watchers, starsToday };
  }

  const gh = githubMeta(item);

  return (
    <>
      <div className="intel-card-topline">
        <span>
          {item.item_state === "new_item" ? (
            <span className="status-badge status-success status-badge-compact">新</span>
          ) : item.item_state === "updated_item" ? (
            <span className="status-badge status-warning status-badge-compact">更</span>
          ) : null}
          {" "}{item.source_name}
        </span>
        <span>{formatRelativeTime(item.collected_at, "刚刚")}</span>
      </div>
      <strong>{item.title}</strong>
      <p>{item.summary}</p>
      <div className="intel-score-row">
        <span>{item.platform}</span>
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
      {item.entity_names && item.entity_names.length > 0 ? (
        <div className="entity-tag-row entity-tag-row-compact">
          {item.entity_names.slice(0, 3).map((name) => (
            <span key={name} className="entity-tag entity-tag-muted">{name}</span>
          ))}
        </div>
      ) : null}
      <a href={item.link} target="_blank" rel="noreferrer">查看原文</a>
    </>
  );
}
export function StreamPage({
  items,
  page,
  pageSize,
  total,
  availablePlatforms,
  availableSources,
  loading = false,
  onFilterChange,
  onPageChange,
  onPageSizeChange,
}: StreamPageProps) {
  const [query, setQuery] = useState("");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("24h");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [changeFilter, setChangeFilter] = useState<ChangeFilter>("all");
  const [heatFilter, setHeatFilter] = useState<HeatFilter>("all");
  const [sortBy, setSortBy] = useState<SortKey>("collected_at");

  const platformOptions = useMemo(() => {
    const options = (availablePlatforms?.length ? availablePlatforms : items.map((item) => item.platform)).filter(Boolean);
    if (platformFilter !== "all") options.push(platformFilter);
    return Array.from(new Set(options)).sort((a, b) => a.localeCompare(b, "zh-CN"));
  }, [availablePlatforms, items, platformFilter]);

  const sourceOptions = useMemo(() => {
    const options = (availableSources?.length ? availableSources : items.map((item) => item.source_name)).filter(Boolean);
    if (sourceFilter !== "all") options.push(sourceFilter);
    return Array.from(new Set(options)).sort((a, b) => a.localeCompare(b, "zh-CN"));
  }, [availableSources, items, sourceFilter]);

  const filters = useMemo<StreamFilters>(() => {
    const next: StreamFilters = {};
    if (query.trim()) next.q = query.trim();
    if (timeFilter !== "all") next.time_range = timeFilter;
    if (platformFilter !== "all") next.platform = platformFilter;
    if (sourceFilter !== "all") next.source = sourceFilter;
    if (changeFilter !== "all") next.item_state = changeFilter;
    if (heatFilter === "none") {
      next.min_engagement = 0;
      next.max_engagement = 0;
    } else if (heatFilter === "low") {
      next.min_engagement = 1;
      next.max_engagement = 9;
    } else if (heatFilter === "mid") {
      next.min_engagement = 10;
      next.max_engagement = 99;
    } else if (heatFilter === "high") {
      next.min_engagement = 100;
    }
    return next;
  }, [query, timeFilter, platformFilter, sourceFilter, changeFilter, heatFilter]);

  useEffect(() => {
    onFilterChange(filters);
  }, [filters, onFilterChange]);

  const sorted = useMemo(() => {
    return [...items].sort((a, b) => {
      if (sortBy === "collected_at") {
        return (Date.parse(b.collected_at ?? "") || 0) - (Date.parse(a.collected_at ?? "") || 0);
      }
      if (sortBy === "engagement_score") {
        return (Number(b.engagement_score) || 0) - (Number(a.engagement_score) || 0);
      }
      return (a[sortBy] ?? "").toString().localeCompare((b[sortBy] ?? "").toString(), "zh-CN");
    });
  }, [items, sortBy]);

  function resetFilters() {
    setQuery("");
    setTimeFilter("24h");
    setPlatformFilter("all");
    setSourceFilter("all");
    setChangeFilter("all");
    setHeatFilter("all");
  }

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">实时流</p>
          <h2>进入聚类前的原始素材</h2>
        </div>
        <span className="subtle">共 {total} 条素材</span>
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
        <span className="intel-sort-separator" aria-hidden="true">|</span>
        {SORT_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            type="button"
            className={`filter-chip compact ${sortBy === opt.key ? "filter-chip-active" : ""}`}
            onClick={() => setSortBy(opt.key)}
          >
            {opt.label}
          </button>
        ))}
        <button type="button" className="ghost-button compact intel-filter-reset" onClick={resetFilters} title="清空筛选">
          <RotateCcw size={14} />
        </button>
      </div>
      <div className="intel-list">
        {!items.length ? (
          loading ? <div className="skeleton-list">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="skeleton-card">
                <div className="skeleton-line skeleton-short" />
                <div className="skeleton-line skeleton-medium" />
                <div className="skeleton-line skeleton-long" />
              </div>
            ))}
          </div> : <p className="empty-state">当前筛选条件下没有匹配的素材。</p>
        ) : sorted.length ? sorted.map((item) => (
          <article key={item.id} className="intel-row-card">
            <StreamCard item={item} />
          </article>
        )) : (
          <p className="empty-state">本轮还没有抓到新的素材。</p>
        )}
      </div>
      <PaginationControls
        page={page}
        pageSize={pageSize}
        total={total}
        currentCount={items.length}
        filteredCount={sorted.length}
        itemLabel="条素材"
        loading={loading}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />
    </section>
  );
}
