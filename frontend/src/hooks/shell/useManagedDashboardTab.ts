import { useEffect, useRef, useState } from "react";

const DASHBOARD_CHANNEL_NAME = "auto-news-studio-dashboard";
const DASHBOARD_TAB_ID_KEY = "auto-news-studio.dashboard-tab-id";
const MANAGED_TAB_KEY = "auto-news-studio.managed-dashboard-tab";
const LAUNCHER_QUERY_KEY = "launcher";
const LAUNCHER_TIMESTAMP_KEY = "ts";
const HANDOFF_TIMEOUT_MS = 450;
const HEALTHCHECK_INTERVAL_MS = 4000;
const HEALTHCHECK_FAILURE_LIMIT = 3;

type DashboardTabMessage =
  | {
      type: "launcher-probe";
      sourceId: string;
      sentAt: number;
    }
  | {
      type: "launcher-ack";
      sourceId: string;
      targetId: string;
      sentAt: number;
    }
  | {
      type: "focus-reload";
      sourceId: string;
      targetId: string;
      sentAt: number;
    };

function safeGetSessionValue(key: string): string {
  try {
    return window.sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function safeSetSessionValue(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Ignore session storage failures and keep the tab usable.
  }
}

function hasLauncherQuery(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.get(LAUNCHER_QUERY_KEY) === "1";
}

function stripLauncherQuery(): void {
  const current = new URL(window.location.href);
  current.searchParams.delete(LAUNCHER_QUERY_KEY);
  current.searchParams.delete(LAUNCHER_TIMESTAMP_KEY);
  const nextSearch = current.searchParams.toString();
  const nextUrl = `${current.pathname}${nextSearch ? `?${nextSearch}` : ""}${current.hash}`;
  window.history.replaceState({}, document.title, nextUrl);
}

function getOrCreateDashboardTabId(): string {
  const existing = safeGetSessionValue(DASHBOARD_TAB_ID_KEY).trim();
  if (existing) {
    return existing;
  }
  const next = `tab-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  safeSetSessionValue(DASHBOARD_TAB_ID_KEY, next);
  return next;
}

function retireManagedDashboardTab(): void {
  if (window.location.port === "4173") {
    return;
  }
  window.setTimeout(() => {
    try {
      window.close();
    } catch {
      // Ignore close errors and fall back to a blank page.
    }

    window.setTimeout(() => {
      if (window.closed) {
        return;
      }
      try {
        window.location.replace("about:blank");
      } catch {
        // Ignore navigation failures as a last resort.
      }
    }, 160);
  }, 120);
}

function markManagedDashboardTab(): void {
  safeSetSessionValue(MANAGED_TAB_KEY, "1");
}

function buildHealthcheckUrl(): string {
  return new URL("/api/health", window.location.origin).toString();
}

export function useManagedDashboardTab(): void {
  return;
  const tabIdRef = useRef<string>("");
  const channelRef = useRef<BroadcastChannel | null>(null);
  const launcherAckIdsRef = useRef<string[]>([]);
  const [managedTab, setManagedTab] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return safeGetSessionValue(MANAGED_TAB_KEY) === "1";
  });

  if (typeof window !== "undefined" && !tabIdRef.current) {
    tabIdRef.current = getOrCreateDashboardTabId();
  }

  useEffect(() => {
    if (typeof window === "undefined" || typeof BroadcastChannel !== "function") {
      return;
    }

    const tabId = tabIdRef.current;
    const channel = new BroadcastChannel(DASHBOARD_CHANNEL_NAME);
    channelRef.current = channel;

    const onMessage = (event: MessageEvent<DashboardTabMessage>) => {
      const message = event.data;
      if (!message || message.sourceId === tabId) {
        return;
      }

      if (message.type === "launcher-probe") {
        channel.postMessage({
          type: "launcher-ack",
          sourceId: tabId,
          targetId: message.sourceId,
          sentAt: Date.now(),
        } satisfies DashboardTabMessage);
        return;
      }

      if (message.type === "launcher-ack" && message.targetId === tabId) {
        launcherAckIdsRef.current = [...launcherAckIdsRef.current, message.sourceId];
        return;
      }

      if (message.type === "focus-reload" && message.targetId === tabId) {
        try {
          window.focus();
        } catch {
          // Best-effort only.
        }
        window.setTimeout(() => {
          window.location.reload();
        }, 120);
      }
    };

    channel.addEventListener("message", onMessage);

    return () => {
      channel.removeEventListener("message", onMessage);
      channel.close();
      if (channelRef.current === channel) {
        channelRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (!hasLauncherQuery()) {
      return;
    }

    launcherAckIdsRef.current = [];
    const channel = channelRef.current;
    if (!channel) {
      markManagedDashboardTab();
      setManagedTab(true);
      stripLauncherQuery();
      return;
    }

    channel.postMessage({
      type: "launcher-probe",
      sourceId: tabIdRef.current,
      sentAt: Date.now(),
    } satisfies DashboardTabMessage);

    const timer = window.setTimeout(() => {
      const targetId = launcherAckIdsRef.current[0];
      if (targetId) {
        channel.postMessage({
          type: "focus-reload",
          sourceId: tabIdRef.current,
          targetId,
          sentAt: Date.now(),
        } satisfies DashboardTabMessage);
        retireManagedDashboardTab();
        return;
      }

      markManagedDashboardTab();
      setManagedTab(true);
      stripLauncherQuery();
    }, HANDOFF_TIMEOUT_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !managedTab) {
      return;
    }

    let cancelled = false;
    let consecutiveFailures = 0;

    const runHealthcheck = async () => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 1500);

      try {
        const response = await fetch(buildHealthcheckUrl(), {
          cache: "no-store",
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`healthcheck_failed:${response.status}`);
        }
        consecutiveFailures = 0;
      } catch {
        consecutiveFailures += 1;
        if (!cancelled && consecutiveFailures >= HEALTHCHECK_FAILURE_LIMIT) {
          retireManagedDashboardTab();
        }
      } finally {
        window.clearTimeout(timeout);
      }
    };

    const timer = window.setInterval(() => {
      void runHealthcheck();
    }, HEALTHCHECK_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [managedTab]);
}
