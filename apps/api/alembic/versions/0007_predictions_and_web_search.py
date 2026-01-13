"""Add predictions, web search and post kind."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0007_predictions_and_web_search"
down_revision = "0006_add_premium_emoji"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_configs",
        sa.Column(
            "predictions_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "gemini_web_search",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    postkind_enum = sa.Enum("news", "prediction", name="postkind")
    postkind_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "posts",
        sa.Column(
            "kind",
            postkind_enum,
            nullable=False,
            server_default="news",
        ),
    )


def downgrade() -> None:
    op.drop_column("posts", "kind")
    op.drop_column("agent_configs", "gemini_web_search")
    op.drop_column("agent_configs", "predictions_enabled")
    postkind_enum = sa.Enum("news", "prediction", name="postkind")
    postkind_enum.drop(op.get_bind(), checkfirst=True)
