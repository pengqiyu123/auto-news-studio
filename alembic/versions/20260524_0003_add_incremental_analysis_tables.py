"""add incremental analysis tables

Revision ID: 20260524_0003
Revises: 20260524_0002
Create Date: 2026-05-24 00:03:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260524_0003"
down_revision = "20260524_0002"
branch_labels = None
depends_on = None


def _json_default(bind: sa.Connection, value: object) -> sa.TextClause:
    suffix = "::json" if bind.dialect.name == "postgresql" else ""
    rendered = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return sa.text(f"'{rendered}'{suffix}")


def _table_exists(bind: sa.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _index_exists(bind: sa.Connection, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def _ensure_index(bind: sa.Connection, index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    json_list_default = _json_default(bind, [])
    json_dict_default = _json_default(bind, {})

    if not _table_exists(bind, "topic_models"):
        op.create_table(
            "topic_models",
            sa.Column("topic_id", sa.String(length=64), primary_key=True),
            sa.Column("keywords_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if not _table_exists(bind, "event_topics"):
        op.create_table(
            "event_topics",
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("topic_id", sa.String(length=64), sa.ForeignKey("topic_models.topic_id"), nullable=False),
            sa.Column("weight", sa.Numeric(6, 4), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("event_id", "topic_id"),
        )
    _ensure_index(bind, "ix_event_topics_topic_id", "event_topics", ["topic_id"])

    if not _table_exists(bind, "event_relations"):
        op.create_table(
            "event_relations",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("source_event_id", sa.String(length=64), nullable=False),
            sa.Column("target_event_id", sa.String(length=64), nullable=False),
            sa.Column("relation_type", sa.String(length=32), nullable=False),
            sa.Column("weight", sa.Numeric(6, 4), nullable=False, server_default="0"),
            sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=json_dict_default),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    _ensure_index(bind, "ix_event_relations_source", "event_relations", ["source_event_id"])
    _ensure_index(bind, "ix_event_relations_target", "event_relations", ["target_event_id"])

    if not _table_exists(bind, "trend_signals"):
        op.create_table(
            "trend_signals",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("entity_id", sa.String(length=64), nullable=False),
            sa.Column("signal_type", sa.String(length=32), nullable=False),
            sa.Column("signal_value", sa.Numeric(10, 4), nullable=False, server_default="0"),
            sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
            sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    _ensure_index(bind, "ix_trend_signals_entity", "trend_signals", ["entity_id"])

    if not _table_exists(bind, "daily_event_metrics"):
        op.create_table(
            "daily_event_metrics",
            sa.Column("metric_date", sa.Date(), nullable=False),
            sa.Column("entity_id", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("avg_composite_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
            sa.Column("max_velocity_score", sa.Numeric(10, 4), nullable=False, server_default="0"),
            sa.Column("breakout_count", sa.Integer(), nullable=False, server_default="0"),
            sa.PrimaryKeyConstraint("metric_date", "entity_id"),
        )
    _ensure_index(bind, "ix_daily_metrics_date", "daily_event_metrics", ["metric_date"])

    if bind.dialect.name == "postgresql" and _table_exists(bind, "intel_events_current"):
        op.execute(
            """
            create index if not exists ix_events_entity_ids_gin
            on intel_events_current using gin ((entity_ids_json::jsonb) jsonb_path_ops)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("drop index if exists ix_events_entity_ids_gin")
    op.drop_index("ix_daily_metrics_date", table_name="daily_event_metrics")
    op.drop_table("daily_event_metrics")
    op.drop_index("ix_trend_signals_entity", table_name="trend_signals")
    op.drop_table("trend_signals")
    op.drop_index("ix_event_relations_target", table_name="event_relations")
    op.drop_index("ix_event_relations_source", table_name="event_relations")
    op.drop_table("event_relations")
    op.drop_index("ix_event_topics_topic_id", table_name="event_topics")
    op.drop_table("event_topics")
    op.drop_table("topic_models")
