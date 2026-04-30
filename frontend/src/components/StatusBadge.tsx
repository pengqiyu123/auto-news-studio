import type {
  AuditStatus,
  ChainStatus,
  LogLevel,
  PublishTaskStatus,
  RefreshStatus,
  SourceHealth
} from "../types";

type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";

function badgeClass(tone: BadgeTone) {
  return `status-badge status-${tone}`;
}

export function AuditBadge({ status }: { status: AuditStatus }) {
  const map: Record<AuditStatus, { label: string; tone: BadgeTone }> = {
    pending: { label: "待审核", tone: "warning" },
    approved: { label: "已通过", tone: "success" },
    rejected: { label: "已驳回", tone: "danger" },
    not_required: { label: "免审核", tone: "neutral" }
  };
  return <span className={badgeClass(map[status].tone)}>{map[status].label}</span>;
}

export function LogBadge({ level }: { level: LogLevel }) {
  const map: Record<LogLevel, { label: string; tone: BadgeTone }> = {
    info: { label: "信息", tone: "info" },
    warning: { label: "警告", tone: "warning" },
    error: { label: "错误", tone: "danger" },
    success: { label: "成功", tone: "success" }
  };
  return <span className={badgeClass(map[level].tone)}>{map[level].label}</span>;
}

export function SourceHealthBadge({ health }: { health: SourceHealth }) {
  const map: Record<SourceHealth, { label: string; tone: BadgeTone }> = {
    idle: { label: "未运行", tone: "neutral" },
    healthy: { label: "正常", tone: "success" },
    warning: { label: "告警", tone: "warning" },
    error: { label: "异常", tone: "danger" }
  };
  return <span className={badgeClass(map[health].tone)}>{map[health].label}</span>;
}

export function PublishTaskBadge({ status }: { status: PublishTaskStatus }) {
  const map: Record<PublishTaskStatus, { label: string; tone: BadgeTone }> = {
    pending: { label: "待执行", tone: "neutral" },
    running: { label: "执行中", tone: "info" },
    completed: { label: "完成", tone: "success" },
    failed: { label: "失败", tone: "danger" },
    blocked: { label: "已阻止", tone: "warning" }
  };
  return <span className={badgeClass(map[status].tone)}>{map[status].label}</span>;
}

export function RefreshBadge({ status }: { status: RefreshStatus }) {
  const map: Record<RefreshStatus, { label: string; tone: BadgeTone }> = {
    ready: { label: "就绪", tone: "success" },
    updated: { label: "已更新", tone: "success" },
    pending_retry: { label: "待重试", tone: "warning" },
    missing: { label: "缺失", tone: "danger" }
  };
  return <span className={badgeClass(map[status].tone)}>{map[status].label}</span>;
}

export function ChainStatusBadge({ status }: { status: ChainStatus }) {
  const map: Record<ChainStatus, { label: string; tone: BadgeTone }> = {
    idle: { label: "空闲", tone: "neutral" },
    running: { label: "运行中", tone: "info" },
    healthy: { label: "正常", tone: "success" },
    warning: { label: "注意", tone: "warning" },
    blocked: { label: "阻断", tone: "danger" }
  };
  return <span className={badgeClass(map[status].tone)}>{map[status].label}</span>;
}
