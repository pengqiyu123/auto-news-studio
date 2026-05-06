from copy import deepcopy
from pathlib import Path
import tempfile
import shutil
import sys
import types

import pytest

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

    class _OpenAI:
        def __init__(self, *args, **kwargs) -> None:
            pass

    openai_stub.APIConnectionError = _OpenAIError
    openai_stub.APITimeoutError = _OpenAIError
    openai_stub.AuthenticationError = _OpenAIError
    openai_stub.BadRequestError = _OpenAIError
    openai_stub.InternalServerError = _OpenAIError
    openai_stub.NotFoundError = _OpenAIError
    openai_stub.OpenAI = _OpenAI
    openai_stub.RateLimitError = _OpenAIError
    sys.modules["openai"] = openai_stub

from backend.app.models import AgentArticlePayload
from backend.app.store import StudioStore


def _make_store_and_state() -> tuple[StudioStore, dict, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="agent-guard-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    state = store._upgrade_state(store._read())
    state["intel_events"] = [
        {
            "id": "evt-1",
            "title": "Test Event",
            "summary": "summary",
            "alert_state": "watch",
            "entity_names": [],
            "entity_ids": [],
            "brief_id": None,
        }
    ]
    state["event_deep_dives"] = [
        {
            "id": "dd-1",
            "event_id": "evt-1",
            "status": "ready",
            "sources": [],
            "worthiness": {"reason": "worth watching"},
            "updated_at": "2026-05-06T00:00:00+08:00",
        }
    ]
    return store, state, temp_root


def test_agent_article_upload_rejected_while_scheduler_running(monkeypatch: pytest.MonkeyPatch) -> None:
    store, state, temp_root = _make_store_and_state()
    state["runtime"]["scheduler_running"] = True
    state["runtime"]["control_state"] = "running"
    state["runtime"]["current_cycle"] = "collecting"
    state["runtime"]["automation_run"] = {
        "status": "running",
        "stage": "collecting",
        "heartbeat_at": "2026-05-06T17:40:00+08:00",
    }

    monkeypatch.setattr(store, "_read", lambda: deepcopy(state))
    monkeypatch.setattr(store, "_write", lambda payload: None)

    payload = AgentArticlePayload(
        event_id="evt-1",
        title="Agent Article",
        article_markdown="# Agent Article\n\nbody",
        publish_to_wechat_draft=True,
        triggered_by="agent",
    )

    with pytest.raises(ValueError, match="当前自动调度器正在运行"):
        store.create_agent_article(payload)
    shutil.rmtree(temp_root, ignore_errors=True)


def test_agent_cannot_upload_rule_brief_via_traditional_draft_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    store, state, temp_root = _make_store_and_state()
    state["briefs"] = [
        {
            "id": "brief-rule-1",
            "event_id": "evt-1",
            "deep_dive_id": "dd-1",
            "brief_level": "rule",
            "stage": "prepared",
            "title": "Rule Brief",
            "one_line": "summary",
            "why_it_matters": "reason",
            "facts": [],
            "quotes": [],
            "timeline": [],
            "entity_names": [],
            "source_links": [],
            "risk_notes": [],
            "prompt_package_markdown": "pkg",
            "wechat_markdown": "# short brief",
            "wechat_html": "<h1>short brief</h1>",
            "updated_at": "2026-05-06T00:00:00+08:00",
        }
    ]

    monkeypatch.setattr(store, "_read", lambda: deepcopy(state))
    monkeypatch.setattr(store, "_write", lambda payload: None)

    with pytest.raises(ValueError, match="Agent 模式禁止上传传统简报"):
        store.sync_brief_wechat_draft("brief-rule-1", triggered_by="agent")
    shutil.rmtree(temp_root, ignore_errors=True)
