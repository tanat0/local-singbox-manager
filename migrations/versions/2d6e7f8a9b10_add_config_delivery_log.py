"""add config delivery log

Revision ID: 2d6e7f8a9b10
Revises: 9ab4d1f2c8e0
Create Date: 2026-05-18 07:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "2d6e7f8a9b10"
down_revision = "9ab4d1f2c8e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "config_delivery_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("managed_user_id", sa.Integer(), nullable=True),
        sa.Column("telegram_id", sa.String(), nullable=False),
        sa.Column("config_group_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["managed_user_id"], ["managed_users.id"]),
        sa.ForeignKeyConstraint(["config_group_id"], ["config_groups.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("config_delivery_log")
