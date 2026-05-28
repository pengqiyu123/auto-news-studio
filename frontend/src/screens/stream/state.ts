import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type { DiscoveryItem } from "../../types";

export interface StreamFilters {
  q?: string;
  time_range?: string;
  platform?: string;
  source?: string;
  item_state?: string;
  min_engagement?: number;
  max_engagement?: number;
}

interface UseStreamStateParams {
  initialPageSize: number;
}

export function useStreamState({ initialPageSize }: UseStreamStateParams) {
  const [streamItems, setStreamItems] = useState<DiscoveryItem[]>([]);
  const [streamPage, setStreamPage] = useState(1);
  const [streamPageSize, setStreamPageSize] = useState(initialPageSize);
  const [streamTotal, setStreamTotal] = useState(0);
  const [availablePlatforms, setAvailablePlatforms] = useState<string[]>([]);
  const [availableSources, setAvailableSources] = useState<string[]>([]);

  const loadStreamData = useCallback(async (page = streamPage, pageSize = streamPageSize, filters?: StreamFilters) => {
    const response = await api.getDiscoveryItems({ page, page_size: pageSize, ...filters });
    setStreamItems(response.items);
    setStreamPage(response.page);
    setStreamPageSize(response.page_size);
    setStreamTotal(response.total);
    setAvailablePlatforms(response.available_platforms ?? []);
    setAvailableSources(response.available_sources ?? []);
  }, [streamPage, streamPageSize]);

  return {
    streamItems,
    streamPage,
    setStreamPage,
    streamPageSize,
    setStreamPageSize,
    streamTotal,
    availablePlatforms,
    availableSources,
    loadStreamData,
  };
}
