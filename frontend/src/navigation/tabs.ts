import {
  AlertCircle,
  CheckCircle,
  FileStack,
  LayoutDashboard,
  RadioTower,
  SearchCheck,
  Settings,
  Siren,
  Sparkles,
} from "lucide-react";

export type TabKey =
  | "overview"
  | "stream"
  | "events"
  | "alerts"
  | "source-health"
  | "watchlist"
  | "briefs"
  | "publish-history"
  | "draft-box"
  | "settings"
  | "logs";

export const intelTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "overview", label: "总览", icon: LayoutDashboard },
  { key: "stream", label: "实时流", icon: RadioTower },
  { key: "events", label: "热点簇", icon: SearchCheck },
  { key: "alerts", label: "预警台", icon: Siren },
  { key: "source-health", label: "来源健康", icon: AlertCircle },
];

export const draftTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "watchlist", label: "深挖池", icon: Sparkles },
  { key: "briefs", label: "简报", icon: FileStack },
  { key: "publish-history", label: "发表记录", icon: CheckCircle },
  { key: "draft-box", label: "微信草稿箱", icon: RadioTower },
];

export const systemTabs: Array<{ key: TabKey; label: string; icon: typeof LayoutDashboard }> = [
  { key: "settings", label: "设置", icon: Settings },
  { key: "logs", label: "日志", icon: AlertCircle },
];

export const pageMeta: Record<TabKey, { eyebrow: string; title: string }> = {
  overview: { eyebrow: "总览", title: "情报总览" },
  stream: { eyebrow: "信息获取", title: "原始素材流" },
  events: { eyebrow: "事件聚合", title: "热点事件列表" },
  alerts: { eyebrow: "趋势判断", title: "热点预警列表" },
  "source-health": { eyebrow: "来源巡检", title: "来源运行状态" },
  watchlist: { eyebrow: "深挖池", title: "待深挖的观察事件" },
  briefs: { eyebrow: "简报", title: "简报工作台" },
  "publish-history": { eyebrow: "发表记录", title: "微信公众号发表记录" },
  "draft-box": { eyebrow: "微信草稿箱", title: "远端草稿与本地简报对照" },
  settings: { eyebrow: "系统配置", title: "AI 模型、信息源与系统偏好" },
  logs: { eyebrow: "运行记录", title: "系统日志与异常" },
};
