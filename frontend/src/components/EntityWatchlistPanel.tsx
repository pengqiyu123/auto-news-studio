import { formatDateTime } from "../lib/time";
import type { EntityWatchlistItem, EntityWatchlistSummaryItem } from "../types";

interface EntityOption {
  entity_id: string;
  entity_name: string;
}

interface EntityWatchlistPanelProps {
  items: EntityWatchlistItem[];
  summary: EntityWatchlistSummaryItem[];
  availableEntities: EntityOption[];
  selectedEntityId: string;
  onSelectEntity: (entityId: string) => void;
  onUpdateWatchlist: (items: EntityWatchlistItem[]) => Promise<void>;
  onOpenEntity: (entityId: string) => void;
}

export function EntityWatchlistPanel({
  items,
  summary,
  availableEntities,
  selectedEntityId,
  onSelectEntity,
  onUpdateWatchlist,
  onOpenEntity,
}: EntityWatchlistPanelProps) {
  const watchlistedIds = new Set(items.map((item) => item.entity_id));
  const selectedOption = availableEntities.find((item) => item.entity_id === selectedEntityId) ?? null;
  const canAdd = Boolean(selectedOption && !watchlistedIds.has(selectedOption.entity_id));
  const canRemove = Boolean(selectedOption && watchlistedIds.has(selectedOption.entity_id));
  const addOptions = availableEntities.filter((item) => !watchlistedIds.has(item.entity_id));

  async function handleAdd() {
    if (!selectedOption || watchlistedIds.has(selectedOption.entity_id)) {
      return;
    }
    await onUpdateWatchlist([
      ...items,
      {
        entity_id: selectedOption.entity_id,
        entity_name: selectedOption.entity_name,
        entity_type: "",
        watchlisted: true,
        added_at: null,
      },
    ]);
  }

  async function handleRemove(entityId: string) {
    await onUpdateWatchlist(items.filter((item) => item.entity_id !== entityId));
  }

  return (
    <aside className="panel entity-watchlist-panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">重点监控实体</p>
          <h2>盯住你关心的品牌与人物</h2>
        </div>
      </div>

      <div className="entity-watchlist-toolbar">
        <select value={selectedEntityId} onChange={(event) => onSelectEntity(event.target.value)}>
          <option value="all">选择实体</option>
          {availableEntities.map((item) => (
            <option key={item.entity_id} value={item.entity_id}>
              {item.entity_name}
            </option>
          ))}
        </select>
        <button type="button" className="ghost-button compact" disabled={!canAdd} onClick={() => void handleAdd()}>
          加入监控
        </button>
      </div>

      {selectedOption && canRemove ? (
        <div className="entity-watchlist-inline-tip">
          <span>当前筛选：{selectedOption.entity_name}</span>
          <button type="button" className="ghost-button compact" onClick={() => void handleRemove(selectedOption.entity_id)}>
            移出
          </button>
        </div>
      ) : null}

      <div className="entity-watchlist-list">
        {summary.length ? summary.map((item) => (
          <article key={item.entity_id} className="entity-watchlist-card">
            <div className="entity-watchlist-head">
              <div>
                <strong>{item.entity_name}</strong>
                <p>{item.entity_type}</p>
              </div>
              <div className="entity-watchlist-actions">
                <button type="button" className="ghost-button compact" onClick={() => onOpenEntity(item.entity_id)}>
                  查看
                </button>
                <button type="button" className="ghost-button compact" onClick={() => void handleRemove(item.entity_id)}>
                  移出
                </button>
              </div>
            </div>
            <div className="entity-watchlist-stats">
              <span>事件 {item.event_count}</span>
              <span>预警 {item.alert_count}</span>
              <span>上升 {item.rising_count}</span>
              <span>爆发 {item.breakout_count}</span>
            </div>
            <p className="subtle">
              最近出现 {formatDateTime(item.last_seen_at, { fallback: "暂无" })}
            </p>
          </article>
        )) : (
          <p className="empty-state">
            {addOptions.length ? "先从当前结果里挑一个实体加入监控。" : "当前结果里还没有可监控的实体。"}
          </p>
        )}
      </div>
    </aside>
  );
}
