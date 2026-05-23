import { useCallback, useEffect, useState } from "react";

import { api } from "../../lib/api";
import type {
  BrowserSessionState,
  WeChatMappingSnapshot,
  WeChatPublishHistorySnapshot,
  PublishTask,
} from "../../types";

type ToastTone = "success" | "info" | "warning";

interface UseWechatStateParams {
  browserSession: BrowserSessionState | null;
  onBrowserSessionChange: (session: BrowserSessionState | null) => void;
  initialWechatMapping?: WeChatMappingSnapshot | null;
  initialWechatPublishHistory?: WeChatPublishHistorySnapshot | null;
  initialPublishTasks?: PublishTask[];
  initialPublishTasksPage?: number;
  initialPublishTasksPageSize: number;
  initialPublishTasksTotal?: number;
  onError: (message: string) => void;
  onToast: (message: string, tone?: ToastTone) => void;
  onReloadBriefs: () => Promise<void>;
  onReloadOverview: (includeEntityWatchlist?: boolean) => Promise<void>;
}

export function useWechatState({
  browserSession,
  onBrowserSessionChange,
  initialWechatMapping = null,
  initialWechatPublishHistory = null,
  initialPublishTasks = [],
  initialPublishTasksPage = 1,
  initialPublishTasksPageSize,
  initialPublishTasksTotal = 0,
  onError,
  onToast,
  onReloadBriefs,
  onReloadOverview,
}: UseWechatStateParams) {
  const [wechatMapping, setWechatMapping] = useState<WeChatMappingSnapshot | null>(initialWechatMapping);
  const [wechatPublishHistory, setWechatPublishHistory] = useState<WeChatPublishHistorySnapshot | null>(initialWechatPublishHistory);
  const [publishTasks, setPublishTasks] = useState<PublishTask[]>(initialPublishTasks);
  const [publishTasksPage, setPublishTasksPage] = useState(initialPublishTasksPage);
  const [publishTasksPageSize, setPublishTasksPageSize] = useState(initialPublishTasksPageSize);
  const [publishTasksTotal, setPublishTasksTotal] = useState(initialPublishTasksTotal);
  const [refreshingMapping, setRefreshingMapping] = useState(false);
  const [refreshingPublishHistory, setRefreshingPublishHistory] = useState(false);
  const [deletingRemoteId, setDeletingRemoteId] = useState<string | null>(null);

  useEffect(() => {
    const latestHistory = browserSession?.last_publish_history_check ?? null;
    if (!latestHistory) return;
    setWechatPublishHistory((current) => current ?? latestHistory);
  }, [browserSession?.last_publish_history_check]);

  const loadPublishHistoryData = useCallback(async (
    forceBrowserRefresh = true,
    page = publishTasksPage,
    pageSize = publishTasksPageSize,
  ) => {
    const [publishTaskData, historyData, browserData] = await Promise.all([
      api.getPublishTasks({ page, page_size: pageSize }),
      forceBrowserRefresh ? api.checkWeChatPublishHistory() : Promise.resolve({ item: wechatPublishHistory }),
      api.getBrowserSession(),
    ]);
    setPublishTasks(publishTaskData.items);
    setPublishTasksPage(publishTaskData.page);
    setPublishTasksPageSize(publishTaskData.page_size);
    setPublishTasksTotal(publishTaskData.total);
    if (historyData.item) {
      setWechatPublishHistory(historyData.item);
    }
    onBrowserSessionChange(browserData.item);
  }, [onBrowserSessionChange, publishTasksPage, publishTasksPageSize, wechatPublishHistory]);

  const loadDraftBoxData = useCallback(async (
    forceBrowserRefresh = true,
    page = publishTasksPage,
    pageSize = publishTasksPageSize,
  ) => {
    if (forceBrowserRefresh) {
      await api.checkWeChatDraftBox();
    }
    const [mappingData, publishTaskData, browserData] = await Promise.all([
      api.getWeChatMapping(),
      api.getPublishTasks({ page, page_size: pageSize }),
      api.getBrowserSession(),
    ]);
    setWechatMapping(mappingData.item);
    setPublishTasks(publishTaskData.items);
    setPublishTasksPage(publishTaskData.page);
    setPublishTasksPageSize(publishTaskData.page_size);
    setPublishTasksTotal(publishTaskData.total);
    onBrowserSessionChange(browserData.item);
  }, [onBrowserSessionChange, publishTasksPage, publishTasksPageSize]);

  const refreshBrowserSession = useCallback(async () => {
    const response = await api.getBrowserSession();
    onBrowserSessionChange(response.item);
    return response.item;
  }, [onBrowserSessionChange]);

  const handleRefreshWeChatMapping = useCallback(async () => {
    setRefreshingMapping(true);
    try {
      const result = await api.refreshWeChatMapping();
      setWechatMapping(result.item);
      await Promise.all([
        onReloadBriefs(),
        refreshBrowserSession(),
      ]);
      onToast(result.item.message || "公众号映射已刷新", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "公众号映射刷新失败");
    } finally {
      setRefreshingMapping(false);
    }
  }, [onError, onReloadBriefs, onToast, refreshBrowserSession]);

  const handleRefreshWeChatPublishHistory = useCallback(async () => {
    setRefreshingPublishHistory(true);
    try {
      const result = await api.checkWeChatPublishHistory();
      setWechatPublishHistory(result.item);
      await Promise.all([
        onReloadBriefs(),
        refreshBrowserSession(),
      ]);
      onToast(result.item.message || "发表记录已刷新", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "发表记录刷新失败");
    } finally {
      setRefreshingPublishHistory(false);
    }
  }, [onError, onReloadBriefs, onToast, refreshBrowserSession]);

  const handleDeleteRemoteDraft = useCallback(async (remoteId: string) => {
    const confirmed = window.confirm("确定删除这个微信远端草稿吗？删除后不可恢复。");
    if (!confirmed) return;
    setDeletingRemoteId(remoteId);
    try {
      await api.deleteWeChatRemoteDraft(remoteId);
      await Promise.all([
        loadDraftBoxData(false),
        onReloadBriefs(),
        onReloadOverview(false),
      ]);
      onToast("远端草稿已删除", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "远端草稿删除失败");
    } finally {
      setDeletingRemoteId(null);
    }
  }, [loadDraftBoxData, onError, onReloadBriefs, onReloadOverview, onToast]);

  const handleSyncBriefById = useCallback(async (briefId: string) => {
    try {
      const response = await api.syncBriefWeChatDraft(briefId);
      await Promise.all([
        onReloadOverview(false),
        onReloadBriefs(),
        loadPublishHistoryData(false),
        loadDraftBoxData(false),
      ]);
      const deliveryStatus = response.item.delivery_status;
      const lastError = response.item.last_error;
      if (deliveryStatus === "verified" && !lastError) {
        onToast("已同步到微信草稿箱", "success");
      } else if (lastError?.includes("无需重复上传")) {
        onToast("当前版本已同步，无需重复上传", "info");
      } else {
        onToast("已处理微信草稿箱同步", "success");
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "未找到对应简报，无法重新同步");
    }
  }, [loadDraftBoxData, loadPublishHistoryData, onError, onReloadBriefs, onReloadOverview, onToast]);

  return {
    browserSession,
    wechatMapping,
    setWechatMapping,
    wechatPublishHistory,
    setWechatPublishHistory,
    publishTasks,
    setPublishTasks,
    publishTasksPage,
    setPublishTasksPage,
    publishTasksPageSize,
    setPublishTasksPageSize,
    publishTasksTotal,
    setPublishTasksTotal,
    refreshingMapping,
    refreshingPublishHistory,
    deletingRemoteId,
    loadPublishHistoryData,
    loadDraftBoxData,
    refreshBrowserSession,
    handleRefreshWeChatMapping,
    handleRefreshWeChatPublishHistory,
    handleDeleteRemoteDraft,
    handleSyncBriefById,
  };
}
