import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  AppUpdateInfo,
  AppVersionInfo,
  BrowserSessionState,
  LLMConfig,
  ReferenceProject,
  RuntimePlan,
  SchedulerStatus,
  SourceConnector,
  SystemDoctorResult,
  WeChatChannelConfig,
} from "../../types";
import { SettingsPage } from "./page";

vi.mock("./llm_panel", () => ({
  LLMSettingsPanel: () => <div data-testid="llm-panel">AI 模型面板</div>,
}));

vi.mock("./sources_panel", () => ({
  SourcesPanel: () => <div data-testid="sources-panel">信息源面板</div>,
}));

vi.mock("./browser_section", () => ({
  BrowserWizardSection: () => <div data-testid="browser-panel">微信浏览器面板</div>,
}));

vi.mock("./reference_panel", () => ({
  ReferenceProjectsPanel: () => <div data-testid="references-panel">参考映射面板</div>,
}));

vi.mock("./runtime_plan_panel", () => ({
  RuntimePlanPanel: () => <div data-testid="runtime-panel">运行计划面板</div>,
}));

const llmConfig: LLMConfig = {
  current_profile_id: "main",
  fallback_profile_id: null,
  profiles: [],
  providers: [],
  usage_today: {},
};

const source: SourceConnector = {
  key: "rss",
  name: "RSS",
  kind: "rss",
  driver: "rss",
  platform: "web",
  enabled: true,
  schedule: "manual",
  priority: 1,
  weight: 1,
  auth: {},
  url: "https://example.com/rss",
  tags: [],
  capabilities: [],
  origin_repo: "",
  origin_license: "",
  health_status: "healthy",
  health_detail: "ok",
  item_count: 0,
  consecutive_failures: 0,
  last_item_count: 0,
};

const referenceProject: ReferenceProject = {
  local_name: "参考项目",
  upstream_repo: "owner/repo",
  branch: "main",
  layer: "writing",
  tags: [],
  refresh_status: "ready",
  local_exists: true,
  license_name: "MIT",
  borrow_mode: "reference_only",
  borrow_targets: [],
};

const doctor: SystemDoctorResult = {
  checked_at: "2026-05-28T10:00:00+08:00",
  ok: true,
  summary: "系统正常",
  items: [
    {
      key: "node",
      label: "Node",
      ok: true,
      detail: "已安装",
    },
  ],
};

const appVersion: AppVersionInfo = {
  version: "0.2.13",
  release_channel: "stable",
  release_repo: "owner/repo",
  release_notes_url: "https://example.com/releases",
};

const updateInfo: AppUpdateInfo = {
  current_version: "0.2.13",
  latest_version: "0.2.13",
  update_available: false,
  checked_at: "2026-05-28T10:00:00+08:00",
  source: "github",
};

const wechatConfig: WeChatChannelConfig = {
  app_id: "app",
  app_secret_masked: "***",
  author: "作者",
  default_cover_strategy: "first_image",
  default_digest_strategy: "auto",
  draft_mode: true,
  preview_enabled: false,
  auto_send_window: "09:00-18:00",
  risk_keywords: [],
  browser_name: "chromium",
  browser_profile_path: "profile",
  publish_entry_url: "https://mp.weixin.qq.com",
  selectors_version: "v1",
  sidecar_url: "http://localhost:9322",
};

const browserSession: BrowserSessionState = {
  platform: "wechat_mp",
  browser_name: "chromium",
  user_data_dir: "profile",
  logged_in: true,
  selectors_version: "v1",
  sidecar_health: "healthy",
};

const runtimePlan: RuntimePlan = {
  launch_mode: "interval_now",
  start_at: null,
  interval_minutes: 30,
  timezone: "Asia/Shanghai",
  effective_mode: "automated",
  work_scope: "collect_events_alerts",
  delivery_mode: "collect_only",
  delivery_schedule_time: null,
  admission_strategy: "top_scored",
  batch_limit: 3,
  admission_filters: {},
};

const runtime: SchedulerStatus = {
  running: false,
  control_state: "stopped",
  launch_mode: "interval_now",
  current_mode: "manual",
  work_scope: "collect_events_alerts",
  delivery_mode: "collect_only",
  admission_strategy: "top_scored",
  batch_limit: 5,
  current_cycle: "idle",
  current_cycle_progress_percent: 0,
  current_cycle_progress_done: 0,
  current_cycle_progress_total: 0,
  stage_key: "idle",
  stage_label: "空闲",
  stage_index: 0,
  stage_total: 0,
  uptime_seconds: 0,
  completed_cycles_today: 0,
  failed_cycles_today: 0,
  last_cycle_issue_count: 0,
  run_status: "idle",
  run_stage: "idle",
  run_stale: false,
  run_intent: "normal_monitoring",
};

function renderPage(overrides: Partial<React.ComponentProps<typeof SettingsPage>> = {}) {
  const props: React.ComponentProps<typeof SettingsPage> = {
    referenceProjects: [referenceProject],
    llmConfig,
    sources: [source],
    syncingSources: false,
    savingSourceKey: null,
    syncingSourceKey: null,
    isSavingLLM: false,
    settings: { max_workers: 8, tavily_api_key: "" },
    doctor,
    appVersion,
    updateInfo,
    wechatConfig,
    browserSession,
    isSavingChannel: false,
    isRefreshingBrowser: false,
    isOpeningBrowser: false,
    onSaveChannel: vi.fn().mockResolvedValue(undefined),
    onRefreshBrowser: vi.fn().mockResolvedValue(undefined),
    onOpenBrowserDashboard: vi.fn().mockResolvedValue(undefined),
    onSaveLLMConfig: vi.fn().mockResolvedValue(undefined),
    onSyncSources: vi.fn().mockResolvedValue(undefined),
    onSyncSource: vi.fn().mockResolvedValue(undefined),
    onSaveSource: vi.fn().mockResolvedValue(undefined),
    onCreateSource: vi.fn().mockResolvedValue(undefined),
    onDeleteSource: vi.fn().mockResolvedValue(undefined),
    onSaveSettings: vi.fn().mockResolvedValue(undefined),
    onExportConfig: vi.fn().mockResolvedValue(undefined),
    onExportBackup: vi.fn().mockResolvedValue(undefined),
    onImportBackup: vi.fn().mockResolvedValue(undefined),
    onCheckUpdate: vi.fn().mockResolvedValue(undefined),
    onDismissUpdate: vi.fn().mockResolvedValue(undefined),
    runtimePlan,
    runtime,
    savingRuntimePlan: false,
    onSaveRuntimePlan: vi.fn().mockResolvedValue(undefined),
    onSetAutomationMode: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };

  return { props, ...render(<SettingsPage {...props} />) };
}

describe("SettingsPage", () => {
  it("renders the AI model section by default", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "AI 模型、信息源与系统偏好" })).toBeInTheDocument();
    expect(screen.getByTestId("llm-panel")).toBeInTheDocument();
  });

  it("switches across all six settings sections", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "信息源" }));
    expect(screen.getByTestId("sources-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "微信浏览器" }));
    expect(screen.getByTestId("browser-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "参考映射" }));
    expect(screen.getByTestId("references-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "运行计划" }));
    expect(screen.getByTestId("runtime-panel")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "系统偏好" }));
    expect(screen.getByRole("heading", { name: "系统级默认项" })).toBeInTheDocument();
  });

  it("shows skeleton cards while settings content is loading", () => {
    const { container } = renderPage({ loading: true });

    expect(container.querySelectorAll(".skeleton-card")).toHaveLength(3);
    expect(screen.queryByTestId("llm-panel")).not.toBeInTheDocument();
  });

  it("hides skeleton cards when loading is false", () => {
    const { container } = renderPage({ loading: false });

    expect(container.querySelector(".skeleton-card")).toBeNull();
    expect(screen.getByTestId("llm-panel")).toBeInTheDocument();
  });
});
