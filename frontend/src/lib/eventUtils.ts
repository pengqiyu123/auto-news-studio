import type { HistoryRecordStatus } from "../types";

export function historyStatusLabel(status: HistoryRecordStatus) {
  if (status === "active") return "仍活跃";
  if (status === "source_uncertain") return "待确认";
  return "已回落";
}

export function historyStatusTone(status: HistoryRecordStatus) {
  if (status === "active") return "success";
  if (status === "source_uncertain") return "warning";
  return "neutral";
}
