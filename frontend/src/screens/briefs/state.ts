import { useCallback, useRef, useState } from "react";

import { api } from "../../lib/api";
import type {
  AgentWorkflowItem,
  BriefItem,
  BriefRecordCounts,
  BriefStageCounts,
  EventDeepDive,
  IntelAlert,
  IntelEvent,
} from "../../types";

type BriefWorkbenchView = "all" | "local_only" | "draft_synced" | "published" | "exceptions";
type BriefWorkflowFilter = "all" | "traditional" | "agent";
type ToastTone = "success" | "info" | "warning";

interface UseBriefsStateParams {
  onError: (message: string) => void;
  onToast: (message: string, tone?: ToastTone) => void;
  onReloadOverview: (includeEntityWatchlist?: boolean) => Promise<void>;
  onReloadEvents: () => Promise<void>;
  onReloadAlerts: () => Promise<void>;
  onReloadWatchlist: () => Promise<void>;
  onReloadPublishHistory: () => Promise<void>;
  onReloadDraftBox: () => Promise<void>;
  onMarkBriefsLoaded: () => void;
  onActivateWatchlist: () => void;
  onActivateBriefs: () => void;
  getEventsSnapshot: () => IntelEvent[];
  getWatchlistSnapshot: () => IntelEvent[];
  getAlertsSnapshot: () => IntelAlert[];
}

export function useBriefsState({
  onError,
  onToast,
  onReloadOverview,
  onReloadEvents,
  onReloadAlerts,
  onReloadWatchlist,
  onReloadPublishHistory,
  onReloadDraftBox,
  onMarkBriefsLoaded,
  onActivateWatchlist,
  onActivateBriefs,
  getEventsSnapshot,
  getWatchlistSnapshot,
  getAlertsSnapshot,
}: UseBriefsStateParams) {
  const [briefs, setBriefs] = useState<BriefItem[]>([]);
  const [briefsPage, setBriefsPage] = useState(1);
  const [briefsPageSize, setBriefsPageSize] = useState(20);
  const [briefsTotal, setBriefsTotal] = useState(0);
  const [briefStageFilter, setBriefStageFilter] = useState<BriefWorkbenchView>("all");
  const [briefWorkflowFilter, setBriefWorkflowFilter] = useState<BriefWorkflowFilter>("all");
  const [briefSearchQuery, setBriefSearchQuery] = useState("");
  const [briefStageCounts, setBriefStageCounts] = useState<BriefStageCounts>({ all: 0, prepared: 0, synced: 0, failed: 0 });
  const [briefRecordCounts, setBriefRecordCounts] = useState<BriefRecordCounts>({
    all: 0,
    local_only: 0,
    draft_synced: 0,
    published: 0,
    exceptions: 0,
  });
  const [selectedDeepDive, setSelectedDeepDive] = useState<EventDeepDive | null>(null);
  const [busyEventId, setBusyEventId] = useState<string | null>(null);
  const [busyBriefId, setBusyBriefId] = useState<string | null>(null);
  const [pendingDeepDiveTitle, setPendingDeepDiveTitle] = useState<string | null>(null);
  const [pendingBriefTitle, setPendingBriefTitle] = useState<string | null>(null);
  const [agentWorkflows, setAgentWorkflows] = useState<AgentWorkflowItem[]>([]);
  const [loadingBriefDetailId, setLoadingBriefDetailId] = useState<string | null>(null);
  const [creatingDailyDigest, setCreatingDailyDigest] = useState(false);
  const [abandoningWorkflowId, setAbandoningWorkflowId] = useState<string | null>(null);
  const briefsLoadingRef = useRef(false);

  const loadBriefsData = useCallback(async (
    page = briefsPage,
    pageSize = briefsPageSize,
    stage = briefStageFilter,
    workflowMode = briefWorkflowFilter,
    query = briefSearchQuery,
  ) => {
    // In-flight guard: skip if already loading
    if (briefsLoadingRef.current) {
      return;
    }
    briefsLoadingRef.current = true;
    try {
      const [response, workflowResponse] = await Promise.all([
        api.getBriefs({
          page,
          page_size: pageSize,
          stage,
          workflow_mode: workflowMode,
          q: query,
        }),
        api.getAgentWorkflows(),
      ]);
      setBriefs(response.items);
      setBriefsPage(response.page);
      setBriefsPageSize(response.page_size);
      setBriefsTotal(response.total);
      setBriefStageCounts(response.stage_counts);
      setBriefRecordCounts(response.record_counts);
      setAgentWorkflows(workflowResponse.items);
    } finally {
      briefsLoadingRef.current = false;
    }
  }, [briefSearchQuery, briefStageFilter, briefWorkflowFilter, briefsPage, briefsPageSize]);

  const handleDeepDiveEvent = useCallback(async (eventId: string, force = false) => {
    const sourceEvent =
      getEventsSnapshot().find((event) => event.id === eventId)
      ?? getWatchlistSnapshot().find((event) => event.id === eventId)
      ?? getAlertsSnapshot().find((alert) => alert.event_id === eventId);
    setBusyEventId(eventId);
    setPendingDeepDiveTitle(sourceEvent?.title ?? "当前事件");
    try {
      const deepDiveResponse = await api.createEventDeepDive(eventId, force);
      setSelectedDeepDive((current) => (current?.event_id === eventId ? deepDiveResponse.item : current));
      await Promise.all([
        onReloadOverview(true),
        onReloadEvents(),
        onReloadWatchlist(),
        onReloadAlerts(),
      ]);
      onActivateWatchlist();
      onToast(`正文深挖已完成：${sourceEvent?.title ?? "当前事件"}`, "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "正文深挖失败");
    } finally {
      setBusyEventId(null);
      setPendingDeepDiveTitle(null);
    }
  }, [getAlertsSnapshot, getEventsSnapshot, getWatchlistSnapshot, onActivateWatchlist, onError, onReloadAlerts, onReloadEvents, onReloadOverview, onReloadWatchlist, onToast]);

  const handleOpenDeepDive = useCallback(async (eventId: string) => {
    if (selectedDeepDive?.event_id === eventId) {
      setSelectedDeepDive(null);
      return;
    }
    try {
      const response = await api.getEventDeepDive(eventId);
      setSelectedDeepDive(response.item);
      onActivateWatchlist();
    } catch (err) {
      onError(err instanceof Error ? err.message : "正文深挖详情加载失败");
    }
  }, [onActivateWatchlist, onError, selectedDeepDive?.event_id]);

  const handleCreateBrief = useCallback(async (eventId: string) => {
    const sourceEvent =
      getEventsSnapshot().find((event) => event.id === eventId)
      ?? getWatchlistSnapshot().find((event) => event.id === eventId)
      ?? getAlertsSnapshot().find((alert) => alert.event_id === eventId);
    setBusyEventId(eventId);
    setPendingBriefTitle(sourceEvent?.title ?? "当前事件");
    try {
      const response = await api.createBriefFromEvent(eventId);
      await Promise.all([
        onReloadOverview(true),
        loadBriefsData(),
        onReloadEvents(),
        onReloadWatchlist(),
        onReloadAlerts(),
      ]);
      onActivateBriefs();
      onMarkBriefsLoaded();
      onToast(
        response.item.brief_level === "article"
          ? `AI文章已生成：${response.item.title}`
          : response.item.brief_level === "enhanced"
            ? `AI增强简报已生成：${response.item.title}`
            : `规则简报已生成：${response.item.title}`,
        "success",
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : "简报生成失败");
    } finally {
      setBusyEventId(null);
      setPendingBriefTitle(null);
    }
  }, [getAlertsSnapshot, getEventsSnapshot, getWatchlistSnapshot, loadBriefsData, onActivateBriefs, onError, onMarkBriefsLoaded, onReloadAlerts, onReloadEvents, onReloadOverview, onReloadWatchlist, onToast]);

  const handleCreateDailyDigestBrief = useCallback(async () => {
    setCreatingDailyDigest(true);
    try {
      const response = await api.createDailyDigestBrief("dashboard");
      await Promise.all([
        onReloadOverview(true),
        loadBriefsData(),
        onReloadEvents(),
        onReloadWatchlist(),
        onReloadAlerts(),
      ]);
      onActivateBriefs();
      onMarkBriefsLoaded();
      onToast(`今日速递已生成：${response.item.title}`, "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "今日速递生成失败");
    } finally {
      setCreatingDailyDigest(false);
    }
  }, [loadBriefsData, onActivateBriefs, onError, onMarkBriefsLoaded, onReloadAlerts, onReloadEvents, onReloadOverview, onReloadWatchlist, onToast]);

  const handleAbandonAgentWorkflow = useCallback(async (workflowSessionId: string) => {
    setAbandoningWorkflowId(workflowSessionId);
    try {
      await api.abandonAgentWorkflow(workflowSessionId);
      await Promise.all([
        onReloadOverview(false),
        loadBriefsData(),
      ]);
      onToast("已放弃 Agent 会话", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "Agent 会话放弃失败");
    } finally {
      setAbandoningWorkflowId(null);
    }
  }, [loadBriefsData, onError, onReloadOverview, onToast]);

  const handleBriefAction = useCallback(async (kind: "sync" | "publish" | "copy" | "copyPackage" | "refresh", brief: BriefItem) => {
    setBusyBriefId(brief.id);
    try {
      if (kind === "sync") {
        const response = await api.syncBriefWeChatDraft(brief.id);
        await Promise.all([
          onReloadOverview(false),
          loadBriefsData(),
          onReloadPublishHistory(),
          onReloadDraftBox(),
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
        return;
      }
      if (kind === "publish") {
        const response = await api.publishBriefWeChatArticle(brief.id);
        await Promise.all([
          onReloadOverview(false),
          loadBriefsData(),
          onReloadPublishHistory(),
          onReloadDraftBox(),
        ]);
        if (response.item.record_exception === "pending_confirmation") {
          onToast("已到微信验证二维码，请扫码确认", "warning");
        } else {
          onToast("已执行微信发表路径", "success");
        }
        return;
      }
      if (kind === "copy") {
        await navigator.clipboard.writeText(brief.wechat_markdown || brief.prompt_package_markdown);
        onToast("简报已复制", "success");
        return;
      }
      if (kind === "copyPackage") {
        const response = await api.copyBriefPackage(brief.id);
        await navigator.clipboard.writeText(response.markdown);
        onToast("来源包已复制", "success");
        return;
      }
      await api.createBriefFromEvent(brief.event_id);
      await Promise.all([
        onReloadOverview(true),
        loadBriefsData(),
        onReloadEvents(),
        onReloadAlerts(),
      ]);
    } catch (err) {
      onError(err instanceof Error ? err.message : "简报动作执行失败");
    } finally {
      setBusyBriefId(null);
    }
  }, [loadBriefsData, onError, onReloadAlerts, onReloadDraftBox, onReloadEvents, onReloadOverview, onReloadPublishHistory, onToast]);

  const handleDeleteBrief = useCallback(async (brief: BriefItem) => {
    const confirmed = window.confirm(
      brief.record_status === "draft_synced"
        ? `确定删除《${brief.title}》吗？这会默认尝试先删除微信草稿箱里的远端稿件，再删除本地简报。`
        : `确定删除《${brief.title}》吗？这会直接删除本地简报。`,
    );
    if (!confirmed) return;
    setBusyBriefId(brief.id);
    try {
      await api.deleteBrief(brief.id, "auto");
      await Promise.all([
        onReloadOverview(true),
        loadBriefsData(),
        onReloadDraftBox(),
        onReloadPublishHistory(),
      ]);
      onToast("简报已删除", "success");
    } catch (err) {
      onError(err instanceof Error ? err.message : "简报删除失败");
    } finally {
      setBusyBriefId(null);
    }
  }, [loadBriefsData, onError, onReloadDraftBox, onReloadOverview, onReloadPublishHistory, onToast]);

  const handleCopyBrief = useCallback(async (brief: BriefItem) => {
    await handleBriefAction("copy", brief);
  }, [handleBriefAction]);

  const loadBriefDetail = useCallback(async (briefId: string) => {
    setLoadingBriefDetailId(briefId);
    try {
      const response = await api.getBrief(briefId);
      setBriefs((current) => current.map((item) => (item.id === briefId ? response.item : item)));
      return response.item;
    } catch (err) {
      onError(err instanceof Error ? err.message : "简报详情加载失败");
      return null;
    } finally {
      setLoadingBriefDetailId((current) => (current === briefId ? null : current));
    }
  }, [onError]);

  const handleCopyBriefPackage = useCallback(async (briefId: string) => {
    const brief = briefs.find((item) => item.id === briefId);
    if (!brief) return;
    await handleBriefAction("copyPackage", brief);
  }, [briefs, handleBriefAction]);

  return {
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
    briefStageCounts,
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
    setSelectedDeepDive,
  };
}
