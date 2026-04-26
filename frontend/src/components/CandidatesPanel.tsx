import { FilePenLine } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { formatDateTime } from "../lib/time";
import type { BatchDraftResult, CandidateTopic, DashboardResponse, PublishMode } from "../types";
import { CandidateBadge } from "./StatusBadge";

interface CandidatesPanelProps {
  candidates: CandidateTopic[];
  dashboard: DashboardResponse;
  busyCandidateId?: string | null;
  batchingDrafts?: boolean;
  batchResult?: BatchDraftResult | null;
  highlightCandidateId?: string | null;
  currentMode: PublishMode;
  onCreateDraft: (candidateId: string, mode: PublishMode) => Promise<void>;
  onBatchCreateDrafts: () => Promise<void>;
}

type CandidateView = "latest" | "recommended";

function freshnessLabel(value: string) {
  const labels: Record<string, string> = {
    fresh: "新鲜",
    recent: "近期",
    aging: "变旧",
    stale: "陈旧",
    unknown: "未知"
  };
  return labels[value] ?? value;
}

export function CandidatesPanel({
  candidates,
  dashboard,
  busyCandidateId,
  batchingDrafts,
  batchResult,
  highlightCandidateId,
  currentMode,
  onCreateDraft,
  onBatchCreateDrafts
}: CandidatesPanelProps) {
  const [view, setView] = useState<CandidateView>("latest");
  const pendingDraftCount = useMemo(() => candidates.filter((item) => !item.draft_exists).length, [candidates]);

  useEffect(() => {
    if (!highlightCandidateId) {
      return;
    }
    const element = document.getElementById(`candidate-${highlightCandidateId}`);
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightCandidateId]);

  const orderedCandidates = useMemo(() => {
    const next = [...candidates];
    if (view === "latest") {
      next.sort((left, right) => {
        const leftAt = left.collected_at ? new Date(left.collected_at).getTime() : 0;
        const rightAt = right.collected_at ? new Date(right.collected_at).getTime() : 0;
        return rightAt - leftAt;
      });
    } else {
      next.sort((left, right) => (right.normalized_score || right.score) - (left.normalized_score || left.score));
    }
    return next;
  }, [candidates, view]);

  const statusCards = [
    { label: "最近一次素材同步", value: formatDateTime(dashboard.runtime_status.last_collect_at) },
    { label: "最近一次候选生成", value: formatDateTime(dashboard.runtime_status.last_candidate_at) },
    { label: "原始素材数", value: String(dashboard.sources.reduce((sum, item) => sum + item.item_count, 0)) },
    { label: "标准化事件数", value: String(dashboard.intel_stream.length) },
    { label: "当前候选数", value: String(candidates.length) },
    { label: "当前运行模式", value: dashboard.current_automation_mode.label }
  ];

  async function handleBatchGenerate() {
    if (pendingDraftCount === 0) {
      return;
    }
    const confirmed = window.confirm(`即将为 ${pendingDraftCount} 条未成稿候选批量生成初稿。建议先确认候选池质量，是否继续？`);
    if (!confirmed) {
      return;
    }
    await onBatchCreateDrafts();
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">候选主题池</p>
          <h2>最近一次同步后的可写主题</h2>
          <p className="subtle">
            这里不是全网原始流，而是经过去重、聚类和评分后的候选池。默认按“最新发现”查看刚进入系统的新主题。
          </p>
        </div>
      </div>

      <div className="candidate-status-strip">
        {statusCards.map((item) => (
          <article key={item.label} className="candidate-status-card">
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </article>
        ))}
      </div>

      <div className="candidate-toolbar">
        <div className="candidate-toolbar-left">
          <div className="segmented-control">
            <button
              type="button"
              className={view === "latest" ? "segment-active" : ""}
              onClick={() => setView("latest")}
            >
              最新发现
            </button>
            <button
              type="button"
              className={view === "recommended" ? "segment-active" : ""}
              onClick={() => setView("recommended")}
            >
              推荐成稿
            </button>
          </div>
          <p className="tiny-meta">
            {view === "latest" ? "按采集时间排序" : "按综合分排序"}，帮助判断这是不是刚抓到的新信息。
          </p>
        </div>
        <button type="button" className="primary-button" disabled={batchingDrafts || pendingDraftCount === 0} onClick={() => void handleBatchGenerate()}>
          <FilePenLine size={16} />
          {batchingDrafts ? "批量生成中..." : `批量生成未成稿候选 (${pendingDraftCount})`}
        </button>
      </div>

      <div className="manual-hint">
        当前会处理所有 `未成稿` 候选，不会自动进入微信链路；批量生成前会先弹出确认。
        {batchResult ? ` 最近一次结果：${batchResult.message}` : ""}
      </div>

      <div className="candidate-list">
        {orderedCandidates.map((candidate) => {
          const busy = busyCandidateId === candidate.id;
          return (
            <article
              key={candidate.id}
              id={`candidate-${candidate.id}`}
              className={`candidate-card ${highlightCandidateId === candidate.id ? "focus-card" : ""}`}
            >
              <div className="candidate-head">
                <div>
                  <div className="row-with-badge">
                    <strong>{candidate.title}</strong>
                    <CandidateBadge status={candidate.status} />
                  </div>
                  <p>{candidate.summary}</p>
                </div>
                <span className="score-chip">{candidate.normalized_score.toFixed(1)}</span>
              </div>

              <div className="candidate-timeline">
                <div>
                  <span>发布时间</span>
                  <strong>{candidate.published_at ? formatDateTime(candidate.published_at) : "发布时间未知"}</strong>
                </div>
                <div>
                  <span>采集时间</span>
                  <strong>{formatDateTime(candidate.collected_at)}</strong>
                </div>
                <div>
                  <span>新鲜度</span>
                  <strong>{freshnessLabel(candidate.freshness_bucket)}</strong>
                </div>
                <div>
                  <span>成稿状态</span>
                  <strong>{candidate.draft_exists ? "已成稿" : "未成稿"}</strong>
                </div>
              </div>

              <div className="meta-grid">
                <div>
                  <span>推荐写法</span>
                  <strong>{candidate.article_type}</strong>
                  <p>{candidate.recommended_angle}</p>
                  <p>事实提要：{candidate.facts.slice(0, 2).join("；") || "暂无"}</p>
                </div>
                <div>
                  <span>证据来源</span>
                  <strong>{candidate.source_names.join(" / ")}</strong>
                  <p>{candidate.source_count} 个来源，证据 {candidate.evidence_links.length} 条</p>
                  <p>{candidate.rationale}</p>
                </div>
              </div>

              <div className="row-with-badge candidate-footer">
                <div className="candidate-mini-meta">
                  <span>热度分 {candidate.score.toFixed(1)}</span>
                  <span>角度 {candidate.angles.map((angle) => angle.name).join(" / ")}</span>
                </div>
                <button
                  type="button"
                  className="primary-button"
                  disabled={busy}
                  onClick={() => void onCreateDraft(candidate.id, currentMode)}
                >
                  <FilePenLine size={16} />
                  {busy ? "生成中..." : candidate.draft_exists ? "重新生成初稿" : "生成初稿"}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
