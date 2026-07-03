from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..store.base import parse_time
from .models import SyncRunRecord
from .session import build_session_factory


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return parse_time(str(value or ""))


def upsert_sync_run(
    *,
    database_url: str,
    run_id: str,
    source_key: str | None,
    triggered_by: str,
    started_at: str | datetime | None,
    finished_at: str | datetime | None,
    status: str,
    warnings: list[str] | None = None,
    raw_count: int = 0,
    discovery_count: int = 0,
    event_count: int = 0,
) -> None:
    session_factory = build_session_factory(database_url)
    with session_factory() as session:
        _upsert_sync_run_in_session(
            session=session,
            run_id=run_id,
            source_key=source_key,
            triggered_by=triggered_by,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            warnings=warnings or [],
            raw_count=raw_count,
            discovery_count=discovery_count,
            event_count=event_count,
        )
        session.commit()


def _upsert_sync_run_in_session(
    *,
    session: Session,
    run_id: str,
    source_key: str | None,
    triggered_by: str,
    started_at: str | datetime | None,
    finished_at: str | datetime | None,
    status: str,
    warnings: list[str],
    raw_count: int,
    discovery_count: int,
    event_count: int,
) -> None:
    record = session.get(SyncRunRecord, run_id)
    if record is None:
        record = SyncRunRecord(
            run_id=run_id,
            source_key=source_key,
            triggered_by=triggered_by,
            started_at=_dt(started_at) or datetime.utcnow(),
            finished_at=_dt(finished_at),
            status=status,
            warnings_json=list(warnings),
            raw_count=int(raw_count),
            discovery_count=int(discovery_count),
            event_count=int(event_count),
        )
        session.add(record)
        return

    record.source_key = source_key
    record.triggered_by = triggered_by
    record.started_at = _dt(started_at) or record.started_at
    record.finished_at = _dt(finished_at)
    record.status = status
    record.warnings_json = list(warnings)
    record.raw_count = int(raw_count)
    record.discovery_count = int(discovery_count)
    record.event_count = int(event_count)
