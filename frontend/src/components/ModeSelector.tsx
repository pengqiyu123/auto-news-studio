import { Check, Lock, Radar, Sparkles } from "lucide-react";

import type { AutomationMode, AutomationModeDefinition } from "../types";

interface ModeSelectorProps {
  currentMode: AutomationMode;
  items: AutomationModeDefinition[];
  pendingMode?: AutomationMode | null;
  onChange: (mode: AutomationMode) => Promise<void>;
}

const capabilityLabels: Array<[keyof AutomationModeDefinition, string]> = [
  ["auto_collect", "自动采集"],
  ["auto_generate_candidates", "自动候选"],
  ["auto_generate_drafts", "自动初稿"],
  ["auto_publish_enabled", "自动发布"]
];

export function ModeSelector({
  currentMode,
  items,
  pendingMode,
  onChange
}: ModeSelectorProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">运行模式</p>
          <h2>控制信息雷达与自动初稿强度</h2>
          <p className="subtle">
            首页主控开关已经改成全局运行模式。当前先开放前两档，第三档保留为后续开放。
          </p>
        </div>
        <div className="panel-icon">
          <Radar size={18} />
        </div>
      </div>
      <div className="mode-grid">
        {items.map((item) => {
          const selected = item.key === currentMode;
          const loading = item.key === pendingMode;
          const disabled = !item.available;
          return (
            <article
              key={item.key}
              className={`mode-card ${selected ? "mode-card-active" : ""} ${disabled ? "mode-card-disabled" : ""}`}
            >
              <div className="mode-card-head">
                <div>
                  <div className="row-with-badge">
                    <h3>{item.label}</h3>
                    {selected ? (
                      <span className="selected-chip">
                        <Check size={14} />
                        当前
                      </span>
                    ) : null}
                  </div>
                  <p>{item.description}</p>
                </div>
              </div>
              <div className="capability-list">
                {capabilityLabels.map(([key, label]) => (
                  <span
                    key={key}
                    className={`capability-pill ${item[key] ? "capability-on" : "capability-off"}`}
                  >
                    {label}
                  </span>
                ))}
              </div>
              <div className="mode-footnote">
                {item.key === "radar_only" ? <Radar size={14} /> : <Sparkles size={14} />}
                <span>{disabled ? "预留模式，暂不开放自动发布。" : "会驱动后台自动调度器的实际行为。"}</span>
              </div>
              <button
                type="button"
                className="primary-button"
                disabled={selected || loading || disabled}
                onClick={() => void onChange(item.key)}
              >
                {loading ? "切换中..." : selected ? "当前模式" : disabled ? "后续开放" : "切换到该模式"}
              </button>
              {disabled ? (
                <div className="mode-locked-note">
                  <Lock size={14} />
                  <span>UI 可见，但不会进入实际自动发布。</span>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
