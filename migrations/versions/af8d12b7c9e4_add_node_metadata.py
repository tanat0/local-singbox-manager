"""add node metadata

Revision ID: af8d12b7c9e4
Revises: d4e9c1a2f7b3
Create Date: 2026-05-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'af8d12b7c9e4'
down_revision: Union[str, None] = 'd4e9c1a2f7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('nodes', sa.Column('country_code', sa.String(length=8), nullable=True))
    op.add_column('nodes', sa.Column('country_name', sa.String(), nullable=True))
    op.add_column('nodes', sa.Column('provider_name', sa.String(), nullable=True))
    op.add_column('nodes', sa.Column('provider_suggestion', sa.String(), nullable=True))
    op.add_column('nodes', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('nodes', 'notes')
    op.drop_column('nodes', 'provider_suggestion')
    op.drop_column('nodes', 'provider_name')
    op.drop_column('nodes', 'country_name')
    op.drop_column('nodes', 'country_code')
