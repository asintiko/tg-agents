"""Add premium emoji fields to agent config."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_add_premium_emoji"
down_revision = "0005_add_brand_emoji"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_configs", sa.Column("premium_emoji_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "agent_configs",
        sa.Column(
            "premium_emoji_fallback",
            sa.String(length=16),
            nullable=True,
            server_default="⚡",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_configs", "premium_emoji_fallback")
    op.drop_column("agent_configs", "premium_emoji_id")
