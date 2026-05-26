"""Status field normalization utilities for deep_dive records.

Phase 1 of PostgreSQL migration: fix dirty status values before switching read chain.

Problem: state.json contains 8 records with fetch_status/extract_status = "success"
         which is NOT a valid value per DeepDiveFetchStatus/DeepDiveExtractStatus Literal types.

Solution: Normalize "success" → "fetched"/"extracted" and add validation.
"""

from __future__ import annotations

from typing import Any


def normalize_fetch_status(status: str | None) -> str:
    """Normalize fetch_status to valid Literal value.

    Valid values: pending, fetched, fetch_failed, fetch_blocked, non_html
    Dirty values found: success (→ fetched)
    """
    raw = str(status or "pending").strip().lower()
    # Map dirty values to correct values
    if raw == "success":
        return "fetched"
    # Validate against known good values
    valid_values = {"pending", "fetched", "fetch_failed", "fetch_blocked", "non_html"}
    if raw in valid_values:
        return raw
    # Unknown value - default to pending
    return "pending"


def normalize_extract_status(status: str | None) -> str:
    """Normalize extract_status to valid Literal value.

    Valid values: pending, extracted, extract_failed, too_short
    Dirty values found: success (→ extracted)
    """
    raw = str(status or "pending").strip().lower()
    # Map dirty values to correct values
    if raw == "success":
        return "extracted"
    # Validate against known good values
    valid_values = {"pending", "extracted", "extract_failed", "too_short"}
    if raw in valid_values:
        return raw
    # Unknown value - default to pending
    return "pending"


def normalize_deep_dive_source_item(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize status fields in a deep dive source item.

    Returns a new dict with normalized status fields.
    """
    return {
        **item,
        "fetch_status": normalize_fetch_status(item.get("fetch_status")),
        "extract_status": normalize_extract_status(item.get("extract_status")),
    }


def normalize_deep_dive_record(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize status fields in a deep dive record.

    Returns a new dict with normalized source items.
    """
    sources = record.get("sources", [])
    normalized_sources = [normalize_deep_dive_source_item(item) for item in sources]

    full_text_sources = record.get("full_text_sources", [])
    normalized_full_text_sources = [normalize_deep_dive_source_item(item) for item in full_text_sources]

    return {
        **record,
        "sources": normalized_sources,
        "full_text_sources": normalized_full_text_sources,
    }


def normalize_state_deep_dives(state: dict[str, Any]) -> dict[str, Any]:
    """Normalize all deep_dive records in state.

    Returns a new state dict with normalized deep_dives.
    """
    deep_dives = state.get("event_deep_dives", [])
    normalized_deep_dives = [normalize_deep_dive_record(record) for record in deep_dives]

    return {
        **state,
        "event_deep_dives": normalized_deep_dives,
    }
