import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type { EntityWatchlistItem, IntelEvent, IntelEventHistoryItem } from "../../types";

interface UseEventsStateParams {
  initialPageSize: number;
  onToast: (message: string, tone?: "success" | "info" | "warning") => void;
  onError: (message: string) => void;
  onReloadOverview: (includeEntityWatchlist?: boolean) => Promise<void>;
  onReloadWatchlist: () => Promise<void>;
  onReloadAlerts: () => Promise<void>;
}

export function useEventsState({
  initialPageSize,
  onToast,
  onError,
  onReloadOverview,
  onReloadWatchlist,
  onReloadAlerts,
}: UseEventsStateParams) {
  const [events, setEvents] = useState<IntelEvent[]>([]);
  const [eventsPage, setEventsPage] = useState(1);
  const [eventsPageSize, setEventsPageSize] = useState(initialPageSize);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventHistory, setEventHistory] = useState<IntelEventHistoryItem[]>([]);
  const [entityWatchlist, setEntityWatchlist] = useState<EntityWatchlistItem[]>([]);
  const [selectedEntityId, setSelectedEntityId] = useState<string>("all");

  const loadEventsData = useCallback(async (page = eventsPage, pageSize = eventsPageSize) => {
    const response = await api.getIntelEvents({ page, page_size: pageSize });
    setEvents(response.items);
    setEventsPage(response.page);
    setEventsPageSize(response.page_size);
    setEventsTotal(response.total);
    setEventHistory(response.history_items ?? []);
  }, [eventsPage, eventsPageSize]);

  const loadEntityWatchlist = useCallback(async () => {
    const response = await api.getEntityWatchlist();
    setEntityWatchlist(response.items);
    return response.items;
  }, []);

  const handleWatchEvent = useCallback(async (eventId: string) => {
    try {
      await api.watchlistEvent(eventId);
      await Promise.all([
        onReloadOverview(true),
        loadEventsData(eventsPage, eventsPageSize),
        onReloadWatchlist(),
      ]);
    } catch (err) {
      onError(err instanceof Error ? err.message : "加入重点观察失败");
    }
  }, [eventsPage, eventsPageSize, loadEventsData, onError, onReloadOverview, onReloadWatchlist]);

  const handleIgnoreEvent = useCallback(async (eventId: string) => {
    try {
      await api.ignoreEvent(eventId);
      await Promise.all([
        onReloadOverview(true),
        loadEventsData(eventsPage, eventsPageSize),
        onReloadAlerts(),
        onReloadWatchlist(),
      ]);
    } catch (err) {
      onError(err instanceof Error ? err.message : "忽略事件失败");
    }
  }, [eventsPage, eventsPageSize, loadEventsData, onError, onReloadAlerts, onReloadOverview, onReloadWatchlist]);

  const handleUpdateEntityWatchlist = useCallback(async (items: EntityWatchlistItem[]) => {
    try {
      const response = await api.updateEntityWatchlist(items);
      setEntityWatchlist(response.items);
      await onReloadOverview(false);
      if (selectedEntityId !== "all" && !response.items.some((item) => item.entity_id === selectedEntityId)) {
        setSelectedEntityId("all");
      }
      onToast("重点监控实体已更新");
    } catch (err) {
      onError(err instanceof Error ? err.message : "实体监控更新失败");
    }
  }, [onError, onReloadOverview, onToast, selectedEntityId]);

  const handleOpenEntity = useCallback((entityId: string) => {
    setSelectedEntityId(entityId);
  }, []);

  return {
    events,
    eventsPage,
    setEventsPage,
    eventsPageSize,
    setEventsPageSize,
    eventsTotal,
    eventHistory,
    entityWatchlist,
    setEntityWatchlist,
    selectedEntityId,
    setSelectedEntityId,
    loadEventsData,
    loadEntityWatchlist,
    handleWatchEvent,
    handleIgnoreEvent,
    handleUpdateEntityWatchlist,
    handleOpenEntity,
  };
}
