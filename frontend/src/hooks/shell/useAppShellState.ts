import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAdaptivePolling } from "../../hooks/shared/useAdaptivePolling";
import { pageMeta, type TabKey } from "../../navigation/tabs";
import type { LogItem, SchedulerStatus } from "../../types";

export type ToastTone = "success" | "info" | "warning";

export interface ToastState {
  id: number;
  message: string;
  tone: ToastTone;
}

const BROWSER_REFRESH_TABS: TabKey[] = [];
type LogLevelFilter = "all" | "info" | "warning" | "error";

function shouldSurfaceBackgroundLog(log: LogItem): boolean {
  if (log.stream !== "business_event" || log.category !== "browser") {
    return false;
  }
  if (log.actor !== "dashboard" && log.actor !== "scheduler" && log.actor !== "runtime_start") {
    return false;
  }
  return (
    log.message.includes("已检查微信草稿箱")
    || log.message.includes("已检查微信发表记录")
    || log.message.includes("本次检查失败")
  );
}

function toastToneForLog(log: LogItem): ToastTone {
  if (log.level === "warning" || log.level === "error") {
    return "warning";
  }
  return "info";
}

export type BriefWorkbenchView = "all" | "local_only" | "draft_synced" | "published" | "exceptions";
export type BriefWorkflowFilter = "all" | "traditional" | "agent";
export type ShellLogLevelFilter = LogLevelFilter;

interface UseAppShellStateParams {
  activeTab: TabKey;
  dashboardRecentLogs: LogItem[] | undefined;
  runtimeStatus: SchedulerStatus | null;
  runtimeAwareTabs: TabKey[];
  loadBriefsData: (page?: number, pageSize?: number, stage?: BriefWorkbenchView, workflowMode?: BriefWorkflowFilter, query?: string) => Promise<unknown>;
  loadLogsData: (page?: number, pageSize?: number, level?: LogLevelFilter, query?: string) => Promise<unknown>;
  loadTabDataImpl: (tab: TabKey, options: { forceBrowserRefresh: boolean }) => Promise<void>;
  refreshOverviewData: (includeEntityWatchlist?: boolean, lite?: boolean) => Promise<void>;
  onError: (message: string | null) => void;
}

export function useAppShellState({
  activeTab,
  dashboardRecentLogs,
  runtimeStatus,
  runtimeAwareTabs,
  loadBriefsData,
  loadLogsData,
  loadTabDataImpl,
  refreshOverviewData,
  onError,
}: UseAppShellStateParams) {
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [tabLoading, setTabLoading] = useState<Partial<Record<TabKey, boolean>>>({});
  const [loadedTabs, setLoadedTabs] = useState<Record<TabKey, boolean>>({
    overview: true,
    stream: false,
    events: false,
    alerts: false,
    "source-health": false,
    analysis: false,
    watchlist: false,
    briefs: false,
    "publish-history": false,
    "draft-box": false,
    settings: false,
    logs: false,
  });

  const toastSeqRef = useRef(0);
  const lastBackgroundToastKeyRef = useRef("");
  const hasSeenInitialBackgroundLogsRef = useRef(false);

  const showToast = useCallback((message: string, tone: ToastTone = "success") => {
    toastSeqRef.current += 1;
    setToast({ id: toastSeqRef.current, message, tone });
  }, []);

  const markTabLoaded = useCallback((tab: TabKey) => {
    setLoadedTabs((current) => (current[tab] ? current : { ...current, [tab]: true }));
  }, []);

  const loadTabData = useCallback(async (
    tab: TabKey,
    options: { markLoaded?: boolean; forceBrowserRefresh?: boolean } = {},
  ) => {
    const { markLoaded: shouldMarkLoaded = true, forceBrowserRefresh = false } = options;
    setTabLoading((current) => current[tab] ? current : { ...current, [tab]: true });
    try {
      await loadTabDataImpl(tab, { forceBrowserRefresh });
      if (shouldMarkLoaded) {
        markTabLoaded(tab);
      }
    } finally {
      setTabLoading((current) => !current[tab] ? current : { ...current, [tab]: false });
    }
  }, [loadTabDataImpl, markTabLoaded]);

  const refreshAll = useCallback(async (options: { refreshActiveTab?: boolean; forceBrowserRefresh?: boolean } = {}) => {
    const { refreshActiveTab = true, forceBrowserRefresh = false } = options;
    setLoading(true);
    onError(null);
    try {
      await refreshOverviewData(true);
      if (refreshActiveTab && activeTab !== "overview") {
        await loadTabData(activeTab, { markLoaded: true, forceBrowserRefresh });
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [activeTab, loadTabData, onError, refreshOverviewData]);

  const pollActiveTabData = useCallback(async () => {
    try {
      if (activeTab === "overview") {
        await refreshOverviewData(false, true);
        return;
      }
      await loadTabDataImpl(activeTab, { forceBrowserRefresh: false });
    } catch (err) {
      onError(err instanceof Error ? err.message : "自动刷新失败");
    }
  }, [activeTab, loadTabDataImpl, onError, refreshOverviewData]);

  useAdaptivePolling(
    activeTab,
    runtimeStatus,
    pollActiveTabData,
    runtimeAwareTabs.includes(activeTab),
  );

  useEffect(() => {
    const newestLog = dashboardRecentLogs?.find(shouldSurfaceBackgroundLog);
    if (!newestLog) {
      return;
    }
    const toastKey = `${newestLog.id}:${newestLog.created_at}`;
    if (!hasSeenInitialBackgroundLogsRef.current) {
      hasSeenInitialBackgroundLogsRef.current = true;
      lastBackgroundToastKeyRef.current = toastKey;
      return;
    }
    if (lastBackgroundToastKeyRef.current === toastKey) {
      return;
    }
    lastBackgroundToastKeyRef.current = toastKey;
    showToast(newestLog.message, toastToneForLog(newestLog));
  }, [dashboardRecentLogs, showToast]);

  useEffect(() => {
    if (loadedTabs[activeTab]) {
      return;
    }
    void loadTabData(activeTab, {
      markLoaded: true,
      forceBrowserRefresh: BROWSER_REFRESH_TABS.includes(activeTab),
    }).catch((err: unknown) => {
      onError(err instanceof Error ? err.message : "页面数据加载失败");
    });
  }, [activeTab, loadedTabs, loadTabData, onError]);

  const reloadBriefsForActiveTab = useCallback(async (pageSize: number, stage: BriefWorkbenchView, workflowMode: BriefWorkflowFilter, query: string) => {
    if (!loadedTabs.briefs || activeTab !== "briefs") {
      return;
    }
    setTabLoading((current) => ({ ...current, briefs: true }));
    try {
      await loadBriefsData(1, pageSize, stage, workflowMode, query);
    } catch (err) {
      onError(err instanceof Error ? err.message : "简报加载失败");
    } finally {
      setTabLoading((current) => ({ ...current, briefs: false }));
    }
  }, [activeTab, loadBriefsData, loadedTabs.briefs, onError]);

  const reloadLogsForActiveTab = useCallback(async (
    pageSize: number,
    level: LogLevelFilter,
    query: string,
  ) => {
    if (!loadedTabs.logs || activeTab !== "logs") {
      return;
    }
    setTabLoading((current) => ({ ...current, logs: true }));
    try {
      await loadLogsData(1, pageSize, level, query);
    } catch (err) {
      onError(err instanceof Error ? err.message : "日志加载失败");
    } finally {
      setTabLoading((current) => ({ ...current, logs: false }));
    }
  }, [activeTab, loadLogsData, loadedTabs.logs, onError]);

  useEffect(() => {
    if (!toast) {
      return;
    }
    const timer = window.setTimeout(() => {
      setToast((current) => (current?.id === toast.id ? null : current));
    }, 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const currentPageMeta = useMemo(() => pageMeta[activeTab], [activeTab]);

  const dismissToast = useCallback(() => {
    setToast(null);
  }, []);

  return {
    loading,
    toast,
    tabLoading,
    setTabLoading,
    loadedTabs,
    showToast,
    markTabLoaded,
    loadTabData,
    refreshAll,
    pollActiveTabData,
    reloadBriefsForActiveTab,
    reloadLogsForActiveTab,
    currentPageMeta,
    dismissToast,
  };
}
