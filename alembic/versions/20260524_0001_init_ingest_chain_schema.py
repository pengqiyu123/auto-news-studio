"""init ingest chain schema

Revision ID: 20260524_0001
Revises:
Create Date: 2026-05-24 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_connectors",
        sa.Column("source_key", sa.String(length=255), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default="rss"),
        sa.Column("driver", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False, server_default="rss"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("schedule", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("interval_minutes", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("weight", sa.Numeric(6, 3), nullable=False, server_default="0.7"),
        sa.Column("auth_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("capabilities_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("origin_repo", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("origin_license", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("health_status", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("health_detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "sync_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("source_key", sa.String(length=255), nullable=True),
        sa.Column("triggered_by", sa.String(length=64), nullable=False, server_default="dashboard"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("raw_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("discovery_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_sync_runs_source_key", "sync_runs", ["source_key"])

    op.create_table(
        "raw_items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("link", sa.Text(), nullable=False, server_default=""),
        sa.Column("canonical_link", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=512), nullable=True),
        sa.Column("source_native_id", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Numeric(10, 4), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_raw_items_collected_at_desc", "raw_items", ["collected_at"])
    op.create_index("ix_raw_items_source_key_collected_at", "raw_items", ["source_key", "collected_at"])

    op.create_table(
        "discovery_items_current",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("raw_item_id", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("source_kind", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("platform", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("link", sa.Text(), nullable=False, server_default=""),
        sa.Column("canonical_link", sa.Text(), nullable=False, server_default=""),
        sa.Column("dedupe_key", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("source_native_id", sa.String(length=255), nullable=True),
        sa.Column("title_tokens_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("anchor_tokens_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("engagement_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("item_state", sa.String(length=32), nullable=False, server_default="new_item"),
        sa.Column("entity_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("entity_names_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_discovery_items_current_collected_at", "discovery_items_current", ["collected_at"])
    op.create_index("ix_discovery_items_current_source_key", "discovery_items_current", ["source_key"])
    op.create_index("ix_discovery_items_current_raw_item_id", "discovery_items_current", ["raw_item_id"])

    op.create_table(
        "intel_events_current",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("representative_link", sa.Text(), nullable=False, server_default=""),
        sa.Column("representative_source_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("representative_discovery_item_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("discovery_item_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("source_keys_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("source_names_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("platforms_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("platform_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("story_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("member_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platform_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("anchor_tokens_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("velocity_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("coverage_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("freshness_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("audience_fit_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("composite_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("velocity_details_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("alert_state", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("change_state", sa.String(length=32), nullable=False, server_default="new_event"),
        sa.Column("alert_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("entity_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("entity_names_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("watchlisted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ignored", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deep_dive_id", sa.String(length=64), nullable=True),
        sa.Column("brief_id", sa.String(length=64), nullable=True),
        sa.Column("deep_dive_status", sa.String(length=32), nullable=True),
        sa.Column("deep_dive_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deep_dive_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deep_dive_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("brief_status", sa.String(length=32), nullable=True),
        sa.Column("deep_dive_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("worth_to_brief", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("worth_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_intel_events_current_last_seen_at", "intel_events_current", ["last_seen_at"])
    op.create_index("ix_intel_events_current_alert_state_score", "intel_events_current", ["alert_state", "composite_score"])

    op.create_table(
        "event_snapshots",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platform_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("velocity_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("coverage_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("freshness_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("audience_fit_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("composite_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("alert_state", sa.String(length=32), nullable=False, server_default="new"),
    )
    op.create_index("ix_event_snapshots_event_id", "event_snapshots", ["event_id"])
    op.create_index("ix_event_snapshots_event_id_captured_at", "event_snapshots", ["event_id", "captured_at"])

    op.create_table(
        "intel_alerts_current",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("level", sa.String(length=32), nullable=False, server_default="watch"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("velocity_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("coverage_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("freshness_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("audience_fit_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("composite_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("platform_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("representative_link", sa.Text(), nullable=False, server_default=""),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entity_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("entity_names_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("deep_dive_id", sa.String(length=64), nullable=True),
        sa.Column("brief_id", sa.String(length=64), nullable=True),
        sa.Column("deep_dive_status", sa.String(length=32), nullable=True),
        sa.Column("brief_status", sa.String(length=32), nullable=True),
        sa.Column("deep_dive_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("worth_to_brief", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("worth_reason", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_intel_alerts_current_event_id", "intel_alerts_current", ["event_id"])
    op.create_index("ix_intel_alerts_current_level", "intel_alerts_current", ["level"])
    op.create_index("ix_intel_alerts_current_triggered_at", "intel_alerts_current", ["triggered_at"])

    op.create_table(
        "intel_event_history",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("representative_link", sa.Text(), nullable=False, server_default=""),
        sa.Column("representative_source_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("change_state", sa.String(length=32), nullable=False, server_default="new_event"),
        sa.Column("alert_state", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("highest_level", sa.String(length=32), nullable=True),
        sa.Column("member_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platform_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("velocity_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("coverage_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("freshness_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("audience_fit_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("composite_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_intel_event_history_event_id", "intel_event_history", ["event_id"])
    op.create_index("ix_intel_event_history_event_id_recorded_at", "intel_event_history", ["event_id", "recorded_at"])

    op.create_table(
        "intel_alert_history",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("level", sa.String(length=32), nullable=False, server_default="watch"),
        sa.Column("highest_level", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("representative_link", sa.Text(), nullable=False, server_default=""),
        sa.Column("velocity_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("coverage_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("freshness_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("audience_fit_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("composite_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_intel_alert_history_event_id", "intel_alert_history", ["event_id"])
    op.create_index("ix_intel_alert_history_event_id_triggered_at", "intel_alert_history", ["event_id", "triggered_at"])


def downgrade() -> None:
    op.drop_index("ix_intel_alert_history_event_id_triggered_at", table_name="intel_alert_history")
    op.drop_index("ix_intel_alert_history_event_id", table_name="intel_alert_history")
    op.drop_table("intel_alert_history")

    op.drop_index("ix_intel_event_history_event_id_recorded_at", table_name="intel_event_history")
    op.drop_index("ix_intel_event_history_event_id", table_name="intel_event_history")
    op.drop_table("intel_event_history")

    op.drop_index("ix_intel_alerts_current_triggered_at", table_name="intel_alerts_current")
    op.drop_index("ix_intel_alerts_current_level", table_name="intel_alerts_current")
    op.drop_index("ix_intel_alerts_current_event_id", table_name="intel_alerts_current")
    op.drop_table("intel_alerts_current")

    op.drop_index("ix_event_snapshots_event_id_captured_at", table_name="event_snapshots")
    op.drop_index("ix_event_snapshots_event_id", table_name="event_snapshots")
    op.drop_table("event_snapshots")

    op.drop_index("ix_intel_events_current_alert_state_score", table_name="intel_events_current")
    op.drop_index("ix_intel_events_current_last_seen_at", table_name="intel_events_current")
    op.drop_table("intel_events_current")

    op.drop_index("ix_discovery_items_current_raw_item_id", table_name="discovery_items_current")
    op.drop_index("ix_discovery_items_current_source_key", table_name="discovery_items_current")
    op.drop_index("ix_discovery_items_current_collected_at", table_name="discovery_items_current")
    op.drop_table("discovery_items_current")

    op.drop_index("ix_raw_items_source_key_collected_at", table_name="raw_items")
    op.drop_index("ix_raw_items_collected_at_desc", table_name="raw_items")
    op.drop_table("raw_items")

    op.drop_index("ix_sync_runs_source_key", table_name="sync_runs")
    op.drop_table("sync_runs")

    op.drop_table("source_connectors")
