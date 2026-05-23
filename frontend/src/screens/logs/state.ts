import { useCallback, useState } from "react";

import { api } from "../../lib/api";
import type { LogItem } from "../../types";

export type LogsLevelFilter = "all" | "info" | "warning" | "error";

interface UseLogsStateParams {
  initialPageSize: number;
}

export function useLogsState({ initialPageSize }: UseLogsStateParams) {
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [logsPage, setLogsPage] = useState(1);
  const [logsPageSize, setLogsPageSize] = useState(initialPageSize);
  const [logsTotal, setLogsTotal] = useState(0);
  const [logLevelFilter, setLogLevelFilter] = useState<LogsLevelFilter>("all");
  const [logSearchQuery, setLogSearchQuery] = useState("");

  const loadLogsData = useCallback(async (
    page = logsPage,
    pageSize = logsPageSize,
    level = logLevelFilter,
    query = logSearchQuery,
  ) => {
    const response = await api.getLogs({
      page,
      page_size: pageSize,
      level,
      q: query,
    });
    setLogs(response.items);
    setLogsPage(response.page);
    setLogsPageSize(response.page_size);
    setLogsTotal(response.total);
  }, [logLevelFilter, logSearchQuery, logsPage, logsPageSize]);

  return {
    logs,
    logsPage,
    setLogsPage,
    logsPageSize,
    setLogsPageSize,
    logsTotal,
    logLevelFilter,
    setLogLevelFilter,
    logSearchQuery,
    setLogSearchQuery,
    loadLogsData,
  };
}
