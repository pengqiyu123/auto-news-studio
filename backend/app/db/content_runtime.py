from __future__ import annotations

from .config import get_database_settings
from .content_projection import sync_content_projection_from_state


def content_database_write_enabled() -> bool:
    settings = get_database_settings()
    return settings.state_backend in {"dual_write", "postgres"} and bool(settings.database_url)


def persist_content_assets(state: dict, *, database_url: str | None = None) -> dict[str, int]:
    settings = get_database_settings()
    url = str(database_url or settings.database_url or "").strip()
    if not url:
        return {}
    if settings.state_backend not in {"dual_write", "postgres"}:
        return {}
    return sync_content_projection_from_state(state, database_url=url)
