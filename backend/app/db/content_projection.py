from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .models import BriefRecord, DeepDiveDocumentRecord, DeepDiveRecord
from .session import build_session_factory
from ..store.base import parse_time, UTC


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return parse_time(str(value or ""))


def _json_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _json_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def load_state_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _upsert(session: Session, model: type, row_id: str, payload: dict[str, Any]) -> None:
    existing = session.get(model, row_id)
    if existing is None:
        session.add(model(**payload))
        return
    for key, value in payload.items():
        setattr(existing, key, value)


def _deep_dive_record_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record.get("id") or ""),
        "event_id": str(record.get("event_id") or ""),
        "status": str(record.get("status") or "pending"),
        "started_at": _dt(record.get("started_at")),
        "finished_at": _dt(record.get("finished_at")),
        "updated_at": _dt(record.get("updated_at")) or datetime.now(UTC),
        "attempted_count": int(record.get("attempted_count") or 0),
        "success_count": int(record.get("success_count") or 0),
        "failed_count": int(record.get("failed_count") or 0),
        "resolved_evidence_pack_json": _json_list(record.get("resolved_evidence_pack")),
        "facts_json": _json_list(record.get("facts")),
        "quotes_json": _json_list(record.get("quotes")),
        "timeline_json": _json_list(record.get("timeline")),
        "worthiness_json": _json_dict(record.get("worthiness")),
        "last_error": record.get("last_error"),
        "article_writing_guide": str(record.get("article_writing_guide") or ""),
    }


def _deep_dive_document_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    deep_dive_id = str(record.get("id") or "")
    event_id = str(record.get("event_id") or "")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(record.get("sources", [])):
        if not isinstance(item, dict):
            continue
        canonical_link = str(item.get("canonical_link") or "")
        original_link = str(item.get("original_link") or canonical_link)
        import hashlib
        row_hash = hashlib.sha256(f"{deep_dive_id}|{index}|{canonical_link or original_link}".encode("utf-8")).hexdigest()[:24]
        row_id = f"{deep_dive_id}:{index}:{row_hash}"
        rows.append(
            {
                "id": row_id,
                "deep_dive_id": deep_dive_id,
                "event_id": event_id,
                "source_key": str(item.get("source_key") or ""),
                "source_name": str(item.get("source_name") or ""),
                "original_link": original_link,
                "canonical_link": canonical_link or original_link,
                "title": str(item.get("title") or ""),
                "published_at": _dt(item.get("published_at")),
                "fetch_status": str(item.get("fetch_status") or "pending"),
                "extract_status": str(item.get("extract_status") or "pending"),
                "word_count": int(item.get("word_count") or 0),
                "cleaned_full_text": str(item.get("cleaned_full_text") or ""),
                "excerpt": str(item.get("excerpt") or ""),
                "quotes_json": _json_list(item.get("quotes")),
                "error": item.get("error"),
            }
        )
    return rows


def _brief_payload(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(brief.get("id") or ""),
        "event_id": str(brief.get("event_id") or ""),
        "deep_dive_id": str(brief.get("deep_dive_id") or ""),
        "brief_level": str(brief.get("brief_level") or "rule"),
        "stage": str(brief.get("stage") or "prepared"),
        "title": str(brief.get("title") or ""),
        "summary": str(brief.get("summary") or ""),
        "one_line": str(brief.get("one_line") or ""),
        "why_it_matters": str(brief.get("why_it_matters") or ""),
        "facts_json": _json_list(brief.get("facts")),
        "quotes_json": _json_list(brief.get("quotes")),
        "timeline_json": _json_list(brief.get("timeline")),
        "entity_names_json": _json_list(brief.get("entity_names")),
        "source_links_json": _json_list(brief.get("source_links")),
        "risk_notes_json": _json_list(brief.get("risk_notes")),
        "prompt_package_markdown": str(brief.get("prompt_package_markdown") or ""),
        "douyin_prompt_package_markdown": str(brief.get("douyin_prompt_package_markdown") or ""),
        "wechat_markdown": str(brief.get("wechat_markdown") or ""),
        "wechat_html": str(brief.get("wechat_html") or ""),
        "douyin_title": str(brief.get("douyin_title") or ""),
        "douyin_summary": str(brief.get("douyin_summary") or ""),
        "douyin_markdown": str(brief.get("douyin_markdown") or ""),
        "wechat_target_id": brief.get("wechat_target_id"),
        "wechat_editor_url": brief.get("wechat_editor_url"),
        "wechat_remote_appmsg_id": brief.get("wechat_remote_appmsg_id"),
        "preview_url": brief.get("preview_url"),
        "delivery_status": brief.get("delivery_status"),
        "delivery_attempt_count": int(brief.get("delivery_attempt_count") or 0),
        "last_delivery_attempt_at": _dt(brief.get("last_delivery_attempt_at")),
        "last_verified_at": _dt(brief.get("last_verified_at")),
        "last_delivery_error_kind": brief.get("last_delivery_error_kind"),
        "needs_resync": bool(brief.get("needs_resync", False)),
        "last_synced_revision": brief.get("last_synced_revision"),
        "last_successful_upload_at": _dt(brief.get("last_successful_upload_at")),
        "last_error": brief.get("last_error"),
        "updated_at": _dt(brief.get("updated_at")) or datetime.now(UTC),
        "driver_label": str(brief.get("driver_label") or ""),
        "record_status": str(brief.get("record_status") or "local_only"),
        "record_exception": brief.get("record_exception"),
        "draft_remote_updated_at": _dt(brief.get("draft_remote_updated_at")),
        "publish_record_published_at": _dt(brief.get("publish_record_published_at")),
        "workflow_mode": str(brief.get("workflow_mode") or "traditional"),
        "workflow_session_id": brief.get("workflow_session_id"),
        "read_count": int(brief.get("read_count") or 0),
        "like_count": int(brief.get("like_count") or 0),
        "share_count": int(brief.get("share_count") or 0),
        "recommend_count": int(brief.get("recommend_count") or 0),
        "comment_count": int(brief.get("comment_count") or 0),
        "highlight_count": int(brief.get("highlight_count") or 0),
        "tip_amount": str(brief.get("tip_amount") or "0.00"),
        "reprint_count": int(brief.get("reprint_count") or 0),
        "metrics_fetched_at": _dt(brief.get("metrics_fetched_at")),
    }


def sync_content_projection_from_state(state: dict[str, Any], *, database_url: str) -> dict[str, int]:
    session_factory = build_session_factory(database_url)
    counts = {"deep_dive_records": 0, "deep_dive_documents": 0, "brief_records": 0}
    with session_factory() as session:
        session.query(DeepDiveRecord).delete()
        session.query(DeepDiveDocumentRecord).delete()
        session.query(BriefRecord).delete()

        for record in state.get("event_deep_dives", []):
            if not isinstance(record, dict) or not record.get("id"):
                continue
            payload = _deep_dive_record_payload(record)
            _upsert(session, DeepDiveRecord, payload["id"], payload)
            counts["deep_dive_records"] += 1
            for document_payload in _deep_dive_document_rows(record):
                _upsert(session, DeepDiveDocumentRecord, document_payload["id"], document_payload)
                counts["deep_dive_documents"] += 1

        for brief in state.get("briefs", []):
            if not isinstance(brief, dict) or not brief.get("id"):
                continue
            payload = _brief_payload(brief)
            _upsert(session, BriefRecord, payload["id"], payload)
            counts["brief_records"] += 1
        session.commit()
    return counts


def sync_content_projection_from_state_file(path: Path, *, database_url: str) -> dict[str, int]:
    state = load_state_file(path)
    return sync_content_projection_from_state(state, database_url=database_url)
