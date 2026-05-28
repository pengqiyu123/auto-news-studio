from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import types

from fastapi.testclient import TestClient

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

from backend.app.routes.common import set_store
from backend.app.store import get_studio_store_class

StudioStore = get_studio_store_class()


def _discovery_item(
    item_id: str,
    *,
    title: str,
    summary: str,
    source_name: str,
    platform: str,
    collected_at: str,
    engagement_score: float,
    item_state: str,
) -> dict:
    return {
        "id": item_id,
        "raw_item_id": f"raw-{item_id}",
        "source_key": source_name.lower().replace(" ", "-"),
        "source_name": source_name,
        "source_kind": "rss",
        "platform": platform,
        "title": title,
        "summary": summary,
        "content": summary,
        "link": f"https://example.com/{item_id}",
        "canonical_link": f"https://example.com/{item_id}",
        "dedupe_key": item_id,
        "source_native_id": item_id,
        "title_tokens": [],
        "anchor_tokens": [],
        "published_at": collected_at,
        "collected_at": collected_at,
        "tags": [],
        "engagement_score": engagement_score,
        "item_state": item_state,
        "entity_ids": [],
        "entity_names": [],
        "metadata": {},
    }


def _client_with_stream_items(items: list[dict]) -> TestClient:
    temp_root = Path(tempfile.mkdtemp(prefix="stream-filters-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    state = store._upgrade_state(store._read())
    state["discovery_items"] = items
    store._write(state)

    import backend.app.main as main_module

    main_module.store = store
    set_store(store)
    return TestClient(main_module.app)


def test_stream_filters_cross_page_and_returns_stable_options() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    items = [
        _discovery_item(
            "disc-old",
            title="Old unrelated item",
            summary="archive",
            source_name="Archive Source",
            platform="web",
            collected_at=(now - timedelta(hours=96)).isoformat(),
            engagement_score=0,
            item_state="seen_item",
        ),
        _discovery_item(
            "disc-openai-low",
            title="OpenAI low signal",
            summary="small update",
            source_name="RSS OpenAI",
            platform="rss",
            collected_at=(now - timedelta(hours=2)).isoformat(),
            engagement_score=5,
            item_state="new_item",
        ),
        _discovery_item(
            "disc-openai-high",
            title="OpenAI high signal",
            summary="major platform update",
            source_name="Hacker News",
            platform="hackernews",
            collected_at=(now - timedelta(minutes=20)).isoformat(),
            engagement_score=150,
            item_state="updated_item",
        ),
    ]
    client = _client_with_stream_items(items)

    response = client.get(
        "/api/admin/intel/stream",
        params={
            "page": 1,
            "page_size": 1,
            "q": "openai",
            "time_range": "24h",
            "min_engagement": 100,
            "item_state": "updated_item",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["has_more"] is False
    assert [item["id"] for item in payload["items"]] == ["disc-openai-high"]
    assert payload["available_platforms"] == ["hackernews", "rss", "web"]
    assert payload["available_sources"] == ["Archive Source", "Hacker News", "RSS OpenAI"]


def test_stream_filters_by_source_platform_heat_and_query_fields() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    client = _client_with_stream_items(
        [
            _discovery_item(
                "disc-platform-match",
                title="Release notes",
                summary="contains target keyword",
                source_name="Alpha Source",
                platform="rss",
                collected_at=(now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                engagement_score=8,
                item_state="new_item",
            ),
            _discovery_item(
                "disc-source-miss",
                title="Release notes",
                summary="contains target keyword",
                source_name="Beta Source",
                platform="web",
                collected_at=(now - timedelta(hours=1)).isoformat(),
                engagement_score=8,
                item_state="new_item",
            ),
            _discovery_item(
                "disc-heat-miss",
                title="Release notes",
                summary="contains target keyword",
                source_name="Alpha Source",
                platform="rss",
                collected_at=(now - timedelta(hours=1)).isoformat(),
                engagement_score=15,
                item_state="new_item",
            ),
        ]
    )

    response = client.get(
        "/api/admin/intel/stream",
        params={
            "q": "target",
            "platform": "rss",
            "source": "Alpha Source",
            "time_range": "6h",
            "min_engagement": 1,
            "max_engagement": 9,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == ["disc-platform-match"]
