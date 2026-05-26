"""add content asset tables

Revision ID: 20260524_0002
Revises: 20260524_0001
Create Date: 2026-05-24 00:02:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import json


revision = "20260524_0002"
down_revision = "20260524_0001"
branch_labels = None
depends_on = None


def _json_server_default(bind: sa.Connection, value: object) -> sa.TextClause:
    rendered = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    suffix = "::json" if bind.dialect.name == "postgresql" else ""
    return sa.text(f"'{rendered}'{suffix}")


def _table_exists(bind: sa.Connection, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _index_exists(bind: sa.Connection, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def _index_matches_columns(bind: sa.Connection, table_name: str, columns: list[str]) -> bool:
    expected = tuple(columns)
    for index in sa.inspect(bind).get_indexes(table_name):
        if tuple(index.get("column_names") or ()) == expected:
            return True
    return False


def _column_type_name(bind: sa.Connection, table_name: str, column_name: str) -> str | None:
    for column in sa.inspect(bind).get_columns(table_name):
        if column["name"] == column_name:
            return str(column["type"]).upper()
    return None


def _ensure_index(bind: sa.Connection, index_name: str, table_name: str, columns: list[str]) -> None:
    if not _index_exists(bind, table_name, index_name) and not _index_matches_columns(bind, table_name, columns):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    json_list_default = _json_server_default(bind, [])
    json_dict_default = _json_server_default(bind, {})

    if not _table_exists(bind, "deep_dive_records"):
        op.create_table(
            "deep_dive_records",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("attempted_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("resolved_evidence_pack_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("facts_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("quotes_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("timeline_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("worthiness_json", sa.JSON(), nullable=False, server_default=json_dict_default),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("article_writing_guide", sa.Text(), nullable=False, server_default=""),
        )
    _ensure_index(bind, "ix_deep_dive_records_event_id", "deep_dive_records", ["event_id"])
    _ensure_index(bind, "ix_deep_dive_records_updated_at", "deep_dive_records", ["updated_at"])

    if not _table_exists(bind, "deep_dive_documents"):
        op.create_table(
            "deep_dive_documents",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("deep_dive_id", sa.String(length=64), nullable=False),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("source_key", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("source_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("original_link", sa.Text(), nullable=False, server_default=""),
            sa.Column("canonical_link", sa.Text(), nullable=False, server_default=""),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fetch_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("extract_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cleaned_full_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("excerpt", sa.Text(), nullable=False, server_default=""),
            sa.Column("quotes_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("error", sa.Text(), nullable=True),
        )
    else:
        id_type_name = _column_type_name(bind, "deep_dive_documents", "id")
        if id_type_name and "TEXT" not in id_type_name and "CLOB" not in id_type_name:
            if bind.dialect.name == "postgresql":
                op.alter_column(
                    "deep_dive_documents",
                    "id",
                    existing_type=sa.String(length=255),
                    type_=sa.Text(),
                    existing_nullable=False,
                    postgresql_using="id::text",
                )
            else:
                with op.batch_alter_table("deep_dive_documents", recreate="always") as batch_op:
                    batch_op.alter_column("id", existing_type=sa.String(length=255), type_=sa.Text(), existing_nullable=False)
    _ensure_index(bind, "ix_deep_dive_documents_deep_dive_id", "deep_dive_documents", ["deep_dive_id"])
    _ensure_index(bind, "ix_deep_dive_documents_event_id", "deep_dive_documents", ["event_id"])
    _ensure_index(bind, "ix_deep_dive_documents_canonical_link", "deep_dive_documents", ["canonical_link"])

    if not _table_exists(bind, "brief_records"):
        op.create_table(
            "brief_records",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("event_id", sa.String(length=64), nullable=False),
            sa.Column("deep_dive_id", sa.String(length=64), nullable=False),
            sa.Column("brief_level", sa.String(length=32), nullable=False, server_default="rule"),
            sa.Column("stage", sa.String(length=32), nullable=False, server_default="prepared"),
            sa.Column("title", sa.Text(), nullable=False, server_default=""),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("one_line", sa.Text(), nullable=False, server_default=""),
            sa.Column("why_it_matters", sa.Text(), nullable=False, server_default=""),
            sa.Column("facts_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("quotes_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("timeline_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("entity_names_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("source_links_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("risk_notes_json", sa.JSON(), nullable=False, server_default=json_list_default),
            sa.Column("prompt_package_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("douyin_prompt_package_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("wechat_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("wechat_html", sa.Text(), nullable=False, server_default=""),
            sa.Column("douyin_title", sa.Text(), nullable=False, server_default=""),
            sa.Column("douyin_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("douyin_markdown", sa.Text(), nullable=False, server_default=""),
            sa.Column("wechat_target_id", sa.String(length=128), nullable=True),
            sa.Column("wechat_editor_url", sa.Text(), nullable=True),
            sa.Column("wechat_remote_appmsg_id", sa.String(length=128), nullable=True),
            sa.Column("preview_url", sa.Text(), nullable=True),
            sa.Column("delivery_status", sa.String(length=32), nullable=True),
            sa.Column("delivery_attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_delivery_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_delivery_error_kind", sa.String(length=64), nullable=True),
            sa.Column("needs_resync", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_synced_revision", sa.String(length=128), nullable=True),
            sa.Column("last_successful_upload_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("driver_label", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("record_status", sa.String(length=32), nullable=False, server_default="local_only"),
            sa.Column("record_exception", sa.String(length=64), nullable=True),
            sa.Column("draft_remote_updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("publish_record_published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("workflow_mode", sa.String(length=32), nullable=False, server_default="traditional"),
            sa.Column("workflow_session_id", sa.String(length=128), nullable=True),
            sa.Column("read_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("share_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("recommend_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("highlight_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tip_amount", sa.String(length=32), nullable=False, server_default="0.00"),
            sa.Column("reprint_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metrics_fetched_at", sa.DateTime(timezone=True), nullable=True),
        )
    _ensure_index(bind, "ix_brief_records_event_id", "brief_records", ["event_id"])
    _ensure_index(bind, "ix_brief_records_deep_dive_id", "brief_records", ["deep_dive_id"])
    _ensure_index(bind, "ix_brief_records_updated_at", "brief_records", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_brief_records_updated_at", table_name="brief_records")
    op.drop_index("ix_brief_records_deep_dive_id", table_name="brief_records")
    op.drop_index("ix_brief_records_event_id", table_name="brief_records")
    op.drop_table("brief_records")

    op.drop_index("ix_deep_dive_documents_canonical_link", table_name="deep_dive_documents")
    op.drop_index("ix_deep_dive_documents_event_id", table_name="deep_dive_documents")
    op.drop_index("ix_deep_dive_documents_deep_dive_id", table_name="deep_dive_documents")
    op.drop_table("deep_dive_documents")

    op.drop_index("ix_deep_dive_records_updated_at", table_name="deep_dive_records")
    op.drop_index("ix_deep_dive_records_event_id", table_name="deep_dive_records")
    op.drop_table("deep_dive_records")
