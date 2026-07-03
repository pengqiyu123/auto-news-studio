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
  TrendSignalInfo,
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
  const [trends, setTrends] = useState<TrendSignalInfo[]>([]);

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

  const loadTrends = useCallback(async () => {
    const trendsData = await api.fetchTrends();
    setTrends(trendsData.items ?? []);
    return trendsData.items ?? [];
  }, []);

  const refreshOverviewData = useCallback(async (includeEntityWatchlist = false, lite = false) => {
    const [dashboardData, summaryData, trendsData] = await Promise.all([
      lite ? api.getDashboardLite() : api.getDashboard(),
      api.getIntelSummary(),
      api.fetchTrends(),
    ]);
    applyDashboardSnapshot(dashboardData);
    setSummary(summaryData.item);
    setTrends(trendsData.items ?? []);
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
    trends,
    setTrends,
    applyDashboardSnapshot,
    loadTrends,
    refreshOverviewData,
  };
}
