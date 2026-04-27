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
import type {
  BrowserSessionState,
  CandidateTopic,
  DashboardResponse,
  DiscoveryItem,
  DraftItem,
  IntelAlert,
  IntelEvent,
  IntelOverviewSummary,
  JobItem,
  LLMConfig,
  LogItem,
  PublishMode,
  PublishTask,
  ReferenceProject,
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
  { key: "watchlist", label: "重点观察", icon: WavesLadder },
  { key: "drafts", label: "稿件", icon: StickyNote },
];

const systemTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "jobs", label: "任务", icon: RadioTower },
  { key: "settings", label: "设置", icon: Settings },
  { key: "logs", label: "日志", icon: AlertCircle },
];

const pageMeta: Record<TabKey, { eyebrow: string; title: string }> = {
  overview: { eyebrow: "总览", title: "情报总览" },
  stream: { eyebrow: "实时流", title: "实时流" },
  events: { eyebrow: "热点簇", title: "热点簇" },
  alerts: { eyebrow: "预警台", title: "预警台" },
  "source-health": { eyebrow: "来源健康", title: "来源健康" },
  watchlist: { eyebrow: "重点观察", title: "重点观察" },
  drafts: { eyebrow: "稿件", title: "稿件" },
  jobs: { eyebrow: "任务", title: "任务" },
  settings: { eyebrow: "设置", title: "设置" },
  logs: { eyebrow: "日志", title: "日志" },
};

export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [summary, setSummary] = useState<IntelOverviewSummary | null>(null);
  const [streamItems, setStreamItems] = useState<DiscoveryItem[]>([]);
  const [events, setEvents] = useState<IntelEvent[]>([]);
  const [alerts, setAlerts] = useState<IntelAlert[]>([]);
  const [sources, setSources] = useState<SourceConnector[]>([]);
  const [candidates, setCandidates] = useState<CandidateTopic[]>([]);
  const [drafts, setDrafts] = useState<DraftItem[]>([]);
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
  const [refreshingBrowser, setRefreshingBrowser] = useState(false);
  const [openingBrowser, setOpeningBrowser] = useState(false);
  const [busyRuntimeAction, setBusyRuntimeAction] = useState<"start" | "stop" | null>(null);
  const [savingRuntimePlan, setSavingRuntimePlan] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const refreshIntelCore = useCallback(async () => {
    const [dashboardData, summaryData, streamData, eventData, alertData, sourceData, candidateData] = await Promise.all([
      api.getDashboard(),
      api.getIntelSummary(),
      api.getDiscoveryItems(),
      api.getIntelEvents(),
      api.getIntelAlerts(),
      api.getIntelSources(),
      api.getCandidates(),
    ]);
    setDashboard(dashboardData);
    setSummary(summaryData.item);
    setStreamItems(streamData.items);
    setEvents(eventData.items);
    setAlerts(alertData.items);
    setSources(sourceData.items);
    setCandidates(candidateData.items);
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
        api.getPublishTasks(),
        api.getJobs(),
        api.getLogs(),
        api.getWeChatConfig(),
        api.getBrowserSession(),
        api.getReferenceProjects(),
        api.getLLMConfig(),
        api.getSettings(),
      ]);
      setDashboard(dashboardData);
      setSummary(summaryData.item);
      setStreamItems(streamData.items);
      setEvents(eventData.items);
      setAlerts(alertData.items);
      setSources(sourceData.items);
      setCandidates(candidateData.items);
      setDrafts(draftData.items);
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
    const intelFocusedTabs: TabKey[] = ["overview", "stream", "events", "alerts", "source-health", "watchlist"];
    if (!intelFocusedTabs.includes(activeTab)) {
      return;
    }
    const isRunning = dashboard?.runtime_status.running;
    const isActiveCycle = dashboard?.runtime_status ? (
      dashboard.runtime_status.control_state === "running" ||
      dashboard.runtime_status.current_cycle === "starting" ||
      dashboard.runtime_status.current_cycle === "collecting" ||
      dashboard.runtime_status.current_cycle === "drafting" ||
      dashboard.runtime_status.current_cycle === "wechat_sync"
    ) : false;
    const intervalMs = isActiveCycle ? 3000 : isRunning ? 10000 : 60000;
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
      setDashboard(dashboardData);
      setBrowserSession(dashboardData.browser_session);
    } catch (err) {
      setError(err instanceof Error ? err.message : "稿件动作执行失败");
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
      setDashboard(dashboardData);
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
      setDashboard((current) => current ? { ...current, runtime_status: response.item } : current);
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

  function showToast(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(null), 3000);
  }

  async function handleStopRuntime() {
    setBusyRuntimeAction("stop");
    try {
      const response = await api.stopRuntime();
      setDashboard((current) => current ? { ...current, runtime_status: response.item } : current);
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
      setDashboard(dashboardData);
      const summaryData = await api.getIntelSummary();
      setSummary(summaryData.item);
    } catch (err) {
      setError(err instanceof Error ? err.message : "工作计划保存失败");
    } finally {
      setSavingRuntimePlan(false);
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
            <p>{dashboard?.runtime_status.running ? "工作中" : "已停止"}</p>
            <strong>{summary ? summary.work_scope.replace(/_/g, " ") : "collect_events_alerts"}</strong>
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
                runtimePlan={dashboard.runtime_plan}
                savingRuntimePlan={savingRuntimePlan}
                busyRuntimeAction={busyRuntimeAction}
                refreshing={loading}
                onSaveRuntimePlan={handleSaveRuntimePlan}
                onStart={handleStartRuntime}
                onStop={handleStopRuntime}
                onSyncNow={handleSourceSync}
                onRefresh={refreshAll}
                onNavigate={(tab) => setActiveTab(tab)}
                onWatchEvent={handleWatchEvent}
                onIgnoreEvent={handleIgnoreEvent}
              />
            ) : null}

            {activeTab === "stream" ? <IntelStreamPage items={streamItems} /> : null}
            {activeTab === "events" ? <IntelEventsPage items={events} onWatchEvent={handleWatchEvent} onIgnoreEvent={handleIgnoreEvent} /> : null}
            {activeTab === "alerts" ? <IntelAlertsPage items={alerts} /> : null}
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
              <WatchlistPanel candidates={candidates} busyCandidateId={busyCandidateId} onCreateDraft={handleCreateDraft} />
            ) : null}

            {activeTab === "drafts" ? (
              <DraftTable
                drafts={drafts}
                busyDraftId={busyDraftId}
                highlightDraftId={null}
                onRegenerate={(draftId) => handleDraftAction("regenerate", draftId)}
                onApprove={(draftId) => handleDraftAction("approve", draftId)}
                onSyncDraft={(draftId) => handleDraftAction("sync", draftId)}
                onPreview={(draftId) => handleDraftAction("preview", draftId)}
                onPublish={(draftId) => handleDraftAction("publish", draftId)}
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
