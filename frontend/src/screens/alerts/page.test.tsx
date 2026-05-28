import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EntityWatchlistItem, IntelAlert, SchedulerStatus } from "../../types";
import { AlertsPage } from "./page";

const runtime = {
  control_state: "running",
  running: true,
  run_intent: "normal",
  current_phase: "idle",
  current_job: null,
  next_collect_at: null,
  last_collect_at: null,
  last_successful_sync_at: null,
  started_at: null,
  stopped_at: null,
  active_run_id: null,
  blocked_reason: null,
  last_cycle_issue_summary: null,
  last_cycle_summary: null,
} as unknown as SchedulerStatus;

function alert(overrides: Partial<IntelAlert>): IntelAlert {
  return {
    id: "alert-1",
    event_id: "evt-1",
    title: "OpenAI launch",
    summary: "Readable alert summary",
    level: "breakout",
    reason: "速度得分突破阈值",
    velocity_score: 12,
    coverage_score: 8,
    freshness_score: 16,
    composite_score: 14,
    platform_count: 2,
    source_count: 1,
    representative_link: "https://example.com",
    triggered_at: "2026-05-12T09:00:00+08:00",
    entity_ids: ["openai"],
    entity_names: ["OpenAI"],
    ...overrides,
  };
}

function renderAlertsPage(overrides: Partial<React.ComponentProps<typeof AlertsPage>> = {}) {
  const props: React.ComponentProps<typeof AlertsPage> = {
    items: [alert({ id: "alert-breakout", level: "breakout" }), alert({ id: "alert-watch", event_id: "evt-2", level: "watch", title: "Watch item", summary: "Watch summary" })],
    historyItems: [],
    runtime,
    eventCount: 2,
    selectedEntityId: "all",
    entityWatchlist: [{ entity_id: "anthropic", entity_name: "Anthropic", entity_type: "COMPANY", watchlisted: true } as EntityWatchlistItem],
    onSelectedEntityChange: vi.fn(),
    onNavigateToEvent: vi.fn(),
    onDeepDive: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  return { props, ...render(<AlertsPage {...props} />) };
}

describe("AlertsPage", () => {
  it("groups alerts, displays summary, and uses severity classes", () => {
    const { container } = renderAlertsPage();

    expect(screen.getByText("爆发 (1)")).toBeInTheDocument();
    expect(screen.getByText("关注 (1)")).toBeInTheDocument();
    expect(screen.getByText("Readable alert summary")).toBeInTheDocument();
    expect(container.querySelector(".intel-row-card.severity-breakout")).toBeTruthy();
  });

  it("navigates to an alert event and includes watchlist entity options", () => {
    const onNavigateToEvent = vi.fn();
    renderAlertsPage({ onNavigateToEvent });

    fireEvent.click(screen.getAllByRole("button", { name: "查看事件" })[0]);

    expect(onNavigateToEvent).toHaveBeenCalledWith("evt-1");
    expect(screen.getByRole("option", { name: "Anthropic" })).toBeInTheDocument();
  });

  it("filters via stats row", () => {
    renderAlertsPage();

    fireEvent.click(screen.getByText("关注"));

    expect(screen.queryByText("Readable alert summary")).not.toBeInTheDocument();
    expect(screen.getByText("Watch item")).toBeInTheDocument();
  });
});
