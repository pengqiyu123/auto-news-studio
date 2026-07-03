import { getTrendPresentation } from "../lib/trends";
import type { TrendSignalInfo } from "../types";

interface EntityTrendIndicatorProps {
  entityName: string;
  trend?: TrendSignalInfo | null;
}

export function EntityTrendIndicator({ entityName, trend }: EntityTrendIndicatorProps) {
  const presentation = getTrendPresentation(trend?.trend);
  if (!trend || !presentation) {
    return null;
  }
  return (
    <span
      className={`entity-trend-indicator ${presentation.className}`}
      aria-label={`${entityName} 趋势 ${presentation.shortLabel}`}
      title={trend.trend_label || presentation.shortLabel}
    >
      <span className="entity-trend-symbol" aria-hidden="true">{presentation.symbol}</span>
      <span className="entity-trend-label">{presentation.shortLabel}</span>
    </span>
  );
}
