from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import types
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
        def __init__(self, *args: Any, **kwargs: Any) -> None:
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
from backend.app.db.read_models import list_intel_alerts_from_db, list_intel_events_from_db
from backend.app.db import models  # noqa: F401
from backend.app.routes.common import set_store
from backend.app.store import get_studio_store_class

StudioStore = get_studio_store_class()


def _event(
    event_id: str,
    *,
    title: str,
    summary: str,
    entity_ids: list[Any],
    entity_names: list[Any],
    composite_score: float,
    velocity_score: float,
    coverage_score: float,
    freshness_score: float,
    member_delta: int,
    platform_delta: int,
    last_seen_at: str,
    alert_state: str = "watch",
    ignored: bool = False,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "title": title,
        "summary": summary,
        "representative_link": f"https://example.com/{event_id}",
        "representative_source_name": "RSS OpenAI",
        "representative_discovery_item_id": f"disc-{event_id}",
        "discovery_item_ids": [f"disc-{event_id}"],
        "source_keys": ["rss-openai"],
        "source_names": ["RSS OpenAI"],
        "platforms": ["rss"],
        "platform_count": 1 + platform_delta,
        "source_count": 1,
        "member_count": 1 + member_delta,
        "story_count": 1,
        "member_delta": member_delta,
        "platform_delta": platform_delta,
        "published_at": "2026-05-24T08:00:00+00:00",
        "latest_collected_at": last_seen_at,
        "first_seen_at": "2026-05-24T08:10:00+00:00",
        "last_seen_at": last_seen_at,
        "tags": ["ai"],
        "anchor_tokens": ["openai"],
        "velocity_score": velocity_score,
        "coverage_score": coverage_score,
        "freshness_score": freshness_score,
        "audience_fit_score": 1.0,
        "composite_score": composite_score,
        "velocity_details": {},
        "alert_state": alert_state,
        "change_state": "new_event",
        "alert_reason": "rule reason",
        "entity_ids": entity_ids,
        "entity_names": entity_names,
        "watchlisted": False,
        "ignored": ignored,
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


def _alert(alert_id: str, event: dict[str, Any], *, level: str = "rising") -> dict[str, Any]:
    return {
        "id": alert_id,
        "event_id": event["id"],
        "title": event["title"],
        "level": level,
        "reason": "速度得分突破阈值",
        "velocity_score": event["velocity_score"],
        "coverage_score": event["coverage_score"],
        "freshness_score": event["freshness_score"],
        "audience_fit_score": event["audience_fit_score"],
        "composite_score": event["composite_score"],
        "platform_count": event["platform_count"],
        "source_count": event["source_count"],
        "representative_link": event["representative_link"],
        "triggered_at": event["last_seen_at"],
        "entity_ids": event["entity_ids"],
        "entity_names": event["entity_names"],
    }


def _state() -> dict[str, Any]:
    openai_event = _event(
        "evt-openai",
        title="OpenAI model launch",
        summary="OpenAI launched a new model for editors.",
        entity_ids=[101],
        entity_names=["OpenAI"],
        composite_score=70,
        velocity_score=90,
        coverage_score=50,
        freshness_score=80,
        member_delta=2,
        platform_delta=1,
        last_seen_at="2026-05-24T09:00:00+00:00",
        alert_state="rising",
    )
    deepseek_event = _event(
        "evt-deepseek",
        title="DeepSeek product update",
        summary="DeepSeek shipped a quieter product update.",
        entity_ids=["deepseek"],
        entity_names=["DeepSeek"],
        composite_score=95,
        velocity_score=20,
        coverage_score=88,
        freshness_score=30,
        member_delta=4,
        platform_delta=0,
        last_seen_at="2026-05-24T08:00:00+00:00",
        alert_state="watch",
    )
    ignored_event = _event(
        "evt-ignored",
        title="Ignored rumor",
        summary="Ignored item",
        entity_ids=["openai"],
        entity_names=["OpenAI"],
        composite_score=99,
        velocity_score=99,
        coverage_score=99,
        freshness_score=99,
        member_delta=9,
        platform_delta=9,
        last_seen_at="2026-05-24T10:00:00+00:00",
        alert_state="breakout",
        ignored=True,
    )
    return {
        "sources": [],
        "raw_items": [],
        "discovery_items": [],
        "intel_events": [openai_event, deepseek_event, ignored_event],
        "event_snapshots": [],
        "intel_alerts": [_alert("alert-openai", openai_event), _alert("alert-deepseek", deepseek_event, level="watch")],
        "intel_event_history": [],
        "intel_alert_history": [],
        "event_deep_dives": [],
        "briefs": [],
        "settings": {
            "entity_watchlist": [
                {
                    "entity_id": "101",
                    "entity_name": "OpenAI",
                    "entity_type": "COMPANY",
                    "watchlisted": True,
                    "added_at": "2026-05-24T08:00:00+00:00",
                }
            ]
        },
        "logs": [],
        "browser": {"wechat": {}},
        "automation_mode_definitions": [],
        "automation_profiles": [],
        "runtime": {"control_state": "running"},
        "app_meta": {},
        "channels": {"wechat": {}},
        "publish_tasks": [],
        "notifications": {},
        "reference_projects": [],
    }


def _client_with_state(state: dict[str, Any]) -> TestClient:
    temp_root = Path(tempfile.mkdtemp(prefix="events-alerts-ux-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    upgraded = store._upgrade_state(store._read())
    upgraded.update(state)
    store._write(upgraded)

    import backend.app.main as main_module

    main_module.store = store
    set_store(store)
    return TestClient(main_module.app)


def _make_sqlite_url() -> tuple[str, Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="events-alerts-db-"))
    return f"sqlite:///{temp_dir / 'projection.sqlite3'}", temp_dir


def _bootstrap_db(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(bind=engine)


def test_lite_dashboard_keeps_entity_watchlist_summary_with_normalized_entity_ids() -> None:
    client = _client_with_state(_state())

    response = client.get("/api/admin/dashboard/lite")

    assert response.status_code == 200
    summary = response.json()["entity_watchlist_summary"]
    assert summary
    assert summary[0]["entity_id"] == "101"
    assert summary[0]["event_count"] == 1
    assert summary[0]["alert_count"] == 1
    assert summary[0]["rising_count"] == 1


def test_lite_dashboard_repairs_watchlist_entities_from_titles_and_sources() -> None:
    state = _state()
    samsung_event = _event(
        "evt-samsung",
        title="三星首款 PCIe Gen6 固态硬盘 PM1743 上线官网",
        summary="Samsung storage business adds a new high-speed SSD.",
        entity_ids=[],
        entity_names=[],
        composite_score=60,
        velocity_score=45,
        coverage_score=55,
        freshness_score=65,
        member_delta=1,
        platform_delta=0,
        last_seen_at="2026-05-24T11:00:00+00:00",
        alert_state="rising",
    )
    ignored_samsung_event = _event(
        "evt-samsung-ignored",
        title="Samsung rumor ignored",
        summary="Ignored Samsung item.",
        entity_ids=[],
        entity_names=[],
        composite_score=99,
        velocity_score=99,
        coverage_score=99,
        freshness_score=99,
        member_delta=1,
        platform_delta=0,
        last_seen_at="2026-05-24T12:00:00+00:00",
        alert_state="breakout",
        ignored=True,
    )
    apple_event = _event(
        "evt-apple",
        title="New accessibility features are rolling out",
        summary="Apple Newsroom shared the new accessibility feature set.",
        entity_ids=[],
        entity_names=[],
        composite_score=50,
        velocity_score=40,
        coverage_score=50,
        freshness_score=60,
        member_delta=1,
        platform_delta=0,
        last_seen_at="2026-05-24T10:30:00+00:00",
        alert_state="watch",
    )
    apple_event["representative_source_name"] = "Apple Newsroom"
    state["intel_events"] = [samsung_event, ignored_samsung_event, apple_event]
    state["intel_alerts"] = [_alert("alert-samsung", samsung_event), _alert("alert-samsung-ignored", ignored_samsung_event, level="breakout")]
    state["settings"]["entity_watchlist"] = [
        {
            "entity_id": "3910b1e0ccab",
            "entity_name": "Samsung",
            "entity_type": "ORG",
            "watchlisted": True,
            "added_at": "2026-05-24T08:00:00+00:00",
        },
        {
            "entity_id": "cc1c4b62dffc",
            "entity_name": "三星",
            "entity_type": "ORG",
            "watchlisted": True,
            "added_at": "2026-05-24T08:00:00+00:00",
        },
        {
            "entity_id": "9f6290f4436e",
            "entity_name": "Apple",
            "entity_type": "ORG",
            "watchlisted": True,
            "added_at": "2026-05-24T08:00:00+00:00",
        },
    ]
    client = _client_with_state(state)

    response = client.get("/api/admin/dashboard/lite")

    assert response.status_code == 200
    summary_by_name = {item["entity_name"]: item for item in response.json()["entity_watchlist_summary"]}
    assert summary_by_name["Samsung"]["event_count"] == 1
    assert summary_by_name["Samsung"]["alert_count"] == 1
    assert summary_by_name["Samsung"]["breakout_count"] == 0
    assert summary_by_name["Apple"]["event_count"] == 1

    events_response = client.get("/api/admin/intel/events", params={"entity_id": "3910b1e0ccab", "ignore_mode": "visible"})
    assert events_response.status_code == 200
    assert [item["id"] for item in events_response.json()["items"]] == ["evt-samsung"]

    legacy_id_response = client.get("/api/admin/intel/events", params={"entity_id": "cc1c4b62dffc", "ignore_mode": "visible"})
    assert legacy_id_response.status_code == 200
    assert [item["id"] for item in legacy_id_response.json()["items"]] == ["evt-samsung"]


def test_events_endpoint_filters_sorts_and_paginates_cross_page() -> None:
    client = _client_with_state(_state())

    response = client.get(
        "/api/admin/intel/events",
        params={
            "page": 1,
            "page_size": 1,
            "entity_id": "101",
            "ignore_mode": "visible",
            "sort_by": "velocity_score",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["has_more"] is False
    assert [item["id"] for item in payload["items"]] == ["evt-openai"]

    event_response = client.get("/api/admin/intel/events", params={"event_id": "evt-deepseek", "page_size": 1})
    assert event_response.status_code == 200
    event_payload = event_response.json()
    assert event_payload["total"] == 1
    assert event_payload["items"][0]["id"] == "evt-deepseek"


def test_alerts_endpoint_includes_event_summary() -> None:
    client = _client_with_state(_state())

    response = client.get("/api/admin/intel/alerts")

    assert response.status_code == 200
    alerts = response.json()["items"]
    assert alerts[0]["summary"]
    assert alerts[0]["summary"] != alerts[0]["reason"]


def test_db_event_read_model_filters_sorts_and_alerts_include_summary() -> None:
    database_url, temp_dir = _make_sqlite_url()
    _bootstrap_db(database_url)
    try:
        sync_ingest_projection_from_state(_state(), database_url=database_url)

        items, total = list_intel_events_from_db(
            database_url=database_url,
            page=1,
            page_size=1,
            entity_id="101",
            ignore_mode="visible",
            sort_by="velocity_score",
        )

        assert total == 1
        assert [item.id for item in items] == ["evt-openai"]

        canonical_items, canonical_total = list_intel_events_from_db(
            database_url=database_url,
            page=1,
            page_size=2,
            entity_keys={"0523b13262c5", "OpenAI"},
            ignore_mode="visible",
        )
        assert canonical_total == 1
        assert [item.id for item in canonical_items] == ["evt-openai"]

        latest_items, latest_total = list_intel_events_from_db(
            database_url=database_url,
            page=1,
            page_size=2,
            sort_by="latest_seen",
        )
        assert latest_total == 3
        assert [item.id for item in latest_items] == ["evt-ignored", "evt-openai"]

        alerts = list_intel_alerts_from_db(database_url=database_url)
        assert alerts[0].summary
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
