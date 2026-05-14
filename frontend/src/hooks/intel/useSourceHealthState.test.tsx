import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type { SourceConnector } from "../../types";
import { useSourceHealthState } from "./useSourceHealthState";

vi.mock("../../lib/api", () => ({
  api: {
    getIntelSources: vi.fn(),
    syncSources: vi.fn(),
    syncSource: vi.fn(),
    updateSource: vi.fn(),
    createSource: vi.fn(),
    deleteSource: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

const sampleSource: SourceConnector = {
  key: "example",
  name: "Example Source",
  kind: "rss",
  driver: "legacy_rss",
  platform: "rss",
  enabled: true,
  schedule: "*/30 * * * *",
  priority: 5,
  weight: 1,
  auth: {},
  url: "https://example.com/rss",
  tags: [],
  capabilities: [],
  origin_repo: "test",
  origin_license: "",
  health_status: "healthy",
  health_detail: "ok",
  item_count: 1,
  consecutive_failures: 0,
  last_item_count: 1,
};

describe("useSourceHealthState", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("loads source health and syncs all sources with cascaded reloads", async () => {
    const onReloadOverview = vi.fn().mockResolvedValue(undefined);
    const onReloadStream = vi.fn().mockResolvedValue(undefined);
    const onReloadEvents = vi.fn().mockResolvedValue(undefined);
    const onReloadWatchlist = vi.fn().mockResolvedValue(undefined);
    const onReloadAlerts = vi.fn().mockResolvedValue(undefined);
    mockedApi.getIntelSources.mockResolvedValue({ items: [sampleSource] });
    mockedApi.syncSources.mockResolvedValue({
      raw_count: 1,
      normalized_count: 1,
      event_count: 1,
      synced_at: "2026-05-12T10:00:00+08:00",
      warnings: [],
    });

    const { result } = renderHook(() =>
      useSourceHealthState({
        onToast: vi.fn(),
        onError: vi.fn(),
        onReloadOverview,
        onReloadStream,
        onReloadEvents,
        onReloadWatchlist,
        onReloadAlerts,
      }),
    );

    await act(async () => {
      await result.current.loadSourceHealthData();
      await result.current.handleSourceSync();
    });

    expect(result.current.sources).toHaveLength(1);
    expect(mockedApi.syncSources).toHaveBeenCalledTimes(1);
    expect(onReloadOverview).toHaveBeenCalledWith(true);
    expect(onReloadStream).toHaveBeenCalledTimes(1);
    expect(onReloadEvents).toHaveBeenCalledTimes(1);
    expect(onReloadWatchlist).toHaveBeenCalledTimes(1);
    expect(onReloadAlerts).toHaveBeenCalledTimes(1);
  });

  it("creates and deletes a source with overview refresh and toast", async () => {
    const onReloadOverview = vi.fn().mockResolvedValue(undefined);
    const onToast = vi.fn();
    mockedApi.createSource.mockResolvedValue({ item: sampleSource });
    mockedApi.deleteSource.mockResolvedValue({ ok: true });
    mockedApi.getIntelSources.mockResolvedValue({ items: [sampleSource] });

    const { result } = renderHook(() =>
      useSourceHealthState({
        onToast,
        onError: vi.fn(),
        onReloadOverview,
        onReloadStream: vi.fn().mockResolvedValue(undefined),
        onReloadEvents: vi.fn().mockResolvedValue(undefined),
        onReloadWatchlist: vi.fn().mockResolvedValue(undefined),
        onReloadAlerts: vi.fn().mockResolvedValue(undefined),
      }),
    );

    await act(async () => {
      await result.current.handleSourceCreate({
        key: "example",
        name: "Example Source",
        kind: "rss",
        driver: "legacy_rss",
      });
      await result.current.handleSourceDelete("example");
    });

    expect(mockedApi.createSource).toHaveBeenCalledTimes(1);
    expect(mockedApi.deleteSource).toHaveBeenCalledWith("example");
    expect(onReloadOverview).toHaveBeenCalledWith(false);
    expect(onToast).toHaveBeenCalledWith("来源已添加");
    expect(onToast).toHaveBeenCalledWith("来源已删除");
  });
});
