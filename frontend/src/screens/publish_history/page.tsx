import { ExternalLink, RefreshCcw } from "lucide-react";

import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type { WeChatPublishHistorySnapshot, WeChatPublishRecordItem } from "../../types";

interface PublishHistoryPageProps {
  history: WeChatPublishHistorySnapshot | null;
  refreshing: boolean;
  loading?: boolean;
  onRefresh: () => Promise<void>;
}

function renderSkeletonCards(count = 4) {
  return (
    <div className="skeleton-list" aria-label="发表记录加载中">
      {Array.from({ length: count }, (_, index) => (
        <div key={`publish-history-skeleton-${index}`} className="skeleton-card">
          <div className="skeleton-line skeleton-short" />
          <div className="skeleton-line skeleton-long" />
          <div className="skeleton-line skeleton-medium" />
        </div>
      ))}
    </div>
  );
}

function formatCount(value?: number | null) {
  if (typeof value !== "number") return "-";
  return String(value);
}

function totalReads(items: WeChatPublishRecordItem[]) {
  return items.reduce((sum, item) => sum + (item.read_count || 0), 0);
}

function bestArticle(items: WeChatPublishRecordItem[]) {
  return items.reduce<WeChatPublishRecordItem | null>((best, item) => {
    if (!best || (item.read_count || 0) > (best.read_count || 0)) {
      return item;
    }
    return best;
  }, null);
}

function publishKey(item: WeChatPublishRecordItem, index: number) {
  return item.remote_key || item.appmsg_id || item.url || `${item.title}-${index}`;
}

function renderEmptyState(history: WeChatPublishHistorySnapshot | null) {
  if (!history) {
    return <p className="empty-state">还没抓取发表记录。</p>;
  }
  return <p className="empty-state">已检查，但没有发表记录。</p>;
}

export function PublishHistoryPage({ history, refreshing, loading = false, onRefresh }: PublishHistoryPageProps) {
  const items = history?.items ?? [];
  const totalReadCount = history?.overview ? totalReads(items) : null;
  const topArticle = bestArticle(items);

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">发表记录</p>
          <h2>查看公众号内容表现</h2>
        </div>
        <button type="button" className="ghost-button compact" onClick={() => void onRefresh()}>
          <RefreshCcw size={16} />
          {refreshing ? "刷新中..." : "刷新"}
        </button>
      </div>

      <div className="publish-history-stats">
        <article className="publish-history-stat">
          <span>最近检查</span>
          <strong>{formatDateTime(history?.checked_at, { fallback: "暂无" })}</strong>
          <p>{formatRelativeTime(history?.checked_at, "尚未检查")}</p>
        </article>
        <article className="publish-history-stat">
          <span>发表条数</span>
          <strong>发表 {history?.record_count ?? 0} 条</strong>
          <p>{history?.message ?? "暂无数据"}</p>
        </article>
        <article className="publish-history-stat">
          <span>总阅读</span>
          <strong>总阅读 {formatCount(totalReadCount)}</strong>
          <p>{history?.overview?.stats_window_label || "暂未抓到账号总览"}</p>
        </article>
        <article className="publish-history-stat">
          <span>最佳文章</span>
          <strong>{topArticle ? `${topArticle.title || "未命名文章"} · 阅读 ${topArticle.read_count || 0}` : "暂无最佳文章"}</strong>
          <p>{topArticle?.published_at || "暂无发表记录"}</p>
        </article>
      </div>

      <div className="publish-history-list wechat-publish-list">
        {loading && !history ? renderSkeletonCards() : (
          items.length ? items.map((item, index) => (
            <article key={publishKey(item, index)} className="wechat-publish-card">
              {item.thumbnail ? (
                <div className="wechat-publish-card__thumb">
                  <img src={item.thumbnail} alt="" loading="lazy" />
                </div>
              ) : null}
              <div className="wechat-publish-card__content">
                {item.url ? (
                  <a className="wechat-publish-card__title" href={item.url} target="_blank" rel="noreferrer">
                    {item.title || "未命名文章"}
                  </a>
                ) : (
                  <span className="wechat-publish-card__title">{item.title || "未命名文章"}</span>
                )}
                <div className="wechat-publish-card__metrics">
                  <span>阅读 {item.read_count || 0} · 赞 {item.like_count || 0} · 分享 {item.share_count || 0} · 留言 {item.comment_count || 0}</span>
                  {(item.recommend_count || 0) > 0 ? <span>推荐 {item.recommend_count}</span> : null}
                  {(item.reprint_count || 0) > 0 ? <span>转载 {item.reprint_count}</span> : null}
                </div>
                <div className="wechat-publish-card__footer">
                  <span className="wechat-publish-card__time">发表于 {item.published_at || "未知时间"}</span>
                  {item.url ? (
                    <a className="wechat-publish-card__link" href={item.url} target="_blank" rel="noreferrer">
                      打开原文
                      <ExternalLink size={12} />
                    </a>
                  ) : null}
                </div>
              </div>
            </article>
          )) : renderEmptyState(history)
        )}
      </div>
    </section>
  );
}
