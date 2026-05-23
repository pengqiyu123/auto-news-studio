import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type { IntelEvent } from "../../types";

interface UseWatchlistStateParams {
  pageSize: number;
}

export function useWatchlistState({ pageSize }: UseWatchlistStateParams) {
  const [watchlistEvents, setWatchlistEvents] = useState<IntelEvent[]>([]);

  const loadWatchlistData = useCallback(async () => {
    const response = await api.getIntelEvents({ page: 1, page_size: pageSize });
    setWatchlistEvents(response.items);
  }, [pageSize]);

  return {
    watchlistEvents,
    loadWatchlistData,
  };
}
