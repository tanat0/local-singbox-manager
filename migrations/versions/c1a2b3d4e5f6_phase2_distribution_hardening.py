"""phase2 distribution hardening

Revision ID: c1a2b3d4e5f6
Revises: 2d6e7f8a9b10
Create Date: 2026-05-23 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c1a2b3d4e5f6"
down_revision = "2d6e7f8a9b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("config_groups", sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("config_groups", sa.Column("refresh_limit_per_hour", sa.Integer(), nullable=True))
    op.add_column("config_groups", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("managed_users", sa.Column("refresh_limit_per_hour", sa.Integer(), nullable=True))
    op.add_column("config_delivery_log", sa.Column("config_version", sa.Integer(), nullable=True))
    op.add_column("config_delivery_log", sa.Column("config_fingerprint", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("config_delivery_log", "config_fingerprint")
    op.drop_column("config_delivery_log", "config_version")
    op.drop_column("managed_users", "refresh_limit_per_hour")
    op.drop_column("config_groups", "updated_at")
    op.drop_column("config_groups", "refresh_limit_per_hour")
    op.drop_column("config_groups", "config_version")
