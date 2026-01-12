"""Add brand emoji settings to agent configs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_add_brand_emoji"
down_revision = "0004_remove_bot_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("brand_emoji_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "brand_emoji_fallback",
            sa.String(length=16),
            nullable=True,
            server_default="⚽",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "brand_emoji_fallback")
    op.drop_column("agent_configs", "brand_emoji_id")
