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


StudioStore = get_studio_store_class()


def _make_store() -> tuple[StudioStore, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="delivery-integration-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    return store, temp_root


def _seed_radar_and_draft_ready_events(store: StudioStore) -> list[str]:
    state = store._upgrade_state(store._read())
    state["automation_mode"] = "automated"
    plan = store._runtime_plan(state)
    plan.update(
        {
            "launch_mode": "interval_now",
            "interval_minutes": 30,
            "timezone": "Asia/Shanghai",
            "work_scope": "collect_events_alerts",
            "delivery_mode": "local_digest",
            "delivery_schedule_time": None,
            "admission_strategy": "top_scored",
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
    )
    runtime = store._runtime(state)
    runtime["current_mode"] = "automated"
    runtime["delivery_mode"] = "local_digest"
    runtime["admission_strategy"] = "top_scored"
    runtime["current_cycle"] = "delivery"
    runtime["current_cycle_metrics"] = {}

    titles = [
        "华为发布 AI DC 全栈方案",
        "OpenAI 推出企业管理更新",
        "国产芯片工具链更新",
        "月之暗面升级长上下文能力",
    ]
    event_ids: list[str] = []
    state["briefs"] = []
    state["intel_events"] = []
    state["event_deep_dives"] = []
    for index, title in enumerate(titles, start=1):
        event_id = f"evt-delivery-digest-{index}"
        deep_dive_id = f"dd-delivery-digest-{index}"
        fact = f"{title}，这是第 {index} 条已核验事实。"
        event_ids.append(event_id)
        state["intel_events"].append(
            {
                "id": event_id,
                "title": title,
                "summary": fact,
                "representative_link": f"https://example.com/delivery-digest-{index}",
                "representative_source_name": "Example",
                "representative_discovery_item_id": f"disc-delivery-digest-{index}",
                "discovery_item_ids": [f"disc-delivery-digest-{index}"],
                "source_keys": ["rss-tech"],
                "source_names": ["Example"],
                "platforms": ["rss"],
                "platform_count": 1,
                "source_count": 2,
                "member_count": 1,
                "story_count": 1,
                "member_delta": 0,
                "platform_delta": 0,
                "published_at": "2026-05-26T10:00:00+08:00",
                "latest_collected_at": f"2026-05-26T10:0{index}:00+08:00",
                "first_seen_at": "2026-05-26T10:00:00+08:00",
                "last_seen_at": f"2026-05-26T10:0{index}:00+08:00",
                "tags": ["ai"],
                "anchor_tokens": ["ai"],
                "velocity_score": 90.0 - index,
                "coverage_score": 80.0,
                "freshness_score": 85.0,
                "composite_score": 95.0 - index,
                "audience_fit_score": 82.0,
                "velocity_details": {},
                "alert_state": "breakout" if index in {1, 3} else "rising",
                "change_state": "growing_event",
                "alert_reason": "该事件正在升温。",
                "entity_ids": [],
                "entity_names": [title.split()[0]],
                "watchlisted": False,
                "ignored": False,
                "deep_dive_id": deep_dive_id,
                "deep_dive_status": "ready",
                "brief_id": None,
                "brief_status": None,
                "worth_to_brief": True,
                "worth_reason": "有明确事实和来源，适合纳入今日速递。",
            }
        )
        state["event_deep_dives"].append(
            {
                "id": deep_dive_id,
                "event_id": event_id,
                "status": "ready",
                "started_at": "2026-05-26T10:00:00+08:00",
                "finished_at": "2026-05-26T10:01:00+08:00",
                "updated_at": f"2026-05-26T10:1{index}:00+08:00",
                "attempted_count": 1,
                "success_count": 1,
                "failed_count": 0,
                "resolved_evidence_pack": [],
                "full_text_sources": [],
                "sources": [
                    {
                        "source_key": "example",
                        "source_name": "Example",
                        "original_link": f"https://example.com/delivery-digest-{index}",
                        "canonical_link": f"https://example.com/delivery-digest-{index}",
                        "title": title,
                        "published_at": "2026-05-26T10:00:00+08:00",
                        "fetch_status": "fetched",
                        "extract_status": "extracted",
                        "word_count": 160,
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
    store._write(state)
    return event_ids


def test_radar_and_draft_delivery_generates_one_daily_digest_not_single_event_briefs(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        event_ids = _seed_radar_and_draft_ready_events(store)

        def _fail_if_single_event_brief_path_is_called(*args, **kwargs):
            raise AssertionError("delivery pipeline must generate one daily digest, not N single-event briefs")

        monkeypatch.setattr(store, "create_brief_from_event", _fail_if_single_event_brief_path_is_called)

        state = store._upgrade_state(store._read())
        runtime = store._runtime(state)
        store._run_delivery_pipeline(state, runtime, triggered_by="scheduler")

        refreshed = store._upgrade_state(store._read())
        metrics = store._runtime(refreshed)["current_cycle_metrics"]
        briefs = refreshed["briefs"]

        assert metrics["brief_count"] == 1
        assert len(briefs) == 1

        brief = briefs[0]
        assert brief["title"].startswith("今日科技速递")
        assert brief["brief_level"] == "rule"
        assert brief["workflow_mode"] == "traditional"
        assert "## 1." in brief["wechat_markdown"]
        assert "## 2." in brief["wechat_markdown"]
        assert "## 3." in brief["wechat_markdown"]
        assert "## 4." in brief["wechat_markdown"]

        events_by_id = {str(item["id"]): item for item in refreshed["intel_events"]}
        assert set(events_by_id) == set(event_ids)
        for event_id in event_ids:
            assert events_by_id[event_id]["brief_id"] == brief["id"]
            assert events_by_id[event_id]["brief_status"] == "prepared"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
