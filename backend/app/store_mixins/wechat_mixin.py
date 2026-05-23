from __future__ import annotations

import re
from typing import Any

from ..models import (
    BrowserSessionPayload,
    BrowserSessionState,
    ChannelConfigPayload,
    DictOkResponse,
    PublishBackendStatus,
    PublishTask,
    WeChatChannelConfig,
    WeChatDraftSyncCheckResult,
    WeChatAnalyticsOverview,
    WeChatMappingRow,
    WeChatMappingSnapshot,
    WeChatEditorDomSnapshot,
    WeChatAnalyticsDomSnapshot,
    WeChatPublishHistorySnapshot,
    WeChatPublishRecordItem,
    WeChatRemoteDraftItem,
)
from ..publishers import (
    WECHAT_BROWSER_MANAGER,
    create_publish_task,
    delete_wechat_remote_draft,
    ensure_channel_defaults,
    inspect_wechat_editor_dom,
    inspect_wechat_analytics_dom,
    inspect_wechat_draft_box,
    inspect_wechat_publish_history_with_overview,
    inspect_wechat_publish_history,
    inspect_wechat_session,
    launch_wechat_dashboard,
    fill_wechat_author_only,
    open_wechat_editor_debug,
    test_wechat_publish_settings_only,
)
from ..services.wechat_reconcile import (
    apply_publish_history_matches,
    build_wechat_mapping_snapshot,
    normalize_wechat_title as _normalize_wechat_title,
    wechat_title_matches as _wechat_title_matches,
)
from ..store.base import deepcopy_json, now_iso


class WeChatMixin:
    def list_publish_tasks(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PublishTask], int, int, int, bool]:
        state = self._read_live()
        visible_actions = {"sync_wechat_draft", "delete_wechat_draft", "delete_brief"}
        items = [
            item for item in state["publish_tasks"]
            if isinstance(item, dict) and str(item.get("action") or "") in visible_actions
        ]
        page_items, total, safe_page, safe_page_size, has_more = self._paginate_items(
            items,
            page=page,
            page_size=page_size,
        )
        return [PublishTask(**item) for item in page_items], total, safe_page, safe_page_size, has_more

    def _build_wechat_mapping_snapshot(self, state: dict[str, Any]) -> WeChatMappingSnapshot:
        return build_wechat_mapping_snapshot(
            state,
            WeChatMappingRow,
            WeChatRemoteDraftItem,
            WeChatMappingSnapshot,
        )

    def _match_brief_to_wechat_remote(
        self,
        brief: dict[str, Any],
        remote_items: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        brief_remote_id = str(brief.get("wechat_remote_appmsg_id") or "").strip()
        brief_remote_url = str(brief.get("wechat_editor_url") or "").strip()
        brief_title = _normalize_wechat_title(brief.get("title"))
        for item in remote_items:
            if not isinstance(item, dict):
                continue
            remote_appmsg_id = str(item.get("appmsg_id") or "").strip()
            remote_url = str(item.get("url") or "").strip()
            remote_title = _normalize_wechat_title(item.get("title"))
            if brief_remote_id and remote_appmsg_id and brief_remote_id == remote_appmsg_id:
                return item
            if brief_remote_url and remote_url and brief_remote_url == remote_url:
                return item
            if brief_title and remote_title and _wechat_title_matches(brief_title, remote_title):
                return item
        return None

    def get_wechat_mapping(self) -> WeChatMappingSnapshot:
        state = self._read_live()
        return self._build_wechat_mapping_snapshot(state)

    def refresh_wechat_mapping(self, triggered_by: str = "dashboard") -> WeChatMappingSnapshot:
        self.check_wechat_draft_box(triggered_by=triggered_by)
        latest_state = self._upgrade_state(self._read())
        return self._build_wechat_mapping_snapshot(latest_state)

    def delete_wechat_remote_draft(self, remote_id: str, triggered_by: str = "mapping") -> DictOkResponse:
        state = self._upgrade_state(self._read())
        mapping = self._build_wechat_mapping_snapshot(state)
        remote_key = str(remote_id or "").strip()
        target_row = next(
            (
                row for row in mapping.mapping_rows
                if str(row.remote_key or "") == remote_key
                or str(row.remote_appmsg_id or "") == remote_key
                or str(row.remote_url or "") == remote_key
            ),
            None,
        )
        if not target_row:
            for row in mapping.mapping_rows:
                if not row.local_brief_id:
                    continue
                try:
                    brief = self._find_brief(state, str(row.local_brief_id))
                except ValueError:
                    continue
                brief_remote_id = str(brief.get("wechat_remote_appmsg_id") or "").strip()
                brief_remote_url = str(brief.get("wechat_editor_url") or "").strip()
                if brief_remote_id == remote_key or brief_remote_url == remote_key:
                    target_row = row
                    break
        if not target_row:
            raise ValueError("未找到对应的远端草稿映射。")

        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = delete_wechat_remote_draft(
            {
                "appmsg_id": target_row.remote_appmsg_id,
                "url": target_row.remote_url,
                "title": target_row.remote_title,
            },
            state["channels"]["wechat"],
            browser,
        )
        state["browser"]["wechat"] = browser
        status = "completed" if not browser.get("last_error") else "failed"
        message = "已删除微信草稿箱远端草稿。" if status == "completed" else "删除微信草稿箱远端草稿失败。"
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                str(target_row.local_brief_id or remote_id),
                "delete_wechat_draft",
                status,
                message,
                triggered_by,
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._append_log(
            state,
            "success" if status == "completed" else "warning",
            "wechat",
            f"{message}{target_row.remote_title}",
            detail=str(browser.get("last_error") or ""),
        )
        self._write(state)
        if status == "completed":
            self.check_wechat_draft_box()
            return DictOkResponse(ok=True, message="已删除远端草稿并刷新映射。")
        raise ValueError(str(browser.get("last_error") or "远端草稿删除失败。"))

    def get_wechat_config(self) -> WeChatChannelConfig:
        config = self._upgrade_user_settings(self._read_config())
        return WeChatChannelConfig(**ensure_channel_defaults(config.get("wechat", {})))

    def update_wechat_config(self, payload: ChannelConfigPayload) -> WeChatChannelConfig:
        state = self._upgrade_state(self._read())
        state["channels"]["wechat"].update(payload.model_dump())
        state["channels"]["wechat"] = ensure_channel_defaults(state["channels"]["wechat"])
        config = self._read_config()
        config["wechat"] = deepcopy_json(state["channels"]["wechat"])
        WECHAT_BROWSER_MANAGER.reset("wechat_config_updated")
        self._refresh_browser_session(state)
        self._append_log(state, "success", "channel", "已更新微信公众号配置。")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return WeChatChannelConfig(**state["channels"]["wechat"])

    def get_browser_session(self) -> BrowserSessionState:
        state = self._read_live()
        browser = self._refresh_browser_session(state)
        self._write(state)
        return BrowserSessionState(**browser)

    def update_browser_session(self, payload: BrowserSessionPayload) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        state["channels"]["wechat"]["browser_name"] = payload.browser_name
        state["channels"]["wechat"]["browser_profile_path"] = payload.user_data_dir
        state["channels"]["wechat"] = ensure_channel_defaults(state["channels"]["wechat"])
        config = self._read_config()
        config.setdefault("wechat", {})
        config["wechat"]["browser_name"] = state["channels"]["wechat"]["browser_name"]
        config["wechat"]["browser_profile_path"] = state["channels"]["wechat"]["browser_profile_path"]
        WECHAT_BROWSER_MANAGER.reset("browser_session_updated")
        browser = self._refresh_browser_session(state)
        self._append_log(state, "info", "browser", "已刷新浏览器会话配置。")
        self._write_config(self._upgrade_user_settings(config))
        self._write(state)
        return BrowserSessionState(**browser)

    def open_browser_dashboard(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = launch_wechat_dashboard(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "info",
            "browser",
            "已打开公众号后台登录窗口。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[:3]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "open_dashboard",
                "completed" if not browser.get("last_error") else "failed",
                "已打开公众号后台登录窗口。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def check_browser_session(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = inspect_wechat_session(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "success" if browser.get("logged_in") else "warning",
            "browser",
            "已完成公众号浏览器会话检查。" if browser.get("logged_in") else "公众号浏览器会话未通过检查。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-2:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "check_browser",
                "completed" if browser.get("logged_in") else "blocked",
                "已完成浏览器会话检查。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def inspect_wechat_editor_dom(self) -> WeChatEditorDomSnapshot:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, snapshot, artifacts, step_logs = inspect_wechat_editor_dom(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "success" if not browser.get("last_error") else "warning",
            "browser",
            "已导出微信编辑页 DOM。" if not browser.get("last_error") else "导出微信编辑页 DOM 失败。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-2:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "inspect_wechat_editor_dom",
                "completed" if not browser.get("last_error") else "failed",
                "已导出微信编辑页 DOM。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return WeChatEditorDomSnapshot(**snapshot)

    def inspect_wechat_analytics_dom(self) -> WeChatAnalyticsDomSnapshot:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, snapshot, artifacts, step_logs = inspect_wechat_analytics_dom(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "success" if not browser.get("last_error") else "warning",
            "browser",
            "已导出微信数据分析页 DOM。" if not browser.get("last_error") else "导出微信数据分析页 DOM 失败。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-2:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "inspect_wechat_analytics_dom",
                "completed" if not browser.get("last_error") else "failed",
                "已导出微信数据分析页 DOM。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return WeChatAnalyticsDomSnapshot(**snapshot)

    def open_wechat_editor_debug(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = open_wechat_editor_debug(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "success" if not browser.get("last_error") else "warning",
            "browser",
            "已打开微信编辑页。" if not browser.get("last_error") else "打开微信编辑页失败。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-2:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "open_wechat_editor_debug",
                "completed" if not browser.get("last_error") else "failed",
                "已打开微信编辑页。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def fill_wechat_author_only(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = fill_wechat_author_only(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "success" if not browser.get("last_error") else "warning",
            "browser",
            "已填写微信作者。" if not browser.get("last_error") else "填写微信作者失败。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-3:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "fill_wechat_author_only",
                "completed" if not browser.get("last_error") else "failed",
                "已执行微信作者填写。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def test_wechat_publish_settings_only(self) -> BrowserSessionState:
        state = self._upgrade_state(self._read())
        browser = self._refresh_browser_session(state)
        browser, artifacts, step_logs = test_wechat_publish_settings_only(state["channels"]["wechat"], browser)
        state["browser"]["wechat"] = browser
        self._append_log(
            state,
            "success" if not browser.get("last_error") else "warning",
            "browser",
            "已完成微信后半段流程测试。" if not browser.get("last_error") else "微信后半段流程测试失败。",
            stream="business_event",
            actor="dashboard",
            detail=" | ".join(step_logs[-4:]),
        )
        state["publish_tasks"].insert(
            0,
            create_publish_task(
                "session-wechat",
                "test_wechat_publish_settings_only",
                "completed" if not browser.get("last_error") else "failed",
                "已执行微信后半段流程测试。",
                "dashboard",
                str(state["channels"]["wechat"]["selectors_version"]),
                artifacts=artifacts,
                step_logs=step_logs,
            ),
        )
        self._write(state)
        return BrowserSessionState(**browser)

    def check_wechat_draft_box(self, triggered_by: str = "dashboard") -> WeChatDraftSyncCheckResult:
        with self._lock:
            state = self._upgrade_state(self._read())
            browser = self._refresh_browser_session(state)
            previous_check = browser.get("last_draft_check") if isinstance(browser.get("last_draft_check"), dict) else {}
            browser, artifacts, step_logs, remote_items = inspect_wechat_draft_box(state["channels"]["wechat"], browser)
            state["browser"]["wechat"] = browser

            matched_count = 0
            missing_count = 0
            diff_logs: list[str] = []
            last_check = previous_check
            empty_confirmations = int(last_check.get("empty_confirmations", 0) or 0)
            empty_confirmed = False
            if not browser.get("last_error"):
                def normalize_title(value: Any) -> str:
                    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip().lower()

                def title_matches(left: str, right: str) -> bool:
                    if not left or not right:
                        return False
                    if left == right:
                        return True
                    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
                    if len(shorter) >= 18 and longer.startswith(shorter):
                        return True
                    if len(shorter) >= 18 and shorter in longer:
                        return True
                    return False

                remote_index: dict[str, dict[str, str | None]] = {}
                remote_titles: list[tuple[str, dict[str, str | None]]] = []
                matched_remote_titles: set[str] = set()
                for item in remote_items:
                    url = str(item.get("url") or "").strip()
                    appmsg_id = str(item.get("appmsg_id") or "").strip()
                    title = normalize_title(item.get("title"))
                    if url:
                        remote_index[url] = item
                    if appmsg_id:
                        remote_index[f"appmsg:{appmsg_id}"] = item
                    if title:
                        remote_titles.append((title, item))

                if remote_items:
                    empty_confirmations = 0
                else:
                    empty_confirmations += 1
                    empty_confirmed = empty_confirmations >= 3
                    step_logs.append(f"远端草稿箱为空候选，第 {empty_confirmations}/3 次。")

                for brief in state.get("briefs", []):
                    if not isinstance(brief, dict):
                        continue
                    previous_synced = str(brief.get("stage") or "") == "synced"
                    remote_match = None
                    remote_appmsg_id = str(brief.get("wechat_remote_appmsg_id") or "").strip()
                    remote_url = str(brief.get("wechat_editor_url") or "").strip()
                    brief_title = normalize_title(brief.get("title"))
                    if remote_appmsg_id:
                        remote_match = remote_index.get(f"appmsg:{remote_appmsg_id}")
                    if not remote_match and remote_url:
                        remote_match = remote_index.get(remote_url)
                    if not remote_match and brief_title:
                        for candidate_title, candidate_item in remote_titles:
                            if title_matches(candidate_title, brief_title):
                                remote_match = candidate_item
                                break

                    if remote_match:
                        matched_count += 1
                        brief["stage"] = "synced"
                        brief["delivery_status"] = "verified"
                        matched_title = normalize_title(remote_match.get("title"))
                        if matched_title:
                            matched_remote_titles.add(matched_title)
                        remote_match_url = str(remote_match.get("url") or "").strip()
                        remote_match_appmsg_id = str(remote_match.get("appmsg_id") or "").strip()
                        if remote_match_url:
                            brief["wechat_editor_url"] = remote_match_url
                        if remote_match_appmsg_id:
                            brief["wechat_remote_appmsg_id"] = remote_match_appmsg_id
                        brief["last_error"] = None
                        brief["last_delivery_error_kind"] = None
                        brief["last_verified_at"] = now_iso()
                        brief["updated_at"] = now_iso()
                        diff_logs.append(f"=远端草稿 \"{brief.get('title') or '未命名简报'}\" 状态无变化")
                        continue

                    entered_formal_draft_box = any("已进入草稿箱页面" in log for log in step_logs)
                    scraped_formal_draft_box = any("共读取到" in log for log in step_logs)
                    if previous_synced and entered_formal_draft_box and scraped_formal_draft_box and (remote_items or empty_confirmed):
                        missing_count += 1
                        brief["stage"] = "prepared"
                        brief["delivery_status"] = "target_missing"
                        brief["last_error"] = "微信草稿箱中未找到对应草稿，可能已被删除。"
                        brief["last_delivery_error_kind"] = "target_missing"
                        brief["updated_at"] = now_iso()
                        diff_logs.append(f"-远端草稿 \"{brief.get('title') or '未命名简报'}\" 已消失，本地 {brief.get('id') or 'brief'} 回退为 prepared")

                local_titles = {
                    normalize_title(brief.get("title"))
                    for brief in state.get("briefs", [])
                    if isinstance(brief, dict) and normalize_title(brief.get("title"))
                }
                for candidate_title, _candidate_item in remote_titles:
                    if candidate_title in matched_remote_titles:
                        continue
                    if candidate_title not in local_titles:
                        diff_logs.append(f"+新增远端草稿 \"{candidate_title}\"（未匹配本地简报）")

            if remote_items:
                message = (
                    f"已检查微信草稿箱，共读取 {len(remote_items)} 条远端草稿；"
                    f"匹配本地简报 {matched_count} 条，发现缺失 {missing_count} 条。"
                )
            else:
                if empty_confirmed:
                    message = (
                        "已检查微信草稿箱，当前远端草稿为 0 条；"
                        f"匹配本地简报 {matched_count} 条，发现缺失 {missing_count} 条。"
                    )
                else:
                    message = (
                        f"已检查微信草稿箱，本次读取到 0 条远端草稿，正在做空列表确认（{empty_confirmations}/3）；"
                        f"当前先保留本地已同步状态。"
                    )
            if browser.get("last_error"):
                previous_items = previous_check.get("items", []) if isinstance(previous_check.get("items"), list) else []
                preserved_remote_count = int(previous_check.get("remote_count", len(previous_items)) or 0)
                preserved_matched = int(previous_check.get("matched_count", 0) or 0)
                preserved_missing = int(previous_check.get("missing_count", 0) or 0)
                fallback_message = (
                    f"本次检查失败，当前展示最近一次成功读取结果：远端 {preserved_remote_count} 条，"
                    f"已匹配 {preserved_matched} 条，待核对 {preserved_missing} 条。"
                )
                result_payload = {
                    "checked_at": now_iso(),
                    "remote_count": preserved_remote_count,
                    "matched_count": preserved_matched,
                    "missing_count": preserved_missing,
                    "items": previous_items[:30],
                    "message": fallback_message if previous_items else str(browser.get("last_error") or "微信草稿箱检查失败。"),
                    "empty_confirmations": int(previous_check.get("empty_confirmations", 0) or 0),
                    "check_ok": False,
                }
                for brief in state.get("briefs", []):
                    if not isinstance(brief, dict):
                        continue
                    if str(brief.get("stage") or "") == "synced":
                        brief["delivery_status"] = "check_failed"
                        brief["last_delivery_error_kind"] = "check_failed"
            else:
                result_payload = {
                    "checked_at": now_iso(),
                    "remote_count": len(remote_items),
                    "matched_count": matched_count,
                    "missing_count": missing_count,
                    "items": remote_items[:30],
                    "message": message,
                    "empty_confirmations": empty_confirmations,
                    "check_ok": True,
                }
            state["browser"]["wechat"]["last_draft_check"] = result_payload
            self._append_log(
                state,
                "success" if not browser.get("last_error") else "warning",
                "browser",
                str(result_payload["message"]),
                stream="business_event",
                actor=triggered_by,
                detail=" | ".join(step_logs[-3:]),
            )
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    "session-wechat",
                    "check_wechat_drafts",
                    "blocked" if browser.get("last_error") else "completed",
                    str(result_payload["message"]),
                    triggered_by,
                    str(state["channels"]["wechat"]["selectors_version"]),
                    artifacts=artifacts,
                    step_logs=step_logs + diff_logs[:8],
                ),
            )
            state["publish_tasks"] = state["publish_tasks"][:80]
            self._write(state)
            return WeChatDraftSyncCheckResult(
                checked_at=str(result_payload["checked_at"]),
                remote_count=int(result_payload["remote_count"]),
                matched_count=int(result_payload["matched_count"]),
                missing_count=int(result_payload["missing_count"]),
                items=[WeChatRemoteDraftItem(**item) for item in result_payload["items"]],
                message=str(result_payload["message"]),
                check_ok=bool(result_payload.get("check_ok", True)),
            )

    def check_wechat_publish_history(self, triggered_by: str = "dashboard") -> WeChatPublishHistorySnapshot:
        with self._lock:
            state = self._upgrade_state(self._read())
            browser = self._refresh_browser_session(state)
            previous_check = (
                browser.get("last_publish_history_check")
                if isinstance(browser.get("last_publish_history_check"), dict)
                else {}
            )
            previous_overview = (
                browser.get("last_analytics_overview")
                if isinstance(browser.get("last_analytics_overview"), dict)
                else None
            )
            browser, artifacts, step_logs, remote_items, overview = inspect_wechat_publish_history_with_overview(
                state["channels"]["wechat"],
                browser,
            )
            state["browser"]["wechat"] = browser
            diff_logs: list[str] = []

            if browser.get("last_error"):
                previous_items = previous_check.get("items", []) if isinstance(previous_check.get("items"), list) else []
                result_payload = {
                    "checked_at": now_iso(),
                    "record_count": int(previous_check.get("record_count", len(previous_items)) or 0),
                    "items": previous_items[:50],
                    "overview": previous_check.get("overview") if isinstance(previous_check.get("overview"), dict) else previous_overview,
                    "message": (
                        f"本次发表记录检查失败，当前展示最近一次成功读取结果：{int(previous_check.get('record_count', len(previous_items)) or 0)} 条。"
                        if previous_items
                        else str(browser.get("last_error") or "微信发表记录检查失败。")
                    ),
                    "check_ok": False,
                }
            else:
                matched_count, diff_logs = apply_publish_history_matches(
                    [brief for brief in state.get("briefs", []) if isinstance(brief, dict)],
                    [item for item in remote_items if isinstance(item, dict)],
                )
                overview_payload = overview if isinstance(overview, dict) else None
                state["browser"]["wechat"]["last_analytics_overview"] = overview_payload
                message = f"已检查微信发表记录，共读取 {len(remote_items)} 条远端记录；命中本地 {matched_count} 条。"
                if not overview_payload:
                    message += " 文章数据已刷新，账号总览暂未抓到。"
                result_payload = {
                    "checked_at": now_iso(),
                    "record_count": len(remote_items),
                    "items": remote_items[:50],
                    "overview": overview_payload,
                    "message": message,
                    "check_ok": True,
                }

            state["browser"]["wechat"]["last_publish_history_check"] = result_payload
            self._append_log(
                state,
                "success" if not browser.get("last_error") else "warning",
                "browser",
                str(result_payload["message"]),
                stream="business_event",
                actor=triggered_by,
                detail=" | ".join(step_logs[-3:]),
            )
            state["publish_tasks"].insert(
                0,
                create_publish_task(
                    "session-wechat",
                    "check_wechat_publish_history",
                    "blocked" if browser.get("last_error") else "completed",
                    str(result_payload["message"]),
                    triggered_by,
                    str(state["channels"]["wechat"]["selectors_version"]),
                    artifacts=artifacts,
                    step_logs=step_logs + (diff_logs[:8] if not browser.get("last_error") else []),
                ),
            )
            state["publish_tasks"] = state["publish_tasks"][:80]
            self._write(state)
            return WeChatPublishHistorySnapshot(
                checked_at=str(result_payload["checked_at"]),
                record_count=int(result_payload["record_count"]),
                items=[WeChatPublishRecordItem(**item) for item in result_payload["items"]],
                overview=WeChatAnalyticsOverview(**result_payload["overview"]) if isinstance(result_payload.get("overview"), dict) else None,
                message=str(result_payload["message"]),
                check_ok=bool(result_payload.get("check_ok", True)),
            )

    def get_publish_backends(self) -> list[PublishBackendStatus]:
        state = self._read_live()
        browser = self._refresh_browser_session(state)
        state["browser"]["wechat"] = browser
        backends = self._publish_backends(state)
        self._write(state)
        return [PublishBackendStatus(**item) for item in backends]
