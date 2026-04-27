import { Save } from "lucide-react";
import { useState } from "react";

import type {
  BrowserSessionState,
  LLMConfig,
  PublishBackendStatus,
  ReferenceProject,
  SettingsSectionKey,
  SourceConnector,
  WeChatChannelConfig,
} from "../types";
import { ChannelPanel } from "./ChannelPanel";
import { LLMSettingsPanel } from "./LLMSettingsPanel";
import { ReferenceProjectsPanel } from "./ReferenceProjectsPanel";
import { SourcesPanel } from "./SourcesPanel";

interface SettingsPanelProps {
  config: WeChatChannelConfig | null;
  browserSession: BrowserSessionState | null;
  publishBackends: PublishBackendStatus[];
  referenceProjects: ReferenceProject[];
  llmConfig: LLMConfig | null;
  sources: SourceConnector[];
  syncingSources: boolean;
  savingSourceKey?: string | null;
  syncingSourceKey?: string | null;
  isSaving: boolean;
  isSavingLLM: boolean;
  isRefreshingBrowser: boolean;
  isOpeningBrowser: boolean;
  settings: Record<string, unknown>;
  onSaveChannel: (payload: WeChatChannelConfig) => Promise<void>;
  onSaveLLMConfig: (config: LLMConfig) => Promise<void>;
  onRefreshBrowser: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
  onOpenBrowserDashboard: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
  onSyncSources: () => Promise<void>;
  onSyncSource: (sourceKey: string) => Promise<void>;
  onSaveSource: (sourceKey: string, payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">) => Promise<void>;
  onCreateSource: (payload: {
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
  onDeleteSource: (sourceKey: string) => Promise<void>;
  onSaveSettings: (payload: Record<string, unknown>) => Promise<void>;
}

export function SettingsPanel({
  config,
  browserSession,
  publishBackends,
  referenceProjects,
  llmConfig,
  sources,
  syncingSources,
  savingSourceKey,
  syncingSourceKey,
  isSaving,
  isSavingLLM,
  isRefreshingBrowser,
  isOpeningBrowser,
  onSaveChannel,
  onSaveLLMConfig,
  onRefreshBrowser,
  onOpenBrowserDashboard,
  onSyncSources,
  onSyncSource,
  onSaveSource,
  onCreateSource,
  onDeleteSource,
  onSaveSettings,
  settings,
}: SettingsPanelProps) {
  const [maxWorkers, setMaxWorkers] = useState(Number(settings?.max_workers ?? 8));
  const [savingSettings, setSavingSettings] = useState(false);

  const maxWorkersDirty = maxWorkers !== Number(settings?.max_workers ?? 8);
  const [section, setSection] = useState<SettingsSectionKey>("channels");

  return (
    <section className="page-content">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">设置</p>
            <h2>发布渠道、AI 模型、信息源与系统偏好</h2>
            <p className="subtle">所有配置型功能集中收纳，不打断主工作流。</p>
          </div>
        </div>

        <div className="segmented-control settings-sections" style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}>
          <button type="button" className={section === "channels" ? "segment-active" : ""} onClick={() => setSection("channels")}>
            发布渠道
          </button>
          <button type="button" className={section === "ai" ? "segment-active" : ""} onClick={() => setSection("ai")}>
            AI 模型
          </button>
          <button type="button" className={section === "sources" ? "segment-active" : ""} onClick={() => setSection("sources")}>
            信息源
          </button>
          <button type="button" className={section === "references" ? "segment-active" : ""} onClick={() => setSection("references")}>
            参考映射
          </button>
          <button type="button" className={section === "system" ? "segment-active" : ""} onClick={() => setSection("system")}>
            系统偏好
          </button>
        </div>
      </section>

      {section === "channels" ? (
        <ChannelPanel
          config={config}
          browserSession={browserSession}
          publishBackends={publishBackends}
          isSaving={isSaving}
          isRefreshingBrowser={isRefreshingBrowser}
          isOpeningBrowser={isOpeningBrowser}
          onSave={onSaveChannel}
          onRefreshBrowser={onRefreshBrowser}
          onOpenBrowserDashboard={onOpenBrowserDashboard}
        />
      ) : null}

      {section === "ai" ? (
        <LLMSettingsPanel config={llmConfig} isSaving={isSavingLLM} onSave={onSaveLLMConfig} />
      ) : null}

      {section === "sources" ? (
        <SourcesPanel
          sources={sources}
          syncing={syncingSources}
          savingSourceKey={savingSourceKey}
          syncingSourceKey={syncingSourceKey}
          onSync={onSyncSources}
          onSyncOne={onSyncSource}
          onSave={onSaveSource}
          onCreate={onCreateSource}
          onDelete={onDeleteSource}
        />
      ) : null}

      {section === "references" ? <ReferenceProjectsPanel items={referenceProjects} /> : null}

      {section === "system" ? (
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">系统偏好</p>
              <h2>系统级默认项</h2>
            </div>
          </div>
          <div className="intel-plan-grid">
            <label>
              <span>采集并发数</span>
              <select
                value={maxWorkers}
                onChange={(e) => setMaxWorkers(Number(e.target.value))}
              >
                {[1, 2, 3, 5, 8, 10, 12, 15, 20].map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              <span>说明</span>
              <p className="subtle" style={{ marginTop: 4 }}>
                并发数越高采集越快，但过高可能触发目标服务器限流。基准测试显示 52 个来源在 8 并发时约 12.6 秒完成，10 并发时约 12.3 秒（瓶颈在慢源本身）。
              </p>
            </label>
          </div>
          <div className="intel-plan-footer">
            <div className="intel-plan-status">
              {maxWorkersDirty ? <span className="dirty-chip">有未保存变更</span> : <span className="subtle-chip">已保存</span>}
            </div>
            <div className="intel-plan-actions">
              <button
                type="button"
                className="ghost-button compact"
                disabled={savingSettings || !maxWorkersDirty}
                onClick={async () => {
                  setSavingSettings(true);
                  try {
                    await onSaveSettings({ max_workers: maxWorkers });
                  } finally {
                    setSavingSettings(false);
                  }
                }}
              >
                <Save size={14} />
                {savingSettings ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </section>
      ) : null}
    </section>
  );
}
