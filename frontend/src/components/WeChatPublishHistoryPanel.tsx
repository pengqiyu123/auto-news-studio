import { ExternalLink, RefreshCcw } from "lucide-react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { WeChatPublishHistorySnapshot } from "../types";

interface WeChatPublishHistoryPanelProps {
  history: WeChatPublishHistorySnapshot | null;
  refreshing: boolean;
  onRefresh: () => Promise<void>;
}

export function WeChatPublishHistoryPanel({ history, refreshing, onRefresh }: WeChatPublishHistoryPanelProps) {
  const items = history?.items ?? [];

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">发表记录</p>
          <h2>微信公众号已发表文章</h2>
          <p className="subtle">这里直接展示浏览器从公众号后台抓到的真实发表记录，只读查看，不提供业务操作。</p>
        </div>
        <button type="button" className="ghost-button" onClick={() => void onRefresh()}>
          <RefreshCcw size={16} />
          {refreshing ? "刷新中..." : "刷新发表记录"}
        </button>
      </div>

      <div className="mapping-summary-grid">
        <article className="channel-session-stat">
          <span>最近检查</span>
          <strong>{formatDateTime(history?.checked_at, { fallback: "暂无" })}</strong>
          <p>{formatRelativeTime(history?.checked_at, "尚未检查")}</p>
        </article>
        <article className="channel-session-stat">
          <span>发表条数</span>
          <strong>{history?.record_count ?? 0}</strong>
          <p>{history?.message ?? "暂无数据"}</p>
        </article>
      </div>

      <div className="intel-list">
        {items.length ? items.map((item, index) => {
          const key = item.remote_key || item.appmsg_id || item.url || `${item.title}-${index}`;
          return (
            <article key={key} className="intel-row-card">
              <div className="intel-card-topline">
                <span className="status-badge status-success">已发表</span>
                <span>{item.published_at || formatDateTime(history?.checked_at, { fallback: "暂无" })}</span>
              </div>
              <strong>{item.title || "未命名文章"}</strong>
              <div className="intel-score-row">
                <span>{item.appmsg_id || "无 appmsg_id"}</span>
                <span>{item.remote_key || "无 remote_key"}</span>
              </div>
              {item.url ? (
                <div className="intel-inline-actions">
                  <a className="ghost-button compact" href={item.url} target="_blank" rel="noreferrer">
                    <ExternalLink size={14} />
                    打开链接
                  </a>
                </div>
              ) : null}
            </article>
          );
        }) : <p className="empty-state">暂时还没有抓到发表记录。</p>}
      </div>
    </section>
  );
}
