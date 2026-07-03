from __future__ import annotations

from typing import Any

from .analysis_projection import sync_analysis_projection_from_events
from .config import get_database_settings


def persist_incremental_analysis(events: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> dict[str, int]:
    settings = get_database_settings()
    if settings.state_backend not in {"dual_write", "postgres"} or not settings.database_url:
        return {}
    return sync_analysis_projection_from_events(events, snapshots, database_url=settings.database_url)
