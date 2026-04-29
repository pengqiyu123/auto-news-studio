import {
  AlertCircle,
  CheckCircle,
  LayoutDashboard,
  RadioTower,
  SearchCheck,
  Settings,
  Siren,
  StickyNote,
  WavesLadder,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { DraftEditorModal } from "./components/DraftEditorModal";
import { DraftTable } from "./components/DraftTable";
import { IntelAlertsPage } from "./components/IntelAlertsPage";
import { IntelEventsPage } from "./components/IntelEventsPage";
import { IntelOverviewPage } from "./components/IntelOverviewPage";
import { IntelStreamPage } from "./components/IntelStreamPage";
import { JobsPanel } from "./components/JobsPanel";
import { LogsPanel } from "./components/LogsPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { SourceHealthPage } from "./components/SourceHealthPage";
import { WatchlistPanel } from "./components/WatchlistPanel";
import { api } from "./lib/api";
import { deriveRuntimeDisplayStatus, isRuntimeActivelyProcessing, pickNewerRuntimeStatus, RUNTIME_INTENT_LABELS } from "./lib/runtimeIntent";
import type {
  BrowserSessionState,
  CandidateTopic,
  DashboardResponse,
  DiscoveryItem,
  DraftItem,
  EntityWatchlistItem,
  IntelAlert,
  IntelAlertHistoryItem,
  IntelEvent,
  IntelEventHistoryItem,
  IntelOverviewSummary,
  JobItem,
  LLMConfig,
  LogItem,
  PublishMode,
  PublishTask,
  ReferenceProject,
  RuntimeIntent,
  RuntimePlan,
  SourceConnector,
  WeChatChannelConfig,
} from "./types";

type TabKey =
  | "overview"
  | "stream"
  | "events"
  | "alerts"
  | "source-health"
  | "watchlist"
  | "drafts"
  | "jobs"
  | "settings"
  | "logs";

const intelTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "overview", label: "总览", icon: LayoutDashboard },
  { key: "stream", label: "实时流", icon: RadioTower },
  { key: "events", label: "热点簇", icon: SearchCheck },
  { key: "alerts", label: "预警台", icon: Siren },
  { key: "source-health", label: "来源健康", icon: AlertCircle },
];

const draftTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "watchlist", label: "选题池", icon: WavesLadder },
  { key: "drafts", label: "稿件", icon: StickyNote },
];

const systemTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "jobs", label: "任务", icon: RadioTower },
  { key: "settings", label: "设置", icon: Settings },
  { key: "logs", label: "日志", icon: AlertCircle },
];

const pageMeta: Record<TabKey, { eyebrow: string; title: string }> = {
  overview: { eyebrow: "总览", title: "情报总览" },
  stream: { eyebrow: "信息获取", title: "原始素材流" },
  events: { eyebrow: "事件聚合", title: "热点事件列表" },
  alerts: { eyebrow: "趋势判断", title: "热点预警列表" },
  "source-health": { eyebrow: "来源巡检", title: "来源运行状态" },
  watchlist: { eyebrow: "选题池", title: "待进入稿件生产的观察事件" },
  drafts: { eyebrow: "内容产出", title: "稿件工作台" },
  jobs: { eyebrow: "补跑与排障", title: "手动任务中心" },
  settings: { eyebrow: "系统配置", title: "渠道与模型设置" },
  logs: { eyebrow: "运行记录", title: "系统日志与异常" },
};

export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [summary, setSummary] = useState<IntelOverviewSummary | null>(null);
  const [streamItems, setStreamItems] = useState<DiscoveryItem[]>([]);
  const [events, setEvents] = useState<IntelEvent[]>([]);
  const [eventHistory, setEventHistory] = useState<IntelEventHistoryItem[]>([]);
  const [alerts, setAlerts] = useState<IntelAlert[]>([]);
  const [alertHistory, setAlertHistory] = useState<IntelAlertHistoryItem[]>([]);
  const [sources, setSources] = useState<SourceConnector[]>([]);
  const [candidates, setCandidates] = useState<CandidateTopic[]>([]);
  const [drafts, setDrafts] = useState<DraftItem[]>([]);
  const [entityWatchlist, setEntityWatchlist] = useState<EntityWatchlistItem[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState<string>("all");
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [publishTasks, setPublishTasks] = useState<PublishTask[]>([]);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [wechatConfig, setWechatConfig] = useState<WeChatChannelConfig | null>(null);
  const [browserSession, setBrowserSession] = useState<BrowserSessionState | null>(null);
  const [referenceProjects, setReferenceProjects] = useState<ReferenceProject[]>([]);
  const [llmConfig, setLlmConfig] = useState<LLMConfig | null>(null);
  const [appSettings, setAppSettings] = useState<Record<string, unknown>>({});
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyDraftId, setBusyDraftId] = useState<string | null>(null);
  const [busyJobAction, setBusyJobAction] = useState<string | null>(null);
  const [savingChannel, setSavingChannel] = useState(false);
  const [savingLLMConfig, setSavingLLMConfig] = useState(false);
  const [refreshingSources, setRefreshingSources] = useState(false);
  const [savingSourceKey, setSavingSourceKey] = useState<string | null>(null);
  const [syncingSourceKey, setSyncingSourceKey] = useState<string | null>(null);
  const [busyCandidateId, setBusyCandidateId] = useState<string | null>(null);
  const [busyEventId, setBusyEventId] = useState<string | null>(null);
  const [refreshingBrowser, setRefreshingBrowser] = useState(false);
  const [openingBrowser, setOpeningBrowser] = useState(false);
  const [busyRuntimeAction, setBusyRuntimeAction] = useState<"start" | "stop" | null>(null);
  const [busyMaintenanceIntent, setBusyMaintenanceIntent] = useState<RuntimeIntent | null>(null);
  const [savingRuntimePlan, setSavingRuntimePlan] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [highlightDraftId, setHighlightDraftId] = useState<string | null>(null);
  const [pendingDraftTitle, setPendingDraftTitle] = useState<string | null>(null);
  const [pendingDraftSourceTab, setPendingDraftSourceTab] = useState<TabKey | null>(null);

  const refreshIntelCore = useCallback(async () => {
    const [dashboardData, summaryData, streamData, eventData, alertData, sourceData, candidateData, logData, jobData, publishTaskData] = await Promise.all([
      api.getDashboard(),
      api.getIntelSummary(),
      api.getDiscoveryItems(),
      api.getIntelEvents(),
      api.getIntelAlerts(),
      api.getIntelSources(),
      api.getCandidates(),
      api.getLogs(),
      api.getJobs(),
      api.getPublishTasks(),
    ]);
    setDashboard((current) =>
      !current
        ? dashboardData
        : {
            ...dashboardData,
            runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
          },
    );
    setSummary(summaryData.item);
    setStreamItems(streamData.items);
    setEvents(eventData.items);
    setEventHistory(eventData.history_items ?? []);
    setAlerts(alertData.items);
    setAlertHistory(alertData.history_items ?? []);
    setSources(sourceData.items);
    setCandidates(candidateData.items);
    setLogs(logData.items);
    setJobs(jobData.items);
    setPublishTasks(publishTaskData.items);
    setBrowserSession(dashboardData.browser_session);
  }, []);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        dashboardData,
        summaryData,
        streamData,
        eventData,
        alertData,
        sourceData,
        candidateData,
        draftData,
        entityWatchlistData,
        publishTaskData,
        jobData,
        logData,
        channelData,
        browserData,
        referenceData,
        llmConfigData,
        settingsData,
      ] = await Promise.all([
        api.getDashboard(),
        api.getIntelSummary(),
        api.getDiscoveryItems(),
        api.getIntelEvents(),
        api.getIntelAlerts(),
        api.getIntelSources(),
        api.getCandidates(),
        api.getDrafts(),
        api.getEntityWatchlist(),
        api.getPublishTasks(),
        api.getJobs(),
        api.getLogs(),
        api.getWeChatConfig(),
        api.getBrowserSession(),
        api.getReferenceProjects(),
        api.getLLMConfig(),
        api.getSettings(),
      ]);
      setDashboard((current) =>
        !current
          ? dashboardData
          : {
              ...dashboardData,
              runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
            },
      );
      setSummary(summaryData.item);
      setStreamItems(streamData.items);
      setEvents(eventData.items);
      setEventHistory(eventData.history_items ?? []);
      setAlerts(alertData.items);
      setAlertHistory(alertData.history_items ?? []);
      setSources(sourceData.items);
      setCandidates(candidateData.items);
      setDrafts(draftData.items);
      setEntityWatchlist(entityWatchlistData.items);
      setPublishTasks(publishTaskData.items);
      setJobs(jobData.items);
      setLogs(logData.items);
      setWechatConfig(channelData.item);
      setBrowserSession(browserData.item);
      setReferenceProjects(referenceData.items);
      setLlmConfig(llmConfigData.item);
      setAppSettings(settingsData.item);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    const runtimeAwareTabs: TabKey[] = ["overview", "stream", "events", "alerts", "source-health", "watchlist", "jobs", "logs"];
    if (!runtimeAwareTabs.includes(activeTab)) {
      return;
    }
    const isRunning = dashboard?.runtime_status.running;
    const isActiveCycle = dashboard?.runtime_status ? isRuntimeActivelyProcessing(dashboard.runtime_status) : false;
    const intervalMs = isActiveCycle ? 2000 : isRunning ? 6000 : 60000;
    const timer = window.setInterval(() => {
      void refreshIntelCore().catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "自动刷新失败");
      });
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [activeTab, dashboard?.runtime_status, refreshIntelCore]);

  async function handleSourceSync() {
    setRefreshingSources(true);
    try {
      await api.syncSources();
      await refreshIntelCore();
    } catch (err) {
      setError(err instanceof Error ? err.message : "来源同步失败");
    } finally {
      setRefreshingSources(false);
    }
  }

  async function handleSourceSyncOne(sourceKey: string) {
    setSyncingSourceKey(sourceKey);
    try {
      await api.syncSource(sourceKey);
      await refreshIntelCore();
    } catch (err) {
      setError(err instanceof Error ? err.message : "单来源重抓失败");
    } finally {
      setSyncingSourceKey(null);
    }
  }

  async function handleSourceSave(
    sourceKey: string,
    payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">
  ) {
    setSavingSourceKey(sourceKey);
    try {
      await api.updateSource(sourceKey, payload);
      await refreshIntelCore();
    } catch (err) {
      setError(err instanceof Error ? err.message : "来源保存失败");
    } finally {
      setSavingSourceKey(null);
    }
  }

  async function handleSourceCreate(payload: Parameters<typeof api.createSource>[0]) {
    try {
      await api.createSource(payload);
      await refreshIntelCore();
      showToast("来源已添加");
    } catch (err) {
      setError(err instanceof Error ? err.message : "来源添加失败");
    }
  }

  async function handleSourceDelete(sourceKey: string) {
    try {
      await api.deleteSource(sourceKey);
      await refreshIntelCore();
      showToast("来源已删除");
    } catch (err) {
      setError(err instanceof Error ? err.message : "来源删除失败");
    }
  }

  async function handleWatchEvent(eventId: string) {
    try {
      await api.watchlistEvent(eventId);
      await refreshIntelCore();
    } catch (err) {
      setError(err instanceof Error ? err.message : "加入重点观察失败");
    }
  }

  async function handleIgnoreEvent(eventId: string) {
    try {
      await api.ignoreEvent(eventId);
      await refreshIntelCore();
    } catch (err) {
      setError(err instanceof Error ? err.message : "忽略事件失败");
    }
  }

  async function handleUpdateEntityWatchlist(items: EntityWatchlistItem[]) {
    try {
      const response = await api.updateEntityWatchlist(items);
      setEntityWatchlist(response.items);
      const dashboardData = await api.getDashboard();
      setDashboard((current) =>
        !current
          ? dashboardData
          : {
              ...dashboardData,
              runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
            },
      );
      if (selectedEntityId !== "all" && !response.items.some((item) => item.entity_id === selectedEntityId)) {
        setSelectedEntityId("all");
      }
      showToast("重点监控实体已更新");
    } catch (err) {
      setError(err instanceof Error ? err.message : "实体监控更新失败");
    }
  }

  function handleOpenEntity(entityId: string) {
    setSelectedEntityId(entityId);
    setActiveTab("events");
  }

  async function handleCreateDraft(candidateId: string, mode: PublishMode) {
    setBusyCandidateId(candidateId);
    try {
      await api.createDraftFromCandidate(candidateId, mode);
      const [candidateData, draftData] = await Promise.all([api.getCandidates(), api.getDrafts()]);
      setCandidates(candidateData.items);
      setDrafts(draftData.items);
      setActiveTab("drafts");
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成稿件失败");
    } finally {
      setBusyCandidateId(null);
    }
  }

  async function handleCreateDraftFromEvent(eventId: string) {
    const sourceEvent = events.find((event) => event.id === eventId) ?? alerts.find((alert) => alert.event_id === eventId);
    const draftTitleHint = sourceEvent?.title ?? "当前事件";
    setBusyEventId(eventId);
    setPendingDraftTitle(draftTitleHint);
    setPendingDraftSourceTab(activeTab);
    setHighlightDraftId(null);
    try {
      const response = await api.createDraftFromEvent(eventId);
      setDrafts((current) => {
        const existing = current.find((item) => item.id === response.item.id);
        if (existing) {
          return current.map((item) => (item.id === response.item.id ? response.item : item));
        }
        return [response.item, ...current];
      });
      setActiveTab("drafts");
      setHighlightDraftId(response.item.id);
      const [draftData, eventData, alertData, dashboardData] = await Promise.all([
        api.getDrafts(),
        api.getIntelEvents(),
        api.getIntelAlerts(),
        api.getDashboard(),
      ]);
      setDrafts(draftData.items);
      setEvents(eventData.items);
      setEventHistory(eventData.history_items ?? []);
      setAlerts(alertData.items);
      setAlertHistory(alertData.history_items ?? []);
      setDashboard((current) =>
        !current
          ? dashboardData
          : {
              ...dashboardData,
              runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
            },
      );
      showToast(`稿件已生成：${response.item.title}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成稿件失败");
    } finally {
      setBusyEventId(null);
      setPendingDraftTitle(null);
      setPendingDraftSourceTab(null);
    }
  }

  async function handleDraftAction(kind: "regenerate" | "approve" | "sync" | "preview" | "publish", draftId: string) {
    setBusyDraftId(draftId);
    try {
      if (kind === "regenerate") {
        await api.regenerateDraft(draftId);
      } else if (kind === "approve") {
        await api.approveDraft(draftId, true);
      } else if (kind === "sync") {
        await api.syncWeChatDraft(draftId);
      } else if (kind === "preview") {
        await api.openPreview(draftId);
      } else {
        await api.publishDraft(draftId);
      }
      const draftData = await api.getDrafts();
      setDrafts(draftData.items);
      const dashboardData = await api.getDashboard();
      setDashboard((current) =>
        !current
          ? dashboardData
          : {
              ...dashboardData,
              runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
            },
      );
      setBrowserSession(dashboardData.browser_session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "稿件动作执行失败");
    } finally {
      setBusyDraftId(null);
    }
  }

  async function handleDeleteDraft(draftId: string) {
    setBusyDraftId(draftId);
    try {
      await api.deleteDraft(draftId);
      const [draftData, candidateData, eventData, alertData, dashboardData] = await Promise.all([
        api.getDrafts(),
        api.getCandidates(),
        api.getIntelEvents(),
        api.getIntelAlerts(),
        api.getDashboard(),
      ]);
      setDrafts(draftData.items);
      setCandidates(candidateData.items);
      setEvents(eventData.items);
      setEventHistory(eventData.history_items ?? []);
      setAlerts(alertData.items);
      setAlertHistory(alertData.history_items ?? []);
      setDashboard((current) =>
        !current
          ? dashboardData
          : {
              ...dashboardData,
              runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
            },
      );
      if (editingDraftId === draftId) {
        setEditingDraftId(null);
      }
      if (highlightDraftId === draftId) {
        setHighlightDraftId(null);
      }
      showToast("稿件已删除");
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除稿件失败");
    } finally {
      setBusyDraftId(null);
    }
  }

  async function handleRunJob(action: string) {
    setBusyJobAction(action);
    try {
      await api.runJob(action);
      const [jobData, logData, dashboardData] = await Promise.all([api.getJobs(), api.getLogs(), api.getDashboard()]);
      setJobs(jobData.items);
      setLogs(logData.items);
      setDashboard((current) =>
        !current
          ? dashboardData
          : {
              ...dashboardData,
              runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
            },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "任务执行失败");
    } finally {
      setBusyJobAction(null);
    }
  }

  async function handleSaveChannel(payload: WeChatChannelConfig) {
    setSavingChannel(true);
    try {
      await api.updateWeChatConfig(payload);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "渠道保存失败");
    } finally {
      setSavingChannel(false);
    }
  }

  async function handleSaveLLMConfig(config: LLMConfig) {
    setSavingLLMConfig(true);
    try {
      const result = await api.updateLLMConfig(config);
      setLlmConfig(result.item);
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI 模型配置保存失败");
    } finally {
      setSavingLLMConfig(false);
    }
  }

  async function handleSaveSettings(payload: Record<string, unknown>) {
    try {
      const result = await api.updateSettings(payload);
      setAppSettings(result.item);
      showToast("设置已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "设置保存失败");
    }
  }

  function handleEditDraft(draftId: string) {
    setEditingDraftId(draftId);
  }

  function handleDraftContentSaved(draftId: string, updated: DraftItem) {
    setDrafts((prev) => prev.map((draft) => (draft.id === draftId ? updated : draft)));
  }

  async function handleRefreshBrowser(payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) {
    setRefreshingBrowser(true);
    try {
      await api.updateBrowserSession(payload);
      await api.checkWeChatBrowserSession();
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "浏览器会话刷新失败");
    } finally {
      setRefreshingBrowser(false);
    }
  }

  async function handleOpenBrowserDashboard(payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) {
    setOpeningBrowser(true);
    try {
      await api.updateBrowserSession(payload);
      await api.openWeChatDashboard();
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "打开公众号后台失败");
    } finally {
      setOpeningBrowser(false);
    }
  }

  async function handleStartRuntime() {
    setBusyRuntimeAction("start");
    try {
      const response = await api.startRuntime();
      setDashboard((current) =>
        current ? { ...current, runtime_status: pickNewerRuntimeStatus(current.runtime_status, response.item) ?? response.item } : current
      );
      setSummary((current) =>
        current
          ? {
              ...current,
              running: response.item.running,
              next_run_at: response.item.next_collect_at ?? current.next_run_at,
              work_scope: response.item.work_scope,
            }
          : current
      );
      await refreshIntelCore();
      showToast("已启动");
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动自动运行失败");
    } finally {
      setBusyRuntimeAction(null);
    }
  }

  // 独立的 runtime 状态快速轮询，活跃周期 2 秒一次，空闲 10 秒
  useEffect(() => {
    if (!dashboard?.runtime_status?.running) return;
    const isActiveCycle = isRuntimeActivelyProcessing(dashboard.runtime_status);
    const intervalMs = isActiveCycle ? 2000 : 10000;
    const timer = window.setInterval(async () => {
      try {
        const res = await api.getRuntimeStatus();
        setDashboard((cur) =>
          cur ? { ...cur, runtime_status: pickNewerRuntimeStatus(cur.runtime_status, res.item) ?? res.item } : cur
        );
      } catch {
        // silent
      }
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [dashboard?.runtime_status?.running, dashboard?.runtime_status?.control_state, dashboard?.runtime_status?.current_cycle]);

  function showToast(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(null), 3000);
  }

  async function handleStopRuntime() {
    setBusyRuntimeAction("stop");
    try {
      const response = await api.stopRuntime();
      setDashboard((current) =>
        current ? { ...current, runtime_status: pickNewerRuntimeStatus(current.runtime_status, response.item) ?? response.item } : current
      );
      setSummary((current) =>
        current
          ? {
              ...current,
              running: response.item.running,
              next_run_at: response.item.next_collect_at ?? null,
              work_scope: response.item.work_scope,
            }
          : current
      );
      await refreshIntelCore();
      showToast("已停止");
    } catch (err) {
      setError(err instanceof Error ? err.message : "停止自动运行失败");
    } finally {
      setBusyRuntimeAction(null);
    }
  }

  async function handleSaveRuntimePlan(payload: Omit<RuntimePlan, "effective_mode">) {
    setSavingRuntimePlan(true);
    try {
      const response = await api.updateRuntimePlan(payload);
      setDashboard((current) => current ? { ...current, runtime_plan: response.item } : current);
      const dashboardData = await api.getDashboard();
      setDashboard((current) =>
        !current
          ? dashboardData
          : {
              ...dashboardData,
              runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
            },
      );
      const summaryData = await api.getIntelSummary();
      setSummary(summaryData.item);
    } catch (err) {
      setError(err instanceof Error ? err.message : "工作计划保存失败");
    } finally {
      setSavingRuntimePlan(false);
    }
  }

  async function handleRunRuntimeIntent(intent: RuntimeIntent) {
    setBusyMaintenanceIntent(intent);
    try {
      const response = await api.runRuntimeIntent(intent);
      setDashboard((current) =>
        current ? { ...current, runtime_status: pickNewerRuntimeStatus(current.runtime_status, response.item) ?? response.item } : current
      );
      await refreshAll();
      showToast(intent === "normal_monitoring" ? "已执行一次完整补跑" : `已执行：${RUNTIME_INTENT_LABELS[intent]}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "维护动作执行失败");
    } finally {
      setBusyMaintenanceIntent(null);
    }
  }

  const currentPageMeta = useMemo(() => pageMeta[activeTab], [activeTab]);

  function dismissToast() {
    setToast(null);
  }

  function renderNavGroup(items: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }>) {
    return items.map((tab) => {
      const Icon = tab.icon;
      return (
        <button
          key={tab.key}
          type="button"
          className={`nav-button ${activeTab === tab.key ? "nav-button-active" : ""}`}
          onClick={() => setActiveTab(tab.key)}
        >
          <Icon size={16} />
          <span>{tab.label}</span>
        </button>
      );
    });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-card">
          <div className="brand-mark">
            <RadioTower size={18} />
          </div>
          <div>
            <strong>Auto News Studio</strong>
            <p>情报优先，人在首页控节奏</p>
          </div>
        </div>

        <div className="nav-group">
          <p className="nav-group-label">信息</p>
          <nav className="nav-list">{renderNavGroup(intelTabs)}</nav>
        </div>

        <div className="nav-group">
          <p className="nav-group-label">稿件</p>
          <nav className="nav-list">{renderNavGroup(draftTabs)}</nav>
        </div>

        <div className="nav-group nav-group-secondary">
          <p className="nav-group-label">系统与排障</p>
          <nav className="nav-list">{renderNavGroup(systemTabs)}</nav>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-footer-stats">
            <div>
              <span>预警</span>
              <strong>{summary?.alert_count ?? 0}</strong>
            </div>
            <div>
              <span>事件</span>
              <strong>{summary?.event_count ?? 0}</strong>
            </div>
            <div>
              <span>来源</span>
              <strong>{summary ? `${summary.healthy_sources}/${summary.total_sources}` : "0/0"}</strong>
            </div>
          </div>
          <div className="sidebar-footer-mode">
            <p>{dashboard ? deriveRuntimeDisplayStatus(dashboard.runtime_status) : "已停止"}</p>
            <strong>{dashboard ? RUNTIME_INTENT_LABELS[dashboard.runtime_status.run_intent] : "正常监测"}</strong>
          </div>
        </div>
      </aside>

      <main className="main-shell">
        <header className="page-header">
          <div>
            <p className="eyebrow">{currentPageMeta.eyebrow}</p>
            <h1>{currentPageMeta.title}</h1>
          </div>
          <button type="button" className="ghost-button" onClick={() => void refreshAll()}>
            {loading ? "刷新中..." : "刷新面板"}
          </button>
        </header>

        {error ? <div className="error-banner">{error}</div> : null}

        {toast ? (
          <div className="toast-banner" onClick={dismissToast}>
            <CheckCircle size={14} />
            <span>{toast}</span>
            <X size={14} className="toast-dismiss" />
          </div>
        ) : null}

        {pendingDraftTitle && activeTab !== "drafts" ? (
          <div className="setup-banner">
            <strong>AI 正在生成稿件</strong>
            <p>
              正在整理《{pendingDraftTitle}》的写稿简报并生成初稿。
              {pendingDraftSourceTab === "events" ? " 生成完成后会自动跳到稿件页。" : ""}
              {pendingDraftSourceTab === "alerts" ? " 生成完成后会自动带你进入稿件页。" : ""}
              {pendingDraftSourceTab === "watchlist" ? " 完成后会自动定位到新稿件。" : ""}
            </p>
          </div>
        ) : null}

        {llmConfig &&
        llmConfig.profiles.length > 0 &&
        llmConfig.profiles.every((profile) => !profile.enabled || !profile.api_key) &&
        activeTab !== "settings" ? (
          <div className="setup-banner" onClick={() => setActiveTab("settings")}>
            <strong>AI 模型未配置</strong>
            <p>填入 API Key 后，稿件生成和情报辅助判断才会启用。</p>
          </div>
        ) : null}

        {loading && !dashboard ? (
          <section className="panel">
            <p className="empty-state">正在加载情报控制台...</p>
          </section>
        ) : null}

        {dashboard && summary ? (
          <div className="page-content">
            {activeTab === "overview" ? (
              <IntelOverviewPage
                summary={summary}
                runtime={dashboard.runtime_status}
                entityWatchlistSummary={dashboard.entity_watchlist_summary}
                runtimePlan={dashboard.runtime_plan}
                savingRuntimePlan={savingRuntimePlan}
                busyRuntimeAction={busyRuntimeAction}
                busyMaintenanceIntent={busyMaintenanceIntent}
                refreshing={loading}
                onSaveRuntimePlan={handleSaveRuntimePlan}
                onStart={handleStartRuntime}
                onStop={handleStopRuntime}
                onRunIntent={handleRunRuntimeIntent}
                onRefresh={refreshAll}
                onNavigate={(tab) => setActiveTab(tab)}
                onOpenEntity={handleOpenEntity}
                onWatchEvent={handleWatchEvent}
                onIgnoreEvent={handleIgnoreEvent}
              />
            ) : null}

            {activeTab === "stream" ? <IntelStreamPage items={streamItems} /> : null}
            {activeTab === "events" ? (
              <IntelEventsPage
                items={events}
                historyItems={eventHistory}
                runtime={dashboard.runtime_status}
                entityWatchlist={entityWatchlist}
                entityWatchlistSummary={dashboard.entity_watchlist_summary}
                selectedEntityId={selectedEntityId}
                onSelectedEntityChange={setSelectedEntityId}
                onUpdateEntityWatchlist={handleUpdateEntityWatchlist}
                onOpenEntity={handleOpenEntity}
                onWatchEvent={handleWatchEvent}
                onIgnoreEvent={handleIgnoreEvent}
                onCreateDraft={handleCreateDraftFromEvent}
                busyEventId={busyEventId}
              />
            ) : null}
            {activeTab === "alerts" ? (
              <IntelAlertsPage
                items={alerts}
                historyItems={alertHistory}
                runtime={dashboard.runtime_status}
                eventCount={events.length}
                selectedEntityId={selectedEntityId}
                onSelectedEntityChange={setSelectedEntityId}
                onCreateDraft={handleCreateDraftFromEvent}
                busyEventId={busyEventId}
              />
            ) : null}
            {activeTab === "source-health" ? (
              <SourceHealthPage
                sources={sources}
                syncing={refreshingSources}
                savingSourceKey={savingSourceKey}
                syncingSourceKey={syncingSourceKey}
                onSyncSources={handleSourceSync}
                onSyncSource={handleSourceSyncOne}
                onSaveSource={handleSourceSave}
              />
            ) : null}

            {activeTab === "watchlist" ? (
              <WatchlistPanel
                items={events.filter((event) => event.watchlisted && !event.ignored)}
                busyEventId={busyEventId}
                onCreateDraft={handleCreateDraftFromEvent}
              />
            ) : null}

            {activeTab === "drafts" ? (
              <DraftTable
                drafts={drafts}
                busyDraftId={busyDraftId}
                highlightDraftId={highlightDraftId}
                pendingDraftTitle={pendingDraftTitle}
                onRegenerate={(draftId) => handleDraftAction("regenerate", draftId)}
                onApprove={(draftId) => handleDraftAction("approve", draftId)}
                onSyncDraft={(draftId) => handleDraftAction("sync", draftId)}
                onPreview={(draftId) => handleDraftAction("preview", draftId)}
                onPublish={(draftId) => handleDraftAction("publish", draftId)}
                onDelete={handleDeleteDraft}
                onEdit={handleEditDraft}
              />
            ) : null}

            {activeTab === "jobs" ? (
              <JobsPanel
                jobs={jobs}
                publishTasks={publishTasks}
                runtime={dashboard.runtime_status}
                runtimePlan={dashboard.runtime_plan}
                currentAutomationMode={dashboard.current_automation_mode}
                busyAction={busyJobAction}
                onRun={handleRunJob}
              />
            ) : null}

            {activeTab === "settings" ? (
              <SettingsPanel
                config={wechatConfig}
                browserSession={browserSession}
                publishBackends={dashboard.publish_backends}
                referenceProjects={referenceProjects}
                llmConfig={llmConfig}
                sources={sources}
                syncingSources={refreshingSources}
                savingSourceKey={savingSourceKey}
                syncingSourceKey={syncingSourceKey}
                isSaving={savingChannel}
                isSavingLLM={savingLLMConfig}
                isRefreshingBrowser={refreshingBrowser}
                isOpeningBrowser={openingBrowser}
                onSaveChannel={handleSaveChannel}
                onSaveLLMConfig={handleSaveLLMConfig}
                onRefreshBrowser={handleRefreshBrowser}
                onOpenBrowserDashboard={handleOpenBrowserDashboard}
                onSyncSources={handleSourceSync}
                onSyncSource={handleSourceSyncOne}
                onSaveSource={handleSourceSave}
                onCreateSource={handleSourceCreate}
                onDeleteSource={handleSourceDelete}
                onSaveSettings={handleSaveSettings}
                settings={appSettings}
              />
            ) : null}

            {activeTab === "logs" ? <LogsPanel logs={logs} runtime={dashboard.runtime_status} /> : null}
          </div>
        ) : null}
      </main>

      {editingDraftId ? (() => {
        const editingDraft = drafts.find((draft) => draft.id === editingDraftId);
        return editingDraft ? (
          <DraftEditorModal
            draft={editingDraft}
            onClose={() => setEditingDraftId(null)}
            onSave={handleDraftContentSaved}
          />
        ) : null;
      })() : null}
    </div>
  );
}
