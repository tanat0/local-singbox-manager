"""add node tag to health check log

Revision ID: e7a9c2d1b8f0
Revises: c1a2b3d4e5f6
Create Date: 2026-06-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7a9c2d1b8f0"
down_revision: Union[str, None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("health_check_log", sa.Column("node_tag", sa.String(), nullable=True))
    op.create_index("ix_health_check_log_node_tag", "health_check_log", ["node_tag"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_health_check_log_node_tag", table_name="health_check_log")
    op.drop_column("health_check_log", "node_tag")
