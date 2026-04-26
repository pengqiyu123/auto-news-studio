import { CheckCircle2, RefreshCcw, Save, ScanLine, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { BrowserSessionState, PublishBackendStatus, WeChatChannelConfig } from "../types";
import { SourceHealthBadge } from "./StatusBadge";

interface ChannelPanelProps {
  config: WeChatChannelConfig | null;
  browserSession: BrowserSessionState | null;
  publishBackends: PublishBackendStatus[];
  isSaving: boolean;
  isRefreshingBrowser: boolean;
  isOpeningBrowser: boolean;
  onSave: (payload: WeChatChannelConfig) => Promise<void>;
  onRefreshBrowser: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
  onOpenBrowserDashboard: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
}

export function ChannelPanel({
  config,
  browserSession,
  publishBackends,
  isSaving,
  isRefreshingBrowser,
  isOpeningBrowser,
  onSave,
  onRefreshBrowser,
  onOpenBrowserDashboard
}: ChannelPanelProps) {
  const [form, setForm] = useState<WeChatChannelConfig | null>(config);

  useEffect(() => {
    setForm(config);
  }, [config]);

  if (!form) {
    return (
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">浏览器发布配置</p>
            <h2>正在加载公众号浏览器配置...</h2>
          </div>
        </div>
        <p className="empty-state">正在读取浏览器发布配置...</p>
      </section>
    );
  }

  const updateField = <K extends keyof WeChatChannelConfig>(key: K, value: WeChatChannelConfig[K]) => {
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const isLoggedIn = Boolean(browserSession?.logged_in);
  const sessionHealth: "healthy" | "warning" = isLoggedIn ? "healthy" : "warning";
  const profilePath = form.browser_profile_path?.trim() || browserSession?.user_data_dir || "点击自动匹配后生成";
  const statusTitle = isLoggedIn ? "浏览器会话已就绪" : "等待完成浏览器登录";
  const statusDescription = isLoggedIn
    ? "当前公众号后台登录态可用，可以继续同步草稿、打开预览和推进发布。"
    : "先完成浏览器配置，打开公众号后台扫码登录，关闭浏览器后再回来验证。";

  const handleAutoConfigure = async () => {
    await onSave({
      ...form,
      browser_profile_path: ""
    });
  };

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">浏览器发布配置</p>
          <h2>把公众号浏览器会话配置成可复用能力</h2>
          <p className="subtle">
            这里走的是网页自动化链路：选择浏览器、自动匹配 profile、扫码登录、验证会话，之后整个项目都能复用这套配置。
          </p>
        </div>
      </div>

      <div className="channel-wizard-card">
        <div className="channel-wizard-head">
          <div>
            <div className="row-with-badge">
              <strong>{statusTitle}</strong>
              <SourceHealthBadge health={sessionHealth} />
            </div>
            <p>{statusDescription}</p>
          </div>
          <div className="channel-quick-meta">
            <span>当前浏览器</span>
            <strong>{form.browser_name === "chrome" ? "Chrome" : "Edge"}</strong>
          </div>
        </div>

        <div className="channel-wizard-steps">
          <article className="channel-step-card">
            <div className="channel-step-number">1</div>
            <div className="channel-step-body">
              <span>选择浏览器</span>
              <strong>确定要复用的本机浏览器</strong>
              <p>建议优先用平时登录公众号的浏览器，当前支持 Edge 和 Chrome。</p>
              <div className="channel-browser-switch">
                <button
                  type="button"
                  className={form.browser_name === "edge" ? "segment-active" : ""}
                  onClick={() => updateField("browser_name", "edge")}
                >
                  Edge
                </button>
                <button
                  type="button"
                  className={form.browser_name === "chrome" ? "segment-active" : ""}
                  onClick={() => updateField("browser_name", "chrome")}
                >
                  Chrome
                </button>
              </div>
            </div>
          </article>

          <article className="channel-step-card">
            <div className="channel-step-number">2</div>
            <div className="channel-step-body">
              <span>自动匹配</span>
              <strong>保存并生成浏览器 profile</strong>
              <p>系统会把会话目录固定到项目运行目录，后续自动复用，不需要你每次重新找路径。</p>
              <div className="channel-step-actions">
                <button type="button" className="primary-button" onClick={() => void handleAutoConfigure()}>
                  <Settings2 size={16} />
                  {isSaving ? "配置中..." : "配置浏览器"}
                </button>
              </div>
            </div>
          </article>

          <article className="channel-step-card">
            <div className="channel-step-number">3</div>
            <div className="channel-step-body">
              <span>扫码登录</span>
              <strong>打开公众号后台并完成登录</strong>
              <p>点击后会直接打开浏览器窗口。扫码成功后，把浏览器窗口关掉，再回这里做验证。</p>
              <div className="channel-step-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() =>
                    void onOpenBrowserDashboard({
                      browser_name: form.browser_name,
                      user_data_dir: form.browser_profile_path.trim()
                    })
                  }
                >
                  <ScanLine size={16} />
                  {isOpeningBrowser ? "打开中..." : "打开公众号后台"}
                </button>
              </div>
            </div>
          </article>

          <article className="channel-step-card">
            <div className="channel-step-number">4</div>
            <div className="channel-step-body">
              <span>会话验证</span>
              <strong>确认登录态已经可复用</strong>
              <p>浏览器关闭后点一次验证，系统会用 Playwright 检查登录态和页面选择器是否正常。</p>
              <div className="channel-step-actions">
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() =>
                    void onRefreshBrowser({
                      browser_name: form.browser_name,
                      user_data_dir: form.browser_profile_path.trim()
                    })
                  }
                >
                  <CheckCircle2 size={16} />
                  {isRefreshingBrowser ? "验证中..." : "验证浏览器会话"}
                </button>
              </div>
            </div>
          </article>
        </div>

        <div className="channel-session-summary">
          <article className="channel-session-stat">
            <span>profile 目录</span>
            <strong>{profilePath}</strong>
          </article>
          <article className="channel-session-stat">
            <span>最近检查</span>
            <strong>{formatDateTime(browserSession?.last_checked_at, { fallback: "暂无" })}</strong>
            <p>{formatRelativeTime(browserSession?.last_checked_at, "尚未检查")}</p>
          </article>
          <article className="channel-session-stat">
            <span>当前页面</span>
            <strong>{browserSession?.current_page ?? "暂无"}</strong>
          </article>
          <article className="channel-session-stat">
            <span>最近截图</span>
            <strong>{browserSession?.last_screenshot ?? "暂无"}</strong>
          </article>
        </div>
      </div>

      <div className="source-list">
        {publishBackends.map((backend) => (
          <article key={backend.key} className="source-card">
            <div className="source-card-head">
              <div>
                <div className="row-with-badge">
                  <strong>{backend.label}</strong>
                  <SourceHealthBadge
                    health={backend.health === "healthy" ? "healthy" : backend.health === "warning" ? "warning" : "error"}
                  />
                </div>
                <p>{backend.detail}</p>
              </div>
              <span className="tiny-meta">{backend.configured ? "已配置" : "未配置"}</span>
            </div>
          </article>
        ))}
      </div>

      <details className="advanced-jobs">
        <summary>高级设置</summary>
        <div className="browser-session-card">
          <div>
            <div className="row-with-badge">
              <strong>浏览器会话状态</strong>
              <SourceHealthBadge health={browserSession?.logged_in ? "healthy" : "warning"} />
            </div>
            <p>
              浏览器：{browserSession?.browser_name ?? "未知"} · 用户目录：
              {browserSession?.user_data_dir || "未配置"}
            </p>
            <p>最近检查：{formatDateTime(browserSession?.last_checked_at, { fallback: "暂无" })}</p>
            <p>当前页面：{browserSession?.current_page ?? "暂无"}</p>
            <p>最近截图：{browserSession?.last_screenshot ?? "暂无"}</p>
            {browserSession?.last_error ? <span className="error-note">{browserSession.last_error}</span> : null}
          </div>
          <div className="source-action-row">
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                void onOpenBrowserDashboard({
                  browser_name: form.browser_name,
                  user_data_dir: form.browser_profile_path
                })
              }
            >
              <RefreshCcw size={16} />
              {isOpeningBrowser ? "打开中..." : "打开公众号后台"}
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={() =>
                void onRefreshBrowser({
                  browser_name: form.browser_name,
                  user_data_dir: form.browser_profile_path
                })
              }
            >
              <RefreshCcw size={16} />
              {isRefreshingBrowser ? "检查中..." : "刷新登录态"}
            </button>
          </div>
        </div>

        <div className="form-grid">
          <label>
            <span>作者名</span>
            <input value={form.author} onChange={(e) => updateField("author", e.target.value)} />
          </label>
          <label>
            <span>自动发送时间窗</span>
            <input
              value={form.auto_send_window}
              onChange={(e) => updateField("auto_send_window", e.target.value)}
            />
          </label>
          <label>
            <span>浏览器类型</span>
            <select value={form.browser_name} onChange={(e) => updateField("browser_name", e.target.value)}>
              <option value="chrome">chrome</option>
              <option value="edge">edge</option>
            </select>
          </label>
          <label>
            <span>选择器版本</span>
            <input
              value={form.selectors_version}
              onChange={(e) => updateField("selectors_version", e.target.value)}
            />
          </label>
          <label className="full-span">
            <span>浏览器用户目录</span>
            <input
              value={form.browser_profile_path}
              onChange={(e) => updateField("browser_profile_path", e.target.value)}
            />
          </label>
          <label className="full-span">
            <span>发布入口 URL</span>
            <input
              value={form.publish_entry_url}
              onChange={(e) => updateField("publish_entry_url", e.target.value)}
            />
          </label>
          <label>
            <span>默认封面策略</span>
            <select
              value={form.default_cover_strategy}
              onChange={(e) => updateField("default_cover_strategy", e.target.value)}
            >
              <option value="auto">auto</option>
              <option value="template">template</option>
              <option value="manual">manual</option>
            </select>
          </label>
          <label>
            <span>默认摘要策略</span>
            <select
              value={form.default_digest_strategy}
              onChange={(e) => updateField("default_digest_strategy", e.target.value)}
            >
              <option value="balanced">balanced</option>
              <option value="conservative">conservative</option>
              <option value="enhanced">enhanced</option>
            </select>
          </label>
          <label className="toggle-field">
            <span>启用草稿模式</span>
            <input
              type="checkbox"
              checked={form.draft_mode}
              onChange={(e) => updateField("draft_mode", e.target.checked)}
            />
          </label>
          <label className="toggle-field">
            <span>启用预览</span>
            <input
              type="checkbox"
              checked={form.preview_enabled}
              onChange={(e) => updateField("preview_enabled", e.target.checked)}
            />
          </label>
          <label className="full-span">
            <span>风险关键词</span>
            <textarea
              rows={4}
              value={form.risk_keywords.join("\n")}
              onChange={(e) =>
                updateField(
                  "risk_keywords",
                  e.target.value
                    .split("\n")
                    .map((item) => item.trim())
                    .filter(Boolean)
                )
              }
            />
          </label>
        </div>

        <button type="button" className="primary-button save-button" onClick={() => void onSave(form)}>
          <Save size={16} />
          {isSaving ? "保存中..." : "保存浏览器发布配置"}
        </button>
      </details>
    </section>
  );
}
