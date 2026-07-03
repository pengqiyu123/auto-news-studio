from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from ...db import current_database_url, database_write_enabled
from ...db.analysis_projection import (
    precompute_event_relations,
    precompute_temporal_rules,
    precompute_topic_model,
    precompute_topic_periodicity,
    precompute_trend_detection,
)
from ...db.models import AnalysisBatchRunRecord
from ...db.session import build_session_factory
from ...routes.common import get_store


@dataclass(frozen=True)
class AnalysisBatchTask:
    name: str
    dependencies: tuple[str, ...]
    runner: Callable[[list[dict[str, Any]], list[dict[str, Any]], str], dict[str, int]]


def _run_topics(events: list[dict[str, Any]], _snapshots: list[dict[str, Any]], database_url: str) -> dict[str, int]:
    return precompute_topic_model(events, database_url=database_url)


def _run_relations(events: list[dict[str, Any]], _snapshots: list[dict[str, Any]], database_url: str) -> dict[str, int]:
    return precompute_event_relations(events, database_url=database_url)


def _run_trends(events: list[dict[str, Any]], snapshots: list[dict[str, Any]], database_url: str) -> dict[str, int]:
    return precompute_trend_detection(events, snapshots, database_url=database_url)


def _run_periodicity(events: list[dict[str, Any]], _snapshots: list[dict[str, Any]], database_url: str) -> dict[str, int]:
    return precompute_topic_periodicity(events, database_url=database_url)


def _run_temporal_rules(events: list[dict[str, Any]], _snapshots: list[dict[str, Any]], database_url: str) -> dict[str, int]:
    return precompute_temporal_rules(events, database_url=database_url)


TASKS: dict[str, AnalysisBatchTask] = {
    "topic_modeling": AnalysisBatchTask("topic_modeling", (), _run_topics),
    "event_relations": AnalysisBatchTask("event_relations", ("topic_modeling",), _run_relations),
    "trend_detection": AnalysisBatchTask("trend_detection", (), _run_trends),
    "topic_periodicity": AnalysisBatchTask("topic_periodicity", ("topic_modeling",), _run_periodicity),
    "temporal_rules": AnalysisBatchTask("temporal_rules", ("event_relations",), _run_temporal_rules),
}


def _read_analysis_inputs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    store = get_store()
    state = store._upgrade_state(store._read())
    events = [item for item in state.get("intel_events", []) if isinstance(item, dict) and not bool(item.get("ignored"))]
    snapshots = [item for item in state.get("event_snapshots", []) if isinstance(item, dict)]
    return events, snapshots


def _latest_success(task_name: str, *, database_url: str) -> datetime | None:
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        value = session.execute(
            text(
                """
                select finished_at
                from analysis_batch_runs
                where task_name = :task_name and status = 'success'
                order by finished_at desc
                limit 1
                """
            ),
            {"task_name": task_name},
        ).scalar_one_or_none()
    return value


def _start_run(task_name: str, *, database_url: str) -> str:
    run_id = f"analysis-batch-{uuid4().hex[:12]}"
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        session.add(
            AnalysisBatchRunRecord(
                id=run_id,
                task_name=task_name,
                status="running",
                started_at=datetime.now(UTC),
                items_processed=0,
                error_message="",
            )
        )
        session.commit()
    return run_id


def _finish_run(
    run_id: str,
    *,
    database_url: str,
    status: str,
    items_processed: int = 0,
    error_message: str = "",
) -> None:
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        record = session.get(AnalysisBatchRunRecord, run_id)
        if record:
            record.status = status
            record.finished_at = datetime.now(UTC)
            record.items_processed = max(0, int(items_processed or 0))
            record.error_message = str(error_message or "")[:4000]
            session.commit()


def run_analysis_batch_task(task_name: str, *, _visited: set[str] | None = None) -> dict[str, int]:
    database_url = current_database_url()
    if not database_write_enabled() or not database_url:
        return {}

    run_id = _start_run(task_name, database_url=database_url)
    try:
        task = TASKS.get(task_name)
        if task is None:
            raise ValueError(f"Unknown analysis batch task: {task_name}")
        visited = set(_visited or set())
        if task_name in visited:
            raise RuntimeError(f"Analysis batch dependency cycle at {task_name}")
        visited.add(task_name)
        task_latest_success = _latest_success(task_name, database_url=database_url)
        for dependency in task.dependencies:
            dependency_success = _latest_success(dependency, database_url=database_url)
            if dependency_success is None or (task_latest_success and dependency_success < task_latest_success):
                run_analysis_batch_task(dependency, _visited=visited)
        events, snapshots = _read_analysis_inputs()
        counts = task.runner(events, snapshots, database_url)
        _finish_run(
            run_id,
            database_url=database_url,
            status="success",
            items_processed=sum(max(0, int(value or 0)) for value in counts.values()),
        )
        return counts
    except Exception as exc:
        _finish_run(run_id, database_url=database_url, status="failed", error_message=str(exc))
        raise


def run_analysis_batch_chain(task_names: tuple[str, ...] | None = None) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = {}
    for task_name in task_names or tuple(TASKS):
        results[task_name] = run_analysis_batch_task(task_name)
    return results


def register_analysis_batch_jobs(scheduler) -> None:
    scheduler.add_job(
        run_analysis_batch_task,
        "cron",
        hour=2,
        minute=0,
        id="analysis-topic-modeling",
        args=["topic_modeling"],
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        run_analysis_batch_task,
        "cron",
        hour=3,
        minute=0,
        id="analysis-event-relations",
        args=["event_relations"],
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        run_analysis_batch_task,
        "cron",
        hour=4,
        minute=0,
        id="analysis-trend-detection",
        args=["trend_detection"],
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        run_analysis_batch_task,
        "cron",
        hour=5,
        minute=0,
        id="analysis-topic-periodicity",
        args=["topic_periodicity"],
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.add_job(
        run_analysis_batch_task,
        "cron",
        hour=5,
        minute=30,
        id="analysis-temporal-rules",
        args=["temporal_rules"],
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
