import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type { EntityWatchlistItem, IntelEvent } from "../../types";
import { useEventsState } from "./useEventsState";

vi.mock("../../lib/api", () => ({
  api: {
    getIntelEvents: vi.fn(),
    getEntityWatchlist: vi.fn(),
    watchlistEvent: vi.fn(),
    ignoreEvent: vi.fn(),
    updateEntityWatchlist: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

const sampleEvent: IntelEvent = {
  id: "evt-1",
  title: "测试事件",
  summary: "摘要",
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
  entity_ids: ["entity-1"],
  entity_names: ["OpenAI"],
  watchlisted: false,
  ignored: false,
};

describe("useEventsState", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("loads paged events and entity watchlist", async () => {
    mockedApi.getIntelEvents.mockResolvedValue({
      items: [sampleEvent],
      history_items: [],
      total: 1,
      page: 1,
      page_size: 50,
      has_more: false,
    });
    mockedApi.getEntityWatchlist.mockResolvedValue({
      items: [{ entity_id: "entity-1", entity_name: "OpenAI", entity_type: "COMPANY", watchlisted: true }],
    });

    const { result } = renderHook(() =>
      useEventsState({
        initialPageSize: 50,
        onToast: vi.fn(),
        onError: vi.fn(),
        onReloadOverview: vi.fn().mockResolvedValue(undefined),
        onReloadWatchlist: vi.fn().mockResolvedValue(undefined),
        onReloadAlerts: vi.fn().mockResolvedValue(undefined),
      }),
    );

    await act(async () => {
      await result.current.loadEventsData();
      await result.current.loadEntityWatchlist();
    });

    expect(result.current.events).toHaveLength(1);
    expect(result.current.eventsTotal).toBe(1);
    expect(result.current.entityWatchlist).toHaveLength(1);
    expect(result.current.entityWatchlist[0].entity_name).toBe("OpenAI");
  });

  it("passes event filters through reloads after watchlist actions", async () => {
    mockedApi.getIntelEvents.mockResolvedValue({
      items: [sampleEvent],
      history_items: [],
      total: 1,
      page: 1,
      page_size: 50,
      has_more: false,
    });
    mockedApi.watchlistEvent.mockResolvedValue({ item: { ...sampleEvent, watchlisted: true } });

    const { result } = renderHook(() =>
      useEventsState({
        initialPageSize: 50,
        onToast: vi.fn(),
        onError: vi.fn(),
        onReloadOverview: vi.fn().mockResolvedValue(undefined),
        onReloadWatchlist: vi.fn().mockResolvedValue(undefined),
        onReloadAlerts: vi.fn().mockResolvedValue(undefined),
      }),
    );

    await act(async () => {
      await result.current.loadEventsData(1, 50, { entity_id: "entity-1", sort_by: "velocity_score", ignore_mode: "visible" });
    });
    await act(async () => {
      await result.current.handleWatchEvent("evt-1");
    });

    expect(mockedApi.getIntelEvents).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 50,
      entity_id: "entity-1",
      sort_by: "velocity_score",
      ignore_mode: "visible",
    });
  });

  it("updates entity watchlist and clears stale selected entity", async () => {
    const onReloadOverview = vi.fn().mockResolvedValue(undefined);
    const onToast = vi.fn();
    const nextItems: EntityWatchlistItem[] = [
      { entity_id: "entity-2", entity_name: "微软", entity_type: "COMPANY", watchlisted: true },
    ];
    mockedApi.updateEntityWatchlist.mockResolvedValue({ items: nextItems });

    const { result } = renderHook(() =>
      useEventsState({
        initialPageSize: 50,
        onToast,
        onError: vi.fn(),
        onReloadOverview,
        onReloadWatchlist: vi.fn().mockResolvedValue(undefined),
        onReloadAlerts: vi.fn().mockResolvedValue(undefined),
      }),
    );

    act(() => {
      result.current.setSelectedEntityId("entity-1");
    });

    await act(async () => {
      await result.current.handleUpdateEntityWatchlist(nextItems);
    });

    expect(result.current.selectedEntityId).toBe("all");
    expect(onReloadOverview).toHaveBeenCalledWith(false);
    expect(onToast).toHaveBeenCalledWith("重点监控实体已更新");
  });
});
