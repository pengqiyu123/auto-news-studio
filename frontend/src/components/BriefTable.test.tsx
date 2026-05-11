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
};

describe("BriefTable", () => {
  it("wires stage filter, search, and pagination controls to parent callbacks", () => {
    const onViewChange = vi.fn();
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
        searchTerm=""
        recordCounts={{ all: 50, local_only: 20, draft_synced: 20, published: 8, exceptions: 2 }}
        onViewChange={onViewChange}
        onSearchChange={onSearchChange}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
        onRefreshBrief={async () => {}}
        onCopyBrief={async () => {}}
        onCopyPackage={async () => {}}
        onSyncBrief={async () => {}}
        onDeleteBrief={async () => {}}
      />,
    );

    fireEvent.click(screen.getAllByRole("button", { name: /仅本地/ })[0]);
    expect(onViewChange).toHaveBeenCalledWith("local_only");

    fireEvent.change(screen.getByPlaceholderText("搜索标题、结论、价值判断"), { target: { value: "OpenAI" } });
    expect(onSearchChange).toHaveBeenCalledWith("OpenAI");

    fireEvent.click(screen.getByLabelText("下一页"));
    expect(onPageChange).toHaveBeenCalledWith(2);

    fireEvent.change(screen.getByDisplayValue("20"), { target: { value: "50" } });
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
  });
});
