from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "Base",
    "DatabaseSettings",
    "build_engine",
    "build_session_factory",
    "check_database_health",
    "content_database_write_enabled",
    "current_database_url",
    "database_read_is_truth",
    "database_write_enabled",
    "get_database_settings",
    "persist_content_assets",
    "persist_incremental_analysis",
    "persist_ingest_chain_state",
    "upsert_sync_run",
]

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "Base": (".base", "Base"),
    "DatabaseSettings": (".config", "DatabaseSettings"),
    "build_engine": (".session", "build_engine"),
    "build_session_factory": (".session", "build_session_factory"),
    "check_database_health": (".health", "check_database_health"),
    "content_database_write_enabled": (".content_runtime", "content_database_write_enabled"),
    "current_database_url": (".ingest_runtime", "current_database_url"),
    "database_read_is_truth": (".ingest_runtime", "database_read_is_truth"),
    "database_write_enabled": (".ingest_runtime", "database_write_enabled"),
    "get_database_settings": (".config", "get_database_settings"),
    "persist_content_assets": (".content_runtime", "persist_content_assets"),
    "persist_incremental_analysis": (".analysis_runtime", "persist_incremental_analysis"),
    "persist_ingest_chain_state": (".ingest_runtime", "persist_ingest_chain_state"),
    "upsert_sync_run": (".sync_runs", "upsert_sync_run"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
