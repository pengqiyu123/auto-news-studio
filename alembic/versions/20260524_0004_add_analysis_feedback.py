"""add analysis feedback table

Revision ID: 20260524_0004
Revises: 20260524_0003
Create Date: 2026-05-24 00:04:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260524_0004"
down_revision = "20260524_0003"
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


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "analysis_feedback"):
        op.create_table(
            "analysis_feedback",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("target_type", sa.String(length=32), nullable=False),
            sa.Column("target_id", sa.String(length=64), nullable=False),
            sa.Column("feedback_type", sa.String(length=16), nullable=False),
            sa.Column("correction_json", sa.JSON(), nullable=False, server_default=_json_default(bind, {})),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if not _index_exists(bind, "analysis_feedback", "ix_analysis_feedback_target"):
        op.create_index("ix_analysis_feedback_target", "analysis_feedback", ["target_type", "target_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "analysis_feedback"):
        if _index_exists(bind, "analysis_feedback", "ix_analysis_feedback_target"):
            op.drop_index("ix_analysis_feedback_target", table_name="analysis_feedback")
        op.drop_table("analysis_feedback")
