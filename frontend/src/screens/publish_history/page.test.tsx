import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { WeChatPublishHistorySnapshot } from "../../types";
import { PublishHistoryPage } from "./page";

function history(overrides: Partial<WeChatPublishHistorySnapshot> = {}): WeChatPublishHistorySnapshot {
  return {
    checked_at: "2026-05-28T10:00:00+08:00",
    record_count: 2,
    message: "抓取成功",
    check_ok: true,
    overview: {
      total_users: 1200,
      yesterday_reads: 3456,
      yesterday_shares: 78,
      yesterday_new_follows: 9,
      stats_window_label: "昨日",
      fetched_at: "2026-05-28T09:00:00+08:00",
    },
    items: [
      {
        title: "低空经济政策观察",
        url: "https://mp.weixin.qq.com/s/a",
        appmsg_id: "101",
        published_at: "2026-05-28 09:30",
        remote_key: "101",
        read_count: 900,
        like_count: 45,
        share_count: 12,
        recommend_count: 0,
        comment_count: 3,
        highlight_count: 0,
        tip_amount: "0.00",
        reprint_count: 0,
        thumbnail: "https://example.com/a.png",
      },
      {
        title: "AI 医疗支付更新",
        url: "https://mp.weixin.qq.com/s/b",
        appmsg_id: "102",
        published_at: "2026-05-27 19:00",
        remote_key: "102",
        read_count: 1200,
        like_count: 60,
        share_count: 18,
        recommend_count: 4,
        comment_count: 5,
        highlight_count: 1,
        tip_amount: "0.00",
        reprint_count: 2,
      },
    ],
    ...overrides,
  };
}

describe("PublishHistoryPage", () => {
  it("shows skeleton cards while loading before history is available", () => {
    const { container } = render(
      <PublishHistoryPage
        history={null}
        refreshing={false}
        loading
        onRefresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(container.querySelectorAll(".skeleton-card")).toHaveLength(4);
    expect(screen.queryByText("还没抓取发表记录。")).not.toBeInTheDocument();
  });

  it("renders four stats and independent publish cards", () => {
    const { container } = render(
      <PublishHistoryPage
        history={history()}
        refreshing={false}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    expect(screen.getByRole("heading", { name: "查看公众号内容表现" })).toBeInTheDocument();
    expect(container.querySelectorAll(".publish-history-stat")).toHaveLength(4);
    expect(screen.getByText("发表 2 条")).toBeInTheDocument();
    expect(screen.getByText("总阅读 2100")).toBeInTheDocument();
    expect(screen.getByText("AI 医疗支付更新 · 阅读 1200")).toBeInTheDocument();
    expect(container.querySelectorAll(".wechat-publish-card")).toHaveLength(2);
    expect(container.querySelector(".publish-history-list .wechat-publish-card")).toBeTruthy();
    expect(screen.getByText("阅读 900 · 赞 45 · 分享 12 · 留言 3")).toBeInTheDocument();
    expect(screen.getByText("发表于 2026-05-28 09:30")).toBeInTheDocument();
    expect(screen.getAllByText("打开原文").length).toBeGreaterThan(0);
  });

  it("uses overview fallback and distinguishes empty states", () => {
    const { rerender } = render(
      <PublishHistoryPage
        history={null}
        refreshing={false}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    expect(screen.getByText("还没抓取发表记录。")).toBeInTheDocument();

    rerender(
      <PublishHistoryPage
        history={history({ record_count: 0, items: [], overview: null, message: "没有记录" })}
        refreshing={false}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
      />,
    );
    expect(screen.getByText("已检查，但没有发表记录。")).toBeInTheDocument();
    expect(screen.getByText("总阅读 -")).toBeInTheDocument();
    expect(screen.getByText("暂无最佳文章")).toBeInTheDocument();
  });

  it("wires refresh button state", () => {
    const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<PublishHistoryPage history={history()} refreshing onRefresh={onRefresh} />);

    fireEvent.click(screen.getByRole("button", { name: "刷新中..." }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
