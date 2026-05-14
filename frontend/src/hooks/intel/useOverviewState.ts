import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import { pickNewerRuntimeStatus } from "../../lib/runtimeIntent";
import type {
  AppUpdateInfo,
  AppVersionInfo,
  BrowserSessionState,
  DashboardResponse,
  EntityWatchlistItem,
  IntelOverviewSummary,
} from "../../types";

interface UseOverviewStateParams {
  onBrowserSessionChange: (session: BrowserSessionState | null) => void;
  onAppVersionChange: (version: AppVersionInfo | null) => void;
  onUpdateInfoChange: (info: AppUpdateInfo | null) => void;
  onEntityWatchlistChange: (items: EntityWatchlistItem[]) => void;
}

export function useOverviewState({
  onBrowserSessionChange,
  onAppVersionChange,
  onUpdateInfoChange,
  onEntityWatchlistChange,
}: UseOverviewStateParams) {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [summary, setSummary] = useState<IntelOverviewSummary | null>(null);

  const applyDashboardSnapshot = useCallback((dashboardData: DashboardResponse) => {
    setDashboard((current) =>
      !current
        ? dashboardData
        : {
            ...dashboardData,
            runtime_status: pickNewerRuntimeStatus(current.runtime_status, dashboardData.runtime_status) ?? dashboardData.runtime_status,
          },
    );
    onBrowserSessionChange(dashboardData.browser_session);
    onAppVersionChange(dashboardData.app_version);
    onUpdateInfoChange(dashboardData.update_info);
  }, [onAppVersionChange, onBrowserSessionChange, onUpdateInfoChange]);

  const refreshOverviewData = useCallback(async (includeEntityWatchlist = false) => {
    const [dashboardData, summaryData] = await Promise.all([
      api.getDashboard(),
      api.getIntelSummary(),
    ]);
    applyDashboardSnapshot(dashboardData);
    setSummary(summaryData.item);
    if (includeEntityWatchlist) {
      const entityWatchlistData = await api.getEntityWatchlist();
      onEntityWatchlistChange(entityWatchlistData.items);
    }
  }, [applyDashboardSnapshot, onEntityWatchlistChange]);

  return {
    dashboard,
    setDashboard,
    summary,
    setSummary,
    applyDashboardSnapshot,
    refreshOverviewData,
  };
}
