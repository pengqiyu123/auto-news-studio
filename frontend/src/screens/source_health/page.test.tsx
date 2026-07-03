import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SourceConnector } from "../../types";
import { SourceHealthPage } from "./page";

function source(overrides: Partial<SourceConnector>): SourceConnector {
  return {
    key: "rss-openai",
    name: "OpenAI Blog",
    kind: "rss",
    driver: "feedparser",
    platform: "rss",
    enabled: true,
    schedule: "*/30 * * * *",
    interval_minutes: 30,
    priority: 9,
    weight: 0.9,
    auth: {},
    url: "https://example.com/feed",
    tags: ["ai"],
    capabilities: ["rss"],
    origin_repo: "curated",
    origin_license: "rss",
    health_status: "healthy",
    health_detail: "正常",
    item_count: 42,
    last_synced_at: "2026-05-24T09:10:00+00:00",
    last_attempt_at: "2026-05-24T09:10:00+00:00",
    last_success_at: "2026-05-24T09:10:00+00:00",
    last_failure_at: null,
    consecutive_failures: 0,
    last_duration_ms: 1200,
    avg_duration_ms: 1500,
    last_item_count: 8,
    updated_at: "2026-05-24T09:10:00+00:00",
    ...overrides,
  };
}

function renderPage(overrides: Partial<React.ComponentProps<typeof SourceHealthPage>> = {}) {
  const props: React.ComponentProps<typeof SourceHealthPage> = {
    sources: [
      source({ key: "rss-ok", name: "OpenAI Blog", platform: "rss", health_status: "healthy", health_detail: "正常" }),
      source({ key: "yt-warn", name: "YouTube Monitor", platform: "youtube", health_status: "warning", health_detail: "连续失败 2 次", consecutive_failures: 2 }),
      source({ key: "api-error", name: "News API", platform: "api", health_status: "error", health_detail: "HTTP 500", consecutive_failures: 4 }),
      source({ key: "rss-idle", name: "Disabled RSS", platform: "rss", enabled: false, health_status: "idle", health_detail: "" }),
    ],
    syncing: false,
    savingSourceKey: null,
    syncingSourceKey: null,
    onSyncSources: vi.fn().mockResolvedValue(undefined),
    onSyncSource: vi.fn().mockResolvedValue(undefined),
    onSaveSource: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  return { props, ...render(<SourceHealthPage {...props} />) };
}

describe("SourceHealthPage", () => {
  it("renders productized stats, filters, severity cards, and actions", () => {
    const { container } = renderPage();

    expect(screen.getByRole("heading", { name: "数据源状态监控" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "全部重新抓取" })).toBeInTheDocument();
    expect(container.querySelectorAll(".source-health-stat")).toHaveLength(4);
    expect(container.querySelector(".source-health-card.severity-error")).toBeTruthy();
    expect(screen.getByText("失败 4 次")).toHaveClass("critical");
    expect(screen.getAllByRole("button", { name: /查看详情/ })).toHaveLength(4);
    expect(screen.getAllByRole("button", { name: "重新抓取" })).toHaveLength(4);
  });

  it("filters by stat, platform, and search without hiding empty-state meaning", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "异常 1 个" }));
    expect(screen.getByText("News API")).toBeInTheDocument();
    expect(screen.queryByText("OpenAI Blog")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "异常 1 个" }));
    fireEvent.change(screen.getByLabelText("平台筛选"), { target: { value: "youtube" } });
    expect(screen.getByText("YouTube Monitor")).toBeInTheDocument();
    expect(screen.queryByText("News API")).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("搜索来源名称或平台"), { target: { value: "missing" } });
    expect(screen.getByText("当前筛选条件下没有匹配的数据源。")).toBeInTheDocument();
  });

  it("shows expanded detail and distinguishes no source data", () => {
    const { rerender, props } = renderPage();

    fireEvent.click(screen.getAllByRole("button", { name: /查看详情/ })[0]);
    expect(screen.getByText(/最近尝试/)).toBeInTheDocument();
    expect(screen.getByText(/平均耗时/)).toBeInTheDocument();

    rerender(<SourceHealthPage {...props} sources={[]} />);
    expect(screen.getByText("还没有配置数据源。")).toBeInTheDocument();
  });
});
