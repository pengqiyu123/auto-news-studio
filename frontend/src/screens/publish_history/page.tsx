import { Eye, Heart, MessageCircle, Repeat2, Share2, Sparkles, ExternalLink, RefreshCcw } from "lucide-react";

import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type { WeChatPublishHistorySnapshot } from "../../types";

interface PublishHistoryPageProps {
  history: WeChatPublishHistorySnapshot | null;
  refreshing: boolean;
  onRefresh: () => Promise<void>;
}

export function PublishHistoryPage({ history, refreshing, onRefresh }: PublishHistoryPageProps) {
  const items = history?.items ?? [];
  const overview = history?.overview ?? null;

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">发表记录</p>
          <h2>微信公众号已发表文章</h2>
          <p className="subtle">从公众号后台实时抓取的发表记录与阅读数据，只读查看。</p>
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
        <article className="channel-session-stat">
          <span>总用户数</span>
          <strong>{overview ? overview.total_users : "-"}</strong>
          <p>{overview?.stats_window_label || "暂未抓到账号总览"}</p>
        </article>
        <article className="channel-session-stat">
          <span>昨日阅读</span>
          <strong>{overview ? overview.yesterday_reads : "-"}</strong>
          <p>{overview?.fetched_at ? formatRelativeTime(overview.fetched_at, "") : "暂未抓到账号总览"}</p>
        </article>
        <article className="channel-session-stat">
          <span>昨日分享</span>
          <strong>{overview ? overview.yesterday_shares : "-"}</strong>
          <p>{overview?.stats_window_label || "暂未抓到账号总览"}</p>
        </article>
        <article className="channel-session-stat">
          <span>昨日新增关注</span>
          <strong>{overview ? overview.yesterday_new_follows : "-"}</strong>
          <p>{overview?.stats_window_label || "暂未抓到账号总览"}</p>
        </article>
      </div>

      <div className="wechat-publish-list">
        {items.length ? items.map((item, index) => {
          const key = item.remote_key || item.appmsg_id || item.url || `${item.title}-${index}`;
          return (
            <article key={key} className="wechat-publish-card">
              <div className="wechat-publish-card__body">
                {item.thumbnail ? (
                  <div className="wechat-publish-card__thumb">
                    <img src={item.thumbnail} alt="" loading="lazy" />
                  </div>
                ) : null}
                <div className="wechat-publish-card__content">
                  <div className="wechat-publish-card__title-row">
                    {item.url ? (
                      <a className="wechat-publish-card__title" href={item.url} target="_blank" rel="noreferrer">
                        {item.title || "未命名文章"}
                      </a>
                    ) : (
                      <span className="wechat-publish-card__title">{item.title || "未命名文章"}</span>
                    )}
                  </div>
                  <div className="wechat-publish-card__metrics">
                    <span className="metric-item" title="阅读人数">
                      <Eye size={14} />
                      <span>{item.read_count ?? 0}</span>
                    </span>
                    <span className="metric-item" title="点赞人数">
                      <Heart size={14} />
                      <span>{item.like_count ?? 0}</span>
                    </span>
                    <span className="metric-item" title="分享人数">
                      <Share2 size={14} />
                      <span>{item.share_count ?? 0}</span>
                    </span>
                    {(item.recommend_count ?? 0) > 0 ? (
                      <span className="metric-item" title="推荐人数">
                        <Sparkles size={14} />
                        <span>{item.recommend_count}</span>
                      </span>
                    ) : null}
                    {(item.comment_count ?? 0) > 0 ? (
                      <span className="metric-item" title="留言条数">
                        <MessageCircle size={14} />
                        <span>{item.comment_count}</span>
                      </span>
                    ) : null}
                    {(item.reprint_count ?? 0) > 0 ? (
                      <span className="metric-item" title="被转载次数">
                        <Repeat2 size={14} />
                        <span>{item.reprint_count}</span>
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>
              <div className="wechat-publish-card__footer">
                <span className="wechat-publish-card__time">{item.published_at || "未知时间"}</span>
                {item.url ? (
                  <a className="wechat-publish-card__link" href={item.url} target="_blank" rel="noreferrer">
                    <ExternalLink size={12} />
                    打开
                  </a>
                ) : null}
              </div>
            </article>
          );
        }) : <p className="empty-state">暂时还没有抓到发表记录。</p>}
      </div>
    </section>
  );
}
