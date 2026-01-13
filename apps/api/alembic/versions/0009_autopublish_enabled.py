"""Add autopublish_enabled flag."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0009_autopublish_enabled"
down_revision = "0008_disable_source_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column(
            "autopublish_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.execute("UPDATE agent_configs SET autopublish_enabled = true")


def downgrade() -> None:
    op.drop_column("agent_configs", "autopublish_enabled")
