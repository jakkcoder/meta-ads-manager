"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("effective_status", sa.String(length=32), nullable=True),
        sa.Column("objective", sa.String(length=64), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "leadgen_forms",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("page_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("leads_count", sa.Integer(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leadgen_forms_page_id", "leadgen_forms", ["page_id"])
    op.create_table(
        "sync_cursors",
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("cursor_value", sa.String(length=64), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("resource_type"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_object_id", "audit_log", ["object_id"])
    op.create_table(
        "ad_sets",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("effective_status", sa.String(length=32), nullable=True),
        sa.Column("daily_budget", sa.String(length=32), nullable=True),
        sa.Column("lifetime_budget", sa.String(length=32), nullable=True),
        sa.Column("targeting", sa.JSON(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ad_sets_campaign_id", "ad_sets", ["campaign_id"])
    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("form_id", sa.String(length=64), nullable=False),
        sa.Column("created_time", sa.DateTime(), nullable=True),
        sa.Column("ad_id", sa.String(length=64), nullable=True),
        sa.Column("adset_id", sa.String(length=64), nullable=True),
        sa.Column("campaign_id", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("is_organic", sa.Boolean(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["form_id"], ["leadgen_forms.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_leads_created_time", "leads", ["created_time"])
    op.create_index("ix_leads_form_id", "leads", ["form_id"])
    op.create_table(
        "ads",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("ad_set_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("effective_status", sa.String(length=32), nullable=True),
        sa.Column("creative_id", sa.String(length=64), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=True),
        sa.Column("updated_time", sa.DateTime(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["ad_set_id"], ["ad_sets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ads_ad_set_id", "ads", ["ad_set_id"])
    op.create_table(
        "lead_fields",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("field_name", sa.String(length=256), nullable=False),
        sa.Column("field_value", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_fields_field_name", "lead_fields", ["field_name"])
    op.create_index("ix_lead_fields_lead_id", "lead_fields", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_fields_lead_id", table_name="lead_fields")
    op.drop_index("ix_lead_fields_field_name", table_name="lead_fields")
    op.drop_table("lead_fields")
    op.drop_index("ix_ads_ad_set_id", table_name="ads")
    op.drop_table("ads")
    op.drop_index("ix_leads_form_id", table_name="leads")
    op.drop_index("ix_leads_created_time", table_name="leads")
    op.drop_table("leads")
    op.drop_index("ix_ad_sets_campaign_id", table_name="ad_sets")
    op.drop_table("ad_sets")
    op.drop_index("ix_audit_log_object_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("sync_cursors")
    op.drop_index("ix_leadgen_forms_page_id", table_name="leadgen_forms")
    op.drop_table("leadgen_forms")
    op.drop_table("campaigns")
