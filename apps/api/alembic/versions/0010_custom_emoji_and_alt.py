"""Add CustomEmoji table and premium_emoji_alt."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0010_custom_emoji_and_alt"
down_revision = "0009_autopublish_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("premium_emoji_alt", sa.String(length=16), nullable=True),
    )
    op.create_table(
        "custom_emojis",
        sa.Column("document_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("alt", sa.String(length=64), nullable=False),
        sa.Column("stickerset_title", sa.String(length=255), nullable=True),
        sa.Column("stickerset_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("custom_emojis")
    op.drop_column("agent_configs", "premium_emoji_alt")
