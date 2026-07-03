import { useEffect, useRef, useState } from "react";
import { MoreVertical, RefreshCcw, RadioTower, Wrench } from "lucide-react";
import type { RuntimeIntent } from "../types";

interface MoreDropdownProps {
  onRefresh: () => void;
  onRunIntent: (intent: RuntimeIntent) => void;
  refreshing?: boolean;
  busyIntent?: RuntimeIntent | null;
  disabled?: boolean;
}

const DEVELOPER_TOOLS: Array<{ intent: RuntimeIntent; label: string }> = [
  { intent: "collect_validation", label: "仅采集素材" },
  { intent: "event_rebuild", label: "重建事件" },
  { intent: "alert_rebuild", label: "重算预警" },
];

export function MoreDropdown({
  onRefresh,
  onRunIntent,
  refreshing = false,
  busyIntent = null,
  disabled = false,
}: MoreDropdownProps) {
  const [open, setOpen] = useState(false);
  const [devToolsOpen, setDevToolsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
        setDevToolsOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  return (
    <div className="more-dropdown" ref={ref}>
      <button
        type="button"
        className="ghost-button compact"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        title="更多操作"
      >
        <MoreVertical size={14} />
      </button>

      {open ? (
        <div className="more-dropdown-menu">
          <button
            type="button"
            className="more-dropdown-item"
            disabled={refreshing}
            onClick={() => {
              onRefresh();
              setOpen(false);
            }}
          >
            <RefreshCcw size={13} />
            {refreshing ? "刷新中..." : "刷新数据"}
          </button>

          <div className="more-dropdown-separator" />

          <div
            className="more-dropdown-submenu-trigger"
            onMouseEnter={() => setDevToolsOpen(true)}
            onMouseLeave={() => setDevToolsOpen(false)}
          >
            <button
              type="button"
              className="more-dropdown-item"
              onClick={() => setDevToolsOpen((v) => !v)}
            >
              <Wrench size={13} />
              开发者工具
              <span className="more-dropdown-arrow">◂</span>
            </button>

            {devToolsOpen ? (
              <div className="more-dropdown-submenu">
                {DEVELOPER_TOOLS.map((item) => (
                  <button
                    key={item.intent}
                    type="button"
                    className="more-dropdown-item"
                    disabled={disabled || busyIntent === item.intent}
                    onClick={() => {
                      onRunIntent(item.intent);
                      setOpen(false);
                      setDevToolsOpen(false);
                    }}
                  >
                    <RadioTower size={13} />
                    {busyIntent === item.intent ? "执行中..." : item.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
