import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PaginationControls } from "./PaginationControls";

describe("PaginationControls", () => {
  it("changes page and page size with proper disabled states", () => {
    const onPageChange = vi.fn();
    const onPageSizeChange = vi.fn();

    render(
      <PaginationControls
        page={2}
        pageSize={20}
        total={90}
        currentCount={20}
        itemLabel="条"
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />,
    );

    fireEvent.click(screen.getByLabelText("上一页"));
    expect(onPageChange).toHaveBeenCalledWith(1);

    fireEvent.click(screen.getByLabelText("下一页"));
    expect(onPageChange).toHaveBeenCalledWith(3);

    fireEvent.change(screen.getByDisplayValue("20"), { target: { value: "50" } });
    expect(onPageSizeChange).toHaveBeenCalledWith(50);
  });

  it("disables forward button on last page while loading", () => {
    render(
      <PaginationControls
        page={5}
        pageSize={20}
        total={100}
        currentCount={20}
        itemLabel="条"
        loading
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );

    expect(screen.getByLabelText("上一页")).toBeDisabled();
    expect(screen.getByLabelText("下一页")).toBeDisabled();
  });
});
