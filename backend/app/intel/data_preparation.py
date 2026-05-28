"""Data preparation layer for analysis pipeline.

Phase 3 of PostgreSQL migration: Prepare analysis data from PostgreSQL
without modifying pipeline.py pure functions.

Design:
    PostgreSQL Query -> Data Preparation Layer -> Memory Assembly -> pipeline.py pure function

This keeps pipeline.py database-free and testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from ..db.config import get_database_settings
from ..db.read_models import (
    get_discovery_items_for_clustering,
    get_event_snapshots_for_analysis,
    get_raw_items_for_analysis,
    list_discovery_items_from_db,
    list_intel_events_from_db,
    list_intel_alerts_from_db,
)


@dataclass
class AnalysisConfig:
    """Configuration for analysis data preparation."""

    raw_items_hours: int = 24
    snapshots_hours: int = 48
    discovery_hours: int = 24
    source_keys: list[str] | None = None


@dataclass
class AnalysisData:
    """Prepared analysis data ready for pipeline processing."""

    raw_items: list[dict[str, Any]] = field(default_factory=list)
    discovery_items: list[dict[str, Any]] = field(default_factory=list)
    event_snapshots: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def prepare_analysis_data_from_db(
    *,
    database_url: str,
    config: AnalysisConfig | None = None,
) -> AnalysisData:
    """Prepare analysis data from PostgreSQL.

    This is the main entry point for database-backed analysis.
    It fetches all necessary data and assembles it in memory
    for the pipeline.py pure functions to process.

    Args:
        database_url: Database connection string
        config: Analysis configuration (optional)

    Returns:
        AnalysisData ready for pipeline processing
    """
    cfg = config or AnalysisConfig()

    # Fetch data from database
    raw_items = get_raw_items_for_analysis(
        database_url=database_url,
        hours=cfg.raw_items_hours,
        source_keys=cfg.source_keys,
    )

    discovery_items = get_discovery_items_for_clustering(
        database_url=database_url,
        hours=cfg.discovery_hours,
    )

    # Get event_ids from discovery_items for snapshot query
    event_ids = list({item.get("event_id") for item in discovery_items if item.get("event_id")})

    event_snapshots = get_event_snapshots_for_analysis(
        database_url=database_url,
        event_ids=event_ids if event_ids else None,
        hours=cfg.snapshots_hours,
    )

    return AnalysisData(
        raw_items=raw_items,
        discovery_items=discovery_items,
        event_snapshots=event_snapshots,
    )


def prepare_analysis_data_from_json(*, state: dict[str, Any]) -> AnalysisData:
    """Prepare analysis data from JSON state (fallback/compatibility).

    This extracts data from the existing JSON state structure
    for backward compatibility.

    Args:
        state: The full state dict from state.json

    Returns:
        AnalysisData ready for pipeline processing
    """
    raw_items = [
        {
            "id": item.get("id"),
            "source_key": item.get("source_key"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "content": item.get("content"),
            "link": item.get("link"),
            "canonical_link": item.get("canonical_link"),
            "dedupe_key": item.get("dedupe_key"),
            "published_at": item.get("published_at"),
            "collected_at": item.get("collected_at"),
            "score": item.get("score", 0),
            "tags": item.get("tags", []),
            "metadata": item.get("metadata", {}),
        }
        for item in state.get("raw_items", [])
        if isinstance(item, dict)
    ]

    discovery_items = [
        {
            "id": item.get("id"),
            "raw_item_id": item.get("raw_item_id"),
            "source_key": item.get("source_key"),
            "source_name": item.get("source_name"),
            "source_kind": item.get("source_kind"),
            "platform": item.get("platform"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "content": item.get("content"),
            "link": item.get("link"),
            "canonical_link": item.get("canonical_link"),
            "dedupe_key": item.get("dedupe_key"),
            "title_tokens": item.get("title_tokens", []),
            "anchor_tokens": item.get("anchor_tokens", []),
            "published_at": item.get("published_at"),
            "collected_at": item.get("collected_at"),
            "tags": item.get("tags", []),
            "engagement_score": item.get("engagement_score", 0),
            "item_state": item.get("item_state"),
            "entity_ids": item.get("entity_ids", []),
            "entity_names": item.get("entity_names", []),
        }
        for item in state.get("discovery_items", [])
        if isinstance(item, dict)
    ]

    # Extract event snapshots from events
    event_snapshots: dict[str, list[dict[str, Any]]] = {}
    for event in state.get("intel_events", []):
        if isinstance(event, dict):
            event_id = event.get("id")
            if event_id:
                # Create a snapshot from current event state
                event_snapshots[event_id] = [
                    {
                        "event_id": event_id,
                        "captured_at": event.get("last_seen_at") or event.get("first_seen_at"),
                        "member_count": event.get("member_count", 0),
                        "platform_count": event.get("platform_count", 0),
                        "source_count": event.get("source_count", 0),
                        "velocity_score": event.get("velocity_score", 0),
                        "coverage_score": event.get("coverage_score", 0),
                        "freshness_score": event.get("freshness_score", 0),
                        "composite_score": event.get("composite_score", 0),
                        "alert_state": event.get("alert_state"),
                    }
                ]

    return AnalysisData(
        raw_items=raw_items,
        discovery_items=discovery_items,
        event_snapshots=event_snapshots,
    )


def prepare_analysis_data(*, state: dict[str, Any] | None = None, config: AnalysisConfig | None = None) -> AnalysisData:
    """Main entry point for analysis data preparation.

    Automatically selects database or JSON source based on STATE_BACKEND setting.

    Args:
        state: Optional state dict (required for JSON fallback)
        config: Optional analysis configuration

    Returns:
        AnalysisData ready for pipeline processing
    """
    settings = get_database_settings()

    if settings.is_database_enabled and settings.database_url:
        return prepare_analysis_data_from_db(
            database_url=settings.database_url,
            config=config,
        )

    if state is None:
        raise ValueError("state is required when database is not enabled")

    return prepare_analysis_data_from_json(state=state)


def load_current_intel_state_to_memory(*, database_url: str) -> dict[str, Any]:
    """Load current intel state from PostgreSQL into memory format.

    This is used to populate state dict for pipeline.py consumption.
    The loaded data matches the JSON state structure for compatibility.

    Args:
        database_url: Database connection string

    Returns:
        Dict with raw_items, discovery_items, intel_events, intel_alerts
    """
    # Load discovery items
    discovery_items, _, _, _ = list_discovery_items_from_db(database_url=database_url, page=1, page_size=10000)

    # Load intel events
    intel_events, _ = list_intel_events_from_db(database_url=database_url, page=1, page_size=10000)

    # Load intel alerts
    intel_alerts = list_intel_alerts_from_db(database_url=database_url)

    # Raw items - use analysis function with longer window
    raw_items = get_raw_items_for_analysis(database_url=database_url, hours=72)

    # Event snapshots
    event_ids = [e.id for e in intel_events]
    event_snapshots = get_event_snapshots_for_analysis(
        database_url=database_url,
        event_ids=event_ids if event_ids else None,
        hours=72,
    )

    return {
        "raw_items": [item.model_dump() for item in raw_items] if raw_items and hasattr(raw_items[0], "model_dump") else raw_items,
        "discovery_items": [item.model_dump() for item in discovery_items],
        "intel_events": [item.model_dump() for item in intel_events],
        "intel_alerts": [item.model_dump() for item in intel_alerts],
        "event_snapshots": event_snapshots,
    }
