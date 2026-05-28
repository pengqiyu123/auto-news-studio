import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";

describe("api.getDiscoveryItems", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("serializes stream filters as query parameters", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          items: [],
          total: 0,
          page: 1,
          page_size: 50,
          has_more: false,
          available_platforms: [],
          available_sources: [],
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.getDiscoveryItems({
      page: 2,
      page_size: 25,
      q: "OpenAI",
      time_range: "24h",
      platform: "rss",
      source: "RSS OpenAI",
      item_state: "updated_item",
      min_engagement: 10,
      max_engagement: 99,
    });

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/api/admin/intel/stream");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("25");
    expect(url.searchParams.get("q")).toBe("OpenAI");
    expect(url.searchParams.get("time_range")).toBe("24h");
    expect(url.searchParams.get("platform")).toBe("rss");
    expect(url.searchParams.get("source")).toBe("RSS OpenAI");
    expect(url.searchParams.get("item_state")).toBe("updated_item");
    expect(url.searchParams.get("min_engagement")).toBe("10");
    expect(url.searchParams.get("max_engagement")).toBe("99");
  });
});
