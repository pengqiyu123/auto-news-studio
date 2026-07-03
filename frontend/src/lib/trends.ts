import type { TrendSignalInfo } from "../types";

export interface TrendPresentation {
  symbol: string;
  shortLabel: string;
  className: string;
}

const TREND_PRESENTATIONS: Record<string, TrendPresentation> = {
  hot: { symbol: "↑", shortLabel: "升温", className: "trend-hot" },
  warm: { symbol: "→", shortLabel: "平稳", className: "trend-warm" },
  cool: { symbol: "↓", shortLabel: "回落", className: "trend-cool" },
  cold: { symbol: "↓", shortLabel: "冷却", className: "trend-cold" },
  emerging: { symbol: "✦", shortLabel: "新升", className: "trend-emerging" },
  insufficient_data: { symbol: "·", shortLabel: "数据少", className: "trend-insufficient" },
};

export function getTrendPresentation(trend?: string | null): TrendPresentation | null {
  if (!trend) return null;
  return TREND_PRESENTATIONS[trend] ?? { symbol: "·", shortLabel: trend, className: "trend-insufficient" };
}

export function buildTrendLookup(trends: TrendSignalInfo[]) {
  const lookup = new Map<string, TrendSignalInfo>();
  for (const item of trends) {
    const entityId = String(item.entity_id || "").trim();
    const entityName = String(item.entity_name || "").trim().toLowerCase();
    if (entityId) lookup.set(entityId, item);
    if (entityName) lookup.set(entityName, item);
  }
  return lookup;
}

export function getTrendForEntity(
  lookup: Map<string, TrendSignalInfo>,
  entityId?: string | null,
  entityName?: string | null,
) {
  if (entityId && lookup.has(entityId)) {
    return lookup.get(entityId) ?? null;
  }
  const normalizedName = String(entityName || "").trim().toLowerCase();
  if (normalizedName && lookup.has(normalizedName)) {
    return lookup.get(normalizedName) ?? null;
  }
  return null;
}
