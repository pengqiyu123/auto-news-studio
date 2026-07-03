"""add analysis batch run records

Revision ID: 20260524_0007
Revises: 20260524_0006
Create Date: 2026-05-24 00:07:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0007"
down_revision = "20260524_0006"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _index_exists(bind: sa.Connection, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "analysis_batch_runs"):
        op.create_table(
            "analysis_batch_runs",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("task_name", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("items_processed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        )
    if not _index_exists(bind, "analysis_batch_runs", "ix_analysis_batch_runs_task_started"):
        op.create_index("ix_analysis_batch_runs_task_started", "analysis_batch_runs", ["task_name", "started_at"])
    if not _index_exists(bind, "analysis_batch_runs", "ix_analysis_batch_runs_status"):
        op.create_index("ix_analysis_batch_runs_status", "analysis_batch_runs", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "analysis_batch_runs"):
        if _index_exists(bind, "analysis_batch_runs", "ix_analysis_batch_runs_status"):
            op.drop_index("ix_analysis_batch_runs_status", table_name="analysis_batch_runs")
        if _index_exists(bind, "analysis_batch_runs", "ix_analysis_batch_runs_task_started"):
            op.drop_index("ix_analysis_batch_runs_task_started", table_name="analysis_batch_runs")
        op.drop_table("analysis_batch_runs")
