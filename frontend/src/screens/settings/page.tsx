import { Save } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../../lib/time";
import type {
  AppUpdateInfo,
  AppVersionInfo,
  BrowserSessionState,
  LLMConfig,
  ReferenceProject,
  SettingsSectionKey,
  SourceConnector,
  SystemDoctorResult,
  WeChatChannelConfig,
} from "../../types";
import { SourceHealthBadge } from "../../components/StatusBadge";
import { BrowserWizardSection } from "./browser_section";
import { LLMSettingsPanel } from "./llm_panel";
import { ReferenceProjectsPanel } from "./reference_panel";
import { SourcesPanel } from "./sources_panel";

interface SettingsPageProps {
  referenceProjects: ReferenceProject[];
  llmConfig: LLMConfig | null;
  sources: SourceConnector[];
  syncingSources: boolean;
  savingSourceKey?: string | null;
  syncingSourceKey?: string | null;
  isSavingLLM: boolean;
  settings: Record<string, unknown>;
  doctor: SystemDoctorResult | null;
  appVersion: AppVersionInfo | null;
  updateInfo: AppUpdateInfo | null;
  wechatConfig: WeChatChannelConfig | null;
  browserSession: BrowserSessionState | null;
  isSavingChannel: boolean;
  isRefreshingBrowser: boolean;
  isOpeningBrowser: boolean;
  onSaveChannel: (payload: WeChatChannelConfig) => Promise<void>;
  onRefreshBrowser: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
  onOpenBrowserDashboard: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
  onSaveLLMConfig: (config: LLMConfig, tavilyApiKey: string) => Promise<void>;
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
  onExportConfig: () => Promise<void>;
  onExportBackup: () => Promise<void>;
  onImportBackup: (file: File) => Promise<void>;
  onCheckUpdate: () => Promise<void>;
  onDismissUpdate: (version: string) => Promise<void>;
}

export function SettingsPage({
  referenceProjects,
  llmConfig,
  sources,
  syncingSources,
  savingSourceKey,
  syncingSourceKey,
  isSavingLLM,
  settings,
  doctor,
  appVersion,
  updateInfo,
  wechatConfig,
  browserSession,
  isSavingChannel,
  isRefreshingBrowser,
  isOpeningBrowser,
  onSaveChannel,
  onRefreshBrowser,
  onOpenBrowserDashboard,
  onSaveLLMConfig,
  onSyncSources,
  onSyncSource,
  onSaveSource,
  onCreateSource,
  onDeleteSource,
  onSaveSettings,
  onExportConfig,
  onExportBackup,
  onImportBackup,
  onCheckUpdate,
  onDismissUpdate,
}: SettingsPageProps) {
  const [maxWorkers, setMaxWorkers] = useState(Number(settings?.max_workers ?? 8));
  const [savingSettings, setSavingSettings] = useState(false);

  useEffect(() => {
    setMaxWorkers(Number(settings?.max_workers ?? 8));
  }, [settings]);

  const maxWorkersDirty = maxWorkers !== Number(settings?.max_workers ?? 8);
  const [section, setSection] = useState<SettingsSectionKey>("ai");

  return (
    <section className="page-content">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">设置</p>
            <h2>AI 模型、信息源与系统偏好</h2>
            <p className="subtle">所有配置型功能集中收纳，不打断主工作流。</p>
          </div>
        </div>

        <div className="segmented-control settings-sections" style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}>
          <button type="button" className={section === "ai" ? "segment-active" : ""} onClick={() => setSection("ai")}>
            AI 模型
          </button>
          <button type="button" className={section === "sources" ? "segment-active" : ""} onClick={() => setSection("sources")}>
            信息源
          </button>
          <button type="button" className={section === "browser" ? "segment-active" : ""} onClick={() => setSection("browser")}>
            微信浏览器
          </button>
          <button type="button" className={section === "references" ? "segment-active" : ""} onClick={() => setSection("references")}>
            参考映射
          </button>
          <button type="button" className={section === "system" ? "segment-active" : ""} onClick={() => setSection("system")}>
            系统偏好
          </button>
        </div>
      </section>

      {section === "ai" && llmConfig ? (
        <LLMSettingsPanel
          config={llmConfig}
          tavilyApiKey={String(settings?.tavily_api_key ?? "")}
          isSaving={isSavingLLM}
          onSave={onSaveLLMConfig}
        />
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

      {section === "browser" ? <BrowserWizardSection
        config={wechatConfig}
        browserSession={browserSession}
        isSaving={isSavingChannel}
        isRefreshingBrowser={isRefreshingBrowser}
        isOpeningBrowser={isOpeningBrowser}
        onSave={onSaveChannel}
        onRefreshBrowser={onRefreshBrowser}
        onOpenBrowserDashboard={onOpenBrowserDashboard}
      /> : null}

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
          <div className="panel" style={{ marginTop: 16 }}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">版本更新</p>
                <h2>应用版本</h2>
                <p className="subtle">
                  当前 {appVersion?.version ?? "-"}
                  {updateInfo?.update_available && updateInfo.latest_version ? `，可升级到 ${updateInfo.latest_version}` : ""}
                </p>
              </div>
            </div>
            <div className="source-grid">
              <article className="source-card">
                <div className="source-card-header">
                  <div>
                    <strong>当前版本</strong>
                    <p>{appVersion?.version ?? "-"}</p>
                  </div>
                  <SourceHealthBadge health="healthy" />
                </div>
              </article>
              <article className="source-card">
                <div className="source-card-header">
                  <div>
                    <strong>最新版本</strong>
                    <p>{updateInfo?.latest_version ?? "尚未发现正式 Release"}</p>
                  </div>
                  <SourceHealthBadge health={updateInfo?.update_available ? "warning" : "healthy"} />
                </div>
                <p className="subtle">
                  {updateInfo?.error
                    ? `检查结果：${updateInfo.error}`
                    : `最近检查：${updateInfo ? formatRelativeTime(updateInfo.checked_at) : "未检查"}`}
                </p>
                {updateInfo?.update_available && !updateInfo.dismissed ? <p className="update-dot-note">有可用新版本</p> : null}
              </article>
            </div>
            <div className="intel-plan-actions" style={{ marginTop: 12, justifyContent: "flex-start" }}>
              <button type="button" className="ghost-button compact" onClick={() => void onCheckUpdate()}>
                立即检查
              </button>
              {updateInfo?.release_url ? (
                <button type="button" className="ghost-button compact" onClick={() => window.open(updateInfo.release_url ?? updateInfo.release_notes_url ?? "", "_blank", "noopener,noreferrer")}>
                  打开发布页
                </button>
              ) : null}
              {updateInfo?.update_available && updateInfo.latest_version ? (
                <button type="button" className="ghost-button compact" onClick={() => void onDismissUpdate(updateInfo.latest_version ?? "")}>
                  忽略此版本
                </button>
              ) : null}
            </div>
          </div>
          <div className="panel" style={{ marginTop: 16 }}>
            <div className="panel-header">
              <div>
                <p className="eyebrow">恢复与自检</p>
                <h2>安装状态与备份</h2>
                <p className="subtle">{doctor?.summary ?? "尚未执行系统自检。"}</p>
              </div>
            </div>
            <div className="source-grid">
              {(doctor?.items ?? []).map((item) => (
                <article key={item.key} className="source-card">
                  <div className="source-card-header">
                    <div>
                      <strong>{item.label}</strong>
                      <p>{item.detail}</p>
                    </div>
                    <SourceHealthBadge health={item.ok ? "healthy" : "warning"} />
                  </div>
                  {item.next_action ? <p className="subtle">{item.next_action}</p> : null}
                </article>
              ))}
            </div>
            <div className="intel-plan-actions" style={{ marginTop: 12, justifyContent: "flex-start" }}>
              <button type="button" className="ghost-button compact" onClick={() => void onExportConfig()}>
                导出配置
              </button>
              <button type="button" className="ghost-button compact" onClick={() => void onExportBackup()}>
                导出备份
              </button>
              <label className="ghost-button compact" style={{ cursor: "pointer" }}>
                导入备份
                <input
                  type="file"
                  accept=".zip,.json"
                  style={{ display: "none" }}
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) {
                      void onImportBackup(file);
                    }
                    event.currentTarget.value = "";
                  }}
                />
              </label>
            </div>
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
