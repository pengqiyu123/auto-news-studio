import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type { SourceConnector } from "../../types";

interface UseSourceHealthStateParams {
  onToast: (message: string, tone?: "success" | "info" | "warning") => void;
  onError: (message: string) => void;
  onReloadOverview: (includeEntityWatchlist?: boolean) => Promise<void>;
  onReloadStream: () => Promise<void>;
  onReloadEvents: () => Promise<void>;
  onReloadWatchlist: () => Promise<void>;
  onReloadAlerts: () => Promise<void>;
}

export function useSourceHealthState({
  onToast,
  onError,
  onReloadOverview,
  onReloadStream,
  onReloadEvents,
  onReloadWatchlist,
  onReloadAlerts,
}: UseSourceHealthStateParams) {
  const [sources, setSources] = useState<SourceConnector[]>([]);
  const [refreshingSources, setRefreshingSources] = useState(false);
  const [savingSourceKey, setSavingSourceKey] = useState<string | null>(null);
  const [syncingSourceKey, setSyncingSourceKey] = useState<string | null>(null);

  const loadSourceHealthData = useCallback(async () => {
    const response = await api.getIntelSources();
    setSources(response.items);
    return response.items;
  }, []);

  const handleSourceSync = useCallback(async (options?: { includeSourceHealth?: boolean }) => {
    setRefreshingSources(true);
    try {
      await api.syncSources();
      await Promise.all([
        onReloadOverview(true),
        onReloadStream(),
        onReloadEvents(),
        onReloadWatchlist(),
        onReloadAlerts(),
        options?.includeSourceHealth === false ? Promise.resolve() : loadSourceHealthData(),
      ]);
    } catch (err) {
      onError(err instanceof Error ? err.message : "来源同步失败");
    } finally {
      setRefreshingSources(false);
    }
  }, [loadSourceHealthData, onError, onReloadAlerts, onReloadEvents, onReloadOverview, onReloadStream, onReloadWatchlist]);

  const handleSourceSyncOne = useCallback(async (sourceKey: string, options?: { includeSourceHealth?: boolean }) => {
    setSyncingSourceKey(sourceKey);
    try {
      await api.syncSource(sourceKey);
      await Promise.all([
        onReloadOverview(true),
        onReloadStream(),
        onReloadEvents(),
        onReloadWatchlist(),
        onReloadAlerts(),
        options?.includeSourceHealth === false ? Promise.resolve() : loadSourceHealthData(),
      ]);
    } catch (err) {
      onError(err instanceof Error ? err.message : "单来源重抓失败");
    } finally {
      setSyncingSourceKey(null);
    }
  }, [loadSourceHealthData, onError, onReloadAlerts, onReloadEvents, onReloadOverview, onReloadStream, onReloadWatchlist]);

  const handleSourceSave = useCallback(async (
    sourceKey: string,
    payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">,
  ) => {
    setSavingSourceKey(sourceKey);
    try {
      await api.updateSource(sourceKey, payload);
      await Promise.all([
        onReloadOverview(false),
        loadSourceHealthData(),
      ]);
    } catch (err) {
      onError(err instanceof Error ? err.message : "来源保存失败");
    } finally {
      setSavingSourceKey(null);
    }
  }, [loadSourceHealthData, onError, onReloadOverview]);

  const handleSourceCreate = useCallback(async (payload: Parameters<typeof api.createSource>[0]) => {
    try {
      await api.createSource(payload);
      await Promise.all([
        onReloadOverview(false),
        loadSourceHealthData(),
      ]);
      onToast("来源已添加");
    } catch (err) {
      onError(err instanceof Error ? err.message : "来源添加失败");
    }
  }, [loadSourceHealthData, onError, onReloadOverview, onToast]);

  const handleSourceDelete = useCallback(async (sourceKey: string) => {
    try {
      await api.deleteSource(sourceKey);
      await Promise.all([
        onReloadOverview(false),
        loadSourceHealthData(),
      ]);
      onToast("来源已删除");
    } catch (err) {
      onError(err instanceof Error ? err.message : "来源删除失败");
    }
  }, [loadSourceHealthData, onError, onReloadOverview, onToast]);

  return {
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
  };
}
