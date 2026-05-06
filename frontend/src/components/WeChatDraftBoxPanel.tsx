import { ExternalLink, RefreshCcw, RotateCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type {
  BriefItem,
  BrowserSessionState,
  PublishTask,
  WeChatMappingSnapshot,
  WeChatMappingStatus,
} from "../types";
import { PublishTaskBadge, SourceHealthBadge } from "./StatusBadge";
import { PaginationControls } from "./PaginationControls";

type MappingView = "all" | "remote_only" | "local_records" | "unresolved";

type LocalRecordViewRow = {
  remote_title: string;
  remote_key: string;
  remote_appmsg_id: string | null;
  remote_url: string;
  remote_updated_at: string | null;
  local_brief_id: string;
  local_brief_title: string;
  local_stage: BriefItem["stage"];
  mapping_status: WeChatMappingStatus;
};
type BrowserRemoteRow = {
  browser_row_key: string;
  remote_title: string;
  remote_key: string;
  remote_appmsg_id: string | null;
  remote_url: string;
  remote_updated_at: string | null;
  local_brief_id: string | null;
  local_brief_title: string | null;
  local_stage: BriefItem["stage"] | null;
  mapping_status: WeChatMappingStatus;
};

const statusLabel: Record<WeChatMappingStatus, string> = {
  matched: "已同步",
  remote_only: "仅微信",
  local_only: "仅本地",
  unresolved: "待确认",
};

const statusTone: Record<WeChatMappingStatus, "success" | "warning" | "danger"> = {
  matched: "success",
  remote_only: "warning",
  local_only: "danger",
  unresolved: "danger",
};

const PUBLISH_ACTION_LABELS: Record<string, string> = {
  sync_wechat_draft: "上传到微信草稿箱",
  delete_wechat_draft: "删除微信远端草稿",
  delete_brief: "删除本地简报",
};

interface WeChatDraftBoxPanelProps {
  mapping: WeChatMappingSnapshot | null;
  localBriefCount: number;
  browserSession: BrowserSessionState | null;
  publishTasks: PublishTask[];
  publishTasksPage: number;
  publishTasksPageSize: number;
  publishTasksTotal: number;
  refreshing: boolean;
  deletingRemoteId?: string | null;
  onRefresh: () => Promise<void>;
  onDeleteRemote: (remoteId: string) => Promise<void>;
  onSyncBrief: (briefId: string) => Promise<void>;
  onPublishTasksPageChange: (page: number) => void;
  onPublishTasksPageSizeChange: (pageSize: number) => void;
}

export function WeChatDraftBoxPanel({
  mapping,
  localBriefCount,
  browserSession,
  publishTasks,
  publishTasksPage,
  publishTasksPageSize,
  publishTasksTotal,
  refreshing,
  deletingRemoteId,
  onRefresh,
  onDeleteRemote,
  onSyncBrief,
  onPublishTasksPageChange,
  onPublishTasksPageSizeChange,
}: WeChatDraftBoxPanelProps) {
  const [view, setView] = useState<MappingView>("all");
  const [showRecords, setShowRecords] = useState(false);

  const rows = mapping?.mapping_rows ?? [];
  const browserItems = mapping?.items ?? [];

  const remoteRows = useMemo(() => rows, [rows]);
  const browserRows = useMemo(
    () => browserItems.map((item, index): BrowserRemoteRow => ({
      browser_row_key: `${item.remote_key || item.appmsg_id || item.url || item.title || "draft"}-${index}`,
      remote_title: item.title,
      remote_key: item.remote_key || item.appmsg_id || item.url || item.title || `draft-${index}`,
      remote_appmsg_id: item.appmsg_id ?? null,
      remote_url: item.url ?? "",
      remote_updated_at: item.updated_at ?? null,
      local_brief_id: null,
      local_brief_title: null,
      local_stage: null,
      mapping_status: "remote_only",
    })),
    [browserItems],
  );

  const localRows = useMemo(() => {
    return remoteRows
      .filter((row) => row.local_brief_id)
      .map((row) => ({
        remote_title: row.local_brief_title || row.remote_title,
        remote_key: row.local_brief_id || row.remote_key || "",
        remote_appmsg_id: row.remote_appmsg_id ?? null,
        remote_url: row.remote_url || "",
        remote_updated_at: row.remote_updated_at ?? null,
        local_brief_id: row.local_brief_id || "",
        local_brief_title: row.local_brief_title || "",
        local_stage: (row.local_stage || "prepared") as BriefItem["stage"],
        mapping_status: (row.mapping_status === "matched" ? "matched" : "local_only") as WeChatMappingStatus,
      }));
  }, [remoteRows]);

  const filteredRows = useMemo(() => {
    if (view === "all") {
      return remoteRows;
    }
    if (view === "local_records") {
      return localRows.map(
        (brief): LocalRecordViewRow => ({
          remote_title: brief.remote_title,
          remote_key: brief.remote_key,
          remote_appmsg_id: brief.remote_appmsg_id,
          remote_url: brief.remote_url,
          remote_updated_at: brief.remote_updated_at,
          local_brief_id: brief.local_brief_id,
          local_brief_title: brief.local_brief_title,
          local_stage: brief.local_stage,
          mapping_status: brief.mapping_status,
        }),
      );
    }
    if (view === "remote_only") {
      return browserRows;
    }
    return remoteRows.filter((row) => row.mapping_status === view);
  }, [browserRows, localRows, remoteRows, view]);

  const counts = useMemo(
    () => ({
      all: remoteRows.length,
      remote_only: browserRows.length,
      local_records: localBriefCount,
      unresolved: remoteRows.filter((row) => row.mapping_status === "unresolved").length,
    }),
    [browserRows.length, localBriefCount, remoteRows],
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

  function renderRemoteTimeLabel(row: WeChatMappingSnapshot["mapping_rows"][number] | BrowserRemoteRow) {
    if (row.remote_updated_at) {
      return `更新于 ${row.remote_updated_at}`;
    }
    return `检查于 ${formatDateTime(mapping?.checked_at, { fallback: "暂无" })}`;
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">微信草稿箱</p>
          <h2>微信草稿与本地记录</h2>
          <p className="subtle">
            上方切换视图，下方直接看结果。仅微信以浏览器为准，本地记录以项目内 `briefs` 为准。
          </p>
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
          <span>远端稿件</span>
          <strong>{mapping?.remote_count ?? 0}</strong>
        </article>
        <article className="channel-session-stat">
          <span>本地记录</span>
          <strong>{counts.local_records}</strong>
          {counts.local_records > 0 ? <p>来自共享 briefs</p> : null}
        </article>
      </div>

      <div className="segmented-control draft-workbench-tabs">
        <button type="button" className={view === "all" ? "segment-active" : ""} onClick={() => setView("all")}>
          全部<strong>{counts.all}</strong>
        </button>
        <button type="button" className={view === "remote_only" ? "segment-active" : ""} onClick={() => setView("remote_only")}>
          仅微信<strong>{counts.remote_only}</strong>
        </button>
        <button type="button" className={view === "local_records" ? "segment-active" : ""} onClick={() => setView("local_records")}>
          本地记录<strong>{counts.local_records}</strong>
        </button>
        <button type="button" className={view === "unresolved" ? "segment-active" : ""} onClick={() => setView("unresolved")}>
          待确认<strong>{counts.unresolved}</strong>
        </button>
      </div>

      <div className="intel-list">
        {filteredRows.length
            ? filteredRows.map((row, index) => {
              const remoteKey = String(
                "browser_row_key" in row
                  ? row.browser_row_key
                  : row.remote_key || row.remote_appmsg_id || row.remote_url || `${row.remote_title}-${index}`,
              );
              const deleteTarget = String(row.remote_key || row.remote_appmsg_id || row.remote_url || "");
              const deleting = deletingRemoteId === remoteKey;
              return (
                <article key={remoteKey} className="intel-row-card">
                  <div className="intel-card-topline">
                    <span className={`status-badge status-${statusTone[row.mapping_status]}`}>
                      {statusLabel[row.mapping_status]}
                    </span>
                    <span>{renderRemoteTimeLabel(row)}</span>
                  </div>
                  <strong>{row.remote_title || row.local_brief_title || "未命名远端稿件"}</strong>
                  <p>
                    {row.local_brief_title
                      ? `本地记录：${row.local_brief_title}`
                      : "当前没有匹配到本地记录。"}
                  </p>
                  <div className="intel-score-row">
                    <span>{row.remote_appmsg_id || "无 appmsg_id"}</span>
                    <span>{row.local_stage || "无本地状态"}</span>
                  </div>
                  <div className="intel-inline-actions">
                    {row.remote_url ? (
                      <a className="ghost-button compact" href={row.remote_url} target="_blank" rel="noreferrer">
                        <ExternalLink size={14} />
                        {view === "remote_only" ? "打开微信草稿" : "打开编辑页"}
                      </a>
                    ) : null}
                    {view !== "remote_only" && deleteTarget ? (
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
                    {view === "local_records" && row.local_brief_id ? (
                      <button
                        type="button"
                        className="ghost-button compact"
                        onClick={() => {
                          const briefId = row.local_brief_id;
                          if (!briefId) return;
                          if (!window.confirm("确认重新同步到微信草稿箱？")) return;
                          void onSyncBrief(briefId);
                        }}
                      >
                        <RotateCcw size={14} />
                        重新同步
                      </button>
                    ) : null}
                  </div>
                </article>
              );
            })
          : <p className="empty-state">当前筛选条件下没有草稿数据。</p>}
      </div>

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
