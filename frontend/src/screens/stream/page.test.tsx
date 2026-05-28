import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DiscoveryItem } from "../../types";
import { StreamPage } from "./page";

function item(overrides: Partial<DiscoveryItem>): DiscoveryItem {
  return {
    id: "disc-1",
    raw_item_id: "raw-1",
    source_key: "rss-openai",
    source_name: "RSS OpenAI",
    source_kind: "rss",
    platform: "rss",
    title: "OpenAI update",
    summary: "Summary",
    content: "Summary",
    link: "https://example.com",
    canonical_link: "https://example.com",
    dedupe_key: "disc-1",
    source_native_id: "disc-1",
    title_tokens: [],
    anchor_tokens: [],
    published_at: "2026-05-12T09:00:00+00:00",
    collected_at: "2026-05-12T09:05:00+00:00",
    tags: [],
    engagement_score: 120,
    item_state: "new_item",
    entity_ids: ["openai"],
    entity_names: ["OpenAI", "GPT-5"],
    metadata: {},
    ...overrides,
  };
}

describe("StreamPage", () => {
  it("emits server filters and keeps current items visible until reload", async () => {
    const onFilterChange = vi.fn();

    render(
      <StreamPage
        items={[item({ title: "Visible current page item" })]}
        page={1}
        pageSize={50}
        total={80}
        availablePlatforms={["hackernews", "rss"]}
        availableSources={["Hacker News", "RSS OpenAI"]}
        onFilterChange={onFilterChange}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );

    expect(screen.getByText("Visible current page item")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("搜索标题、摘要、来源、平台..."), { target: { value: "missing locally" } });

    await waitFor(() => {
      expect(onFilterChange).toHaveBeenLastCalledWith({
        q: "missing locally",
        time_range: "24h",
      });
    });
    expect(screen.getByText("Visible current page item")).toBeInTheDocument();
  });

  it("renders stable options, status badges, entity tags, and only one pager", () => {
    render(
      <StreamPage
        items={[item({ id: "disc-1", item_state: "updated_item", source_name: "RSS OpenAI", platform: "rss" })]}
        page={1}
        pageSize={50}
        total={1}
        availablePlatforms={["hackernews", "rss"]}
        availableSources={["Hacker News", "RSS OpenAI"]}
        onFilterChange={() => {}}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );

    expect(screen.getByRole("option", { name: "Hacker News" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "hackernews" })).toBeInTheDocument();
    expect(screen.getByText("更")).toBeInTheDocument();
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("GPT-5")).toBeInTheDocument();
    expect(screen.getAllByLabelText("下一页")).toHaveLength(1);
  });
});
