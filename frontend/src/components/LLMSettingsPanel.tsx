import { Download, Edit, ExternalLink, Eye, EyeOff, Loader2, Save, TestTube2, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { CCSwitchProviderInfo, LLMConfig, LLMProfileConfig, LLMTestResult } from "../types";

const SILICONFLOW_DEFAULT_MODEL = "THUDM/GLM-4-9B-0414";
const SILICONFLOW_MODEL_ALIASES_TO_MIGRATE = new Set(["glm4", "glm-4"]);

const PROVIDER_REGISTRY: Record<string, { label: string; base_url: string; models: string[]; free?: boolean }> = {
  nvidia: {
    label: "NVIDIA NIM",
    base_url: "https://integrate.api.nvidia.com/v1",
    free: true,
    models: [
      "qwen/qwen3.5-122b-a10b",
      "deepseek-ai/deepseek-v4-flash",
      "z-ai/glm4.7",
      "minimaxai/minimax-m2.7",
      "deepseek-ai/deepseek-v3.1-terminus",
      "deepseek-ai/deepseek-v4-pro",
      "google/gemma-4-31b-it",
    ],
  },
  siliconflow: {
    label: "SiliconFlow",
    base_url: "https://api.siliconflow.cn/v1",
    free: true,
    models: [
      "THUDM/GLM-4-9B-0414",
      "deepseek-ai/DeepSeek-V3",
      "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
      "Qwen/Qwen3-8B",
      "THUDM/GLM-Z1-9B-0414",
      "Qwen/Qwen3.5-4B",
    ],
  },
};

const PRESET_PROFILE_IDS = new Set(["preset-nvidia", "preset-siliconflow"]);

const DEFAULT_PROFILES: LLMProfileConfig[] = [
  {
    id: "preset-nvidia",
    label: "NVIDIA NIM",
    description: "免费模型平台，支持多种开源模型。",
    provider_key: "nvidia",
    base_url: "https://integrate.api.nvidia.com/v1",
    api_key: "",
    model_id: "qwen/qwen3.5-122b-a10b",
    enabled: false,
  },
  {
    id: "preset-siliconflow",
    label: "SiliconFlow",
    description: "免费模型平台，支持多种开源模型。",
    provider_key: "siliconflow",
    base_url: "https://api.siliconflow.cn/v1",
    api_key: "",
    model_id: SILICONFLOW_DEFAULT_MODEL,
    enabled: false,
  },
];

function normalizeProfiles(profiles: LLMProfileConfig[]) {
  const keys: Record<string, string> = {};
  for (const profile of profiles) {
    if (profile.api_key.trim() && !profile.api_key.includes("****")) {
      keys[profile.provider_key] = profile.api_key;
    }
  }
  return profiles.map((profile) => {
    const apiKey = profile.api_key || keys[profile.provider_key] || "";
    const nextModelId =
      profile.provider_key === "siliconflow" && SILICONFLOW_MODEL_ALIASES_TO_MIGRATE.has(profile.model_id.toLowerCase())
        ? SILICONFLOW_DEFAULT_MODEL
        : profile.model_id;
    return {
      ...profile,
      api_key: apiKey,
      model_id: nextModelId,
      enabled: Boolean(profile.enabled && apiKey.trim()),
    };
  });
}

function hasUsableApiKey(profile: Pick<LLMProfileConfig, "api_key">) {
  return Boolean(profile.api_key.trim()) && !profile.api_key.includes("****");
}

function hasConfiguredApiKey(profile: Pick<LLMProfileConfig, "api_key">) {
  return Boolean(profile.api_key.trim());
}

function isPreset(id: string) {
  return PRESET_PROFILE_IDS.has(id);
}

function isCCImport(id: string) {
  return id.startsWith("cc-");
}

function buildProviders(profiles: LLMProfileConfig[]) {
  return profiles
    .filter((profile) => hasUsableApiKey(profile))
    .map((profile) => ({
      key: profile.provider_key,
      label: profile.label,
      base_url: profile.base_url,
      api_key: profile.api_key,
      model_id: profile.model_id,
      enabled: profile.enabled,
    }));
}

function normalizeProfileSelection(
  profiles: LLMProfileConfig[],
  currentProfileId?: string | null,
  fallbackProfileId?: string | null,
) {
  const current = profiles.find((profile) => profile.id === currentProfileId) ?? profiles[0] ?? null;
  let fallback = profiles.find((profile) => profile.id === fallbackProfileId) ?? null;
  if (fallback && (!hasConfiguredApiKey(fallback) || fallback.id === current?.id)) {
    fallback = null;
  }
  return {
    current_profile_id: current?.id ?? "",
    fallback_profile_id: fallback?.id ?? null,
  };
}

function hydrate(config: LLMConfig | null): LLMConfig {
  const sourceProfiles = config?.profiles?.length ? config.profiles : [];
  const mergedPresets = DEFAULT_PROFILES.map((preset) => {
    const existing = sourceProfiles.find((profile) => profile.id === preset.id);
    return {
      ...preset,
      ...existing,
      provider_key: preset.provider_key,
      base_url: existing?.base_url || preset.base_url,
      model_id: existing?.model_id || preset.model_id,
    };
  });

  const legacyKeys: Record<string, string> = {};
  for (const profile of sourceProfiles) {
    if (isPreset(profile.id)) {
      continue;
    }
    if (profile.api_key?.trim() && !profile.api_key.includes("****")) {
      legacyKeys[profile.provider_key] = profile.api_key;
    }
  }

  for (const profile of mergedPresets) {
    if (!profile.api_key.trim() && legacyKeys[profile.provider_key]) {
      profile.api_key = legacyKeys[profile.provider_key];
    }
  }

  const customProfiles = sourceProfiles.filter((profile) => !isPreset(profile.id) && !["nvidia", "siliconflow"].includes(profile.provider_key));
  const profiles = normalizeProfiles([...mergedPresets, ...customProfiles]);
  const selection = normalizeProfileSelection(profiles, config?.current_profile_id, config?.fallback_profile_id);

  return {
    current_profile_id: selection.current_profile_id,
    fallback_profile_id: selection.fallback_profile_id,
    profiles,
    providers: buildProviders(profiles),
    usage_today: config?.usage_today ?? {},
  };
}

function profileOptionLabel(profile: LLMProfileConfig) {
  return `${profile.label}${profile.model_id ? ` / ${profile.model_id}` : " / 默认模型"}${hasConfiguredApiKey(profile) ? "" : " / 未配置"}`;
}

function formatAppType(profile: Pick<LLMProfileConfig, "cc_app_type">) {
  const appType = profile.cc_app_type ?? "";
  if (appType === "claude") {
    return "Claude";
  }
  if (appType === "codex") {
    return "Codex";
  }
  if (appType === "gemini") {
    return "Gemini";
  }
  return appType || "通用";
}

function formatApiFormat(format?: string | null) {
  if (format === "openai_chat") {
    return "OpenAI Chat";
  }
  if (format === "openai_responses") {
    return "OpenAI Responses";
  }
  if (format === "anthropic") {
    return "Anthropic Messages";
  }
  if (format === "gemini_native") {
    return "Gemini Native";
  }
  return "未声明";
}

function formatProbeStatus(status?: string | null) {
  if (status === "verified") {
    return "已验证";
  }
  if (status === "html_homepage") {
    return "返回首页";
  }
  if (status === "auth_failed") {
    return "认证失败";
  }
  if (status === "protocol_mismatch") {
    return "协议不匹配";
  }
  if (status === "model_missing") {
    return "缺少模型";
  }
  if (status === "connection_failed") {
    return "连接失败";
  }
  if (status === "rate_limited") {
    return "请求限流";
  }
  if (status === "request_failed") {
    return "请求失败";
  }
  return "尚未验证";
}

function isVerifiedForGeneration(profile: Pick<LLMProfileConfig, "cc_probe_status"> | null) {
  return profile?.cc_probe_status === "verified";
}

function EditDialog({ profile, onSave, onClose }: { profile: LLMProfileConfig; onSave: (p: LLMProfileConfig) => void; onClose: () => void }) {
  const [draft, setDraft] = useState(profile);
  const [showKey, setShowKey] = useState(false);
  const registry = PROVIDER_REGISTRY[draft.provider_key];
  const isPresetProfile = isPreset(draft.id);
  const isCC = isCCImport(draft.id);
  const isKeyMasked = draft.api_key.includes("****");

  return (
    <div className="cc-dialog-overlay" onClick={onClose}>
      <div className="cc-dialog-panel" onClick={(event) => event.stopPropagation()}>
        <div className="cc-dialog-header">
          <h3>编辑模型</h3>
          <button className="ghost-button icon-only" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="source-form-grid">
          <label><span>模型名称</span><input type="text" value={draft.label} onChange={(event) => setDraft((prev) => ({ ...prev, label: event.target.value }))} /></label>
          <label><span>服务商</span>
            {isPresetProfile || isCC ? (
              <input type="text" value={registry?.label ?? draft.provider_key} disabled className="disabled-input" />
            ) : (
              <input type="text" value={draft.provider_key} onChange={(event) => setDraft((prev) => ({ ...prev, provider_key: event.target.value }))} />
            )}
          </label>
          {isPresetProfile ? (
            <label><span>模型</span>
              <select value={draft.model_id} onChange={(event) => setDraft((prev) => ({ ...prev, model_id: event.target.value }))}>
                {(registry?.models ?? []).map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            </label>
          ) : (
            <>
              <label><span>Base URL</span>
                {isCC ? (
                  <input type="text" value={draft.base_url} disabled className="disabled-input" />
                ) : (
                  <input type="text" value={draft.base_url} onChange={(event) => setDraft((prev) => ({ ...prev, base_url: event.target.value }))} />
                )}
              </label>
              <label><span>模型 ID</span><input type="text" value={draft.model_id} onChange={(event) => setDraft((prev) => ({ ...prev, model_id: event.target.value }))} placeholder="留空则使用中转站默认模型" /></label>
            </>
          )}
          <label className="llm-key-field"><span>API Key</span>
            {isCC && isKeyMasked ? (
              <div>
                <input type="text" value={draft.api_key} disabled className="disabled-input" />
                <p style={{ margin: "4px 0 0", fontSize: 12, color: "#64748b" }}>密钥已脱敏，如需更新请从 CC-Switch 重新导入</p>
              </div>
            ) : (
              <div className="llm-key-input-row">
                <input type={showKey ? "text" : "password"} value={draft.api_key} placeholder="sk-... / nvapi-..." onChange={(event) => setDraft((prev) => ({ ...prev, api_key: event.target.value }))} />
                <button className="ghost-button compact" onClick={() => setShowKey((value) => !value)}>{showKey ? <EyeOff size={14} /> : <Eye size={14} />}</button>
              </div>
            )}
          </label>
          <label className="llm-profile-description-field"><span>说明</span><textarea rows={2} value={draft.description} onChange={(event) => setDraft((prev) => ({ ...prev, description: event.target.value }))} /></label>
        </div>
        <div className="cc-dialog-footer">
          <button className="secondary-button" onClick={onClose}>取消</button>
          <button className="primary-button" onClick={() => onSave(draft)}><Save size={14} />保存</button>
        </div>
      </div>
    </div>
  );
}

function CCImportDialog({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [providers, setProviders] = useState<CCSwitchProviderInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const result = await api.getCCSwitchProviders();
        setProviders(result.providers);
        if (!result.db_available) {
          setError("未找到 CC-Switch 数据库，请确认 CC-Switch 已安装并配置了 provider。");
        }
      } catch {
        setError("读取 CC-Switch 数据失败。");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function toggle(id: string) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === providers.length) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(providers.map((provider) => provider.id)));
  }

  async function handleImport() {
    if (selected.size === 0) {
      return;
    }
    setImporting(true);
    try {
      await api.importCCSwitchProviders([...selected]);
      onImported();
      onClose();
    } catch {
      setError("导入失败，请重试。");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="cc-dialog-overlay" onClick={onClose}>
      <div className="cc-dialog-panel" onClick={(event) => event.stopPropagation()}>
        <div className="cc-dialog-header">
          <h3>从 CC-Switch 导入</h3>
          <button className="ghost-button icon-only" onClick={onClose}><X size={18} /></button>
        </div>
        <div style={{ padding: "20px" }}>
          {loading && <div className="llm-cc-loading">正在读取 CC-Switch 数据...</div>}
          {error && <div className="llm-cc-error">{error}</div>}
          {!loading && !error && providers.length === 0 && (
            <div className="llm-cc-empty">CC-Switch 中没有找到可导入的 provider。</div>
          )}
          {!loading && providers.length > 0 && (
            <>
              <div className="llm-cc-toolbar">
                <button className="ghost-button compact" onClick={toggleAll}>
                  {selected.size === providers.length ? "取消全选" : "全选"}
                </button>
                <span className="llm-cc-count">已选 {selected.size} / {providers.length}</span>
              </div>
              <div className="llm-cc-list">
                {providers.map((provider) => (
                  <label key={provider.id} className={`llm-cc-item ${selected.has(provider.id) ? "llm-cc-item-selected" : ""}`}>
                    <input type="checkbox" checked={selected.has(provider.id)} onChange={() => toggle(provider.id)} />
                    <div className="llm-cc-item-info">
                      <div className="llm-cc-item-name">
                        {provider.label}
                        {provider.cc_is_current && <span className="llm-cc-badge-current">当前使用</span>}
                        {provider.cc_health && !provider.cc_health.is_healthy && <span className="llm-cc-badge-unhealthy">异常</span>}
                        {!provider.model_id && <span className="llm-cc-badge-relay">中转站</span>}
                      </div>
                      <div className="llm-cc-item-detail">
                        <span>{provider.base_url || "无 URL"}</span>
                        <span>{provider.model_id || "默认模型"}</span>
                        <span>{formatApiFormat(provider.cc_api_format)}</span>
                        {provider.api_key_preview && <span className="llm-cc-item-key">{provider.api_key_preview}</span>}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="cc-dialog-footer">
          <button className="secondary-button" onClick={onClose}>取消</button>
          <button className="primary-button" disabled={selected.size === 0 || importing} onClick={() => void handleImport()}>
            {importing ? <><Loader2 size={14} className="spin-icon" />导入中...</> : <><Download size={14} />导入 {selected.size > 0 ? `(${selected.size})` : ""}</>}
          </button>
        </div>
      </div>
    </div>
  );
}

export function LLMSettingsPanel({
  config: initialConfig,
  tavilyApiKey: initialTavilyApiKey,
  isSaving,
  onSave,
}: {
  config: LLMConfig;
  tavilyApiKey: string;
  isSaving: boolean;
  onSave: (config: LLMConfig, tavilyApiKey: string) => Promise<void>;
}) {
  const [draftConfig, setDraftConfig] = useState<LLMConfig>(() => hydrate(initialConfig));
  const [tavilyApiKey, setTavilyApiKey] = useState(initialTavilyApiKey);
  const [editingProfile, setEditingProfile] = useState<LLMProfileConfig | null>(null);
  const [testingProfileId, setTestingProfileId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<LLMTestResult | null>(null);
  const [showCCImport, setShowCCImport] = useState(false);

  useEffect(() => {
    setDraftConfig(hydrate(initialConfig));
    setTavilyApiKey(initialTavilyApiKey);
    setTestResult(null);
  }, [initialConfig, initialTavilyApiKey]);

  function updateProfiles(
    profiles: LLMProfileConfig[],
    opts?: { currentProfileId?: string | null; fallbackProfileId?: string | null },
  ): LLMConfig {
    const normalizedProfiles = normalizeProfiles(profiles);
    const selection = normalizeProfileSelection(
      normalizedProfiles,
      opts?.currentProfileId ?? draftConfig.current_profile_id,
      opts?.fallbackProfileId ?? draftConfig.fallback_profile_id,
    );
    const nextConfig: LLMConfig = {
      current_profile_id: selection.current_profile_id,
      fallback_profile_id: selection.fallback_profile_id,
      profiles: normalizedProfiles,
      providers: buildProviders(normalizedProfiles),
      usage_today: draftConfig.usage_today,
    };
    setDraftConfig(nextConfig);
    return nextConfig;
  }

  async function handleSave() {
    await onSave(draftConfig, tavilyApiKey);
  }

  async function handleTest(profile: LLMProfileConfig) {
    setTestingProfileId(profile.id);
    setTestResult(null);
    try {
      const result = await api.testLLMProvider(profile.id);
      setTestResult(result);
      setDraftConfig((previous) => ({
        ...previous,
        profiles: previous.profiles.map((item) => {
          if (item.id !== profile.id) {
            return item;
          }
          return {
            ...item,
            cc_probe_status: result.probe_status,
            cc_probe_message: result.ok ? result.probe_message : (result.error || result.probe_message),
            cc_last_verified_endpoint: result.ok ? (result.resolved_endpoint || item.cc_last_verified_endpoint || null) : item.cc_last_verified_endpoint,
            cc_last_verified_format: result.ok ? (result.resolved_format || item.cc_last_verified_format || null) : item.cc_last_verified_format,
            cc_last_verified_model: result.ok ? (result.resolved_model || result.model || item.cc_last_verified_model || null) : item.cc_last_verified_model,
          };
        }),
      }));
    } catch (error) {
      setTestResult({
        ok: false,
        model: "",
        content: "",
        latency_ms: 0,
        error: String(error),
        probe_status: "request_failed",
        probe_message: "请求失败",
        resolved_endpoint: "",
        resolved_format: "",
        resolved_model: "",
        supports_generation: false,
      });
    } finally {
      setTestingProfileId(null);
    }
  }

  async function handleDelete(profileId: string) {
    const profile = draftConfig.profiles.find((item) => item.id === profileId);
    if (!profile || !window.confirm(`确定删除 "${profile.label}" 吗？`)) {
      return;
    }
    const remaining = draftConfig.profiles.filter((item) => item.id !== profileId);
    const nextCurrentId = draftConfig.current_profile_id === profileId ? (remaining[0]?.id ?? "") : draftConfig.current_profile_id;
    const nextFallbackId = draftConfig.fallback_profile_id === profileId ? null : draftConfig.fallback_profile_id;
    const nextConfig = updateProfiles(remaining, {
      currentProfileId: nextCurrentId,
      fallbackProfileId: nextFallbackId,
    });
    await onSave(nextConfig, tavilyApiKey);
  }

  async function handleCCImported() {
    const fresh = await api.getLLMConfig();
    setDraftConfig(() => hydrate(fresh.item));
  }

  const customProfiles = draftConfig.profiles.filter((profile) => !isPreset(profile.id));
  const configuredProfiles = draftConfig.profiles.filter((profile) => hasConfiguredApiKey(profile));
  const activeProfile = draftConfig.profiles.find((profile) => profile.id === draftConfig.current_profile_id) ?? null;
  const fallbackProfile = draftConfig.profiles.find((profile) => profile.id === draftConfig.fallback_profile_id) ?? null;
  const activeReady = activeProfile ? hasConfiguredApiKey(activeProfile) : false;
  const activeVerified = isVerifiedForGeneration(activeProfile);
  const activeIsCC = Boolean(activeProfile && isCCImport(activeProfile.id));

  return (
    <div>
      <div className="llm-workbench">
        <div className="llm-library">
          <div className="llm-library-head">
            <div>
              <strong>模型库</strong>
              <p className="subtle" style={{ margin: "2px 0 0", fontSize: 12 }}>
                已配置 {draftConfig.profiles.filter((profile) => hasConfiguredApiKey(profile)).length} / {draftConfig.profiles.length}
              </p>
            </div>
            <div className="panel-header-actions">
              <button className="secondary-button compact" onClick={() => setShowCCImport(true)}>
                <Download size={14} />从 CC-Switch 导入
              </button>
              <button className="primary-button compact" onClick={() => void api.openCCSwitch()}>
                <ExternalLink size={14} />添加模型
              </button>
            </div>
          </div>

          <div className="llm-model-grid">
            {DEFAULT_PROFILES.map((preset) => {
              const profile = draftConfig.profiles.find((item) => item.id === preset.id) ?? preset;
              const hasKey = hasConfiguredApiKey(profile);
              const registry = PROVIDER_REGISTRY[profile.provider_key];
              return (
                <div key={profile.id} className={`llm-model-card ${hasKey ? "llm-model-card-configured" : ""}`}>
                  <div className="llm-model-card-header">
                    <span className="llm-model-name">{profile.label}</span>
                    <span className="llm-model-badge-free">免费</span>
                  </div>
                  <div className="llm-model-card-body">
                    <span className="llm-model-provider">{registry?.label ?? profile.provider_key}</span>
                    <span className="llm-model-id">{profile.model_id || "未设置"}</span>
                  </div>
                  <div className="llm-model-card-actions">
                    <button className="ghost-button compact icon-only" title="编辑" onClick={() => setEditingProfile(profile)}><Edit size={12} /></button>
                    <button className="ghost-button compact icon-only" title="测试" disabled={!hasKey || testingProfileId === profile.id} onClick={() => void handleTest(profile)}>
                      {testingProfileId === profile.id ? <Loader2 size={12} className="spin-icon" /> : <TestTube2 size={12} />}
                    </button>
                  </div>
                </div>
              );
            })}

            {customProfiles.map((profile) => {
              const hasKey = hasConfiguredApiKey(profile);
              const registry = PROVIDER_REGISTRY[profile.provider_key];
              const ccImported = isCCImport(profile.id);
              const isRelay = !profile.model_id.trim();
              return (
                <div key={profile.id} className={`llm-model-card ${hasKey ? "llm-model-card-configured" : ""}`}>
                  <div className="llm-model-card-header">
                    <span className="llm-model-name">{profile.label}</span>
                    {ccImported && <span className="llm-model-badge-cc">CC</span>}
                    {isRelay && <span className="llm-model-badge-relay">中转站</span>}
                  </div>
                  <div className="llm-model-card-body">
                    <span className="llm-model-provider">{registry?.label ?? profile.provider_key}</span>
                    <span className="llm-model-id">{isRelay ? "默认" : profile.model_id}</span>
                  </div>
                  <div className="llm-model-card-actions">
                    <button className="ghost-button compact icon-only" title="编辑" onClick={() => setEditingProfile(profile)}><Edit size={12} /></button>
                    <button className="ghost-button compact icon-only" title="测试" disabled={!hasKey || testingProfileId === profile.id} onClick={() => void handleTest(profile)}>
                      {testingProfileId === profile.id ? <Loader2 size={12} className="spin-icon" /> : <TestTube2 size={12} />}
                    </button>
                    <button className="ghost-button compact icon-only danger" title="删除" onClick={() => void handleDelete(profile.id)}><Trash2 size={12} /></button>
                  </div>
                </div>
              );
            })}
          </div>

          {testResult && (
            <div style={{ marginTop: 12, padding: 10, borderRadius: 8, background: testResult.ok ? "#ecfdf5" : "#fef2f2", border: `1px solid ${testResult.ok ? "#a7f3d0" : "#fecaca"}`, fontSize: 13 }}>
              <strong>{testResult.ok ? (testResult.supports_generation ? "测试成功，可用于增强简报" : "连接成功") : "测试失败"}</strong>
              {testResult.ok ? (
                <>
                  <p style={{ margin: "4px 0 0", color: "#166534" }}>
                    {formatProbeStatus(testResult.probe_status)} · {testResult.resolved_format || "未识别协议"} · {testResult.resolved_model || testResult.model || "未识别模型"}
                  </p>
                  <p style={{ margin: "4px 0 0", color: "#166534" }}>
                    {testResult.content || "已返回有效结果"} ({testResult.latency_ms}ms)
                  </p>
                  {testResult.resolved_endpoint ? (
                    <p style={{ margin: "4px 0 0", color: "#166534", wordBreak: "break-all" }}>
                      端点：{testResult.resolved_endpoint}
                    </p>
                  ) : null}
                </>
              ) : (
                <>
                  <p style={{ margin: "4px 0 0", color: "#991b1b" }}>{formatProbeStatus(testResult.probe_status)}</p>
                  <p style={{ margin: "4px 0 0", color: "#991b1b" }}>{testResult.error || testResult.probe_message}</p>
                  {testResult.resolved_endpoint ? (
                    <p style={{ margin: "4px 0 0", color: "#991b1b", wordBreak: "break-all" }}>
                      端点：{testResult.resolved_endpoint}
                    </p>
                  ) : null}
                </>
              )}
            </div>
          )}
        </div>

        <div className="llm-editor">
          <div className="llm-editor-head">
            <strong>当前默认模型</strong>
          </div>
          <p className="subtle" style={{ fontSize: 13, marginBottom: 12 }}>
            系统只在生成增强简报时使用 AI。这里决定默认模型。
          </p>
          <div className="llm-task-row" style={{ marginBottom: 20 }}>
            <span className="llm-task-label">默认模型</span>
            <div className="llm-task-selects">
              <select
                value={draftConfig.current_profile_id}
                onChange={(event) => {
                  const nextCurrentId = event.target.value;
                  const nextFallbackId = draftConfig.fallback_profile_id === nextCurrentId ? null : draftConfig.fallback_profile_id;
                  updateProfiles(draftConfig.profiles, {
                    currentProfileId: nextCurrentId,
                    fallbackProfileId: nextFallbackId,
                  });
                  setTestResult(null);
                }}
              >
                {draftConfig.profiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profileOptionLabel(profile)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="llm-editor-head">
            <strong>备用模型</strong>
          </div>
          <p className="subtle" style={{ fontSize: 13, marginBottom: 12 }}>
            默认模型遇到限流、超时或连接失败时，系统会自动切到这里继续补全增强简报。
          </p>
          <div className="llm-task-row">
            <span className="llm-task-label">备用模型</span>
            <div className="llm-task-selects">
              <select
                value={draftConfig.fallback_profile_id ?? ""}
                onChange={(event) => {
                  updateProfiles(draftConfig.profiles, {
                    currentProfileId: draftConfig.current_profile_id,
                    fallbackProfileId: event.target.value || null,
                  });
                  setTestResult(null);
                }}
              >
                <option value="">无备用模型</option>
                {configuredProfiles
                  .filter((profile) => profile.id !== draftConfig.current_profile_id)
                  .map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profileOptionLabel(profile)}
                    </option>
                  ))}
              </select>
            </div>
          </div>

          <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 10, background: "#f8fafc", border: "1px solid #e2e8f0", fontSize: 13, color: "#475569" }}>
            <div><strong>当前生效：</strong>{activeProfile ? profileOptionLabel(activeProfile) : "未选择"}</div>
            <div style={{ marginTop: 4 }}><strong>自动切换：</strong>{fallbackProfile ? profileOptionLabel(fallbackProfile) : "未配置备用模型"}</div>
          </div>

          {activeProfile && (
            <div className="llm-runtime-card">
              <div className="llm-runtime-row">
                <strong>当前状态</strong>
                <span className={`llm-runtime-badge ${activeVerified ? "llm-runtime-badge-ok" : "llm-runtime-badge-warn"}`}>
                  {activeVerified ? "可用于增强简报" : "存在运行风险"}
                </span>
              </div>
              <div className="llm-runtime-grid">
                <span>来源：{activeIsCC ? `CC-Switch / ${formatAppType(activeProfile)}` : "本地模型卡"}</span>
                <span>协议：{formatApiFormat(activeProfile.cc_api_format)}</span>
                <span>完整 URL：{activeProfile.cc_is_full_url ? "是" : "否"}</span>
                <span>自动选端点：{activeProfile.cc_endpoint_auto_select === false ? "关闭" : "开启"}</span>
                <span>验证状态：{formatProbeStatus(activeProfile.cc_probe_status)}</span>
                <span>模型：{activeProfile.cc_last_verified_model || activeProfile.model_id || "未确认"}</span>
              </div>
              {activeProfile.cc_probe_message ? (
                <p className="subtle" style={{ marginTop: 8 }}>{activeProfile.cc_probe_message}</p>
              ) : null}
              {activeProfile.cc_last_verified_endpoint ? (
                <p className="subtle llm-runtime-endpoint">已验证端点：{activeProfile.cc_last_verified_endpoint}</p>
              ) : null}
            </div>
          )}

          {!activeReady && (
            <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 10, background: "#fff7ed", border: "1px solid #fed7aa", fontSize: 13, color: "#9a3412" }}>
              当前默认模型还没有可用 API Key，增强简报时不会调用 AI。
            </div>
          )}

          {activeReady && !activeVerified && (
            <div style={{ marginTop: 12, padding: "10px 12px", borderRadius: 10, background: "#fff7ed", border: "1px solid #fed7aa", fontSize: 13, color: "#9a3412" }}>
              当前默认模型尚未完成增强简报能力验证。建议先点一次测试，确认它不是网页首页、协议不匹配或缺少模型。
            </div>
          )}

          <div style={{ marginTop: 20, padding: "14px 16px", borderRadius: 12, background: "#f8fafc", border: "1px solid #e2e8f0" }}>
            <div className="llm-editor-head" style={{ marginBottom: 8 }}>
              <strong>Tavily</strong>
            </div>
            <p className="subtle" style={{ fontSize: 13, marginBottom: 12 }}>
              Tavily 只在正文深挖前补充来源，不参与增强简报模型主备切换。
            </p>
            <label className="llm-key-field">
              <span>Tavily API Key</span>
              <input
                type="password"
                value={tavilyApiKey}
                onChange={(event) => setTavilyApiKey(event.target.value)}
                placeholder="tvly-..."
              />
            </label>
          </div>

          <div style={{ marginTop: 20, display: "flex", justifyContent: "flex-end" }}>
            <button className="primary-button" disabled={isSaving} onClick={() => void handleSave()}>
              {isSaving ? <><Loader2 size={14} className="spin-icon" />保存中...</> : <><Save size={14} />保存配置</>}
            </button>
          </div>
        </div>
      </div>

      {editingProfile && (
        <EditDialog
          profile={editingProfile}
          onSave={(updated) => {
            const profiles = draftConfig.profiles.map((profile) => profile.id === updated.id ? updated : profile);
            const nextConfig = updateProfiles(profiles);
            onSave(nextConfig, tavilyApiKey).then(() => setEditingProfile(null));
          }}
          onClose={() => setEditingProfile(null)}
        />
      )}
      {showCCImport && (
        <CCImportDialog
          onClose={() => setShowCCImport(false)}
          onImported={() => void handleCCImported()}
        />
      )}
    </div>
  );
}
