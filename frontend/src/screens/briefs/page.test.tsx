import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BriefItem } from "../../types";
import { BriefsPage } from "./page";

function brief(overrides: Partial<BriefItem> = {}): BriefItem {
  return {
    id: "brief-1",
    event_id: "evt-1",
    deep_dive_id: "dd-1",
    brief_level: "enhanced",
    stage: "prepared",
    title: "OpenAI Health 正式发布",
    one_line: "一句话结论",
    why_it_matters: "为什么重要",
    facts: ["事实 1", "事实 2"],
    quotes: ["引用 1"],
    timeline: [],
    entity_names: ["OpenAI", "Apple"],
    source_links: ["https://example.com/a", "https://example.com/b"],
    risk_notes: [],
    prompt_package_markdown: "pkg",
    wechat_markdown: "# article",
    wechat_html: "<h1>article</h1>",
    wechat_target_id: null,
    wechat_editor_url: "https://mp.weixin.qq.com/editor",
    wechat_remote_appmsg_id: null,
    preview_url: "https://example.com/preview",
    delivery_status: null,
    delivery_attempt_count: 0,
    last_delivery_attempt_at: null,
    last_verified_at: null,
    last_delivery_error_kind: null,
    needs_resync: false,
    last_synced_revision: null,
    last_successful_upload_at: null,
    last_error: null,
    updated_at: "2026-05-05T12:00:00+00:00",
    driver_label: "rule",
    record_status: "local_only",
    record_exception: null,
    draft_remote_updated_at: null,
    publish_record_published_at: null,
    workflow_mode: "agent",
    workflow_session_id: "agentwf-1",
    read_count: 1200,
    like_count: 45,
    share_count: 12,
    recommend_count: 3,
    comment_count: 2,
    highlight_count: 1,
    tip_amount: "0.00",
    reprint_count: 0,
    metrics_fetched_at: "2026-05-05T13:00:00+00:00",
    included_events: [],
    ...overrides,
  };
}

function renderPage(overrides: Partial<React.ComponentProps<typeof BriefsPage>> = {}) {
  const props: React.ComponentProps<typeof BriefsPage> = {
    briefs: [brief()],
    page: 1,
    pageSize: 20,
    total: 1,
    view: "all",
    workflowView: "all",
    searchTerm: "",
    recordCounts: { all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 },
    agentWorkflows: [
      {
        workflow_session_id: "agentwf-1",
        status: "running",
        current_step: "article_saved",
        target_platforms: ["wechat"],
        started_at: "2026-05-05T11:00:00+00:00",
        updated_at: "2026-05-05T12:00:00+00:00",
      },
    ],
    loading: false,
    busyBriefId: null,
    creatingDailyDigest: false,
    abandoningWorkflowId: null,
    loadingBriefDetailId: null,
    onViewChange: vi.fn(),
    onWorkflowViewChange: vi.fn(),
    onSearchChange: vi.fn(),
    onPageChange: vi.fn(),
    onPageSizeChange: vi.fn(),
    onRefreshBrief: vi.fn().mockResolvedValue(undefined),
    onCopyBrief: vi.fn().mockResolvedValue(undefined),
    onCopyPackage: vi.fn().mockResolvedValue(undefined),
    onSyncBrief: vi.fn().mockResolvedValue(undefined),
    onPublishBrief: vi.fn().mockResolvedValue(undefined),
    onDeleteBrief: vi.fn().mockResolvedValue(undefined),
    onAbandonAgentWorkflow: vi.fn().mockResolvedValue(undefined),
    onCreateDailyDigest: vi.fn().mockResolvedValue(undefined),
    onLoadBriefDetail: vi.fn().mockResolvedValue(null),
    ...overrides,
  };
  return { props, ...render(<BriefsPage {...props} />) };
}

describe("BriefsPage redesign", () => {
  it("renders counts, merged filter bar, status-colored card, and compact card summary", () => {
    const { container } = renderPage({ total: 9, recordCounts: { all: 9, local_only: 4, draft_synced: 3, published: 1, exceptions: 1 } });

    expect(screen.getByRole("heading", { name: "简报/文章" })).toBeInTheDocument();
    expect(screen.getByText("9 篇文章")).toBeInTheDocument();
    expect(screen.getByLabelText("来源筛选")).toBeInTheDocument();
    expect(screen.getByLabelText("状态筛选")).toBeInTheDocument();
    expect(screen.getByText("第 1 / 1 页")).toBeInTheDocument();
    expect(container.querySelector(".briefs-filter-bar")).toBeTruthy();
    expect(container.querySelector(".briefs-card.severity-prepared")).toBeTruthy();
    expect(screen.getByText("一句话结论")).toBeInTheDocument();
    expect(screen.getByText("事实 2")).toBeInTheDocument();
    expect(screen.getByText("来源 2")).toBeInTheDocument();
    expect(screen.getByText("引文 1")).toBeInTheDocument();
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
  });

  it("wires select filters, search, pagination, and expansion detail loading", () => {
    const onViewChange = vi.fn();
    const onWorkflowViewChange = vi.fn();
    const onSearchChange = vi.fn();
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();
    const onLoadBriefDetail = vi.fn().mockResolvedValue(null);
    const { container } = renderPage({
      total: 50,
      onViewChange,
      onWorkflowViewChange,
      onSearchChange,
      onPageChange,
      onPageSizeChange,
      onLoadBriefDetail,
    });

    fireEvent.change(screen.getByLabelText("来源筛选"), { target: { value: "agent" } });
    expect(onWorkflowViewChange).toHaveBeenCalledWith("agent");

    fireEvent.change(screen.getByLabelText("状态筛选"), { target: { value: "local_only" } });
    expect(onViewChange).toHaveBeenCalledWith("local_only");

    fireEvent.change(screen.getByPlaceholderText("搜索标题、结论、价值判断"), { target: { value: "OpenAI" } });
    expect(onSearchChange).toHaveBeenCalledWith("OpenAI");

    fireEvent.click(screen.getByLabelText("下一页"));
    expect(onPageChange).toHaveBeenCalledWith(2);

    fireEvent.change(screen.getByDisplayValue("20"), { target: { value: "50" } });
    expect(onPageSizeChange).toHaveBeenCalledWith(50);

    fireEvent.click(screen.getByRole("button", { name: "查看详情 ▼" }));
    expect(container.querySelector(".briefs-detail")).toBeTruthy();
    expect(onLoadBriefDetail).toHaveBeenCalledWith("brief-1");
  });

  it("filters current page items by workflow, status, and search term", () => {
    renderPage({
      briefs: [
        brief({ id: "brief-agent", title: "OpenAI Health 正式发布", workflow_mode: "agent", record_status: "local_only" }),
        brief({ id: "brief-traditional", title: "华为云发布新方案", workflow_mode: "traditional", record_status: "draft_synced" }),
        brief({ id: "brief-published", title: "苹果芯片路线", workflow_mode: "traditional", record_status: "published" }),
      ],
      workflowView: "traditional",
      view: "draft_synced",
      searchTerm: "华为",
      total: 3,
      recordCounts: { all: 3, local_only: 1, draft_synced: 1, published: 1, exceptions: 0 },
    });

    expect(screen.getByText("华为云发布新方案")).toBeInTheDocument();
    expect(screen.queryByText("OpenAI Health 正式发布")).not.toBeInTheDocument();
    expect(screen.queryByText("苹果芯片路线")).not.toBeInTheDocument();
  });

  it("shows skeleton loading and distinct empty states", () => {
    const { container, rerender, props } = renderPage({ briefs: [], total: 0, loading: true, recordCounts: { all: 0, local_only: 0, draft_synced: 0, published: 0, exceptions: 0 } });
    expect(container.querySelectorAll(".skeleton-card")).toHaveLength(4);

    rerender(<BriefsPage {...props} loading={false} />);
    expect(screen.getByText("还没有生成简报。")).toBeInTheDocument();

    rerender(<BriefsPage {...props} briefs={[brief()]} total={1} loading={false} searchTerm="missing" recordCounts={{ all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 }} />);
    expect(screen.getByText("没有匹配的简报。")).toBeInTheDocument();
  });

  it("confirms deletion before calling the delete callback", () => {
    const onDeleteBrief = vi.fn().mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { rerender, props } = renderPage({ onDeleteBrief });

    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(confirmSpy).toHaveBeenCalledWith("确认删除《OpenAI Health 正式发布》？此操作不可撤销。");
    expect(onDeleteBrief).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    rerender(<BriefsPage {...props} onDeleteBrief={onDeleteBrief} />);
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(onDeleteBrief).toHaveBeenCalledWith(props.briefs[0]);
    confirmSpy.mockRestore();
  });

  it("confirms before entering the WeChat publish verification flow", () => {
    const onPublishBrief = vi.fn().mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { rerender, props } = renderPage({ onPublishBrief });

    fireEvent.click(screen.getByRole("button", { name: "发表到验证" }));
    expect(confirmSpy).toHaveBeenCalledWith("确认进入《OpenAI Health 正式发布》的微信发表流程？系统会停在微信验证二维码。");
    expect(onPublishBrief).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    rerender(<BriefsPage {...props} onPublishBrief={onPublishBrief} />);
    fireEvent.click(screen.getByRole("button", { name: "发表到验证" }));
    expect(onPublishBrief).toHaveBeenCalledWith(props.briefs[0]);
    confirmSpy.mockRestore();
  });

  it("maps severity classes for synced, published, and exception cards", () => {
    const { container } = renderPage({
      briefs: [
        brief({ id: "synced", title: "已同步文章", record_status: "draft_synced", workflow_session_id: null }),
        brief({ id: "published", title: "已发表文章", record_status: "published", workflow_session_id: null }),
        brief({ id: "failed", title: "异常文章", record_status: "local_only", record_exception: "draft_missing", workflow_session_id: null }),
        brief({ id: "failed-stage", title: "生成失败文章", stage: "failed", record_status: "local_only", workflow_session_id: null }),
      ],
      recordCounts: { all: 3, local_only: 1, draft_synced: 1, published: 1, exceptions: 1 },
      total: 3,
    });

    expect(container.querySelector(".briefs-card.severity-synced")).toBeTruthy();
    expect(container.querySelector(".briefs-card.severity-published")).toBeTruthy();
    expect(container.querySelectorAll(".briefs-card.severity-failed")).toHaveLength(2);
  });

  it("renders reading data only in the expanded detail area", () => {
    renderPage();

    expect(screen.queryByText("阅读数据")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看详情 ▼" }));
    expect(screen.getByText("阅读数据")).toBeInTheDocument();
    expect(screen.getByText("阅读 1200")).toBeInTheDocument();
    expect(screen.getByText("点赞 45")).toBeInTheDocument();
    expect(screen.getByText("分享 12")).toBeInTheDocument();
    expect(screen.getByText("留言 2")).toBeInTheDocument();
  });
});
