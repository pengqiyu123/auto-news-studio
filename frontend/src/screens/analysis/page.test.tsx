import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AnalysisFeedbackStats,
  AnalysisReportItem,
  AnalysisReportSummary,
  AnalysisBatchRunInfo,
  AnalysisSignalInfo,
  AnalysisTopicEventInfo,
  EventRelationInfo,
  TemporalRuleInfo,
  TopicInfo,
  TopicPeriodicityInfo,
  TrendSignalInfo,
} from "../../types";
import { AnalysisPage } from "./page";

const topics: TopicInfo[] = [
  { topic_id: "topic-1", label: "OpenAI / 医疗 / 模型", keywords: ["OpenAI", "医疗", "模型"], event_count: 12 },
  { topic_id: "topic-2", label: "芯片 / 制裁 / 供应链", keywords: ["芯片", "制裁", "供应链"], event_count: 8 },
];

const trends: TrendSignalInfo[] = [
  { entity_id: "openai", entity_name: "OpenAI", trend: "hot", trend_label: "近7天持续上升", sma_7d: 12, sma_14d: 8, signals: [] },
  { entity_id: "huawei", entity_name: "华为", trend: "emerging", trend_label: "近3天明显升温", sma_7d: 9, sma_14d: 4, signals: [] },
];

const signals: AnalysisSignalInfo[] = [
  {
    entity_id: "openai",
    entity_name: "OpenAI",
    trend: "hot",
    trend_label: "近7天持续上升",
    sma_7d: 12,
    sma_14d: 8,
    recent_event_count: 8,
    latest_event_title: "OpenAI 医疗模型进入医院测试",
  },
  {
    entity_id: "huawei",
    entity_name: "华为",
    trend: "emerging",
    trend_label: "近3天明显升温",
    sma_7d: 9,
    sma_14d: 4,
    recent_event_count: 6,
    latest_event_title: "华为 AI 芯片产能提升",
  },
];

const relatedEvents: EventRelationInfo[] = [
  { event_id: "evt-1", title: "OpenAI 医疗 AI 智能体发布", relation_type: "entity_shared", weight: 0.82, evidence: {} },
  { event_id: "evt-2", title: "OpenAI 医疗模型进入医院测试", relation_type: "topic_shared", weight: 0.74, evidence: {} },
  { event_id: "evt-3", title: "医院引入端侧推理方案", relation_type: "temporal_proximity", weight: 0.62, evidence: {} },
];

const topicsPeriodicity: TopicPeriodicityInfo[] = [
  { topic_id: "topic-1", label: "OpenAI / 医疗 / 模型", period_days: 7, confidence: 0.76 },
];

const temporalRules: TemporalRuleInfo[] = [
  {
    id: "rule-1",
    antecedent_event_id: "evt-1",
    antecedent_title: "OpenAI 医疗 AI 智能体发布",
    consequent_event_id: "evt-2",
    consequent_title: "OpenAI 医疗模型进入医院测试",
    lag_days: 2,
    support: 0.24,
    confidence: 0.82,
    lift: 1.4,
  },
];

const topicEvents: AnalysisTopicEventInfo[] = [
  { event_id: "evt-topic-1", title: "OpenAI 医疗 AI 智能体发布", composite_score: 78, first_seen_at: "2026-05-29T10:00:00+00:00" },
];

const report: AnalysisReportItem = {
  report_id: "report-1",
  scope: "daily",
  period_start: "2026-05-20",
  period_end: "2026-05-29",
  status: "no_llm",
  markdown: "# 研判报告\n\n## 主结论\nOpenAI 医疗主题升温。",
  sections: {
    executive_summary: "OpenAI 医疗主题升温。",
    key_findings: "医疗模型事件集中。",
    risk_assessment: "样本仍偏少。",
    recommendation: "继续跟踪。",
  },
};

const reportSummaries: AnalysisReportSummary[] = [
  { report_id: "report-1", scope: "daily", period_start: "2026-05-20", period_end: "2026-05-29", status: "no_llm", preview: "OpenAI 医疗主题升温。" },
];

const feedbackStats: AnalysisFeedbackStats = {
  total: 4,
  accurate_pct: 0.5,
  by_type: { confirm: 2, correct: 1, dismiss: 1 },
};

const batchStatus: AnalysisBatchRunInfo[] = [
  {
    id: "run-1",
    task_name: "topic_modeling",
    status: "success",
    started_at: "2026-05-30T02:00:00+08:00",
    finished_at: "2026-05-30T02:01:00+08:00",
    items_processed: 12,
    error_message: "",
  },
  {
    id: "run-2",
    task_name: "event_relations",
    status: "failed",
    started_at: "2026-05-30T03:00:00+08:00",
    finished_at: "2026-05-30T03:01:00+08:00",
    items_processed: 0,
    error_message: "relation failed",
  },
];

const percentageFeedbackStats: AnalysisFeedbackStats = {
  total: 6,
  accurate_pct: 50,
  by_type: { confirm: 3, correct: 2, dismiss: 1 },
};

describe("AnalysisPage", () => {
  it("renders the hero and four core panels", () => {
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        topicsPeriodicity={topicsPeriodicity}
        temporalRules={temporalRules}
        batchStatus={batchStatus}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    expect(screen.getByRole("heading", { name: "分析中心" })).toBeInTheDocument();
    expect(screen.getByText("主题趋势")).toBeInTheDocument();
    expect(screen.getByText("实体热度")).toBeInTheDocument();
    expect(screen.getByText("事件关联")).toBeInTheDocument();
    expect(screen.getByText("周期检测")).toBeInTheDocument();
    expect(screen.getByText("时序规则")).toBeInTheDocument();
    expect(screen.getByText("研判报告")).toBeInTheDocument();
    expect(screen.getByText("批处理状态")).toBeInTheDocument();
  });

  it("renders and expands batch status details", () => {
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        batchStatus={batchStatus}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    expect(screen.getByText(/上次成功/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /批处理状态/ }));

    expect(screen.getByText("topic_modeling")).toBeInTheDocument();
    expect(screen.getByText("event_relations")).toBeInTheDocument();
    expect(screen.getByText("relation failed")).toBeInTheDocument();
  });

  it("shows a realtime-compute hint when batch status is empty", () => {
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        batchStatus={[]}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    expect(screen.getByText("定时分析未启动，当前数据为实时计算")).toBeInTheDocument();
  });

  it("shows topic bars, entity trends, and relation list content", () => {
    const { container } = render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        topicsPeriodicity={topicsPeriodicity}
        temporalRules={temporalRules}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    expect(screen.getAllByText("OpenAI / 医疗 / 模型").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".analysis-topic-bar-fill").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("OpenAI 趋势 升温")).toBeInTheDocument();
    expect(screen.getAllByText("OpenAI 医疗 AI 智能体发布").length).toBeGreaterThan(0);
    expect(screen.getByText("实体重合")).toBeInTheDocument();
    expect(screen.getByText("7 天周期")).toBeInTheDocument();
    expect(screen.getByText(/延迟 2 天/)).toBeInTheDocument();
  });

  it("shows empty states when no analysis data exists", () => {
    render(
      <AnalysisPage
        topics={[]}
        trends={[]}
        signals={[]}
        relatedEvents={[]}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    expect(screen.getAllByText("暂无分析数据。").length).toBeGreaterThan(0);
  });

  it("expands a topic row and shows its events", async () => {
    const onLoadTopicEvents = vi.fn().mockResolvedValue(undefined);
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        topicEventsByTopicId={{ "topic-1": topicEvents }}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={onLoadTopicEvents}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /OpenAI \/ 医疗 \/ 模型/ }));

    expect(onLoadTopicEvents).toHaveBeenCalledWith("topic-1");
    const topicRegion = await screen.findByLabelText("OpenAI / 医疗 / 模型 关联事件");
    expect(within(topicRegion).getByText("OpenAI 医疗 AI 智能体发布")).toBeInTheDocument();
  });

  it("navigates to events when an entity row is clicked", () => {
    const onNavigate = vi.fn();
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={onNavigate}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "查看 OpenAI 的热点簇" }));

    expect(onNavigate).toHaveBeenCalledWith("events", { entityId: "openai" });
  });

  it("submits report feedback with a correction note", async () => {
    const onSubmitFeedback = vi.fn().mockResolvedValue(undefined);
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={onSubmitFeedback}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "部分有误" }));
    fireEvent.change(screen.getByPlaceholderText("补充修正说明"), { target: { value: "需要降低 OpenAI 权重" } });
    fireEvent.click(screen.getByRole("button", { name: "提交反馈" }));

    await waitFor(() => {
      expect(onSubmitFeedback).toHaveBeenCalledWith({
        target_type: "analysis_summary",
        target_id: "openai",
        feedback_type: "correct",
        correction: { note: "需要降低 OpenAI 权重" },
      });
    });
    expect(screen.getByText("反馈已提交")).toBeInTheDocument();
  });

  it("generates and renders an analysis report", async () => {
    const onGenerateReport = vi.fn().mockResolvedValue(report);
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        currentReport={report}
        feedbackStats={feedbackStats}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={onGenerateReport}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));

    await waitFor(() => {
      expect(onGenerateReport).toHaveBeenCalled();
    });
    expect(screen.getByText("OpenAI 医疗主题升温。")).toBeInTheDocument();
    expect(screen.getByText("4 条反馈")).toBeInTheDocument();
    expect(screen.getByText("准确率 50%")).toBeInTheDocument();
  });

  it("renders markdown formatting without exposing raw syntax", () => {
    const richReport: AnalysisReportItem = {
      ...report,
      markdown: [
        "# 研判报告",
        "## 主结论",
        "OpenAI **医疗** *模型* [官网](https://openai.com) `升温`。",
        "- 关注下一轮更新",
        "```",
        "risk_score = 7",
        "```",
      ].join("\n"),
    };

    const { container } = render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        currentReport={richReport}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    const markdownRoot = container.querySelector(".analysis-report-markdown");
    expect(markdownRoot).not.toBeNull();
    const markdown = within(markdownRoot as HTMLElement);
    expect(markdown.getByRole("heading", { name: "研判报告" })).toBeInTheDocument();
    expect(markdown.getByText("医疗").tagName.toLowerCase()).toBe("strong");
    expect(markdown.getByText("模型").tagName.toLowerCase()).toBe("em");
    expect(markdown.getByRole("link", { name: "官网" })).toHaveAttribute("href", "https://openai.com");
    expect(markdown.getByText("升温").tagName.toLowerCase()).toBe("code");
    expect(container.querySelector(".analysis-report-code-block")).toHaveTextContent("risk_score = 7");
    expect(markdown.queryByText(/\*\*医疗\*\*/)).not.toBeInTheDocument();
  });

  it("normalizes feedback accuracy whether backend returns a ratio or percent value", () => {
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        currentReport={report}
        feedbackStats={percentageFeedbackStats}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
      />,
    );

    expect(screen.getByText("准确率 50%")).toBeInTheDocument();
    expect(screen.queryByText("准确率 5000%")).not.toBeInTheDocument();
  });

  it("uses a monthly report window for the all-time range", async () => {
    const onGenerateReport = vi.fn().mockResolvedValue(report);
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        loading={false}
        timeRange="all"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={onGenerateReport}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));

    await waitFor(() => {
      expect(onGenerateReport).toHaveBeenCalledWith(expect.objectContaining({ scope: "monthly" }));
    });
  });

  it("expands a report history item and shows full markdown", async () => {
    const onLoadReportDetail = vi.fn().mockResolvedValue(report);
    render(
      <AnalysisPage
        topics={topics}
        trends={trends}
        signals={signals}
        relatedEvents={relatedEvents}
        reports={reportSummaries}
        reportDetailsById={{ "report-1": report }}
        loading={false}
        timeRange="7d"
        onTimeRangeChange={vi.fn()}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onLoadTopicEvents={vi.fn().mockResolvedValue(undefined)}
        onNavigate={vi.fn()}
        onSubmitFeedback={vi.fn().mockResolvedValue(undefined)}
        onGenerateReport={vi.fn().mockResolvedValue(report)}
        onLoadReportDetail={onLoadReportDetail}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /OpenAI 医疗主题升温。/ }));

    expect(onLoadReportDetail).toHaveBeenCalledWith("report-1");
    const historyRegion = await screen.findByLabelText("report-1 报告详情");
    expect(within(historyRegion).getByText("主结论")).toBeInTheDocument();
  });
});
