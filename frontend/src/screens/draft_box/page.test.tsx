import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { BriefItem, BrowserSessionState, PublishTask, WeChatMappingSnapshot } from "../../types";
import { DraftBoxPage } from "./page";

const browserSession: BrowserSessionState = {
  platform: "wechat_mp",
  browser_name: "chromium",
  user_data_dir: "profile",
  logged_in: true,
  selectors_version: "v1",
  sidecar_health: "healthy",
  manager_alive: true,
  window_state: "restored",
  resident_page: "drafts",
  busy: false,
};

function brief(overrides: Partial<BriefItem> = {}): BriefItem {
  return {
    id: "brief-1",
    event_id: "evt-1",
    deep_dive_id: "dd-1",
    brief_level: "enhanced",
    stage: "prepared",
    title: "本地待同步文章",
    one_line: "本地摘要",
    why_it_matters: "值得关注",
    facts: ["事实"],
    quotes: ["引用"],
    timeline: [],
    entity_names: ["OpenAI"],
    source_links: ["https://example.com/source"],
    risk_notes: [],
    prompt_package_markdown: "pkg",
    wechat_markdown: "# article",
    wechat_html: "<h1>article</h1>",
    updated_at: "2026-05-28T09:00:00+08:00",
    record_status: "local_only",
    record_exception: null,
    draft_remote_updated_at: null,
    publish_record_published_at: null,
    workflow_mode: "agent",
    workflow_session_id: "wf-1",
    ...overrides,
  };
}

function mapping(overrides: Partial<WeChatMappingSnapshot> = {}): WeChatMappingSnapshot {
  return {
    checked_at: "2026-05-28T10:00:00+08:00",
    remote_count: 2,
    matched_count: 1,
    missing_count: 1,
    message: "映射完成",
    items: [
      {
        title: "已匹配远程文章",
        url: "https://mp.weixin.qq.com/s/matched",
        appmsg_id: "matched",
        remote_key: "remote-matched",
        updated_at: "2026-05-28 09:30",
      },
      {
        title: "仅微信端草稿",
        url: "https://mp.weixin.qq.com/s/remote-only",
        appmsg_id: "remote-only",
        remote_key: "remote-only",
        updated_at: "2026-05-28 09:45",
      },
    ],
    mapping_rows: [
      {
        remote_title: "已匹配远程文章",
        remote_key: "remote-matched",
        remote_appmsg_id: "matched",
        remote_url: "https://mp.weixin.qq.com/s/matched",
        remote_updated_at: "2026-05-28 09:30",
        local_brief_id: "brief-matched",
        local_brief_title: "已匹配远程文章",
        local_stage: "synced",
        mapping_status: "matched",
      },
      {
        remote_title: "仅微信端草稿",
        remote_key: "remote-only",
        remote_appmsg_id: "remote-only",
        remote_url: "https://mp.weixin.qq.com/s/remote-only",
        remote_updated_at: "2026-05-28 09:45",
        local_brief_id: null,
        local_brief_title: null,
        local_stage: null,
        mapping_status: "remote_only",
      },
    ],
    ...overrides,
  };
}

function publishTask(overrides: Partial<PublishTask> = {}): PublishTask {
  return {
    id: "task-1",
    target_id: "brief-1",
    action: "sync_wechat_draft",
    status: "completed",
    stage: "done",
    message: "同步完成",
    triggered_by: "test",
    created_at: "2026-05-28T10:05:00+08:00",
    artifacts: [],
    step_logs: ["打开草稿箱"],
    selector_profile: "v1",
    ...overrides,
  };
}

function renderPage(overrides: Partial<React.ComponentProps<typeof DraftBoxPage>> = {}) {
  const props: React.ComponentProps<typeof DraftBoxPage> = {
    mapping: mapping(),
    briefs: [
      brief({ id: "brief-matched", title: "已匹配远程文章", record_status: "draft_synced", draft_remote_updated_at: "2026-05-28T09:30:00+08:00" }),
      brief(),
      brief({ id: "brief-exception", title: "异常本地文章", record_status: "draft_synced", record_exception: "draft_missing" }),
    ],
    agentWorkflows: [{ workflow_session_id: "wf-1", status: "running", current_step: "article_saved", target_platforms: ["wechat"], started_at: "2026-05-28T08:00:00+08:00", updated_at: "2026-05-28T09:00:00+08:00" }],
    localBriefCount: 3,
    browserSession,
    publishTasks: [publishTask()],
    publishTasksPage: 1,
    publishTasksPageSize: 20,
    publishTasksTotal: 1,
    refreshing: false,
    loading: false,
    deletingRemoteId: null,
    loadingBriefDetailId: null,
    onRefresh: vi.fn().mockResolvedValue(undefined),
    onDeleteRemote: vi.fn().mockResolvedValue(undefined),
    onSyncBrief: vi.fn().mockResolvedValue(undefined),
    onLoadBriefDetail: vi.fn().mockResolvedValue(null),
    onPublishTasksPageChange: vi.fn(),
    onPublishTasksPageSizeChange: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<DraftBoxPage {...props} />) };
}

describe("DraftBoxPage", () => {
  it("shows skeleton cards while loading before mapping is available", () => {
    const { container } = renderPage({ mapping: null, briefs: [], localBriefCount: 0, loading: true });

    expect(container.querySelectorAll(".skeleton-card")).toHaveLength(4);
    expect(screen.queryByText("当前还没有抓到微信端草稿。")).not.toBeInTheDocument();
  });

  it("renders browser state, mapping summary row, tabs, and unified remote cards", () => {
    const { container } = renderPage();

    expect(screen.getByRole("heading", { name: "管理本地与远程草稿" })).toBeInTheDocument();
    expect(screen.getByText("已登录")).toBeInTheDocument();
    expect(screen.getByText("已匹配 1")).toBeInTheDocument();
    expect(screen.getByText("仅微信 1")).toBeInTheDocument();
    expect(screen.getByText("仅本地 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "微信端 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "本地记录 3" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "待确认 3" })).toBeInTheDocument();
    expect(container.querySelectorAll(".draftbox-card")).toHaveLength(2);
    expect(container.querySelector(".draftbox-card.severity-synced")).toBeTruthy();
    expect(screen.getByText("仅微信端草稿")).toBeInTheDocument();
  });

  it("confirms before deleting a remote draft", () => {
    const onDeleteRemote = vi.fn().mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage({ onDeleteRemote });

    fireEvent.click(screen.getAllByRole("button", { name: "删除远端" })[0]);
    expect(confirmSpy).toHaveBeenCalledWith("确认删除微信远端草稿《已匹配远程文章》？此操作不可撤销。");
    expect(onDeleteRemote).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getAllByRole("button", { name: "删除远端" })[0]);
    expect(onDeleteRemote).toHaveBeenCalledWith("remote-matched");
    confirmSpy.mockRestore();
  });

  it("switches to local records and calls sync/detail callbacks", () => {
    const onSyncBrief = vi.fn().mockResolvedValue(undefined);
    const onLoadBriefDetail = vi.fn().mockResolvedValue(null);
    renderPage({ onSyncBrief, onLoadBriefDetail });

    fireEvent.click(screen.getByRole("button", { name: "本地记录 3" }));
    expect(screen.getByText("本地待同步文章")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "查看详情" })[0]);
    expect(onLoadBriefDetail).toHaveBeenCalledWith("brief-matched");
    fireEvent.click(screen.getAllByRole("button", { name: "同步微信" })[0]);
    expect(onSyncBrief).toHaveBeenCalledWith("brief-matched");
  });

  it("splits pending view into local pending and remote-only sections", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "待确认 3" }));
    expect(screen.getByRole("heading", { name: "本地待同步" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "仅微信端" })).toBeInTheDocument();
    expect(screen.getByText("本地待同步文章")).toBeInTheDocument();
    expect(screen.getByText("异常本地文章")).toBeInTheDocument();
    expect(screen.getByText("仅微信端草稿")).toBeInTheDocument();
  });

  it("renders operation records in a separated collapsible tasks panel", () => {
    const { container } = renderPage();

    expect(container.querySelector(".draftbox-tasks-panel")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "展开 (1)" }));
    expect(screen.getByText("上传到微信草稿箱")).toBeInTheDocument();
    expect(screen.getByText("同步完成")).toBeInTheDocument();
  });
});
