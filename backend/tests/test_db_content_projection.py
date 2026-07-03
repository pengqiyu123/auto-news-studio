from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import types

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
from backend.app.db.content_projection import sync_content_projection_from_state
from backend.app.db import models  # noqa: F401


def _make_sqlite_url() -> tuple[str, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="db-content-projection-"))
    sqlite_path = temp_dir / "content.sqlite3"
    return f"sqlite:///{sqlite_path}", temp_dir


def _bootstrap_db(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)
    engine.dispose()


def _state() -> dict:
    return {
        "event_deep_dives": [
            {
                "id": "dd-1",
                "event_id": "evt-1",
                "status": "ready",
                "started_at": "2026-05-24T09:00:00+00:00",
                "finished_at": "2026-05-24T09:02:00+00:00",
                "updated_at": "2026-05-24T09:02:00+00:00",
                "attempted_count": 1,
                "success_count": 1,
                "failed_count": 0,
                "resolved_evidence_pack": [],
                "sources": [
                    {
                        "source_key": "rss-openai",
                        "source_name": "RSS OpenAI",
                        "original_link": "https://example.com/source-1",
                        "canonical_link": "https://example.com/source-1",
                        "title": "Source title",
                        "published_at": "2026-05-24T08:00:00+00:00",
                        "fetch_status": "fetched",
                        "extract_status": "extracted",
                        "word_count": 600,
                        "cleaned_full_text": "full text body",
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
                "wechat_markdown": "# title\n\nbody",
                "wechat_html": "<h1>title</h1><p>body</p>",
                "douyin_title": "title",
                "douyin_summary": "douyin summary",
                "douyin_markdown": "# title\n\nbody",
                "delivery_status": "idle",
                "delivery_attempt_count": 0,
                "updated_at": "2026-05-24T09:03:00+00:00",
                "driver_label": "test",
                "record_status": "local_only",
                "workflow_mode": "agent",
                "workflow_session_id": "wf-1",
                "read_count": 0,
                "like_count": 0,
                "share_count": 0,
                "recommend_count": 0,
                "comment_count": 0,
                "highlight_count": 0,
                "tip_amount": "0.00",
                "reprint_count": 0,
            }
        ],
    }


def test_content_projection_persists_deep_dive_and_brief_assets() -> None:
    database_url, temp_dir = _make_sqlite_url()
    _bootstrap_db(database_url)
    try:
        counts = sync_content_projection_from_state(_state(), database_url=database_url)
        engine = create_engine(database_url, future=True)
        with engine.connect() as conn:
            deep_dive_records = conn.execute(text("select count(*) from deep_dive_records")).scalar_one()
            deep_dive_documents = conn.execute(text("select count(*) from deep_dive_documents")).scalar_one()
            brief_records = conn.execute(text("select count(*) from brief_records")).scalar_one()
        engine.dispose()

        assert counts["deep_dive_records"] == 1
        assert counts["deep_dive_documents"] == 1
        assert counts["brief_records"] == 1
        assert deep_dive_records == 1
        assert deep_dive_documents == 1
        assert brief_records == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_content_projection_bootstrap_schema_on_sqlite() -> None:
    database_url, temp_dir = _make_sqlite_url()
    try:
        _bootstrap_db(database_url)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_content_projection_bounds_document_ids_for_long_links() -> None:
    database_url, temp_dir = _make_sqlite_url()
    _bootstrap_db(database_url)
    try:
        state = _state()
        source = state["event_deep_dives"][0]["sources"][0]
        source["canonical_link"] = "https://example.com/" + ("a" * 600)
        source["original_link"] = source["canonical_link"]

        counts = sync_content_projection_from_state(state, database_url=database_url)

        engine = create_engine(database_url, future=True)
        with engine.connect() as conn:
            row = conn.execute(text("select id, length(id) from deep_dive_documents")).one()
        engine.dispose()

        assert counts["deep_dive_documents"] == 1
        assert row[0].startswith("dd-1:0:")
        assert row[1] < 64
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_content_projection_backfill_is_stable_across_repeated_runs() -> None:
    database_url, temp_dir = _make_sqlite_url()
    _bootstrap_db(database_url)
    try:
        first_counts = sync_content_projection_from_state(_state(), database_url=database_url)
        second_counts = sync_content_projection_from_state(_state(), database_url=database_url)

        engine = create_engine(database_url, future=True)
        with engine.connect() as conn:
            deep_dive_records = conn.execute(text("select count(*) from deep_dive_records")).scalar_one()
            deep_dive_documents = conn.execute(text("select count(*) from deep_dive_documents")).scalar_one()
            brief_records = conn.execute(text("select count(*) from brief_records")).scalar_one()
        engine.dispose()

        assert first_counts == second_counts
        assert deep_dive_records == 1
        assert deep_dive_documents == 1
        assert brief_records == 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_content_asset_migration_accepts_existing_equivalent_indexes() -> None:
    database_url, temp_dir = _make_sqlite_url()
    engine = create_engine(database_url, future=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    create table alembic_version (
                        version_num varchar(32) not null
                    )
                    """
                )
            )
            conn.execute(text("insert into alembic_version (version_num) values ('20260524_0001')"))
            conn.execute(
                text(
                    """
                    create table deep_dive_records (
                        id varchar(64) primary key,
                        event_id varchar(64) not null,
                        status varchar(32) not null default 'pending',
                        started_at datetime null,
                        finished_at datetime null,
                        updated_at datetime not null,
                        attempted_count integer not null default 0,
                        success_count integer not null default 0,
                        failed_count integer not null default 0,
                        resolved_evidence_pack_json json not null default '[]',
                        facts_json json not null default '[]',
                        quotes_json json not null default '[]',
                        timeline_json json not null default '[]',
                        worthiness_json json not null default '{}',
                        last_error text null,
                        article_writing_guide text not null default ''
                    )
                    """
                )
            )
            conn.execute(text("create index legacy_deep_dive_event_idx on deep_dive_records (event_id)"))
            conn.execute(text("create index legacy_deep_dive_updated_idx on deep_dive_records (updated_at)"))
        engine.dispose()

        old_env_database_url = os.environ.get("DATABASE_URL")
        try:
            os.environ["DATABASE_URL"] = database_url
            from alembic.config import Config
            from alembic import command

            command.upgrade(Config(str(REPO_ROOT / "alembic.ini")), "head")
        finally:
            if old_env_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_env_database_url

        engine = create_engine(database_url, future=True)
        with engine.connect() as conn:
            version = conn.execute(text("select version_num from alembic_version")).scalar_one()
            deep_dive_documents = conn.execute(text("select name from sqlite_master where type='table' and name='deep_dive_documents'")).scalar_one()
            brief_records = conn.execute(text("select name from sqlite_master where type='table' and name='brief_records'")).scalar_one()
            topic_models = conn.execute(text("select name from sqlite_master where type='table' and name='topic_models'")).scalar_one()
            event_relations = conn.execute(text("select name from sqlite_master where type='table' and name='event_relations'")).scalar_one()
            analysis_feedback = conn.execute(text("select name from sqlite_master where type='table' and name='analysis_feedback'")).scalar_one()
            analysis_reports = conn.execute(text("select name from sqlite_master where type='table' and name='analysis_reports'")).scalar_one()
        engine.dispose()

        assert version == "20260524_0005"
        assert deep_dive_documents == "deep_dive_documents"
        assert brief_records == "brief_records"
        assert topic_models == "topic_models"
        assert event_relations == "event_relations"
        assert analysis_feedback == "analysis_feedback"
        assert analysis_reports == "analysis_reports"
    finally:
        engine.dispose()
        shutil.rmtree(temp_dir, ignore_errors=True)
