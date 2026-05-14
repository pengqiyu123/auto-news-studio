import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type { DiscoveryItem } from "../../types";

interface UseStreamStateParams {
  initialPageSize: number;
}

export function useStreamState({ initialPageSize }: UseStreamStateParams) {
  const [streamItems, setStreamItems] = useState<DiscoveryItem[]>([]);
  const [streamPage, setStreamPage] = useState(1);
  const [streamPageSize, setStreamPageSize] = useState(initialPageSize);
  const [streamTotal, setStreamTotal] = useState(0);

  const loadStreamData = useCallback(async (page = streamPage, pageSize = streamPageSize) => {
    const response = await api.getDiscoveryItems({ page, page_size: pageSize });
    setStreamItems(response.items);
    setStreamPage(response.page);
    setStreamPageSize(response.page_size);
    setStreamTotal(response.total);
  }, [streamPage, streamPageSize]);

  return {
    streamItems,
    streamPage,
    setStreamPage,
    streamPageSize,
    setStreamPageSize,
    streamTotal,
    loadStreamData,
  };
}
