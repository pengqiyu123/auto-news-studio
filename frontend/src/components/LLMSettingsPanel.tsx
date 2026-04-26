import { CheckCircle, Eye, EyeOff, Loader2, RotateCcw, Save, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import type { LLMConfig, LLMProviderConfig, LLMTaskConfig, LLMTestResult } from "../types";

const PROVIDER_REGISTRY: Record<string, { label: string; base_url: string; models: string[]; free_models?: string[] }> = {
  deepseek: { label: "DeepSeek", base_url: "https://api.deepseek.com/v1", models: ["deepseek-chat", "deepseek-reasoner"] },
  openrouter: { label: "OpenRouter", base_url: "https://openrouter.ai/api/v1", models: ["deepseek/deepseek-v3.2", "anthropic/claude-sonnet-4", "openai/gpt-4o", "google/gemini-2.5-flash"] },
  doubao: { label: "豆包 (火山引擎)", base_url: "https://ark.cn-beijing.volces.com/api/v3", models: ["doubao-seed-1-8-251228", "doubao-1-5-pro-32k-250115"] },
  glm: { label: "智谱 GLM", base_url: "https://open.bigmodel.cn/api/paas/v4", models: ["glm-4.7-flash", "glm-4-plus", "glm-4-flash", "glm-4-air"], free_models: ["glm-4.7-flash"] },
  siliconflow: { label: "SiliconFlow", base_url: "https://api.siliconflow.cn/v1", models: ["Qwen/Qwen3-8B", "deepseek-ai/DeepSeek-V3"] },
  qwen: { label: "通义千问", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen-turbo", "qwen-plus", "qwen-max"] },
  openai: { label: "OpenAI", base_url: "https://api.openai.com/v1", models: ["gpt-4o", "gpt-4o-mini", "o3-mini"] },
};

const DEFAULT_TASKS: LLMTaskConfig[] = [
  { task_key: "outline", label: "大纲生成", provider_key: "", model_id: "", temperature: 0.4, max_tokens: 2048, system_prompt: "" },
  { task_key: "article", label: "正文撰写", provider_key: "", model_id: "", temperature: 0.7, max_tokens: 4096, system_prompt: "" },
  { task_key: "title", label: "标题优化", provider_key: "", model_id: "", temperature: 0.8, max_tokens: 512, system_prompt: "" },
  { task_key: "summary", label: "摘要生成", provider_key: "", model_id: "", temperature: 0.5, max_tokens: 1024, system_prompt: "" },
];

interface LLMSettingsPanelProps {
  config: LLMConfig | null;
  isSaving: boolean;
  onSave: (config: LLMConfig) => Promise<void>;
}

export function LLMSettingsPanel({ config: initialConfig, isSaving, onSave }: LLMSettingsPanelProps) {
  const [config, setConfig] = useState<LLMConfig | null>(initialConfig);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [testingKey, setTestingKey] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, LLMTestResult>>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setConfig(initialConfig);
    setDirty(false);
  }, [initialConfig]);

  const updateProvider = useCallback((key: string, patch: Partial<LLMProviderConfig>) => {
    setConfig((prev) => {
      if (!prev) return prev;
      const providers = prev.providers.map((p) => (p.key === key ? { ...p, ...patch } : p));
      return { ...prev, providers };
    });
    setDirty(true);
  }, []);

  const addProvider = useCallback((key: string) => {
    setConfig((prev) => {
      if (!prev) return prev;
      if (prev.providers.some((p) => p.key === key)) return prev;
      const registry = PROVIDER_REGISTRY[key];
      return { ...prev, providers: [...prev.providers, { key, api_key: "", base_url: registry.base_url, enabled: false }] };
    });
    setDirty(true);
  }, []);

  const removeProvider = useCallback((key: string) => {
    setConfig((prev) => {
      if (!prev) return prev;
      return { ...prev, providers: prev.providers.filter((p) => p.key !== key) };
    });
    setDirty(true);
  }, []);

  const updateTask = useCallback((taskKey: string, patch: Partial<LLMTaskConfig>) => {
    setConfig((prev) => {
      if (!prev) return prev;
      const tasks = prev.tasks.map((t) => (t.task_key === taskKey ? { ...t, ...patch } : t));
      return { ...prev, tasks };
    });
    setDirty(true);
  }, []);

  const ensureTasks = useCallback(() => {
    setConfig((prev) => {
      if (!prev) return prev;
      const existingKeys = new Set(prev.tasks.map((t) => t.task_key));
      const missing = DEFAULT_TASKS.filter((t) => !existingKeys.has(t.task_key));
      if (missing.length === 0) return prev;
      return { ...prev, tasks: [...prev.tasks, ...missing] };
    });
  }, []);

  const testProvider = useCallback(
    async (key: string) => {
      setTestingKey(key);
      try {
        const result = await api.testLLMProvider(key);
        setTestResults((prev) => ({ ...prev, [key]: result }));
      } catch {
        setTestResults((prev) => ({ ...prev, [key]: { ok: false, model: "", content: "", latency_ms: 0, error: "请求失败" } }));
      } finally {
        setTestingKey(null);
      }
    },
    [],
  );

  const handleSave = async () => {
    if (!config) return;
    ensureTasks();
    await onSave(config);
    setDirty(false);
  };

  const enabledProviders = config?.providers.filter((p) => p.enabled) ?? [];
  const availableKeys = enabledProviders.map((p) => p.key);
  const unusedProviders = Object.keys(PROVIDER_REGISTRY).filter((k) => !config?.providers.some((p) => p.key === k));

  if (!config) {
    return (
      <section className="panel">
        <p className="empty-state">正在加载 AI 模型配置...</p>
      </section>
    );
  }

  return (
    <div className="page-content">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">AI 模型配置</p>
            <h2>选择并配置 LLM 服务商</h2>
            <p className="subtle">启用至少一个服务商并分配任务模型后，文章生成将使用真实 AI 输出。</p>
          </div>
          <div className="panel-header-actions">
            {dirty && <span className="dirty-chip">有未保存的修改</span>}
            <button type="button" className="primary-button" disabled={isSaving || !dirty} onClick={() => void handleSave()}>
              <Save size={14} />
              {isSaving ? "保存中..." : "保存配置"}
            </button>
          </div>
        </div>

        {enabledProviders.length === 0 && (
          <div className="channel-notice">
            <strong>尚未配置任何 AI 服务商</strong>
            <p>添加并启用至少一个服务商后，文章生成将从模板模式切换为 AI 模式。未配置时仍可使用模板生成。</p>
          </div>
        )}

        {config.providers.length > 0 && (
          <div className="source-list">
            {config.providers.map((provider) => {
              const registry = PROVIDER_REGISTRY[provider.key];
              const label = registry?.label ?? provider.key;
              const models = registry?.models ?? [];
              const testResult = testResults[provider.key];
              const isTesting = testingKey === provider.key;

              return (
                <div key={provider.key} className="source-card">
                  <div className="source-card-head">
                    <div>
                      <strong>{label}</strong>
                      {registry?.free_models && registry.free_models.length > 0 && (
                        <span style={{ marginLeft: 6, display: "inline-block", padding: "1px 6px", borderRadius: 4, background: "#dcfce7", color: "#166534", fontSize: 11, fontWeight: 600 }}>
                          有免费模型
                        </span>
                      )}
                      <p>
                        {provider.enabled ? (
                          <span className="status-badge status-success">已启用</span>
                        ) : (
                          <span className="status-badge status-neutral">未启用</span>
                        )}
                        {provider.last_test_result && (
                          <span className={`status-badge ${provider.last_test_result === "ok" ? "status-success" : "status-danger"}`} style={{ marginLeft: 8 }}>
                            {provider.last_test_result === "ok" ? "连接正常" : "连接失败"}
                          </span>
                        )}
                      </p>
                    </div>
                    <div className="table-actions">
                      <button type="button" className="secondary-button" disabled={isTesting || !provider.api_key || !provider.enabled} onClick={() => void testProvider(provider.key)}>
                        {isTesting ? <Loader2 size={14} className="spin-icon" /> : <Zap size={14} />}
                        {isTesting ? "测试中..." : "测试连接"}
                      </button>
                      <button type="button" className="ghost-button compact" onClick={() => removeProvider(provider.key)}>
                        移除
                      </button>
                    </div>
                  </div>

                  {!provider.api_key && provider.enabled && (
                    <div style={{ marginTop: 8, padding: "8px 12px", borderRadius: 6, background: "#fffbeb", fontSize: 13, color: "#92400e" }}>
                      请填入 API Key 后点击「测试连接」验证可用性。
                    </div>
                  )}

                  {testResult && (
                    <div style={{ marginTop: 8, padding: "8px 12px", borderRadius: 6, background: testResult.ok ? "#f0fdf4" : "#fef2f2", fontSize: 13 }}>
                      {testResult.ok ? (
                        <span>
                          <CheckCircle size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />
                          模型 {testResult.model} 响应正常，延迟 {testResult.latency_ms.toFixed(0)}ms
                        </span>
                      ) : (
                        <span style={{ color: "#b91c1c" }}>{testResult.error}</span>
                      )}
                    </div>
                  )}

                  <div className="source-form-grid compact">
                    <label>
                      <span>启用</span>
                      <div className="toggle-field">
                        <span>{provider.enabled ? "已启用" : "未启用"}</span>
                        <button
                          type="button"
                          className={`secondary-button inline-toggle ${provider.enabled ? "primary-button" : ""}`}
                          onClick={() => updateProvider(provider.key, { enabled: !provider.enabled })}
                        >
                          {provider.enabled ? "ON" : "OFF"}
                        </button>
                      </div>
                    </label>
                    <label>
                      <span>API Key</span>
                      <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                        <input
                          type={showKeys[provider.key] ? "text" : "password"}
                          value={provider.api_key}
                          placeholder="sk-..."
                          onChange={(e) => updateProvider(provider.key, { api_key: e.target.value })}
                        />
                        <button type="button" className="ghost-button compact" onClick={() => setShowKeys((prev) => ({ ...prev, [provider.key]: !prev[provider.key] }))}>
                          {showKeys[provider.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </label>
                    {provider.base_url && (
                      <label>
                        <span>Base URL</span>
                        <input
                          type="text"
                          value={provider.base_url}
                          onChange={(e) => updateProvider(provider.key, { base_url: e.target.value })}
                        />
                      </label>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {unusedProviders.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <p className="subtle" style={{ marginBottom: 8 }}>
              添加服务商：
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {unusedProviders.map((key) => (
                <button key={key} type="button" className="secondary-button" onClick={() => addProvider(key)}>
                  + {PROVIDER_REGISTRY[key].label}
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {availableKeys.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">任务-模型分配</p>
              <h2>为每个生成任务指定服务商和模型</h2>
              <p className="subtle">不同任务可以使用不同模型，大纲用低成本模型、正文用高质量模型。</p>
            </div>
            <div className="panel-header-actions">
              <button type="button" className="ghost-button compact" onClick={ensureTasks}>
                <RotateCcw size={14} />
                重置为默认
              </button>
            </div>
          </div>

          <div className="mode-config-grid">
            {(config.tasks.length > 0 ? config.tasks : DEFAULT_TASKS).map((task) => {
              const providerModels = task.provider_key ? PROVIDER_REGISTRY[task.provider_key]?.models ?? [] : [];

              return (
                <div key={task.task_key} className="mode-config-details" style={{ padding: 14 }}>
                  <div style={{ marginBottom: 10 }}>
                    <strong>{task.label}</strong>
                    <p style={{ margin: "2px 0 0", color: "#64748b", fontSize: 12 }}>
                      {task.provider_key && task.model_id ? `${task.provider_key} / ${task.model_id}` : "未分配"}
                    </p>
                  </div>
                  <label>
                    <span>服务商</span>
                    <select
                      value={task.provider_key}
                      style={{ width: "100%", marginTop: 4, border: "1px solid #cbd5e1", borderRadius: 8, padding: "8px 10px", background: "#fff" }}
                      onChange={(e) => {
                        updateTask(task.task_key, { provider_key: e.target.value, model_id: "" });
                      }}
                    >
                      <option value="">-- 选择服务商 --</option>
                      {availableKeys.map((k) => (
                        <option key={k} value={k}>
                          {PROVIDER_REGISTRY[k]?.label ?? k}
                        </option>
                      ))}
                    </select>
                  </label>
                  {task.provider_key && (
                    <label style={{ marginTop: 10 }}>
                      <span>模型</span>
                      <select
                        value={task.model_id}
                        style={{ width: "100%", marginTop: 4, border: "1px solid #cbd5e1", borderRadius: 8, padding: "8px 10px", background: "#fff" }}
                        onChange={(e) => updateTask(task.task_key, { model_id: e.target.value })}
                      >
                        <option value="">-- 选择模型 --</option>
                        {providerModels.map((m) => {
                          const reg = PROVIDER_REGISTRY[task.provider_key];
                          const isFree = reg?.free_models?.includes(m);
                          return (
                            <option key={m} value={m}>
                              {isFree ? `${m} (免费)` : m}
                            </option>
                          );
                        })}
                      </select>
                    </label>
                  )}
                  <div className="form-grid" style={{ marginTop: 10 }}>
                    <label>
                      <span>Temperature</span>
                      <input
                        type="number"
                        min={0}
                        max={2}
                        step={0.1}
                        value={task.temperature}
                        style={{ width: "100%", marginTop: 4, border: "1px solid #cbd5e1", borderRadius: 8, padding: "8px 10px", background: "#fff" }}
                        onChange={(e) => updateTask(task.task_key, { temperature: parseFloat(e.target.value) || 0.7 })}
                      />
                    </label>
                    <label>
                      <span>Max Tokens</span>
                      <input
                        type="number"
                        min={64}
                        max={32768}
                        step={256}
                        value={task.max_tokens}
                        style={{ width: "100%", marginTop: 4, border: "1px solid #cbd5e1", borderRadius: 8, padding: "8px 10px", background: "#fff" }}
                        onChange={(e) => updateTask(task.task_key, { max_tokens: parseInt(e.target.value, 10) || 4096 })}
                      />
                    </label>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
