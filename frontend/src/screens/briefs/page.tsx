import { Copy, FileSearch, Newspaper, RefreshCcw, RadioTower, Trash2 } from "lucide-react";
import { useMemo } from "react";

import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type { AgentWorkflowItem, BriefItem, BriefRecordCounts, BriefRecordException, BriefRecordStatus } from "../../types";
import { PaginationControls } from "../../components/PaginationControls";

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
  onDeleteBrief: (brief: BriefItem) => Promise<void>;
  onAbandonAgentWorkflow: (workflowSessionId: string) => Promise<void>;
  onCreateDailyDigest: () => Promise<void>;
  onLoadBriefDetail: (briefId: string) => Promise<BriefItem | null>;
}

type BriefWorkbenchView = "all" | "local_only" | "draft_synced" | "published" | "exceptions";
type BriefWorkflowView = "all" | "traditional" | "agent";

const recordStatusLabel: Record<BriefRecordStatus, string> = {
  local_only: "仅本地",
  draft_synced: "已同步草稿箱",
  published: "已同步发表记录",
};

const briefLevelLabel: Record<BriefItem["brief_level"], string> = {
  rule: "传统简报",
  enhanced: "增强简报",
  article: "AI 长文",
};

const recordStatusTone: Record<BriefRecordStatus, "success" | "warning" | "info"> = {
  local_only: "warning",
  draft_synced: "info",
  published: "success",
};

const recordExceptionLabel: Record<BriefRecordException, string> = {
  pending_confirmation: "待确认",
  draft_check_failed: "草稿箱检查失败",
  publish_check_failed: "发表记录检查失败",
  draft_missing: "草稿已丢失",
};

const workflowModeLabel: Record<BriefItem["workflow_mode"], string> = {
  traditional: "传统",
  agent: "Agent",
};

function matchesView(brief: BriefItem, view: BriefWorkbenchView) {
  if (view === "all") return true;
  if (view === "exceptions") return Boolean(brief.record_exception);
  return brief.record_status === view;
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).trim()}...`;
}

function detailExcerpt(brief: BriefItem): string {
  const text = brief.wechat_markdown || brief.one_line || "";
  return truncate(text.replace(/^#+\s*/gm, "").replace(/\s+/g, " ").trim(), 240) || "暂无正文摘要。";
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
  onDeleteBrief,
  onAbandonAgentWorkflow,
  onCreateDailyDigest,
  onLoadBriefDetail,
}: BriefsPageProps) {
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
  const filtered = useMemo(
    () => [...briefs].sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()),
    [briefs],
  );
  const hasTodayDigest = useMemo(() => briefs.some((brief) => isTodayDailyDigest(brief)), [briefs]);
  const dailyDigestButtonLabel = hasTodayDigest ? "今日速递已生成" : creatingDailyDigest ? "生成中..." : "生成今日速递";

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">简报</p>
          <h2>共享总账：区分传统链与 Agent 会话产物</h2>
        </div>
        <div className="panel-header-actions">
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

      <div className="segmented-control draft-workbench-tabs">
        <button type="button" className={workflowView === "all" ? "segment-active" : ""} onClick={() => onWorkflowViewChange("all")}>
          全部
          <strong>{workflowCounts.all}</strong>
        </button>
        <button type="button" className={workflowView === "traditional" ? "segment-active" : ""} onClick={() => onWorkflowViewChange("traditional")}>
          传统
          <strong>{workflowCounts.traditional}</strong>
        </button>
        <button type="button" className={workflowView === "agent" ? "segment-active" : ""} onClick={() => onWorkflowViewChange("agent")}>
          Agent
          <strong>{workflowCounts.agent}</strong>
        </button>
      </div>

      <div className="segmented-control draft-workbench-tabs">
        <button type="button" className={view === "all" ? "segment-active" : ""} onClick={() => onViewChange("all")}>
          全部
          <strong>{recordCounts.all}</strong>
        </button>
        <button type="button" className={view === "local_only" ? "segment-active" : ""} onClick={() => onViewChange("local_only")}>
          仅本地
          <strong>{recordCounts.local_only}</strong>
        </button>
        <button type="button" className={view === "draft_synced" ? "segment-active" : ""} onClick={() => onViewChange("draft_synced")}>
          已同步草稿箱
          <strong>{recordCounts.draft_synced}</strong>
        </button>
        <button type="button" className={view === "published" ? "segment-active" : ""} onClick={() => onViewChange("published")}>
          已同步发表记录
          <strong>{recordCounts.published}</strong>
        </button>
        <button type="button" className={view === "exceptions" ? "segment-active" : ""} onClick={() => onViewChange("exceptions")}>
          待确认
          <strong>{recordCounts.exceptions}</strong>
        </button>
      </div>

      <div className="draft-toolbar">
        <label className="draft-search">
          <FileSearch size={16} />
          <input
            value={searchTerm}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜索标题、结论、价值判断"
          />
        </label>
        <div className="draft-toolbar-summary">
          <span>当前显示</span>
          <strong>{filtered.length}</strong>
          <span>/ {total} 条</span>
        </div>
      </div>

      <PaginationControls
        page={page}
        pageSize={pageSize}
        total={total}
        currentCount={filtered.length}
        itemLabel="条简报"
        loading={loading}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />

      <div className="intel-list">
        {filtered.length ? filtered.map((brief) => {
          const busy = busyBriefId === brief.id;
          const workflow = brief.workflow_session_id ? workflowMap.get(brief.workflow_session_id) : null;
          const workflowBusy = Boolean(workflow && abandoningWorkflowId === workflow.workflow_session_id);
          return (
            <article key={brief.id} className="intel-row-card">
              <div className="intel-card-topline">
                <span className={`status-badge status-${recordStatusTone[brief.record_status]}`}>
                  {recordStatusLabel[brief.record_status]}
                </span>
                {brief.record_exception ? (
                  <span className="status-badge status-danger">{recordExceptionLabel[brief.record_exception]}</span>
                ) : null}
                <span className={`status-badge status-${brief.workflow_mode === "agent" ? "info" : "neutral"}`}>
                  {workflowModeLabel[brief.workflow_mode]}
                </span>
                <span>{briefLevelLabel[brief.brief_level]}</span>
              </div>
              <strong>{brief.title}</strong>
              <p>{truncate(brief.one_line || "尚未生成一句话结论。", 160)}</p>
              <div className="intel-score-row">
                <span>{formatRelativeTime(brief.updated_at, "刚更新")}</span>
                <span>草稿箱: {brief.draft_remote_updated_at ? `已命中 ${formatDateTime(brief.draft_remote_updated_at, { fallback: "暂无" })}` : "未命中"}</span>
                <span>发表记录: {brief.publish_record_published_at ? brief.publish_record_published_at : "未命中"}</span>
              </div>
              <div className="intel-score-row">
                <span>{brief.facts.length} 条事实</span>
                <span>{brief.source_links.length} 条来源</span>
                <span>{brief.quotes.length} 条引文</span>
              </div>
              {brief.workflow_session_id ? (
                <div className="intel-score-row">
                  <span>会话 {brief.workflow_session_id}</span>
                  <span>步骤 {workflow?.current_step ?? "article_saved"}</span>
                  <span>状态 {workflow?.status ?? "running"}</span>
                </div>
              ) : null}
              <div className="draft-list-block">
                <span>为什么值得关注</span>
                <p>{brief.why_it_matters || "当前仍以规则简报为主，可继续补充判断。"}</p>
              </div>
              {!!brief.facts.length ? (
                <div className="draft-list-block">
                  <span>核心事实</span>
                  <ul>
                    {brief.facts.slice(0, 4).map((fact) => (
                      <li key={fact}>{fact}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <details className="draft-list-block">
                <summary
                  onClick={() => {
                    if (!brief.wechat_markdown || !brief.prompt_package_markdown || (brief.title.includes("今日科技速递") && !brief.included_events)) {
                      void onLoadBriefDetail(brief.id);
                    }
                  }}
                >
                  文章详情{loadingBriefDetailId === brief.id ? "（加载中...）" : ""}
                </summary>
                <p>{detailExcerpt(brief)}</p>
                {shouldShowIncludedEvents(brief) ? (
                  <div className="draft-list-block">
                    <span>收录事件</span>
                    <ul>
                      {brief.included_events?.map((event) => (
                        <li key={event.event_id}>
                          {event.representative_link ? (
                            <a href={event.representative_link} target="_blank" rel="noreferrer">{event.title}</a>
                          ) : event.title}
                          <div className="intel-score-row">
                            <span>{event.alert_state}</span>
                            <span>来源 {event.source_count}</span>
                            <span>深挖 {event.deep_dive_status ?? "pending"}</span>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </details>
              {(brief.read_count || 0) > 0 || (brief.like_count || 0) > 0 || (brief.share_count || 0) > 0 ? (
                <div className="intel-score-row" style={{ gap: "12px" }}>
                  <span style={{ color: "#576b95", fontWeight: 600 }}>阅读 {brief.read_count || 0}</span>
                  <span>点赞 {brief.like_count || 0}</span>
                  <span>分享 {brief.share_count || 0}</span>
                  {(brief.comment_count || 0) > 0 ? <span>留言 {brief.comment_count}</span> : null}
                  {(brief.recommend_count || 0) > 0 ? <span>推荐 {brief.recommend_count}</span> : null}
                  {(brief.highlight_count || 0) > 0 ? <span>划线 {brief.highlight_count}</span> : null}
                  {(brief.reprint_count || 0) > 0 ? <span>转载 {brief.reprint_count}</span> : null}
                  {brief.tip_amount !== "0.00" ? <span>赞赏 ¥{brief.tip_amount}</span> : null}
                  <span style={{ color: "#999", fontSize: "11px" }}>
                    {brief.metrics_fetched_at ? formatRelativeTime(brief.metrics_fetched_at, "") : ""}
                  </span>
                </div>
              ) : null}
              {brief.last_error ? <span className="error-note">{brief.last_error}</span> : null}
              <div className="intel-inline-actions">
                <span>{formatDateTime(brief.updated_at, { fallback: "暂无" })}</span>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => {
                  if (!window.confirm("确认重新生成简报？将消耗 LLM token。")) return;
                  void onRefreshBrief(brief.event_id);
                }}>
                  <RefreshCcw size={14} />
                  重新生成
                </button>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onSyncBrief(brief)}>
                  <RadioTower size={14} />
                  同步到微信草稿箱
                </button>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onCopyBrief(brief)}>
                  <Copy size={14} />
                  复制简报
                </button>
                <button type="button" className="ghost-button compact" disabled={busy} onClick={() => void onCopyPackage(brief.id)}>
                  <Copy size={14} />
                  复制来源包
                </button>
                <button type="button" className="ghost-button compact danger" disabled={busy} onClick={() => void onDeleteBrief(brief)}>
                  <Trash2 size={14} />
                  删除简报
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
            </article>
          );
        }) : <p className="empty-state">当前筛选条件下没有简报。</p>}
      </div>
    </section>
  );
}
