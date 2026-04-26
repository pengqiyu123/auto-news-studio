import { Activity, AlertTriangle, Clock3, RadioTower, ScanSearch, Send, TimerReset } from "lucide-react";

import { formatDateTime, formatDuration, formatRelativeTime } from "../lib/time";
import type { DashboardResponse } from "../types";
import { ChainStatusBadge, JobBadge } from "./StatusBadge";

interface OverviewPanelProps {
  dashboard: DashboardResponse;
  onNavigate: (tab: "intel" | "candidates" | "drafts" | "jobs" | "settings" | "logs") => void;
}

function renderDualTime(label: string, value?: string | null) {
  return (
    <div className="time-pair">
      <span>{label}</span>
      <strong>{formatDateTime(value)}</strong>
      <p>{formatRelativeTime(value)}</p>
    </div>
  );
}

function freshnessLabel(value?: number | null) {
  if (value == null) {
    return "未知";
  }
  if (value <= 15) {
    return "新鲜";
  }
  if (value <= 60) {
    return "近期";
  }
  if (value <= 360) {
    return "变旧";
  }
  return "陈旧";
}

function runtimeTone(dashboard: DashboardResponse) {
  return dashboard.runtime_status.running ? "success" : "warning";
}

function nextActionSummary(dashboard: DashboardResponse) {
  if (!dashboard.runtime_status.running) {
    return {
      title: "自动运行当前已关闭",
      body: "先在上方全局主控设置计划并启动，再观察采集和候选是否开始更新。",
      target: "overview" as const
    };
  }
  if (dashboard.execution_chain.source_alerts.some((item) => !item.includes("暂无来源异常"))) {
    return {
      title: "来源层有告警，建议先看情报页",
      body: "优先处理来源健康和单来源重抓，先把信息入口跑顺。",
      target: "intel" as const
    };
  }
  if (dashboard.top_bar.waiting_review > 0) {
    return {
      title: "已有稿件等待审核",
      body: "候选和成稿已经有结果了，下一步更适合去稿件页推进正式稿。",
      target: "drafts" as const
    };
  }
  if (dashboard.stats.candidate_count > 0 && dashboard.stats.total_drafts === 0) {
    return {
      title: "候选已就绪，稿件还偏少",
      body: "可以先去候选页做人工筛一轮，再决定是否批量成稿。",
      target: "candidates" as const
    };
  }
  return {
    title: "系统正在稳定工作",
    body: "现在更适合去情报页看刚流入的信息，或者去任务页做手动补跑。",
    target: "intel" as const
  };
}

export function OverviewPanel({ dashboard, onNavigate }: OverviewPanelProps) {
  const nextAction = nextActionSummary(dashboard);
  const keyStats = [
    {
      label: "自动运行",
      value: dashboard.runtime_status.control_state === "stopped" ? "已关闭" : "已启用",
      helper: dashboard.runtime_status.current_cycle || "idle",
      icon: Activity,
    },
    {
      label: "来源健康",
      value: `${dashboard.top_bar.healthy_sources}/${dashboard.top_bar.total_sources}`,
      helper: "正常来源 / 总来源",
      icon: RadioTower,
    },
    {
      label: "待审核",
      value: dashboard.top_bar.waiting_review,
      helper: "稿件待人工推进",
      icon: ScanSearch,
    },
    {
      label: "1 小时新情报",
      value: dashboard.freshness.items_1h,
      helper: "最近 60 分钟进入系统",
      icon: TimerReset,
    },
  ];

  return (
    <div className="cockpit-layout">
      <section className="panel cockpit-focus-panel">
        <div className="panel-header compact">
          <div>
            <p className="eyebrow">关键提醒</p>
            <h2>先看这里，再决定下一步去哪里</h2>
          </div>
          <div className="panel-icon">
            <AlertTriangle size={18} />
          </div>
        </div>

        <div className="cockpit-focus-grid">
          <article className="next-action-card prominent">
            <div className="row-with-badge">
              <strong>{nextAction.title}</strong>
              <span className={`status-badge status-${runtimeTone(dashboard)}`}>{dashboard.runtime_status.control_state}</span>
            </div>
            <p>{nextAction.body}</p>
            <div className="next-action-buttons single-row">
              {nextAction.target === "overview" ? null : (
                <button type="button" className="primary-button" onClick={() => onNavigate(nextAction.target)}>
                  现在去处理
                </button>
              )}
              <button type="button" className="ghost-button" onClick={() => onNavigate("intel")}>
                去看情报
              </button>
              <button type="button" className="ghost-button" onClick={() => onNavigate("drafts")}>
                去看稿件
              </button>
              <button type="button" className="ghost-button" onClick={() => onNavigate("settings")}>
                去看设置
              </button>
            </div>
          </article>

          <div className="blocker-list compact">
            {dashboard.execution_chain.blockers.length ? (
              dashboard.execution_chain.blockers.slice(0, 3).map((blocker) => (
                <p key={blocker} className="blocker-item">
                  {blocker}
                </p>
              ))
            ) : (
              <p className="empty-state">当前没有明显阻断。</p>
            )}
            {dashboard.execution_chain.source_alerts.slice(0, 2).map((item) => (
              <p key={item} className="source-alert-item">
                {item}
              </p>
            ))}
          </div>
        </div>
      </section>

      <section className="panel cockpit-hero">
        <div className="panel-header">
          <div>
            <p className="eyebrow">驾驶舱</p>
            <h2>现在系统怎么样</h2>
          </div>
          <div className="panel-icon">
            <Activity size={18} />
          </div>
        </div>
        <div className="topbar-grid compact">
          <article className="hero-mode-card">
            <span>当前运行模式</span>
            <strong>{dashboard.current_automation_mode.label}</strong>
            <p>{dashboard.current_automation_mode.description}</p>
          </article>
          {keyStats.map((card) => {
            const Icon = card.icon;
            return (
              <article key={card.label} className="hero-stat-card">
                <div className="stat-top">
                  <span>{card.label}</span>
                  <Icon size={16} />
                </div>
                <strong>{card.value}</strong>
                <p>{card.helper}</p>
              </article>
            );
          })}
        </div>
        <div className="hero-times">
          {renderDualTime("最近采集", dashboard.top_bar.latest_collected_at)}
          {renderDualTime("最近发布时间", dashboard.top_bar.latest_published_at)}
          {renderDualTime("最后成功同步", dashboard.freshness.last_successful_sync_at)}
          <div className="time-pair">
            <span>已运行时长</span>
            <strong>{formatDuration(dashboard.runtime_status.uptime_seconds, "0秒")}</strong>
            <p>{dashboard.runtime_status.last_error ?? "当前没有自动运行异常"}</p>
          </div>
        </div>
      </section>

      <div className="cockpit-summary-grid cockpit-summary-grid-tight">
        <section className="panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">新鲜度</p>
              <h2>信息进入速度</h2>
            </div>
            <div className="panel-icon">
              <Clock3 size={18} />
            </div>
          </div>
          <div className="freshness-grid compact">
            <article className="freshness-card">
              <span>最近 1 小时</span>
              <strong>{dashboard.freshness.items_1h}</strong>
              <p>刚进入系统的情报</p>
            </article>
            <article className="freshness-card">
              <span>最近 6 小时</span>
              <strong>{dashboard.freshness.items_6h}</strong>
              <p>半天内持续更新</p>
            </article>
            <article className="freshness-card">
              <span>平均采集延迟</span>
              <strong>
                {dashboard.freshness.avg_collection_lag_minutes != null
                  ? `${dashboard.freshness.avg_collection_lag_minutes} 分钟`
                  : "未知"}
              </strong>
              <p>{freshnessLabel(dashboard.freshness.avg_collection_lag_minutes)}</p>
            </article>
            <article className={`freshness-card ${dashboard.freshness.has_staleness_alert ? "freshness-alert" : ""}`}>
              <span>老化来源</span>
              <strong>{dashboard.freshness.stale_source_count}</strong>
              <p>{dashboard.freshness.has_staleness_alert ? "存在超过 6 小时未更新来源" : "当前没有明显老化"}</p>
            </article>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header compact">
            <div>
              <p className="eyebrow">链路摘要</p>
              <h2>从采集到发布的当前状态</h2>
            </div>
            <div className="panel-icon">
              <Send size={18} />
            </div>
          </div>
          <div className="chain-grid">
            {dashboard.execution_chain.stages.map((stage) => (
              <article key={stage.key} className="chain-card">
                <div className="row-with-badge">
                  <strong>{stage.label}</strong>
                  <ChainStatusBadge status={stage.status} />
                </div>
                <p>{stage.detail}</p>
              </article>
            ))}
          </div>
          <div className="execution-meta">
            <div>
              <span>浏览器会话</span>
              <strong>{dashboard.execution_chain.browser_logged_in ? "已登录" : "未登录"}</strong>
            </div>
            <div>
              <span>选择器版本</span>
              <strong>{dashboard.execution_chain.selectors_version}</strong>
            </div>
            <div>
              <span>最近任务</span>
              <strong>{dashboard.stats.last_job_label ?? "暂无"}</strong>
            </div>
          </div>
          <div className="inline-status-actions">
            <button type="button" className="ghost-button compact" onClick={() => onNavigate("jobs")}>
              去看任务
            </button>
            <button type="button" className="ghost-button compact" onClick={() => onNavigate("settings")}>
              去看发布设置
            </button>
            {dashboard.stats.last_job_status ? <JobBadge status={dashboard.stats.last_job_status} /> : null}
          </div>
        </section>
      </div>
    </div>
  );
}
