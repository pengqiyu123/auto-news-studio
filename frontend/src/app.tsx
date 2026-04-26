import {
  AlertCircle,
  LayoutDashboard,
  Newspaper,
  RadioTower,
  Settings,
  StickyNote,
  WavesLadder,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CandidatesPanel } from "./components/CandidatesPanel";
import { DraftEditorModal } from "./components/DraftEditorModal";
import { DraftTable } from "./components/DraftTable";
import { GlobalControlBar } from "./components/GlobalControlBar";
import { IntelPanel } from "./components/IntelPanel";
import { JobsPanel } from "./components/JobsPanel";
import { LogsPanel } from "./components/LogsPanel";
import { OverviewPanel } from "./components/OverviewPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { api } from "./lib/api";
import type {
  AutomationMode,
  AutomationModeDefinition,
  AutomationModeProfile,
  BatchDraftResult,
  BrowserSessionState,
  CandidateTopic,
  DashboardResponse,
  DraftItem,
  IntelSnapshot,
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

type TabKey = "overview" | "intel" | "candidates" | "drafts" | "jobs" | "settings" | "logs";

const primaryTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "overview", label: "驾驶舱", icon: LayoutDashboard },
  { key: "intel", label: "情报", icon: Newspaper },
  { key: "candidates", label: "候选", icon: WavesLadder },
  { key: "drafts", label: "稿件", icon: StickyNote },
];

const secondaryTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "settings", label: "设置", icon: Settings },
  { key: "logs", label: "日志", icon: AlertCircle },
];

const pageMeta: Record<TabKey, { eyebrow: string; title: string; description: string }> = {
  overview: {
    eyebrow: "驾驶舱",
    title: "系统状态与全局主控",
    description: "这里只看系统有没有在跑、哪里卡住，以及下一步更适合去哪一页处理。",
  },
  intel: {
    eyebrow: "情报中心",
    title: "最新发现、热点簇与来源健康",
    description: "集中查看最新流入的信息、热点主题、GitHub 技术动态和来源健康状态。",
  },
  candidates: {
    eyebrow: "候选池",
    title: "最近同步后的可写主题池",
    description: "这里不是全网原始流，而是经过去重聚类后，已经值得写的候选主题。",
  },
  drafts: {
    eyebrow: "稿件工作台",
    title: "正式稿、编辑信息与微信状态",
    description: "先把正式稿打磨稳定，再决定何时同步微信草稿箱或推进下一步。",
  },
  jobs: {
    eyebrow: "手动任务中心",
    title: "补跑、重建和强制重试入口",
    description: "自动运行归驾驶舱总控，任务页只保留手动补刀和排障动作。",
  },
  settings: {
    eyebrow: "设置",
    title: "发布渠道、AI 模型、信息源与系统偏好",
    description: "所有配置型功能集中收纳，不打断主工作流。",
  },
  logs: {
    eyebrow: "运行日志",
    title: "系统痕迹与异常线索",
    description: "区分系统运行日志和业务动作日志，直接判断后台是否持续在工作。",
  },
};

export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [intel, setIntel] = useState<IntelSnapshot | null>(null);
  const [automationModes, setAutomationModes] = useState<AutomationModeDefinition[]>([]);
  const [automationProfiles, setAutomationProfiles] = useState<AutomationModeProfile[]>([]);
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
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingMode, setPendingMode] = useState<AutomationMode | null>(null);
  const [savingAutomationProfile, setSavingAutomationProfile] = useState<AutomationMode | null>(null);
  const [busyDraftId, setBusyDraftId] = useState<string | null>(null);
  const [busyJobAction, setBusyJobAction] = useState<string | null>(null);
  const [savingChannel, setSavingChannel] = useState(false);
  const [savingLLMConfig, setSavingLLMConfig] = useState(false);
  const [refreshingSources, setRefreshingSources] = useState(false);
  const [savingSourceKey, setSavingSourceKey] = useState<string | null>(null);
  const [syncingSourceKey, setSyncingSourceKey] = useState<string | null>(null);
  const [busyCandidateId, setBusyCandidateId] = useState<string | null>(null);
  const [batchingDrafts, setBatchingDrafts] = useState(false);
  const [batchDraftResult, setBatchDraftResult] = useState<BatchDraftResult | null>(null);
  const [refreshingBrowser, setRefreshingBrowser] = useState(false);
  const [openingBrowser, setOpeningBrowser] = useState(false);
  const [highlightCandidateId, setHighlightCandidateId] = useState<string | null>(null);
  const [highlightDraftId, setHighlightDraftId] = useState<string | null>(null);
  const [busyRuntimeAction, setBusyRuntimeAction] = useState<"start" | "stop" | null>(null);
  const [savingRuntimePlan, setSavingRuntimePlan] = useState(false);

  const refreshDashboard = useCallback(async () => {
    try {
      const dashboardData = await api.getDashboard();
      setDashboard(dashboardData);
      setBrowserSession(dashboardData.browser_session);
      setSources(dashboardData.sources);
    } catch (err) {
      setError(err instanceof Error ? err.message : "驾驶舱刷新失败");
    }
  }, []);

  const refreshIntel = useCallback(async () => {
    try {
      const intelData = await api.getIntel();
      setIntel(intelData.item);
      setSources(intelData.item.source_health);
    } catch (err) {
      setError(err instanceof Error ? err.message : "情报刷新失败");
    }
  }, []);

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        dashboardData,
        intelData,
        automationModeData,
        automationProfileData,
        candidateData,
        draftData,
        publishTaskData,
        jobData,
        logData,
        channelData,
        browserData,
        referenceData,
        llmConfigData,
      ] = await Promise.all([
        api.getDashboard(),
        api.getIntel(),
        api.getAutomationModes(),
        api.getAutomationProfiles(),
        api.getCandidates(),
        api.getDrafts(),
        api.getPublishTasks(),
        api.getJobs(),
        api.getLogs(),
        api.getWeChatConfig(),
        api.getBrowserSession(),
        api.getReferenceProjects(),
        api.getLLMConfig(),
      ]);
      setDashboard(dashboardData);
      setIntel(intelData.item);
      setAutomationModes(automationModeData.items);
      setAutomationProfiles(automationProfileData.items);
      setSources(intelData.item.source_health);
      setCandidates(candidateData.items);
      setDrafts(draftData.items);
      setPublishTasks(publishTaskData.items);
      setJobs(jobData.items);
      setLogs(logData.items);
      setWechatConfig(channelData.item);
      setBrowserSession(browserData.item);
      setReferenceProjects(referenceData.items);
      setLlmConfig(llmConfigData.item);
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
    if (!dashboard || activeTab !== "overview") {
      return;
    }
    const hasRunningWork = dashboard.execution_chain.stages.some((item) => item.status === "running");
    const intervalMs = hasRunningWork ? 15000 : 60000;
    const timer = window.setInterval(() => {
      void refreshDashboard();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [activeTab, dashboard, refreshDashboard]);

  useEffect(() => {
    if (activeTab !== "intel" || !dashboard?.runtime_status.running) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshIntel();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [activeTab, dashboard?.runtime_status.running, refreshIntel]);

  useEffect(() => {
    if (activeTab !== "candidates" || !dashboard?.runtime_status.running) {
      return;
    }
    const timer = window.setInterval(() => {
      void Promise.all([api.getCandidates(), api.getDashboard()])
        .then(([candidateData, dashboardData]) => {
          setCandidates(candidateData.items);
          setDashboard(dashboardData);
          setBrowserSession(dashboardData.browser_session);
          setSources(dashboardData.sources);
        })
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "候选池自动刷新失败");
        });
    }, 30000);
    return () => window.clearInterval(timer);
  }, [activeTab, dashboard?.runtime_status.running]);

  const currentMode = useMemo(() => dashboard?.current_mode.key ?? "draft_only", [dashboard]);
  const currentPageMeta = useMemo(() => pageMeta[activeTab], [activeTab]);

  async function handleModeChange(mode: AutomationMode) {
    setPendingMode(mode);
    try {
      await api.setAutomationMode(mode);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "模式切换失败");
    } finally {
      setPendingMode(null);
    }
  }

  async function handleAutomationProfileSave(mode: AutomationMode, profile: AutomationModeProfile) {
    setSavingAutomationProfile(mode);
    try {
      const response = await api.updateAutomationProfile(mode, profile);
      setAutomationProfiles(response.items);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行参数保存失败");
    } finally {
      setSavingAutomationProfile(null);
    }
  }

  async function handleSourceSync() {
    setRefreshingSources(true);
    try {
      await api.syncSources();
      await refreshAll();
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
      await refreshAll();
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
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "来源保存失败");
    } finally {
      setSavingSourceKey(null);
    }
  }

  async function handleCreateDraft(candidateId: string, mode: PublishMode) {
    setBusyCandidateId(candidateId);
    try {
      const response = await api.createDraftFromCandidate(candidateId, mode);
      await refreshAll();
      setHighlightCandidateId(null);
      setHighlightDraftId(response.item.id);
      setActiveTab("drafts");
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成初稿失败");
    } finally {
      setBusyCandidateId(null);
    }
  }

  async function handleBatchCreateDrafts() {
    setBatchingDrafts(true);
    try {
      const result = await api.batchCreateDrafts();
      setBatchDraftResult(result);
      await refreshAll();
      if (result.draft_ids.length) {
        setHighlightDraftId(result.draft_ids[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "批量生成初稿失败");
    } finally {
      setBatchingDrafts(false);
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
      await refreshAll();
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
      await refreshAll();
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

  function handleEditDraft(draftId: string) {
    setEditingDraftId(draftId);
  }

  function handleDraftContentSaved(draftId: string, updated: DraftItem) {
    setDrafts((prev) => prev.map((d) => (d.id === draftId ? updated : d)));
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
      await api.startRuntime();
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动自动运行失败");
    } finally {
      setBusyRuntimeAction(null);
    }
  }

  async function handleStopRuntime() {
    setBusyRuntimeAction("stop");
    try {
      await api.stopRuntime();
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "停止自动运行失败");
    } finally {
      setBusyRuntimeAction(null);
    }
  }

  async function handleSaveRuntimePlan(payload: Omit<RuntimePlan, "effective_mode">) {
    setSavingRuntimePlan(true);
    try {
      await api.updateRuntimePlan(payload);
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "自动运行计划保存失败");
    } finally {
      setSavingRuntimePlan(false);
    }
  }

  async function handleOpenCandidate(candidateId: string) {
    setHighlightCandidateId(candidateId);
    setHighlightDraftId(null);
    setActiveTab("candidates");
    try {
      const candidateData = await api.getCandidates();
      setCandidates(candidateData.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "候选池刷新失败");
    }
  }

  async function handleOpenDraft(draftId: string) {
    setHighlightDraftId(draftId);
    setHighlightCandidateId(null);
    setActiveTab("drafts");
    try {
      const draftData = await api.getDrafts();
      setDrafts(draftData.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "稿件列表刷新失败");
    }
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
            <p>信息优先、草稿优先</p>
          </div>
        </div>

        <div className="nav-group">
          <p className="nav-group-label">主流程</p>
          <nav className="nav-list">{renderNavGroup(primaryTabs)}</nav>
        </div>

        <div className="nav-group nav-group-secondary">
          <p className="nav-group-label">系统与排障</p>
          <nav className="nav-list">{renderNavGroup(secondaryTabs)}</nav>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-footer-stats">
            <div>
              <span>候选</span>
              <strong>{candidates.length}</strong>
            </div>
            <div>
              <span>稿件</span>
              <strong>{drafts.length}</strong>
            </div>
            <div>
              <span>来源</span>
              <strong>{dashboard?.top_bar.healthy_sources ?? 0}/{dashboard?.top_bar.total_sources ?? 0}</strong>
            </div>
          </div>
          <div className="sidebar-footer-mode">
            <p>{dashboard?.runtime_status.running ? "运行中" : "已停止"}</p>
            <strong>{dashboard?.current_automation_mode.label ?? "雷达捕获"}</strong>
          </div>
        </div>
      </aside>

      <main className="main-shell">
        <header className="page-header">
          <div>
            <p className="eyebrow">{currentPageMeta.eyebrow}</p>
            <h1>{currentPageMeta.title}</h1>
            <p className="subtle">{currentPageMeta.description}</p>
          </div>
          <button type="button" className="ghost-button" onClick={() => void refreshAll()}>
            {loading ? "刷新中..." : "刷新面板"}
          </button>
        </header>

        {error ? <div className="error-banner">{error}</div> : null}

        {dashboard && llmConfig && llmConfig.providers.length > 0 && llmConfig.providers.every((p) => !p.enabled || !p.api_key) && activeTab !== "settings" ? (
          <div className="setup-banner" onClick={() => setActiveTab("settings")}>
            <strong>AI 模型未配置</strong>
            <p>填入 API Key 后才能使用 AI 生成文章。点击前往设置。</p>
          </div>
        ) : null}

        {loading && !dashboard ? (
          <section className="panel">
            <p className="empty-state">正在加载控制台数据...</p>
          </section>
        ) : null}

        {dashboard ? (
          <div className="page-content">
            {activeTab === "overview" ? (
              <>
                <GlobalControlBar
                  runtime={dashboard.runtime_status}
                  runtimePlan={dashboard.runtime_plan}
                  currentMode={dashboard.current_automation_mode.key}
                  modes={automationModes}
                  profiles={automationProfiles}
                  pendingMode={pendingMode}
                  savingProfileMode={savingAutomationProfile}
                  savingRuntimePlan={savingRuntimePlan}
                  busyRuntimeAction={busyRuntimeAction}
                  refreshing={loading}
                  onModeChange={handleModeChange}
                  onSaveProfile={handleAutomationProfileSave}
                  onSaveRuntimePlan={handleSaveRuntimePlan}
                  onStart={handleStartRuntime}
                  onStop={handleStopRuntime}
                  onRefresh={refreshAll}
                />
                <OverviewPanel dashboard={dashboard} onNavigate={(tab) => setActiveTab(tab)} />
              </>
            ) : null}

            {activeTab === "intel" && intel ? (
              <IntelPanel
                intel={intel}
                currentMode={currentMode}
                syncing={refreshingSources}
                savingSourceKey={savingSourceKey}
                syncingSourceKey={syncingSourceKey}
                busyCandidateId={busyCandidateId}
                onSyncSources={handleSourceSync}
                onSyncSource={handleSourceSyncOne}
                onSaveSource={handleSourceSave}
                onCreateDraft={handleCreateDraft}
                onOpenCandidate={(candidateId) => void handleOpenCandidate(candidateId)}
                onOpenDraft={(draftId) => void handleOpenDraft(draftId)}
              />
            ) : null}

            {activeTab === "candidates" ? (
              <CandidatesPanel
                candidates={candidates}
                busyCandidateId={busyCandidateId}
                highlightCandidateId={highlightCandidateId}
                dashboard={dashboard}
                currentMode={currentMode}
                batchingDrafts={batchingDrafts}
                batchResult={batchDraftResult}
                onCreateDraft={handleCreateDraft}
                onBatchCreateDrafts={handleBatchCreateDrafts}
              />
            ) : null}

            {activeTab === "drafts" ? (
              <DraftTable
                drafts={drafts}
                busyDraftId={busyDraftId}
                highlightDraftId={highlightDraftId}
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
              />
            ) : null}

            {activeTab === "logs" ? <LogsPanel logs={logs} runtime={dashboard.runtime_status} /> : null}
          </div>
        ) : null}
      </main>

      {editingDraftId ? (() => {
        const editingDraft = drafts.find((d) => d.id === editingDraftId);
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
