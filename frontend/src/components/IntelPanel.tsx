import { FolderGit2, RadioTower, WavesLadder } from "lucide-react";
import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { HotClusterCard, IntelSnapshot, IntelStreamItem, PublishMode, SourceConnector } from "../types";
import { CandidateBadge, SourceHealthBadge, StageBadge } from "./StatusBadge";
import { SourcesPanel } from "./SourcesPanel";

interface IntelPanelProps {
  intel: IntelSnapshot;
  currentMode: PublishMode;
  syncing: boolean;
  savingSourceKey?: string | null;
  syncingSourceKey?: string | null;
  busyCandidateId?: string | null;
  onSyncSources: () => Promise<void>;
  onSyncSource: (sourceKey: string) => Promise<void>;
  onSaveSource: (
    sourceKey: string,
    payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">
  ) => Promise<void>;
  onCreateDraft: (candidateId: string, mode: PublishMode) => Promise<void>;
  onOpenCandidate: (candidateId: string) => void;
  onOpenDraft: (draftId: string) => void;
}

type IntelSectionKey = "stream" | "clusters" | "github" | "sources";
type IntelStatusFilter = "all" | "candidate" | "draft" | "only_intel";
type IntelTimeFilter = "all" | "1h" | "6h" | "24h";

function actionLabel(item: { candidate_id?: string | null; draft_id?: string | null }) {
  if (item.draft_id) {
    return "查看稿件";
  }
  if (item.candidate_id) {
    return "查看候选";
  }
  return "仅情报";
}

function goToRelated(
  item: { candidate_id?: string | null; draft_id?: string | null },
  onOpenCandidate: (candidateId: string) => void,
  onOpenDraft: (draftId: string) => void
) {
  if (item.draft_id) {
    onOpenDraft(item.draft_id);
    return;
  }
  if (item.candidate_id) {
    onOpenCandidate(item.candidate_id);
  }
}

function withinWindow(value: string | null | undefined, filter: IntelTimeFilter) {
  if (filter === "all") {
    return true;
  }
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) {
    return false;
  }
  const diffMinutes = (Date.now() - date.getTime()) / 60000;
  if (filter === "1h") {
    return diffMinutes <= 60;
  }
  if (filter === "6h") {
    return diffMinutes <= 360;
  }
  return diffMinutes <= 1440;
}

function sourceLabel(item: IntelStreamItem) {
  return item.source_names.length ? item.source_names.join(" / ") : "未知来源";
}

function clusterSourceLabel(item: HotClusterCard) {
  return item.source_names.length ? item.source_names.join(" / ") : "未知来源";
}

export function IntelPanel({
  intel,
  currentMode,
  syncing,
  savingSourceKey,
  syncingSourceKey,
  busyCandidateId,
  onSyncSources,
  onSyncSource,
  onSaveSource,
  onCreateDraft,
  onOpenCandidate,
  onOpenDraft,
}: IntelPanelProps) {
  const [section, setSection] = useState<IntelSectionKey>("stream");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [timeFilter, setTimeFilter] = useState<IntelTimeFilter>("all");
  const [statusFilter, setStatusFilter] = useState<IntelStatusFilter>("all");

  const sourceOptions = useMemo(() => {
    const values = new Set<string>();
    for (const item of intel.stream) {
      item.source_names.forEach((source) => values.add(source));
    }
    return ["all", ...Array.from(values)];
  }, [intel.stream]);

  const filteredStream = useMemo(() => {
    return intel.stream.filter((item) => {
      if (sourceFilter !== "all" && !item.source_names.includes(sourceFilter)) {
        return false;
      }
      if (!withinWindow(item.collected_at, timeFilter)) {
        return false;
      }
      if (statusFilter === "candidate" && !item.candidate_id) {
        return false;
      }
      if (statusFilter === "draft" && !item.draft_id) {
        return false;
      }
      if (statusFilter === "only_intel" && (item.candidate_id || item.draft_id)) {
        return false;
      }
      return true;
    });
  }, [intel.stream, sourceFilter, timeFilter, statusFilter]);

  return (
    <div className="page-content intel-panel-shell">
      <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">情报中心</p>
          <h2>最新情报与来源健康</h2>
          <p className="subtle">
            这里集中看最新流入的信息、当前热点、GitHub 技术信号，以及来源是否稳定。
          </p>
        </div>
      </div>

      <div className="segmented-control intel-sections">
        <button type="button" className={section === "stream" ? "segment-active" : ""} onClick={() => setSection("stream")}>
          实时流
        </button>
        <button type="button" className={section === "clusters" ? "segment-active" : ""} onClick={() => setSection("clusters")}>
          热点簇
        </button>
        <button type="button" className={section === "github" ? "segment-active" : ""} onClick={() => setSection("github")}>
          GitHub
        </button>
        <button type="button" className={section === "sources" ? "segment-active" : ""} onClick={() => setSection("sources")}>
          来源与健康
        </button>
      </div>
      </section>

      {section === "stream" ? (
        <section className="panel">
          <div className="intel-filter-bar">
            <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
              {sourceOptions.map((item) => (
                <option key={item} value={item}>
                  {item === "all" ? "全部来源" : item}
                </option>
              ))}
            </select>
            <select value={timeFilter} onChange={(event) => setTimeFilter(event.target.value as IntelTimeFilter)}>
              <option value="all">全部时间</option>
              <option value="1h">最近 1 小时</option>
              <option value="6h">最近 6 小时</option>
              <option value="24h">最近 24 小时</option>
            </select>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as IntelStatusFilter)}>
              <option value="all">全部状态</option>
              <option value="candidate">已进候选</option>
              <option value="draft">已进稿件</option>
              <option value="only_intel">仅情报未入池</option>
            </select>
            <div className="draft-toolbar-summary">
              <span>当前显示</span>
              <strong>{filteredStream.length}</strong>
              <span>/ {intel.stream.length} 条</span>
            </div>
          </div>

          <div className="intel-list">
            {filteredStream.map((item) => {
              const actionable = Boolean(item.candidate_id || item.draft_id);
              const busy = item.candidate_id ? busyCandidateId === item.candidate_id : false;
              return (
                <article
                  key={item.id}
                  className={`intel-card ${actionable ? "intel-card-actionable" : ""}`}
                  onClick={() => actionable && goToRelated(item, onOpenCandidate, onOpenDraft)}
                  onKeyDown={(event) => {
                    if (actionable && (event.key === "Enter" || event.key === " ")) {
                      event.preventDefault();
                      goToRelated(item, onOpenCandidate, onOpenDraft);
                    }
                  }}
                  role={actionable ? "button" : undefined}
                  tabIndex={actionable ? 0 : undefined}
                >
                  <div className="row-with-badge">
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.summary || "暂无摘要。"}</p>
                    </div>
                    <span className="score-chip">{item.score.toFixed(1)}</span>
                  </div>
                  <div className="intel-meta-grid">
                    <div>
                      <span>来源</span>
                      <strong>{sourceLabel(item)}</strong>
                      <p>{item.source_count} 个来源进入同一事件簇</p>
                    </div>
                    <div>
                      <span>发布时间</span>
                      <strong>{formatDateTime(item.published_at, { fallback: "发布时间未知" })}</strong>
                      <p>{formatRelativeTime(item.published_at, "未知")}</p>
                    </div>
                    <div>
                      <span>采集时间</span>
                      <strong>{formatDateTime(item.collected_at, { fallback: "采集时间未知" })}</strong>
                      <p>{formatRelativeTime(item.collected_at, "未知")}</p>
                    </div>
                    <div>
                      <span>链路状态</span>
                      <div className="intel-badges">
                        {item.candidate_status ? <CandidateBadge status={item.candidate_status} /> : null}
                        {item.draft_stage ? <StageBadge stage={item.draft_stage} /> : null}
                      </div>
                      <p>{item.time_lag_minutes != null ? `采集延迟 ${item.time_lag_minutes} 分钟` : "采集延迟未知"}</p>
                    </div>
                  </div>
                  <div className="intel-footer">
                    <a href={item.link} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()}>
                      查看原文
                    </a>
                    <div className="intel-inline-actions">
                      {item.candidate_id && !item.draft_id ? (
                        <button
                          type="button"
                          className="ghost-button compact"
                          disabled={busy}
                          onClick={(event) => {
                            event.stopPropagation();
                            void onCreateDraft(item.candidate_id!, currentMode);
                          }}
                        >
                          {busy ? "生成中..." : "生成初稿"}
                        </button>
                      ) : null}
                      <span>{actionLabel(item)}</span>
                    </div>
                  </div>
                </article>
              );
            })}
            {!filteredStream.length ? <p className="empty-state">当前筛选条件下没有情报。</p> : null}
          </div>
        </section>
      ) : null}

      {section === "clusters" ? (
        <section className="panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">热点簇</p>
              <h2>当前最值得继续跟的事件</h2>
            </div>
            <div className="panel-icon">
              <WavesLadder size={18} />
            </div>
          </div>
          <div className="mini-list">
          {intel.clusters.map((cluster) => (
            <article key={cluster.cluster_id} className="mini-row stacked">
              <div className="row-with-badge">
                <strong>{cluster.title}</strong>
                <span className="score-chip">{cluster.final_score.toFixed(1)}</span>
              </div>
              <p>{cluster.member_count} 条成员，覆盖 {clusterSourceLabel(cluster)}</p>
              <p>
                最近发布时间：{formatDateTime(cluster.published_at, { fallback: "发布时间未知" })} · 最近采集：
                {formatDateTime(cluster.latest_collected_at, { fallback: "采集时间未知" })}
              </p>
              <p>{cluster.signals.length ? cluster.signals.join("；") : "暂无额外信号说明。"}</p>
            </article>
          ))}
          {!intel.clusters.length ? <p className="empty-state">暂无热点事件簇。</p> : null}
          </div>
        </section>
      ) : null}

      {section === "github" ? (
        <section className="panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">GitHub</p>
              <h2>技术热度信号</h2>
            </div>
            <div className="panel-icon">
              <FolderGit2 size={18} />
            </div>
          </div>
          <div className="mini-list">
          {intel.github_watch.map((item) => {
            const actionable = Boolean(item.candidate_id || item.draft_id);
            return (
              <article
                key={item.id}
                className={`mini-row stacked ${actionable ? "intel-card-actionable" : ""}`}
                onClick={() => actionable && goToRelated(item, onOpenCandidate, onOpenDraft)}
                onKeyDown={(event) => {
                  if (actionable && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    goToRelated(item, onOpenCandidate, onOpenDraft);
                  }
                }}
                role={actionable ? "button" : undefined}
                tabIndex={actionable ? 0 : undefined}
              >
                <div className="row-with-badge">
                  <div className="intel-row-title">
                    <FolderGit2 size={16} />
                    <strong>{item.repo_name}</strong>
                  </div>
                  <span className="score-chip">Star {item.stars_signal}</span>
                </div>
                <p>{item.summary || "暂无说明。"}</p>
                <p>
                  来源 {item.source_name} · 发布时间 {formatDateTime(item.published_at, { fallback: "未知" })} · 采集{" "}
                  {formatDateTime(item.collected_at, { fallback: "未知" })}
                </p>
                <div className="intel-badges">
                  {item.candidate_status ? <CandidateBadge status={item.candidate_status} /> : null}
                  {item.draft_stage ? <StageBadge stage={item.draft_stage} /> : null}
                </div>
              </article>
            );
          })}
          {!intel.github_watch.length ? <p className="empty-state">暂无 GitHub 技术信号。</p> : null}
          </div>
        </section>
      ) : null}

      {section === "sources" ? (
        <div className="page-content">
          <div className="intel-health-summary">
            <article className="runtime-card">
              <span>来源总数</span>
              <strong>{intel.source_health.length}</strong>
              <p>当前情报系统已接入来源</p>
            </article>
            <article className="runtime-card">
              <span>健康来源</span>
              <strong>{intel.source_health.filter((item) => item.health_status === "healthy").length}</strong>
              <p>可持续自动抓取</p>
            </article>
            <article className="runtime-card">
              <span>告警来源</span>
              <strong>{intel.source_health.filter((item) => item.health_status === "warning").length}</strong>
              <p>需要观察</p>
            </article>
            <article className="runtime-card">
              <span>异常来源</span>
              <strong>{intel.source_health.filter((item) => item.health_status === "error").length}</strong>
              <p>建议优先处理</p>
            </article>
          </div>

          <div className="source-health-list">
            {intel.source_health
              .filter((item) => item.health_status === "warning" || item.health_status === "error")
              .slice(0, 6)
              .map((item) => (
                <article key={item.key} className="mini-row stacked">
                  <div className="row-with-badge">
                    <div className="intel-row-title">
                      <RadioTower size={16} />
                      <strong>{item.name}</strong>
                    </div>
                    <SourceHealthBadge health={item.health_status} />
                  </div>
                  <p>{item.health_detail || "暂无详细状态。"}</p>
                  <p>上次同步：{formatDateTime(item.last_synced_at, { fallback: "暂无" })}</p>
                </article>
              ))}
          </div>

          <SourcesPanel
            sources={intel.source_health}
            syncing={syncing}
            savingSourceKey={savingSourceKey}
            syncingSourceKey={syncingSourceKey}
            onSync={onSyncSources}
            onSyncOne={onSyncSource}
            onSave={onSaveSource}
          />
        </div>
      ) : null}
    </div>
  );
}
