import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type {
  AppUpdateInfo,
  AppVersionInfo,
  BrowserSessionState,
  LLMConfig,
  LogItem,
  ReferenceProject,
  SourceConnector,
  SystemDoctorResult,
  WeChatChannelConfig,
} from "../../types";

type ToastTone = "success" | "info" | "warning";

interface UseSettingsStateParams {
  initialLogsPageSize: number;
  browserSession: BrowserSessionState | null;
  onBrowserSessionChange: (session: BrowserSessionState | null) => void;
  updateInfo: AppUpdateInfo | null;
  onUpdateInfoChange: (value: AppUpdateInfo | null) => void;
  onError: (message: string) => void;
  onToast: (message: string, tone?: ToastTone) => void;
  onReloadOverview: (includeEntityWatchlist?: boolean) => Promise<void>;
  onLoadSources: () => Promise<SourceConnector[]>;
}

export function useSettingsState({
  initialLogsPageSize,
  browserSession,
  onBrowserSessionChange,
  updateInfo,
  onUpdateInfoChange,
  onError,
  onToast,
  onReloadOverview,
  onLoadSources,
}: UseSettingsStateParams) {
  const [wechatConfig, setWechatConfig] = useState<WeChatChannelConfig | null>(null);
  const [referenceProjects, setReferenceProjects] = useState<ReferenceProject[]>([]);
  const [llmConfig, setLlmConfig] = useState<LLMConfig | null>(null);
  const [appSettings, setAppSettings] = useState<Record<string, unknown>>({});
  const [systemDoctor, setSystemDoctor] = useState<SystemDoctorResult | null>(null);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [logsPage, setLogsPage] = useState(1);
  const [logsPageSize, setLogsPageSize] = useState(initialLogsPageSize);
  const [logsTotal, setLogsTotal] = useState(0);
  const [logLevelFilter, setLogLevelFilter] = useState<"all" | "info" | "warning" | "error">("all");
  const [logSearchQuery, setLogSearchQuery] = useState("");
  const [savingChannel, setSavingChannel] = useState(false);
  const [savingLLMConfig, setSavingLLMConfig] = useState(false);
  const [refreshingBrowser, setRefreshingBrowser] = useState(false);
  const [openingBrowser, setOpeningBrowser] = useState(false);

  const loadSettingsData = useCallback(async () => {
    const [channelData, browserData, referenceData, llmConfigData, settingsData, doctorData, sourceData] = await Promise.all([
      api.getWeChatConfig(),
      api.getBrowserSession(),
      api.getReferenceProjects(),
      api.getLLMConfig(),
      api.getSettings(),
      api.getSystemDoctor(),
      onLoadSources(),
    ]);
    setWechatConfig(channelData.item);
    onBrowserSessionChange(browserData.item);
    setReferenceProjects(referenceData.items);
    setLlmConfig(llmConfigData.item);
    setAppSettings(settingsData.item);
    setSystemDoctor(doctorData.item);
    return sourceData;
  }, [onBrowserSessionChange, onLoadSources]);

  const loadLogsData = useCallback(async (
    page = logsPage,
    pageSize = logsPageSize,
    level = logLevelFilter,
    query = logSearchQuery,
  ) => {
    const response = await api.getLogs({
      page,
      page_size: pageSize,
      level,
      q: query,
    });
    setLogs(response.items);
    setLogsPage(response.page);
    setLogsPageSize(response.page_size);
    setLogsTotal(response.total);
  }, [logLevelFilter, logSearchQuery, logsPage, logsPageSize]);

  const loadUpdateInfo = useCallback(async (force = false) => {
    const response = await api.getSystemUpdate(force);
    onUpdateInfoChange(response.item);
    return response.item;
  }, [onUpdateInfoChange]);

  const handleCheckUpdate = useCallback(async () => {
    try {
      const item = await loadUpdateInfo(true);
      if (item.update_available && item.latest_version) {
        onToast(`发现新版本 ${item.latest_version}`, "info");
      } else if (!item.error) {
        onToast("当前已经是最新版本", "info");
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "检查更新失败");
    }
  }, [loadUpdateInfo, onError, onToast]);

  const handleDismissUpdate = useCallback(async (version: string) => {
    try {
      const response = await api.dismissSystemUpdate(version);
      onUpdateInfoChange(response.item);
      onToast(`已忽略版本 ${version}`, "info");
    } catch (err) {
      onError(err instanceof Error ? err.message : "忽略版本失败");
    }
  }, [onError, onToast, onUpdateInfoChange]);

  const handleSaveChannel = useCallback(async (payload: WeChatChannelConfig) => {
    setSavingChannel(true);
    try {
      const [channelResult, browserResult] = await Promise.all([
        api.updateWeChatConfig(payload),
        api.getBrowserSession(),
      ]);
      setWechatConfig(channelResult.item);
      onBrowserSessionChange(browserResult.item);
      await onReloadOverview(false);
      onToast(`浏览器配置已保存：${channelResult.item.browser_name === "chrome" ? "Chrome" : "Edge"}`, "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "渠道保存失败");
    } finally {
      setSavingChannel(false);
    }
  }, [onBrowserSessionChange, onError, onReloadOverview, onToast]);

  const handleSaveLLMConfig = useCallback(async (config: LLMConfig, tavilyApiKey: string) => {
    setSavingLLMConfig(true);
    try {
      const [llmResult, settingsResult] = await Promise.all([
        api.updateLLMConfig(config),
        api.updateSettings({ tavily_api_key: tavilyApiKey }),
      ]);
      setLlmConfig(llmResult.item);
      setAppSettings(settingsResult.item);
      onToast("AI 配置已保存", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "AI 模型配置保存失败");
    } finally {
      setSavingLLMConfig(false);
    }
  }, [onError, onToast]);

  const handleSaveSettings = useCallback(async (payload: Record<string, unknown>) => {
    try {
      const result = await api.updateSettings(payload);
      setAppSettings(result.item);
      const doctor = await api.getSystemDoctor();
      setSystemDoctor(doctor.item);
      onToast("设置已保存", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "设置保存失败");
    }
  }, [onError, onToast]);

  const handleExportConfig = useCallback(async () => {
    try {
      const blob = await api.exportSystemConfig();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "auto-news-studio-config.json";
      anchor.click();
      URL.revokeObjectURL(url);
      onToast("配置已导出", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "导出配置失败");
    }
  }, [onError, onToast]);

  const handleExportBackup = useCallback(async () => {
    try {
      const blob = await api.exportSystemBackup();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "auto-news-studio-backup.zip";
      anchor.click();
      URL.revokeObjectURL(url);
      onToast("备份已导出", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "导出备份失败");
    }
  }, [onError, onToast]);

  const handleRefreshBrowser = useCallback(async (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => {
    setRefreshingBrowser(true);
    try {
      await api.updateBrowserSession(payload);
      await api.checkWeChatBrowserSession();
      await loadSettingsData();
      await onReloadOverview(false);
    } catch (err) {
      onError(err instanceof Error ? err.message : "浏览器会话刷新失败");
    } finally {
      setRefreshingBrowser(false);
    }
  }, [loadSettingsData, onError, onReloadOverview]);

  const handleOpenBrowserDashboard = useCallback(async (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => {
    setOpeningBrowser(true);
    try {
      await api.updateBrowserSession(payload);
      await api.openWeChatDashboard();
      await loadSettingsData();
      await onReloadOverview(false);
    } catch (err) {
      onError(err instanceof Error ? err.message : "打开公众号后台失败");
    } finally {
      setOpeningBrowser(false);
    }
  }, [loadSettingsData, onError, onReloadOverview]);

  return {
    browserSession,
    wechatConfig,
    referenceProjects,
    llmConfig,
    appSettings,
    systemDoctor,
    updateInfo,
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
    savingChannel,
    savingLLMConfig,
    refreshingBrowser,
    openingBrowser,
    loadSettingsData,
    loadLogsData,
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
  };
}
