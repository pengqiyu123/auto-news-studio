from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
import tempfile
import types

from sqlalchemy import create_engine, text

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

from backend.app.db.base import Base
from backend.app.db.ingest_projection import sync_ingest_projection_from_state
from backend.app.db.content_projection import sync_content_projection_from_state
from backend.app.db.read_models import get_brief_from_db, list_intel_events_from_db
from backend.app.db import models  # noqa: F401


UTC = timezone.utc


def _make_sqlite_url() -> tuple[str, Path]:
    temp_file = Path(tempfile.mkdtemp(prefix="db-ingest-projection-")) / "projection.sqlite3"
    return f"sqlite:///{temp_file}", temp_file


def _bootstrap_db(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)


def _state(raw_id: str, captured_at: str, history_id: str) -> dict:
    return {
        "sources": [
            {
                "key": "rss-openai",
                "name": "RSS OpenAI",
                "kind": "rss",
                "driver": "legacy_rss",
                "platform": "rss",
                "enabled": True,
                "schedule": "*/30 * * * *",
                "interval_minutes": 30,
                "priority": 5,
                "weight": 0.7,
                "auth": {},
                "url": "https://example.com/rss.xml",
                "tags": ["ai"],
                "capabilities": [],
                "origin_repo": "test",
                "origin_license": "",
                "health_status": "healthy",
                "health_detail": "ok",
                "item_count": 1,
                "last_synced_at": "2026-05-24T09:00:00+00:00",
                "last_error": None,
                "updated_at": "2026-05-24T09:00:00+00:00",
            }
        ],
        "raw_items": [
            {
                "id": raw_id,
                "source_key": "rss-openai",
                "title": f"title-{raw_id}",
                "summary": "summary",
                "content": "content",
                "link": f"https://example.com/{raw_id}",
                "canonical_link": f"https://example.com/{raw_id}",
                "dedupe_key": raw_id,
                "source_native_id": raw_id,
                "published_at": "2026-05-24T08:00:00+00:00",
                "collected_at": "2026-05-24T09:00:00+00:00",
                "score": 1.0,
                "tags": ["ai"],
                "metadata": {"collector": "test"},
            }
        ],
        "discovery_items": [
            {
                "id": f"disc-{raw_id}",
                "raw_item_id": raw_id,
                "source_key": "rss-openai",
                "source_name": "RSS OpenAI",
                "source_kind": "rss",
                "platform": "rss",
                "title": f"title-{raw_id}",
                "summary": "summary",
                "content": "content",
                "link": f"https://example.com/{raw_id}",
                "canonical_link": f"https://example.com/{raw_id}",
                "dedupe_key": raw_id,
                "source_native_id": raw_id,
                "title_tokens": ["openai"],
                "anchor_tokens": ["openai"],
                "published_at": "2026-05-24T08:00:00+00:00",
                "collected_at": "2026-05-24T09:00:00+00:00",
                "tags": ["ai"],
                "engagement_score": 1.0,
                "item_state": "new_item",
                "entity_ids": ["openai"],
                "entity_names": ["OpenAI"],
                "metadata": {},
            }
        ],
        "intel_events": [
            {
                "id": "evt-1",
                "title": "OpenAI update",
                "summary": "summary",
                "representative_link": "https://example.com/evt-1",
                "representative_source_name": "RSS OpenAI",
                "representative_discovery_item_id": f"disc-{raw_id}",
                "discovery_item_ids": [f"disc-{raw_id}"],
                "source_keys": ["rss-openai"],
                "source_names": ["RSS OpenAI"],
                "platforms": ["rss"],
                "platform_count": 1,
                "source_count": 1,
                "member_count": 1,
                "story_count": 1,
                "member_delta": 0,
                "platform_delta": 0,
                "published_at": "2026-05-24T08:00:00+00:00",
                "latest_collected_at": "2026-05-24T09:00:00+00:00",
                "first_seen_at": "2026-05-24T09:00:00+00:00",
                "last_seen_at": "2026-05-24T09:00:00+00:00",
                "tags": ["ai"],
                "anchor_tokens": ["openai"],
                "velocity_score": 10.0,
                "coverage_score": 20.0,
                "freshness_score": 30.0,
                "audience_fit_score": 40.0,
                "composite_score": 25.0,
                "velocity_details": {},
                "alert_state": "watch",
                "change_state": "new_event",
                "alert_reason": "reason",
                "entity_ids": ["openai"],
                "entity_names": ["OpenAI"],
                "watchlisted": False,
                "ignored": False,
                "deep_dive_id": None,
                "brief_id": None,
                "deep_dive_status": None,
                "deep_dive_started_at": None,
                "deep_dive_finished_at": None,
                "deep_dive_updated_at": None,
                "brief_status": None,
                "deep_dive_summary": "",
                "worth_to_brief": False,
                "worth_reason": "",
            }
        ],
        "event_snapshots": [
            {
                "id": f"snap-{captured_at[-5:]}",
                "event_id": "evt-1",
                "captured_at": captured_at,
                "member_count": 1,
                "platform_count": 1,
                "source_count": 1,
                "velocity_score": 10.0,
                "coverage_score": 20.0,
                "freshness_score": 30.0,
                "audience_fit_score": 40.0,
                "composite_score": 25.0,
                "alert_state": "watch",
            }
        ],
        "intel_alerts": [],
        "intel_event_history": [
            {
                "history_id": history_id,
                "event_id": "evt-1",
                "title": "OpenAI update",
                "summary": "summary",
                "representative_link": "https://example.com/evt-1",
                "entity_ids": ["openai"],
                "entity_names": ["OpenAI"],
                "discovered_at": "2026-05-24T09:00:00+00:00",
                "last_seen_at": "2026-05-24T09:00:00+00:00",
                "expires_at": "2026-05-25T09:00:00+00:00",
                "status": "active",
                "latest_alert_state": "watch",
                "platform_count": 1,
                "source_count": 1,
                "member_count": 1,
                "member_delta": 0,
                "platform_delta": 0,
                "composite_score": 25.0,
            }
        ],
        "intel_alert_history": [],
    }


def test_ingest_projection_keeps_raw_and_snapshot_history_append_only() -> None:
    database_url, sqlite_path = _make_sqlite_url()
    _bootstrap_db(database_url)
    try:
        sync_ingest_projection_from_state(_state("raw-1", "2026-05-24T09:00:00+00:00", "evh-1"), database_url=database_url)
        sync_ingest_projection_from_state(_state("raw-2", "2026-05-24T10:00:00+00:00", "evh-1"), database_url=database_url)

        engine = create_engine(database_url, future=True)
        with engine.connect() as conn:
            raw_count = conn.execute(text("select count(*) from raw_items")).scalar_one()
            snapshot_count = conn.execute(text("select count(*) from event_snapshots")).scalar_one()
            event_history_count = conn.execute(text("select count(*) from intel_event_history")).scalar_one()
            current_discovery = conn.execute(text("select count(*) from discovery_items_current")).scalar_one()
        assert raw_count == 2
        assert snapshot_count == 1
        assert event_history_count == 1
        assert current_discovery == 1
    finally:
        engine.dispose()
        shutil.rmtree(sqlite_path.parent, ignore_errors=True)


def test_db_event_reads_resolve_latest_deep_dive_and_brief_links() -> None:
    database_url, sqlite_path = _make_sqlite_url()
    _bootstrap_db(database_url)
    try:
        state = _state("raw-1", "2026-05-24T09:00:00+00:00", "evh-1")
        state["intel_events"][0]["watchlisted"] = True
        sync_ingest_projection_from_state(state, database_url=database_url)
        content_state = {
            "event_deep_dives": [
                {
                    "id": "dd-1",
                    "event_id": "evt-1",
                    "status": "ready",
                    "started_at": "2026-05-24T09:01:00+00:00",
                    "finished_at": "2026-05-24T09:02:00+00:00",
                    "updated_at": "2026-05-24T09:02:00+00:00",
                    "attempted_count": 3,
                    "success_count": 2,
                    "failed_count": 1,
                    "resolved_evidence_pack": [{"source_key": "tavily"}],
                    "facts": ["fact 1"],
                    "quotes": ["quote 1"],
                    "timeline": ["timeline 1"],
                    "worthiness": {"reason": "worth it"},
                    "last_error": None,
                    "article_writing_guide": "guide",
                }
            ],
            "briefs": [
                {
                    "id": "brief-1",
                    "event_id": "evt-1",
                    "deep_dive_id": "dd-1",
                    "brief_level": "article",
                    "stage": "prepared",
                    "title": "OpenAI Brief",
                    "summary": "summary",
                    "one_line": "one line",
                    "why_it_matters": "why",
                    "facts": ["fact 1"],
                    "quotes": ["quote 1"],
                    "timeline": ["timeline 1"],
                    "entity_names": ["OpenAI"],
                    "source_links": ["https://example.com/source-1"],
                    "risk_notes": [],
                    "prompt_package_markdown": "pkg",
                    "douyin_prompt_package_markdown": "douyin-pkg",
                    "wechat_markdown": "# title",
                    "wechat_html": "<h1>title</h1>",
                    "douyin_title": "title",
                    "douyin_summary": "summary",
                    "douyin_markdown": "# title",
                    "updated_at": "2026-05-24T09:03:00+00:00",
                    "record_status": "local_only",
                    "workflow_mode": "traditional",
                }
            ],
        }
        sync_content_projection_from_state(content_state, database_url=database_url)

        items, total = list_intel_events_from_db(database_url=database_url, page=1, page_size=20)

        assert total == 1
        assert items[0].id == "evt-1"
        assert items[0].deep_dive_id == "dd-1"
        assert items[0].brief_id == "brief-1"
        assert items[0].deep_dive_status == "ready"
        assert items[0].brief_status == "prepared"
        assert items[0].deep_dive_summary
        assert items[0].worth_to_brief is True
    finally:
        shutil.rmtree(sqlite_path.parent, ignore_errors=True)


def test_db_brief_detail_read_returns_full_article_fields() -> None:
    database_url, sqlite_path = _make_sqlite_url()
    _bootstrap_db(database_url)
    try:
        sync_content_projection_from_state(
            {
                "event_deep_dives": [],
                "briefs": [
                    {
                        "id": "brief-1",
                        "event_id": "evt-1",
                        "deep_dive_id": "dd-1",
                        "brief_level": "article",
                        "stage": "prepared",
                        "title": "OpenAI Brief",
                        "summary": "summary",
                        "one_line": "one line",
                        "why_it_matters": "why",
                        "facts": ["fact 1"],
                        "quotes": ["quote 1"],
                        "timeline": ["timeline 1"],
                        "entity_names": ["OpenAI"],
                        "source_links": ["https://example.com/source-1"],
                        "risk_notes": [],
                        "prompt_package_markdown": "pkg",
                        "douyin_prompt_package_markdown": "douyin-pkg",
                        "wechat_markdown": "# title",
                        "wechat_html": "<h1>title</h1>",
                        "douyin_title": "title",
                        "douyin_summary": "summary",
                        "douyin_markdown": "# title",
                        "updated_at": "2026-05-24T09:03:00+00:00",
                        "record_status": "local_only",
                        "workflow_mode": "traditional",
                    }
                ],
            },
            database_url=database_url,
        )

        brief = get_brief_from_db(database_url=database_url, brief_id="brief-1")

        assert brief is not None
        assert brief["prompt_package_markdown"] == "pkg"
        assert brief["facts"] == ["fact 1"]
        assert brief["quotes"] == ["quote 1"]
        assert brief["timeline"] == ["timeline 1"]
    finally:
        shutil.rmtree(sqlite_path.parent, ignore_errors=True)
