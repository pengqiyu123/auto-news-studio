import {
  AlertCircle,
  ArrowUpRight,
  CheckCircle,
  FileStack,
  LayoutDashboard,
  RadioTower,
  SearchCheck,
  Settings,
  Siren,
  Sparkles,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BriefTable } from "./components/BriefTable";
import { DeepDivePoolPanel } from "./components/DeepDivePoolPanel";
import { IntelAlertsPage } from "./components/IntelAlertsPage";
import { IntelEventsPage } from "./components/IntelEventsPage";
import { IntelOverviewPage } from "./components/IntelOverviewPage";
import { IntelStreamPage } from "./components/IntelStreamPage";
import { LogsPanel } from "./components/LogsPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { SourceHealthPage } from "./components/SourceHealthPage";
import { WeChatDraftBoxPanel } from "./components/WeChatDraftBoxPanel";
import { api } from "./lib/api";
import { deriveRuntimeDisplayStatus, isRuntimeActivelyProcessing, pickNewerRuntimeStatus, RUNTIME_INTENT_LABELS } from "./lib/runtimeIntent";
import type {
  AppUpdateInfo,
  AppVersionInfo,
  BrowserSessionState,
  BriefItem,
  DashboardResponse,
  DiscoveryItem,
  EntityWatchlistItem,
  EventDeepDive,
  IntelAlert,
  IntelAlertHistoryItem,
  IntelEvent,
  IntelEventHistoryItem,
  IntelOverviewSummary,
  LLMConfig,
  LogItem,
  PublishTask,
  ReferenceProject,
  RuntimeIntent,
  RuntimePlan,
  SourceConnector,
  SystemDoctorResult,
  WeChatMappingSnapshot,
  WeChatChannelConfig,
} from "./types";

type TabKey =
  | "overview"
  | "stream"
  | "events"
  | "alerts"
  | "source-health"
  | "watchlist"
  | "briefs"
  | "draft-box"
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
  { key: "watchlist", label: "深挖池", icon: Sparkles },
  { key: "briefs", label: "简报", icon: FileStack },
  { key: "draft-box", label: "微信草稿箱", icon: RadioTower },
];

const systemTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "settings", label: "设置", icon: Settings },
  { key: "logs", label: "日志", icon: AlertCircle },
];

const pageMeta: Record<TabKey, { eyebrow: string; title: string }> = {
  overview: { eyebrow: "总览", title: "情报总览" },
  stream: { eyebrow: "信息获取", title: "原始素材流" },
  events: { eyebrow: "事件聚合", title: "热点事件列表" },
  alerts: { eyebrow: "趋势判断", title: "热点预警列表" },
  "source-health": { eyebrow: "来源巡检", title: "来源运行状态" },
  watchlist: { eyebrow: "深挖池", title: "待深挖的观察事件" },
  briefs: { eyebrow: "简报", title: "简报工作台" },
  "draft-box": { eyebrow: "微信草稿箱", title: "远端草稿与本地简报对照" },
  settings: { eyebrow: "系统配置", title: "AI 模型、信息源与系统偏好" },
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
  const [briefs, setBriefs] = useState<BriefItem[]>([]);
  const [selectedDeepDive, setSelectedDeepDive] = useState<EventDeepDive | null>(null);
  const [entityWatchlist, setEntityWatchlist] = useState<EntityWatchlistItem[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState<string>("all");
  const [publishTasks, setPublishTasks] = useState<PublishTask[]>([]);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [wechatMapping, setWechatMapping] = useState<WeChatMappingSnapshot | null>(null);
  const [wechatConfig, setWechatConfig] = useState<WeChatChannelConfig | null>(null);
  const [browserSession, setBrowserSession] = useState<BrowserSessionState | null>(null);
  const [referenceProjects, setReferenceProjects] = useState<ReferenceProject[]>([]);
  const [llmConfig, setLlmConfig] = useState<LLMConfig | null>(null);
  const [appSettings, setAppSettings] = useState<Record<string, unknown>>({});
  const [systemDoctor, setSystemDoctor] = useState<SystemDoctorResult | null>(null);
  const [appVersion, setAppVersion] = useState<AppVersionInfo | null>(null);
  const [updateInfo, setUpdateInfo] = useState<AppUpdateInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingChannel, setSavingChannel] = useState(false);
  const [savingLLMConfig, setSavingLLMConfig] = useState(false);
  const [refreshingSources, setRefreshingSources] = useState(false);
  const [savingSourceKey, setSavingSourceKey] = useState<string | null>(null);
  const [syncingSourceKey, setSyncingSourceKey] = useState<string | null>(null);
  const [busyEventId, setBusyEventId] = useState<string | null>(null);
  const [busyBriefId, setBusyBriefId] = useState<string | null>(null);
  const [refreshingBrowser, setRefreshingBrowser] = useState(false);
  const [openingBrowser, setOpeningBrowser] = useState(false);
  const [refreshingMapping, setRefreshingMapping] = useState(false);
  const [deletingRemoteId, setDeletingRemoteId] = useState<string | null>(null);
  const [busyRuntimeAction, setBusyRuntimeAction] = useState<"start" | "stop" | null>(null);
  const [busyMaintenanceIntent, setBusyMaintenanceIntent] = useState<RuntimeIntent | null>(null);
  const [savingRuntimePlan, setSavingRuntimePlan] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [pendingDeepDiveTitle, setPendingDeepDiveTitle] = useState<string | null>(null);
  const [pendingBriefTitle, setPendingBriefTitle] = useState<string | null>(null);

  const refreshIntelCore = useCallback(async () => {
    const [dashboardData, summaryData, streamData, eventData, alertData, sourceData, logData, publishTaskData, mappingData] = await Promise.all([
      api.getDashboard(),
      api.getIntelSummary(),
      api.getDiscoveryItems(),
      api.getIntelEvents(),
      api.getIntelAlerts(),
      api.getIntelSources(),
      api.getLogs(),
      api.getPublishTasks(),
      api.getWeChatMapping(),
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
    setLogs(logData.items);
    setPublishTasks(publishTaskData.items);
    setWechatMapping(mappingData.item);
    setBrowserSession(dashboardData.browser_session);
    setAppVersion(dashboardData.app_version);
    setUpdateInfo(dashboardData.update_info);
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
        briefData,
        entityWatchlistData,
        publishTaskData,
        logData,
        mappingData,
        channelData,
        browserData,
        referenceData,
        llmConfigData,
        settingsData,
        doctorData,
      ] = await Promise.all([
        api.getDashboard(),
        api.getIntelSummary(),
        api.getDiscoveryItems(),
        api.getIntelEvents(),
        api.getIntelAlerts(),
        api.getIntelSources(),
        api.getBriefs(),
        api.getEntityWatchlist(),
        api.getPublishTasks(),
        api.getLogs(),
        api.getWeChatMapping(),
        api.getWeChatConfig(),
        api.getBrowserSession(),
        api.getReferenceProjects(),
        api.getLLMConfig(),
        api.getSettings(),
        api.getSystemDoctor(),
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
      setBriefs(briefData.items);
      setEntityWatchlist(entityWatchlistData.items);
      setPublishTasks(publishTaskData.items);
      setLogs(logData.items);
      setWechatMapping(mappingData.item);
      setWechatConfig(channelData.item);
      setBrowserSession(browserData.item);
      setAppVersion(dashboardData.app_version);
      setUpdateInfo(dashboardData.update_info);
      setReferenceProjects(referenceData.items);
      setLlmConfig(llmConfigData.item);
      setAppSettings(settingsData.item);
      setSystemDoctor(doctorData.item);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "settings") {
      return;
    }
    const llmReady = Boolean(systemDoctor?.items.find((item) => item.key === "llm")?.ok);
    const wechatReady = Boolean(systemDoctor?.items.find((item) => item.key === "wechat_login")?.ok);
    if (!llmReady || !wechatReady) {
      setActiveTab("settings");
    }
  }, [systemDoctor, activeTab]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api.getSystemUpdate(true)
        .then((response) => {
          if (!cancelled) {
            setUpdateInfo(response.item);
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
  }, []);

  const handleCheckUpdate = useCallback(async () => {
    const response = await api.getSystemUpdate(true);
    setUpdateInfo(response.item);
    if (response.item.update_available && response.item.latest_version) {
      setToast(`发现新版本 ${response.item.latest_version}`);
    } else if (!response.item.error) {
      setToast("当前已经是最新版本");
    }
  }, []);

  const handleDismissUpdate = useCallback(async (version: string) => {
    const response = await api.dismissSystemUpdate(version);
    setUpdateInfo(response.item);
    setToast(`已忽略版本 ${version}`);
  }, []);

  useEffect(() => {
    const runtimeAwareTabs: TabKey[] = ["overview", "stream", "events", "alerts", "source-health", "watchlist", "draft-box", "logs"];
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

  async function handleDeepDiveEvent(eventId: string, force = false) {
    const sourceEvent = events.find((event) => event.id === eventId) ?? alerts.find((alert) => alert.event_id === eventId);
    setBusyEventId(eventId);
    setPendingDeepDiveTitle(sourceEvent?.title ?? "当前事件");
    try {
      const [deepDiveResponse, eventData, alertData, dashboardData] = await Promise.all([
        api.createEventDeepDive(eventId, force),
        api.getIntelEvents(),
        api.getIntelAlerts(),
        api.getDashboard(),
      ]);
      setSelectedDeepDive((current) => (current?.event_id === eventId ? deepDiveResponse.item : current));
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
      setActiveTab("watchlist");
      showToast(`正文深挖已完成：${sourceEvent?.title ?? "当前事件"}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "正文深挖失败");
    } finally {
      setBusyEventId(null);
      setPendingDeepDiveTitle(null);
    }
  }

  async function handleOpenDeepDive(eventId: string) {
    if (selectedDeepDive?.event_id === eventId) {
      setSelectedDeepDive(null);
      return;
    }
    try {
      const response = await api.getEventDeepDive(eventId);
      setSelectedDeepDive(response.item);
      setActiveTab("watchlist");
    } catch (err) {
      setError(err instanceof Error ? err.message : "正文深挖详情加载失败");
    }
  }

  async function handleCreateBrief(eventId: string) {
    const sourceEvent = events.find((event) => event.id === eventId) ?? alerts.find((alert) => alert.event_id === eventId);
    setBusyEventId(eventId);
    setPendingBriefTitle(sourceEvent?.title ?? "当前事件");
    try {
      const response = await api.createBriefFromEvent(eventId);
      const [briefData, eventData, alertData, dashboardData] = await Promise.all([
        api.getBriefs(),
        api.getIntelEvents(),
        api.getIntelAlerts(),
        api.getDashboard(),
      ]);
      setBriefs(briefData.items);
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
      setActiveTab("briefs");
      showToast(response.item.brief_level === "enhanced" ? `AI增强简报已生成：${response.item.title}` : `规则简报已生成：${response.item.title}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "简报生成失败");
    } finally {
      setBusyEventId(null);
      setPendingBriefTitle(null);
    }
  }

  async function handleBriefAction(kind: "sync" | "copy" | "copyPackage" | "refresh", brief: BriefItem) {
    setBusyBriefId(brief.id);
    try {
      if (kind === "sync") {
        const response = await api.syncBriefWeChatDraft(brief.id);
        await refreshAll();
        const deliveryStatus = response.item.delivery_status;
        const lastError = response.item.last_error;
        if (deliveryStatus === "verified" && !lastError) {
          showToast("已同步到微信草稿箱");
        } else if (lastError?.includes("无需重复上传")) {
          showToast("当前版本已同步，无需重复上传");
        } else {
          showToast("已处理微信草稿箱同步");
        }
        return;
      } else if (kind === "copy") {
        await navigator.clipboard.writeText(brief.wechat_markdown || brief.prompt_package_markdown);
        showToast("简报已复制");
      } else if (kind === "copyPackage") {
        const response = await api.copyBriefPackage(brief.id);
        await navigator.clipboard.writeText(response.markdown);
        showToast("来源包已复制");
      } else {
        await api.createBriefFromEvent(brief.event_id);
      }
      const [briefData, eventData, alertData, dashboardData] = await Promise.all([
        api.getBriefs(),
        api.getIntelEvents(),
        api.getIntelAlerts(),
        api.getDashboard(),
      ]);
      setBriefs(briefData.items);
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "简报动作执行失败");
    } finally {
      setBusyBriefId(null);
    }
  }

  async function handleDeleteBrief(brief: BriefItem) {
    const confirmed = window.confirm(
      brief.stage === "synced"
        ? `确定删除《${brief.title}》吗？这会默认尝试先删除微信草稿箱里的远端稿件，再删除本地简报。`
        : `确定删除《${brief.title}》吗？这会直接删除本地简报。`,
    );
    if (!confirmed) return;
    setBusyBriefId(brief.id);
    try {
      await api.deleteBrief(brief.id, "auto");
      await refreshAll();
      showToast("简报已删除");
    } catch (err) {
      setError(err instanceof Error ? err.message : "简报删除失败");
    } finally {
      setBusyBriefId(null);
    }
  }

  async function handleCopyBrief(brief: BriefItem) {
    await handleBriefAction("copy", brief);
  }

  async function handleCopyBriefPackage(briefId: string) {
    const brief = briefs.find((item) => item.id === briefId);
    if (!brief) return;
    await handleBriefAction("copyPackage", brief);
  }

  async function handleSaveChannel(payload: WeChatChannelConfig) {
    setSavingChannel(true);
    try {
      const [channelResult, browserResult, publishBackendsResult] = await Promise.all([
        api.updateWeChatConfig(payload),
        api.getBrowserSession(),
        api.getPublishBackends(),
      ]);
      setWechatConfig(channelResult.item);
      setBrowserSession(browserResult.item);
      setDashboard((current) =>
        current
          ? {
              ...current,
              browser_session: browserResult.item,
              publish_backends: publishBackendsResult.items,
            }
          : current,
      );
      showToast(`浏览器配置已保存：${channelResult.item.browser_name === "chrome" ? "Chrome" : "Edge"}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "渠道保存失败");
    } finally {
      setSavingChannel(false);
    }
  }

  async function handleSaveLLMConfig(config: LLMConfig, tavilyApiKey: string) {
    setSavingLLMConfig(true);
    try {
      const [llmResult, settingsResult] = await Promise.all([
        api.updateLLMConfig(config),
        api.updateSettings({ tavily_api_key: tavilyApiKey }),
      ]);
      setLlmConfig(llmResult.item);
      setAppSettings(settingsResult.item);
      showToast("AI 配置已保存");
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
      const doctor = await api.getSystemDoctor();
      setSystemDoctor(doctor.item);
      showToast("设置已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "设置保存失败");
    }
  }

  async function handleExportConfig() {
    try {
      const blob = await api.exportSystemConfig();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "auto-news-studio-config.json";
      anchor.click();
      URL.revokeObjectURL(url);
      showToast("配置已导出");
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出配置失败");
    }
  }

  async function handleExportBackup() {
    try {
      const blob = await api.exportSystemBackup();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "auto-news-studio-backup.zip";
      anchor.click();
      URL.revokeObjectURL(url);
      showToast("备份已导出");
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出备份失败");
    }
  }

  async function handleImportBackup(file: File) {
    try {
      const result = await api.importSystemBackup(file);
      await refreshAll();
      showToast(result.message || "备份已导入");
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入备份失败");
    }
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

  async function handleRefreshWeChatMapping() {
    setRefreshingMapping(true);
    try {
      const result = await api.refreshWeChatMapping();
      setWechatMapping(result.item);
      const browserData = await api.getBrowserSession();
      setBrowserSession(browserData.item);
      showToast(result.item.message || "公众号映射已刷新");
    } catch (err) {
      setError(err instanceof Error ? err.message : "公众号映射刷新失败");
    } finally {
      setRefreshingMapping(false);
    }
  }

  async function handleDeleteRemoteDraft(remoteId: string) {
    const confirmed = window.confirm("确定删除这个微信远端草稿吗？删除后不可恢复。");
    if (!confirmed) return;
    setDeletingRemoteId(remoteId);
    try {
      await api.deleteWeChatRemoteDraft(remoteId);
      await refreshAll();
      showToast("远端草稿已删除");
    } catch (err) {
      setError(err instanceof Error ? err.message : "远端草稿删除失败");
    } finally {
      setDeletingRemoteId(null);
    }
  }

  async function handleSyncBriefById(briefId: string) {
    const brief = briefs.find((item) => item.id === briefId);
    if (!brief) {
      setError("未找到对应简报，无法重新同步");
      return;
    }
    await handleBriefAction("sync", brief);
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
          <div className="toast-banner" onClick={dismissToast}>
            <CheckCircle size={14} />
            <span>{toast}</span>
            <X size={14} className="toast-dismiss" />
          </div>
        ) : null}

        {updateInfo?.update_available &&
        updateInfo.latest_version &&
        updateInfo.latest_version !== updateInfo.dismissed_version ? (
          <div className="update-banner">
            <div>
              <strong>发现新版本 {updateInfo.latest_version}</strong>
              <p>
                当前 {updateInfo.current_version}
                {updateInfo.published_at ? `，发布于 ${updateInfo.published_at}` : ""}
              </p>
            </div>
            <div className="update-banner-actions">
              <button
                type="button"
                className="ghost-button compact"
                onClick={() => window.open(updateInfo.release_url ?? updateInfo.release_notes_url ?? "", "_blank", "noopener,noreferrer")}
              >
                <ArrowUpRight size={14} />
                查看更新
              </button>
              <button type="button" className="ghost-button compact" onClick={() => void handleDismissUpdate(updateInfo.latest_version ?? "")}>
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
                onDeepDive={handleDeepDiveEvent}
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
                onSyncSources={handleSourceSync}
                onSyncSource={handleSourceSyncOne}
                onSaveSource={handleSourceSave}
              />
            ) : null}

            {activeTab === "watchlist" ? (
              <DeepDivePoolPanel
                items={events.filter((event) => (event.watchlisted || event.deep_dive_id || event.brief_id) && !event.ignored)}
                selectedDeepDive={selectedDeepDive}
                busyEventId={busyEventId}
                onDeepDive={handleDeepDiveEvent}
                onCreateBrief={handleCreateBrief}
                onOpenDeepDive={handleOpenDeepDive}
              />
            ) : null}

            {activeTab === "briefs" ? (
              <BriefTable
                briefs={briefs}
                busyBriefId={busyBriefId}
                onRefreshBrief={(eventId) => handleCreateBrief(eventId)}
                onCopyBrief={handleCopyBrief}
                onCopyPackage={handleCopyBriefPackage}
                onSyncBrief={(brief) => handleBriefAction("sync", brief)}
                onDeleteBrief={handleDeleteBrief}
              />
            ) : null}

            {activeTab === "draft-box" ? (
              <WeChatDraftBoxPanel
                mapping={wechatMapping}
                browserSession={browserSession}
                publishTasks={publishTasks}
                refreshing={refreshingMapping}
                deletingRemoteId={deletingRemoteId}
                onRefresh={handleRefreshWeChatMapping}
                onDeleteRemote={handleDeleteRemoteDraft}
                onSyncBrief={handleSyncBriefById}
              />
            ) : null}

            {activeTab === "settings" ? (
              <SettingsPanel
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
                onSyncSources={handleSourceSync}
                onSyncSource={handleSourceSyncOne}
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

            {activeTab === "logs" ? <LogsPanel logs={logs} runtime={dashboard.runtime_status} /> : null}
          </div>
        ) : null}
      </main>

    </div>
  );
}
