import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type {
  AnalysisFeedbackPayload,
  AnalysisFeedbackStats,
  AnalysisBatchRunInfo,
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

interface UseAnalysisStateParams {
  onError: (message: string) => void;
  onToast?: (message: string, tone?: "success" | "info" | "warning") => void;
}

export function useAnalysisState({ onError }: UseAnalysisStateParams) {
  const [topics, setTopics] = useState<TopicInfo[]>([]);
  const [trends, setTrends] = useState<TrendSignalInfo[]>([]);
  const [signals, setSignals] = useState<AnalysisSignalInfo[]>([]);
  const [relatedEvents, setRelatedEvents] = useState<EventRelationInfo[]>([]);
  const [topicsPeriodicity, setTopicsPeriodicity] = useState<TopicPeriodicityInfo[]>([]);
  const [temporalRules, setTemporalRules] = useState<TemporalRuleInfo[]>([]);
  const [batchStatus, setBatchStatus] = useState<AnalysisBatchRunInfo[]>([]);
  const [topicEventsByTopicId, setTopicEventsByTopicId] = useState<Record<string, AnalysisTopicEventInfo[]>>({});
  const [loadingTopicIds, setLoadingTopicIds] = useState<Set<string>>(() => new Set());
  const [reports, setReports] = useState<AnalysisReportSummary[]>([]);
  const [currentReport, setCurrentReport] = useState<AnalysisReportItem | null>(null);
  const [reportDetailsById, setReportDetailsById] = useState<Record<string, AnalysisReportItem>>({});
  const [feedbackStats, setFeedbackStats] = useState<AnalysisFeedbackStats | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [timeRange, setTimeRange] = useState<"7d" | "30d" | "all">("7d");
  const [loading, setLoading] = useState(false);

  const loadAnalysisData = useCallback(async () => {
    setLoading(true);
    try {
      const [topicsData, trendsData, signalsData, periodicityData, temporalRulesData, batchStatusData, reportsData, statsData] = await Promise.all([
        api.fetchTopics(),
        api.fetchTrends(),
        api.fetchAnalysisSignals(),
        api.fetchTopicsPeriodicity(),
        api.fetchTemporalRules(),
        api.fetchAnalysisBatchStatus(),
        api.fetchAnalysisReports(),
        api.fetchAnalysisFeedbackStats(),
      ]);
      const nextTopics = topicsData.items ?? [];
      const nextTrends = trendsData.items ?? [];
      const nextSignals = signalsData.items ?? [];
      setTopics(nextTopics);
      setTrends(nextTrends);
      setSignals(nextSignals);
      setTopicsPeriodicity(periodicityData.items ?? []);
      setTemporalRules(temporalRulesData.items ?? []);
      setBatchStatus(batchStatusData.items ?? []);
      setReports(reportsData?.items ?? []);
      setFeedbackStats(statsData);

      const seedEventId = nextSignals.find((item) => item.latest_event_id)?.latest_event_id;
      if (seedEventId) {
        const related = await api.fetchRelatedEvents(seedEventId);
        setRelatedEvents(related.items ?? []);
      } else {
        setRelatedEvents([]);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "分析数据加载失败");
    } finally {
      setLoading(false);
    }
  }, [onError]);

  const loadTopicEvents = useCallback(async (topicId: string) => {
    const normalizedTopicId = String(topicId || "").trim();
    if (!normalizedTopicId) return;
    setLoadingTopicIds((current) => new Set(current).add(normalizedTopicId));
    try {
      const response = await api.fetchTopicEvents(normalizedTopicId);
      setTopicEventsByTopicId((current) => ({
        ...current,
        [normalizedTopicId]: response.items ?? [],
      }));
    } catch (err) {
      onError(err instanceof Error ? err.message : "主题事件加载失败");
    } finally {
      setLoadingTopicIds((current) => {
        const next = new Set(current);
        next.delete(normalizedTopicId);
        return next;
      });
    }
  }, [onError]);

  const submitFeedback = useCallback(async (payload: AnalysisFeedbackPayload) => {
    try {
      const response = await api.submitAnalysisFeedback(payload);
      const stats = await api.fetchAnalysisFeedbackStats();
      setFeedbackStats(stats);
      return response;
    } catch (err) {
      onError(err instanceof Error ? err.message : "反馈提交失败");
      throw err;
    }
  }, [onError]);

  const generateReport = useCallback(async (payload: AnalysisReportRequest) => {
    setGeneratingReport(true);
    try {
      const response = await api.generateAnalysisReport(payload);
      setCurrentReport(response.item);
      setReportDetailsById((current) => ({
        ...current,
        [response.item.report_id]: response.item,
      }));
      const reportsData = await api.fetchAnalysisReports();
      setReports(reportsData.items ?? []);
      return response.item;
    } catch (err) {
      onError(err instanceof Error ? err.message : "研判报告生成失败");
      throw err;
    } finally {
      setGeneratingReport(false);
    }
  }, [onError]);

  const loadReportDetail = useCallback(async (reportId: string) => {
    const normalizedReportId = String(reportId || "").trim();
    if (!normalizedReportId) return null;
    try {
      const response = await api.fetchAnalysisReport(normalizedReportId);
      setCurrentReport(response.item);
      setReportDetailsById((current) => ({
        ...current,
        [normalizedReportId]: response.item,
      }));
      return response.item;
    } catch (err) {
      onError(err instanceof Error ? err.message : "报告详情加载失败");
      throw err;
    }
  }, [onError]);

  return {
    topics,
    trends,
    signals,
    relatedEvents,
    topicsPeriodicity,
    temporalRules,
    batchStatus,
    topicEventsByTopicId,
    loadingTopicIds,
    reports,
    currentReport,
    reportDetailsById,
    feedbackStats,
    generatingReport,
    timeRange,
    setTimeRange,
    loading,
    loadAnalysisData,
    loadTopicEvents,
    submitFeedback,
    generateReport,
    loadReportDetail,
  };
}
