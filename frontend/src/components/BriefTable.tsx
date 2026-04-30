import { Copy, FileSearch, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { BriefItem } from "../types";

interface BriefTableProps {
  briefs: BriefItem[];
  busyBriefId?: string | null;
  onRefreshBrief: (eventId: string) => Promise<void>;
  onCopyBrief: (brief: BriefItem) => Promise<void>;
  onCopyPackage: (briefId: string) => Promise<void>;
}

type BriefWorkbenchView = "all" | "prepared" | "synced" | "failed";

function matchesView(brief: BriefItem, view: BriefWorkbenchView) {
  if (view === "all") return true;
  if (view === "prepared") return brief.stage === "prepared";
  if (view === "synced") return brief.stage === "synced";
  return brief.stage === "failed" || Boolean(brief.last_error);
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).trim()}...`;
}

export function BriefTable({
  briefs,
  busyBriefId,
  onRefreshBrief,
  onCopyBrief,
  onCopyPackage,
}: BriefTableProps) {
  const [view, setView] = useState<BriefWorkbenchView>("all");
  const [searchTerm, setSearchTerm] = useState("");

  const viewCounts = useMemo(
    () => ({
      all: briefs.length,
      prepared: briefs.filter((item) => matchesView(item, "prepared")).length,
      synced: briefs.filter((item) => matchesView(item, "synced")).length,
      failed: briefs.filter((item) => matchesView(item, "failed")).length,
    }),
    [briefs],
  );

  const filtered = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    return briefs
      .filter((item) => {
        const matchesStatus = matchesView(item, view);
        const matchesSearch =
          !keyword
          || item.title.toLowerCase().includes(keyword)
          || item.one_line.toLowerCase().includes(keyword)
          || item.why_it_matters.toLowerCase().includes(keyword);
        return matchesStatus && matchesSearch;
      })
      .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
  }, [briefs, searchTerm, view]);

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">简报</p>
          <h2>查看已经整理好的简报与来源包</h2>
        </div>
      </div>

      <div className="segmented-control draft-workbench-tabs">
        <button type="button" className={view === "all" ? "segment-active" : ""} onClick={() => setView("all")}>
          全部
          <strong>{viewCounts.all}</strong>
        </button>
        <button type="button" className={view === "prepared" ? "segment-active" : ""} onClick={() => setView("prepared")}>
          待同步
          <strong>{viewCounts.prepared}</strong>
        </button>
        <button type="button" className={view === "synced" ? "segment-active" : ""} onClick={() => setView("synced")}>
          已进草稿箱
          <strong>{viewCounts.synced}</strong>
        </button>
        <button type="button" className={view === "failed" ? "segment-active" : ""} onClick={() => setView("failed")}>
          失败
          <strong>{viewCounts.failed}</strong>
        </button>
      </div>

      <div className="draft-toolbar">
        <label className="draft-search">
          <FileSearch size={16} />
          <input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="搜索标题、结论、价值判断"
          />
        </label>
        <div className="draft-toolbar-summary">
          <span>当前显示</span>
          <strong>{filtered.length}</strong>
          <span>/ {briefs.length} 条</span>
        </div>
      </div>

      <div className="intel-list">
        {filtered.length ? filtered.map((brief) => {
          const busy = busyBriefId === brief.id;
          return (
            <article key={brief.id} className="intel-row-card">
              <div className="intel-card-topline">
                <span className={`status-badge status-${brief.stage === "synced" ? "success" : brief.stage === "failed" ? "danger" : "warning"}`}>
                  {brief.stage}
                </span>
                <span>{brief.brief_level === "enhanced" ? "增强简报" : "规则简报"}</span>
              </div>
              <p className="subtle">
                {brief.brief_level === "enhanced" ? "AI 已基于正文全文生成增强简报。" : "当前为规则简报，AI 未参与或增强失败。"}
              </p>
              <strong>{brief.title}</strong>
              <p>{truncate(brief.one_line || "尚未生成一句话结论。", 160)}</p>
              <div className="intel-score-row">
                <span>{brief.facts.length} 条事实</span>
                <span>{brief.source_links.length} 条来源</span>
                <span>{brief.quotes.length} 条引文</span>
                <span>{formatRelativeTime(brief.updated_at, "刚更新")}</span>
              </div>
              <div className="draft-list-block">
                <span>为什么值得关注</span>
                <p>{brief.why_it_matters || "当前仍以规则简报为主，可继续补充判断。"}</p>
              </div>
              {!!brief.facts.length ? (
                <div className="draft-list-block">
                  <span>核心事实</span>
                  <ul>
                    {brief.facts.slice(0, 4).map((fact) => (
                      <li key={fact}>{fact}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {brief.last_error ? <span className="error-note">{brief.last_error}</span> : null}
              <div className="intel-inline-actions">
                <span>{formatDateTime(brief.updated_at, { fallback: "暂无" })}</span>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onRefreshBrief(brief.event_id)}>
                  <RefreshCcw size={14} />
                  重新生成
                </button>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onCopyBrief(brief)}>
                  <Copy size={14} />
                  复制简报
                </button>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onCopyPackage(brief.id)}>
                  <Copy size={14} />
                  复制来源包
                </button>
              </div>
            </article>
          );
        }) : <p className="empty-state">当前筛选条件下没有简报。</p>}
      </div>
    </section>
  );
}
