from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..models import (
    ChainStateCard,
    DashboardTopBar,
    ExecutionChainSnapshot,
    FreshnessSnapshot,
    GithubSignalItem,
    HotClusterCard,
    IntelStreamItem,
)
from ..store.base import UTC, minutes_between, parse_time


class DashboardMixin:
    def _freshness_snapshot(self, state: dict[str, Any]) -> FreshnessSnapshot:
        now = datetime.now(UTC)
        raw_items = state["raw_items"]
        collected_times = [parse_time(item.get("collected_at")) for item in raw_items]
        collected_times = [item for item in collected_times if item]
        published_times = [parse_time(item.get("published_at")) for item in raw_items]
        published_times = [item for item in published_times if item]

        def count_within(hours: int) -> int:
            return sum(1 for item in collected_times if (now - item).total_seconds() <= hours * 3600)

        lags = [
            minutes_between(item.get("published_at"), item.get("collected_at"))
            for item in raw_items
        ]
        lag_values = [item for item in lags if item is not None]
        enabled_sources = [item for item in state["sources"] if item.get("enabled")]
        stale_source_count = 0
        for source in enabled_sources:
            synced_at = parse_time(source.get("last_synced_at"))
            if not synced_at or (now - synced_at).total_seconds() > 6 * 3600:
                stale_source_count += 1

        latest_collected = max(collected_times).replace(microsecond=0).isoformat() if collected_times else None
        latest_published = max(published_times).replace(microsecond=0).isoformat() if published_times else None
        latest_collected_dt = parse_time(latest_collected)
        has_staleness_alert = stale_source_count > 0
        if latest_collected_dt and (now - latest_collected_dt).total_seconds() > 6 * 3600:
            has_staleness_alert = True

        return FreshnessSnapshot(
            latest_published_at=latest_published,
            latest_collected_at=latest_collected,
            items_1h=count_within(1),
            items_6h=count_within(6),
            items_24h=count_within(24),
            avg_collection_lag_minutes=round(sum(lag_values) / len(lag_values), 1) if lag_values else None,
            stale_source_count=stale_source_count,
            has_staleness_alert=has_staleness_alert,
            last_successful_sync_at=self._runtime(state).get("last_successful_sync_at"),
        )

    def _dashboard_top_bar(self, state: dict[str, Any], freshness: FreshnessSnapshot) -> DashboardTopBar:
        blocked_publish_ids = {
            str(item.get("id") or "")
            for item in state.get("briefs", [])
            if str(item.get("stage") or "") == "failed" or str(item.get("last_error") or "").strip()
        }
        blocked_publish_ids.update(
            str(item.get("target_id") or "")
            for item in state.get("publish_tasks", [])
            if item.get("status") in {"blocked", "failed"}
        )
        return DashboardTopBar(
            current_mode_label=self._current_automation_mode_def(state)["label"],
            healthy_sources=len([item for item in state["sources"] if item["health_status"] == "healthy"]),
            total_sources=len(state["sources"]),
            latest_collected_at=freshness.latest_collected_at,
            latest_published_at=freshness.latest_published_at,
            pending_briefs=len([item for item in state.get("briefs", []) if str(item.get("stage") or "") == "prepared"]),
            blocked_publish_count=len([item for item in blocked_publish_ids if item]),
        )

    def _intel_stream(self, state: dict[str, Any]) -> list[IntelStreamItem]:
        raw_lookup = {item["id"]: item for item in state["raw_items"]}
        stream: list[IntelStreamItem] = []

        for normalized in state["normalized_items"]:
            collected_at = self._latest_collected_at(raw_lookup, normalized.get("raw_item_ids", []))
            stream.append(
                IntelStreamItem(
                    id=normalized["id"],
                    title=normalized["title"],
                    summary=normalized.get("summary", ""),
                    link=normalized["link"],
                    score=float(normalized.get("final_score", 0)),
                    source_names=list(normalized.get("source_names", [])),
                    source_count=len(normalized.get("source_names", [])),
                    published_at=normalized.get("published_at"),
                    collected_at=collected_at,
                    time_lag_minutes=minutes_between(normalized.get("published_at"), collected_at),
                )
            )

        stream.sort(key=lambda item: parse_time(item.collected_at) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return stream[:12]

    def _hot_clusters(self, state: dict[str, Any]) -> list[HotClusterCard]:
        raw_lookup = {item["id"]: item for item in state["raw_items"]}
        cards = [
            HotClusterCard(
                cluster_id=item["cluster_id"],
                title=item["title"],
                final_score=float(item.get("final_score", 0)),
                member_count=len(item.get("cluster_members", [])),
                source_names=list(item.get("source_names", [])),
                published_at=item.get("published_at"),
                latest_collected_at=self._latest_collected_at(raw_lookup, item.get("raw_item_ids", [])),
                signals=list(item.get("signals", [])),
            )
            for item in sorted(state["normalized_items"], key=lambda value: value.get("final_score", 0), reverse=True)[:8]
        ]
        return cards

    def _is_github_signal(self, raw_item: dict[str, Any], source: dict[str, Any] | None) -> bool:
        if raw_item.get("source_kind") == "github":
            return True
        if "github.com/" in (raw_item.get("link") or ""):
            return True
        tags = source.get("tags", []) if source else []
        return "github" in tags or raw_item.get("source_key") == "rsshub-github-ai"

    def _extract_repo_name(self, raw_item: dict[str, Any]) -> str:
        link = raw_item.get("link") or ""
        match = re.search(r"github\.com/([^/]+/[^/?#]+)", link)
        if match:
            return match.group(1)
        return raw_item.get("title", "GitHub Repo")

    def _github_watch(self, state: dict[str, Any]) -> list[GithubSignalItem]:
        sources_by_key = self._sources_by_key(state)
        github_items: list[GithubSignalItem] = []

        for raw_item in state["raw_items"]:
            source = sources_by_key.get(raw_item["source_key"])
            if not self._is_github_signal(raw_item, source):
                continue
            github_items.append(
                GithubSignalItem(
                    id=raw_item["id"],
                    repo_name=self._extract_repo_name(raw_item),
                    summary=raw_item.get("summary", ""),
                    link=raw_item.get("link", ""),
                    stars_signal=int(raw_item.get("engagement", {}).get("score", 0) or 0),
                    source_name=raw_item.get("source_name", ""),
                    published_at=raw_item.get("published_at"),
                    collected_at=raw_item.get("collected_at"),
                )
            )

        github_items.sort(key=lambda item: parse_time(item.collected_at) or datetime.min.replace(tzinfo=UTC), reverse=True)
        return github_items[:8]

    def _execution_chain(self, state: dict[str, Any], browser: dict[str, Any]) -> ExecutionChainSnapshot:
        # Lazy import to avoid circular dependency
        from ..store.core import JOB_LABELS

        source_errors = [item for item in state["sources"] if item.get("enabled") and item["health_status"] == "error"]
        source_warnings = [item for item in state["sources"] if item.get("enabled") and item["health_status"] == "warning"]
        running_jobs = [item for item in state["jobs"] if item["status"] == "running"]
        running_tasks = [item for item in state["publish_tasks"] if item["status"] == "running"]
        blocked_tasks = [item for item in state["publish_tasks"] if item["status"] in {"blocked", "failed"}]
        deep_dive_errors = [item for item in state.get("event_deep_dives", []) if str(item.get("status") or "") == "failed"]
        brief_errors = [item for item in state.get("briefs", []) if item.get("last_error") or str(item.get("stage") or "") == "failed"]
        pending_briefs = [item for item in state.get("briefs", []) if str(item.get("stage") or "") == "prepared"]
        runtime = self._runtime(state)

        if any(item["action"] == "collect_news" for item in running_jobs):
            collect_status = "running"
        elif source_errors:
            collect_status = "blocked"
        elif source_warnings:
            collect_status = "warning"
        elif state["raw_items"]:
            collect_status = "healthy"
        else:
            collect_status = "idle"

        if str(runtime.get("current_cycle") or "") == "deep_dive":
            admission_status = "running"
        elif state.get("intel_events"):
            admission_status = "healthy"
        elif state["raw_items"]:
            admission_status = "warning"
        else:
            admission_status = "idle"

        if str(runtime.get("current_cycle") or "") in {"deep_dive", "briefing"}:
            briefing_status = "running"
        elif deep_dive_errors or brief_errors:
            briefing_status = "warning"
        elif state.get("event_deep_dives") or state.get("briefs"):
            briefing_status = "healthy"
        else:
            briefing_status = "idle"

        if pending_briefs:
            review_status = "warning"
        elif state.get("briefs"):
            review_status = "healthy"
        else:
            review_status = "idle"

        if browser.get("logged_in"):
            wechat_status = "healthy"
        elif browser.get("last_error"):
            wechat_status = "blocked"
        elif state["channels"]["wechat"].get("browser_profile_path"):
            wechat_status = "warning"
        else:
            wechat_status = "blocked"

        if running_tasks or any(item["action"] == "publish_pipeline" for item in running_jobs):
            publish_status = "running"
        elif blocked_tasks:
            publish_status = "blocked"
        elif any(str(item.get("stage") or "") == "synced" for item in state.get("briefs", [])):
            publish_status = "healthy"
        else:
            publish_status = "idle"

        blockers: list[str] = []
        blockers.extend([f"来源异常：{item['name']}" for item in source_errors[:2]])
        blockers.extend(str(item.get("last_error") or "").strip() for item in brief_errors[:2] if str(item.get("last_error") or "").strip())
        if not browser.get("logged_in"):
            blockers.append("微信公众号浏览器登录态不可用。")
        browser_error = browser.get("last_error")
        if browser_error:
            blockers.append(browser_error.replace("None ", "").strip())
        if blocked_tasks:
            blockers.append(blocked_tasks[0]["message"])
        if runtime.get("blocked_reason"):
            blockers.append(str(runtime.get("blocked_reason")))
        seen: list[str] = []
        for blocker in blockers:
            if blocker and blocker not in seen:
                seen.append(blocker)
        blockers = seen[:6]

        latest_failure = next(
            (
                item for item in state["publish_tasks"]
                if item["status"] in {"blocked", "failed"}
            ),
            None,
        )
        if not latest_failure:
            latest_failure = next((item for item in state["jobs"] if item["status"] == "failed"), None)

        if latest_failure:
            latest_failure_label = latest_failure.get("label") or JOB_LABELS.get(latest_failure.get("action", ""), latest_failure.get("action", ""))
            latest_failure_at = latest_failure.get("created_at") or latest_failure.get("finished_at")
        else:
            latest_failure_label = None
            latest_failure_at = None

        stages = [
            ChainStateCard(key="collect", label="采集", status=collect_status, detail=f"健康 {len([item for item in state['sources'] if item['health_status'] == 'healthy'])}/{len(state['sources'])}"),
            ChainStateCard(key="admission", label="准入", status=admission_status, detail=f"{len(state.get('intel_events', []))} 个事件"),
            ChainStateCard(key="briefing", label="深挖/简报", status=briefing_status, detail=f"{len(state.get('event_deep_dives', []))} 次深挖 / {len(state.get('briefs', []))} 条简报"),
            ChainStateCard(key="review", label="待交付", status=review_status, detail=f"{len(pending_briefs)} 条待上传简报"),
            ChainStateCard(key="wechat", label="微信会话", status=wechat_status, detail="已登录" if browser.get("logged_in") else "未登录"),
            ChainStateCard(key="publish", label="发布", status=publish_status, detail=f"{len(blocked_tasks)} 条阻断记录"),
        ]

        source_alerts = [
            f"{item['name']}：{item['health_detail']}"
            for item in state["sources"]
            if item.get("enabled") and item.get("health_status") in {"warning", "error"}
        ]
        if not source_alerts:
            source_alerts = ["暂无来源异常，信息层运行平稳。"]

        return ExecutionChainSnapshot(
            collect_status=collect_status,
            admission_status=admission_status,
            briefing_status=briefing_status,
            review_status=review_status,
            wechat_status=wechat_status,
            publish_status=publish_status,
            blockers=blockers,
            stages=stages,
            selectors_version=str(browser.get("selectors_version", "")),
            browser_logged_in=bool(browser.get("logged_in")),
            last_screenshot=browser.get("last_screenshot"),
            last_failed_task_label=latest_failure_label,
            last_failed_task_at=latest_failure_at,
            source_alerts=source_alerts[:6],
        )
