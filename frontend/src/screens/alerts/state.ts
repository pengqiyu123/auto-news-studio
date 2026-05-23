import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type { IntelAlert, IntelAlertHistoryItem } from "../../types";

export function useAlertsState() {
  const [alerts, setAlerts] = useState<IntelAlert[]>([]);
  const [alertHistory, setAlertHistory] = useState<IntelAlertHistoryItem[]>([]);

  const loadAlertsData = useCallback(async () => {
    const response = await api.getIntelAlerts();
    setAlerts(response.items);
    setAlertHistory(response.history_items ?? []);
  }, []);

  return {
    alerts,
    alertHistory,
    loadAlertsData,
  };
}
