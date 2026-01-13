"""Set include_source_link default to false and update existing configs."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0008_disable_source_links"
down_revision = "0007_predictions_and_web_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "agent_configs",
        "include_source_link",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
    )
    op.execute("UPDATE agent_configs SET include_source_link = false")


def downgrade() -> None:
    op.alter_column(
        "agent_configs",
        "include_source_link",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
    )
