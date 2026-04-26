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
  onSaveChannel: (payload: WeChatChannelConfig) => Promise<void>;
  onSaveLLMConfig: (config: LLMConfig) => Promise<void>;
  onRefreshBrowser: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
  onOpenBrowserDashboard: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
  onSyncSources: () => Promise<void>;
  onSyncSource: (sourceKey: string) => Promise<void>;
  onSaveSource: (sourceKey: string, payload: Pick<SourceConnector, "enabled" | "schedule" | "priority" | "url" | "tags">) => Promise<void>;
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
}: SettingsPanelProps) {
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
        />
      ) : null}

      {section === "references" ? <ReferenceProjectsPanel items={referenceProjects} /> : null}

      {section === "system" ? (
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">系统偏好</p>
              <h2>系统级默认项</h2>
              <p className="subtle">低频配置收纳位，避免散落在主导航里。</p>
            </div>
          </div>
          <div className="runtime-card-grid">
            <article className="runtime-card">
              <span>界面定位</span>
              <strong>信息优先</strong>
              <p>驾驶舱只控全局，情报页专看信息。</p>
            </article>
            <article className="runtime-card">
              <span>自动化默认</span>
              <strong>草稿优先</strong>
              <p>先发现、再成稿、再决定是否进发布链路。</p>
            </article>
            <article className="runtime-card">
              <span>发布策略</span>
              <strong>浏览器复用</strong>
              <p>公众号发布走本机浏览器会话，一次配置后可持续复用。</p>
            </article>
          </div>
        </section>
      ) : null}
    </section>
  );
}
