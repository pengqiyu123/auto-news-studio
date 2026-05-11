import { Copy, FileSearch, RefreshCcw, RadioTower, Trash2 } from "lucide-react";
import { useMemo } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { BriefItem, BriefRecordCounts, BriefRecordException, BriefRecordStatus } from "../types";
import { PaginationControls } from "./PaginationControls";

interface BriefTableProps {
  briefs: BriefItem[];
  page: number;
  pageSize: number;
  total: number;
  view: BriefWorkbenchView;
  searchTerm: string;
  recordCounts: BriefRecordCounts;
  loading?: boolean;
  busyBriefId?: string | null;
  onViewChange: (view: BriefWorkbenchView) => void;
  onSearchChange: (value: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onRefreshBrief: (eventId: string) => Promise<void>;
  onCopyBrief: (brief: BriefItem) => Promise<void>;
  onCopyPackage: (briefId: string) => Promise<void>;
  onSyncBrief: (brief: BriefItem) => Promise<void>;
  onDeleteBrief: (brief: BriefItem) => Promise<void>;
}

type BriefWorkbenchView = "all" | "local_only" | "draft_synced" | "published" | "exceptions";

const recordStatusLabel: Record<BriefRecordStatus, string> = {
  local_only: "仅本地",
  draft_synced: "已同步草稿箱",
  published: "已同步发表记录",
};

const briefLevelLabel: Record<BriefItem["brief_level"], string> = {
  rule: "传统简报",
  enhanced: "增强简报",
  article: "AI 长文",
};

const recordStatusTone: Record<BriefRecordStatus, "success" | "warning" | "info"> = {
  local_only: "warning",
  draft_synced: "info",
  published: "success",
};

const recordExceptionLabel: Record<BriefRecordException, string> = {
  pending_confirmation: "待确认",
  draft_check_failed: "草稿箱检查失败",
  publish_check_failed: "发表记录检查失败",
  draft_missing: "草稿已丢失",
};

function matchesView(brief: BriefItem, view: BriefWorkbenchView) {
  if (view === "all") return true;
  if (view === "exceptions") return Boolean(brief.record_exception);
  return brief.record_status === view;
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).trim()}...`;
}

function detailExcerpt(brief: BriefItem): string {
  const text = brief.wechat_markdown || brief.one_line || "";
  return truncate(text.replace(/^#+\s*/gm, "").replace(/\s+/g, " ").trim(), 240) || "暂无正文摘要。";
}

export function BriefTable({
  briefs,
  page,
  pageSize,
  total,
  view,
  searchTerm,
  recordCounts,
  loading = false,
  busyBriefId,
  onViewChange,
  onSearchChange,
  onPageChange,
  onPageSizeChange,
  onRefreshBrief,
  onCopyBrief,
  onCopyPackage,
  onSyncBrief,
  onDeleteBrief,
}: BriefTableProps) {
  const filtered = useMemo(
    () => [...briefs].sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()),
    [briefs],
  );

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">简报</p>
          <h2>查看已经整理好的简报与来源包</h2>
        </div>
      </div>

      <div className="segmented-control draft-workbench-tabs">
        <button type="button" className={view === "all" ? "segment-active" : ""} onClick={() => onViewChange("all")}>
          全部
          <strong>{recordCounts.all}</strong>
        </button>
        <button type="button" className={view === "local_only" ? "segment-active" : ""} onClick={() => onViewChange("local_only")}>
          仅本地
          <strong>{recordCounts.local_only}</strong>
        </button>
        <button type="button" className={view === "draft_synced" ? "segment-active" : ""} onClick={() => onViewChange("draft_synced")}>
          已同步草稿箱
          <strong>{recordCounts.draft_synced}</strong>
        </button>
        <button type="button" className={view === "published" ? "segment-active" : ""} onClick={() => onViewChange("published")}>
          已同步发表记录
          <strong>{recordCounts.published}</strong>
        </button>
        <button type="button" className={view === "exceptions" ? "segment-active" : ""} onClick={() => onViewChange("exceptions")}>
          待确认
          <strong>{recordCounts.exceptions}</strong>
        </button>
      </div>

      <div className="draft-toolbar">
        <label className="draft-search">
          <FileSearch size={16} />
          <input
            value={searchTerm}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜索标题、结论、价值判断"
          />
        </label>
        <div className="draft-toolbar-summary">
          <span>当前显示</span>
          <strong>{filtered.length}</strong>
          <span>/ {total} 条</span>
        </div>
      </div>

      <PaginationControls
        page={page}
        pageSize={pageSize}
        total={total}
        currentCount={filtered.length}
        itemLabel="条简报"
        loading={loading}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />

      <div className="intel-list">
        {filtered.length ? filtered.map((brief) => {
          const busy = busyBriefId === brief.id;
          return (
            <article key={brief.id} className="intel-row-card">
              <div className="intel-card-topline">
                <span className={`status-badge status-${recordStatusTone[brief.record_status]}`}>
                  {recordStatusLabel[brief.record_status]}
                </span>
                {brief.record_exception ? (
                  <span className="status-badge status-danger">{recordExceptionLabel[brief.record_exception]}</span>
                ) : null}
                <span>{briefLevelLabel[brief.brief_level]}</span>
              </div>
              <strong>{brief.title}</strong>
              <p>{truncate(brief.one_line || "尚未生成一句话结论。", 160)}</p>
              <div className="intel-score-row">
                <span>{formatRelativeTime(brief.updated_at, "刚更新")}</span>
                <span>草稿箱: {brief.draft_remote_updated_at ? `已命中 ${formatDateTime(brief.draft_remote_updated_at, { fallback: "暂无" })}` : "未命中"}</span>
                <span>发表记录: {brief.publish_record_published_at ? brief.publish_record_published_at : "未命中"}</span>
              </div>
              <div className="intel-score-row">
                <span>{brief.facts.length} 条事实</span>
                <span>{brief.source_links.length} 条来源</span>
                <span>{brief.quotes.length} 条引文</span>
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
              <details className="draft-list-block">
                <summary>文章详情</summary>
                <p>{detailExcerpt(brief)}</p>
              </details>
              {brief.last_error ? <span className="error-note">{brief.last_error}</span> : null}
              <div className="intel-inline-actions">
                <span>{formatDateTime(brief.updated_at, { fallback: "暂无" })}</span>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => {
                  if (!window.confirm("确认重新生成简报？将消耗 LLM token。")) return;
                  void onRefreshBrief(brief.event_id);
                }}>
                  <RefreshCcw size={14} />
                  重新生成
                </button>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onSyncBrief(brief)}>
                  <RadioTower size={14} />
                  同步到微信草稿箱
                </button>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onCopyBrief(brief)}>
                  <Copy size={14} />
                  复制简报
                </button>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onCopyPackage(brief.id)}>
                  <Copy size={14} />
                  复制来源包
                </button>
                <button type="button" className="ghost-button compact danger" disabled={busy} onClick={() => void onDeleteBrief(brief)}>
                  <Trash2 size={14} />
                  删除简报
                </button>
              </div>
            </article>
          );
        }) : <p className="empty-state">当前筛选条件下没有简报。</p>}
      </div>
    </section>
  );
}
