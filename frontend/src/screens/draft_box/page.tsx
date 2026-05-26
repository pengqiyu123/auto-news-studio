import { ExternalLink, RefreshCcw, RotateCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type {
  AgentWorkflowItem,
  BriefItem,
  BrowserSessionState,
  PublishTask,
  WeChatMappingSnapshot,
  WeChatRemoteDraftItem,
} from "../../types";
import { PublishTaskBadge, SourceHealthBadge } from "../../components/StatusBadge";
import { PaginationControls } from "../../components/PaginationControls";

type MappingView = "wechat_remote" | "local_records" | "pending_confirmation";

const PUBLISH_ACTION_LABELS: Record<string, string> = {
  sync_wechat_draft: "上传到微信草稿箱",
  delete_wechat_draft: "删除微信远端草稿",
  delete_brief: "删除本地简报",
};

const recordStatusLabel: Record<BriefItem["record_status"], string> = {
  local_only: "仅本地",
  draft_synced: "已同步草稿箱",
  published: "已同步发表记录",
};

const recordStatusTone: Record<BriefItem["record_status"], "warning" | "info" | "success"> = {
  local_only: "warning",
  draft_synced: "info",
  published: "success",
};

const recordExceptionLabel: Partial<Record<NonNullable<BriefItem["record_exception"]>, string>> = {
  pending_confirmation: "待确认",
  draft_check_failed: "草稿箱检查失败",
  publish_check_failed: "发表记录检查失败",
  draft_missing: "草稿已丢失",
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
  deletingRemoteId?: string | null;
  loadingBriefDetailId?: string | null;
  onRefresh: () => Promise<void>;
  onDeleteRemote: (remoteId: string) => Promise<void>;
  onSyncBrief: (briefId: string) => Promise<void>;
  onLoadBriefDetail: (briefId: string) => Promise<BriefItem | null>;
  onPublishTasksPageChange: (page: number) => void;
  onPublishTasksPageSizeChange: (pageSize: number) => void;
}

function detailExcerpt(brief: BriefItem): string {
  const text = brief.wechat_markdown || brief.one_line || "";
  return text.replace(/^#+\s*/gm, "").replace(/\s+/g, " ").trim().slice(0, 220) || "暂无文章详情。";
}

function remoteRowKey(item: WeChatRemoteDraftItem, index: number): string {
  return item.remote_key || item.appmsg_id || item.url || `${item.title}-${index}`;
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
  const remoteOnlyItems = useMemo(() => {
    const localTitles = new Set(localRecords.map((brief) => brief.title.trim()));
    return remoteItems.filter((item) => !localTitles.has(item.title.trim()));
  }, [localRecords, remoteItems]);

  const counts = useMemo(
    () => ({
      wechat_remote: remoteItems.length,
      local_records: localBriefCount,
      pending_confirmation: pendingRecords.length + remoteOnlyItems.length,
    }),
    [localBriefCount, pendingRecords.length, remoteItems.length],
  );

  const isLoggedIn = Boolean(browserSession?.logged_in);
  const browserTone = !browserSession?.logged_in || !browserSession?.manager_alive
    ? "danger"
    : browserSession?.busy
      ? "warning"
      : "success";
  const browserLabel = !browserSession?.logged_in || !browserSession?.manager_alive
    ? "未就绪"
    : browserSession?.busy
      ? "执行中"
      : "空闲";

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">微信草稿箱</p>
          <h2>微信端与本地总账对账工作台</h2>
          <p className="subtle">微信端继续以实时抓取为准，本地记录直接复用同一份简报总账，不再维护第二份本地库。</p>
        </div>
        <button type="button" className="ghost-button" onClick={() => void onRefresh()}>
          <RefreshCcw size={16} />
          {refreshing ? "刷新中..." : "刷新草稿箱"}
        </button>
      </div>

      <div className="mapping-summary-grid">
        <article className="channel-session-stat">
          <span>登录状态</span>
          <div className="row-with-badge">
            <strong>{isLoggedIn ? "已登录" : "未登录"}</strong>
            <SourceHealthBadge health={isLoggedIn ? "healthy" : "warning"} />
            <span className={`browser-status-indicator browser-status-${browserTone}`}>
              <span className="browser-status-dot" />
              {browserLabel}
            </span>
          </div>
          <p>
            {browserSession?.window_state ?? "unknown"} | {browserSession?.resident_page ?? "unknown"}
          </p>
        </article>
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

      {view === "wechat_remote" ? (
        <div className="intel-list">
          {remoteItems.length ? remoteItems.map((item, index) => {
            const key = remoteRowKey(item, index);
            const deleting = deletingRemoteId === key;
            const deleteTarget = item.remote_key || item.appmsg_id || item.url || "";
            return (
              <article key={key} className="intel-row-card">
                <div className="intel-card-topline">
                  <span className="status-badge status-info">微信端</span>
                  <span>{item.updated_at || formatDateTime(mapping?.checked_at, { fallback: "暂无" })}</span>
                </div>
                <strong>{item.title || "未命名草稿"}</strong>
                <div className="intel-score-row">
                  <span>{item.appmsg_id || "无 appmsg_id"}</span>
                  <span>{item.url || "无远端链接"}</span>
                </div>
                <div className="intel-inline-actions">
                  {item.url ? (
                    <a className="ghost-button compact" href={item.url} target="_blank" rel="noreferrer">
                      <ExternalLink size={14} />
                      打开微信草稿
                    </a>
                  ) : null}
                  {deleteTarget ? (
                    <button
                      type="button"
                      className="ghost-button compact danger"
                      disabled={deleting}
                      onClick={() => void onDeleteRemote(deleteTarget)}
                    >
                      <Trash2 size={14} />
                      {deleting ? "删除中..." : "删除远端草稿"}
                    </button>
                  ) : null}
                </div>
              </article>
            );
          }) : <p className="empty-state">当前还没有抓到微信端草稿。</p>}
        </div>
      ) : null}

      {view === "local_records" ? (
        <div className="intel-list">
          {localRecords.length ? localRecords.map((brief) => (
            <article key={brief.id} className="intel-row-card">
              <div className="intel-card-topline">
                <span className={`status-badge status-${recordStatusTone[brief.record_status]}`}>{recordStatusLabel[brief.record_status]}</span>
                {brief.record_exception ? (
                  <span className="status-badge status-danger">{recordExceptionLabel[brief.record_exception] ?? "待确认"}</span>
                ) : null}
                <span className={`status-badge status-${brief.workflow_mode === "agent" ? "info" : "neutral"}`}>
                  {brief.workflow_mode === "agent" ? "Agent" : "传统"}
                </span>
                <span>{formatRelativeTime(brief.updated_at, "刚更新")}</span>
              </div>
              <strong>{brief.title}</strong>
              <p>{brief.one_line || "尚未生成一句话摘要。"}</p>
              <div className="intel-score-row">
                <span>更新时间 {formatDateTime(brief.updated_at, { fallback: "暂无" })}</span>
                <span>草稿箱 {brief.draft_remote_updated_at ? "已命中" : "未命中"}</span>
                <span>发表记录 {brief.publish_record_published_at ? "已命中" : "未命中"}</span>
              </div>
              {brief.workflow_session_id ? (
                <div className="intel-score-row">
                  <span>会话 {brief.workflow_session_id}</span>
                  <span>步骤 {workflowMap.get(brief.workflow_session_id)?.current_step ?? "article_saved"}</span>
                </div>
              ) : null}
              <details className="draft-list-block">
                <summary
                  onClick={() => {
                    if (!brief.wechat_markdown || !brief.prompt_package_markdown) {
                      void onLoadBriefDetail(brief.id);
                    }
                  }}
                >
                  文章详情{loadingBriefDetailId === brief.id ? "（加载中...）" : ""}
                </summary>
                <p>{detailExcerpt(brief)}</p>
                <p>来源数 {brief.source_links.length} / 引文数 {brief.quotes.length}</p>
              </details>
              <div className="intel-inline-actions">
                {brief.wechat_editor_url ? (
                  <a className="ghost-button compact" href={brief.wechat_editor_url} target="_blank" rel="noreferrer">
                    <ExternalLink size={14} />
                    打开微信编辑页
                  </a>
                ) : null}
                <button
                  type="button"
                  className="ghost-button compact"
                  onClick={() => {
                    if (!window.confirm("确认重新同步到微信草稿箱？")) return;
                    void onSyncBrief(brief.id);
                  }}
                >
                  <RotateCcw size={14} />
                  重新同步
                </button>
              </div>
            </article>
          )) : <p className="empty-state">当前没有本地总账记录。</p>}
        </div>
      ) : null}

      {view === "pending_confirmation" ? (
        <div className="intel-list">
          {pendingRecords.length || remoteOnlyItems.length ? (
            <>
              {pendingRecords.map((brief) => (
                <article key={brief.id} className="intel-row-card">
                  <div className="intel-card-topline">
                    <span className="status-badge status-warning">本地有，微信待确认</span>
                    {brief.record_exception ? (
                      <span className="status-badge status-danger">{recordExceptionLabel[brief.record_exception] ?? "待确认"}</span>
                    ) : null}
                    <span className={`status-badge status-${brief.workflow_mode === "agent" ? "info" : "neutral"}`}>
                      {brief.workflow_mode === "agent" ? "Agent" : "传统"}
                    </span>
                  </div>
                  <strong>{brief.title}</strong>
                  <p>{brief.one_line || "尚未生成一句话摘要。"}</p>
                  <div className="intel-inline-actions">
                    {brief.wechat_editor_url ? (
                      <a className="ghost-button compact" href={brief.wechat_editor_url} target="_blank" rel="noreferrer">
                        <ExternalLink size={14} />
                        打开微信编辑页
                      </a>
                    ) : null}
                    <button
                      type="button"
                      className="ghost-button compact"
                      onClick={() => {
                        if (!window.confirm("确认重新同步到微信草稿箱？")) return;
                        void onSyncBrief(brief.id);
                      }}
                    >
                      <RotateCcw size={14} />
                      重新同步
                    </button>
                  </div>
                </article>
              ))}
              {remoteOnlyItems.map((item, index) => {
                const key = `remote-only-${remoteRowKey(item, index)}`;
                return (
                  <article key={key} className="intel-row-card">
                    <div className="intel-card-topline">
                      <span className="status-badge status-warning">微信有，本地无</span>
                      <span>{item.updated_at || formatDateTime(mapping?.checked_at, { fallback: "暂无" })}</span>
                    </div>
                    <strong>{item.title || "未命名草稿"}</strong>
                    <div className="intel-inline-actions">
                      {item.url ? (
                        <a className="ghost-button compact" href={item.url} target="_blank" rel="noreferrer">
                          <ExternalLink size={14} />
                          打开微信草稿
                        </a>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </>
          ) : <p className="empty-state">当前没有待确认记录。</p>}
        </div>
      ) : null}

      <section className="panel">
        <div className="panel-header">
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
                              <li key={i}>{step}</li>
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
