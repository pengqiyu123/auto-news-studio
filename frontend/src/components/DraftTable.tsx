import { useEffect, useMemo, useState } from "react";
import { CheckCheck, Eye, Pencil, RefreshCcw, Search, SendHorizontal, Trash2, UploadCloud } from "lucide-react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { AuditStatus, DraftItem } from "../types";
import { AuditBadge, StageBadge } from "./StatusBadge";

interface DraftTableProps {
  drafts: DraftItem[];
  busyDraftId?: string | null;
  highlightDraftId?: string | null;
  pendingDraftTitle?: string | null;
  onRegenerate: (draftId: string) => Promise<void>;
  onApprove: (draftId: string, approved: boolean) => Promise<void>;
  onSyncDraft: (draftId: string) => Promise<void>;
  onPreview: (draftId: string) => Promise<void>;
  onPublish: (draftId: string) => Promise<void>;
  onDelete: (draftId: string) => Promise<void>;
  onEdit: (draftId: string) => void;
}

type DraftSortKey = "updated_at" | "title" | "source_count";
type DraftWorkbenchView = "all" | "active" | "synced" | "published" | "failed";

function matchesWorkbenchView(draft: DraftItem, view: DraftWorkbenchView): boolean {
  const hasFailure = Boolean(draft.last_error) && draft.pipeline_stage !== "published";
  if (view === "all") {
    return true;
  }
  if (view === "failed") {
    return draft.pipeline_stage === "failed" || hasFailure;
  }
  if (view === "published") {
    return draft.pipeline_stage === "published";
  }
  if (view === "synced") {
    return draft.pipeline_stage === "draft_synced" && !hasFailure;
  }
  return ["drafted", "preview_ready", "approved"].includes(draft.pipeline_stage) && !hasFailure;
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit).trim()}...`;
}

function previewParagraphs(draft: DraftItem): string[] {
  const blocks = draft.body_blocks
    .map((block) => block.content.trim())
    .filter(Boolean)
    .slice(0, 2);
  if (blocks.length) {
    return blocks.map((block) => truncate(block, 130));
  }
  return draft.markdown
    .split("\n\n")
    .map((segment) => segment.replace(/^#+\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 2)
    .map((segment) => truncate(segment, 130));
}

function pendingImageCount(draft: DraftItem): number {
  return draft.image_slots.filter((slot) => slot.required_image && !slot.fulfilled).length;
}

export function DraftTable({
  drafts,
  busyDraftId,
  highlightDraftId,
  pendingDraftTitle,
  onRegenerate,
  onApprove,
  onSyncDraft,
  onPreview,
  onPublish,
  onDelete,
  onEdit
}: DraftTableProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [workbenchView, setWorkbenchView] = useState<DraftWorkbenchView>("all");
  const [auditFilter, setAuditFilter] = useState<AuditStatus | "all">("all");
  const [sortBy, setSortBy] = useState<DraftSortKey>("updated_at");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const highlightedDraft = useMemo(
    () => drafts.find((draft) => draft.id === highlightDraftId) ?? null,
    [drafts, highlightDraftId],
  );

  const viewCounts = useMemo(
    () => ({
      all: drafts.length,
      active: drafts.filter((draft) => matchesWorkbenchView(draft, "active")).length,
      synced: drafts.filter((draft) => matchesWorkbenchView(draft, "synced")).length,
      published: drafts.filter((draft) => matchesWorkbenchView(draft, "published")).length,
      failed: drafts.filter((draft) => matchesWorkbenchView(draft, "failed")).length,
    }),
    [drafts],
  );

  useEffect(() => {
    if (!highlightDraftId) {
      return;
    }
    setSearchTerm("");
    setAuditFilter("all");
    setSortBy("updated_at");
    setConfirmDeleteId(null);
    if (highlightedDraft && matchesWorkbenchView(highlightedDraft, "active")) {
      setWorkbenchView("active");
      return;
    }
    setWorkbenchView("all");
  }, [highlightDraftId, highlightedDraft]);

  useEffect(() => {
    if (!highlightDraftId) {
      return;
    }
    const element = document.getElementById(`draft-${highlightDraftId}`);
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightDraftId]);

  const filteredDrafts = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    const next = drafts.filter((draft) => {
      const matchesView = matchesWorkbenchView(draft, workbenchView);
      const matchesSearch =
        !keyword ||
        draft.title.toLowerCase().includes(keyword) ||
        draft.summary.toLowerCase().includes(keyword) ||
        draft.cover_suggestion.toLowerCase().includes(keyword) ||
        (draft.reader_summary ?? "").toLowerCase().includes(keyword);
      const matchesAudit = auditFilter === "all" || draft.audit_status === auditFilter;
      return matchesView && matchesSearch && matchesAudit;
    });

    next.sort((left, right) => {
      if (sortBy === "title") {
        return left.title.localeCompare(right.title, "zh-CN");
      }
      if (sortBy === "source_count") {
        return right.source_count - left.source_count;
      }
      return new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime();
    });

    return next;
  }, [drafts, searchTerm, workbenchView, auditFilter, sortBy]);

  async function handleDelete(draft: DraftItem) {
    if (confirmDeleteId !== draft.id) {
      setConfirmDeleteId(draft.id);
      return;
    }
    setConfirmDeleteId(null);
    await onDelete(draft.id);
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">稿件工作台</p>
          <h2>正式稿、编辑信息和微信状态都在这里汇总</h2>
          <p className="subtle">保留排序和筛选，但默认先看正式稿，再看内部编辑信息和微信链路状态。</p>
        </div>
      </div>

      {pendingDraftTitle ? (
        <div className="setup-banner" style={{ marginBottom: 16 }}>
          <strong>AI 正在生成稿件</strong>
          <p>正在整理《{pendingDraftTitle}》的写稿简报并生成初稿，完成后会自动定位到新稿件。</p>
        </div>
      ) : null}

      {!pendingDraftTitle && highlightDraftId ? (
        <div className="setup-banner" style={{ marginBottom: 16 }}>
          <strong>新稿件已就位</strong>
          <p>
            {highlightedDraft
              ? `《${highlightedDraft.title}》已生成完成，并且已经自动定位到这篇稿件。`
              : "已自动定位到刚生成的稿件，可以直接编辑、重生成或推进到草稿箱。"}
          </p>
        </div>
      ) : null}

      <div className="segmented-control draft-workbench-tabs">
        <button type="button" className={workbenchView === "all" ? "segment-active" : ""} onClick={() => setWorkbenchView("all")}>
          全部
          <strong>{viewCounts.all}</strong>
        </button>
        <button type="button" className={workbenchView === "active" ? "segment-active" : ""} onClick={() => setWorkbenchView("active")}>
          进行中
          <strong>{viewCounts.active}</strong>
        </button>
        <button type="button" className={workbenchView === "synced" ? "segment-active" : ""} onClick={() => setWorkbenchView("synced")}>
          草稿箱记录
          <strong>{viewCounts.synced}</strong>
        </button>
        <button type="button" className={workbenchView === "published" ? "segment-active" : ""} onClick={() => setWorkbenchView("published")}>
          已发布
          <strong>{viewCounts.published}</strong>
        </button>
        <button type="button" className={workbenchView === "failed" ? "segment-active" : ""} onClick={() => setWorkbenchView("failed")}>
          失败
          <strong>{viewCounts.failed}</strong>
        </button>
      </div>

      <div className="draft-toolbar">
        <label className="draft-search">
          <Search size={16} />
          <input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="搜索标题、摘要、封面建议"
          />
        </label>
        <select value={auditFilter} onChange={(event) => setAuditFilter(event.target.value as AuditStatus | "all")}>
          <option value="all">全部审核状态</option>
          <option value="pending">待审核</option>
          <option value="approved">已通过</option>
          <option value="rejected">已驳回</option>
          <option value="not_required">免审核</option>
        </select>
        <select value={sortBy} onChange={(event) => setSortBy(event.target.value as DraftSortKey)}>
          <option value="updated_at">按最近更新排序</option>
          <option value="source_count">按来源数排序</option>
          <option value="title">按标题排序</option>
        </select>
        <div className="draft-toolbar-summary">
          <span>当前显示</span>
          <strong>{filteredDrafts.length}</strong>
          <span>/ {drafts.length} 篇</span>
        </div>
      </div>

      <div className="table-shell">
        <table className="draft-table draft-table-wide">
          <thead>
            <tr>
              <th>稿件内容</th>
              <th>阶段</th>
              <th>审核</th>
              <th>更新时间</th>
              <th>动作</th>
            </tr>
          </thead>
          <tbody>
            {filteredDrafts.map((draft) => {
              const busy = busyDraftId === draft.id;
              const isPublished = draft.pipeline_stage === "published";
              const isDeleteConfirming = confirmDeleteId === draft.id;
              const deleteHint = draft.wechat_draft_id
                ? "仅删除本地记录，不会删除微信草稿箱中的稿件，是否继续？"
                : "确认删除这篇稿件？";
              const missingImages = pendingImageCount(draft);
              const articlePreview = previewParagraphs(draft);
              const evidenceCount = draft.brief?.evidence_links?.length ?? draft.evidence_links.length;
              const displayedSummary = truncate(draft.reader_summary || draft.summary, 150);
              return (
                <tr key={draft.id} id={`draft-${draft.id}`} className={highlightDraftId === draft.id ? "focus-row" : ""}>
                  <td>
                    <div className="draft-layout">
                      <section className="draft-section-card">
                        <div className="draft-section-head">
                          <span className="draft-section-label">正式稿</span>
                          <span className="draft-chip">{draft.article_variant === "flash_explainer" ? "快讯解读" : "正式稿"}</span>
                        </div>
                        <strong className="draft-article-title">{draft.title}</strong>
                        <p className="draft-reader-summary">{displayedSummary}</p>
                        <div className="draft-time-grid">
                          <div className="time-cell">
                            <span>发布时间</span>
                            <strong>{draft.brief?.time_context?.published_at_label ?? "发布时间未知"}</strong>
                          </div>
                          <div className="time-cell">
                            <span>采集时间</span>
                            <strong>{draft.brief?.time_context?.collected_at_label ?? "采集时间未知"}</strong>
                          </div>
                        </div>
                        <div className="draft-preview-stack">
                          {articlePreview.map((paragraph) => (
                            <p key={paragraph}>{paragraph}</p>
                          ))}
                        </div>
                      </section>

                      <section className="draft-section-card">
                        <div className="draft-section-head">
                          <span className="draft-section-label">编辑信息</span>
                          <span className="draft-chip muted">{draft.source_count} 个来源</span>
                        </div>
                        <div className="draft-meta-grid">
                          <div>
                            <span>一句话判断</span>
                            <strong>{draft.brief?.event_judgement ?? "待补充"}</strong>
                          </div>
                          <div>
                            <span>证据链接</span>
                            <strong>{evidenceCount} 条</strong>
                          </div>
                        </div>
                        {!!draft.brief?.facts?.length ? (
                          <div className="draft-list-block">
                            <span>核心事实</span>
                            <ul>
                              {draft.brief.facts.slice(0, 4).map((fact) => (
                                <li key={fact}>{fact}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {!!draft.title_options.length ? (
                          <div className="draft-list-block">
                            <span>备选标题</span>
                            <ul>
                              {draft.title_options.slice(0, 3).map((option) => (
                                <li key={option}>{option}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {!!draft.editor_notes.length ? (
                          <div className="draft-list-block">
                            <span>编辑提示</span>
                            <ul>
                              {draft.editor_notes.slice(0, 4).map((note) => (
                                <li key={note}>{note}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {draft.risk_flags.length ? (
                          <span className="warning-note">风险提醒：{draft.risk_flags.join("、")}</span>
                        ) : null}
                      </section>

                      <section className="draft-section-card">
                        <div className="draft-section-head">
                          <span className="draft-section-label">微信状态</span>
                          <span className={`draft-chip ${missingImages ? "danger" : "success"}`}>
                            {missingImages ? "待补图" : "可预览"}
                          </span>
                        </div>
                        <div className="draft-meta-grid">
                          <div>
                            <span>草稿箱状态</span>
                            <strong>{draft.wechat_draft_id ?? "未同步"}</strong>
                          </div>
                          <div>
                            <span>发布模式</span>
                            <strong>{draft.publish_mode}</strong>
                          </div>
                        </div>
                        {!!draft.image_slots.length ? (
                          <div className="draft-list-block">
                            <span>图片槽位</span>
                            <ul>
                              {draft.image_slots.map((slot) => (
                                <li key={slot.slot_id}>
                                  {slot.label} · {slot.suggestion}
                                  {slot.required_image && !slot.fulfilled ? "（待补）" : ""}
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {!!draft.blocked_reasons.length ? (
                          <span className="warning-note">阻断原因：{draft.blocked_reasons.join("、")}</span>
                        ) : null}
                        {draft.last_error ? <span className="error-note">{draft.last_error}</span> : null}
                      </section>
                    </div>
                  </td>
                  <td><StageBadge stage={draft.pipeline_stage} /></td>
                  <td><AuditBadge status={draft.audit_status} /></td>
                  <td>
                    <div className="time-cell">
                      <strong>{formatDateTime(draft.updated_at, { fallback: "暂无" })}</strong>
                      <span>{formatRelativeTime(draft.updated_at)}</span>
                    </div>
                  </td>
                  <td>
                    <div className="table-actions wrap-actions">
                      <button type="button" disabled={busy} onClick={() => onEdit(draft.id)}>
                        <Pencil size={14} />
                        编辑
                      </button>
                      <button type="button" disabled={busy} onClick={() => void onRegenerate(draft.id)}>
                        <RefreshCcw size={14} />
                        重生成
                      </button>
                      <button type="button" disabled={busy} onClick={() => void onApprove(draft.id, true)}>
                        <CheckCheck size={14} />
                        通过
                      </button>
                      <button type="button" disabled={busy} onClick={() => void onSyncDraft(draft.id)}>
                        <UploadCloud size={14} />
                        草稿箱
                      </button>
                      <button type="button" disabled={busy} onClick={() => void onPreview(draft.id)}>
                        <Eye size={14} />
                        预览
                      </button>
                      <button type="button" disabled={busy} onClick={() => void onPublish(draft.id)}>
                        <SendHorizontal size={14} />
                        推进发布
                      </button>
                      {!isPublished ? (
                        <button type="button" disabled={busy} onClick={() => void handleDelete(draft)}>
                          <Trash2 size={14} />
                          {busy ? "删除中..." : isDeleteConfirming ? "确认删除？" : "删除"}
                        </button>
                      ) : null}
                    </div>
                    {isDeleteConfirming ? <span className="draft-delete-hint">{deleteHint}</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!filteredDrafts.length ? <p className="empty-state table-empty">当前筛选条件下没有稿件。</p> : null}
      </div>
    </section>
  );
}
