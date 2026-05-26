import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWechatState } from "./useWechatState";
import { api } from "../../lib/api";
import type { BrowserSessionState, WeChatPublishHistorySnapshot } from "../../types";

vi.mock("../../lib/api", () => ({
  api: {
    getPublishTasks: vi.fn(),
    checkWeChatPublishHistory: vi.fn(),
    getBrowserSession: vi.fn(),
    checkWeChatDraftBox: vi.fn(),
    getWeChatMapping: vi.fn(),
    refreshWeChatMapping: vi.fn(),
    deleteWeChatRemoteDraft: vi.fn(),
    syncBriefWeChatDraft: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

const browserSession: BrowserSessionState = {
  platform: "wechat_mp",
  browser_name: "edge",
  user_data_dir: "D:/profiles/wechat",
  logged_in: true,
  selectors_version: "wechat-mp-v1",
  sidecar_health: "healthy",
  manager_alive: true,
  window_state: "restored",
  resident_page: "home",
  busy: false,
};

const publishHistory: WeChatPublishHistorySnapshot = {
  checked_at: "2026-05-12T11:00:00+08:00",
  record_count: 1,
  overview: {
    total_users: 26,
    yesterday_reads: 6,
    yesterday_shares: 6,
    yesterday_new_follows: 0,
    stats_window_label: "5月19日 00:00 - 24:00",
    fetched_at: "2026-05-12T11:00:00+08:00",
  },
  items: [
    {
      title: "示例文章",
      url: "https://mp.weixin.qq.com/s/example",
      appmsg_id: null,
      published_at: "今天 20:49",
      remote_key: "url:https://mp.weixin.qq.com/s/example",
      read_count: 12,
      like_count: 3,
      share_count: 2,
      recommend_count: 1,
      comment_count: 4,
      highlight_count: 5,
      tip_amount: "6.66",
      reprint_count: 7,
    },
  ],
  message: "ok",
  check_ok: true,
};

describe("useWechatState", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads draft-box snapshot without forcing publish-history refresh", async () => {
    const onBrowserSessionChange = vi.fn();
    const reloadBriefs = vi.fn().mockResolvedValue(undefined);
    mockedApi.getWeChatMapping.mockResolvedValue({
      item: {
        checked_at: "2026-05-12T10:00:00+08:00",
        remote_count: 0,
        matched_count: 0,
        missing_count: 0,
        message: "empty",
        items: [],
        mapping_rows: [],
      },
    });
    mockedApi.getPublishTasks.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_more: false,
    });
    mockedApi.getBrowserSession.mockResolvedValue({ item: browserSession });
    mockedApi.checkWeChatDraftBox.mockResolvedValue({
      item: {
        checked_at: "2026-05-12T10:00:00+08:00",
        remote_count: 0,
        matched_count: 0,
        missing_count: 0,
        items: [],
        message: "checked",
        check_ok: true,
      },
    });

    const { result } = renderHook(() =>
      useWechatState({
        browserSession: null,
        onBrowserSessionChange,
        initialPublishTasksPageSize: 20,
        onError: vi.fn(),
        onToast: vi.fn(),
        onReloadBriefs: reloadBriefs,
        onReloadOverview: vi.fn().mockResolvedValue(undefined),
      }),
    );

    await act(async () => {
      await result.current.loadDraftBoxData(false);
    });

    expect(mockedApi.checkWeChatDraftBox).not.toHaveBeenCalled();
    expect(mockedApi.getWeChatMapping).toHaveBeenCalledTimes(1);
    expect(result.current.wechatMapping?.message).toBe("empty");
    expect(reloadBriefs).toHaveBeenCalledTimes(1);
    expect(onBrowserSessionChange).toHaveBeenCalledWith(expect.objectContaining({ resident_page: "home" }));
  });

  it("refreshes publish history and cascades local refresh callbacks", async () => {
    const reloadBriefs = vi.fn().mockResolvedValue(undefined);
    const onToast = vi.fn();
    mockedApi.checkWeChatPublishHistory.mockResolvedValue({ item: publishHistory });
    mockedApi.getBrowserSession.mockResolvedValue({ item: browserSession });

    const { result } = renderHook(() =>
      useWechatState({
        browserSession: null,
        onBrowserSessionChange: vi.fn(),
        initialPublishTasksPageSize: 20,
        onError: vi.fn(),
        onToast,
        onReloadBriefs: reloadBriefs,
        onReloadOverview: vi.fn().mockResolvedValue(undefined),
      }),
    );

    await act(async () => {
      await result.current.handleRefreshWeChatPublishHistory();
    });

    expect(mockedApi.checkWeChatPublishHistory).toHaveBeenCalledTimes(1);
    expect(mockedApi.getBrowserSession).toHaveBeenCalledTimes(1);
    expect(reloadBriefs).toHaveBeenCalledTimes(1);
    expect(result.current.wechatPublishHistory?.record_count).toBe(1);
    expect(result.current.wechatPublishHistory?.overview?.total_users).toBe(26);
    expect(onToast).toHaveBeenCalledWith("ok", "success");
  });
});
