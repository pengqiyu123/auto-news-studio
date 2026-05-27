import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../../lib/api";
import type { BriefItem, IntelAlert, IntelEvent } from "../../types";
import { useBriefsState } from "./useBriefsState";

vi.mock("../../lib/api", () => ({
  api: {
    getBriefs: vi.fn(),
    getBrief: vi.fn(),
    getAgentWorkflows: vi.fn(),
    createEventDeepDive: vi.fn(),
    getEventDeepDive: vi.fn(),
    createBriefFromEvent: vi.fn(),
    createDailyDigestBrief: vi.fn(),
    abandonAgentWorkflow: vi.fn(),
    syncBriefWeChatDraft: vi.fn(),
    copyBriefPackage: vi.fn(),
    deleteBrief: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

const sampleBrief: BriefItem = {
  id: "brief-1",
  event_id: "evt-1",
  deep_dive_id: "dd-1",
  brief_level: "article",
  stage: "prepared",
  title: "测试长文",
  one_line: "一句话结论",
  why_it_matters: "值得关注",
  facts: ["事实 1"],
  quotes: [],
  timeline: [],
  entity_names: [],
  source_links: ["https://example.com/a"],
  risk_notes: [],
  prompt_package_markdown: "pkg",
  wechat_markdown: "# 测试长文",
  wechat_html: "<h1>测试长文</h1>",
  updated_at: "2026-05-12T10:00:00+08:00",
  record_status: "local_only",
  record_exception: null,
  draft_remote_updated_at: null,
  publish_record_published_at: null,
  workflow_mode: "agent",
  workflow_session_id: "agentwf-1",
};

const events: IntelEvent[] = [
  {
    id: "evt-1",
    title: "地平线 6 泄露",
    summary: "事件摘要",
    representative_link: "https://example.com/e1",
    representative_source_name: "Example Source",
    representative_discovery_item_id: "disc-1",
    discovery_item_ids: ["disc-1"],
    source_keys: ["example"],
    source_names: ["Example Source"],
    platforms: ["web"],
    alert_state: "watch",
    entity_ids: [],
    entity_names: [],
    watchlisted: true,
    ignored: false,
    brief_id: null,
    deep_dive_id: null,
    deep_dive_status: "pending",
    deep_dive_summary: undefined,
    deep_dive_started_at: null,
    deep_dive_updated_at: null,
    deep_dive_finished_at: null,
    worth_to_brief: false,
    worth_reason: undefined,
    platform_count: 1,
    source_count: 1,
    member_count: 1,
    story_count: 1,
    member_delta: 0,
    platform_delta: 0,
    tags: [],
    anchor_tokens: [],
    velocity_score: 5,
    coverage_score: 4,
    freshness_score: 3,
    composite_score: 10,
    velocity_details: {},
    change_state: "growing_event",
    alert_reason: "增长中",
    published_at: "2026-05-12T09:00:00+08:00",
    first_seen_at: "2026-05-12T09:00:00+08:00",
    last_seen_at: "2026-05-12T09:30:00+08:00",
    latest_collected_at: "2026-05-12T09:30:00+08:00",
  },
];

describe("useBriefsState", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("loads briefs with record counts from API", async () => {
    mockedApi.getBriefs.mockResolvedValue({
      items: [sampleBrief],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
      stage_counts: { all: 1, prepared: 1, synced: 0, failed: 0 },
      record_counts: { all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 },
    });
    mockedApi.getAgentWorkflows.mockResolvedValue({ items: [] });

    const { result } = renderHook(() =>
      useBriefsState({
        onError: vi.fn(),
        onToast: vi.fn(),
        onReloadOverview: vi.fn().mockResolvedValue(undefined),
        onReloadEvents: vi.fn().mockResolvedValue(undefined),
        onReloadAlerts: vi.fn().mockResolvedValue(undefined),
        onReloadWatchlist: vi.fn().mockResolvedValue(undefined),
        onReloadPublishHistory: vi.fn().mockResolvedValue(undefined),
        onReloadDraftBox: vi.fn().mockResolvedValue(undefined),
        onMarkBriefsLoaded: vi.fn(),
        onActivateWatchlist: vi.fn(),
        onActivateBriefs: vi.fn(),
        getEventsSnapshot: () => events,
        getWatchlistSnapshot: () => [],
        getAlertsSnapshot: () => [],
      }),
    );

    await act(async () => {
      await result.current.loadBriefsData();
    });

    expect(mockedApi.getBriefs).toHaveBeenCalledWith({
      page: 1,
      page_size: 20,
      stage: "all",
      workflow_mode: "all",
      q: "",
    });
    expect(result.current.briefs).toHaveLength(1);
    expect(result.current.briefRecordCounts.local_only).toBe(1);
    expect(result.current.briefs[0].title).toBe("测试长文");
  });

  it("creates brief and fans out reloads through injected callbacks", async () => {
    const onReloadOverview = vi.fn().mockResolvedValue(undefined);
    const onReloadEvents = vi.fn().mockResolvedValue(undefined);
    const onReloadAlerts = vi.fn().mockResolvedValue(undefined);
    const onReloadWatchlist = vi.fn().mockResolvedValue(undefined);
    const onMarkBriefsLoaded = vi.fn();
    const onActivateBriefs = vi.fn();
    const onToast = vi.fn();

    mockedApi.createBriefFromEvent.mockResolvedValue({
      item: {
        ...sampleBrief,
        brief_level: "article",
        title: "地平线 6 泄露",
      },
    });
    mockedApi.getBriefs.mockResolvedValue({
      items: [{ ...sampleBrief, title: "地平线 6 泄露" }],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
      stage_counts: { all: 1, prepared: 1, synced: 0, failed: 0 },
      record_counts: { all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 },
    });
    mockedApi.getAgentWorkflows.mockResolvedValue({ items: [] });

    const { result } = renderHook(() =>
      useBriefsState({
        onError: vi.fn(),
        onToast,
        onReloadOverview,
        onReloadEvents,
        onReloadAlerts,
        onReloadWatchlist,
        onReloadPublishHistory: vi.fn().mockResolvedValue(undefined),
        onReloadDraftBox: vi.fn().mockResolvedValue(undefined),
        onMarkBriefsLoaded,
        onActivateWatchlist: vi.fn(),
        onActivateBriefs,
        getEventsSnapshot: () => events,
        getWatchlistSnapshot: () => [],
        getAlertsSnapshot: (): IntelAlert[] => [],
      }),
    );

    await act(async () => {
      await result.current.handleCreateBrief("evt-1");
    });

    expect(mockedApi.createBriefFromEvent).toHaveBeenCalledWith("evt-1");
    expect(mockedApi.getBriefs).toHaveBeenCalledTimes(1);
    expect(onReloadOverview).toHaveBeenCalledWith(true);
    expect(onReloadEvents).toHaveBeenCalledTimes(1);
    expect(onReloadAlerts).toHaveBeenCalledTimes(1);
    expect(onReloadWatchlist).toHaveBeenCalledTimes(1);
    expect(onActivateBriefs).toHaveBeenCalledTimes(1);
    expect(onMarkBriefsLoaded).toHaveBeenCalledTimes(1);
    expect(onToast).toHaveBeenCalledWith("AI文章已生成：地平线 6 泄露", "success");
  });

  it("creates daily digest and refreshes the brief workbench", async () => {
    const onReloadOverview = vi.fn().mockResolvedValue(undefined);
    const onReloadEvents = vi.fn().mockResolvedValue(undefined);
    const onReloadAlerts = vi.fn().mockResolvedValue(undefined);
    const onReloadWatchlist = vi.fn().mockResolvedValue(undefined);
    const onMarkBriefsLoaded = vi.fn();
    const onActivateBriefs = vi.fn();
    const onToast = vi.fn();

    const digestBrief: BriefItem = {
      ...sampleBrief,
      id: "brief-digest",
      title: "今日科技速递｜2026-05-26",
      one_line: "3 条值得关注的科技动态。",
      brief_level: "rule",
      workflow_mode: "traditional",
      workflow_session_id: null,
      wechat_markdown: "# 今日科技速递｜2026-05-26",
    };
    mockedApi.createDailyDigestBrief.mockResolvedValue({ item: digestBrief });
    mockedApi.getBriefs.mockResolvedValue({
      items: [digestBrief],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
      stage_counts: { all: 1, prepared: 1, synced: 0, failed: 0 },
      record_counts: { all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 },
    });
    mockedApi.getAgentWorkflows.mockResolvedValue({ items: [] });

    const { result } = renderHook(() =>
      useBriefsState({
        onError: vi.fn(),
        onToast,
        onReloadOverview,
        onReloadEvents,
        onReloadAlerts,
        onReloadWatchlist,
        onReloadPublishHistory: vi.fn().mockResolvedValue(undefined),
        onReloadDraftBox: vi.fn().mockResolvedValue(undefined),
        onMarkBriefsLoaded,
        onActivateWatchlist: vi.fn(),
        onActivateBriefs,
        getEventsSnapshot: () => events,
        getWatchlistSnapshot: () => [],
        getAlertsSnapshot: (): IntelAlert[] => [],
      }),
    );

    await act(async () => {
      await result.current.handleCreateDailyDigestBrief();
    });

    expect(mockedApi.createDailyDigestBrief).toHaveBeenCalledWith("dashboard");
    expect(result.current.creatingDailyDigest).toBe(false);
    expect(mockedApi.getBriefs).toHaveBeenCalledTimes(1);
    expect(result.current.briefs[0].title).toBe("今日科技速递｜2026-05-26");
    expect(onReloadOverview).toHaveBeenCalledWith(true);
    expect(onReloadEvents).toHaveBeenCalledTimes(1);
    expect(onReloadAlerts).toHaveBeenCalledTimes(1);
    expect(onReloadWatchlist).toHaveBeenCalledTimes(1);
    expect(onActivateBriefs).toHaveBeenCalledTimes(1);
    expect(onMarkBriefsLoaded).toHaveBeenCalledTimes(1);
    expect(onToast).toHaveBeenCalledWith("今日速递已生成：今日科技速递｜2026-05-26", "success");
  });

  it("surfaces daily digest API errors without reloading", async () => {
    const onError = vi.fn();
    const onReloadOverview = vi.fn().mockResolvedValue(undefined);

    mockedApi.createDailyDigestBrief.mockRejectedValue(new Error("至少需要 2 条合格事件才能生成今日速递"));

    const { result } = renderHook(() =>
      useBriefsState({
        onError,
        onToast: vi.fn(),
        onReloadOverview,
        onReloadEvents: vi.fn().mockResolvedValue(undefined),
        onReloadAlerts: vi.fn().mockResolvedValue(undefined),
        onReloadWatchlist: vi.fn().mockResolvedValue(undefined),
        onReloadPublishHistory: vi.fn().mockResolvedValue(undefined),
        onReloadDraftBox: vi.fn().mockResolvedValue(undefined),
        onMarkBriefsLoaded: vi.fn(),
        onActivateWatchlist: vi.fn(),
        onActivateBriefs: vi.fn(),
        getEventsSnapshot: () => events,
        getWatchlistSnapshot: () => [],
        getAlertsSnapshot: (): IntelAlert[] => [],
      }),
    );

    await act(async () => {
      await result.current.handleCreateDailyDigestBrief();
    });

    expect(onError).toHaveBeenCalledWith("至少需要 2 条合格事件才能生成今日速递");
    expect(onReloadOverview).not.toHaveBeenCalled();
    expect(result.current.creatingDailyDigest).toBe(false);
  });

  it("abandons an unfinished agent workflow and refreshes the workbench", async () => {
    const onToast = vi.fn();
    const onReloadOverview = vi.fn().mockResolvedValue(undefined);
    mockedApi.abandonAgentWorkflow.mockResolvedValue({
      item: {
        workflow_session_id: "agentwf-1",
        status: "abandoned",
        current_step: "article_saved",
        target_platforms: ["wechat"],
        started_at: "2026-05-13T10:00:00+08:00",
        updated_at: "2026-05-13T10:02:00+08:00",
        finished_at: "2026-05-13T10:02:00+08:00",
      },
    });
    mockedApi.getBriefs.mockResolvedValue({
      items: [sampleBrief],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
      stage_counts: { all: 1, prepared: 1, synced: 0, failed: 0 },
      record_counts: { all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 },
    });
    mockedApi.getAgentWorkflows
      .mockResolvedValueOnce({
        items: [{
          workflow_session_id: "agentwf-1",
          status: "failed",
          current_step: "article_saved",
          target_platforms: ["wechat"],
          started_at: "2026-05-13T10:00:00+08:00",
          updated_at: "2026-05-13T10:01:00+08:00",
        }],
      })
      .mockResolvedValueOnce({
        items: [{
          workflow_session_id: "agentwf-1",
          status: "abandoned",
          current_step: "article_saved",
          target_platforms: ["wechat"],
          started_at: "2026-05-13T10:00:00+08:00",
          updated_at: "2026-05-13T10:02:00+08:00",
          finished_at: "2026-05-13T10:02:00+08:00",
        }],
      });

    const { result } = renderHook(() =>
      useBriefsState({
        onError: vi.fn(),
        onToast,
        onReloadOverview,
        onReloadEvents: vi.fn().mockResolvedValue(undefined),
        onReloadAlerts: vi.fn().mockResolvedValue(undefined),
        onReloadWatchlist: vi.fn().mockResolvedValue(undefined),
        onReloadPublishHistory: vi.fn().mockResolvedValue(undefined),
        onReloadDraftBox: vi.fn().mockResolvedValue(undefined),
        onMarkBriefsLoaded: vi.fn(),
        onActivateWatchlist: vi.fn(),
        onActivateBriefs: vi.fn(),
        getEventsSnapshot: () => events,
        getWatchlistSnapshot: () => [],
        getAlertsSnapshot: (): IntelAlert[] => [],
      }),
    );

    await act(async () => {
      await result.current.loadBriefsData();
      await result.current.handleAbandonAgentWorkflow("agentwf-1");
    });

    expect(mockedApi.abandonAgentWorkflow).toHaveBeenCalledWith("agentwf-1");
    expect(onReloadOverview).toHaveBeenCalledWith(false);
    expect(result.current.agentWorkflows[0].status).toBe("abandoned");
    expect(onToast).toHaveBeenCalledWith("已放弃 Agent 会话", "success");
  });

  it("loads single brief detail and merges heavy article fields into local state", async () => {
    mockedApi.getBriefs.mockResolvedValue({
      items: [{ ...sampleBrief, wechat_markdown: "", prompt_package_markdown: "" }],
      total: 1,
      page: 1,
      page_size: 20,
      has_more: false,
      stage_counts: { all: 1, prepared: 1, synced: 0, failed: 0 },
      record_counts: { all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 },
    });
    mockedApi.getAgentWorkflows.mockResolvedValue({ items: [] });
    mockedApi.getBrief.mockResolvedValue({
      item: {
        ...sampleBrief,
        prompt_package_markdown: "full-pkg",
        wechat_markdown: "# 完整正文",
        quotes: ["引文 1"],
        included_events: [
          {
            event_id: "evt-1",
            title: "地平线 6 泄露",
            alert_state: "watch",
            source_count: 1,
            deep_dive_status: "ready",
            representative_link: "https://example.com/e1",
          },
        ],
      },
    });

    const { result } = renderHook(() =>
      useBriefsState({
        onError: vi.fn(),
        onToast: vi.fn(),
        onReloadOverview: vi.fn().mockResolvedValue(undefined),
        onReloadEvents: vi.fn().mockResolvedValue(undefined),
        onReloadAlerts: vi.fn().mockResolvedValue(undefined),
        onReloadWatchlist: vi.fn().mockResolvedValue(undefined),
        onReloadPublishHistory: vi.fn().mockResolvedValue(undefined),
        onReloadDraftBox: vi.fn().mockResolvedValue(undefined),
        onMarkBriefsLoaded: vi.fn(),
        onActivateWatchlist: vi.fn(),
        onActivateBriefs: vi.fn(),
        getEventsSnapshot: () => events,
        getWatchlistSnapshot: () => [],
        getAlertsSnapshot: () => [],
      }),
    );

    await act(async () => {
      await result.current.loadBriefsData();
      await result.current.loadBriefDetail("brief-1");
    });

    expect(mockedApi.getBrief).toHaveBeenCalledWith("brief-1");
    expect(result.current.briefs[0].wechat_markdown).toBe("# 完整正文");
    expect(result.current.briefs[0].prompt_package_markdown).toBe("full-pkg");
    expect(result.current.briefs[0].quotes).toEqual(["引文 1"]);
    expect(result.current.briefs[0].included_events?.[0].title).toBe("地平线 6 泄露");
  });
});
