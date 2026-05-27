import {
  AlertCircle,
  ArrowUpRight,
  CheckCircle,
  LayoutDashboard,
  RadioTower,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAdaptivePolling } from "./hooks/shared/useAdaptivePolling";
import { useRuntimeState } from "./hooks/shared/useRuntimeState";
import { useManagedDashboardTab } from "./hooks/shell/useManagedDashboardTab";
import { type BriefWorkbenchView, type BriefWorkflowFilter, type ShellLogLevelFilter } from "./hooks/shell/useAppShellState";
import { api } from "./lib/api";
import { deriveRuntimeDisplayStatus, RUNTIME_INTENT_LABELS } from "./lib/runtimeIntent";
import { draftTabs, intelTabs, systemTabs, type TabKey } from "./navigation/tabs";

const RUNTIME_POLL_INTERVALS = { active: 2000, running: 10000, idle: 10000 } as const;
import { AlertsPage } from "./screens/alerts/page";
import { useAlertsState } from "./screens/alerts/state";
import { BriefsPage } from "./screens/briefs/page";
import { useBriefsState } from "./screens/briefs/state";
import { DraftBoxPage } from "./screens/draft_box/page";
import { useWechatState } from "./screens/draft_box/state";
import { EventsPage } from "./screens/events/page";
import { useEventsState } from "./screens/events/state";
import { LogsPage } from "./screens/logs/page";
import { useAppShellState } from "./hooks/shell/useAppShellState";
import { useLogsState } from "./screens/logs/state";
import { OverviewPage } from "./screens/overview/page";
import { useOverviewState } from "./screens/overview/state";
import { PublishHistoryPage } from "./screens/publish_history/page";
import { SettingsPage } from "./screens/settings/page";
import { useSettingsState } from "./screens/settings/state";
import { SourceHealthPage } from "./screens/source_health/page";
import { useSourceHealthState } from "./screens/source_health/state";
import { StreamPage } from "./screens/stream/page";
import { useStreamState } from "./screens/stream/state";
import { WatchlistPage } from "./screens/watchlist/page";
import { useWatchlistState } from "./screens/watchlist/state";
import type { AppUpdateInfo, AppVersionInfo, BrowserSessionState, EntityWatchlistItem } from "./types";

const DEFAULT_STREAM_TAB_PAGE_SIZE = 50;
const DEFAULT_EVENTS_TAB_PAGE_SIZE = 50;
const DEFAULT_BRIEFS_PAGE_SIZE = 20;
const DEFAULT_LOGS_PAGE_SIZE = 50;
const DEFAULT_PUBLISH_TASKS_PAGE_SIZE = 20;
const WATCHLIST_TAB_PAGE_SIZE = 200;
// briefs removed from runtime-aware tabs to prevent request storm
const RUNTIME_AWARE_TABS: TabKey[] = ["overview", "stream", "events", "alerts", "source-health", "watchlist", "logs"];
const SETTINGS_REMINDER_TOAST = "请先在设置里完成 AI 配置和微信登录，再继续其他工作流。";
export default function App() {
  useManagedDashboardTab();

  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [browserSession, setBrowserSession] = useState<BrowserSessionState | null>(null);
  const [appVersion, setAppVersion] = useState<AppVersionInfo | null>(null);
  const [updateInfo, setUpdateInfo] = useState<AppUpdateInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const visibleUpdateInfo =
    updateInfo?.update_available && updateInfo.latest_version && !updateInfo.dismissed
      ? updateInfo
      : null;

  const reloadCurrentBriefsRef = useRef<() => Promise<void>>(async () => undefined);
  const didShowSettingsReminderRef = useRef(false);

  const reloadCurrentBriefs = useCallback(() => reloadCurrentBriefsRef.current(), []);

  const [entityWatchlist, setEntityWatchlist] = useState<EntityWatchlistItem[]>([]);

  const {
    dashboard,
    setDashboard,
    summary,
    setSummary,
    refreshOverviewData,
  } = useOverviewState({
    onBrowserSessionChange: setBrowserSession,
    onAppVersionChange: setAppVersion,
    onUpdateInfoChange: setUpdateInfo,
    onEntityWatchlistChange: setEntityWatchlist,
  });

  const {
    streamItems,
    streamPage,
    setStreamPage,
    streamPageSize,
    setStreamPageSize,
    streamTotal,
    loadStreamData,
  } = useStreamState({
    initialPageSize: DEFAULT_STREAM_TAB_PAGE_SIZE,
  });

  const {
    alerts,
    alertHistory,
    loadAlertsData,
  } = useAlertsState();

  const {
    watchlistEvents,
    loadWatchlistData,
  } = useWatchlistState({
    pageSize: WATCHLIST_TAB_PAGE_SIZE,
  });

  const loadBriefsDataRef = useRef<
    (page?: number, pageSize?: number, stage?: BriefWorkbenchView, workflowMode?: BriefWorkflowFilter, query?: string) => Promise<unknown>
  >(async () => undefined);
  const loadLogsDataRef = useRef<
    (page?: number, pageSize?: number, level?: ShellLogLevelFilter, query?: string) => Promise<unknown>
  >(async () => undefined);
  const loadTabDataImplRef = useRef<(tab: TabKey, options: { forceBrowserRefresh: boolean }) => Promise<void>>(async () => undefined);

  const runtimeStatus = dashboard?.runtime_status ?? null;
  const runtimeRunning = Boolean(runtimeStatus?.running);

  const shellLoadBriefsData = useCallback((...args: Parameters<typeof loadBriefsDataRef.current>) => {
    return loadBriefsDataRef.current(...args);
  }, []);

  const shellLoadLogsData = useCallback((...args: Parameters<typeof loadLogsDataRef.current>) => {
    return loadLogsDataRef.current(...args);
  }, []);

  const shellLoadTabDataImpl = useCallback((tab: TabKey, options: { forceBrowserRefresh: boolean }) => {
    return loadTabDataImplRef.current(tab, options);
  }, []);

  const {
    loading,
    toast,
    tabLoading,
    setTabLoading,
    showToast,
    markTabLoaded,
    refreshAll,
    reloadBriefsForActiveTab,
    reloadLogsForActiveTab,
    currentPageMeta,
    dismissToast,
  } = useAppShellState({
    activeTab,
    dashboardRecentLogs: dashboard?.recent_logs,
    runtimeStatus,
    runtimeAwareTabs: RUNTIME_AWARE_TABS,
    loadBriefsData: shellLoadBriefsData,
    loadLogsData: shellLoadLogsData,
    loadTabDataImpl: shellLoadTabDataImpl,
    refreshOverviewData,
    onError: setError,
  });

  const {
    events,
    eventsPage,
    setEventsPage,
    eventsPageSize,
    setEventsPageSize,
    eventsTotal,
    eventHistory,
    entityWatchlist: managedEntityWatchlist,
    setEntityWatchlist: setManagedEntityWatchlist,
    selectedEntityId,
    setSelectedEntityId,
    loadEventsData,
    loadEntityWatchlist,
    handleWatchEvent,
    handleIgnoreEvent,
    handleUpdateEntityWatchlist,
    handleOpenEntity,
  } = useEventsState({
    initialPageSize: DEFAULT_EVENTS_TAB_PAGE_SIZE,
    onToast: showToast,
    onError: (message) => setError(message),
    onReloadOverview: refreshOverviewData,
    onReloadWatchlist: loadWatchlistData,
    onReloadAlerts: loadAlertsData,
  });

  const {
    sources,
    setSources,
    refreshingSources,
    savingSourceKey,
    syncingSourceKey,
    loadSourceHealthData,
    handleSourceSync,
    handleSourceSyncOne,
    handleSourceSave,
    handleSourceCreate,
    handleSourceDelete,
  } = useSourceHealthState({
    onToast: showToast,
    onError: (message) => setError(message),
    onReloadOverview: refreshOverviewData,
    onReloadStream: () => loadStreamData(streamPage, streamPageSize),
    onReloadEvents: () => loadEventsData(eventsPage, eventsPageSize),
    onReloadWatchlist: loadWatchlistData,
    onReloadAlerts: loadAlertsData,
  });

  const {
    wechatMapping,
    wechatPublishHistory,
    publishTasks,
    publishTasksPage,
    setPublishTasksPage,
    publishTasksPageSize,
    setPublishTasksPageSize,
    publishTasksTotal,
    refreshingMapping,
    refreshingPublishHistory,
    deletingRemoteId,
    loadPublishHistoryData,
    loadDraftBoxData,
    handleRefreshWeChatMapping,
    handleRefreshWeChatPublishHistory,
    handleDeleteRemoteDraft,
    handleSyncBriefById,
  } = useWechatState({
    browserSession,
    onBrowserSessionChange: setBrowserSession,
    initialWechatPublishHistory: browserSession?.last_publish_history_check ?? null,
    initialPublishTasksPageSize: DEFAULT_PUBLISH_TASKS_PAGE_SIZE,
    onError: (message) => setError(message),
    onToast: showToast,
    onReloadBriefs: reloadCurrentBriefs,
    onReloadOverview: refreshOverviewData,
  });

  const loadSourcesForSettings = useCallback(async () => {
    const items = await loadSourceHealthData();
    setSources(items);
    return items;
  }, [loadSourceHealthData, setSources]);

  const {
    wechatConfig,
    referenceProjects,
    llmConfig,
    appSettings,
    systemDoctor,
    savingChannel,
    savingLLMConfig,
    refreshingBrowser,
    openingBrowser,
    loadSettingsData,
    loadUpdateInfo,
    handleCheckUpdate,
    handleDismissUpdate,
    handleSaveChannel,
    handleSaveLLMConfig,
    handleSaveSettings,
    handleExportConfig,
    handleExportBackup,
    handleRefreshBrowser,
    handleOpenBrowserDashboard,
  } = useSettingsState({
    browserSession,
    onBrowserSessionChange: setBrowserSession,
    updateInfo,
    onUpdateInfoChange: setUpdateInfo,
    onError: (message) => setError(message),
    onToast: showToast,
    onReloadOverview: refreshOverviewData,
    onLoadSources: loadSourcesForSettings,
  });

  const {
    logs,
    logsPage,
    setLogsPage,
    logsPageSize,
    setLogsPageSize,
    logsTotal,
    logLevelFilter,
    setLogLevelFilter,
    logSearchQuery,
    setLogSearchQuery,
    loadLogsData,
  } = useLogsState({
    initialPageSize: DEFAULT_LOGS_PAGE_SIZE,
  });

  const activateWatchlist = useCallback(() => {
    setActiveTab("watchlist");
    markTabLoaded("watchlist");
  }, [markTabLoaded]);

  const activateBriefs = useCallback(() => {
    setActiveTab("briefs");
    markTabLoaded("briefs");
  }, [markTabLoaded]);

  const {
    briefs,
    briefsPage,
    setBriefsPage,
    briefsPageSize,
    setBriefsPageSize,
    briefsTotal,
    briefStageFilter,
    setBriefStageFilter,
    briefWorkflowFilter,
    setBriefWorkflowFilter,
    briefSearchQuery,
    setBriefSearchQuery,
    briefRecordCounts,
    agentWorkflows,
    selectedDeepDive,
    busyEventId,
    busyBriefId,
    pendingDeepDiveTitle,
    pendingBriefTitle,
    creatingDailyDigest,
    abandoningWorkflowId,
    loadBriefsData,
    handleDeepDiveEvent,
    handleOpenDeepDive,
    handleCreateBrief,
    handleCreateDailyDigestBrief,
    handleAbandonAgentWorkflow,
    handleBriefAction,
    handleDeleteBrief,
    handleCopyBrief,
    handleCopyBriefPackage,
    loadBriefDetail,
    loadingBriefDetailId,
  } = useBriefsState({
    onError: (message) => setError(message),
    onToast: showToast,
    onReloadOverview: refreshOverviewData,
    onReloadEvents: () => loadEventsData(eventsPage, eventsPageSize),
    onReloadAlerts: loadAlertsData,
    onReloadWatchlist: loadWatchlistData,
    onReloadPublishHistory: () => loadPublishHistoryData(false),
    onReloadDraftBox: () => loadDraftBoxData(false),
    onMarkBriefsLoaded: () => markTabLoaded("briefs"),
    onActivateWatchlist: activateWatchlist,
    onActivateBriefs: activateBriefs,
    getEventsSnapshot: () => events,
    getWatchlistSnapshot: () => watchlistEvents,
    getAlertsSnapshot: () => alerts,
  });

  useEffect(() => {
    setManagedEntityWatchlist(entityWatchlist);
  }, [entityWatchlist, setManagedEntityWatchlist]);

  useEffect(() => {
    reloadCurrentBriefsRef.current = () => loadBriefsData();
  }, [loadBriefsData]);

  const {
    busyRuntimeAction,
    busyMaintenanceIntent,
    savingRuntimePlan,
    pollRuntimeStatus,
    handleStartRuntime,
    handleStopRuntime,
    handleSaveRuntimePlan,
    handleSetAutomationMode,
    handleRunRuntimeIntent,
  } = useRuntimeState({
    runtimePlan: dashboard?.runtime_plan ?? null,
    onDashboardChange: setDashboard,
    onSummaryChange: setSummary,
    onReloadOverview: refreshOverviewData,
    onRefreshAll: refreshAll,
    onError: (message) => setError(message),
    onToast: showToast,
  });

  loadBriefsDataRef.current = loadBriefsData;
  loadLogsDataRef.current = loadLogsData;
  loadTabDataImplRef.current = async (tab, { forceBrowserRefresh }) => {
    switch (tab) {
      case "overview":
        await refreshOverviewData(true);
        break;
      case "stream":
        await loadStreamData();
        break;
      case "events":
        await Promise.all([loadEventsData(), loadEntityWatchlist()]);
        break;
      case "alerts":
        await loadAlertsData();
        break;
      case "source-health":
        await loadSourceHealthData();
        break;
      case "watchlist":
        await loadWatchlistData();
        break;
      case "briefs":
        await loadBriefsData();
        break;
      case "publish-history":
        await loadPublishHistoryData(forceBrowserRefresh);
        break;
      case "draft-box":
        await loadDraftBoxData(forceBrowserRefresh);
        break;
      case "settings":
        await loadSettingsData();
        break;
      case "logs":
        await loadLogsData();
        break;
      default:
        break;
    }
  };

  // Only run once on mount, not on every refreshAll change
  const didInitRef = useRef(false);
  useEffect(() => {
    if (!didInitRef.current) {
      didInitRef.current = true;
      void refreshAll({ refreshActiveTab: false });
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void loadUpdateInfo(true)
        .then((response) => {
          if (!cancelled) {
            setUpdateInfo(response);
          }
        })
        .catch(() => {
          // Keep startup quiet when update check is temporarily unavailable.
        });
    }, 1200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [loadUpdateInfo]);

  useEffect(() => {
    if (!systemDoctor || activeTab === "settings" || didShowSettingsReminderRef.current) {
      return;
    }
    const llmReady = Boolean(systemDoctor.items.find((item) => item.key === "llm")?.ok);
    const wechatReady = Boolean(systemDoctor.items.find((item) => item.key === "wechat_login")?.ok);
    if (!llmReady || !wechatReady) {
      didShowSettingsReminderRef.current = true;
      showToast(SETTINGS_REMINDER_TOAST, "warning");
    }
  }, [activeTab, showToast, systemDoctor]);

  useEffect(() => {
    void reloadBriefsForActiveTab(briefsPageSize, briefStageFilter, briefWorkflowFilter, briefSearchQuery);
  }, [briefSearchQuery, briefStageFilter, briefWorkflowFilter, briefsPageSize, reloadBriefsForActiveTab]);

  useEffect(() => {
    void reloadLogsForActiveTab(logsPageSize, logLevelFilter, logSearchQuery);
  }, [logLevelFilter, logSearchQuery, logsPageSize, reloadLogsForActiveTab]);

  async function handleImportBackup(file: File) {
    try {
      const result = await api.importSystemBackup(file);
      await refreshAll({ refreshActiveTab: true, forceBrowserRefresh: false });
      showToast(result.message || "备份已导入");
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入备份失败");
    }
  }

  useAdaptivePolling(
    "runtime-status",
    runtimeStatus,
    pollRuntimeStatus,
    runtimeRunning,
    RUNTIME_POLL_INTERVALS,
  );

  function renderNavGroup(items: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }>) {
    return items.map((tab) => {
      const Icon = tab.icon;
      const showUpdateDot = tab.key === "settings" && Boolean(visibleUpdateInfo);
      return (
        <button
          key={tab.key}
          type="button"
          className={`nav-button ${activeTab === tab.key ? "nav-button-active" : ""}`}
          onClick={() => setActiveTab(tab.key)}
        >
          <Icon size={16} />
          <span>{tab.label}</span>
          {showUpdateDot ? <span className="nav-update-dot" aria-label="发现新版本" /> : null}
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
          <p className="nav-group-label">交付</p>
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
          <div className={`toast-banner toast-${toast.tone}`} onClick={dismissToast}>
            {toast.tone === "warning" ? <AlertCircle size={14} /> : <CheckCircle size={14} />}
            <span>{toast.message}</span>
            <X size={14} className="toast-dismiss" />
          </div>
        ) : null}

        {visibleUpdateInfo ? (
          <div className="update-banner">
            <div>
              <strong>发现新版本 {visibleUpdateInfo.latest_version}</strong>
              <p>
                当前 {visibleUpdateInfo.current_version}
                {visibleUpdateInfo.published_at ? `，发布于 ${visibleUpdateInfo.published_at}` : ""}
              </p>
            </div>
            <div className="update-banner-actions">
              <button
                type="button"
                className="ghost-button compact"
                onClick={() => window.open(visibleUpdateInfo.release_url ?? visibleUpdateInfo.release_notes_url ?? "", "_blank", "noopener,noreferrer")}
              >
                <ArrowUpRight size={14} />
                查看更新
              </button>
              <button type="button" className="ghost-button compact" onClick={() => void handleDismissUpdate(visibleUpdateInfo.latest_version ?? "")}>
                忽略此版本
              </button>
            </div>
          </div>
        ) : null}

        {pendingDeepDiveTitle && activeTab !== "watchlist" ? (
          <div className="setup-banner">
            <strong>正在执行正文深挖</strong>
            <p>如已配置 Tavily，会先补充《{pendingDeepDiveTitle}》的来源；随后抓取正文全文，完成后会更新深挖池状态。</p>
          </div>
        ) : null}

        {pendingBriefTitle && activeTab !== "briefs" ? (
          <div className="setup-banner">
            <strong>正在生成简报</strong>
            <p>正在把《{pendingBriefTitle}》的已抓取全文与证据全部交给 AI，完成后会更新简报工作台。</p>
          </div>
        ) : null}

        {llmConfig &&
        llmConfig.profiles.length > 0 &&
        llmConfig.profiles.every((profile) => !profile.enabled || !profile.api_key) &&
        activeTab !== "settings" ? (
          <div className="setup-banner" onClick={() => setActiveTab("settings")}>
            <strong>AI 模型未配置</strong>
            <p>填入 API Key 后，增强简报才会启用；规则简报和正文深挖仍可继续运行。</p>
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
              <OverviewPage
                summary={summary}
                runtime={dashboard.runtime_status}
                entityWatchlistSummary={dashboard.entity_watchlist_summary}
                runtimePlan={dashboard.runtime_plan}
                savingRuntimePlan={savingRuntimePlan}
                busyRuntimeAction={busyRuntimeAction}
                busyMaintenanceIntent={busyMaintenanceIntent}
                refreshing={loading}
                onSaveRuntimePlan={handleSaveRuntimePlan}
                onSetAutomationMode={handleSetAutomationMode}
                onStart={handleStartRuntime}
                onStop={handleStopRuntime}
                onRunIntent={handleRunRuntimeIntent}
                onRefresh={refreshAll}
                onNavigate={(tab: "alerts" | "events" | "source-health") => setActiveTab(tab)}
                onOpenEntity={(entityId: string) => {
                  handleOpenEntity(entityId);
                  setActiveTab("events");
                }}
                onWatchEvent={handleWatchEvent}
                onIgnoreEvent={handleIgnoreEvent}
              />
            ) : null}

            {activeTab === "stream" ? (
              <StreamPage
                items={streamItems}
                page={streamPage}
                pageSize={streamPageSize}
                total={streamTotal}
                loading={Boolean(tabLoading.stream)}
                onPageChange={(page) => {
                  setTabLoading((current) => ({ ...current, stream: true }));
                  void loadStreamData(page, streamPageSize).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : "实时流加载失败");
                  }).finally(() => {
                    setTabLoading((current) => ({ ...current, stream: false }));
                  });
                }}
                onPageSizeChange={(pageSize) => {
                  setStreamPageSize(pageSize);
                  setStreamPage(1);
                  setTabLoading((current) => ({ ...current, stream: true }));
                  void loadStreamData(1, pageSize).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : "实时流加载失败");
                  }).finally(() => {
                    setTabLoading((current) => ({ ...current, stream: false }));
                  });
                }}
              />
            ) : null}
            {activeTab === "events" ? (
              <EventsPage
                items={events}
                page={eventsPage}
                pageSize={eventsPageSize}
                total={eventsTotal}
                historyItems={eventHistory}
                runtime={dashboard.runtime_status}
                entityWatchlist={managedEntityWatchlist}
                entityWatchlistSummary={dashboard.entity_watchlist_summary}
                selectedEntityId={selectedEntityId}
                onSelectedEntityChange={setSelectedEntityId}
                onUpdateEntityWatchlist={handleUpdateEntityWatchlist}
                onOpenEntity={(entityId) => {
                  handleOpenEntity(entityId);
                  setActiveTab("events");
                }}
                onWatchEvent={handleWatchEvent}
                onIgnoreEvent={handleIgnoreEvent}
                onDeepDive={handleDeepDiveEvent}
                busyEventId={busyEventId}
                loading={Boolean(tabLoading.events)}
                onPageChange={(page) => {
                  setTabLoading((current) => ({ ...current, events: true }));
                  void loadEventsData(page, eventsPageSize).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : "热点簇加载失败");
                  }).finally(() => {
                    setTabLoading((current) => ({ ...current, events: false }));
                  });
                }}
                onPageSizeChange={(pageSize) => {
                  setEventsPageSize(pageSize);
                  setEventsPage(1);
                  setTabLoading((current) => ({ ...current, events: true }));
                  void loadEventsData(1, pageSize).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : "热点簇加载失败");
                  }).finally(() => {
                    setTabLoading((current) => ({ ...current, events: false }));
                  });
                }}
              />
            ) : null}
            {activeTab === "alerts" ? (
              <AlertsPage
                items={alerts}
                historyItems={alertHistory}
                runtime={dashboard.runtime_status}
                eventCount={events.length}
                selectedEntityId={selectedEntityId}
                onSelectedEntityChange={setSelectedEntityId}
                onDeepDive={handleDeepDiveEvent}
                busyEventId={busyEventId}
              />
            ) : null}
            {activeTab === "source-health" ? (
              <SourceHealthPage
                sources={sources}
                syncing={refreshingSources}
                savingSourceKey={savingSourceKey}
                syncingSourceKey={syncingSourceKey}
                onSyncSources={() => handleSourceSync()}
                onSyncSource={(sourceKey) => handleSourceSyncOne(sourceKey)}
                onSaveSource={handleSourceSave}
              />
            ) : null}

            {activeTab === "watchlist" ? (
              <WatchlistPage
                items={watchlistEvents.filter((event) => (event.watchlisted || event.deep_dive_id || event.brief_id) && !event.ignored)}
                selectedDeepDive={selectedDeepDive}
                busyEventId={busyEventId}
                onDeepDive={handleDeepDiveEvent}
                onCreateBrief={handleCreateBrief}
                onOpenDeepDive={handleOpenDeepDive}
              />
            ) : null}

            {activeTab === "briefs" ? (
              <BriefsPage
                briefs={briefs}
                page={briefsPage}
                pageSize={briefsPageSize}
                total={briefsTotal}
                view={briefStageFilter}
                workflowView={briefWorkflowFilter}
                searchTerm={briefSearchQuery}
                recordCounts={briefRecordCounts}
                agentWorkflows={agentWorkflows}
                loading={Boolean(tabLoading.briefs)}
                busyBriefId={busyBriefId}
                creatingDailyDigest={creatingDailyDigest}
                abandoningWorkflowId={abandoningWorkflowId}
                loadingBriefDetailId={loadingBriefDetailId}
                onViewChange={(view) => {
                  setBriefStageFilter(view);
                  setBriefsPage(1);
                }}
                onWorkflowViewChange={(view) => {
                  setBriefWorkflowFilter(view);
                  setBriefsPage(1);
                }}
                onSearchChange={(value) => {
                  setBriefSearchQuery(value);
                  setBriefsPage(1);
                }}
                onPageChange={(page) => {
                  setTabLoading((current) => ({ ...current, briefs: true }));
                  void loadBriefsData(page, briefsPageSize, briefStageFilter, briefWorkflowFilter, briefSearchQuery).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : "简报加载失败");
                  }).finally(() => {
                    setTabLoading((current) => ({ ...current, briefs: false }));
                  });
                }}
                onPageSizeChange={(pageSize) => {
                  setBriefsPageSize(pageSize);
                  setBriefsPage(1);
                }}
                onRefreshBrief={(eventId) => handleCreateBrief(eventId)}
                onCreateDailyDigest={handleCreateDailyDigestBrief}
                onLoadBriefDetail={loadBriefDetail}
                onCopyBrief={handleCopyBrief}
                onCopyPackage={handleCopyBriefPackage}
                onSyncBrief={(brief) => handleBriefAction("sync", brief)}
                onDeleteBrief={handleDeleteBrief}
                onAbandonAgentWorkflow={handleAbandonAgentWorkflow}
              />
            ) : null}

            {activeTab === "publish-history" ? (
              <PublishHistoryPage
                history={wechatPublishHistory}
                refreshing={refreshingPublishHistory}
                onRefresh={handleRefreshWeChatPublishHistory}
              />
            ) : null}

            {activeTab === "draft-box" ? (
              <DraftBoxPage
                mapping={wechatMapping}
                briefs={briefs}
                agentWorkflows={agentWorkflows}
                localBriefCount={briefRecordCounts.all}
                browserSession={browserSession}
                publishTasks={publishTasks}
                publishTasksPage={publishTasksPage}
                publishTasksPageSize={publishTasksPageSize}
                publishTasksTotal={publishTasksTotal}
                refreshing={refreshingMapping}
                deletingRemoteId={deletingRemoteId}
                loadingBriefDetailId={loadingBriefDetailId}
                onRefresh={handleRefreshWeChatMapping}
                onDeleteRemote={handleDeleteRemoteDraft}
                onSyncBrief={handleSyncBriefById}
                onLoadBriefDetail={loadBriefDetail}
                onPublishTasksPageChange={(page) => {
                  setTabLoading((current) => ({ ...current, ["draft-box"]: true }));
                  void loadDraftBoxData(false, page, publishTasksPageSize).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : "操作记录加载失败");
                  }).finally(() => {
                    setTabLoading((current) => ({ ...current, ["draft-box"]: false }));
                  });
                }}
                onPublishTasksPageSizeChange={(pageSize) => {
                  setPublishTasksPageSize(pageSize);
                  setPublishTasksPage(1);
                  setTabLoading((current) => ({ ...current, ["draft-box"]: true }));
                  void loadDraftBoxData(false, 1, pageSize).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : "操作记录加载失败");
                  }).finally(() => {
                    setTabLoading((current) => ({ ...current, ["draft-box"]: false }));
                  });
                }}
              />
            ) : null}

            {activeTab === "settings" ? (
              <SettingsPage
                referenceProjects={referenceProjects}
                llmConfig={llmConfig}
                sources={sources}
                syncingSources={refreshingSources}
                savingSourceKey={savingSourceKey}
                syncingSourceKey={syncingSourceKey}
                isSavingLLM={savingLLMConfig}
                settings={appSettings}
                doctor={systemDoctor}
                appVersion={appVersion}
                updateInfo={updateInfo}
                wechatConfig={wechatConfig}
                browserSession={browserSession}
                isSavingChannel={savingChannel}
                isRefreshingBrowser={refreshingBrowser}
                isOpeningBrowser={openingBrowser}
                onSaveChannel={handleSaveChannel}
                onRefreshBrowser={handleRefreshBrowser}
                onOpenBrowserDashboard={handleOpenBrowserDashboard}
                onSaveLLMConfig={handleSaveLLMConfig}
                onSyncSources={() => handleSourceSync({ includeSourceHealth: true })}
                onSyncSource={(sourceKey) => handleSourceSyncOne(sourceKey, { includeSourceHealth: true })}
                onSaveSource={handleSourceSave}
                onCreateSource={handleSourceCreate}
                onDeleteSource={handleSourceDelete}
                onSaveSettings={handleSaveSettings}
                onExportConfig={handleExportConfig}
                onExportBackup={handleExportBackup}
                onImportBackup={handleImportBackup}
                onCheckUpdate={handleCheckUpdate}
                onDismissUpdate={handleDismissUpdate}
              />
            ) : null}

            {activeTab === "logs" ? (
              <LogsPage
                logs={logs}
                page={logsPage}
                pageSize={logsPageSize}
                total={logsTotal}
                levelFilter={logLevelFilter}
                searchQuery={logSearchQuery}
                loading={Boolean(tabLoading.logs)}
                runtime={dashboard.runtime_status}
                onLevelFilterChange={(value) => {
                  setLogLevelFilter(value);
                  setLogsPage(1);
                }}
                onSearchChange={(value) => {
                  setLogSearchQuery(value);
                  setLogsPage(1);
                }}
                onPageChange={(page) => {
                  setTabLoading((current) => ({ ...current, logs: true }));
                  void loadLogsData(page, logsPageSize, logLevelFilter, logSearchQuery).catch((err: unknown) => {
                    setError(err instanceof Error ? err.message : "日志加载失败");
                  }).finally(() => {
                    setTabLoading((current) => ({ ...current, logs: false }));
                  });
                }}
                onPageSizeChange={(pageSize) => {
                  setLogsPageSize(pageSize);
                  setLogsPage(1);
                }}
              />
            ) : null}
          </div>
        ) : null}
      </main>

    </div>
  );
}
