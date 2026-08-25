"""add node topology role

Revision ID: a8c1d4e6f2b0
Revises: f3a9b2c4d6e7
Create Date: 2026-08-25 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "a8c1d4e6f2b0"
down_revision = "f3a9b2c4d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nodes", sa.Column("topology_role", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("nodes", "topology_role")
