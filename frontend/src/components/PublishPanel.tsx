import { CheckCircle2, Settings2, ScanLine } from "lucide-react";
import { useEffect, useState } from "react";

import { formatDateTime, formatRelativeTime } from "../lib/time";
import type { BrowserSessionState, PublishBackendStatus, PublishTask, WeChatChannelConfig } from "../types";
import { PublishTaskBadge, SourceHealthBadge } from "./StatusBadge";

const PUBLISH_ACTION_LABELS: Record<string, string> = {
  sync_wechat_draft: "上传到微信草稿箱",
  delete_wechat_draft: "删除微信远端草稿",
  delete_brief: "删除本地简报",
};

interface PublishPanelProps {
  config: WeChatChannelConfig | null;
  browserSession: BrowserSessionState | null;
  publishBackends: PublishBackendStatus[];
  publishTasks: PublishTask[];
  isSaving: boolean;
  isRefreshingBrowser: boolean;
  isOpeningBrowser: boolean;
  onSave: (payload: WeChatChannelConfig) => Promise<void>;
  onRefreshBrowser: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
  onOpenBrowserDashboard: (payload: Pick<BrowserSessionState, "browser_name" | "user_data_dir">) => Promise<void>;
}

export function PublishPanel({
  config,
  browserSession,
  publishBackends,
  publishTasks,
  isSaving,
  isRefreshingBrowser,
  isOpeningBrowser,
  onSave,
  onRefreshBrowser,
  onOpenBrowserDashboard,
}: PublishPanelProps) {
  const [form, setForm] = useState<WeChatChannelConfig | null>(config);

  useEffect(() => {
    setForm(config);
  }, [config]);

  if (!form) {
    return (
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">发布</p>
            <h2>正在加载交付配置...</h2>
          </div>
        </div>
        <p className="empty-state">正在读取微信交付配置...</p>
      </section>
    );
  }

  const updateField = <K extends keyof WeChatChannelConfig>(key: K, value: WeChatChannelConfig[K]) => {
    setForm((previous) => (previous ? { ...previous, [key]: value } : previous));
  };

  const isLoggedIn = Boolean(browserSession?.logged_in);
  const sessionHealth: "healthy" | "warning" = isLoggedIn ? "healthy" : "warning";
  const profilePath = form.browser_profile_path?.trim() || browserSession?.user_data_dir || "点击自动匹配后生成";
  const statusTitle = isLoggedIn ? "浏览器会话已就绪" : "等待完成浏览器登录";
  const statusDescription = isLoggedIn
    ? "当前公众号后台登录态可用，可以继续把简报推进到微信草稿箱。"
    : "先完成浏览器配置，打开公众号后台扫码登录，关闭浏览器后再回来验证。";
  const browserIndicatorTone = !browserSession?.logged_in || !browserSession?.manager_alive
    ? "danger"
    : browserSession?.busy
      ? "warning"
      : "success";
  const browserIndicatorLabel = !browserSession?.logged_in || !browserSession?.manager_alive
    ? "未就绪"
    : browserSession?.busy
      ? "执行中"
      : "空闲";

  return (
    <section className="page-content">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">发布</p>
            <h2>把简报交付到微信草稿箱</h2>
            <p className="subtle">这里统一处理浏览器会话、发布配置和草稿箱写入记录。</p>
          </div>
        </div>

        <div className="channel-wizard-card">
          <div className="channel-wizard-head">
            <div>
              <div className="row-with-badge">
                <strong>{statusTitle}</strong>
                <SourceHealthBadge health={sessionHealth} />
                <span className={`browser-status-indicator browser-status-${browserIndicatorTone}`}>
                  <span className="browser-status-dot" />
                  {browserIndicatorLabel}
                </span>
              </div>
              <p>{statusDescription}</p>
            </div>
            <div className="channel-quick-meta">
              <span>当前浏览器</span>
              <strong>{form.browser_name === "chrome" ? "Chrome" : "Edge"}</strong>
              <p style={{ marginTop: 8 }}>
                窗口：{browserSession?.window_state ?? "unknown"}<br />
                驻留页：{browserSession?.resident_page ?? "unknown"}
              </p>
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
                  <button type="button" className={form.browser_name === "edge" ? "segment-active" : ""} onClick={() => updateField("browser_name", "edge")}>
                    Edge
                  </button>
                  <button type="button" className={form.browser_name === "chrome" ? "segment-active" : ""} onClick={() => updateField("browser_name", "chrome")}>
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
                <p>这一步只负责写入并固定浏览器 profile。成功后会更新下方 profile 目录，再继续打开公众号后台。</p>
                <div className="channel-step-actions">
                  <button type="button" className="primary-button" onClick={() => void onSave({ ...form, browser_profile_path: "" })}>
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
                    onClick={() => void onOpenBrowserDashboard({ browser_name: form.browser_name, user_data_dir: form.browser_profile_path.trim() })}
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
                    onClick={() => void onRefreshBrowser({ browser_name: form.browser_name, user_data_dir: form.browser_profile_path.trim() })}
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
                    <SourceHealthBadge health={backend.health === "healthy" ? "healthy" : backend.health === "warning" ? "warning" : "error"} />
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
          <div className="form-grid">
            <label>
              <span>作者名</span>
              <input value={form.author} onChange={(event) => updateField("author", event.target.value)} />
            </label>
            <label>
              <span>自动发送时间窗</span>
              <input value={form.auto_send_window} onChange={(event) => updateField("auto_send_window", event.target.value)} />
            </label>
            <label>
              <span>选择器版本</span>
              <input value={form.selectors_version} onChange={(event) => updateField("selectors_version", event.target.value)} />
            </label>
            <label className="full-span">
              <span>浏览器用户目录</span>
              <input value={form.browser_profile_path} onChange={(event) => updateField("browser_profile_path", event.target.value)} />
            </label>
            <label className="full-span">
              <span>发布入口 URL</span>
              <input value={form.publish_entry_url} onChange={(event) => updateField("publish_entry_url", event.target.value)} />
            </label>
            <label className="toggle-field">
              <span>启用草稿模式</span>
              <input type="checkbox" checked={form.draft_mode} onChange={(event) => updateField("draft_mode", event.target.checked)} />
            </label>
            <label className="toggle-field">
              <span>启用预览</span>
              <input type="checkbox" checked={form.preview_enabled} onChange={(event) => updateField("preview_enabled", event.target.checked)} />
            </label>
            <label className="full-span">
              <span>风险关键词</span>
              <textarea
                rows={4}
                value={form.risk_keywords.join("\n")}
                onChange={(event) => updateField("risk_keywords", event.target.value.split("\n").map((item) => item.trim()).filter(Boolean))}
              />
            </label>
          </div>
          <div className="source-action-row" style={{ marginTop: 16 }}>
            <button type="button" className="primary-button" onClick={() => void onSave(form)}>
              <Settings2 size={16} />
              {isSaving ? "保存中..." : "保存发布配置"}
            </button>
          </div>
        </details>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">发布记录</p>
            <h2>上传与删除记录</h2>
          </div>
        </div>
        <div className="task-list">
          {publishTasks.length ? publishTasks.map((task) => (
            <article key={task.id} className="mini-row stacked">
              <div className="row-with-badge">
                <strong>{PUBLISH_ACTION_LABELS[task.action] ?? task.action}</strong>
                <PublishTaskBadge status={task.status} />
              </div>
              <p>{task.message}</p>
              {task.step_logs.length ? <details><summary>查看调试步骤</summary><p>{task.step_logs.slice(0, 6).join(" | ")}</p></details> : null}
              {task.artifacts.length ? <details><summary>查看产物</summary><p>{task.artifacts[0]}</p></details> : null}
              <span className="tiny-meta">{formatDateTime(task.created_at, { fallback: "暂无" })}</span>
            </article>
          )) : <p className="empty-state">暂时还没有发布记录。</p>}
        </div>
      </section>
    </section>
  );
}
