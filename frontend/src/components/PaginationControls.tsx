import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationControlsProps {
  page: number;
  pageSize: number;
  total: number;
  currentCount: number;
  filteredCount?: number;
  itemLabel: string;
  loading?: boolean;
  note?: string;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

const PAGE_SIZE_OPTIONS = [20, 50, 100];

export function PaginationControls({
  page,
  pageSize,
  total,
  currentCount,
  filteredCount,
  itemLabel,
  loading = false,
  note,
  onPageChange,
  onPageSizeChange,
}: PaginationControlsProps) {
  const safePage = Math.max(1, page);
  const safePageSize = Math.max(1, pageSize);
  const pageCount = Math.max(1, Math.ceil(total / safePageSize) || 1);
  const canGoPrev = safePage > 1 && !loading;
  const canGoNext = safePage < pageCount && !loading;
  const hasFilteredCount = typeof filteredCount === "number";

  return (
    <div className="list-pagination">
      <div className="list-pagination-summary">
        <strong>第 {safePage} / {pageCount} 页</strong>
        <span>
          本页 {currentCount} {itemLabel}
          {hasFilteredCount ? `，筛后 ${filteredCount}` : ""}
          ，总计 {total}
        </span>
        {note ? <p>{note}</p> : null}
      </div>
      <div className="pagination-controls">
        <label className="pagination-page-size">
          <span>每页</span>
          <select
            value={safePageSize}
            disabled={loading}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {PAGE_SIZE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="ghost-button compact pagination-icon-button"
          onClick={() => onPageChange(safePage - 1)}
          disabled={!canGoPrev}
          title="上一页"
          aria-label="上一页"
        >
          <ChevronLeft size={16} />
        </button>
        <button
          type="button"
          className="ghost-button compact pagination-icon-button"
          onClick={() => onPageChange(safePage + 1)}
          disabled={!canGoNext}
          title="下一页"
          aria-label="下一页"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
