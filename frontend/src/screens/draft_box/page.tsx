import { ExternalLink, RefreshCcw, RotateCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { PaginationControls } from "../../components/PaginationControls";
import { PublishTaskBadge, SourceHealthBadge } from "../../components/StatusBadge";
import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type {
  AgentWorkflowItem,
  BriefItem,
  BrowserSessionState,
  PublishTask,
  WeChatMappingSnapshot,
  WeChatRemoteDraftItem,
} from "../../types";

type MappingView = "wechat_remote" | "local_records" | "pending_confirmation";

const PUBLISH_ACTION_LABELS: Record<string, string> = {
  sync_wechat_draft: "上传到微信草稿箱",
  delete_wechat_draft: "删除微信远端草稿",
  delete_brief: "删除本地简报",
};

const recordStatusLabel: Record<BriefItem["record_status"], string> = {
  local_only: "仅本地",
  draft_synced: "已同步",
  published: "已发表",
};

const recordStatusTone: Record<BriefItem["record_status"], "warning" | "success" | "neutral"> = {
  local_only: "warning",
  draft_synced: "success",
  published: "success",
};

const recordExceptionLabel: Partial<Record<NonNullable<BriefItem["record_exception"]>, string>> = {
  pending_confirmation: "待确认",
  draft_check_failed: "草稿检查失败",
  publish_check_failed: "发表检查失败",
  draft_missing: "草稿丢失",
};

interface DraftBoxPageProps {
  mapping: WeChatMappingSnapshot | null;
  briefs: BriefItem[];
  agentWorkflows: AgentWorkflowItem[];
  localBriefCount: number;
  browserSession: BrowserSessionState | null;
  publishTasks: PublishTask[];
  publishTasksPage: number;
  publishTasksPageSize: number;
  publishTasksTotal: number;
  refreshing: boolean;
  loading?: boolean;
  deletingRemoteId?: string | null;
  loadingBriefDetailId?: string | null;
  onRefresh: () => Promise<void>;
  onDeleteRemote: (remoteId: string) => Promise<void>;
  onSyncBrief: (briefId: string) => Promise<void>;
  onLoadBriefDetail: (briefId: string) => Promise<BriefItem | null>;
  onPublishTasksPageChange: (page: number) => void;
  onPublishTasksPageSizeChange: (pageSize: number) => void;
}

function remoteRowKey(item: WeChatRemoteDraftItem, index: number): string {
  return item.remote_key || item.appmsg_id || item.url || `${item.title}-${index}`;
}

function remoteDeleteTarget(item: WeChatRemoteDraftItem) {
  return item.remote_key || item.appmsg_id || item.url || "";
}

function renderSkeletonCards(count = 4) {
  return (
    <div className="skeleton-list" aria-label="微信草稿箱加载中">
      {Array.from({ length: count }, (_, index) => (
        <div key={`draft-box-skeleton-${index}`} className="skeleton-card">
          <div className="skeleton-line skeleton-short" />
          <div className="skeleton-line skeleton-long" />
          <div className="skeleton-line skeleton-medium" />
        </div>
      ))}
    </div>
  );
}

function briefSeverityClass(brief: BriefItem) {
  if (brief.record_exception || brief.stage === "failed") return "severity-failed";
  if (brief.record_status === "draft_synced") return "severity-synced";
  if (brief.record_status === "published") return "severity-published";
  return "severity-pending";
}

function remoteOnlyItems(mapping: WeChatMappingSnapshot | null, remoteItems: WeChatRemoteDraftItem[]) {
  if (!mapping?.mapping_rows.length) {
    return remoteItems;
  }
  const remoteOnlyKeys = new Set(
    mapping.mapping_rows
      .filter((row) => row.mapping_status === "remote_only" || !row.local_brief_id)
      .map((row) => row.remote_key || row.remote_appmsg_id || row.remote_url || row.remote_title),
  );
  return remoteItems.filter((item, index) => {
    const candidates = [
      item.remote_key,
      item.appmsg_id,
      item.url,
      item.title,
      remoteRowKey(item, index),
    ].filter(Boolean);
    return candidates.some((candidate) => remoteOnlyKeys.has(candidate as string));
  });
}

function matchedCount(mapping: WeChatMappingSnapshot | null) {
  if (!mapping) return 0;
  const rowCount = mapping.mapping_rows.filter((row) => Boolean(row.local_brief_id) && row.mapping_status === "matched").length;
  return rowCount || mapping.matched_count || 0;
}

export function DraftBoxPage({
  mapping,
  briefs,
  agentWorkflows,
  localBriefCount,
  browserSession,
  publishTasks,
  publishTasksPage,
  publishTasksPageSize,
  publishTasksTotal,
  refreshing,
  loading = false,
  deletingRemoteId,
  loadingBriefDetailId,
  onRefresh,
  onDeleteRemote,
  onSyncBrief,
  onLoadBriefDetail,
  onPublishTasksPageChange,
  onPublishTasksPageSizeChange,
}: DraftBoxPageProps) {
  const [view, setView] = useState<MappingView>("wechat_remote");
  const [showRecords, setShowRecords] = useState(false);
  const workflowMap = useMemo(
    () => new Map(agentWorkflows.map((workflow) => [workflow.workflow_session_id, workflow])),
    [agentWorkflows],
  );

  const remoteItems = mapping?.items ?? [];
  const localRecords = useMemo(
    () => [...briefs].sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()),
    [briefs],
  );
  const pendingRecords = useMemo(
    () => localRecords.filter((brief) => brief.record_status === "local_only" || Boolean(brief.record_exception)),
    [localRecords],
  );
  const remoteOnly = useMemo(() => remoteOnlyItems(mapping, remoteItems), [mapping, remoteItems]);
  const matched = matchedCount(mapping);
  const localOnly = Math.max(localBriefCount - matched, 0);
  const counts = {
    wechat_remote: remoteItems.length,
    local_records: localBriefCount,
    pending_confirmation: pendingRecords.length + remoteOnly.length,
  };

  const isLoggedIn = Boolean(browserSession?.logged_in);
  const browserTone = !browserSession?.logged_in || !browserSession?.manager_alive
    ? "danger"
    : browserSession?.busy
      ? "warning"
      : "success";
  const browserLabel = !browserSession?.logged_in || !browserSession?.manager_alive
    ? "未登录"
    : browserSession?.busy
      ? "执行中"
      : "已登录";

  function handleDeleteRemote(item: WeChatRemoteDraftItem) {
    const deleteTarget = remoteDeleteTarget(item);
    if (!deleteTarget) return;
    const title = item.title || "未命名草稿";
    if (!window.confirm(`确认删除微信远端草稿《${title}》？此操作不可撤销。`)) return;
    void onDeleteRemote(deleteTarget);
  }

  function renderRemoteCard(item: WeChatRemoteDraftItem, index: number, tone: "synced" | "remote-only" = "synced") {
    const key = remoteRowKey(item, index);
    const deleteTarget = remoteDeleteTarget(item);
    const deleting = Boolean(deleteTarget && deletingRemoteId === deleteTarget);
    return (
      <article key={`${tone}-${key}`} className={`draftbox-card ${tone === "remote-only" ? "severity-warning" : "severity-synced"}`}>
        <div className="draftbox-card-topline">
          <div>
            <span className={`status-badge status-${tone === "remote-only" ? "warning" : "success"} status-badge-compact`}>
              {tone === "remote-only" ? "仅微信端" : "微信端"}
            </span>
            <span className="entity-tag entity-tag-muted">远程草稿</span>
          </div>
          <span>{item.updated_at || formatDateTime(mapping?.checked_at, { fallback: "暂无" })}</span>
        </div>
        <strong className="draftbox-card-title">{item.title || "未命名草稿"}</strong>
        <p className="draftbox-card-summary">{item.appmsg_id || item.url || "暂无远端标识。"}</p>
        <div className="draftbox-card-actions">
          {item.url ? (
            <a className="ghost-button compact" href={item.url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} />
              打开草稿
            </a>
          ) : null}
          {deleteTarget ? (
            <button
              type="button"
              className="ghost-button compact danger"
              disabled={deleting}
              onClick={() => handleDeleteRemote(item)}
            >
              <Trash2 size={14} />
              {deleting ? "删除中..." : "删除远端"}
            </button>
          ) : null}
        </div>
      </article>
    );
  }

  function renderBriefCard(brief: BriefItem, mode: "local" | "pending" = "local") {
    const workflow = brief.workflow_session_id ? workflowMap.get(brief.workflow_session_id) : null;
    const loadingDetail = loadingBriefDetailId === brief.id;
    return (
      <article key={`${mode}-${brief.id}`} className={`draftbox-card ${briefSeverityClass(brief)}`}>
        <div className="draftbox-card-topline">
          <div>
            <span className={`status-badge status-${brief.record_exception ? "danger" : recordStatusTone[brief.record_status]} status-badge-compact`}>
              {brief.record_exception ? recordExceptionLabel[brief.record_exception] ?? "待确认" : recordStatusLabel[brief.record_status]}
            </span>
            <span className={`status-badge status-${brief.workflow_mode === "agent" ? "info" : "neutral"} status-badge-compact`}>
              {brief.workflow_mode === "agent" ? "Agent" : "传统"}
            </span>
          </div>
          <span>{formatRelativeTime(brief.updated_at, "刚更新")}</span>
        </div>
        <strong className="draftbox-card-title">{brief.title}</strong>
        <p className="draftbox-card-summary">{brief.one_line || "尚未生成一句话摘要。"}</p>
        <div className="draftbox-card-meta">
          <span>更新时间 {formatDateTime(brief.updated_at, { fallback: "暂无" })}</span>
          <span>草稿箱 {brief.draft_remote_updated_at ? "已命中" : "未命中"}</span>
          <span>发表记录 {brief.publish_record_published_at ? "已命中" : "未命中"}</span>
          {workflow ? <span>步骤 {workflow.current_step}</span> : null}
        </div>
        <div className="draftbox-card-actions">
          {brief.wechat_editor_url ? (
            <a className="ghost-button compact" href={brief.wechat_editor_url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} />
              打开编辑页
            </a>
          ) : null}
          <button
            type="button"
            className="ghost-button compact"
            onClick={() => void onLoadBriefDetail(brief.id)}
          >
            {loadingDetail ? "详情加载中..." : "查看详情"}
          </button>
          <button type="button" className="ghost-button compact" onClick={() => void onSyncBrief(brief.id)}>
            <RotateCcw size={14} />
            同步微信
          </button>
        </div>
      </article>
    );
  }

  function renderActiveView() {
    if (loading && !mapping) {
      return renderSkeletonCards();
    }
    if (view === "wechat_remote") {
      return remoteItems.length ? remoteItems.map((item, index) => renderRemoteCard(item, index)) : <p className="empty-state">当前还没有抓到微信端草稿。</p>;
    }
    if (view === "local_records") {
      return localRecords.length ? localRecords.map((brief) => renderBriefCard(brief)) : <p className="empty-state">当前没有本地总账记录。</p>;
    }
    if (!pendingRecords.length && !remoteOnly.length) {
      return <p className="empty-state">当前没有待确认记录。</p>;
    }
    return (
      <>
        <div className="draftbox-section-heading">
          <h3>本地待同步</h3>
          <span>{pendingRecords.length} 条</span>
        </div>
        {pendingRecords.length ? pendingRecords.map((brief) => renderBriefCard(brief, "pending")) : <p className="empty-state">暂无本地待同步记录。</p>}
        <div className="draftbox-section-heading">
          <h3>仅微信端</h3>
          <span>{remoteOnly.length} 条</span>
        </div>
        {remoteOnly.length ? remoteOnly.map((item, index) => renderRemoteCard(item, index, "remote-only")) : <p className="empty-state">暂无仅微信端草稿。</p>}
      </>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">微信草稿箱</p>
          <h2>管理本地与远程草稿</h2>
        </div>
        <button type="button" className="ghost-button compact" onClick={() => void onRefresh()}>
          <RefreshCcw size={16} />
          {refreshing ? "刷新中..." : "刷新"}
        </button>
      </div>

      <div className="draftbox-browser-bar">
        <div className="row-with-badge">
          <strong>{browserLabel}</strong>
          <SourceHealthBadge health={isLoggedIn ? "healthy" : "warning"} />
          <span className={`browser-status-indicator browser-status-${browserTone}`}>
            <span className="browser-status-dot" />
            {browserTone === "success" ? "空闲" : browserTone === "warning" ? "执行中" : "未就绪"}
          </span>
        </div>
        <span>{browserSession?.window_state ?? "unknown"} · {browserSession?.resident_page ?? "unknown"}</span>
      </div>

      <div className="mapping-summary-grid">
        <article className="channel-session-stat">
          <span>最近检查</span>
          <strong>{formatDateTime(mapping?.checked_at, { fallback: "暂无" })}</strong>
          <p>{formatRelativeTime(mapping?.checked_at, "尚未检查")}</p>
        </article>
        <article className="channel-session-stat">
          <span>微信端</span>
          <strong>{counts.wechat_remote}</strong>
          <p>{mapping?.message ?? "暂无数据"}</p>
        </article>
        <article className="channel-session-stat">
          <span>本地记录</span>
          <strong>{counts.local_records}</strong>
          <p>全部来自总账 briefs</p>
        </article>
      </div>

      <div className="draftbox-summary-row">
        <span>已匹配 {matched}</span>
        <span>仅微信 {remoteOnly.length}</span>
        <span>仅本地 {localOnly}</span>
      </div>

      <div className="segmented-control draft-workbench-tabs">
        <button type="button" className={view === "wechat_remote" ? "segment-active" : ""} onClick={() => setView("wechat_remote")}>
          微信端<strong>{counts.wechat_remote}</strong>
        </button>
        <button type="button" className={view === "local_records" ? "segment-active" : ""} onClick={() => setView("local_records")}>
          本地记录<strong>{counts.local_records}</strong>
        </button>
        <button type="button" className={view === "pending_confirmation" ? "segment-active" : ""} onClick={() => setView("pending_confirmation")}>
          待确认<strong>{counts.pending_confirmation}</strong>
        </button>
      </div>

      <div className="draftbox-list">
        {renderActiveView()}
      </div>

      <section className="draftbox-tasks-panel">
        <div className="panel-header compact">
          <div>
            <p className="eyebrow">操作记录</p>
            <h2>上传与删除记录</h2>
          </div>
          <button
            type="button"
            className="ghost-button compact"
            onClick={() => setShowRecords((prev) => !prev)}
          >
            {showRecords ? "收起" : `展开 (${publishTasksTotal})`}
          </button>
        </div>
        {showRecords ? (
          <>
            <PaginationControls
              page={publishTasksPage}
              pageSize={publishTasksPageSize}
              total={publishTasksTotal}
              currentCount={publishTasks.length}
              itemLabel="条记录"
              onPageChange={onPublishTasksPageChange}
              onPageSizeChange={onPublishTasksPageSizeChange}
            />
            <div className="task-list">
              {publishTasks.length
                ? publishTasks.map((task) => (
                    <article key={task.id} className="mini-row stacked">
                      <div className="row-with-badge">
                        <strong>{PUBLISH_ACTION_LABELS[task.action] ?? task.action}</strong>
                        <PublishTaskBadge status={task.status} />
                      </div>
                      <p>{task.message}</p>
                      {task.step_logs.length ? (
                        <details>
                          <summary>查看调试步骤</summary>
                          <ol>
                            {task.step_logs.slice(0, 6).map((step, i) => (
                              <li key={`${task.id}-step-${i}`}>{step}</li>
                            ))}
                          </ol>
                        </details>
                      ) : null}
                      {task.artifacts.length ? (
                        <details>
                          <summary>查看产物</summary>
                          <p>{task.artifacts[0]}</p>
                        </details>
                      ) : null}
                      <span className="tiny-meta">{formatDateTime(task.created_at, { fallback: "暂无" })}</span>
                    </article>
                  ))
                : <p className="empty-state">暂时还没有操作记录。</p>}
            </div>
          </>
        ) : null}
      </section>
    </section>
  );
}
