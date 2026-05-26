from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SourceConnectorRecord(Base):
    __tablename__ = "source_connectors"

    source_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="rss")
    driver: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="rss")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    schedule: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    weight: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, default=0.7)
    auth_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    capabilities_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    origin_repo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    origin_license: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    health_status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    health_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncRunRecord(Base):
    __tablename__ = "sync_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False, default="dashboard")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discovery_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RawItemRecord(Base):
    __tablename__ = "raw_items"
    __table_args__ = (
        Index("ix_raw_items_collected_at_desc", "collected_at"),
        Index("ix_raw_items_source_key_collected_at", "source_key", "collected_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    canonical_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_native_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class DiscoveryItemCurrentRecord(Base):
    __tablename__ = "discovery_items_current"
    __table_args__ = (
        Index("ix_discovery_items_current_collected_at", "collected_at"),
        Index("ix_discovery_items_current_source_key", "source_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    raw_item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    canonical_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dedupe_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    source_native_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title_tokens_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    anchor_tokens_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    engagement_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    item_state: Mapped[str] = mapped_column(String(32), nullable=False, default="new_item")
    entity_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    entity_names_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class IntelEventCurrentRecord(Base):
    __tablename__ = "intel_events_current"
    __table_args__ = (
        Index("ix_intel_events_current_last_seen_at", "last_seen_at"),
        Index("ix_intel_events_current_alert_state_score", "alert_state", "composite_score"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    representative_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    representative_source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    representative_discovery_item_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    discovery_item_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_keys_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_names_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    platforms_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    platform_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    story_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    member_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    platform_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latest_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    anchor_tokens_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    velocity_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    coverage_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    freshness_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    audience_fit_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    composite_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    velocity_details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    alert_state: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    change_state: Mapped[str] = mapped_column(String(32), nullable=False, default="new_event")
    alert_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    entity_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    entity_names_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    watchlisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deep_dive_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brief_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deep_dive_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deep_dive_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deep_dive_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deep_dive_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    brief_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deep_dive_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    worth_to_brief: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    worth_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class EventSnapshotRecord(Base):
    __tablename__ = "event_snapshots"
    __table_args__ = (
        Index("ix_event_snapshots_event_id_captured_at", "event_id", "captured_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    platform_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    velocity_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    coverage_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    freshness_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    audience_fit_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    composite_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    alert_state: Mapped[str] = mapped_column(String(32), nullable=False, default="new")


class IntelAlertCurrentRecord(Base):
    __tablename__ = "intel_alerts_current"
    __table_args__ = (
        Index("ix_intel_alerts_current_triggered_at", "triggered_at"),
        Index("ix_intel_alerts_current_level", "level"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="watch")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    velocity_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    coverage_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    freshness_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    audience_fit_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    composite_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    platform_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    representative_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entity_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    entity_names_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    deep_dive_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brief_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deep_dive_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    brief_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deep_dive_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    worth_to_brief: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    worth_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")


class IntelEventHistoryRecord(Base):
    __tablename__ = "intel_event_history"
    __table_args__ = (
        Index("ix_intel_event_history_event_id_recorded_at", "event_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    representative_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    representative_source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    change_state: Mapped[str] = mapped_column(String(32), nullable=False, default="new_event")
    alert_state: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    highest_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    platform_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    velocity_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    coverage_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    freshness_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    audience_fit_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    composite_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class IntelAlertHistoryRecord(Base):
    __tablename__ = "intel_alert_history"
    __table_args__ = (
        Index("ix_intel_alert_history_event_id_triggered_at", "event_id", "triggered_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[str] = mapped_column(String(32), nullable=False, default="watch")
    highest_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    representative_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    velocity_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    coverage_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    freshness_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    audience_fit_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    composite_score: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detail_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class DeepDiveRecord(Base):
    __tablename__ = "deep_dive_records"
    __table_args__ = (
        Index("ix_deep_dive_records_event_id", "event_id"),
        Index("ix_deep_dive_records_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_evidence_pack_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    facts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    quotes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    timeline_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    worthiness_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_writing_guide: Mapped[str] = mapped_column(Text, nullable=False, default="")


class DeepDiveDocumentRecord(Base):
    __tablename__ = "deep_dive_documents"
    __table_args__ = (
        Index("ix_deep_dive_documents_deep_dive_id", "deep_dive_id"),
        Index("ix_deep_dive_documents_event_id", "event_id"),
        Index("ix_deep_dive_documents_canonical_link", "canonical_link"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    deep_dive_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    original_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    canonical_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetch_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    extract_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cleaned_full_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    quotes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class BriefRecord(Base):
    __tablename__ = "brief_records"
    __table_args__ = (
        Index("ix_brief_records_event_id", "event_id"),
        Index("ix_brief_records_deep_dive_id", "deep_dive_id"),
        Index("ix_brief_records_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    deep_dive_id: Mapped[str] = mapped_column(String(64), nullable=False)
    brief_level: Mapped[str] = mapped_column(String(32), nullable=False, default="rule")
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="prepared")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    one_line: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False, default="")
    facts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    quotes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    timeline_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    entity_names_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_links_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_notes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    prompt_package_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    douyin_prompt_package_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wechat_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wechat_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    douyin_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    douyin_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    douyin_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    wechat_target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wechat_editor_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    wechat_remote_appmsg_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    delivery_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_delivery_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_delivery_error_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    needs_resync: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_synced_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_successful_upload_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    driver_label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    record_status: Mapped[str] = mapped_column(String(32), nullable=False, default="local_only")
    record_exception: Mapped[str | None] = mapped_column(String(64), nullable=True)
    draft_remote_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_record_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workflow_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="traditional")
    workflow_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    read_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    share_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recommend_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    highlight_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tip_amount: Mapped[str] = mapped_column(String(32), nullable=False, default="0.00")
    reprint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
