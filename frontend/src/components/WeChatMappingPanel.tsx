import { ExternalLink, RefreshCcw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { WeChatMappingSnapshot, WeChatMappingStatus } from "../types";

type MappingView = "all" | "matched" | "remote_only" | "local_only" | "unresolved";

const statusLabel: Record<WeChatMappingStatus, string> = {
  matched: "已同步",
  remote_only: "仅远端",
  local_only: "仅本地",
  unresolved: "未解析",
};

interface WeChatMappingPanelProps {
  mapping: WeChatMappingSnapshot | null;
  refreshing: boolean;
  deletingRemoteId?: string | null;
  onRefresh: () => Promise<void>;
  onDeleteRemote: (remoteId: string) => Promise<void>;
}

export function WeChatMappingPanel({
  mapping,
  refreshing,
  deletingRemoteId,
  onRefresh,
  onDeleteRemote,
}: WeChatMappingPanelProps) {
  const [view, setView] = useState<MappingView>("all");

  const rows = mapping?.mapping_rows ?? [];
  const filteredRows = useMemo(() => {
    if (view === "all") return rows;
    return rows.filter((row) => row.mapping_status === view);
  }, [rows, view]);

  const counts = useMemo(() => ({
    all: rows.length,
    matched: rows.filter((row) => row.mapping_status === "matched").length,
    remote_only: rows.filter((row) => row.mapping_status === "remote_only").length,
    local_only: rows.filter((row) => row.mapping_status === "local_only").length,
    unresolved: rows.filter((row) => row.mapping_status === "unresolved").length,
  }), [rows]);

  return (
    <section className="panel">
      <div className="panel-header">
          <div>
            <p className="eyebrow">公众号映射</p>
            <h2>微信草稿与本地记录</h2>
            <p className="subtle">这里直接看浏览器抓到的公众号草稿箱数据，以及它和本地记录的对应关系。</p>
          </div>
        <button type="button" className="ghost-button" onClick={() => void onRefresh()}>
          <RefreshCcw size={16} />
          {refreshing ? "刷新中..." : "刷新映射"}
        </button>
      </div>

      <div className="segmented-control draft-workbench-tabs">
        <button type="button" className={view === "all" ? "segment-active" : ""} onClick={() => setView("all")}>全部<strong>{counts.all}</strong></button>
        <button type="button" className={view === "matched" ? "segment-active" : ""} onClick={() => setView("matched")}>已同步<strong>{counts.matched}</strong></button>
        <button type="button" className={view === "remote_only" ? "segment-active" : ""} onClick={() => setView("remote_only")}>仅远端<strong>{counts.remote_only}</strong></button>
        <button type="button" className={view === "local_only" ? "segment-active" : ""} onClick={() => setView("local_only")}>仅本地<strong>{counts.local_only}</strong></button>
        <button type="button" className={view === "unresolved" ? "segment-active" : ""} onClick={() => setView("unresolved")}>未解析<strong>{counts.unresolved}</strong></button>
      </div>

      <div className="mapping-summary-grid">
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
          <span>已映射</span>
          <strong>{mapping?.matched_count ?? 0}</strong>
        </article>
        <article className="channel-session-stat">
          <span>异常</span>
          <strong>{mapping?.missing_count ?? 0}</strong>
          <p>{mapping?.message ?? "暂无"}</p>
        </article>
      </div>

      <div className="intel-list">
        {filteredRows.length ? filteredRows.map((row, index) => {
          const remoteKey = row.remote_appmsg_id || row.remote_url || `${row.remote_title}-${index}`;
          const deleting = deletingRemoteId === remoteKey;
          return (
            <article key={remoteKey} className="intel-row-card">
              <div className="intel-card-topline">
                <span className={`status-badge status-${row.mapping_status === "matched" ? "success" : row.mapping_status === "remote_only" ? "warning" : "danger"}`}>
                  {statusLabel[row.mapping_status]}
                </span>
                <span>{row.remote_updated_at || "时间未知"}</span>
              </div>
              <strong>{row.remote_title || row.local_brief_title || "未命名远端稿件"}</strong>
              <p>{row.local_brief_title ? `本地记录：${row.local_brief_title}` : "当前没有匹配到本地记录。"}</p>
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
                {(row.remote_appmsg_id || row.remote_url) ? (
                  <button
                    type="button"
                    className="ghost-button compact danger"
                    disabled={deleting}
                    onClick={() => void onDeleteRemote(row.remote_appmsg_id || row.remote_url)}
                  >
                    <Trash2 size={14} />
                    {deleting ? "删除中..." : "删除远端草稿"}
                  </button>
                ) : null}
              </div>
            </article>
          );
        }) : <p className="empty-state">当前筛选条件下没有远端映射数据。</p>}
      </div>
    </section>
  );
}
