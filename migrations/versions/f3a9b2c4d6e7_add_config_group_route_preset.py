"""add config group route preset

Revision ID: f3a9b2c4d6e7
Revises: e7a9c2d1b8f0
Create Date: 2026-06-13 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "f3a9b2c4d6e7"
down_revision = "e7a9c2d1b8f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "config_groups",
        sa.Column("route_preset", sa.String(), nullable=False, server_default="full_tunnel"),
    )


def downgrade() -> None:
    op.drop_column("config_groups", "route_preset")
