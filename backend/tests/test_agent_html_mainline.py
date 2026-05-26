from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import types


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _prepare_import_stubs() -> None:
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


def _make_repo_temp_dir() -> Path:
    base = Path.cwd() / "runtime" / "pytest-temp"
    base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="agent-html-mainline-", dir=base))


def _configure_store(temp_dir: Path):
    _prepare_import_stubs()
    import backend.app.store.reference_projects as reference_projects
    import backend.app.store as store_module
    import backend.app.store.base as store_base

    state_file = temp_dir / "state.json"
    config_file = temp_dir / "config" / "settings.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps({"sources": {"overrides": {}}, "llm": {"profiles": [], "providers": [], "tasks": []}}, ensure_ascii=False), encoding="utf-8")

    store_base.DATA_FILE = state_file
    store_base.CONFIG_DIR = config_file.parent
    store_base.CONFIG_FILE = config_file
    store_module.DATA_FILE = state_file
    store_module.CONFIG_FILE = config_file
    reference_projects.REFERENCES_ROOT = temp_dir / "references"
    reference_projects.REFERENCE_FILE = reference_projects.REFERENCES_ROOT / "reference_projects.json"
    reference_projects.BORROW_MAP_FILE = reference_projects.REFERENCES_ROOT / "borrow_map.json"

    store = store_module.StudioStore(data_file=state_file)
    return store, store_module


def test_sync_agent_html_into_mainline_projects_anthropic_document_into_raw_items() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        store, store_module = _configure_store(temp_dir)
        target = store.create_agent_html_target(
            store_module.AgentHtmlTargetCreatePayload(
                brand="Anthropic",
                name="Anthropic News",
                entry_url="https://www.anthropic.com/news",
                target_type="newsroom",
                discovery_rules={
                    "link_allow_patterns": ["/news/"],
                    "link_deny_patterns": ["/news$"],
                },
            )
        )

        def _fake_run_agent_html_target(target_id: str, *, triggered_by: str = "dashboard"):
            with store._lock:
                state = store._upgrade_state(store._read())
                state["agent_html_documents"] = [
                    {
                        "id": "ahdoc-1",
                        "target_id": target_id,
                        "canonical_url": "https://www.anthropic.com/news/claude-opus-4-7",
                        "current_revision_id": "ahrv-1",
                        "title": "Introducing Claude Opus 4.7 \\ Anthropic",
                        "published_at": "2026-05-07T10:00:00+00:00",
                        "latest_seen_at": "2026-05-07T10:00:00+00:00",
                        "current_content_hash": "hash-1",
                        "word_count": 1800,
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
                        "source_url": "https://www.anthropic.com/news/claude-opus-4-7",
                        "title": "Introducing Claude Opus 4.7 \\ Anthropic",
                        "content_text": "Anthropic launches Claude Opus 4.7 with enterprise improvements " * 40,
                        "excerpt": "Anthropic launches Claude Opus 4.7",
                        "content_hash": "hash-1",
                        "word_count": 1800,
                        "extractor": "extracted",
                        "published_at": "2026-05-07T10:00:00+00:00",
                        "fetched_at": "2026-05-07T10:05:00+00:00",
                        "revision_index": 1,
                        "change_summary": "initial_capture",
                    }
                ]
                store._write(state)
            return store_module.AgentHtmlRun(
                id="ahr-1",
                target_id=target_id,
                status="completed",
                started_at="2026-05-07T10:00:00+00:00",
                finished_at="2026-05-07T10:05:00+00:00",
                discovered_count=1,
                new_discovery_count=1,
                updated_discovery_count=0,
                fetched_count=1,
                extracted_count=1,
                failed_count=0,
                list_fetch_status="fetched",
                ai_fallback_used=False,
                error_summary=None,
                triggered_by=triggered_by,
                created_at="2026-05-07T10:00:00+00:00",
                updated_at="2026-05-07T10:05:00+00:00",
            )

        store.run_agent_html_target = _fake_run_agent_html_target  # type: ignore[method-assign]

        response = store.sync_agent_html_into_mainline([target.id], triggered_by="test")
        state = store._read_live()
        raw_items = [item for item in state.get("raw_items", []) if item.get("source_key") == f"html-{target.id}"]

        assert response.raw_count >= 1
        assert len(raw_items) == 1
        assert raw_items[0]["title"] == "Introducing Claude Opus 4.7 \\ Anthropic"
        assert raw_items[0]["metadata"]["collector"] == "agent_html"
        assert state.get("normalized_items")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_agent_html_candidate_filter_blocks_samsung_media_and_shop_like_pages() -> None:
    temp_dir = _make_repo_temp_dir()
    try:
        store, store_module = _configure_store(temp_dir)
        target = {"target_type": "newsroom"}
        blocked = {
            "link": "https://news.samsung.com/global/medialibrary/global/album/170",
            "title": "Galaxy S26 Series - Samsung Newsroom Global Media Library",
        }
        allowed = {
            "link": "https://www.anthropic.com/news/claude-opus-4-7",
            "title": "Introducing Claude Opus 4.7",
        }

        assert store._agent_html_is_article_candidate(blocked, target) is False
        assert store._agent_html_is_article_candidate(allowed, target) is True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
