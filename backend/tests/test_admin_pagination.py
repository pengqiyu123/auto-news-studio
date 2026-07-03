from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
from typing import Any

from fastapi.testclient import TestClient


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_state() -> dict[str, Any]:
    return {
        "automation_mode": "radar_only",
        "automation_mode_definitions": [],
        "automation_profiles": [],
        "sources": [
            {
                "id": "source-1",
                "key": "rss-openai",
                "name": "RSS OpenAI",
                "driver": "legacy_rss",
                "enabled": True,
                "schedule": "*/30 * * * *",
                "item_count": 1,
                "health_status": "healthy",
                "health_detail": None,
                "capabilities": ["legacy-import"],
            }
        ],
        "raw_items": [],
        "discovery_items": [],
        "intel_events": [
            {
                "id": "evt-1",
                "title": "OpenAI Health rollout",
                "summary": "summary",
                "representative_link": "https://example.com/evt-1",
                "representative_source_name": "RSS",
                "representative_discovery_item_id": "disc-1",
                "discovery_item_ids": ["disc-1"],
                "source_keys": ["rss-openai"],
                "source_names": ["RSS OpenAI"],
                "platforms": ["rss"],
                "platform_count": 1,
                "source_count": 1,
                "member_count": 1,
                "story_count": 1,
                "member_delta": 0,
                "platform_delta": 0,
                "published_at": "2026-05-05T10:00:00+00:00",
                "latest_collected_at": "2026-05-05T10:10:00+00:00",
                "first_seen_at": "2026-05-05T10:10:00+00:00",
                "last_seen_at": "2026-05-05T10:10:00+00:00",
                "tags": ["ai"],
                "anchor_tokens": ["openai", "health"],
                "velocity_score": 80.0,
                "coverage_score": 70.0,
                "freshness_score": 90.0,
                "composite_score": 82.0,
                "velocity_details": {},
                "alert_state": "watch",
                "change_state": "new_event",
                "alert_reason": "",
                "entity_ids": ["openai"],
                "entity_names": ["OpenAI"],
                "watchlisted": True,
                "ignored": False,
                "deep_dive_id": "dd-1",
                "brief_id": "brief-1",
                "deep_dive_status": "ready",
                "brief_status": "prepared",
                "deep_dive_summary": "summary",
                "worth_to_brief": True,
                "worth_reason": "important",
            }
        ],
        "event_snapshots": [],
        "intel_alerts": [],
        "intel_event_history": [],
        "intel_alert_history": [],
        "event_deep_dives": [
            {
                "id": "dd-1",
                "event_id": "evt-1",
                "status": "ready",
                "started_at": "2026-05-05T10:11:00+00:00",
                "finished_at": "2026-05-05T10:13:00+00:00",
                "updated_at": "2026-05-05T10:13:00+00:00",
                "attempted_count": 1,
                "success_count": 1,
                "failed_count": 0,
                "resolved_evidence_pack": [],
                "full_text_sources": [],
                "sources": [
                    {
                        "source_key": "rss-openai",
                        "source_name": "RSS OpenAI",
                        "original_link": "https://example.com/source-1",
                        "canonical_link": "https://example.com/source-1",
                        "title": "source title",
                        "published_at": "2026-05-05T10:00:00+00:00",
                        "fetch_status": "fetched",
                        "extract_status": "extracted",
                        "word_count": 600,
                        "cleaned_full_text": "full text",
                        "excerpt": "excerpt",
                        "quotes": ["quote 1"],
                        "error": None,
                    }
                ],
                "facts": ["fact 1"],
                "quotes": ["quote 1"],
                "timeline": ["timeline 1"],
                "worthiness": {"reason": "worth it"},
                "last_error": None,
                "article_writing_guide": "Guide text",
            }
        ],
        "briefs": [
            {
                "id": "brief-1",
                "event_id": "evt-1",
                "deep_dive_id": "dd-1",
                "brief_level": "enhanced",
                "stage": "prepared",
                "title": "OpenAI Health 正式发布",
                "one_line": "OpenAI expands health efforts",
                "why_it_matters": "Healthcare scale matters",
                "facts": ["fact 1"],
                "quotes": [],
                "timeline": [],
                "entity_names": ["OpenAI"],
                "source_links": ["https://example.com/source-1"],
                "risk_notes": [],
                "prompt_package_markdown": "pkg",
                "wechat_markdown": "# article 1",
                "wechat_html": "<h1>article 1</h1>",
                "wechat_target_id": "wx-1",
                "wechat_editor_url": None,
                "wechat_remote_appmsg_id": None,
                "preview_url": "https://preview/1",
                "delivery_status": "idle",
                "delivery_attempt_count": 0,
                "last_delivery_attempt_at": None,
                "last_verified_at": None,
                "last_delivery_error_kind": None,
                "needs_resync": False,
                "last_synced_revision": None,
                "last_successful_upload_at": None,
                "last_error": None,
                "updated_at": "2026-05-05T11:00:00+00:00",
            },
            {
                "id": "brief-2",
                "event_id": "evt-2",
                "deep_dive_id": "dd-2",
                "brief_level": "rule",
                "stage": "synced",
                "title": "DeepSeek TUI update",
                "one_line": "CLI agent news",
                "why_it_matters": "Terminal workflow is growing",
                "facts": ["fact 2"],
                "quotes": [],
                "timeline": [],
                "entity_names": ["DeepSeek"],
                "source_links": ["https://example.com/source-2"],
                "risk_notes": [],
                "prompt_package_markdown": "pkg-2",
                "wechat_markdown": "# article 2",
                "wechat_html": "<h1>article 2</h1>",
                "wechat_target_id": "wx-2",
                "wechat_editor_url": "https://mp.weixin.qq.com/draft2",
                "wechat_remote_appmsg_id": "appmsg-2",
                "preview_url": "https://preview/2",
                "delivery_status": "verified",
                "delivery_attempt_count": 1,
                "last_delivery_attempt_at": "2026-05-05T12:00:00+00:00",
                "last_verified_at": "2026-05-05T12:01:00+00:00",
                "last_delivery_error_kind": None,
                "needs_resync": False,
                "last_synced_revision": "rev-2",
                "last_successful_upload_at": "2026-05-05T12:00:00+00:00",
                "last_error": None,
                "updated_at": "2026-05-05T12:00:00+00:00",
            },
            {
                "id": "brief-3",
                "event_id": "evt-3",
                "deep_dive_id": "dd-3",
                "brief_level": "rule",
                "stage": "failed",
                "title": "Uber robotics rumor",
                "one_line": "Rumor watch",
                "why_it_matters": "May be noise",
                "facts": ["fact 3"],
                "quotes": [],
                "timeline": [],
                "entity_names": ["Uber"],
                "source_links": ["https://example.com/source-3"],
                "risk_notes": [],
                "prompt_package_markdown": "pkg-3",
                "wechat_markdown": "# article 3",
                "wechat_html": "<h1>article 3</h1>",
                "wechat_target_id": "wx-3",
                "wechat_editor_url": None,
                "wechat_remote_appmsg_id": None,
                "preview_url": "https://preview/3",
                "delivery_status": "idle",
                "delivery_attempt_count": 1,
                "last_delivery_attempt_at": "2026-05-05T13:00:00+00:00",
                "last_verified_at": None,
                "last_delivery_error_kind": "upload",
                "needs_resync": False,
                "last_synced_revision": None,
                "last_successful_upload_at": None,
                "last_error": "upload failed",
                "updated_at": "2026-05-05T13:00:00+00:00",
            },
        ],
        "normalized_items": [],
        "publish_tasks": [
            {
                "id": "task-1",
                "target_id": "brief-1",
                "action": "sync_wechat_draft",
                "status": "completed",
                "stage": "wechat",
                "message": "synced 1",
                "triggered_by": "dashboard",
                "created_at": "2026-05-05T13:10:00+00:00",
                "artifacts": [],
                "step_logs": [],
                "selector_profile": "wechat-mp-v1",
            },
            {
                "id": "task-2",
                "target_id": "brief-2",
                "action": "delete_brief",
                "status": "completed",
                "stage": "cleanup",
                "message": "deleted local",
                "triggered_by": "agent",
                "created_at": "2026-05-05T13:11:00+00:00",
                "artifacts": [],
                "step_logs": [],
                "selector_profile": "wechat-mp-v1",
            },
            {
                "id": "task-3",
                "target_id": "brief-3",
                "action": "check_wechat_publish_history",
                "status": "completed",
                "stage": "browser",
                "message": "should be hidden",
                "triggered_by": "system",
                "created_at": "2026-05-05T13:12:00+00:00",
                "artifacts": [],
                "step_logs": [],
                "selector_profile": "wechat-mp-v1",
            },
        ],
        "jobs": [],
        "logs": [
            {
                "id": "log-1",
                "level": "info",
                "message": "Alpha complete",
                "created_at": "2026-05-05T10:00:00+00:00",
                "category": "brief",
                "stream": "business_event",
                "actor": "agent",
                "detail": "detail alpha",
            },
            {
                "id": "log-2",
                "level": "warning",
                "message": "Beta warning",
                "created_at": "2026-05-05T11:00:00+00:00",
                "category": "collection",
                "stream": "business_event",
                "actor": "system",
                "detail": "detail beta",
            },
            {
                "id": "log-3",
                "level": "error",
                "message": "Gamma error",
                "created_at": "2026-05-05T12:00:00+00:00",
                "category": "wechat",
                "stream": "business_event",
                "actor": "browser",
                "detail": "detail gamma",
            },
        ],
        "notifications": {"webhook": {"enabled": False, "url": "", "secret": "", "events": ["breakout"]}, "delivery_log": []},
        "app_meta": {"dismissed_update_version": None, "last_update_check": None},
        "channels": {
            "wechat": {
                "app_id": "",
                "app_secret_masked": "",
                "author": "Auto News Studio",
                "default_cover_strategy": "auto",
                "default_digest_strategy": "balanced",
                "draft_mode": True,
                "preview_enabled": True,
                "auto_send_window": "09:00-10:00",
                "risk_keywords": [],
                "browser_name": "edge",
                "browser_profile_path": "",
                "publish_entry_url": "https://mp.weixin.qq.com/",
                "selectors_version": "wechat-mp-v1",
                "sidecar_url": "http://127.0.0.1:8091",
            }
        },
        "browser": {
            "wechat": {
                "platform": "wechat_mp",
                "browser_name": "edge",
                "user_data_dir": "",
                "logged_in": False,
                "last_checked_at": None,
                "last_opened_url": None,
                "last_error": None,
                "selectors_version": "wechat-mp-v1",
                "last_screenshot": None,
                "last_selector_check": None,
                "current_page": None,
                "sidecar_health": "offline",
                "manager_alive": False,
                "window_state": "unknown",
                "resident_page": None,
                "busy": False,
                "last_reset_reason": None,
                "session_generation": 0,
                "last_action": None,
                "last_action_phase": None,
                "is_session_level_error": False,
                "last_draft_check": {
                    "checked_at": "2026-05-05T12:20:00+00:00",
                    "remote_count": 1,
                    "matched_count": 1,
                    "missing_count": 0,
                    "message": "已检查微信草稿箱。",
                    "check_ok": True,
                    "items": [
                        {
                            "title": "DeepSeek TUI update",
                            "url": "https://mp.weixin.qq.com/draft2",
                            "appmsg_id": "appmsg-2",
                            "updated_at": "2026-05-05T12:10:00+00:00",
                            "remote_key": "appmsg:appmsg-2",
                        }
                    ],
                },
                "last_publish_history_check": {
                    "checked_at": "2026-05-05T12:30:00+00:00",
                    "record_count": 1,
                    "message": "已检查微信发表记录。",
                    "check_ok": True,
                    "items": [
                        {
                            "title": "OpenAI Health 正式发布",
                            "url": "https://mp.weixin.qq.com/s/health",
                            "appmsg_id": "appmsg-1",
                            "published_at": "2026-05-05 20:00",
                            "remote_key": "appmsg:appmsg-1",
                        }
                    ],
                },
            }
        },
        "reference_projects": [],
        "entity_watchlist": [],
        "runtime": {
            "control_state": "stopped",
            "last_successful_sync_at": None,
            "last_cycle_summary": None,
        },
    }


def _build_client(tmp_root: Path) -> TestClient:
    state_file = tmp_root / "data" / "state.json"
    config_file = tmp_root / "config" / "user-settings.json"
    _write_json(state_file, _build_state())
    _write_json(config_file, {"schema_version": 1, "llm": {"profiles": [], "providers": []}, "sources": {"overrides": {}}, "settings": {"max_workers": 4, "tavily_api_key": ""}, "wechat": {}})

    if "trafilatura" not in sys.modules:
        trafilatura_stub = types.ModuleType("trafilatura")
        trafilatura_stub.extract = lambda *args, **kwargs: ""
        sys.modules["trafilatura"] = trafilatura_stub
    if "readability" not in sys.modules:
        readability_stub = types.ModuleType("readability")

        class _Document:
            def __init__(self, html: str) -> None:
                self._html = html

            def summary(self, html_partial: bool = True) -> str:
                return self._html

        readability_stub.Document = _Document
        sys.modules["readability"] = readability_stub
    if "openai" not in sys.modules:
        openai_stub = types.ModuleType("openai")

        class _OpenAIError(Exception):
            pass

        class _OpenAIClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                self.args = args
                self.kwargs = kwargs

        openai_stub.APIConnectionError = _OpenAIError
        openai_stub.APITimeoutError = _OpenAIError
        openai_stub.AuthenticationError = _OpenAIError
        openai_stub.BadRequestError = _OpenAIError
        openai_stub.InternalServerError = _OpenAIError
        openai_stub.NotFoundError = _OpenAIError
        openai_stub.OpenAI = _OpenAIClient
        openai_stub.RateLimitError = _OpenAIError
        sys.modules["openai"] = openai_stub
    if "python_multipart" not in sys.modules:
        python_multipart_stub = types.ModuleType("python_multipart")
        python_multipart_stub.__version__ = "0.0.20"
        sys.modules["python_multipart"] = python_multipart_stub

    import backend.app.store.reference_projects as reference_projects
    import backend.app.store as store_module
    import backend.app.store.base as store_base

    store_base.DATA_FILE = state_file
    store_base.CONFIG_DIR = config_file.parent
    store_base.CONFIG_FILE = config_file
    reference_projects.REFERENCES_ROOT = tmp_root / "references"
    reference_projects.REFERENCE_FILE = reference_projects.REFERENCES_ROOT / "reference_projects.json"
    reference_projects.BORROW_MAP_FILE = reference_projects.REFERENCES_ROOT / "borrow_map.json"
    store_module.DATA_FILE = state_file
    store_module.CONFIG_FILE = config_file

    import backend.app.main as main_module

    main_module = importlib.reload(main_module)
    return TestClient(main_module.app)


def _make_repo_temp_dir() -> Path:
    base = Path.cwd() / "runtime" / "pytest-temp"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="admin-pagination-", dir=base))


def test_list_briefs_supports_pagination_and_filters() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        response = client.get("/api/admin/briefs?page=1&page_size=2&stage=local_only&q=uber")
        assert response.status_code == 200
        payload = response.json()

        assert payload["total"] == 1
        assert payload["page"] == 1
        assert payload["page_size"] == 2
        assert payload["has_more"] is False
        assert [item["id"] for item in payload["items"]] == ["brief-3"]
        assert payload["stage_counts"] == {
            "all": 3,
            "prepared": 1,
            "synced": 1,
            "failed": 1,
        }
        assert payload["record_counts"] == {
            "all": 3,
            "local_only": 1,
            "draft_synced": 1,
            "published": 1,
            "exceptions": 0,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_briefs_projection_reports_record_statuses_and_filters() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        response = client.get("/api/admin/briefs?page=1&page_size=10")
        assert response.status_code == 200
        payload = response.json()
        statuses = {item["id"]: item["record_status"] for item in payload["items"]}

        assert statuses["brief-1"] == "published"
        assert statuses["brief-2"] == "draft_synced"
        assert statuses["brief-3"] == "local_only"
        published_at = {item["id"]: item["publish_record_published_at"] for item in payload["items"]}
        draft_times = {item["id"]: item["draft_remote_updated_at"] for item in payload["items"]}
        assert published_at["brief-1"] == "2026-05-05 20:00"
        assert draft_times["brief-2"] == "2026-05-05T12:10:00+00:00"

        published_only = client.get("/api/admin/briefs?stage=published")
        assert published_only.status_code == 200
        assert [item["id"] for item in published_only.json()["items"]] == ["brief-1"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_briefs_projection_marks_check_failures_and_pending_confirmation() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)
        state_file = temp_dir / "data" / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["browser"]["wechat"]["last_draft_check"]["check_ok"] = False
        state["browser"]["wechat"]["last_publish_history_check"]["check_ok"] = False
        state["briefs"][2]["delivery_attempt_count"] = 1
        state["briefs"][2]["last_delivery_attempt_at"] = "2026-05-05T13:00:00+00:00"
        _write_json(state_file, state)

        response = client.get("/api/admin/briefs")
        assert response.status_code == 200
        payload = response.json()
        exceptions = {item["id"]: item["record_exception"] for item in payload["items"]}
        assert exceptions["brief-1"] == "draft_check_failed"
        assert exceptions["brief-2"] == "draft_check_failed"
        assert exceptions["brief-3"] == "draft_check_failed"

        state["browser"]["wechat"]["last_draft_check"]["check_ok"] = True
        state["browser"]["wechat"]["last_publish_history_check"]["check_ok"] = True
        state["browser"]["wechat"]["last_draft_check"]["items"] = []
        state["browser"]["wechat"]["last_publish_history_check"]["items"] = []
        state["browser"]["wechat"]["last_publish_history_check"]["record_count"] = 0
        state["briefs"][1]["stage"] = "prepared"
        state["briefs"][1]["delivery_status"] = "idle"
        state["briefs"][1]["last_synced_revision"] = None
        state["briefs"][1]["last_successful_upload_at"] = None
        state["briefs"][1]["wechat_editor_url"] = None
        state["briefs"][1]["wechat_remote_appmsg_id"] = None
        state["briefs"][0]["last_delivery_attempt_at"] = "2026-05-05T13:40:00+00:00"
        _write_json(state_file, state)

        response = client.get("/api/admin/briefs")
        assert response.status_code == 200
        payload = response.json()
        exceptions = {item["id"]: item["record_exception"] for item in payload["items"]}
        assert exceptions["brief-1"] == "pending_confirmation"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_briefs_projection_keeps_published_when_draft_snapshot_misses() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)
        state_file = temp_dir / "data" / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["browser"]["wechat"]["last_draft_check"]["items"] = []
        state["browser"]["wechat"]["last_draft_check"]["matched_count"] = 0
        state["browser"]["wechat"]["last_draft_check"]["missing_count"] = 1
        state["browser"]["wechat"]["last_draft_check"]["checked_at"] = "2026-05-05T12:30:00+00:00"
        state["browser"]["wechat"]["last_publish_history_check"]["checked_at"] = "2026-05-05T13:30:00+00:00"
        _write_json(state_file, state)

        response = client.get("/api/admin/briefs")
        assert response.status_code == 200
        payload = response.json()
        statuses = {item["id"]: item["record_status"] for item in payload["items"]}
        exceptions = {item["id"]: item["record_exception"] for item in payload["items"]}
        assert statuses["brief-1"] == "published"
        assert exceptions["brief-1"] is None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_briefs_projection_delays_draft_missing_until_publish_check_catches_up() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)
        state_file = temp_dir / "data" / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["browser"]["wechat"]["last_draft_check"]["items"] = []
        state["browser"]["wechat"]["last_draft_check"]["checked_at"] = "2026-05-05T13:30:00+00:00"
        state["browser"]["wechat"]["last_publish_history_check"]["items"] = []
        state["browser"]["wechat"]["last_publish_history_check"]["record_count"] = 0
        state["browser"]["wechat"]["last_publish_history_check"]["checked_at"] = "2026-05-05T12:00:00+00:00"
        state["briefs"][1]["stage"] = "synced"
        state["briefs"][1]["delivery_status"] = "verified"
        state["briefs"][1]["wechat_editor_url"] = "https://mp.weixin.qq.com/draft2"
        state["briefs"][1]["wechat_remote_appmsg_id"] = "appmsg-2"
        state["briefs"][1]["last_verified_at"] = "2026-05-05T11:00:00+00:00"
        _write_json(state_file, state)

        response = client.get("/api/admin/briefs")
        assert response.status_code == 200
        payload = response.json()
        exceptions = {item["id"]: item["record_exception"] for item in payload["items"]}
        assert exceptions["brief-2"] == "pending_confirmation"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_wechat_mapping_message_uses_current_reconcile_snapshot() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        response = client.get("/api/admin/wechat/mapping")
        assert response.status_code == 200
        payload = response.json()["item"]

        assert payload["remote_count"] == 1
        assert payload["matched_count"] == 1
        assert payload["missing_count"] == 1
        assert payload["message"] == "已检查微信草稿箱，共读取 1 条远端草稿；当前对账已映射 1 条，待核对 1 条。"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_list_logs_supports_level_query_and_page_size_clamp() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        response = client.get("/api/admin/logs?page=1&page_size=500&level=warning&q=beta")
        assert response.status_code == 200
        payload = response.json()

        assert payload["page_size"] == 200
        assert payload["total"] == 1
        assert [item["id"] for item in payload["items"]] == ["log-2"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_list_publish_tasks_uses_visible_actions_with_pagination() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        response = client.get("/api/admin/publish-tasks?page=2&page_size=1")
        assert response.status_code == 200
        payload = response.json()

        assert payload["total"] == 2
        assert payload["page"] == 2
        assert payload["page_size"] == 1
        assert payload["has_more"] is False
        assert [item["id"] for item in payload["items"]] == ["task-2"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_get_event_deep_dive_keeps_article_writing_guide() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        response = client.get("/api/admin/intel/deep-dives/evt-1")
        assert response.status_code == 200
        payload = response.json()

        assert payload["item"]["article_writing_guide"] == "Guide text"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_agent_can_create_local_brief_record_without_upload() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        response = client.post("/api/admin/intel/events/evt-1/brief?triggered_by=agent")
        assert response.status_code == 200
        payload = response.json()

        assert payload["item"]["event_id"] == "evt-1"
        assert payload["item"]["brief_level"] in {"rule", "enhanced"}

        briefs_response = client.get("/api/admin/briefs?q=OpenAI Health")
        assert briefs_response.status_code == 200
        briefs_payload = briefs_response.json()
        assert briefs_payload["total"] >= 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_manual_daily_digest_endpoint_creates_one_local_roundup() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)
        state_file = temp_dir / "data" / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["automation_mode"] = "radar_and_draft"
        state["runtime_plan"] = {
            "launch_mode": "interval_now",
            "interval_minutes": 30,
            "timezone": "Asia/Shanghai",
            "work_scope": "collect_events_alerts",
            "delivery_mode": "immediate",
            "admission_strategy": "balanced",
            "batch_limit": 5,
            "admission_filters": {
                "require_watchlisted": False,
                "require_entity_match": False,
                "min_source_count": 0,
                "min_fulltext_count": 1,
                "breakout_only": False,
                "exclude_existing_brief": True,
                "exclude_synced_brief": True,
            },
        }
        state["briefs"] = []
        state["intel_events"] = []
        state["event_deep_dives"] = []
        for index, title in enumerate(
            [
                "华为发布 AI DC 全栈方案",
                "OpenAI 推出企业管理更新",
                "国产芯片工具链更新",
                "三星 PCIe Gen6 固态硬盘上线官网",
                "雷鸟发布 V4 AI 拍摄眼镜",
            ],
            start=1,
        ):
            event_id = f"evt-daily-api-{index}"
            fact = f"{title}，这是第 {index} 条可核验事实。"
            state["intel_events"].append(
                {
                    "id": event_id,
                    "title": title,
                    "summary": fact,
                    "representative_link": f"https://example.com/daily-api-{index}",
                    "representative_source_name": "Example",
                    "representative_discovery_item_id": f"disc-daily-api-{index}",
                    "discovery_item_ids": [f"disc-daily-api-{index}"],
                    "source_keys": ["rss-openai"],
                    "source_names": ["Example"],
                    "platforms": ["rss"],
                    "platform_count": 1,
                    "source_count": 2,
                    "member_count": 1,
                    "story_count": 1,
                    "member_delta": 0,
                    "platform_delta": 0,
                    "published_at": "2026-05-26T10:00:00+08:00",
                    "latest_collected_at": "2026-05-26T10:05:00+08:00",
                    "first_seen_at": "2026-05-26T10:05:00+08:00",
                    "last_seen_at": "2026-05-26T10:05:00+08:00",
                    "tags": ["ai"],
                    "anchor_tokens": ["ai"],
                    "velocity_score": 80.0,
                    "coverage_score": 70.0,
                    "freshness_score": 90.0,
                    "composite_score": 90.0 - index,
                    "velocity_details": {},
                    "alert_state": "breakout" if index == 1 else "rising",
                    "change_state": "new_event",
                    "alert_reason": "",
                    "entity_ids": [],
                    "entity_names": [title.split()[0]],
                    "watchlisted": False,
                    "ignored": False,
                    "deep_dive_id": f"dd-daily-api-{index}",
                    "brief_id": None,
                    "deep_dive_status": "ready",
                    "brief_status": None,
                    "worth_to_brief": True,
                    "worth_reason": "有明确事实和来源。",
                }
            )
            state["event_deep_dives"].append(
                {
                    "id": f"dd-daily-api-{index}",
                    "event_id": event_id,
                    "status": "ready",
                    "started_at": "2026-05-26T10:00:00+08:00",
                    "finished_at": "2026-05-26T10:01:00+08:00",
                    "updated_at": f"2026-05-26T10:0{index}:00+08:00",
                    "attempted_count": 1,
                    "success_count": 1,
                    "failed_count": 0,
                    "resolved_evidence_pack": [],
                    "full_text_sources": [],
                    "sources": [
                        {
                            "source_key": "example",
                            "source_name": "Example",
                            "original_link": f"https://example.com/daily-api-{index}",
                            "canonical_link": f"https://example.com/daily-api-{index}",
                            "title": title,
                            "published_at": "2026-05-26T10:00:00+08:00",
                            "fetch_status": "fetched",
                            "extract_status": "extracted",
                            "word_count": 120,
                            "cleaned_full_text": fact,
                            "excerpt": fact,
                            "quotes": [],
                            "error": None,
                        }
                    ],
                    "facts": [fact],
                    "quotes": [],
                    "timeline": [f"2026-05-26：{title}"],
                    "worthiness": {"worth_to_brief": True, "reason": "该事件值得纳入今日速递。"},
                    "last_error": None,
                    "article_writing_guide": "Guide text",
                }
            )
        _write_json(state_file, state)

        response = client.post("/api/admin/briefs/daily-digest?triggered_by=dashboard")

        assert response.status_code == 200
        payload = response.json()["item"]
        assert payload["title"].startswith("今日科技速递")
        assert payload["brief_level"] == "rule"
        assert payload["workflow_mode"] == "traditional"
        assert payload["stage"] == "prepared"
        assert payload["wechat_editor_url"] is None
        assert "## 1. 华为发布 AI DC 全栈方案" in payload["wechat_markdown"]
        assert "## 2. OpenAI 推出企业管理更新" in payload["wechat_markdown"]
        assert "## 3. 国产芯片工具链更新" in payload["wechat_markdown"]
        assert "## 4. 三星 PCIe Gen6 固态硬盘上线官网" in payload["wechat_markdown"]
        assert "## 5. 雷鸟发布 V4 AI 拍摄眼镜" in payload["wechat_markdown"]

        refreshed = json.loads(state_file.read_text(encoding="utf-8"))
        assert len(refreshed["briefs"]) == 1
        assert all(item.get("brief_id") == payload["id"] for item in refreshed["intel_events"])
        assert all(item.get("brief_status") == "prepared" for item in refreshed["intel_events"])
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_manual_daily_digest_endpoint_requires_five_qualified_events() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)
        state_file = temp_dir / "data" / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["automation_mode"] = "radar_and_draft"
        state["runtime_plan"] = {
            "launch_mode": "interval_now",
            "interval_minutes": 30,
            "timezone": "Asia/Shanghai",
            "work_scope": "collect_events_alerts",
            "delivery_mode": "immediate",
            "admission_strategy": "balanced",
            "batch_limit": 5,
            "admission_filters": {
                "require_watchlisted": False,
                "require_entity_match": False,
                "min_source_count": 0,
                "min_fulltext_count": 1,
                "breakout_only": False,
                "exclude_existing_brief": True,
                "exclude_synced_brief": True,
            },
        }
        state["briefs"] = []
        state["intel_events"] = [
            {
                "id": "evt-daily-api-single",
                "title": "唯一可写事件",
                "summary": "只有一条可写事件。",
                "representative_link": "https://example.com/single",
                "representative_source_name": "Example",
                "representative_discovery_item_id": "disc-single",
                "discovery_item_ids": ["disc-single"],
                "source_keys": ["rss-openai"],
                "source_names": ["Example"],
                "platforms": ["rss"],
                "platform_count": 1,
                "source_count": 2,
                "member_count": 1,
                "story_count": 1,
                "member_delta": 0,
                "platform_delta": 0,
                "published_at": "2026-05-26T10:00:00+08:00",
                "latest_collected_at": "2026-05-26T10:05:00+08:00",
                "first_seen_at": "2026-05-26T10:05:00+08:00",
                "last_seen_at": "2026-05-26T10:05:00+08:00",
                "tags": ["ai"],
                "anchor_tokens": ["ai"],
                "velocity_score": 80.0,
                "coverage_score": 70.0,
                "freshness_score": 90.0,
                "composite_score": 90.0,
                "velocity_details": {},
                "alert_state": "breakout",
                "change_state": "new_event",
                "alert_reason": "",
                "entity_ids": [],
                "entity_names": ["唯一"],
                "watchlisted": False,
                "ignored": False,
                "deep_dive_id": "dd-daily-api-single",
                "brief_id": None,
                "deep_dive_status": "ready",
                "brief_status": None,
                "worth_to_brief": True,
                "worth_reason": "有明确事实和来源。",
            }
        ]
        state["event_deep_dives"] = [
            {
                "id": "dd-daily-api-single",
                "event_id": "evt-daily-api-single",
                "status": "ready",
                "started_at": "2026-05-26T10:00:00+08:00",
                "finished_at": "2026-05-26T10:01:00+08:00",
                "updated_at": "2026-05-26T10:01:00+08:00",
                "attempted_count": 1,
                "success_count": 1,
                "failed_count": 0,
                "resolved_evidence_pack": [],
                "full_text_sources": [],
                "sources": [
                    {
                        "source_key": "example",
                        "source_name": "Example",
                        "original_link": "https://example.com/single",
                        "canonical_link": "https://example.com/single",
                        "title": "唯一可写事件",
                        "published_at": "2026-05-26T10:00:00+08:00",
                        "fetch_status": "fetched",
                        "extract_status": "extracted",
                        "word_count": 120,
                        "cleaned_full_text": "只有一条可写事件。",
                        "excerpt": "只有一条可写事件。",
                        "quotes": [],
                        "error": None,
                    }
                ],
                "facts": ["只有一条可写事件。"],
                "quotes": [],
                "timeline": [],
                "worthiness": {"worth_to_brief": True, "reason": "该事件值得观察。"},
                "last_error": None,
                "article_writing_guide": "Guide text",
            }
        ]
        _write_json(state_file, state)

        response = client.post("/api/admin/briefs/daily-digest?triggered_by=dashboard")

        assert response.status_code == 400
        assert "必须由 5 条合格事件组成" in response.json()["detail"]
        refreshed = json.loads(state_file.read_text(encoding="utf-8"))
        assert refreshed["briefs"] == []
        assert refreshed["intel_events"][0].get("brief_id") is None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_create_agent_article_still_saves_into_shared_briefs() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        response = client.post(
            "/api/admin/agent/articles",
            json={
                "event_id": "evt-1",
                "title": "OpenAI Health 正式发布，医疗 AI 商业化进入新阶段",
                "article_markdown": "# 标题\n\n正文",
                "one_line": "一句话总结",
                "why_it_matters": "因为行业意义明确",
                "facts": ["事实 A"],
                "quotes": ["引文 A"],
                "timeline": ["时间 A"],
                "entity_names": ["OpenAI"],
                "source_links": ["https://example.com/source-1"],
                "risk_notes": ["风险 A"],
                "publish_to_wechat_draft": False,
                "triggered_by": "agent",
                "driver_label": "codex",
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["item"]["title"].startswith("OpenAI Health 正式发布")
        assert payload["item"]["brief_level"] == "article"

        briefs_response = client.get("/api/admin/briefs?q=商业化")
        assert briefs_response.status_code == 200
        briefs_payload = briefs_response.json()
        assert briefs_payload["total"] == 1
        assert briefs_payload["items"][0]["title"].startswith("OpenAI Health 正式发布")
        assert briefs_payload["items"][0]["brief_level"] == "article"

        all_briefs_response = client.get("/api/admin/briefs?page=1&page_size=20")
        assert all_briefs_response.status_code == 200
        all_briefs_payload = all_briefs_response.json()
        titles = [item["title"] for item in all_briefs_payload["items"]]
        levels = {item["title"]: item["brief_level"] for item in all_briefs_payload["items"]}
        assert "OpenAI Health 正式发布" in titles
        assert any(title.startswith("OpenAI Health 正式发布，医疗 AI 商业化进入新阶段") for title in titles)
        assert levels["OpenAI Health 正式发布"] == "enhanced"
        agent_article_title = next(title for title in titles if title.startswith("OpenAI Health 正式发布，医疗 AI 商业化进入新阶段"))
        assert levels[agent_article_title] == "article"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_abandon_agent_workflow_endpoint_marks_session_abandoned() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)
        state_file = temp_dir / "data" / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        state["agent_workflows"] = [
            {
                "workflow_session_id": "agentwf-api-1",
                "status": "failed",
                "current_step": "article_saved",
                "event_id": "evt-1",
                "material_brief_id": None,
                "article_brief_id": "brief-1",
                "target_platforms": ["wechat"],
                "last_error": "上传失败",
                "started_at": "2026-05-13T10:00:00+08:00",
                "updated_at": "2026-05-13T10:01:00+08:00",
                "finished_at": None,
            }
        ]
        _write_json(state_file, state)

        response = client.post("/api/admin/agent/workflows/agentwf-api-1/abandon?triggered_by=dashboard")

        assert response.status_code == 200
        payload = response.json()
        assert payload["item"]["workflow_session_id"] == "agentwf-api-1"
        assert payload["item"]["status"] == "abandoned"
        assert payload["item"]["finished_at"]

        workflows_response = client.get("/api/admin/agent/workflows")
        assert workflows_response.status_code == 200
        assert workflows_response.json()["items"][0]["status"] == "abandoned"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
