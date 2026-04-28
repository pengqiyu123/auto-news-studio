import { CheckCircle, Copy, Edit, Eye, EyeOff, Loader2, Plus, Save, TestTube2, Trash2, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api";
import type { LLMConfig, LLMProfileConfig, LLMTaskConfig, LLMTestResult } from "../types";

const PROVIDER_REGISTRY: Record<string, { label: string; base_url: string; models: string[] }> = {
  nvidia: {
    label: "NVIDIA NIM",
    base_url: "https://integrate.api.nvidia.com/v1",
    models: [
      "qwen/qwen3.5-122b-a10b",
      "z-ai/glm4.7",
      "minimaxai/minimax-m2.7",
      "z-ai/glm-5.1",
      "deepseek-ai/deepseek-v4-flash",
      "deepseek-ai/deepseek-v4-pro",
    ],
  },
  siliconflow: {
    label: "SiliconFlow",
    base_url: "https://api.siliconflow.cn/v1",
    models: [
      "THUDM/GLM-4-9B-0414",
      "THUDM/GLM-Z1-9B-0414",
      "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
      "Qwen/Qwen3-8B",
      "Qwen/Qwen3.5-4B",
      "THUDM/GLM-4.1V-9B-Thinking",
    ],
  },
  openrouter: {
    label: "OpenRouter",
    base_url: "https://openrouter.ai/api/v1",
    models: ["google/gemini-2.5-flash", "deepseek/deepseek-v3.2", "openai/gpt-4o"],
  },
  glm: {
    label: "智谱 GLM",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    models: ["glm-4.7-flash", "glm-4-plus", "glm-4-flash", "glm-4-air"],
  },
  deepseek: {
    label: "DeepSeek",
    base_url: "https://api.deepseek.com/v1",
    models: ["deepseek-chat", "deepseek-reasoner"],
  },
  doubao: {
    label: "豆包 (火山引擎)",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    models: ["doubao-seed-1-8-251228"],
  },
  qwen: {
    label: "通义千问",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    models: ["qwen-max", "qwen-plus", "qwen-turbo"],
  },
  openai: {
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    models: ["gpt-4o", "gpt-4o-mini", "o3-mini"],
  },
};

// 3 任务配置：judgement(判断)、translation(翻译)、article(生成)
// outline/title 合并到 article；summary 改名为 translation
const DEFAULT_TASKS: LLMTaskConfig[] = [
  { task_key: "judgement", label: "初步判断", provider_key: "", model_id: "", fallback_provider_key: "", fallback_model_id: "", temperature: 0.2, max_tokens: 2048, system_prompt: "" },
  { task_key: "translation", label: "事件翻译", provider_key: "", model_id: "", fallback_provider_key: "", fallback_model_id: "", temperature: 0.3, max_tokens: 512, system_prompt: "" },
  { task_key: "article", label: "稿件生成", provider_key: "", model_id: "", fallback_provider_key: "", fallback_model_id: "", temperature: 0.7, max_tokens: 4096, system_prompt: "" },
];

const DEFAULT_PROFILES: LLMProfileConfig[] = [
  {
    id: "nvidia-qwen35-122b",
    label: "NVIDIA Qwen 122B",
    description: "主力强模型，实测连通快，适合优先做正式稿。",
    provider_key: "nvidia",
    api_key: "",
    base_url: PROVIDER_REGISTRY.nvidia.base_url,
    model_id: "qwen/qwen3.5-122b-a10b",
    enabled: false,
  },
  {
    id: "nvidia-glm47",
    label: "NVIDIA GLM 4.7",
    description: "NVIDIA 通道下的 GLM 备选，实测可用且响应很快。",
    provider_key: "nvidia",
    api_key: "",
    base_url: PROVIDER_REGISTRY.nvidia.base_url,
    model_id: "z-ai/glm4.7",
    enabled: false,
  },
  {
    id: "nvidia-minimax-m27",
    label: "NVIDIA MiniMax M2.7",
    description: "实测可用，但更适合作为额外备选。",
    provider_key: "nvidia",
    api_key: "",
    base_url: PROVIDER_REGISTRY.nvidia.base_url,
    model_id: "minimaxai/minimax-m2.7",
    enabled: false,
  },
  {
    id: "siliconflow-glm4-9b",
    label: "SiliconFlow GLM 4 9B",
    description: "免费且快，适合做稳态兜底。",
    provider_key: "siliconflow",
    api_key: "",
    base_url: PROVIDER_REGISTRY.siliconflow.base_url,
    model_id: "THUDM/GLM-4-9B-0414",
    enabled: false,
  },
  {
    id: "siliconflow-glmz1-9b",
    label: "SiliconFlow GLM Z1 9B",
    description: "免费备选，实测连通和速度都不错。",
    provider_key: "siliconflow",
    api_key: "",
    base_url: PROVIDER_REGISTRY.siliconflow.base_url,
    model_id: "THUDM/GLM-Z1-9B-0414",
    enabled: false,
  },
  {
    id: "siliconflow-deepseek-r1-qwen3-8b",
    label: "SiliconFlow DeepSeek R1 Qwen3 8B",
    description: "免费推理型备选，适合做判断和摘要。",
    provider_key: "siliconflow",
    api_key: "",
    base_url: PROVIDER_REGISTRY.siliconflow.base_url,
    model_id: "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    enabled: false,
  },
  {
    id: "siliconflow-qwen3-8b",
    label: "SiliconFlow Qwen3 8B",
    description: "免费通用备选，适合快速切换测试。",
    provider_key: "siliconflow",
    api_key: "",
    base_url: PROVIDER_REGISTRY.siliconflow.base_url,
    model_id: "Qwen/Qwen3-8B",
    enabled: false,
  },
];

const PRESET_PROFILE_IDS = new Set(DEFAULT_PROFILES.map((item) => item.id));

interface LLMSettingsPanelProps {
  config: LLMConfig | null;
  isSaving: boolean;
  onSave: (config: LLMConfig) => Promise<void>;
}

function buildTasks(profile: LLMProfileConfig): LLMTaskConfig[] {
  return DEFAULT_TASKS.map((task) => ({
    ...task,
    provider_key: profile.enabled ? profile.provider_key : "",
    model_id: profile.enabled ? profile.model_id : "",
  }));
}

function buildProviders(profile: LLMProfileConfig) {
  return [
    {
      key: profile.provider_key,
      api_key: profile.api_key,
      base_url: profile.base_url,
      model_id: profile.model_id,
      enabled: profile.enabled && Boolean(profile.api_key.trim()),
      last_tested_at: profile.last_tested_at ?? null,
      last_test_result: profile.last_test_result ?? null,
    },
  ];
}

function normalizeProfiles(profiles: LLMProfileConfig[]) {
  const providerKeys = new Map<string, string>();
  for (const profile of profiles) {
    const apiKey = profile.api_key.trim();
    if (apiKey && !apiKey.includes("****")) {
      providerKeys.set(profile.provider_key, apiKey);
    }
  }
  return profiles.map((profile) => {
    const fallbackKey = providerKeys.get(profile.provider_key) || "";
    const nextApiKey = profile.api_key || fallbackKey;
    return {
      ...profile,
      api_key: nextApiKey,
      enabled: profile.enabled && Boolean(nextApiKey.trim()),
    };
  });
}

function isPresetProfile(profileId: string) {
  return PRESET_PROFILE_IDS.has(profileId);
}

function buildCustomProfile(seed?: Partial<LLMProfileConfig>): LLMProfileConfig {
  const providerKey = seed?.provider_key || "siliconflow";
  const registry = PROVIDER_REGISTRY[providerKey] ?? PROVIDER_REGISTRY.siliconflow;
  const now = Date.now();
  return {
    id: `custom-${now}`,
    label: seed?.label ? `${seed.label} 副本` : "自定义模型",
    description: seed?.description || "你自己的可切换模型档位。",
    provider_key: providerKey,
    api_key: seed?.api_key || "",
    base_url: seed?.base_url || registry.base_url,
    model_id: seed?.model_id || registry.models[0] || "",
    enabled: false,
    last_test_result: null,
    last_tested_at: null,
  };
}

function hydrateConfig(config: LLMConfig | null): LLMConfig {
  const sourceProfiles = config?.profiles?.length ? config.profiles : DEFAULT_PROFILES;
  const mergedPresets = DEFAULT_PROFILES.map((preset) => {
    const existing = sourceProfiles.find((item) => item.id === preset.id);
    return {
      ...preset,
      ...existing,
      provider_key: existing?.provider_key || preset.provider_key,
      base_url: existing?.base_url || preset.base_url,
      model_id: existing?.model_id || preset.model_id,
    };
  });

  const customProfiles = sourceProfiles
    .filter((item) => !isPresetProfile(item.id))
    .map((profile) => {
      const registry = PROVIDER_REGISTRY[profile.provider_key] ?? PROVIDER_REGISTRY.siliconflow;
      return {
        ...profile,
        base_url: profile.base_url || registry.base_url,
        model_id: profile.model_id || registry.models[0] || "",
      };
    });

  const profiles = normalizeProfiles([...mergedPresets, ...customProfiles]);
  const currentProfileId = config?.current_profile_id || profiles[0]?.id || "";
  const activeProfile = profiles.find((item) => item.id === currentProfileId) ?? profiles[0];
  return {
    current_profile_id: activeProfile?.id ?? "",
    profiles,
    providers: activeProfile ? buildProviders(activeProfile) : [],
    tasks: activeProfile ? buildTasks(activeProfile) : [],
    usage_today: config?.usage_today ?? {},
  };
}

export function LLMSettingsPanel({ config: initialConfig, isSaving, onSave }: LLMSettingsPanelProps) {
  const [draftConfig, setDraftConfig] = useState<LLMConfig>(() => hydrateConfig(initialConfig));
  const [selectedProfileId, setSelectedProfileId] = useState(draftConfig.current_profile_id);
  const [showKey, setShowKey] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [testing, setTesting] = useState(false);
  const [switchingProfileId, setSwitchingProfileId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null);

  useEffect(() => {
    const next = hydrateConfig(initialConfig);
    setDraftConfig(next);
    setSelectedProfileId(next.current_profile_id);
    setDirty(false);
    setTestResult(null);
  }, [initialConfig]);

  const selectedProfile = draftConfig.profiles.find((item) => item.id === selectedProfileId) ?? draftConfig.profiles[0];
  const activeProfile = draftConfig.profiles.find((item) => item.id === draftConfig.current_profile_id) ?? selectedProfile;
  const registry = selectedProfile ? PROVIDER_REGISTRY[selectedProfile.provider_key] ?? PROVIDER_REGISTRY.siliconflow : PROVIDER_REGISTRY.siliconflow;
  const configuredCount = draftConfig.profiles.filter((item) => Boolean(item.api_key.trim())).length;
  const activeSummary = useMemo(() => {
    if (!activeProfile) {
      return "当前还没有可用模型档位。";
    }
    if (!activeProfile.enabled || !activeProfile.api_key.trim()) {
      return "当前未启用 AI 写作，系统会继续使用模板生成。";
    }
    const providerLabel = PROVIDER_REGISTRY[activeProfile.provider_key]?.label ?? activeProfile.provider_key;
    return `当前启用 ${providerLabel} / ${activeProfile.model_id}，判断、提纲、正文、标题和摘要都会走这一档。`;
  }, [activeProfile]);

  function updateProfiles(nextProfiles: LLMProfileConfig[], options?: { currentProfileId?: string; selectedId?: string }) {
    const normalizedProfiles = normalizeProfiles(nextProfiles);
    const currentProfileId = options?.currentProfileId ?? draftConfig.current_profile_id;
    const active = normalizedProfiles.find((item) => item.id === currentProfileId) ?? normalizedProfiles[0];
    // Preserve existing tasks if they exist and have the same task keys (don't reset task edits)
    const existingTaskKeys = new Set(draftConfig.tasks.map((t) => t.task_key));
    const profileTasks = active ? buildTasks(active) : [];
    const profileTaskKeys = new Set(profileTasks.map((t) => t.task_key));
    // If task keys match, keep existing tasks (preserve user's task edits)
    const tasks = existingTaskKeys.size === profileTaskKeys.size && [...existingTaskKeys].every((k) => profileTaskKeys.has(k))
      ? draftConfig.tasks
      : profileTasks;
    setDraftConfig({
      current_profile_id: active?.id ?? "",
      profiles: normalizedProfiles,
      providers: active ? buildProviders(active) : [],
      tasks,
      usage_today: draftConfig.usage_today,
    });
    if (options?.selectedId) {
      setSelectedProfileId(options.selectedId);
    }
    setDirty(true);
  }

  function updateTasks(nextTasks: LLMTaskConfig[]) {
    setDraftConfig((prev) => ({
      ...prev,
      tasks: nextTasks,
    }));
    setDirty(true);
  }

  function updateSelectedProfile(patch: Partial<LLMProfileConfig>) {
    if (!selectedProfile) return;
    const nextProfiles = draftConfig.profiles.map((profile) => {
      if (profile.id !== selectedProfile.id) return profile;
      const nextProfile = { ...profile, ...patch };
      if (patch.provider_key) {
        const nextRegistry = PROVIDER_REGISTRY[patch.provider_key] ?? PROVIDER_REGISTRY.siliconflow;
        nextProfile.base_url = nextRegistry.base_url;
        nextProfile.model_id = nextRegistry.models[0] ?? "";
      }
      return nextProfile;
    });
    updateProfiles(nextProfiles);
  }

  async function persist(nextConfig: LLMConfig) {
    await onSave(nextConfig);
    setDirty(false);
  }

  async function handleSave() {
    await persist(draftConfig);
  }

  function handleAddProfile() {
    const nextProfile = buildCustomProfile(selectedProfile);
    updateProfiles([...draftConfig.profiles, nextProfile], { selectedId: nextProfile.id });
    setTestResult(null);
  }

  function handleDuplicateProfile(profile: LLMProfileConfig) {
    const duplicate = buildCustomProfile(profile);
    updateProfiles([...draftConfig.profiles, duplicate], { selectedId: duplicate.id });
    setTestResult(null);
  }

  function handleDeleteProfile(profileId: string) {
    if (isPresetProfile(profileId)) return;
    const remaining = draftConfig.profiles.filter((item) => item.id !== profileId);
    const fallbackId =
      draftConfig.current_profile_id === profileId
        ? remaining[0]?.id ?? ""
        : draftConfig.current_profile_id;
    const nextSelectedId =
      selectedProfileId === profileId
        ? remaining.find((item) => item.id === fallbackId)?.id || remaining[0]?.id || ""
        : selectedProfileId;
    updateProfiles(remaining, { currentProfileId: fallbackId, selectedId: nextSelectedId });
    setTestResult(null);
  }

  async function handleQuickSwitch(profileId: string) {
    const target = draftConfig.profiles.find((item) => item.id === profileId);
    if (!target || !target.api_key.trim()) return;
    const nextProfiles = draftConfig.profiles.map((profile) => ({
      ...profile,
      enabled: profile.id === profileId ? Boolean(profile.api_key.trim()) : profile.enabled,
    }));
    const normalizedProfiles = normalizeProfiles(nextProfiles);
    const active = normalizedProfiles.find((item) => item.id === profileId) ?? normalizedProfiles[0];
    // Preserve existing tasks (don't reset task edits on profile switch)
    const payload: LLMConfig = {
      current_profile_id: active?.id ?? "",
      profiles: normalizedProfiles,
      providers: active ? buildProviders(active) : [],
      tasks: draftConfig.tasks,
      usage_today: draftConfig.usage_today,
    };
    setSwitchingProfileId(profileId);
    try {
      await onSave(payload);
      setDirty(false);
      setSelectedProfileId(profileId);
    } finally {
      setSwitchingProfileId(null);
    }
  }

  async function handleTest() {
    if (!selectedProfile) return;
    setTesting(true);
    setTestResult(null);
    try {
      const nextProfiles = draftConfig.profiles.map((profile) => ({
        ...profile,
        enabled: profile.id === selectedProfile.id ? Boolean(profile.api_key.trim()) : profile.enabled,
      }));
      const normalizedProfiles = normalizeProfiles(nextProfiles);
      const active = normalizedProfiles.find((item) => item.id === selectedProfile.id) ?? normalizedProfiles[0];
      // Preserve existing tasks (don't reset task edits on test)
      const payload: LLMConfig = {
        current_profile_id: active?.id ?? "",
        profiles: normalizedProfiles,
        providers: active ? buildProviders(active) : [],
        tasks: draftConfig.tasks,
        usage_today: draftConfig.usage_today,
      };
      await persist(payload);
      const result = await api.testLLMProvider(active.provider_key);
      setTestResult(result);
    } catch (error) {
      setTestResult({
        ok: false,
        model: "",
        content: "",
        latency_ms: 0,
        error: error instanceof Error ? error.message : "测试失败",
      });
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="page-content">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">AI 模型</p>
            <h2>模型档位切换器</h2>
            <p className="subtle">先把常用模型做成档位卡片。选中即可启用，需要时再新增、复制、编辑和删除自定义档位。</p>
          </div>
          <div className="panel-header-actions">
            {dirty ? <span className="dirty-chip">有未保存的修改</span> : null}
            <button type="button" className="secondary-button" onClick={handleAddProfile}>
              <Plus size={14} />
              新建档位
            </button>
            <button type="button" className="primary-button" disabled={isSaving || !dirty} onClick={() => void handleSave()}>
              <Save size={14} />
              {isSaving ? "保存中..." : "保存全部"}
            </button>
          </div>
        </div>

        <div className="runtime-card-grid">
          <article className="runtime-card">
            <span>当前状态</span>
            <strong>{activeProfile?.enabled && activeProfile.api_key.trim() ? "已启用 AI 写作" : "未启用 AI 写作"}</strong>
            <p>{activeProfile ? `${activeProfile.label} / ${activeProfile.model_id}` : "还没有模型档位"}</p>
          </article>
          <article className="runtime-card">
            <span>可切换档位</span>
            <strong>{draftConfig.profiles.length} 个</strong>
            <p>{configuredCount} 个已配 API Key，可直接切换使用。</p>
          </article>
          <article className="runtime-card">
            <span>连接测试</span>
            <strong>{testResult ? (testResult.ok ? "连接正常" : "连接失败") : "尚未测试"}</strong>
            <p>{testResult ? (testResult.ok ? `延迟 ${testResult.latency_ms.toFixed(0)}ms` : testResult.error) : "右侧保存后可立即测试当前档位。"}</p>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="mode-config-subhead">
          <div>
            <p className="eyebrow">当前主模型</p>
            <h2>{activeProfile?.label ?? "未设置"}</h2>
            <p className="subtle">{activeSummary}</p>
          </div>
        </div>

        <div className="llm-workbench">
          <div className="llm-library">
            <div className="llm-library-head">
              <strong>模型档位</strong>
              <span className="subtle-chip">点卡片，右边改；点按钮，直接切</span>
            </div>

            <div className="llm-profile-grid llm-profile-grid-stacked">
              {draftConfig.profiles.map((profile) => {
                const providerLabel = PROVIDER_REGISTRY[profile.provider_key]?.label ?? profile.provider_key;
                const isSelected = profile.id === selectedProfileId;
                const isCurrent = profile.id === draftConfig.current_profile_id;
                const hasKey = Boolean(profile.api_key.trim());
                const canSwitch = hasKey && !isCurrent;
                const preset = isPresetProfile(profile.id);

                return (
                  <article
                    key={profile.id}
                    className={`llm-profile-card ${isSelected ? "llm-profile-card-selected" : ""} ${isCurrent ? "llm-profile-card-current" : ""}`}
                    onClick={() => setSelectedProfileId(profile.id)}
                  >
                    <div className="llm-profile-head">
                      <div>
                        <strong>{profile.label}</strong>
                        <p>{providerLabel}</p>
                      </div>
                      <div className="llm-profile-badges">
                        <span className={`status-chip ${isCurrent ? "status-chip-ok" : hasKey ? "status-chip-warn" : "status-chip-muted"}`}>
                          {isCurrent ? "当前启用" : hasKey ? "已配置 Key" : "待配置"}
                        </span>
                        <span className="subtle-chip">{preset ? "预制" : "自定义"}</span>
                      </div>
                    </div>

                    <p className="llm-profile-model">{profile.model_id}</p>
                    <p className="subtle">{profile.description}</p>

                    <div className="llm-profile-actions llm-profile-actions-wrap">
                      <button
                        type="button"
                        className={isCurrent ? "secondary-button" : "primary-button"}
                        disabled={!canSwitch || switchingProfileId === profile.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleQuickSwitch(profile.id);
                        }}
                      >
                        {switchingProfileId === profile.id ? <Loader2 size={14} className="spin-icon" /> : null}
                        {isCurrent ? "使用中" : hasKey ? "切换启用" : "先配置 Key"}
                      </button>

                      <button
                        type="button"
                        className="ghost-button compact"
                        title="编辑档位"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedProfileId(profile.id);
                        }}
                      >
                        <Edit size={14} />
                      </button>

                      <button
                        type="button"
                        className="ghost-button compact"
                        title="测试连接"
                        disabled={!profile.api_key.trim() || testing}
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelectedProfileId(profile.id);
                          void handleTest();
                        }}
                      >
                        {testing ? <Loader2 size={14} className="spin-icon" /> : <TestTube2 size={14} />}
                      </button>

                      <button
                        type="button"
                        className="ghost-button compact"
                        title="复制档位"
                        onClick={(event) => {
                          event.stopPropagation();
                          handleDuplicateProfile(profile);
                        }}
                      >
                        <Copy size={14} />
                      </button>

                      {!preset ? (
                        <button
                          type="button"
                          className="ghost-button compact danger"
                          title="删除档位"
                          onClick={(event) => {
                            event.stopPropagation();
                            if (window.confirm(`确定要删除档位"${profile.label}"吗？`)) {
                              handleDeleteProfile(profile.id);
                            }
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          </div>

          {selectedProfile ? (
            <div className="llm-editor">
              <div className="llm-editor-head">
                <div>
                  <p className="eyebrow">当前编辑</p>
                  <h2>{selectedProfile.label}</h2>
                  <p className="subtle">
                    {isPresetProfile(selectedProfile.id)
                      ? "这是预制档位。你可以直接改成自己的可用配置，也可以复制一份做自定义变体。"
                      : "这是你自己的自定义档位。保存后会长期保留，随时可切换回来。"}
                  </p>
                </div>
              </div>

              <div className="source-form-grid compact">
                <label>
                  <span>档位名称</span>
                  <input type="text" value={selectedProfile.label} onChange={(e) => updateSelectedProfile({ label: e.target.value })} />
                </label>

                <label>
                  <span>服务商</span>
                  <select value={selectedProfile.provider_key} onChange={(e) => updateSelectedProfile({ provider_key: e.target.value })}>
                    {Object.entries(PROVIDER_REGISTRY).map(([key, item]) => (
                      <option key={key} value={key}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>模型</span>
                  <select value={selectedProfile.model_id} onChange={(e) => updateSelectedProfile({ model_id: e.target.value })}>
                    {registry.models.map((modelId) => (
                      <option key={modelId} value={modelId}>
                        {modelId}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  <span>Base URL</span>
                  <input type="text" value={selectedProfile.base_url} onChange={(e) => updateSelectedProfile({ base_url: e.target.value })} />
                </label>

                <label className="llm-key-field">
                  <span>API Key</span>
                  <div className="llm-key-input-row">
                    <input
                      type={showKey ? "text" : "password"}
                      value={selectedProfile.api_key}
                      placeholder="sk-... / nvapi-..."
                      onChange={(e) => updateSelectedProfile({ api_key: e.target.value, enabled: Boolean(e.target.value.trim()) })}
                    />
                    <button type="button" className="ghost-button compact" onClick={() => setShowKey((prev) => !prev)}>
                      {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </label>

                <label className="llm-profile-description-field">
                  <span>说明</span>
                  <textarea rows={3} value={selectedProfile.description} onChange={(e) => updateSelectedProfile({ description: e.target.value })} />
                </label>
              </div>

              <div className="mode-config-actions">
                <button type="button" className="primary-button" disabled={isSaving || !dirty} onClick={() => void handleSave()}>
                  <Save size={14} />
                  {isSaving ? "保存中..." : "保存当前修改"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={testing || !selectedProfile.api_key.trim()}
                  onClick={() => void handleTest()}
                >
                  {testing ? <Loader2 size={14} className="spin-icon" /> : <Zap size={14} />}
                  {testing ? "测试中..." : "保存并测试"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={!selectedProfile.api_key.trim() || switchingProfileId === selectedProfile.id}
                  onClick={() => void handleQuickSwitch(selectedProfile.id)}
                >
                  {switchingProfileId === selectedProfile.id ? <Loader2 size={14} className="spin-icon" /> : null}
                  {selectedProfile.id === draftConfig.current_profile_id ? "当前正在使用" : "设为当前主模型"}
                </button>
              </div>

              <div className="llm-editor-note">
                <span className="subtle-chip">
                  {selectedProfile.api_key.trim()
                    ? "同一服务商的 Key 会自动复用到这个服务商下的其他档位。"
                    : "先填入 Key，再切换不同模型。"}
                </span>
              </div>

              {testResult ? (
                <div className={`llm-test-result ${testResult.ok ? "llm-test-ok" : "llm-test-error"}`}>
                  {testResult.ok ? (
                    <>
                      <CheckCircle size={14} />
                      <span>
                        已连通 {selectedProfile.model_id}，返回 {testResult.content || "OK"}
                      </span>
                    </>
                  ) : (
                    <span>{testResult.error}</span>
                  )}
                </div>
              ) : null}
            </div>
          ) : null}

          {/* Task-level primary/fallback settings */}
          <div className="llm-tasks-section">
            <div className="llm-tasks-header">
              <p className="eyebrow">任务路由</p>
              <h3>主备模型配置</h3>
              <p className="subtle">每个任务的主模型不可用时，自动切换到备用模型。</p>
            </div>
            <div className="llm-tasks-grid">
              {draftConfig.tasks.map((task) => (
                <div key={task.task_key} className="llm-task-row">
                  <div className="llm-task-label">{task.label}</div>
                  <div className="llm-task-selects">
                    <select
                      value={task.provider_key}
                      onChange={(e) => {
                        const nextRegistry = PROVIDER_REGISTRY[e.target.value] ?? PROVIDER_REGISTRY.siliconflow;
                        const updatedTasks = draftConfig.tasks.map((t) =>
                          t.task_key === task.task_key
                            ? { ...t, provider_key: e.target.value, model_id: nextRegistry.models[0] ?? "" }
                            : t
                        );
                        updateTasks(updatedTasks);
                      }}
                    >
                      <option value="">-- 主模型服务商 --</option>
                      {Object.entries(PROVIDER_REGISTRY).map(([key, item]) => (
                        <option key={key} value={key}>{item.label}</option>
                      ))}
                    </select>
                    {task.provider_key && (
                      <select
                        value={task.model_id}
                        onChange={(e) => {
                          const updatedTasks = draftConfig.tasks.map((t) =>
                            t.task_key === task.task_key ? { ...t, model_id: e.target.value } : t
                          );
                          updateTasks(updatedTasks);
                        }}
                      >
                        {PROVIDER_REGISTRY[task.provider_key]?.models.map((modelId) => (
                          <option key={modelId} value={modelId}>{modelId}</option>
                        )) ?? <option value={task.model_id}>{task.model_id}</option>}
                      </select>
                    )}
                  </div>
                  <div className="llm-task-separator">→</div>
                  <div className="llm-task-selects">
                    <select
                      value={task.fallback_provider_key}
                      onChange={(e) => {
                        const nextRegistry = PROVIDER_REGISTRY[e.target.value] ?? PROVIDER_REGISTRY.siliconflow;
                        const updatedTasks = draftConfig.tasks.map((t) =>
                          t.task_key === task.task_key
                            ? { ...t, fallback_provider_key: e.target.value, fallback_model_id: nextRegistry.models[0] ?? "" }
                            : t
                        );
                        updateTasks(updatedTasks);
                      }}
                    >
                      <option value="">-- 备用服务商 --</option>
                      {Object.entries(PROVIDER_REGISTRY).map(([key, item]) => (
                        <option key={key} value={key}>{item.label}</option>
                      ))}
                    </select>
                    {task.fallback_provider_key && (
                      <select
                        value={task.fallback_model_id}
                        onChange={(e) => {
                          const updatedTasks = draftConfig.tasks.map((t) =>
                            t.task_key === task.task_key ? { ...t, fallback_model_id: e.target.value } : t
                          );
                          updateTasks(updatedTasks);
                        }}
                      >
                        {PROVIDER_REGISTRY[task.fallback_provider_key]?.models.map((modelId) => (
                          <option key={modelId} value={modelId}>{modelId}</option>
                        )) ?? <option value={task.fallback_model_id}>{task.fallback_model_id}</option>}
                      </select>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
