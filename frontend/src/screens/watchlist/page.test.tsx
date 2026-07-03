import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EventDeepDive, IntelEvent } from "../../types";
import { WatchlistPage } from "./page";

function isoDaysAgo(days: number) {
  const value = new Date();
  value.setDate(value.getDate() - days);
  return value.toISOString();
}

function event(overrides: Partial<IntelEvent>): IntelEvent {
  return {
    id: "evt-1",
    title: "Apple expands on-device AI",
    summary: "A short summary about the event.",
    representative_link: "https://example.com/story",
    representative_source_name: "Example News",
    representative_discovery_item_id: "di-1",
    discovery_item_ids: ["di-1"],
    source_keys: ["example"],
    source_names: ["Example News"],
    platforms: ["web"],
    platform_count: 1,
    source_count: 1,
    member_count: 2,
    story_count: 2,
    member_delta: 0,
    platform_delta: 0,
    published_at: isoDaysAgo(0),
    latest_collected_at: isoDaysAgo(0),
    first_seen_at: isoDaysAgo(0),
    last_seen_at: isoDaysAgo(0),
    tags: [],
    anchor_tokens: [],
    velocity_score: 10,
    coverage_score: 20,
    freshness_score: 30,
    composite_score: 40,
    velocity_details: {},
    alert_state: "watch",
    change_state: "new_event",
    alert_reason: "watch",
    entity_ids: ["apple"],
    entity_names: ["Apple"],
    watchlisted: true,
    ignored: false,
    deep_dive_id: null,
    brief_id: null,
    deep_dive_status: "pending",
    deep_dive_started_at: null,
    deep_dive_finished_at: null,
    deep_dive_updated_at: null,
    brief_status: null,
    deep_dive_summary: "",
    worth_to_brief: false,
    worth_reason: "",
    ...overrides,
  };
}

function deepDive(overrides: Partial<EventDeepDive> = {}): EventDeepDive {
  return {
    id: "dd-1",
    event_id: "evt-ready",
    status: "ready",
    started_at: isoDaysAgo(0),
    finished_at: isoDaysAgo(0),
    updated_at: isoDaysAgo(0),
    attempted_count: 3,
    success_count: 2,
    failed_count: 1,
    resolved_evidence_pack: [],
    full_text_sources: [
      {
        source_key: "example",
        source_name: "Example News",
        original_link: "https://example.com/story",
        canonical_link: "https://example.com/story",
        title: "Full text",
        published_at: isoDaysAgo(0),
        fetch_status: "fetched",
        extract_status: "extracted",
        word_count: 800,
        cleaned_full_text: "Long body text for preview.".repeat(20),
        excerpt: "Long body text for preview.",
        quotes: ["quoted text"],
        error: null,
      },
    ],
    sources: [],
    facts: ["Fact one"],
    quotes: ["Quote one"],
    timeline: ["Now"],
    worthiness: { worth_to_brief: true, reason: "深挖详情判断完整" },
    last_error: null,
    ...overrides,
  };
}

function renderPage(overrides: Partial<React.ComponentProps<typeof WatchlistPage>> = {}) {
  const props: React.ComponentProps<typeof WatchlistPage> = {
    items: [
      event({ id: "evt-pending", title: "Samsung source needs text", entity_names: ["Samsung"], deep_dive_status: "pending" }),
      event({
        id: "evt-ready",
        title: "Apple ready insight",
        summary: "This event is ready for delivery.",
        entity_names: ["Apple"],
        deep_dive_status: "ready",
        deep_dive_id: "dd-1",
        deep_dive_finished_at: isoDaysAgo(0),
        deep_dive_updated_at: isoDaysAgo(0),
        worth_to_brief: true,
        worth_reason: "证据完整，适合交付。",
      }),
      event({
        id: "evt-old-pending",
        title: "Legacy pending item",
        entity_names: ["OpenAI"],
        deep_dive_status: "failed",
        latest_collected_at: isoDaysAgo(3),
        first_seen_at: isoDaysAgo(3),
        last_seen_at: isoDaysAgo(3),
        published_at: isoDaysAgo(3),
      }),
      event({
        id: "evt-old-ready",
        title: "Past ready item",
        entity_names: ["NVIDIA"],
        deep_dive_status: "partial",
        deep_dive_id: "dd-old",
        deep_dive_finished_at: isoDaysAgo(3),
        deep_dive_updated_at: isoDaysAgo(3),
      }),
    ],
    selectedDeepDive: null,
    busyEventId: null,
    loading: false,
    onDeepDive: vi.fn().mockResolvedValue(undefined),
    onCreateBrief: vi.fn().mockResolvedValue(undefined),
    onOpenDeepDive: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  return { props, ...render(<WatchlistPage {...props} />) };
}

describe("WatchlistPage", () => {
  it("renders stat navigation with section counts and severity cards", () => {
    const { container } = renderPage();

    expect(screen.getByRole("heading", { name: "先拿到正文，再决定哪些事件值得交付成简报" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "待深挖 1 条" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "已深挖 1 条" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "往日待深挖 1 条" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "往日已深挖 1 条" })).toBeInTheDocument();
    expect(screen.getByText("Samsung source needs text")).toBeInTheDocument();
    expect(container.querySelector(".watchlist-card.severity-pending")).toBeTruthy();
  });

  it("uses stat cards to switch sections and search title, summary, and entities", () => {
    renderPage({
      items: [
        event({ id: "evt-samsung", title: "Samsung source needs text", summary: "Normal body", entity_names: ["Samsung"] }),
        event({ id: "evt-entity", title: "Chip supply update", summary: "Normal body", entity_names: ["Qualcomm"] }),
        event({ id: "evt-summary", title: "Cloud update", summary: "Mentions robotics in the summary", entity_names: ["OpenAI"] }),
      ],
    });

    fireEvent.change(screen.getByPlaceholderText("搜索标题、摘要或实体"), { target: { value: "Qualcomm" } });
    expect(screen.getByText("Chip supply update")).toBeInTheDocument();
    expect(screen.queryByText("Samsung source needs text")).not.toBeInTheDocument();

    const search = screen.getByPlaceholderText("搜索标题、摘要或实体");
    fireEvent.change(search, { target: { value: "robotics" } });
    expect(screen.getByText("Cloud update")).toBeInTheDocument();
    expect(screen.queryByText("Chip supply update")).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "往日已深挖 0 条" }));
    expect(screen.getByText("往日已深挖暂无事件。")).toBeInTheDocument();
  });

  it("shows skeleton and distinct empty states", () => {
    const { rerender, props, container } = renderPage({ items: [], loading: true });
    expect(container.querySelectorAll(".skeleton-card")).toHaveLength(4);

    rerender(<WatchlistPage {...props} loading={false} />);
    expect(screen.getByText("深挖池暂无事件。")).toBeInTheDocument();

    rerender(<WatchlistPage {...props} items={[event({ id: "evt-only", title: "Only visible item" })]} />);
    fireEvent.change(screen.getByPlaceholderText("搜索标题、摘要或实体"), { target: { value: "missing" } });
    expect(screen.getByText("没有匹配的深挖事件。")).toBeInTheDocument();
  });

  it("renders actions without confirmation and opens detail on expand", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const onCreateBrief = vi.fn().mockResolvedValue(undefined);
    const onOpenDeepDive = vi.fn().mockResolvedValue(undefined);

    renderPage({ onCreateBrief, onOpenDeepDive });

    fireEvent.click(screen.getByRole("button", { name: "生成简报" }));
    expect(confirmSpy).not.toHaveBeenCalled();
    expect(onCreateBrief).toHaveBeenCalledWith("evt-pending");

    fireEvent.click(screen.getByRole("button", { name: "查看详情 ▼" }));
    expect(onOpenDeepDive).toHaveBeenCalledWith("evt-pending");
    confirmSpy.mockRestore();
  });

  it("expands selected deep dive details inside the card", () => {
    renderPage({ selectedDeepDive: deepDive() });

    fireEvent.click(screen.getByRole("button", { name: "已深挖 1 条" }));
    expect(screen.getByText("Apple ready insight")).toBeInTheDocument();
    expect(screen.getByText("深挖详情")).toBeInTheDocument();
    expect(screen.getByText("2/3 来源成功")).toBeInTheDocument();
    expect(screen.getByText("深挖详情判断完整")).toBeInTheDocument();
  });
});
