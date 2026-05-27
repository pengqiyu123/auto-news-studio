import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import { pickNewerRuntimeStatus, RUNTIME_INTENT_LABELS } from "../../lib/runtimeIntent";
import type { AgentWorkflowItem, AutomationMode, DashboardResponse, IntelOverviewSummary, RuntimeIntent, RuntimePlan } from "../../types";

type ToastTone = "success" | "info" | "warning";

interface UseRuntimeStateParams {
  runtimePlan?: RuntimePlan | null;
  onDashboardChange: React.Dispatch<React.SetStateAction<DashboardResponse | null>>;
  onSummaryChange: React.Dispatch<React.SetStateAction<IntelOverviewSummary | null>>;
  onReloadOverview: (includeEntityWatchlist?: boolean) => Promise<void>;
  onRefreshAll: (options?: { refreshActiveTab?: boolean; forceBrowserRefresh?: boolean }) => Promise<void>;
  onError: (message: string) => void;
  onToast: (message: string, tone?: ToastTone) => void;
}

export function useRuntimeState({
  runtimePlan,
  onDashboardChange,
  onSummaryChange,
  onReloadOverview,
  onRefreshAll,
  onError,
  onToast,
}: UseRuntimeStateParams) {
  const [busyRuntimeAction, setBusyRuntimeAction] = useState<"start" | "stop" | null>(null);
  const [busyMaintenanceIntent, setBusyMaintenanceIntent] = useState<RuntimeIntent | null>(null);
  const [savingRuntimePlan, setSavingRuntimePlan] = useState(false);

  const pollRuntimeStatus = useCallback(async () => {
    try {
      const res = await api.getRuntimeStatus();
      onDashboardChange((current) =>
        current ? { ...current, runtime_status: pickNewerRuntimeStatus(current.runtime_status, res.item) ?? res.item } : current
      );
    } catch {
      // Keep runtime heartbeat polling silent.
    }
  }, [onDashboardChange]);

  const handleStartRuntime = useCallback(async () => {
    setBusyRuntimeAction("start");
    try {
      if (runtimePlan?.effective_mode === "automated" && ["immediate", "scheduled_batch"].includes(runtimePlan.delivery_mode)) {
        const workflowResponse = await api.getAgentWorkflows();
        const unfinished = workflowResponse.items.filter((item: AgentWorkflowItem) => item.status === "running" || item.status === "failed");
        if (unfinished.length) {
          throw new Error("当前存在未完成的 Agent 会话，请先完成或明确放弃后，再启动计划上传。");
        }
      }
      const response = await api.startRuntime();
      onDashboardChange((current) =>
        current ? { ...current, runtime_status: pickNewerRuntimeStatus(current.runtime_status, response.item) ?? response.item } : current
      );
      onSummaryChange((current) =>
        current
          ? {
              ...current,
              running: response.item.running,
              next_run_at: response.item.next_collect_at ?? current.next_run_at,
              work_scope: response.item.work_scope,
            }
          : current
      );
      await onReloadOverview(false);
      onToast("已启动");
    } catch (err) {
      onError(err instanceof Error ? err.message : "启动自动运行失败");
    } finally {
      setBusyRuntimeAction(null);
    }
  }, [onDashboardChange, onError, onReloadOverview, onSummaryChange, onToast, runtimePlan]);

  const handleStopRuntime = useCallback(async () => {
    setBusyRuntimeAction("stop");
    try {
      const response = await api.stopRuntime();
      onDashboardChange((current) =>
        current ? { ...current, runtime_status: pickNewerRuntimeStatus(current.runtime_status, response.item) ?? response.item } : current
      );
      onSummaryChange((current) =>
        current
          ? {
              ...current,
              running: response.item.running,
              next_run_at: response.item.next_collect_at ?? null,
              work_scope: response.item.work_scope,
            }
          : current
      );
      await onReloadOverview(false);
      onToast("已停止");
    } catch (err) {
      onError(err instanceof Error ? err.message : "停止自动运行失败");
    } finally {
      setBusyRuntimeAction(null);
    }
  }, [onDashboardChange, onError, onReloadOverview, onSummaryChange, onToast]);

  const handleSaveRuntimePlan = useCallback(async (payload: Omit<RuntimePlan, "effective_mode">) => {
    setSavingRuntimePlan(true);
    try {
      const response = await api.updateRuntimePlan(payload);
      onDashboardChange((current) => (current ? { ...current, runtime_plan: response.item } : current));
      await onReloadOverview(false);
    } catch (err) {
      onError(err instanceof Error ? err.message : "工作计划保存失败");
    } finally {
      setSavingRuntimePlan(false);
    }
  }, [onDashboardChange, onError, onReloadOverview]);

  const handleSetAutomationMode = useCallback(async (mode: AutomationMode) => {
    setSavingRuntimePlan(true);
    try {
      const response = await api.setAutomationMode(mode);
      onDashboardChange((current) => (current ? { ...current, current_automation_mode: response.current } : current));
      await onReloadOverview(false);
      onToast(mode === "automated" ? "已切换到计划模式" : "已切换到手动模式");
    } catch (err) {
      onError(err instanceof Error ? err.message : "运行模式切换失败");
    } finally {
      setSavingRuntimePlan(false);
    }
  }, [onDashboardChange, onError, onReloadOverview, onToast]);

  const handleRunRuntimeIntent = useCallback(async (intent: RuntimeIntent) => {
    setBusyMaintenanceIntent(intent);
    try {
      const response = await api.runRuntimeIntent(intent);
      onDashboardChange((current) =>
        current ? { ...current, runtime_status: pickNewerRuntimeStatus(current.runtime_status, response.item) ?? response.item } : current
      );
      await onRefreshAll({ refreshActiveTab: true, forceBrowserRefresh: false });
      onToast(intent === "normal_monitoring" ? "已执行一次完整补跑" : `已执行：${RUNTIME_INTENT_LABELS[intent]}`);
    } catch (err) {
      onError(err instanceof Error ? err.message : "维护动作执行失败");
    } finally {
      setBusyMaintenanceIntent(null);
    }
  }, [onDashboardChange, onError, onRefreshAll, onToast]);

  return {
    busyRuntimeAction,
    busyMaintenanceIntent,
    savingRuntimePlan,
    pollRuntimeStatus,
    handleStartRuntime,
    handleStopRuntime,
    handleSaveRuntimePlan,
    handleSetAutomationMode,
    handleRunRuntimeIntent,
  };
}
