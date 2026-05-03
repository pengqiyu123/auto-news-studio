const relativeFormatter = new Intl.RelativeTimeFormat("zh-CN", { numeric: "auto" });

interface FormatDateTimeOptions {
  fallback?: string;
}

function parseDate(value?: string | null) {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date;
}

export function formatDateTime(value?: string | null, options: FormatDateTimeOptions = {}) {
  const { fallback = "未知" } = options;
  const date = parseDate(value);
  if (!date) {
    return fallback;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

export function formatRelativeTime(value?: string | null, fallback = "未知") {
  const date = parseDate(value);
  if (!date) {
    return fallback;
  }
  const diffMinutes = Math.round((date.getTime() - Date.now()) / 60000);
  const absMinutes = Math.abs(diffMinutes);
  if (absMinutes < 60) {
    return relativeFormatter.format(diffMinutes, "minute");
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) {
    return relativeFormatter.format(diffHours, "hour");
  }
  return relativeFormatter.format(Math.round(diffHours / 24), "day");
}

export function formatDuration(seconds?: number | null, fallback = "未知") {
  if (seconds == null || Number.isNaN(seconds)) {
    return fallback;
  }
  const total = Math.max(Math.round(seconds), 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  if (hours > 0) {
    return `${hours}小时 ${minutes}分钟`;
  }
  if (minutes > 0) {
    return `${minutes}分钟 ${remainingSeconds}秒`;
  }
  return `${remainingSeconds}秒`;
}

export function formatDurationMs(value?: number | null) {
  if (value == null) return "暂无";
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

export function toDateTimeLocalValue(value?: string | null) {
  const date = parseDate(value);
  if (!date) {
    return "";
  }
  const pad = (item: number) => String(item).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
