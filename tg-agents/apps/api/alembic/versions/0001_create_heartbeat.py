"""Create heartbeat table

Revision ID: 0001
Revises: 
Create Date: 2026-01-11 17:45:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "heartbeat",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("note", sa.String(length=255), nullable=False, server_default="init"),
    )


def downgrade() -> None:
    op.drop_table("heartbeat")
