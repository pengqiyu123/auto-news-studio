from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_state() -> dict:
    return {
        "automation_mode": "radar_only",
        "automation_mode_definitions": [],
        "automation_profiles": [],
        "sources": [],
        "raw_items": [],
        "discovery_items": [],
        "intel_events": [],
        "event_snapshots": [],
        "intel_alerts": [],
        "intel_event_history": [],
        "intel_alert_history": [],
        "event_deep_dives": [],
        "briefs": [],
        "agent_html_targets": [],
        "agent_html_runs": [],
        "agent_html_discovery_items": [],
        "agent_html_events": [],
        "agent_html_event_snapshots": [],
        "agent_html_event_history": [],
        "agent_html_documents": [],
        "agent_html_document_revisions": [],
        "normalized_items": [],
        "publish_tasks": [],
        "jobs": [],
        "logs": [],
        "reference_projects": [],
        "runtime_plan": {},
        "notifications": {"webhook": {"enabled": False, "url": "", "secret": "", "events": ["breakout"]}, "delivery_log": []},
        "app_meta": {"dismissed_update_version": None, "last_update_check": None},
        "channels": {"wechat": {}},
        "browser": {"wechat": {}},
        "llm": {"profiles": [], "providers": [], "tasks": [], "usage_today": {}},
        "settings": {"max_workers": 4, "tavily_api_key": ""},
    }


def _build_client(tmp_root: Path) -> TestClient:
    state_file = tmp_root / "state.json"
    config_file = tmp_root / "config" / "settings.json"
    _write_json(state_file, _build_state())
    _write_json(config_file, {"sources": {"overrides": {}}, "llm": {"profiles": [], "providers": [], "tasks": []}})

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

            def title(self) -> str:
                return "Stub Title"

        readability_stub.Document = _Document
        sys.modules["readability"] = readability_stub
    if "openai" not in sys.modules:
        openai_stub = types.ModuleType("openai")
        class _OpenAIError(Exception):
            pass
        class _OpenAI:
            def __init__(self, *args, **kwargs) -> None:
                pass
        openai_stub.APIConnectionError = _OpenAIError
        openai_stub.APITimeoutError = _OpenAIError
        openai_stub.AuthenticationError = _OpenAIError
        openai_stub.BadRequestError = _OpenAIError
        openai_stub.InternalServerError = _OpenAIError
        openai_stub.NotFoundError = _OpenAIError
        openai_stub.RateLimitError = _OpenAIError
        openai_stub.OpenAI = _OpenAI
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
    return Path(tempfile.mkdtemp(prefix="agent-html-", dir=base))


def test_agent_html_target_crud_and_lists() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)

        create_response = client.post(
            "/api/admin/agent-html/targets",
            json={
                "brand": "OpenAI",
                "name": "OpenAI News",
                "entry_url": "https://openai.com/news/",
                "target_type": "newsroom",
                "discovery_rules": {
                    "link_selector": "",
                    "link_allow_patterns": ["/news/"],
                    "link_deny_patterns": ["/index/"],
                },
            },
        )
        assert create_response.status_code == 200
        created = create_response.json()["item"]
        assert created["brand"] == "OpenAI"

        list_response = client.get("/api/admin/agent-html/targets")
        assert list_response.status_code == 200
        listed_targets = list_response.json()["items"]
        assert any(item["id"] == created["id"] for item in listed_targets)

        patch_response = client.patch(
            f"/api/admin/agent-html/targets/{created['id']}",
            json={"enabled": False, "tags": ["ai", "official"]},
        )
        assert patch_response.status_code == 200
        updated = patch_response.json()["item"]
        assert updated["enabled"] is False
        assert updated["tags"] == ["ai", "official"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_agent_html_reextract_document_endpoint() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        client = _build_client(temp_dir)
        import backend.app.store as store_module

        state = json.loads(store_module.DATA_FILE.read_text(encoding="utf-8"))
        state["agent_html_documents"] = [
            {
                "id": "ahdoc-1",
                "target_id": "aht-1",
                "canonical_url": "https://example.com/post-1",
                "current_revision_id": "ahrv-1",
                "title": "Old title",
                "published_at": "2026-05-07T10:00:00+00:00",
                "latest_seen_at": "2026-05-07T10:00:00+00:00",
                "current_content_hash": "old-hash",
                "word_count": 10,
                "extractor": "extracted",
                "first_seen_at": "2026-05-07T10:00:00+00:00",
                "updated_at": "2026-05-07T10:00:00+00:00",
            }
        ]
        state["agent_html_document_revisions"] = [
            {
                "id": "ahrv-1",
                "document_id": "ahdoc-1",
                "run_id": "ahr-1",
                "source_url": "https://example.com/post-1",
                "title": "Old title",
                "content_text": "old text",
                "excerpt": "old text",
                "content_hash": "old-hash",
                "word_count": 10,
                "extractor": "extracted",
                "published_at": "2026-05-07T10:00:00+00:00",
                "fetched_at": "2026-05-07T10:00:00+00:00",
                "revision_index": 1,
                "change_summary": "initial_capture",
            }
        ]
        store_module.DATA_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        def _fake_fetch_and_extract_link(item: dict, *, timeout_seconds: float) -> dict:
            return {
                "canonical_link": item["link"],
                "title": "New title",
                "published_at": "2026-05-07T10:00:00+00:00",
                "fetch_status": "fetched",
                "extract_status": "extracted",
                "word_count": 500,
                "cleaned_full_text": "new content text " * 30,
                "excerpt": "new content text",
                "error": None,
            }

        store_module.fetch_and_extract_link = _fake_fetch_and_extract_link

        response = client.post("/api/admin/agent-html/documents/ahdoc-1/reextract")
        assert response.status_code == 200
        payload = response.json()["item"]
        assert payload["id"] == "ahdoc-1"
        assert payload["title"] == "New title"
        assert len(payload["revisions"]) == 2
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
