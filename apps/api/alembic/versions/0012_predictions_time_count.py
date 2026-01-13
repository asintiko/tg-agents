"""Add predictions_time_msk and predictions_matches_count."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0012_predictions_time_count"
down_revision = "0011_web_search_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column("predictions_time_msk", sa.String(length=5), nullable=False, server_default="10:00"),
    )
    op.add_column(
        "agent_configs",
        sa.Column("predictions_matches_count", sa.Integer(), nullable=False, server_default="3"),
    )
    op.execute("UPDATE agent_configs SET predictions_time_msk='10:00' WHERE predictions_time_msk IS NULL")
    op.execute("UPDATE agent_configs SET predictions_matches_count=3 WHERE predictions_matches_count IS NULL")


def downgrade() -> None:
    op.drop_column("agent_configs", "predictions_matches_count")
    op.drop_column("agent_configs", "predictions_time_msk")
