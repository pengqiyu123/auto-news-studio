import { Copy, FileSearch, Newspaper, RefreshCcw, RadioTower, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { PaginationControls } from "../../components/PaginationControls";
import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type { AgentWorkflowItem, BriefItem, BriefRecordCounts, BriefRecordException, BriefRecordStatus } from "../../types";

interface BriefsPageProps {
  briefs: BriefItem[];
  page: number;
  pageSize: number;
  total: number;
  view: BriefWorkbenchView;
  workflowView: BriefWorkflowView;
  searchTerm: string;
  recordCounts: BriefRecordCounts;
  agentWorkflows: AgentWorkflowItem[];
  loading?: boolean;
  busyBriefId?: string | null;
  creatingDailyDigest?: boolean;
  abandoningWorkflowId?: string | null;
  loadingBriefDetailId?: string | null;
  onViewChange: (view: BriefWorkbenchView) => void;
  onWorkflowViewChange: (view: BriefWorkflowView) => void;
  onSearchChange: (value: string) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onRefreshBrief: (eventId: string) => Promise<void>;
  onCopyBrief: (brief: BriefItem) => Promise<void>;
  onCopyPackage: (briefId: string) => Promise<void>;
  onSyncBrief: (brief: BriefItem) => Promise<void>;
  onPublishBrief: (brief: BriefItem) => Promise<void>;
  onDeleteBrief: (brief: BriefItem) => Promise<void>;
  onAbandonAgentWorkflow: (workflowSessionId: string) => Promise<void>;
  onCreateDailyDigest: () => Promise<void>;
  onLoadBriefDetail: (briefId: string) => Promise<BriefItem | null>;
}

type BriefWorkbenchView = "all" | "local_only" | "draft_synced" | "published" | "exceptions";
type BriefWorkflowView = "all" | "traditional" | "agent";

const recordStatusLabel: Record<BriefRecordStatus, string> = {
  local_only: "仅本地",
  draft_synced: "已同步",
  published: "已发表",
};

const recordStatusTone: Record<BriefRecordStatus, "success" | "warning" | "neutral"> = {
  local_only: "neutral",
  draft_synced: "success",
  published: "success",
};

const recordExceptionLabel: Record<BriefRecordException, string> = {
  pending_confirmation: "待确认",
  draft_check_failed: "草稿检查失败",
  publish_check_failed: "发表检查失败",
  draft_missing: "草稿丢失",
};

const workflowModeLabel: Record<BriefItem["workflow_mode"], string> = {
  traditional: "传统",
  agent: "Agent",
};

const briefLevelLabel: Record<BriefItem["brief_level"], string> = {
  rule: "规则简报",
  enhanced: "增强简报",
  article: "AI 长文",
};

const workflowOptions: Array<{ value: BriefWorkflowView; label: string }> = [
  { value: "all", label: "全部来源" },
  { value: "traditional", label: "传统" },
  { value: "agent", label: "Agent" },
];

const statusOptions: Array<{ value: BriefWorkbenchView; label: string; countKey?: keyof BriefRecordCounts }> = [
  { value: "all", label: "全部状态", countKey: "all" },
  { value: "local_only", label: "仅本地", countKey: "local_only" },
  { value: "draft_synced", label: "已同步", countKey: "draft_synced" },
  { value: "published", label: "已发表", countKey: "published" },
  { value: "exceptions", label: "异常", countKey: "exceptions" },
];

function matchesView(brief: BriefItem, view: BriefWorkbenchView) {
  if (view === "all") return true;
  if (view === "exceptions") return Boolean(brief.record_exception);
  return brief.record_status === view;
}

function buildSearchText(brief: BriefItem) {
  return [
    brief.title,
    brief.one_line,
    brief.why_it_matters,
    brief.driver_label,
    ...brief.facts,
    ...brief.quotes,
    ...brief.entity_names,
  ].filter(Boolean).join(" ").toLowerCase();
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).trim()}...`;
}

function detailExcerpt(brief: BriefItem): string {
  const text = brief.wechat_markdown || brief.prompt_package_markdown || brief.one_line || "";
  return truncate(text.replace(/^#+\s*/gm, "").replace(/\s+/g, " ").trim(), 420) || "暂无正文摘要。";
}

function todayDateLabel(): string {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isTodayDailyDigest(brief: BriefItem, today = todayDateLabel()): boolean {
  return brief.title.includes("今日科技速递") && brief.title.includes(today);
}

function shouldShowIncludedEvents(brief: BriefItem): boolean {
  return brief.workflow_mode === "traditional" && brief.title.includes("今日科技速递") && Boolean(brief.included_events?.length);
}

function canAbandonWorkflow(workflow?: AgentWorkflowItem | null): workflow is AgentWorkflowItem {
  return Boolean(workflow && (workflow.status === "running" || workflow.status === "failed"));
}

function severityClass(brief: BriefItem) {
  if (brief.stage === "failed" || brief.record_exception) return "severity-failed";
  if (brief.record_status === "published") return "severity-published";
  if (brief.record_status === "draft_synced") return "severity-synced";
  return "severity-prepared";
}

function hasReadingMetrics(brief: BriefItem) {
  return (brief.read_count || 0) > 0;
}

function formatMetricCount(value?: number) {
  return String(value || 0);
}

function renderSkeletonCards(count = 4) {
  return (
    <div className="skeleton-list" aria-label="简报加载中">
      {Array.from({ length: count }, (_, index) => (
        <div key={`brief-skeleton-${index}`} className="skeleton-card">
          <div className="skeleton-line skeleton-short" />
          <div className="skeleton-line skeleton-long" />
          <div className="skeleton-line skeleton-medium" />
        </div>
      ))}
    </div>
  );
}

export function BriefsPage({
  briefs,
  page,
  pageSize,
  total,
  view,
  workflowView,
  searchTerm,
  recordCounts,
  agentWorkflows,
  loading = false,
  busyBriefId,
  creatingDailyDigest = false,
  abandoningWorkflowId,
  loadingBriefDetailId,
  onViewChange,
  onWorkflowViewChange,
  onSearchChange,
  onPageChange,
  onPageSizeChange,
  onRefreshBrief,
  onCopyBrief,
  onCopyPackage,
  onSyncBrief,
  onPublishBrief,
  onDeleteBrief,
  onAbandonAgentWorkflow,
  onCreateDailyDigest,
  onLoadBriefDetail,
}: BriefsPageProps) {
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());
  const workflowCounts = useMemo(
    () => ({
      all: briefs.length,
      traditional: briefs.filter((brief) => brief.workflow_mode === "traditional").length,
      agent: briefs.filter((brief) => brief.workflow_mode === "agent").length,
    }),
    [briefs],
  );
  const workflowMap = useMemo(
    () => new Map(agentWorkflows.map((workflow) => [workflow.workflow_session_id, workflow])),
    [agentWorkflows],
  );
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const filtered = useMemo(() => {
    return [...briefs]
      .filter((brief) => workflowView === "all" || brief.workflow_mode === workflowView)
      .filter((brief) => matchesView(brief, view))
      .filter((brief) => !normalizedSearch || buildSearchText(brief).includes(normalizedSearch))
      .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
  }, [briefs, normalizedSearch, view, workflowView]);
  const hasTodayDigest = useMemo(() => briefs.some((brief) => isTodayDailyDigest(brief)), [briefs]);
  const dailyDigestButtonLabel = hasTodayDigest ? "今日速递已生成" : creatingDailyDigest ? "生成中..." : "生成今日速递";

  function toggleExpanded(brief: BriefItem) {
    const nextExpanded = !expandedCards.has(brief.id);
    setExpandedCards((previous) => {
      const next = new Set(previous);
      if (nextExpanded) {
        next.add(brief.id);
      } else {
        next.delete(brief.id);
      }
      return next;
    });
    if (nextExpanded) {
      void onLoadBriefDetail(brief.id);
    }
  }

  function renderEmptyState() {
    if (!briefs.length) {
      return <p className="empty-state">还没有生成简报。</p>;
    }
    if (normalizedSearch) {
      return <p className="empty-state">没有匹配的简报。</p>;
    }
    return <p className="empty-state">当前筛选条件下没有简报。</p>;
  }

  function renderBriefCard(brief: BriefItem) {
    const expanded = expandedCards.has(brief.id);
    const busy = busyBriefId === brief.id;
    const workflow = brief.workflow_session_id ? workflowMap.get(brief.workflow_session_id) : null;
    const workflowBusy = Boolean(workflow && abandoningWorkflowId === workflow.workflow_session_id);
    const visibleTags = brief.entity_names.slice(0, 4);
    const hiddenTagCount = Math.max(brief.entity_names.length - visibleTags.length, 0);
    const representativeLink = brief.source_links[0] ?? brief.preview_url ?? brief.wechat_editor_url ?? null;
    const loadingDetail = loadingBriefDetailId === brief.id;

    return (
      <article key={brief.id} className={`briefs-card ${severityClass(brief)}`}>
        <div className="briefs-card-topline">
          <div>
            <span className={`status-badge status-${brief.record_exception ? "danger" : recordStatusTone[brief.record_status]} status-badge-compact`}>
              {brief.record_exception ? recordExceptionLabel[brief.record_exception] : recordStatusLabel[brief.record_status]}
            </span>
            <span className={`status-badge status-${brief.workflow_mode === "agent" ? "info" : "neutral"} status-badge-compact`}>
              {workflowModeLabel[brief.workflow_mode]}
            </span>
            <span className="entity-tag entity-tag-muted">{briefLevelLabel[brief.brief_level]}</span>
          </div>
          <span>{formatRelativeTime(brief.updated_at, "刚更新")}</span>
        </div>

        <h3 className="briefs-card-title">{brief.title}</h3>
        <p className="briefs-card-summary">{brief.one_line || "尚未生成一句话结论。"}</p>

        <div className="briefs-card-meta">
          <span>来源 {brief.source_links.length}</span>
          <span>事实 {brief.facts.length}</span>
          <span>引文 {brief.quotes.length}</span>
          {visibleTags.map((name) => (
            <span key={`${brief.id}-${name}`} className="entity-tag entity-tag-muted">
              {name}
            </span>
          ))}
          {hiddenTagCount ? <span className="entity-tag entity-tag-muted">+{hiddenTagCount}</span> : null}
          {brief.workflow_session_id ? <span>会话 {brief.workflow_session_id}</span> : null}
        </div>

        <div className="briefs-card-actions">
          <button type="button" className="briefs-expand" onClick={() => toggleExpanded(brief)}>
            {expanded ? "收起详情 ▲" : loadingDetail ? "详情加载中..." : "查看详情 ▼"}
          </button>
          {representativeLink ? <a href={representativeLink} target="_blank" rel="noreferrer">查看原文</a> : null}
          <button
            type="button"
            className="ghost-button compact"
            disabled={busy}
            onClick={() => {
              if (!window.confirm("确认重新生成简报？将消耗 LLM token。")) return;
              void onRefreshBrief(brief.event_id);
            }}
          >
            <RefreshCcw size={14} />
            重新生成
          </button>
          <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onSyncBrief(brief)}>
            <RadioTower size={14} />
            同步微信
          </button>
          <button
            type="button"
            className="ghost-button compact"
            disabled={busy}
            onClick={() => {
              if (!window.confirm(`确认进入《${brief.title}》的微信发表流程？系统会停在微信验证二维码。`)) return;
              void onPublishBrief(brief);
            }}
          >
            <RadioTower size={14} />
            发表到验证
          </button>
          <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onCopyBrief(brief)}>
            <Copy size={14} />
            复制
          </button>
          <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onCopyPackage(brief.id)}>
            <Copy size={14} />
            来源包
          </button>
          <button
            type="button"
            className="ghost-button compact danger"
            disabled={busy}
            onClick={() => {
              if (!window.confirm(`确认删除《${brief.title}》？此操作不可撤销。`)) return;
              void onDeleteBrief(brief);
            }}
          >
            <Trash2 size={14} />
            删除
          </button>
          {canAbandonWorkflow(workflow) ? (
            <button
              type="button"
              className="ghost-button compact danger"
              disabled={busy || workflowBusy}
              onClick={() => {
                if (!window.confirm("确定放弃这个 Agent 会话吗？这不会删除已保存的文章，只会解除未完成会话状态。")) return;
                void onAbandonAgentWorkflow(workflow.workflow_session_id);
              }}
            >
              {workflowBusy ? "放弃中..." : "放弃 Agent 会话"}
            </button>
          ) : null}
        </div>

        {expanded ? (
          <div className="briefs-detail">
            <div className="briefs-detail-head">
              <span>深挖详情</span>
              {loadingDetail ? <span className="subtle">加载中...</span> : null}
            </div>
            <div className="draft-list-block">
              <span>为什么值得关注</span>
              <p>{brief.why_it_matters || "当前仍以规则简报为主，可继续补充判断。"}</p>
            </div>
            {!!brief.facts.length ? (
              <div className="draft-list-block">
                <span>核心事实</span>
                <ul>
                  {brief.facts.slice(0, 5).map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="draft-list-block">
              <span>文章详情</span>
              <p>{detailExcerpt(brief)}</p>
            </div>
            {shouldShowIncludedEvents(brief) ? (
              <div className="draft-list-block">
                <span>收录事件</span>
                <ul>
                  {brief.included_events?.map((event) => (
                    <li key={event.event_id}>
                      {event.representative_link ? (
                        <a href={event.representative_link} target="_blank" rel="noreferrer">{event.title}</a>
                      ) : event.title}
                      <div className="briefs-card-meta">
                        <span>{event.alert_state}</span>
                        <span>来源 {event.source_count}</span>
                        <span>深挖 {event.deep_dive_status ?? "pending"}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {workflow ? (
              <div className="briefs-card-meta">
                <span>Agent 状态 {workflow.status}</span>
                <span>步骤 {workflow.current_step}</span>
                <span>更新 {formatRelativeTime(workflow.updated_at, "时间未知")}</span>
                {workflow.last_error ? <span className="error-note">{workflow.last_error}</span> : null}
              </div>
            ) : null}
            {hasReadingMetrics(brief) ? (
              <div className="briefs-metrics-block">
                <span>阅读数据</span>
                <strong>阅读 {formatMetricCount(brief.read_count)}</strong>
                <strong>点赞 {formatMetricCount(brief.like_count)}</strong>
                <strong>分享 {formatMetricCount(brief.share_count)}</strong>
                <strong>留言 {formatMetricCount(brief.comment_count)}</strong>
                {(brief.recommend_count || 0) > 0 ? <strong>推荐 {brief.recommend_count}</strong> : null}
                {(brief.highlight_count || 0) > 0 ? <strong>划线 {brief.highlight_count}</strong> : null}
                {(brief.reprint_count || 0) > 0 ? <strong>转载 {brief.reprint_count}</strong> : null}
                {brief.tip_amount && brief.tip_amount !== "0.00" ? <strong>赞赏 ¥{brief.tip_amount}</strong> : null}
                {brief.metrics_fetched_at ? <em>数据更新于 {formatDateTime(brief.metrics_fetched_at, { fallback: "时间未知" })}</em> : null}
              </div>
            ) : null}
            {brief.last_error ? <span className="error-note">{brief.last_error}</span> : null}
            <button type="button" className="briefs-expand" onClick={() => toggleExpanded(brief)}>
              收起详情 ▲
            </button>
          </div>
        ) : null}
      </article>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">简报/文章</p>
          <h2>简报/文章</h2>
        </div>
        <div className="panel-header-actions">
          <span className="subtle">{total} 篇文章</span>
          <button
            type="button"
            className="primary-button compact"
            disabled={creatingDailyDigest || hasTodayDigest}
            onClick={() => void onCreateDailyDigest()}
          >
            <Newspaper size={14} />
            {dailyDigestButtonLabel}
          </button>
        </div>
      </div>

      <div className="briefs-filter-bar">
        <label className="briefs-filter-group">
          <span>来源</span>
          <select aria-label="来源筛选" value={workflowView} disabled={loading} onChange={(event) => onWorkflowViewChange(event.target.value as BriefWorkflowView)}>
            {workflowOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label} ({workflowCounts[option.value]})
              </option>
            ))}
          </select>
        </label>

        <label className="briefs-filter-group">
          <span>状态</span>
          <select aria-label="状态筛选" value={view} disabled={loading} onChange={(event) => onViewChange(event.target.value as BriefWorkbenchView)}>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}{option.countKey ? ` (${recordCounts[option.countKey]})` : ""}
              </option>
            ))}
          </select>
        </label>

        <label className="draft-search briefs-search">
          <FileSearch size={16} />
          <input
            type="search"
            value={searchTerm}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜索标题、结论、价值判断"
            aria-label="搜索简报"
          />
        </label>

        <PaginationControls
          page={page}
          pageSize={pageSize}
          total={total}
          currentCount={filtered.length}
          filteredCount={filtered.length}
          itemLabel="篇文章"
          loading={loading}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      </div>

      <div className="briefs-list">
        {loading && filtered.length === 0 ? renderSkeletonCards() : (
          filtered.length ? filtered.map((brief) => renderBriefCard(brief)) : renderEmptyState()
        )}
      </div>
    </section>
  );
}
