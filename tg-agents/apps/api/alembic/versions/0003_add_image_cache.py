"""add image cache table

Revision ID: 0003_add_image_cache
Revises: 0002
Create Date: 2026-01-11 19:45:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_add_image_cache"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("query_hash", sa.String(length=255), nullable=False),
        sa.Column("image_path", sa.String(length=1000), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_image_cache_query_hash", "image_cache", ["query_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_image_cache_query_hash", table_name="image_cache")
    op.drop_table("image_cache")
