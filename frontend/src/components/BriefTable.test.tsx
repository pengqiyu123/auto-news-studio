import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BriefTable } from "./BriefTable";
import type { BriefItem } from "../types";

const brief: BriefItem = {
  id: "brief-1",
  event_id: "evt-1",
  deep_dive_id: "dd-1",
  brief_level: "enhanced",
  stage: "prepared",
  title: "OpenAI Health 正式发布",
  one_line: "一句话",
  why_it_matters: "为什么重要",
  facts: ["事实 1"],
  quotes: [],
  timeline: [],
  entity_names: ["OpenAI"],
  source_links: ["https://example.com"],
  risk_notes: [],
  prompt_package_markdown: "pkg",
  wechat_markdown: "# article",
  wechat_html: "<h1>article</h1>",
  updated_at: "2026-05-05T12:00:00+00:00",
  record_status: "local_only",
  record_exception: null,
  draft_remote_updated_at: null,
  publish_record_published_at: null,
  workflow_mode: "agent",
  workflow_session_id: "agentwf-1",
};

describe("BriefTable", () => {
  it("wires stage filter, search, and pagination controls to parent callbacks", () => {
    const onViewChange = vi.fn();
    const onWorkflowViewChange = vi.fn();
    const onSearchChange = vi.fn();
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();

    render(
      <BriefTable
        briefs={[brief]}
        page={1}
        pageSize={20}
        total={50}
        view="all"
        workflowView="all"
        searchTerm=""
        recordCounts={{ all: 50, local_only: 20, draft_synced: 20, published: 8, exceptions: 2 }}
        agentWorkflows={[{ workflow_session_id: "agentwf-1", status: "running", current_step: "article_saved", target_platforms: ["wechat"], started_at: "2026-05-13T10:00:00+08:00", updated_at: "2026-05-13T10:01:00+08:00" }]}
        onViewChange={onViewChange}
        onWorkflowViewChange={onWorkflowViewChange}
        onSearchChange={onSearchChange}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
        onRefreshBrief={async () => {}}
        onCopyBrief={async () => {}}
        onCopyPackage={async () => {}}
        onSyncBrief={async () => {}}
        onDeleteBrief={async () => {}}
        onAbandonAgentWorkflow={async () => {}}
        onCreateDailyDigest={async () => {}}
        onLoadBriefDetail={async () => null}
      />,
    );

    fireEvent.click(screen.getAllByRole("button", { name: /仅本地/ })[0]);
    expect(onViewChange).toHaveBeenCalledWith("local_only");

    fireEvent.click(screen.getAllByRole("button", { name: /Agent/ })[0]);
    expect(onWorkflowViewChange).toHaveBeenCalledWith("agent");

    fireEvent.change(screen.getByPlaceholderText("搜索标题、结论、价值判断"), { target: { value: "OpenAI" } });
    expect(onSearchChange).toHaveBeenCalledWith("OpenAI");

    fireEvent.click(screen.getByLabelText("下一页"));
    expect(onPageChange).toHaveBeenCalledWith(2);

    fireEvent.change(screen.getByDisplayValue("20"), { target: { value: "50" } });
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
  });

  it("shows the manual daily digest action and disables it after today's digest exists", () => {
    const onCreateDailyDigest = vi.fn();
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;

    const { rerender } = render(
      <BriefTable
        briefs={[brief]}
        page={1}
        pageSize={20}
        total={1}
        view="all"
        workflowView="all"
        searchTerm=""
        recordCounts={{ all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 }}
        agentWorkflows={[]}
        onViewChange={() => {}}
        onWorkflowViewChange={() => {}}
        onSearchChange={() => {}}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
        onRefreshBrief={async () => {}}
        onCopyBrief={async () => {}}
        onCopyPackage={async () => {}}
        onSyncBrief={async () => {}}
        onDeleteBrief={async () => {}}
        onAbandonAgentWorkflow={async () => {}}
        onCreateDailyDigest={onCreateDailyDigest}
        onLoadBriefDetail={async () => null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "生成今日速递" }));
    expect(onCreateDailyDigest).toHaveBeenCalledTimes(1);

    rerender(
      <BriefTable
        briefs={[{ ...brief, title: `今日科技速递｜${today}` }]}
        page={1}
        pageSize={20}
        total={1}
        view="all"
        workflowView="all"
        searchTerm=""
        recordCounts={{ all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 }}
        agentWorkflows={[]}
        onViewChange={() => {}}
        onWorkflowViewChange={() => {}}
        onSearchChange={() => {}}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
        onRefreshBrief={async () => {}}
        onCopyBrief={async () => {}}
        onCopyPackage={async () => {}}
        onSyncBrief={async () => {}}
        onDeleteBrief={async () => {}}
        onAbandonAgentWorkflow={async () => {}}
        onCreateDailyDigest={onCreateDailyDigest}
        onLoadBriefDetail={async () => null}
      />,
    );

    expect(screen.getByRole("button", { name: "今日速递已生成" })).toBeDisabled();
  });

  it("renders included events only for digest brief details", () => {
    const digestBrief: BriefItem = {
      ...brief,
      id: "brief-digest",
      title: "今日科技速递｜2026-05-26",
      workflow_mode: "traditional",
      brief_level: "rule",
      included_events: [
        {
          event_id: "evt-1",
          title: "华为发布 AI DC 全栈方案",
          alert_state: "breakout",
          source_count: 3,
          deep_dive_status: "ready",
          representative_link: "https://example.com/huawei-ai-dc",
        },
        {
          event_id: "evt-2",
          title: "OpenAI 推出企业管理更新",
          alert_state: "rising",
          source_count: 2,
          deep_dive_status: "ready",
          representative_link: "https://example.com/openai-enterprise",
        },
      ],
    };

    const { rerender } = render(
      <BriefTable
        briefs={[brief]}
        page={1}
        pageSize={20}
        total={1}
        view="all"
        workflowView="all"
        searchTerm=""
        recordCounts={{ all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 }}
        agentWorkflows={[]}
        onViewChange={() => {}}
        onWorkflowViewChange={() => {}}
        onSearchChange={() => {}}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
        onRefreshBrief={async () => {}}
        onCopyBrief={async () => {}}
        onCopyPackage={async () => {}}
        onSyncBrief={async () => {}}
        onDeleteBrief={async () => {}}
        onAbandonAgentWorkflow={async () => {}}
        onCreateDailyDigest={async () => {}}
        onLoadBriefDetail={async () => null}
      />,
    );

    expect(screen.queryByText("收录事件")).not.toBeInTheDocument();

    rerender(
      <BriefTable
        briefs={[digestBrief]}
        page={1}
        pageSize={20}
        total={1}
        view="all"
        workflowView="all"
        searchTerm=""
        recordCounts={{ all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 }}
        agentWorkflows={[]}
        onViewChange={() => {}}
        onWorkflowViewChange={() => {}}
        onSearchChange={() => {}}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
        onRefreshBrief={async () => {}}
        onCopyBrief={async () => {}}
        onCopyPackage={async () => {}}
        onSyncBrief={async () => {}}
        onDeleteBrief={async () => {}}
        onAbandonAgentWorkflow={async () => {}}
        onCreateDailyDigest={async () => {}}
        onLoadBriefDetail={async () => null}
      />,
    );

    expect(screen.getByText("收录事件")).toBeInTheDocument();
    expect(screen.getByText("华为发布 AI DC 全栈方案")).toBeInTheDocument();
    expect(screen.getByText("breakout")).toBeInTheDocument();
    expect(screen.getByText("来源 3")).toBeInTheDocument();
    expect(screen.getAllByText("深挖 ready")[0]).toBeInTheDocument();
  });

  it("shows abandon action for unfinished agent workflows only", () => {
    const onAbandonAgentWorkflow = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { rerender } = render(
      <BriefTable
        briefs={[brief]}
        page={1}
        pageSize={20}
        total={1}
        view="all"
        workflowView="all"
        searchTerm=""
        recordCounts={{ all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 }}
        agentWorkflows={[{ workflow_session_id: "agentwf-1", status: "failed", current_step: "article_saved", target_platforms: ["wechat"], started_at: "2026-05-13T10:00:00+08:00", updated_at: "2026-05-13T10:01:00+08:00" }]}
        onViewChange={() => {}}
        onWorkflowViewChange={() => {}}
        onSearchChange={() => {}}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
        onRefreshBrief={async () => {}}
        onCopyBrief={async () => {}}
        onCopyPackage={async () => {}}
        onSyncBrief={async () => {}}
        onDeleteBrief={async () => {}}
        onAbandonAgentWorkflow={onAbandonAgentWorkflow}
        onCreateDailyDigest={async () => {}}
        onLoadBriefDetail={async () => null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "放弃 Agent 会话" }));
    expect(onAbandonAgentWorkflow).toHaveBeenCalledWith("agentwf-1");

    rerender(
      <BriefTable
        briefs={[brief]}
        page={1}
        pageSize={20}
        total={1}
        view="all"
        workflowView="all"
        searchTerm=""
        recordCounts={{ all: 1, local_only: 1, draft_synced: 0, published: 0, exceptions: 0 }}
        agentWorkflows={[{ workflow_session_id: "agentwf-1", status: "abandoned", current_step: "article_saved", target_platforms: ["wechat"], started_at: "2026-05-13T10:00:00+08:00", updated_at: "2026-05-13T10:02:00+08:00", finished_at: "2026-05-13T10:02:00+08:00" }]}
        onViewChange={() => {}}
        onWorkflowViewChange={() => {}}
        onSearchChange={() => {}}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
        onRefreshBrief={async () => {}}
        onCopyBrief={async () => {}}
        onCopyPackage={async () => {}}
        onSyncBrief={async () => {}}
        onDeleteBrief={async () => {}}
        onAbandonAgentWorkflow={onAbandonAgentWorkflow}
        onCreateDailyDigest={async () => {}}
        onLoadBriefDetail={async () => null}
      />,
    );

    expect(screen.queryByRole("button", { name: "放弃 Agent 会话" })).not.toBeInTheDocument();
  });
});
