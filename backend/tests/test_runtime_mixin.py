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

from backend.app.models import RuntimePlanPayload
from backend.app.store import get_studio_store_class
from backend.app.store_mixins import RuntimeMixin

StudioStore = get_studio_store_class()


def _make_store() -> tuple[StudioStore, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="runtime-mixin-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    return store, temp_root


def _seed_digest_delivery_state(store: StudioStore, *, event_count: int = 3) -> None:
    state = store._upgrade_state(store._read())
    state["automation_mode"] = "automated"
    plan = store._runtime_plan(state)
    plan["batch_limit"] = 5
    plan["delivery_mode"] = "local_digest"
    plan["admission_strategy"] = "top_scored"
    plan["admission_filters"] = {
        "require_watchlisted": False,
        "require_entity_match": False,
        "min_source_count": 0,
        "min_fulltext_count": 1,
        "breakout_only": False,
        "exclude_existing_brief": True,
        "exclude_synced_brief": True,
    }
    runtime = store._runtime(state)
    runtime["current_mode"] = "automated"
    runtime["delivery_mode"] = "local_digest"
    runtime["admission_strategy"] = "top_scored"
    runtime["current_cycle"] = "collecting"

    titles = [
        "华为发布 AI DC 全栈方案",
        "OpenAI 推出企业管理更新",
        "国产芯片工具链更新",
    ]
    facts = [
        "华为发布 AI DC 数据基础设施全栈方案",
        "OpenAI 面向企业用户更新管理能力",
        "国产芯片工具链发布新版本",
    ]
    state["intel_events"] = []
    state["event_deep_dives"] = []
    for index in range(event_count):
        event_id = f"evt-runtime-digest-{index + 1}"
        title = titles[index]
        fact = facts[index]
        state["intel_events"].append(
            {
                "id": event_id,
                "title": title,
                "summary": fact,
                "alert_state": "new",
                "entity_names": [title.split()[0]],
                "entity_ids": [],
                "brief_id": None,
                "watchlisted": False,
                "ignored": False,
                "source_count": 2,
                "composite_score": 90 - index,
                "audience_fit_score": 80,
                "velocity_score": 70,
                "coverage_score": 70,
                "freshness_score": 70,
            }
        )
        state["event_deep_dives"].append(
            {
                "id": f"dd-runtime-digest-{index + 1}",
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
                        "original_link": f"https://example.com/runtime-digest-{index + 1}",
                        "canonical_link": f"https://example.com/runtime-digest-{index + 1}",
                        "title": title,
                        "fetch_status": "fetched",
                        "extract_status": "extracted",
                        "word_count": 100,
                        "cleaned_full_text": fact,
                        "excerpt": fact,
                        "quotes": [],
                    }
                ],
                "facts": [fact],
                "quotes": [],
                "timeline": [f"2026-05-26：{title}"],
                "worthiness": {"worth_to_brief": True, "reason": "该事件有明确事实和读者价值。"},
                "last_error": None,
                "article_writing_guide": "",
            }
        )
    store._write(state)


def test_studio_store_runtime_methods_are_bound_from_mixin() -> None:
    store, temp_root = _make_store()
    try:
        assert StudioStore.get_runtime_status is RuntimeMixin.get_runtime_status
        assert StudioStore.start_runtime is RuntimeMixin.start_runtime
        assert StudioStore.stop_runtime is RuntimeMixin.stop_runtime
        assert StudioStore.run_runtime_intent is RuntimeMixin.run_runtime_intent
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_update_runtime_plan_updates_runtime_projection() -> None:
    store, temp_root = _make_store()
    try:
        payload = RuntimePlanPayload(
            launch_mode="interval_now",
            interval_minutes=30,
            timezone="Asia/Shanghai",
            work_scope="collect_events_alerts",
            delivery_mode="local_digest",
            delivery_schedule_time=None,
            admission_strategy="top_scored",
            batch_limit=5,
            admission_filters={"exclude_existing_brief": True},
        )

        plan = store.update_runtime_plan(payload)
        status = store.get_runtime_status()

        assert plan.batch_limit == 5
        assert plan.interval_minutes == 30
        assert status.batch_limit == 5
        assert status.work_scope == "collect_events_alerts"
        assert status.delivery_mode == "local_digest"
        assert status.admission_strategy == "top_scored"
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_legacy_automation_modes_migrate_to_two_mode_delivery_combinations() -> None:
    cases = [
        ("radar_only", "manual", "collect_only"),
        ("radar_and_draft", "automated", "local_digest"),
        ("full_pipeline", "automated", "immediate"),
    ]
    for legacy_mode, expected_mode, expected_delivery_mode in cases:
        store, temp_root = _make_store()
        try:
            state = store._upgrade_state(store._read())
            state["automation_mode"] = legacy_mode
            state["runtime"]["current_mode"] = legacy_mode
            state["runtime_plan"]["delivery_mode"] = "immediate"
            store._write(state)

            migrated = store._upgrade_state(store._read())
            plan = store._runtime_plan(migrated)
            runtime = store._runtime(migrated)

            assert migrated["automation_mode"] == expected_mode
            assert runtime["current_mode"] == expected_mode
            assert plan["delivery_mode"] == expected_delivery_mode
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)


def test_set_scheduler_running_false_resets_stopped_runtime_state() -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        runtime = store._runtime(state)
        runtime["scheduler_running"] = True
        runtime["control_state"] = "waiting"
        runtime["current_cycle"] = "collecting"
        runtime["enabled_at"] = "2026-05-13T10:00:00+08:00"
        runtime["scheduled_start_at"] = "2026-05-13T10:30:00+08:00"
        runtime["current_cycle_started_at"] = "2026-05-13T10:01:00+08:00"
        runtime["next_collect_at"] = "2026-05-13T10:30:00+08:00"
        store._write(state)

        store.set_scheduler_running(False)
        next_state = store._upgrade_state(store._read())
        next_runtime = store._runtime(next_state)

        assert next_runtime["scheduler_running"] is False
        assert next_runtime["control_state"] == "stopped"
        assert next_runtime["current_cycle"] == "idle"
        assert next_runtime["enabled_at"] is None
        assert next_runtime["scheduled_start_at"] is None
        assert next_runtime["current_cycle_started_at"] is None
        assert next_runtime["next_collect_at"] is None
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_delivery_pipeline_generates_one_daily_digest_without_wechat_upload(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        _seed_digest_delivery_state(store, event_count=3)

        def _fail_if_wechat_upload_called(*args, **kwargs):
            raise AssertionError("传统每日短讯 MVP 不应自动上传微信草稿箱。")

        monkeypatch.setattr(store, "sync_brief_wechat_draft", _fail_if_wechat_upload_called)

        state = store._upgrade_state(store._read())
        runtime = store._runtime(state)
        store._run_delivery_pipeline(state, runtime, triggered_by="scheduler")

        refreshed = store._upgrade_state(store._read())
        refreshed_runtime = store._runtime(refreshed)
        metrics = refreshed_runtime["current_cycle_metrics"]

        assert metrics["selected_event_count"] == 3
        assert metrics["deep_dive_count"] == 3
        assert metrics["brief_count"] == 1
        assert metrics["wechat_sync_count"] == 0
        assert metrics["wechat_verify_count"] == 0
        assert len(refreshed["briefs"]) == 1

        brief = refreshed["briefs"][0]
        assert brief["title"].startswith("今日科技速递")
        assert "## 1. 华为发布 AI DC 全栈方案" in brief["wechat_markdown"]
        assert "## 2. OpenAI 推出企业管理更新" in brief["wechat_markdown"]
        assert "## 3. 国产芯片工具链更新" in brief["wechat_markdown"]
        assert all(item.get("brief_id") == brief["id"] for item in refreshed["intel_events"])
        assert all(item.get("brief_status") == "prepared" for item in refreshed["intel_events"])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_top_scored_strategy_selects_new_events_by_score() -> None:
    store, temp_root = _make_store()
    try:
        _seed_digest_delivery_state(store, event_count=3)

        state = store._upgrade_state(store._read())
        selected = store._select_delivery_events_strict(state)

        assert [item["id"] for item in selected] == [
            "evt-runtime-digest-1",
            "evt-runtime-digest-2",
            "evt-runtime-digest-3",
        ]
        assert all(item["alert_state"] == "new" for item in selected)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_delivery_pipeline_collect_only_skips_deep_dive_and_digest(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        _seed_digest_delivery_state(store, event_count=3)
        state = store._upgrade_state(store._read())
        state["runtime_plan"]["delivery_mode"] = "collect_only"
        store._runtime(state)["delivery_mode"] = "collect_only"
        store._write(state)

        def _fail_if_deep_dive_called(*args, **kwargs):
            raise AssertionError("collect_only must not run deep dive or briefing")

        monkeypatch.setattr(store, "create_event_deep_dive", _fail_if_deep_dive_called)

        state = store._upgrade_state(store._read())
        runtime = store._runtime(state)
        store._run_delivery_pipeline(state, runtime, triggered_by="scheduler")

        refreshed = store._upgrade_state(store._read())
        metrics = store._runtime(refreshed)["current_cycle_metrics"]

        assert metrics["selected_event_count"] == 0
        assert metrics["deep_dive_count"] == 0
        assert metrics["brief_count"] == 0
        assert refreshed["briefs"] == []
        assert all(not item.get("brief_id") for item in refreshed["intel_events"])
        assert any("跳过自动交付" in str(item.get("message") or "") for item in refreshed["logs"])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_manual_mode_runtime_cycle_skips_delivery(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        state = store._upgrade_state(store._read())
        state["automation_mode"] = "manual"
        state["runtime_plan"]["delivery_mode"] = "local_digest"
        runtime = store._runtime(state)
        runtime["scheduler_running"] = True
        runtime["control_state"] = "running"
        store._write(state)

        def _fake_sync_due_sources(state, **kwargs):
            class _SyncResponse:
                raw_count = 0
                event_count = 0

            return _SyncResponse()

        def _fail_if_delivery_called(*args, **kwargs):
            raise AssertionError("manual mode must not call delivery pipeline automatically")

        monkeypatch.setattr(store, "_sync_due_sources", _fake_sync_due_sources)
        monkeypatch.setattr(store, "_run_delivery_pipeline", _fail_if_delivery_called)

        result = store._run_automation_cycle_locked(store._upgrade_state(store._read()), triggered_by="scheduler", force=True)

        refreshed = store._upgrade_state(store._read())
        assert result["brief_count"] == 0
        assert result["wechat_synced_count"] == 0
        assert any("手动模式" in str(item.get("message") or "") and "跳过自动交付" in str(item.get("message") or "") for item in refreshed["logs"])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_delivery_pipeline_retry_briefs_do_not_block_new_daily_digest(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        _seed_digest_delivery_state(store, event_count=3)
        state = store._upgrade_state(store._read())
        store._runtime_plan(state)["batch_limit"] = 3
        state["briefs"] = [
            {
                "id": f"brief-old-{index}",
                "event_id": f"evt-old-{index}",
                "deep_dive_id": f"dd-old-{index}",
                "brief_level": "rule",
                "stage": "prepared",
                "title": f"旧简报 {index}",
                "summary": "",
                "one_line": "",
                "why_it_matters": "",
                "facts": [],
                "quotes": [],
                "timeline": [],
                "entity_names": [],
                "source_links": [],
                "risk_notes": [],
                "prompt_package_markdown": "",
                "wechat_markdown": "",
                "wechat_html": "",
                "needs_resync": False,
                "delivery_status": "idle",
                "updated_at": f"2026-05-25T10:0{index}:00+08:00",
            }
            for index in range(1, 4)
        ]
        store._write(state)

        def _fail_if_wechat_upload_called(*args, **kwargs):
            raise AssertionError("传统每日短讯 MVP 不应自动上传微信草稿箱。")

        monkeypatch.setattr(store, "sync_brief_wechat_draft", _fail_if_wechat_upload_called)

        state = store._upgrade_state(store._read())
        runtime = store._runtime(state)
        store._run_delivery_pipeline(state, runtime, triggered_by="scheduler")

        refreshed = store._upgrade_state(store._read())
        metrics = store._runtime(refreshed)["current_cycle_metrics"]

        assert metrics["selected_event_count"] == 3
        assert metrics["brief_count"] == 1
        assert metrics["wechat_sync_count"] == 0
        assert len(refreshed["briefs"]) == 4
        assert refreshed["briefs"][0]["title"].startswith("今日科技速递")
        assert any("仅生成本地简报" in str(item.get("message") or "") and "跳过微信上传" in str(item.get("message") or "") for item in refreshed["logs"])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_scheduled_batch_not_due_generates_digest_without_upload(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        _seed_digest_delivery_state(store, event_count=3)
        state = store._upgrade_state(store._read())
        plan = store._runtime_plan(state)
        plan["delivery_mode"] = "scheduled_batch"
        plan["delivery_schedule_time"] = "23:59"
        runtime = store._runtime(state)
        runtime["delivery_mode"] = "scheduled_batch"
        runtime["last_delivery_batch_at"] = None
        store._write(state)

        def _fail_if_wechat_upload_called(*args, **kwargs):
            raise AssertionError("scheduled_batch before schedule must not upload WeChat drafts")

        monkeypatch.setattr(store, "sync_brief_wechat_draft", _fail_if_wechat_upload_called)

        state = store._upgrade_state(store._read())
        runtime = store._runtime(state)
        store._run_delivery_pipeline(state, runtime, triggered_by="scheduler")

        refreshed = store._upgrade_state(store._read())
        metrics = store._runtime(refreshed)["current_cycle_metrics"]

        assert metrics["selected_event_count"] == 3
        assert metrics["deep_dive_count"] == 3
        assert metrics["brief_count"] == 1
        assert metrics["wechat_sync_count"] == 0
        assert len(refreshed["briefs"]) == 1
        assert refreshed["briefs"][0]["title"].startswith("今日科技速递")
        assert all(item.get("brief_id") == refreshed["briefs"][0]["id"] for item in refreshed["intel_events"])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_scheduled_batch_due_records_upload_slot(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        _seed_digest_delivery_state(store, event_count=3)
        state = store._upgrade_state(store._read())
        plan = store._runtime_plan(state)
        plan["delivery_mode"] = "scheduled_batch"
        plan["delivery_schedule_time"] = "00:00"
        runtime = store._runtime(state)
        runtime["delivery_mode"] = "scheduled_batch"
        runtime["last_delivery_batch_at"] = None
        store._write(state)

        def _fake_wechat_upload(brief_id: str, **kwargs):
            upload_state = store._upgrade_state(store._read())
            brief = next(item for item in upload_state["briefs"] if item["id"] == brief_id)
            brief["stage"] = "synced"
            brief["last_verified_at"] = "2026-05-27T10:00:00+00:00"
            store._write(upload_state)

            class _UploadResult:
                def model_dump(self):
                    return dict(brief)

            return _UploadResult()

        monkeypatch.setattr(store, "sync_brief_wechat_draft", _fake_wechat_upload)

        state = store._upgrade_state(store._read())
        runtime = store._runtime(state)
        store._run_delivery_pipeline(state, runtime, triggered_by="scheduler")

        refreshed = store._upgrade_state(store._read())
        metrics = store._runtime(refreshed)["current_cycle_metrics"]

        assert metrics["brief_count"] == 1
        assert metrics["wechat_sync_count"] == 1
        assert metrics["wechat_verify_count"] == 1
        assert store._runtime(refreshed).get("last_delivery_batch_at")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def test_delivery_pipeline_skips_daily_digest_when_fewer_than_two_qualified_events(monkeypatch) -> None:
    store, temp_root = _make_store()
    try:
        _seed_digest_delivery_state(store, event_count=1)

        def _fail_if_wechat_upload_called(*args, **kwargs):
            raise AssertionError("传统每日短讯 MVP 不应自动上传微信草稿箱。")

        monkeypatch.setattr(store, "sync_brief_wechat_draft", _fail_if_wechat_upload_called)

        state = store._upgrade_state(store._read())
        runtime = store._runtime(state)
        store._run_delivery_pipeline(state, runtime, triggered_by="scheduler")

        refreshed = store._upgrade_state(store._read())
        refreshed_runtime = store._runtime(refreshed)
        metrics = refreshed_runtime["current_cycle_metrics"]

        assert metrics["selected_event_count"] == 1
        assert metrics["deep_dive_count"] == 1
        assert metrics["brief_count"] == 0
        assert metrics["wechat_sync_count"] == 0
        assert refreshed["briefs"] == []
        assert not refreshed["intel_events"][0].get("brief_id")
        assert any("至少需要 2 条合格事件" in str(item.get("message") or "") for item in refreshed["logs"])
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
