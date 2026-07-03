import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import { useAnalysisState } from "./state";

vi.mock("../../lib/api", () => ({
  api: {
    fetchTopics: vi.fn(),
    fetchTrends: vi.fn(),
    fetchAnalysisSignals: vi.fn(),
    fetchRelatedEvents: vi.fn(),
    fetchTopicEvents: vi.fn(),
    fetchTopicsPeriodicity: vi.fn(),
    fetchTemporalRules: vi.fn(),
    fetchAnalysisBatchStatus: vi.fn(),
    submitAnalysisFeedback: vi.fn(),
    generateAnalysisReport: vi.fn(),
    fetchAnalysisReports: vi.fn(),
    fetchAnalysisReport: vi.fn(),
    fetchAnalysisFeedbackStats: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

describe("useAnalysisState", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("loads topics, trends, and signals together", async () => {
    mockedApi.fetchTopics.mockResolvedValue({ items: [{ topic_id: "topic-1", label: "OpenAI", keywords: ["OpenAI"], event_count: 2 }] });
    mockedApi.fetchTrends.mockResolvedValue({ items: [{ entity_id: "openai", entity_name: "OpenAI", trend: "hot", trend_label: "近7天持续上升", sma_7d: 10, sma_14d: 6, signals: [] }] });
    mockedApi.fetchAnalysisSignals.mockResolvedValue({ items: [{ entity_id: "openai", entity_name: "OpenAI", trend: "hot", trend_label: "近7天持续上升", sma_7d: 10, sma_14d: 6, recent_event_count: 3, latest_event_title: "OpenAI launch" }] });
    mockedApi.fetchRelatedEvents.mockResolvedValue({ items: [] });
    mockedApi.fetchTopicsPeriodicity.mockResolvedValue({ items: [{ topic_id: "topic-1", label: "OpenAI", period_days: 7, confidence: 0.72 }] });
    mockedApi.fetchTemporalRules.mockResolvedValue({ items: [{ id: "rule-1", antecedent_event_id: "evt-a", antecedent_title: "OpenAI 发布", consequent_event_id: "evt-b", consequent_title: "医疗落地", lag_days: 2, support: 0.25, confidence: 0.8, lift: 1.4 }] });
    mockedApi.fetchAnalysisBatchStatus.mockResolvedValue({ items: [{ id: "run-1", task_name: "topic_modeling", status: "success", started_at: "2026-05-30T02:00:00+08:00", finished_at: "2026-05-30T02:01:00+08:00", items_processed: 4, error_message: "" }] });
    mockedApi.fetchAnalysisReports.mockResolvedValue({ items: [{ report_id: "report-1", scope: "daily", period_start: "2026-05-20", period_end: "2026-05-29", status: "no_llm", preview: "OpenAI" }] });
    mockedApi.fetchAnalysisFeedbackStats.mockResolvedValue({ total: 2, accurate_pct: 0.5, by_type: { confirm: 1, correct: 1, dismiss: 0 } });

    const { result } = renderHook(() =>
      useAnalysisState({
        onError: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.loadAnalysisData();
    });

    expect(result.current.topics).toHaveLength(1);
    expect(result.current.trends).toHaveLength(1);
    expect(result.current.signals).toHaveLength(1);
    expect(result.current.topicsPeriodicity).toHaveLength(1);
    expect(result.current.temporalRules).toHaveLength(1);
    expect(result.current.batchStatus).toHaveLength(1);
    expect(result.current.reports).toHaveLength(1);
    expect(result.current.feedbackStats?.total).toBe(2);
  });

  it("loads topic events and submits feedback", async () => {
    mockedApi.fetchTopicEvents.mockResolvedValue({
      items: [{ event_id: "evt-1", title: "OpenAI 医疗 AI 智能体发布", composite_score: 78, first_seen_at: "2026-05-29T10:00:00+00:00" }],
    });
    mockedApi.submitAnalysisFeedback.mockResolvedValue({ ok: true, feedback_id: "feedback-1" });

    const { result } = renderHook(() =>
      useAnalysisState({
        onError: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.loadTopicEvents("topic-1");
      await result.current.submitFeedback({
        target_type: "analysis_summary",
        target_id: "openai",
        feedback_type: "confirm",
      });
    });

    expect(result.current.topicEventsByTopicId["topic-1"]).toHaveLength(1);
    expect(mockedApi.submitAnalysisFeedback).toHaveBeenCalledWith({
      target_type: "analysis_summary",
      target_id: "openai",
      feedback_type: "confirm",
    });
  });

  it("generates reports and loads report detail", async () => {
    mockedApi.generateAnalysisReport.mockResolvedValue({
      item: {
        report_id: "report-1",
        scope: "daily",
        period_start: "2026-05-20",
        period_end: "2026-05-29",
        status: "no_llm",
        markdown: "# 研判报告\n\nOpenAI 升温",
        sections: {
          executive_summary: "OpenAI 升温",
          key_findings: "医疗主题集中",
          risk_assessment: "样本偏少",
          recommendation: "继续跟踪",
        },
      },
    });
    mockedApi.fetchAnalysisReport.mockResolvedValue({
      item: {
        report_id: "report-1",
        scope: "daily",
        period_start: "2026-05-20",
        period_end: "2026-05-29",
        status: "no_llm",
        markdown: "# 研判报告\n\n完整内容",
        sections: {
          executive_summary: "完整内容",
          key_findings: "",
          risk_assessment: "",
          recommendation: "",
        },
      },
    });
    mockedApi.fetchAnalysisReports.mockResolvedValue({ items: [] });

    const { result } = renderHook(() =>
      useAnalysisState({
        onError: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.generateReport({ scope: "daily", date_from: "2026-05-20", date_to: "2026-05-29" });
      await result.current.loadReportDetail("report-1");
    });

    expect(result.current.currentReport?.report_id).toBe("report-1");
    expect(result.current.reportDetailsById["report-1"].markdown).toContain("完整内容");
  });
});
