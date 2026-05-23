import { ChevronDown, Plus, RefreshCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDateTime } from "../../lib/time";
import type { SourceConnector } from "../../types";
import { SourceHealthBadge } from "../../components/StatusBadge";

interface SourcesPanelProps {
  sources: SourceConnector[];
  syncing: boolean;
  savingSourceKey?: string | null;
  syncingSourceKey?: string | null;
  onSync: () => Promise<void>;
  onSyncOne: (sourceKey: string) => Promise<void>;
  onSave: (sourceKey: string, payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">) => Promise<void>;
  onCreate: (payload: {
    key: string;
    name: string;
    kind: string;
    driver: string;
    url?: string;
    enabled?: boolean;
    schedule?: string;
    priority?: number;
    weight?: number;
    tags?: string[];
  }) => Promise<void>;
  onDelete: (sourceKey: string) => Promise<void>;
}

const schedulePresets = [
  { label: "每 15 分钟", value: "*/15 * * * *" },
  { label: "每 20 分钟", value: "*/20 * * * *" },
  { label: "每 30 分钟", value: "*/30 * * * *" },
  { label: "每 45 分钟", value: "*/45 * * * *" },
  { label: "每小时", value: "0 * * * *" },
  { label: "每 4 小时", value: "0 */4 * * *" }
];

const KIND_OPTIONS = [
  { value: "rss", label: "RSS" },
  { value: "rsshub", label: "RSSHub" },
  { value: "api", label: "API" },
  { value: "reddit", label: "Reddit" },
  { value: "hackernews", label: "Hacker News" },
  { value: "github", label: "GitHub" },
  { value: "vvhan", label: "VVhan 热榜" },
  { value: "bilibili", label: "Bilibili" },
];

const DRIVER_OPTIONS = [
  { value: "rss_feed", label: "RSS 通用", kinds: ["rss", "rsshub"] },
  { value: "reddit_hot", label: "Reddit 热帖", kinds: ["reddit"] },
  { value: "hackernews_frontpage", label: "HN 首页", kinds: ["hackernews"] },
  { value: "github_trending", label: "GitHub Trending", kinds: ["github"] },
  { value: "vvhan_hotlist", label: "VVhan 热榜", kinds: ["vvhan"] },
  { value: "bilibili_hot", label: "Bilibili 热门", kinds: ["bilibili"] },
];

function formatSchedule(schedule: string) {
  const preset = schedulePresets.find((item) => item.value === schedule.trim());
  return preset?.label ?? "高级计划：原始 Cron";
}

interface NewSourceDraft {
  key: string;
  name: string;
  kind: string;
  driver: string;
  url: string;
  schedule: string;
  priority: number;
  weight: number;
  tags: string;
  auth_subreddit: string;
}

const EMPTY_DRAFT: NewSourceDraft = {
  key: "",
  name: "",
  kind: "rss",
  driver: "rss_feed",
  url: "",
  schedule: "*/30 * * * *",
  priority: 5,
  weight: 0.7,
  tags: "",
  auth_subreddit: "",
};

function kindToDrivers(kind: string): typeof DRIVER_OPTIONS {
  return DRIVER_OPTIONS.filter((d) => d.kinds.includes(kind));
}

export function SourcesPanel({ sources, syncing, savingSourceKey, syncingSourceKey, onSync, onSyncOne, onSave, onCreate, onDelete }: SourcesPanelProps) {
  const [drafts, setDrafts] = useState<Record<string, SourceConnector>>({});
  const [showAddForm, setShowAddForm] = useState(false);
  const [newDraft, setNewDraft] = useState<NewSourceDraft>(EMPTY_DRAFT);
  const [creating, setCreating] = useState(false);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null);

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

  async function handleCreate() {
    if (!newDraft.key.trim() || !newDraft.name.trim()) return;
    setCreating(true);
    try {
      const payload = {
        key: newDraft.key.trim(),
        name: newDraft.name.trim(),
        kind: newDraft.kind,
        driver: newDraft.driver,
        url: newDraft.url.trim() || undefined,
        schedule: newDraft.schedule,
        priority: newDraft.priority,
        weight: newDraft.weight,
        tags: newDraft.tags.split(",").map((t) => t.trim()).filter(Boolean),
        auth: newDraft.kind === "reddit" && newDraft.auth_subreddit
          ? { subreddit: newDraft.auth_subreddit }
          : undefined,
      };
      await onCreate(payload);
      setNewDraft(EMPTY_DRAFT);
      setShowAddForm(false);
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(sourceKey: string) {
    if (confirmDeleteKey !== sourceKey) {
      setConfirmDeleteKey(sourceKey);
      return;
    }
    setDeletingKey(sourceKey);
    setConfirmDeleteKey(null);
    try {
      await onDelete(sourceKey);
    } finally {
      setDeletingKey(null);
    }
  }

  const availableDrivers = kindToDrivers(newDraft.kind);

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">来源控制台</p>
          <h2>来源管理</h2>
        </div>
        <div className="intel-hero-actions">
          <button
            type="button"
            className="primary-button"
            onClick={() => setShowAddForm((v) => !v)}
          >
            <Plus size={14} />
            {showAddForm ? "收起" : "添加来源"}
          </button>
          <button type="button" className="ghost-button" onClick={() => void onSync()}>
            <RefreshCcw size={16} />
            {syncing ? "同步中..." : "立即采集"}
          </button>
        </div>
      </div>

      {showAddForm ? (
        <div className="intel-plan-grid">
          <label>
            <span>来源标识 (key)</span>
            <input
              type="text"
              placeholder="my-custom-rss"
              value={newDraft.key}
              onChange={(e) => setNewDraft((d) => ({ ...d, key: e.target.value.replace(/[^a-z0-9_\-]/g, "") }))}
            />
          </label>
          <label>
            <span>来源名称</span>
            <input
              type="text"
              placeholder="我的自定义来源"
              value={newDraft.name}
              onChange={(e) => setNewDraft((d) => ({ ...d, name: e.target.value }))}
            />
          </label>
          <label>
            <span>类型</span>
            <select
              value={newDraft.kind}
              onChange={(e) => {
                const kind = e.target.value;
                const drivers = kindToDrivers(kind);
                setNewDraft((d) => ({
                  ...d,
                  kind,
                  driver: drivers.length ? drivers[0].value : "rss_feed",
                }));
              }}
            >
              {KIND_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>
          <label>
            <span>驱动</span>
            <select
              value={availableDrivers.some((d) => d.value === newDraft.driver) ? newDraft.driver : (availableDrivers[0]?.value ?? "rss_feed")}
              onChange={(e) => setNewDraft((d) => ({ ...d, driver: e.target.value }))}
            >
              {availableDrivers.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
          </label>
          <label className="full-span">
            <span>URL</span>
            <input
              type="text"
              placeholder="https://example.com/feed.xml"
              value={newDraft.url}
              onChange={(e) => setNewDraft((d) => ({ ...d, url: e.target.value }))}
            />
          </label>
          {newDraft.kind === "reddit" ? (
            <label>
              <span>Subreddit</span>
              <input
                type="text"
                placeholder="technology"
                value={newDraft.auth_subreddit}
                onChange={(e) => setNewDraft((d) => ({ ...d, auth_subreddit: e.target.value }))}
              />
            </label>
          ) : null}
          <label>
            <span>频率</span>
            <select
              value={schedulePresets.some((s) => s.value === newDraft.schedule) ? newDraft.schedule : "__custom__"}
              onChange={(e) => {
                if (e.target.value !== "__custom__") {
                  setNewDraft((d) => ({ ...d, schedule: e.target.value }));
                }
              }}
            >
              {schedulePresets.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
              <option value="__custom__">自定义</option>
            </select>
          </label>
          <label>
            <span>优先级 (1-10)</span>
            <input
              type="number"
              min={1}
              max={10}
              value={newDraft.priority}
              onChange={(e) => setNewDraft((d) => ({ ...d, priority: Number(e.target.value) }))}
            />
          </label>
          <label>
            <span>标签 (逗号分隔)</span>
            <input
              type="text"
              placeholder="AI, 科技"
              value={newDraft.tags}
              onChange={(e) => setNewDraft((d) => ({ ...d, tags: e.target.value }))}
            />
          </label>
          <div className="intel-plan-footer" style={{ gridColumn: "1 / -1" }}>
            <div className="intel-plan-actions">
              <button
                type="button"
                className="primary-button"
                disabled={creating || !newDraft.key.trim() || !newDraft.name.trim()}
                onClick={() => void handleCreate()}
              >
                <Plus size={14} />
                {creating ? "添加中..." : "确认添加"}
              </button>
              <button
                type="button"
                className="ghost-button compact"
                onClick={() => { setNewDraft(EMPTY_DRAFT); setShowAddForm(false); }}
              >
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}

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
          const isDeleting = deletingKey === source.key;
          const isConfirming = confirmDeleteKey === source.key;
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
                    <p>标识：{source.key}</p>
                    <p>驱动：{source.driver}</p>
                    <p>权重：{source.weight}</p>
                    <p>来源仓库：{source.origin_repo}</p>
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
                    {saving ? "保存中..." : "保存配置"}
                  </button>

                  <button
                    type="button"
                    className="ghost-button danger"
                    disabled={isDeleting}
                    onClick={() => void handleDelete(source.key)}
                  >
                    <Trash2 size={14} />
                    {isDeleting ? "删除中..." : isConfirming ? "确认删除？" : "删除"}
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
