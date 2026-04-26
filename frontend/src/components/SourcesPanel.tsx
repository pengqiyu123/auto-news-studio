import { ChevronDown, RefreshCcw, Save } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDateTime } from "../lib/time";
import type { SourceConnector } from "../types";
import { SourceHealthBadge } from "./StatusBadge";

interface SourcesPanelProps {
  sources: SourceConnector[];
  syncing: boolean;
  savingSourceKey?: string | null;
  syncingSourceKey?: string | null;
  onSync: () => Promise<void>;
  onSyncOne: (sourceKey: string) => Promise<void>;
  onSave: (sourceKey: string, payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">) => Promise<void>;
}

const schedulePresets = [
  { label: "每 15 分钟", value: "*/15 * * * *" },
  { label: "每 20 分钟", value: "*/20 * * * *" },
  { label: "每 30 分钟", value: "*/30 * * * *" },
  { label: "每 45 分钟", value: "*/45 * * * *" },
  { label: "每小时", value: "0 * * * *" },
  { label: "每 4 小时", value: "0 */4 * * *" }
];

function formatSchedule(schedule: string) {
  const preset = schedulePresets.find((item) => item.value === schedule.trim());
  return preset?.label ?? "高级计划：原始 Cron";
}

export function SourcesPanel({ sources, syncing, savingSourceKey, syncingSourceKey, onSync, onSyncOne, onSave }: SourcesPanelProps) {
  const [drafts, setDrafts] = useState<Record<string, SourceConnector>>({});

  useEffect(() => {
    const next: Record<string, SourceConnector> = {};
    for (const source of sources) {
      next[source.key] = source;
    }
    setDrafts(next);
  }, [sources]);

  const updateDraft = <K extends keyof SourceConnector>(sourceKey: string, key: K, value: SourceConnector[K]) => {
    setDrafts((current) => ({
      ...current,
      [sourceKey]: {
        ...current[sourceKey],
        [key]: value
      }
    }));
  };

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">来源控制台</p>
          <h2>紧凑查看频率、健康状态和同步情况</h2>
          <p className="subtle">
            这里默认展示人类可读频率；原始 Cron 仍然保留在展开区，方便高级调整。
          </p>
        </div>
        <button type="button" className="ghost-button" onClick={() => void onSync()}>
          <RefreshCcw size={16} />
          {syncing ? "同步中..." : "立即采集来源"}
        </button>
      </div>

      <div className="source-table">
        <div className="source-table-head">
          <span>来源</span>
          <span>类型</span>
          <span>频率</span>
          <span>上次同步</span>
          <span>状态</span>
          <span>已采集</span>
          <span>启用</span>
        </div>

        {sources.map((source) => {
          const draft = drafts[source.key] ?? source;
          const saving = savingSourceKey === source.key;
          const syncingOne = syncingSourceKey === source.key;
          return (
            <details key={source.key} className="source-row-card">
              <summary className="source-row-summary">
                <div className="source-primary">
                  <strong>{source.name}</strong>
                  <p>{source.tags.join(" / ") || "未标注标签"}</p>
                </div>
                <span>{source.kind}</span>
                <span>{formatSchedule(source.schedule)}</span>
                <span>{formatDateTime(source.last_synced_at, { fallback: "暂无" })}</span>
                <span>
                  <SourceHealthBadge health={source.health_status} />
                </span>
                <span>{source.item_count}</span>
                <span>{draft.enabled ? "已启用" : "已停用"}</span>
                <ChevronDown size={16} className="summary-chevron" />
              </summary>

              <div className="source-row-detail">
                <div className="source-detail-top">
                  <div>
                    <p>驱动：{source.driver}</p>
                    <p>来源仓库：{source.origin_repo}</p>
                    <p>许可证：{source.origin_license}</p>
                    <p>健康详情：{source.health_detail || "暂无"}</p>
                    {source.last_error ? <p className="error-note">{source.last_error}</p> : null}
                  </div>
                  <label className="toggle-field inline-toggle">
                    <span>启用来源</span>
                    <input
                      type="checkbox"
                      checked={draft.enabled}
                      onChange={(event) => updateDraft(source.key, "enabled", event.target.checked)}
                    />
                  </label>
                </div>

                <div className="source-form-grid compact">
                  <label>
                    <span>频率预设</span>
                    <select
                      value={schedulePresets.some((item) => item.value === draft.schedule) ? draft.schedule : "__custom__"}
                      onChange={(event) => {
                        if (event.target.value !== "__custom__") {
                          updateDraft(source.key, "schedule", event.target.value);
                        }
                      }}
                    >
                      {schedulePresets.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                      <option value="__custom__">自定义 Cron</option>
                    </select>
                  </label>
                  <label>
                    <span>优先级</span>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={draft.priority}
                      onChange={(event) => updateDraft(source.key, "priority", Number(event.target.value))}
                    />
                  </label>
                  <label className="full-span">
                    <span>URL</span>
                    <input
                      value={draft.url ?? ""}
                      onChange={(event) => updateDraft(source.key, "url", event.target.value)}
                    />
                  </label>
                  <label className="full-span">
                    <span>标签</span>
                    <input
                      value={draft.tags.join(", ")}
                      onChange={(event) =>
                        updateDraft(
                          source.key,
                          "tags",
                          event.target.value
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean)
                        )
                      }
                    />
                  </label>
                  <label className="full-span">
                    <span>高级计划：原始 Cron</span>
                    <input
                      value={draft.schedule}
                      onChange={(event) => updateDraft(source.key, "schedule", event.target.value)}
                    />
                  </label>
                </div>

                <div className="source-action-row">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={syncingOne}
                    onClick={() => void onSyncOne(source.key)}
                  >
                    <RefreshCcw size={16} />
                    {syncingOne ? "重抓中..." : "立即重抓"}
                  </button>

                  <button
                    type="button"
                    className="secondary-button"
                    disabled={saving}
                    onClick={() =>
                      void onSave(source.key, {
                        enabled: draft.enabled,
                        schedule: draft.schedule,
                        priority: draft.priority,
                        url: draft.url,
                        tags: draft.tags
                      })
                    }
                  >
                    <Save size={16} />
                    {saving ? "保存中..." : "保存来源配置"}
                  </button>
                </div>
              </div>
            </details>
          );
        })}
      </div>
    </section>
  );
}
