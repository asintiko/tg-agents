"""Add web_search_enabled flag."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0011_web_search_enabled"
down_revision = "0010_custom_emoji_and_alt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column(
            "web_search_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.execute("UPDATE agent_configs SET web_search_enabled = false")


def downgrade() -> None:
    op.drop_column("agent_configs", "web_search_enabled")
