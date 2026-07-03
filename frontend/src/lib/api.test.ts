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

describe("api.getIntelEvents", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("serializes event filters as query parameters", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          items: [],
          history_items: [],
          total: 0,
          page: 1,
          page_size: 50,
          has_more: false,
        }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.getIntelEvents({
      page: 2,
      page_size: 25,
      entity_id: "openai",
      event_id: "evt-1",
      sort_by: "velocity_score",
      ignore_mode: "visible",
    });

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/api/admin/intel/events");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("25");
    expect(url.searchParams.get("entity_id")).toBe("openai");
    expect(url.searchParams.get("event_id")).toBe("evt-1");
    expect(url.searchParams.get("sort_by")).toBe("velocity_score");
    expect(url.searchParams.get("ignore_mode")).toBe("visible");
  });
});

describe("brief publishing api helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("posts to the WeChat publish endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ item: { id: "brief-1" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.publishBriefWeChatArticle("brief-1");

    expect(fetchMock).toHaveBeenCalledWith("/api/admin/briefs/brief-1/wechat-publish", {
      method: "POST",
    });
  });
});

describe("analysis api helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches topics from the analysis endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchTopics();

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/api/admin/topics");
  });

  it("fetches related events for a specific event", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchRelatedEvents("evt-123");

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/api/admin/events/evt-123/related");
  });

  it("fetches entity trends", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchTrends();

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/api/admin/trends");
  });

  it("fetches topic periodicity and temporal rules", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchTopicsPeriodicity();
    await api.fetchTemporalRules();

    expect(new URL(fetchMock.mock.calls[0][0] as string).pathname).toBe("/api/admin/topics/periodicity");
    expect(new URL(fetchMock.mock.calls[1][0] as string).pathname).toBe("/api/admin/analysis/temporal-rules");
  });

  it("fetches analysis batch status", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchAnalysisBatchStatus();

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/api/admin/analysis/batch-status");
  });

  it("fetches aggregated analysis signals", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchAnalysisSignals();

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/api/admin/analysis/signals");
  });

  it("fetches events for a topic", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchTopicEvents("topic-01");

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe("/api/admin/topics/topic-01/events");
  });

  it("submits analysis feedback", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true, feedback_id: "feedback-1" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.submitAnalysisFeedback({
      target_type: "analysis_summary",
      target_id: "openai",
      feedback_type: "correct",
      correction: { note: "OpenAI 事件权重偏高" },
    });

    const [urlText, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const url = new URL(urlText);
    expect(url.pathname).toBe("/api/admin/analysis/feedback");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toMatchObject({
      target_type: "analysis_summary",
      target_id: "openai",
      feedback_type: "correct",
      correction: { note: "OpenAI 事件权重偏高" },
    });
  });

  it("generates an analysis report", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ item: { report_id: "report-1" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.generateAnalysisReport({
      scope: "daily",
      date_from: "2026-05-20",
      date_to: "2026-05-29",
      focus_entities: ["openai"],
    });

    const [urlText, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const url = new URL(urlText);
    expect(url.pathname).toBe("/api/admin/analysis/report");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toMatchObject({
      scope: "daily",
      date_from: "2026-05-20",
      date_to: "2026-05-29",
      focus_entities: ["openai"],
    });
  });

  it("fetches analysis report history and feedback stats", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api.fetchAnalysisReports();
    await api.fetchAnalysisReport("report-1");
    await api.fetchAnalysisFeedbackStats();

    expect(new URL(fetchMock.mock.calls[0][0] as string).pathname).toBe("/api/admin/analysis/reports");
    expect(new URL(fetchMock.mock.calls[1][0] as string).pathname).toBe("/api/admin/analysis/reports/report-1");
    expect(new URL(fetchMock.mock.calls[2][0] as string).pathname).toBe("/api/admin/analysis/feedback/stats");
  });
});
