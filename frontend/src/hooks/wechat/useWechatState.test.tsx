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
  items: [],
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
        onReloadBriefs: vi.fn().mockResolvedValue(undefined),
        onReloadOverview: vi.fn().mockResolvedValue(undefined),
      }),
    );

    await act(async () => {
      await result.current.loadDraftBoxData(false);
    });

    expect(mockedApi.checkWeChatDraftBox).not.toHaveBeenCalled();
    expect(mockedApi.getWeChatMapping).toHaveBeenCalledTimes(1);
    expect(result.current.wechatMapping?.message).toBe("empty");
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
    expect(onToast).toHaveBeenCalledWith("ok", "success");
  });
});
