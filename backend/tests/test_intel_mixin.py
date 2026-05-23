from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import types

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

from backend.app.store import get_studio_store_class
from backend.app.store_mixins import IntelMixin

StudioStore = get_studio_store_class()


def _make_store() -> tuple[StudioStore, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="intel-mixin-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    return store, temp_root


def test_studio_store_intel_methods_are_bound_from_mixin() -> None:
    store, temp_root = _make_store()
    try:
        assert StudioStore.get_dashboard is IntelMixin.get_dashboard
        assert StudioStore.get_intel_summary is IntelMixin.get_intel_summary
        assert StudioStore.list_intel_events is IntelMixin.list_intel_events
        assert StudioStore.watchlist_event is IntelMixin.watchlist_event
        assert StudioStore.update_entity_watchlist is IntelMixin.update_entity_watchlist
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_watchlist_and_ignore_event_mutate_runtime_projection() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["intel_events"] = [
            {
                "id": "evt-1",
                "title": "示例事件",
                "summary": "摘要",
                "representative_link": "https://example.com/evt-1",
                "representative_source_name": "Example",
                "representative_discovery_item_id": "disc-1",
                "discovery_item_ids": ["disc-1"],
                "source_keys": ["example"],
                "source_names": ["Example"],
                "platforms": ["web"],
                "platform_count": 1,
                "source_count": 1,
                "member_count": 1,
                "story_count": 1,
                "member_delta": 0,
                "platform_delta": 0,
                "published_at": "2026-05-12T09:00:00+08:00",
                "latest_collected_at": "2026-05-12T09:10:00+08:00",
                "first_seen_at": "2026-05-12T09:00:00+08:00",
                "last_seen_at": "2026-05-12T09:10:00+08:00",
                "tags": [],
                "anchor_tokens": [],
                "velocity_score": 20,
                "coverage_score": 10,
                "freshness_score": 30,
                "audience_fit_score": 55,
                "composite_score": 25,
                "velocity_details": {},
                "alert_state": "watch",
                "change_state": "new_event",
                "alert_reason": "",
                "entity_ids": ["entity-1"],
                "entity_names": ["OpenAI"],
                "watchlisted": False,
                "ignored": False,
            }
        ]
        state["normalized_items"] = [{"event_id": "evt-1", "title": "示例事件"}]
        store._write(state)

        watched = store.watchlist_event("evt-1")
        assert watched.watchlisted is True
        assert watched.ignored is False

        ignored = store.ignore_event("evt-1")
        assert ignored.ignored is True
        assert ignored.watchlisted is False

        latest_state = store._upgrade_state(store._read())
        assert latest_state["intel_events"][0]["ignored"] is True
        assert latest_state["intel_events"][0]["watchlisted"] is False
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_update_entity_watchlist_normalizes_and_deduplicates_items() -> None:
    store, temp_root = _make_store()
    try:
        items = store.update_entity_watchlist(
            [
                {"entity_name": "OpenAI", "entity_type": "company", "watchlisted": True},
                {"entity_name": "OpenAI", "entity_type": "company", "watchlisted": True},
                {"entity_name": "微软", "entity_type": "company", "watchlisted": True},
            ]
        )

        assert len(items) == 2
        assert {item.entity_name for item in items} == {"OpenAI", "微软"}
        assert all(item.watchlisted is True for item in items)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
