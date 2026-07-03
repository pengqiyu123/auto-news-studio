"""add analysis reports table

Revision ID: 20260524_0005
Revises: 20260524_0004
Create Date: 2026-05-24 00:05:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260524_0005"
down_revision = "20260524_0004"
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
    if not _table_exists(bind, "analysis_reports"):
        op.create_table(
            "analysis_reports",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("report_type", sa.String(length=16), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="ready"),
            sa.Column("content_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("sections_json", sa.JSON(), nullable=False, server_default=_json_default(bind, {})),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=_json_default(bind, {})),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if not _index_exists(bind, "analysis_reports", "ix_analysis_reports_created"):
        op.create_index("ix_analysis_reports_created", "analysis_reports", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "analysis_reports"):
        if _index_exists(bind, "analysis_reports", "ix_analysis_reports_created"):
            op.drop_index("ix_analysis_reports_created", table_name="analysis_reports")
        op.drop_table("analysis_reports")
