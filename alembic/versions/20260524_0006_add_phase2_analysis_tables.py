"""add phase 2 analysis tables

Revision ID: 20260524_0006
Revises: 20260524_0005
Create Date: 2026-05-24 00:06:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260524_0006"
down_revision = "20260524_0005"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _index_exists(bind: sa.Connection, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "topic_periodicity"):
        op.create_table(
            "topic_periodicity",
            sa.Column("topic_id", sa.String(length=64), primary_key=True),
            sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("period_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("confidence", sa.Numeric(6, 4), nullable=False, server_default="0"),
            sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if not _index_exists(bind, "topic_periodicity", "ix_topic_periodicity_detected"):
        op.create_index("ix_topic_periodicity_detected", "topic_periodicity", ["detected_at"])

    if not _table_exists(bind, "temporal_association_rules"):
        op.create_table(
            "temporal_association_rules",
            sa.Column("id", sa.String(length=128), primary_key=True),
            sa.Column("antecedent_event_id", sa.String(length=64), nullable=False),
            sa.Column("consequent_event_id", sa.String(length=64), nullable=False),
            sa.Column("lag_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("support", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("confidence", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("lift", sa.Numeric(8, 4), nullable=False, server_default="0"),
            sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if not _index_exists(bind, "temporal_association_rules", "ix_temporal_rules_antecedent"):
        op.create_index("ix_temporal_rules_antecedent", "temporal_association_rules", ["antecedent_event_id"])
    if not _index_exists(bind, "temporal_association_rules", "ix_temporal_rules_consequent"):
        op.create_index("ix_temporal_rules_consequent", "temporal_association_rules", ["consequent_event_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "temporal_association_rules"):
        if _index_exists(bind, "temporal_association_rules", "ix_temporal_rules_consequent"):
            op.drop_index("ix_temporal_rules_consequent", table_name="temporal_association_rules")
        if _index_exists(bind, "temporal_association_rules", "ix_temporal_rules_antecedent"):
            op.drop_index("ix_temporal_rules_antecedent", table_name="temporal_association_rules")
        op.drop_table("temporal_association_rules")
    if _table_exists(bind, "topic_periodicity"):
        if _index_exists(bind, "topic_periodicity", "ix_topic_periodicity_detected"):
            op.drop_index("ix_topic_periodicity_detected", table_name="topic_periodicity")
        op.drop_table("topic_periodicity")

