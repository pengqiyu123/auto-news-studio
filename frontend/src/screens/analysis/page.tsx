import { BarChart3, Check, Edit3, FileText, RefreshCw, X } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState } from "react";

import { EntityTrendIndicator } from "../../components/EntityTrendIndicator";
import { buildTrendLookup, getTrendForEntity } from "../../lib/trends";
import type {
  AnalysisBatchRunInfo,
  AnalysisFeedbackPayload,
  AnalysisFeedbackStats,
  AnalysisFeedbackType,
  AnalysisReportItem,
  AnalysisReportRequest,
  AnalysisReportSummary,
  AnalysisSignalInfo,
  AnalysisTopicEventInfo,
  EventRelationInfo,
  TemporalRuleInfo,
  TopicInfo,
  TopicPeriodicityInfo,
  TrendSignalInfo,
} from "../../types";

interface AnalysisPageProps {
  topics: TopicInfo[];
  trends: TrendSignalInfo[];
  signals: AnalysisSignalInfo[];
  relatedEvents: EventRelationInfo[];
  topicsPeriodicity?: TopicPeriodicityInfo[];
  temporalRules?: TemporalRuleInfo[];
  batchStatus?: AnalysisBatchRunInfo[];
  topicEventsByTopicId?: Record<string, AnalysisTopicEventInfo[]>;
  loadingTopicIds?: Set<string>;
  reports?: AnalysisReportSummary[];
  currentReport?: AnalysisReportItem | null;
  reportDetailsById?: Record<string, AnalysisReportItem>;
  feedbackStats?: AnalysisFeedbackStats | null;
  generatingReport?: boolean;
  loading?: boolean;
  timeRange: "7d" | "30d" | "all";
  onTimeRangeChange: (value: "7d" | "30d" | "all") => void;
  onRefresh: () => Promise<void>;
  onLoadTopicEvents: (topicId: string) => Promise<void>;
  onNavigate: (tab: "events", context: { entityId: string }) => void;
  onSubmitFeedback: (payload: AnalysisFeedbackPayload) => Promise<unknown>;
  onGenerateReport: (payload: AnalysisReportRequest) => Promise<AnalysisReportItem>;
  onLoadReportDetail?: (reportId: string) => Promise<AnalysisReportItem | null>;
}

const TIME_RANGE_OPTIONS: Array<{ key: "7d" | "30d" | "all"; label: string }> = [
  { key: "7d", label: "7天" },
  { key: "30d", label: "30天" },
  { key: "all", label: "全部" },
];

function relationTypeLabel(relationType: string) {
  if (relationType.includes("entity_shared")) return "实体重合";
  if (relationType.includes("topic_shared")) return "主题同类";
  if (relationType.includes("temporal_proximity")) return "时间接近";
  if (relationType.includes("anchor_overlap")) return "锚点重合";
  return relationType || "关联";
}

function emptyState() {
  return <p className="empty-state">暂无分析数据。</p>;
}

function feedbackLabel(type: AnalysisFeedbackType) {
  if (type === "confirm") return "准确";
  if (type === "correct") return "部分有误";
  return "偏离事实";
}

function formatReportScope(scope: string) {
  if (scope === "daily") return "日报";
  if (scope === "weekly") return "周报";
  if (scope === "monthly") return "月报";
  return scope || "报告";
}

function defaultReportWindow(scope: "daily" | "weekly" | "monthly") {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - (scope === "monthly" ? 30 : scope === "weekly" ? 7 : 1));
  return {
    date_from: start.toISOString().slice(0, 10),
    date_to: end.toISOString().slice(0, 10),
  };
}

function resolveReportScope(timeRange: "7d" | "30d" | "all"): "daily" | "weekly" | "monthly" {
  if (timeRange === "7d") return "daily";
  return "monthly";
}

function formatAccuratePct(value: number | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  const normalized = value > 1 ? value : value * 100;
  return Math.round(Math.max(0, Math.min(100, normalized)));
}

function formatBatchTaskName(taskName: string) {
  const labels: Record<string, string> = {
    topic_modeling: "主题建模",
    event_relations: "关联计算",
    trend_detection: "趋势检测",
    topic_periodicity: "周期检测",
    temporal_rules: "时序规则",
  };
  return labels[taskName] ?? taskName;
}

function batchStatusIcon(status: AnalysisBatchRunInfo["status"]) {
  if (status === "success") return "✓";
  if (status === "failed") return "✗";
  return "⟳";
}

function formatBatchTime(value?: string | null) {
  if (!value) return "";
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return value;
  return new Date(parsed).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function safeMarkdownHref(href: string) {
  const trimmed = href.trim();
  if (/^(https?:\/\/|mailto:)/i.test(trimmed)) return trimmed;
  return null;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const tokenPattern = /`[^`]+`|\*\*[^*]+?\*\*|\*[^*]+?\*|\[[^\]\n]+\]\([^) \n]+\)/g;
  let lastIndex = 0;

  text.replace(tokenPattern, (token, index: number) => {
    if (index > lastIndex) {
      nodes.push(text.slice(lastIndex, index));
    }

    const key = `${token}-${index}`;
    if (token.startsWith("`")) {
      nodes.push(<code key={key} className="analysis-report-inline-code">{token.slice(1, -1)}</code>);
    } else if (token.startsWith("**")) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("*")) {
      nodes.push(<em key={key}>{token.slice(1, -1)}</em>);
    } else {
      const match = token.match(/^\[([^\]\n]+)\]\(([^) \n]+)\)$/);
      const href = match ? safeMarkdownHref(match[2]) : null;
      if (match && href) {
        nodes.push(
          <a key={key} className="analysis-report-link" href={href} target="_blank" rel="noreferrer noopener">
            {match[1]}
          </a>,
        );
      } else {
        nodes.push(match?.[1] ?? token);
      }
    }

    lastIndex = index + token.length;
    return token;
  });

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

function renderMarkdown(markdown: string) {
  const blocks: ReactNode[] = [];
  const lines = markdown.split(/\r?\n/);
  let codeLines: string[] = [];
  let inCodeBlock = false;

  function pushCodeBlock(key: string) {
    blocks.push(
      <pre key={key} className="analysis-report-code-block">
        <code>{codeLines.join("\n")}</code>
      </pre>,
    );
    codeLines = [];
  }

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();
    if (line.startsWith("```")) {
      if (inCodeBlock) {
        pushCodeBlock(`code-${index}`);
      }
      inCodeBlock = !inCodeBlock;
      return;
    }

    if (inCodeBlock) {
      codeLines.push(rawLine);
      return;
    }

    if (!line) return;

    if (line.startsWith("## ")) {
      blocks.push(<h4 key={`${line}-${index}`}>{renderInlineMarkdown(line.slice(3))}</h4>);
      return;
    }
    if (line.startsWith("# ")) {
      blocks.push(<h3 key={`${line}-${index}`}>{renderInlineMarkdown(line.slice(2))}</h3>);
      return;
    }
    if (line.startsWith("- ")) {
      blocks.push(<p key={`${line}-${index}`} className="analysis-report-bullet">{renderInlineMarkdown(line.slice(2))}</p>);
      return;
    }
    blocks.push(<p key={`${line}-${index}`}>{renderInlineMarkdown(line)}</p>);
  });

  if (inCodeBlock && codeLines.length) {
    pushCodeBlock("code-open");
  }

  return blocks;
}

export function AnalysisPage({
  topics,
  trends,
  signals,
  relatedEvents,
  topicsPeriodicity = [],
  temporalRules = [],
  batchStatus = [],
  topicEventsByTopicId = {},
  loadingTopicIds = new Set<string>(),
  reports = [],
  currentReport = null,
  reportDetailsById = {},
  feedbackStats = null,
  generatingReport = false,
  loading = false,
  timeRange,
  onTimeRangeChange,
  onRefresh,
  onLoadTopicEvents,
  onNavigate,
  onSubmitFeedback,
  onGenerateReport,
  onLoadReportDetail,
}: AnalysisPageProps) {
  const [expandedTopicIds, setExpandedTopicIds] = useState<Set<string>>(() => new Set());
  const [batchStatusOpen, setBatchStatusOpen] = useState(false);
  const [expandedReportIds, setExpandedReportIds] = useState<Set<string>>(() => new Set());
  const [feedbackMode, setFeedbackMode] = useState<AnalysisFeedbackType | null>(null);
  const [feedbackNote, setFeedbackNote] = useState("");
  const [submittedFeedback, setSubmittedFeedback] = useState<AnalysisFeedbackType | null>(null);
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const trendLookup = useMemo(() => buildTrendLookup(trends), [trends]);
  const topTopics = useMemo(() => topics.slice(0, 8), [topics]);
  const topSignals = useMemo(() => signals.slice(0, 8), [signals]);
  const topRelations = useMemo(() => relatedEvents.slice(0, 6), [relatedEvents]);
  const topPeriodicity = useMemo(() => topicsPeriodicity.slice(0, 5), [topicsPeriodicity]);
  const topTemporalRules = useMemo(() => temporalRules.slice(0, 5), [temporalRules]);
  const topReports = useMemo(() => reports.slice(0, 6), [reports]);
  const latestSuccessfulBatch = useMemo(() => {
    return batchStatus.find((item) => item.status === "success") ?? null;
  }, [batchStatus]);
  const latestBatchByTask = useMemo(() => {
    const result = new Map<string, AnalysisBatchRunInfo>();
    batchStatus.forEach((item) => {
      if (!result.has(item.task_name)) {
        result.set(item.task_name, item);
      }
    });
    return result;
  }, [batchStatus]);
  const maxTopicCount = useMemo(
    () => Math.max(1, ...topTopics.map((item) => Number(item.event_count) || 0)),
    [topTopics],
  );
  const leadingSignal = topSignals[0] ?? null;

  function toggleTopic(topicId: string) {
    const isExpanded = expandedTopicIds.has(topicId);
    setExpandedTopicIds((current) => {
      const next = new Set(current);
      if (isExpanded) {
        next.delete(topicId);
      } else {
        next.add(topicId);
      }
      return next;
    });
    if (!isExpanded) {
      void onLoadTopicEvents(topicId);
    }
  }

  async function submitFeedback(type: AnalysisFeedbackType, note = "") {
    const targetId = leadingSignal?.entity_id || "analysis-summary";
    setSubmittingFeedback(true);
    setSubmittedFeedback(type);
    try {
      await onSubmitFeedback({
        target_type: "analysis_summary",
        target_id: targetId,
        feedback_type: type,
        correction: note.trim() ? { note: note.trim() } : undefined,
      });
      setFeedbackMode(null);
      setFeedbackNote("");
    } catch {
      setSubmittedFeedback(null);
    } finally {
      setSubmittingFeedback(false);
    }
  }

  async function handleGenerateReport() {
    const scope = resolveReportScope(timeRange);
    const window = defaultReportWindow(scope);
    await onGenerateReport({
      scope,
      date_from: window.date_from,
      date_to: window.date_to,
      focus_entities: topSignals.slice(0, 5).map((item) => item.entity_id),
      focus_topics: topTopics.slice(0, 5).map((item) => item.topic_id),
    });
  }

  function toggleReport(reportId: string) {
    const expanded = expandedReportIds.has(reportId);
    setExpandedReportIds((current) => {
      const next = new Set(current);
      if (expanded) {
        next.delete(reportId);
      } else {
        next.add(reportId);
      }
      return next;
    });
    if (!expanded && !reportDetailsById[reportId]) {
      void onLoadReportDetail?.(reportId);
    } else if (!expanded) {
      void onLoadReportDetail?.(reportId);
    }
  }

  return (
    <div className="analysis-page">
      <section className="panel analysis-hero">
        <div className="panel-header compact">
          <div>
            <p className="eyebrow">分析中心</p>
            <h2>分析中心</h2>
          </div>
          <div className="analysis-hero-actions">
            <div className="analysis-range-switch" role="tablist" aria-label="时间范围">
              {TIME_RANGE_OPTIONS.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  className={`filter-chip compact ${timeRange === option.key ? "filter-chip-active" : ""}`}
                  onClick={() => onTimeRangeChange(option.key)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <button type="button" className="ghost-button compact" onClick={() => void onRefresh()} disabled={loading}>
              <RefreshCw size={14} className={loading ? "spin-icon" : ""} />
              {loading ? "加载中" : "刷新"}
            </button>
          </div>
        </div>
        <div className="analysis-summary-grid">
          <div className="analysis-summary-card">
            <span>整体覆盖</span>
            <strong>{signals.length} 个活跃实体</strong>
            <p>覆盖 {topics.length} 个主题，已识别 {relatedEvents.length} 组事件关联。</p>
          </div>
          <div className="analysis-summary-card">
            <span>最新信号</span>
            <strong>{leadingSignal?.entity_name || "暂无信号"}</strong>
            <p>{leadingSignal?.latest_event_title || "暂无最新事件摘要。"}</p>
          </div>
          <div className="analysis-summary-card">
            <span>趋势分布</span>
            <strong>{trends.length} 条趋势线索</strong>
            <p>{leadingSignal?.trend_label || "等待更多快照沉淀后再判断。"}</p>
          </div>
        </div>
        <div className="analysis-batch-status">
          <button
            type="button"
            className="analysis-batch-status-trigger"
            onClick={() => setBatchStatusOpen((current) => !current)}
            aria-expanded={batchStatusOpen}
          >
            <span className="analysis-batch-status-main">
              <strong>批处理状态</strong>
              <span>
                {latestSuccessfulBatch
                  ? `上次成功 ${formatBatchTime(latestSuccessfulBatch.finished_at || latestSuccessfulBatch.started_at)}`
                  : "定时分析未启动，当前数据为实时计算"}
              </span>
            </span>
            <span className="analysis-batch-icons" aria-hidden="true">
              {["topic_modeling", "event_relations", "trend_detection", "topic_periodicity", "temporal_rules"].map((taskName) => {
                const item = latestBatchByTask.get(taskName);
                return (
                  <span
                    key={taskName}
                    className={`analysis-batch-icon analysis-batch-icon-${item?.status ?? "idle"}`}
                    title={formatBatchTaskName(taskName)}
                  >
                    {item ? batchStatusIcon(item.status) : "•"}
                  </span>
                );
              })}
            </span>
            <span className="analysis-topic-chevron" aria-hidden="true">{batchStatusOpen ? "▲" : "▼"}</span>
          </button>
          {batchStatusOpen ? (
            <div className="analysis-batch-status-detail">
              {batchStatus.length ? (
                batchStatus.slice(0, 10).map((item) => (
                  <div key={item.id} className="analysis-batch-run">
                    <span className={`analysis-batch-icon analysis-batch-icon-${item.status}`}>{batchStatusIcon(item.status)}</span>
                    <strong>{item.task_name}</strong>
                    <span>{formatBatchTaskName(item.task_name)}</span>
                    <span>{formatBatchTime(item.finished_at || item.started_at)}</span>
                    <span>{item.items_processed} 项</span>
                    {item.error_message ? <em>{item.error_message}</em> : null}
                  </div>
                ))
              ) : (
                <p className="empty-state">定时分析未启动，当前数据为实时计算</p>
              )}
            </div>
          ) : null}
        </div>
      </section>

      <section className="panel analysis-periodicity-panel">
        <div className="panel-header compact">
          <div>
            <p className="eyebrow">周期</p>
            <h2>周期检测</h2>
          </div>
          <span className="subtle">Top {topPeriodicity.length}</span>
        </div>
        {topPeriodicity.length ? (
          <div className="analysis-periodicity-list">
            {topPeriodicity.map((item) => (
              <div key={item.topic_id} className="analysis-periodicity-item">
                <div className="analysis-periodicity-main">
                  <strong>{item.label || item.topic_id}</strong>
                  <span>{item.period_days} 天周期</span>
                </div>
                <div className="analysis-periodicity-meter" aria-label={`${item.label || item.topic_id} 周期置信度`}>
                  <div
                    className="analysis-periodicity-meter-fill"
                    style={{ width: `${Math.max(8, Math.round((item.confidence || 0) * 100))}%` }}
                  />
                </div>
                <span className="analysis-periodicity-confidence">{Math.round((item.confidence || 0) * 100)}%</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-state">暂无周期信号。</p>
        )}
      </section>

      <div className="analysis-grid-row">
        <section className="panel analysis-topics-panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">主题</p>
              <h2>主题趋势</h2>
            </div>
            <span className="subtle">Top {topTopics.length}</span>
          </div>
          {topTopics.length ? (
            <div className="analysis-topic-list">
              {topTopics.map((topic) => {
                const width = `${Math.max(10, Math.round(((Number(topic.event_count) || 0) / maxTopicCount) * 100))}%`;
                const expanded = expandedTopicIds.has(topic.topic_id);
                const topicEvents = topicEventsByTopicId[topic.topic_id] ?? [];
                return (
                  <div key={topic.topic_id} className={`analysis-topic-row ${expanded ? "analysis-topic-row-open" : ""}`}>
                    <button
                      type="button"
                      className="analysis-topic-trigger"
                      onClick={() => toggleTopic(topic.topic_id)}
                      aria-expanded={expanded}
                    >
                      <span className="analysis-topic-meta">
                        <strong>{topic.label}</strong>
                        <span>{topic.event_count} 个事件</span>
                      </span>
                      <span className="analysis-topic-chevron" aria-hidden="true">{expanded ? "▲" : "▼"}</span>
                    </button>
                    <div className="analysis-topic-bar" aria-hidden="true">
                      <div className="analysis-topic-bar-fill" style={{ width }} />
                    </div>
                    <div className="entity-tag-row entity-tag-row-compact">
                      {topic.keywords.slice(0, 4).map((keyword) => (
                        <span key={keyword} className="entity-tag entity-tag-muted">{keyword}</span>
                      ))}
                    </div>
                    {expanded ? (
                      <div className="analysis-topic-events" aria-label={`${topic.label} 关联事件`}>
                        {loadingTopicIds.has(topic.topic_id) ? (
                          <p className="empty-state">正在加载关联事件...</p>
                        ) : topicEvents.length ? (
                          topicEvents.map((event) => (
                            <div key={event.event_id} className="analysis-topic-event-item">
                              <strong>{event.title}</strong>
                              <span>{Math.round(event.composite_score)} 分</span>
                            </div>
                          ))
                        ) : (
                          <p className="empty-state">暂无关联事件。</p>
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : emptyState()}
        </section>

        <section className="panel analysis-entity-panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">实体</p>
              <h2>实体热度</h2>
            </div>
            <span className="subtle">Top {topSignals.length}</span>
          </div>
          {topSignals.length ? (
            <div className="analysis-entity-table">
              {topSignals.map((signal, index) => {
                const trend = getTrendForEntity(trendLookup, signal.entity_id, signal.entity_name) ?? {
                  entity_id: signal.entity_id,
                  entity_name: signal.entity_name,
                  trend: signal.trend,
                  trend_label: signal.trend_label,
                  sma_7d: signal.sma_7d,
                  sma_14d: signal.sma_14d,
                  signals: [],
                };
                return (
                  <button
                    key={signal.entity_id}
                    type="button"
                    className="analysis-entity-row"
                    aria-label={`查看 ${signal.entity_name} 的热点簇`}
                    onClick={() => onNavigate("events", { entityId: signal.entity_id })}
                  >
                    <div className="analysis-entity-rank">{index + 1}</div>
                    <div className="analysis-entity-main">
                      <div className="analysis-entity-head">
                        <strong>{signal.entity_name}</strong>
                        <EntityTrendIndicator entityName={signal.entity_name} trend={trend} />
                      </div>
                      <div className="intel-score-row">
                        <span>7日均值 {signal.sma_7d.toFixed(1)}</span>
                        <span>14日均值 {signal.sma_14d.toFixed(1)}</span>
                        <span>{signal.recent_event_count} 个事件</span>
                      </div>
                      <p>{signal.latest_event_title || "暂无关联事件摘要。"}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : emptyState()}
        </section>
      </div>

      <div className="analysis-grid-row">
        <section className="panel analysis-relation-panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">关联</p>
              <h2>事件关联</h2>
            </div>
            <span className="subtle">Top {topRelations.length}</span>
          </div>
          <>
            {topRelations.length ? (
              <>
              <div className="analysis-relation-graph" aria-hidden="true">
                <BarChart3 size={16} />
                <span>关联强度越高，越值得交叉研判。</span>
              </div>
              <div className="analysis-relation-pairs">
                {topRelations.map((relation) => (
                  <div key={`${relation.event_id}-${relation.relation_type}`} className="analysis-relation-item">
                    <div className="analysis-relation-topline">
                      <strong>{relation.title}</strong>
                      <span className="status-badge status-neutral status-badge-compact">
                        {relationTypeLabel(relation.relation_type)}
                      </span>
                    </div>
                    <div className="analysis-relation-meter">
                      <div
                        className="analysis-relation-meter-fill"
                        style={{ width: `${Math.max(8, Math.round((relation.weight || 0) * 100))}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              </>
            ) : (
              <p className="empty-state">暂无事件关联。</p>
            )}
            <div className="analysis-temporal-section">
              <div className="analysis-temporal-header">
                <strong>时序规则</strong>
                <span>Top {topTemporalRules.length}</span>
              </div>
              {topTemporalRules.length ? (
                <div className="analysis-temporal-list">
                  {topTemporalRules.map((rule) => (
                    <div key={rule.id} className="analysis-temporal-card">
                      <div className="analysis-temporal-flow">
                        <span>{rule.antecedent_title || rule.antecedent_event_id}</span>
                        <strong>→</strong>
                        <span>{rule.consequent_title || rule.consequent_event_id}</span>
                      </div>
                      <div className="intel-score-row">
                        <span>延迟 {rule.lag_days} 天</span>
                        <span>置信度 {Math.round((rule.confidence || 0) * 100)}%</span>
                        <span>Lift {Number(rule.lift || 0).toFixed(1)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="empty-state">暂无时序规则。</p>
              )}
            </div>
          </>
        </section>

        <section className="panel analysis-report-panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">研判</p>
              <h2>研判报告</h2>
            </div>
            <button
              type="button"
              className="ghost-button compact"
              onClick={() => void handleGenerateReport()}
              disabled={generatingReport}
            >
              <FileText size={14} />
              {generatingReport ? "生成中..." : "生成报告"}
            </button>
          </div>
          {topSignals.length ? (
            <div className="analysis-report-summary">
              {currentReport ? (
                <div className="analysis-report-markdown">
                  {renderMarkdown(currentReport.markdown)}
                  {currentReport.status === "no_llm" ? (
                    <span className="status-badge status-neutral status-badge-compact">规则生成</span>
                  ) : null}
                </div>
              ) : (
                <blockquote>
                  当前最活跃实体为 {topSignals[0].entity_name}，最近事件为《{topSignals[0].latest_event_title || "暂无标题"}》。
                </blockquote>
              )}
              <div className="analysis-feedback-row">
                <button
                  type="button"
                  className="ghost-button compact"
                  onClick={() => void submitFeedback("confirm")}
                  disabled={submittingFeedback}
                >
                  <Check size={14} />
                  准确
                </button>
                <button type="button" className="ghost-button compact" onClick={() => setFeedbackMode("correct")}>
                  <Edit3 size={14} />
                  部分有误
                </button>
                <button type="button" className="ghost-button compact" onClick={() => setFeedbackMode("dismiss")}>
                  <X size={14} />
                  偏离事实
                </button>
                {feedbackStats ? (
                  <>
                    <span className="analysis-feedback-metric">{feedbackStats.total} 条反馈</span>
                    <span className="analysis-feedback-metric">准确率 {formatAccuratePct(feedbackStats.accurate_pct)}%</span>
                  </>
                ) : null}
                {submittedFeedback ? <span className="analysis-feedback-status">反馈已提交</span> : null}
              </div>
              {feedbackMode && feedbackMode !== "confirm" ? (
                <div className="analysis-feedback-editor">
                  <input
                    value={feedbackNote}
                    onChange={(event) => setFeedbackNote(event.target.value)}
                    placeholder="补充修正说明"
                  />
                  <button
                    type="button"
                    className="ghost-button compact"
                    onClick={() => void submitFeedback(feedbackMode, feedbackNote)}
                    disabled={submittingFeedback}
                  >
                    提交反馈
                  </button>
                  <span>{feedbackLabel(feedbackMode)}</span>
                </div>
              ) : null}
            </div>
          ) : emptyState()}
        </section>
      </div>

      <section className="panel analysis-history-panel">
        <div className="panel-header compact">
          <div>
            <p className="eyebrow">历史</p>
            <h2>历史报告</h2>
          </div>
          <span className="subtle">{topReports.length} 份</span>
        </div>
        {topReports.length ? (
          <div className="analysis-report-history-list">
            {topReports.map((report) => {
              const expanded = expandedReportIds.has(report.report_id);
              const detail = reportDetailsById[report.report_id];
              return (
                <div key={report.report_id} className={`analysis-report-history-item ${expanded ? "analysis-report-history-open" : ""}`}>
                  <button type="button" onClick={() => toggleReport(report.report_id)} aria-expanded={expanded}>
                    <span>
                      <strong>{formatReportScope(report.scope)}</strong>
                      <span>{report.period_start} 至 {report.period_end}</span>
                    </span>
                    <span className="analysis-report-history-preview">{report.preview || "暂无摘要"}</span>
                    <span className="analysis-topic-chevron" aria-hidden="true">{expanded ? "▲" : "▼"}</span>
                  </button>
                  {expanded ? (
                    <div className="analysis-report-detail" aria-label={`${report.report_id} 报告详情`}>
                      {detail ? renderMarkdown(detail.markdown) : <p className="empty-state">正在加载报告...</p>}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="empty-state">暂无历史报告。</p>
        )}
      </section>
    </div>
  );
}
