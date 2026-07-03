import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type { EntityWatchlistItem, EntityWatchlistSummaryItem, IntelEvent, SchedulerStatus } from "../../types";
import { EventsPage } from "./page";

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

function event(overrides: Partial<IntelEvent>): IntelEvent {
  return {
    id: "evt-1",
    title: "OpenAI launch",
    summary: "Readable event summary",
    representative_link: "https://example.com/e1",
    representative_source_name: "Example",
    representative_discovery_item_id: "disc-1",
    discovery_item_ids: ["disc-1"],
    source_keys: ["example"],
    source_names: ["Example"],
    platforms: ["web"],
    platform_count: 1,
    source_count: 1,
    member_count: 1,
    story_count: 1,
    member_delta: 0,
    platform_delta: 0,
    published_at: "2026-05-12T09:00:00+08:00",
    latest_collected_at: "2026-05-12T09:10:00+08:00",
    first_seen_at: "2026-05-12T09:00:00+08:00",
    last_seen_at: "2026-05-12T09:10:00+08:00",
    tags: [],
    anchor_tokens: [],
    velocity_score: 12,
    coverage_score: 8,
    freshness_score: 16,
    composite_score: 14,
    velocity_details: {},
    alert_state: "watch",
    change_state: "new_event",
    alert_reason: "",
    entity_ids: ["openai"],
    entity_names: ["OpenAI"],
    watchlisted: false,
    ignored: false,
    ...overrides,
  };
}

function renderEventsPage(overrides: Partial<React.ComponentProps<typeof EventsPage>> = {}) {
  const props: React.ComponentProps<typeof EventsPage> = {
    items: [event({ id: "evt-openai" }), event({ id: "evt-deepseek", title: "DeepSeek item", entity_ids: ["deepseek"], entity_names: ["DeepSeek"] })],
    page: 1,
    pageSize: 50,
    total: 2,
    historyItems: [],
    runtime,
    entityWatchlist: [],
    entityWatchlistSummary: [],
    selectedEntityId: "all",
    onSelectedEntityChange: vi.fn(),
    onFilterChange: vi.fn(),
    onUpdateEntityWatchlist: vi.fn().mockResolvedValue(undefined),
    onOpenEntity: vi.fn(),
    onWatchEvent: vi.fn().mockResolvedValue(undefined),
    onIgnoreEvent: vi.fn().mockResolvedValue(undefined),
    onDeepDive: vi.fn().mockResolvedValue(undefined),
    onNavigateToAlerts: vi.fn(),
    onPageChange: vi.fn(),
    onPageSizeChange: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<EventsPage {...props} />) };
}

describe("EventsPage", () => {
  it("requests server filtering instead of hiding current page items locally", async () => {
    const onFilterChange = vi.fn();
    renderEventsPage({ onFilterChange });

    fireEvent.change(screen.getByDisplayValue("全部实体"), { target: { value: "openai" } });

    await waitFor(() => {
      expect(onFilterChange).toHaveBeenLastCalledWith({ entity_id: "openai", sort_by: "composite_score", ignore_mode: "visible" });
    });
    expect(screen.getByText("DeepSeek item")).toBeInTheDocument();
  });

  it("keeps one pagination control and expands highlighted event", () => {
    renderEventsPage({ highlightEventId: "evt-openai" });

    expect(screen.getAllByLabelText("下一页")).toHaveLength(1);
    expect(screen.getByText(/收起详情/)).toBeInTheDocument();
  });

  it("renders severity classes and split sort controls", () => {
    const { container } = renderEventsPage({ items: [event({ alert_state: "rising" })] });

    expect(container.querySelector(".intel-row-card.severity-rising")).toBeTruthy();
    expect(screen.getByRole("button", { name: "总分" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "成员增量" })).toBeInTheDocument();
  });

  it("shows trend indicators in the watchlist panel", () => {
    renderEventsPage({
      entityWatchlistSummary: [
        {
          entity_id: "openai",
          entity_name: "OpenAI",
          entity_type: "COMPANY",
          watchlisted: true,
          event_count: 2,
          alert_count: 1,
          rising_count: 1,
          breakout_count: 0,
          last_seen_at: "2026-05-12T09:10:00+08:00",
        } as EntityWatchlistSummaryItem,
      ],
      trends: [
        {
          entity_id: "openai",
          entity_name: "OpenAI",
          trend: "hot",
          trend_label: "近7天持续上升",
          sma_7d: 10,
          sma_14d: 6,
          signals: [],
        },
      ],
    });

    expect(screen.getByLabelText("OpenAI 趋势 升温")).toBeInTheDocument();
  });

  it("loads related events inside expanded details", async () => {
    vi.spyOn(api, "fetchRelatedEvents").mockResolvedValue({
      items: [
        {
          event_id: "evt-related",
          title: "Supplier response follows launch",
          relation_type: "entity_shared",
          weight: 0.78,
          evidence: {},
        },
      ],
    });

    renderEventsPage();

    fireEvent.click(screen.getAllByRole("button", { name: "展开详情 ▼" })[0]);

    expect(await screen.findByText("关联事件")).toBeInTheDocument();
    expect(api.fetchRelatedEvents).toHaveBeenCalledWith("evt-openai");
    expect(await screen.findByText("Supplier response follows launch")).toBeInTheDocument();
    expect(screen.getByText("实体重合")).toBeInTheDocument();
    expect(screen.getByText("78%")).toBeInTheDocument();
  });
});
