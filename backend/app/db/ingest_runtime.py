from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from .config import get_database_settings
from .ingest_projection import sync_ingest_projection_from_state
from .sync_runs import upsert_sync_run


def database_write_enabled() -> bool:
    settings = get_database_settings()
    return settings.state_backend in {"dual_write", "postgres"} and bool(settings.database_url)


def database_read_is_truth() -> bool:
    settings = get_database_settings()
    return settings.state_backend == "postgres" and bool(settings.database_url)


def current_database_url() -> str:
    return get_database_settings().database_url


def persist_ingest_chain_state(
    state: dict[str, Any],
    *,
    source_key: str | None,
    triggered_by: str,
    run_id: str | None = None,
    started_at: str | datetime | None = None,
    finished_at: str | datetime | None = None,
    status: str = "completed",
    warnings: list[str] | None = None,
) -> dict[str, int]:
    settings = get_database_settings()
    if settings.state_backend not in {"dual_write", "postgres"} or not settings.database_url:
        return {}

    counts = sync_ingest_projection_from_state(state, database_url=settings.database_url)
    upsert_sync_run(
        database_url=settings.database_url,
        run_id=str(run_id or f"sync-{uuid4().hex[:12]}"),
        source_key=source_key,
        triggered_by=triggered_by,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        warnings=warnings or [],
        raw_count=int(counts.get("raw_items", 0)),
        discovery_count=int(counts.get("discovery_items_current", 0)),
        event_count=int(counts.get("intel_events_current", 0)),
    )
    return counts
