import { ExternalLink, RefreshCcw, RotateCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type {
  BrowserSessionState,
  PublishTask,
  WeChatMappingSnapshot,
  WeChatMappingStatus,
} from "../types";
import { PublishTaskBadge, SourceHealthBadge } from "./StatusBadge";

type MappingView = "all" | "matched" | "remote_only" | "unresolved";

const statusLabel: Record<WeChatMappingStatus, string> = {
  matched: "已同步",
  remote_only: "仅微信",
  local_only: "待核对",
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
  browserSession: BrowserSessionState | null;
  publishTasks: PublishTask[];
  refreshing: boolean;
  deletingRemoteId?: string | null;
  onRefresh: () => Promise<void>;
  onDeleteRemote: (remoteId: string) => Promise<void>;
  onSyncBrief: (briefId: string) => Promise<void>;
}

export function WeChatDraftBoxPanel({
  mapping,
  browserSession,
  publishTasks,
  refreshing,
  deletingRemoteId,
  onRefresh,
  onDeleteRemote,
  onSyncBrief,
}: WeChatDraftBoxPanelProps) {
  const [view, setView] = useState<MappingView>("all");
  const [showRecords, setShowRecords] = useState(false);
  const [showPending, setShowPending] = useState(false);

  const rows = mapping?.mapping_rows ?? [];

  const remoteRows = useMemo(
    () => rows.filter((row) => row.mapping_status !== "local_only"),
    [rows],
  );

  const pendingRows = useMemo(
    () => rows.filter((row) => row.mapping_status === "local_only"),
    [rows],
  );

  const filteredRows = useMemo(() => {
    if (view === "all") return remoteRows;
    return remoteRows.filter((row) => row.mapping_status === view);
  }, [remoteRows, view]);

  const counts = useMemo(
    () => ({
      all: remoteRows.length,
      matched: remoteRows.filter((row) => row.mapping_status === "matched").length,
      remote_only: remoteRows.filter((row) => row.mapping_status === "remote_only").length,
      unresolved: remoteRows.filter((row) => row.mapping_status === "unresolved").length,
    }),
    [remoteRows],
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

  function renderRemoteTimeLabel(row: WeChatMappingSnapshot["mapping_rows"][number]) {
    if (row.remote_updated_at) {
      return `更新于 ${row.remote_updated_at}`;
    }
    return `检查于 ${formatDateTime(mapping?.checked_at, { fallback: "暂无" })}`;
  }

  return (
    <section className="panel">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">微信草稿箱</p>
            <h2>远端草稿与本地简报对照</h2>
            <p className="subtle">
              这里展示浏览器抓到的公众号草稿箱数据，以及它和本地简报的映射关系。
              浏览器配置请前往「设置」页。
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
            <span>已同步</span>
            <strong>{counts.matched}</strong>
            {pendingRows.length > 0 ? <p>待核对 {pendingRows.length}</p> : null}
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="segmented-control draft-workbench-tabs">
          <button type="button" className={view === "all" ? "segment-active" : ""} onClick={() => setView("all")}>
            全部<strong>{counts.all}</strong>
          </button>
          <button type="button" className={view === "matched" ? "segment-active" : ""} onClick={() => setView("matched")}>
            已同步<strong>{counts.matched}</strong>
          </button>
          <button type="button" className={view === "remote_only" ? "segment-active" : ""} onClick={() => setView("remote_only")}>
            仅微信<strong>{counts.remote_only}</strong>
          </button>
          <button type="button" className={view === "unresolved" ? "segment-active" : ""} onClick={() => setView("unresolved")}>
            待确认<strong>{counts.unresolved}</strong>
          </button>
        </div>

        <div className="intel-list">
          {filteredRows.length
              ? filteredRows.map((row, index) => {
                const remoteKey = row.remote_key || row.remote_appmsg_id || row.remote_url || `${row.remote_title}-${index}`;
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
                        ? `本地简报：${row.local_brief_title}`
                        : "当前没有匹配到本地简报。"}
                    </p>
                    <div className="intel-score-row">
                      <span>{row.remote_appmsg_id || "无 appmsg_id"}</span>
                      <span>{row.local_stage || "无本地状态"}</span>
                    </div>
                    <div className="intel-inline-actions">
                      {row.remote_url ? (
                        <a className="ghost-button compact" href={row.remote_url} target="_blank" rel="noreferrer">
                          <ExternalLink size={14} />
                          打开编辑页
                        </a>
                      ) : null}
                      {(row.remote_key || row.remote_appmsg_id || row.remote_url) ? (
                        <button
                          type="button"
                          className="ghost-button compact danger"
                          disabled={deleting}
                          onClick={() => void onDeleteRemote(row.remote_key || row.remote_appmsg_id || row.remote_url)}
                        >
                          <Trash2 size={14} />
                          {deleting ? "删除中..." : "删除远端草稿"}
                        </button>
                      ) : null}
                    </div>
                  </article>
                );
              })
            : <p className="empty-state">当前筛选条件下没有远端草稿数据。</p>}
        </div>
      </section>

      {pendingRows.length > 0 ? (
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">待核对</p>
              <h2>本地简报未在微信确认 ({pendingRows.length})</h2>
            </div>
            <button
              type="button"
              className="ghost-button compact"
              onClick={() => setShowPending((prev) => !prev)}
            >
              {showPending ? "收起" : "展开"}
            </button>
          </div>
          {showPending ? (
            <div className="intel-list">
              {pendingRows.map((row, index) => (
                <article key={`pending-${row.local_brief_id ?? index}`} className="intel-row-card">
                  <div className="intel-card-topline">
                    <span className="status-badge status-danger">待核对</span>
                    <span>{row.local_stage || "未知状态"}</span>
                  </div>
                  <strong>{row.local_brief_title || "未命名简报"}</strong>
                  <p>微信侧暂未确认到对应稿件，可能尚未同步或已被手动删除。</p>
                  {row.local_brief_id ? (
                    <div className="intel-inline-actions">
                      <button
                        type="button"
                        className="ghost-button compact"
                        onClick={() => {
                        if (!window.confirm("确认重新同步到微信草稿箱？")) return;
                        void onSyncBrief(row.local_brief_id!);
                      }}
                      >
                        <RotateCcw size={14} />
                        重新同步
                      </button>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          ) : null}
        </section>
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
            {showRecords ? "收起" : `展开 (${publishTasks.length})`}
          </button>
        </div>
        {showRecords ? (
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
        ) : null}
      </section>
    </section>
  );
}
