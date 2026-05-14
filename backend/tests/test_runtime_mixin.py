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
from backend.app.store import StudioStore
from backend.app.store_mixins import RuntimeMixin


def _make_store() -> tuple[StudioStore, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="runtime-mixin-"))
    store = StudioStore(data_file=temp_root / "data" / "state.json")
    return store, temp_root


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
            delivery_mode="immediate",
            delivery_schedule_time=None,
            admission_strategy="balanced",
            batch_limit=5,
            admission_filters={"exclude_existing_brief": True},
        )

        plan = store.update_runtime_plan(payload)
        status = store.get_runtime_status()

        assert plan.batch_limit == 5
        assert plan.interval_minutes == 30
        assert status.batch_limit == 5
        assert status.work_scope == "collect_events_alerts"
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
