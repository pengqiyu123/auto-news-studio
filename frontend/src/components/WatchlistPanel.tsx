import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { CandidateTopic, PublishMode } from "../types";

interface WatchlistPanelProps {
  candidates: CandidateTopic[];
  busyCandidateId?: string | null;
  onCreateDraft: (candidateId: string, mode: PublishMode) => Promise<void>;
}

export function WatchlistPanel({ candidates, busyCandidateId, onCreateDraft }: WatchlistPanelProps) {
  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">重点观察</p>
          <h2>人工标记继续跟的事件</h2>
        </div>
      </div>
      <div className="intel-list">
        {candidates.length ? candidates.map((candidate) => (
          <article key={candidate.id} className="intel-row-card">
            <div className="intel-card-topline">
              <span className="status-badge status-success">{candidate.status}</span>
              <span>{candidate.source_count} 来源 / {candidate.score.toFixed(1)} 分</span>
            </div>
            <strong>{candidate.title}</strong>
            <p>{candidate.summary}</p>
            <div className="intel-score-row">
              <span>{formatDateTime(candidate.published_at, { fallback: "发布时间未知" })}</span>
              <span>{formatRelativeTime(candidate.collected_at, "刚抓到")}</span>
              <span>{candidate.freshness_bucket}</span>
            </div>
            <p className="subtle">{candidate.rationale}</p>
            <div className="intel-inline-actions">
              {candidate.evidence_links[0] ? <a href={candidate.evidence_links[0]} target="_blank" rel="noreferrer">查看证据</a> : null}
              <button
                type="button"
                className="primary-button"
                disabled={busyCandidateId === candidate.id || candidate.draft_exists}
                onClick={() => void onCreateDraft(candidate.id, candidate.recommended_mode)}
              >
                {busyCandidateId === candidate.id ? "生成中..." : candidate.draft_exists ? "已生成稿件" : "生成稿件"}
              </button>
            </div>
          </article>
        )) : <p className="empty-state">还没有加入重点观察的事件。</p>}
      </div>
    </section>
  );
}
