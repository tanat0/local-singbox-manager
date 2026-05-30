"""add admin action log

Revision ID: 7c0f3a2e9d11
Revises: af8d12b7c9e4
Create Date: 2026-05-18 06:45:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "7c0f3a2e9d11"
down_revision = "af8d12b7c9e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_action_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("admin_action_log")
